from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend.common.artifacts import create_artifact_dir, dump_json, latest_artifact_dir, load_joblib
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, build_region_grid
from backend.common.real_features import (
    build_real_feature_row,
    extract_cell_terrain,
    fetch_forecast_weather_profile,
    select_hourly_weather_sample,
)
from backend.common.regions import load_regions, repo_root
from backend.common.runout import RUN_PHYSICS_RUNOUT, build_runout_polygons
from backend.common.supabase_io import has_supabase_credentials, patch_first_row, rest_upsert
from backend.common.training_dataset import load_training_frame
from backend.train_model import fit_model


def risk_level(probability: float) -> int:
    if probability < 0.15:
        return 1
    if probability < 0.30:
        return 2
    if probability < 0.50:
        return 3
    if probability < 0.70:
        return 4
    return 5


def uncertainty_class(span: float) -> str:
    if span > 0.30:
        return 'high'
    if span > 0.18:
        return 'medium'
    return 'low'


def cell_probabilities(base_model, x_sel: pd.DataFrame) -> np.ndarray:
    trees = getattr(base_model, 'estimators_', [])
    if not trees:
        return np.zeros(len(x_sel))
    tree_probs = np.column_stack([tree.predict_proba(x_sel)[:, 1] for tree in trees])
    return tree_probs


def top_feature_contributions(row: pd.Series, selected_features: list[str], feature_means: dict[str, float], feature_importances: np.ndarray) -> dict[str, float]:
    contributions = {
        feature: float((row[feature] - feature_means.get(feature, 0.0)) * importance)
        for feature, importance in zip(selected_features, feature_importances)
    }
    return dict(sorted(contributions.items(), key=lambda item: abs(item[1]), reverse=True)[:5])


def compute_tree_shap(explainer, selected_frame: pd.DataFrame, selected_features: list[str]) -> tuple[dict[str, float], list[dict[str, float | str | int]]]:
    shap_values = explainer.shap_values(selected_frame)
    if isinstance(shap_values, list):
        shap_vector = np.asarray(shap_values[-1])[0]
    else:
        shap_array = np.asarray(shap_values)
        if shap_array.ndim == 3:
            shap_vector = shap_array[0, :, -1]
        else:
            shap_vector = shap_array[0]

    feature_values = selected_frame.iloc[0].to_dict()
    ordered = sorted(
        [
            {
                'feature': feature,
                'shap_value': float(value),
                'feature_value': float(feature_values[feature]),
            }
            for feature, value in zip(selected_features, shap_vector)
        ],
        key=lambda item: abs(float(item['shap_value'])),
        reverse=True,
    )[:5]
    for rank, item in enumerate(ordered, start=1):
        item['rank'] = rank
    return (
        {item['feature']: float(item['shap_value']) for item in ordered},
        ordered,
    )


def build_cells(region, bundle, grid_size: int, forecast_date: pd.Timestamp):
    selector = bundle['selector']
    calibrated_model = bundle['calibrated_model']
    base_model = bundle['base_model']
    selected_features: list[str] = bundle['selected_features']
    feature_means: dict[str, float] = bundle['feature_means']
    region_grid = build_region_grid(region, grid_size=grid_size)
    weather_profile = fetch_forecast_weather_profile(region.center, forecast_date.to_pydatetime(), 72)
    weather_sample = select_hourly_weather_sample(weather_profile, forecast_date.to_pydatetime())
    import shap

    explainer = shap.TreeExplainer(base_model)
    dem_path = repo_root() / 'backend' / 'data' / 'dem' / f'{region.key}.tif'
    rows = []

    for cell in region_grid:
        center_lat = float(cell['lat'] + (cell['lat_end'] - cell['lat']) / 2)
        center_lng = float(cell['lng'] + (cell['lng_end'] - cell['lng']) / 2)
        terrain = extract_cell_terrain(str(dem_path), lat=center_lat, lng=center_lng)
        assembled = build_real_feature_row(
            weather_sample=weather_sample,
            terrain=terrain,
            timestamp=forecast_date.to_pydatetime(),
            lat=center_lat,
            lng=center_lng,
        )
        feature_row = assembled['feature_row']
        feature_frame = pd.DataFrame([feature_row], columns=FEATURE_COLUMNS)
        selected_frame = pd.DataFrame(selector.transform(feature_frame), columns=selected_features)
        probabilities = cell_probabilities(base_model, selected_frame)
        calibrated_probability = float(calibrated_model.predict_proba(selected_frame)[0, 1])
        mean_probability = float(probabilities.mean()) if probabilities.size else calibrated_probability
        variance = float(probabilities.var()) if probabilities.size else 0.0
        confidence_lower = float(max(0.0, mean_probability - 1.96 * np.sqrt(variance)))
        confidence_upper = float(min(1.0, mean_probability + 1.96 * np.sqrt(variance)))
        span = confidence_upper - confidence_lower
        risk = risk_level(calibrated_probability)
        shap_values, shap_context = compute_tree_shap(explainer, selected_frame, selected_features)
        dominant_driver = shap_context[0]['feature'] if shap_context else None
        rows.append({
            'row': int(cell['row']),
            'col': int(cell['col']),
            'lat': center_lat,
            'lng': center_lng,
            'lat_end': float(cell['lat_end']),
            'lng_end': float(cell['lng_end']),
            'risk_score': risk,
            'probability': calibrated_probability,
            'confidence_lower': confidence_lower,
            'confidence_upper': confidence_upper,
            'uncertainty_span': span,
            'uncertainty_class': uncertainty_class(span),
            'hazard': calibrated_probability,
            'exposure': float(np.clip(feature_row['elevation'] * 0.55 + feature_row['terrain_roughness'] * 0.45, 0, 1)),
            'vulnerability': float(np.clip(feature_row['aspect_loading'] * 0.6 + feature_row['wind_loading'] * 0.4, 0, 1)),
            'problem_type': ['Storm Slab', 'Wind Slab', 'Persistent Slab', 'Deep Persistent Slab', 'Wet Loose'][min(4, risk - 1)],
            'shap_values': shap_values,
            'shap_context': {'top_features': shap_context},
            'feature_values': selected_frame.iloc[0].to_dict(),
            'explanation_summary': None,
            'coverage_flags': {
                'sar_coverage_state': 'not_applicable',
                'residual_shadow': False,
                'data_gaps': [],
            },
            'selected_features': selected_features,
            'weather_inputs': {
                'snowfall_24h': feature_row['snowfall_24h'],
                'wind_loading': feature_row['wind_loading'],
                'temp_gradient': feature_row['temp_gradient'],
                'freezing_level_proxy': feature_row['freezing_level_proxy'],
                'temperature_2m': assembled['raw_inputs']['temperature_2m'],
                'windspeed_10m': assembled['raw_inputs']['windspeed_10m'],
                'winddirection_10m': assembled['raw_inputs']['winddirection_10m'],
                'downscaled_temperature_c': assembled['raw_inputs']['downscaled_temperature_c'],
                'snowfall_24h_cm': assembled['raw_inputs']['snowfall_24h_cm'],
                'precipitation_24h_mm': assembled['raw_inputs']['precipitation_24h_mm'],
            },
            'terrain_inputs': {
                'slope': feature_row['slope'],
                'elevation': feature_row['elevation'],
                'aspect_loading': feature_row['aspect_loading'],
                'terrain_roughness': feature_row['terrain_roughness'],
                'elevation_m': terrain['elevation_m'],
                'slope_angle_deg': terrain['slope_angle_deg'],
                'aspect_deg': terrain['aspect_deg'],
            },
            'dominant_driver_feature': dominant_driver,
            'runout_seed': risk >= 4,
            'inference_backend': 'github_actions',
            'model_version': bundle['created_at'],
            'calibration_profile': bundle['calibration_method'],
            'snowpack_proxy': {
                'estimated_shear_strength': assembled['snowpack_proxy'].estimated_shear_strength,
                'snow_settlement_index': assembled['snowpack_proxy'].snow_settlement_index,
                'season_start': assembled['snowpack_proxy'].season_start,
                'method': assembled['snowpack_proxy'].method,
            },
        })

    return rows


def upsert_forecast_grid(region, bundle, forecast_date: pd.Timestamp, rows: list[dict[str, object]], horizon_hours: int):
    weather_inputs = [row['weather_inputs'] for row in rows if isinstance(row.get('weather_inputs'), dict)]
    terrain_inputs = [row['terrain_inputs'] for row in rows if isinstance(row.get('terrain_inputs'), dict)]
    snowfall_avg = float(np.mean([item.get('snowfall_24h_cm', item.get('snowfall_24h', 0) * 40) for item in weather_inputs])) if weather_inputs else 0.0
    wind_avg = float(np.mean([item.get('windspeed_10m', item.get('wind_loading', 0) * 55) for item in weather_inputs])) if weather_inputs else 0.0
    temperature_avg = float(np.mean([item.get('downscaled_temperature_c', item.get('temperature_2m', 0)) for item in weather_inputs])) if weather_inputs else 0.0
    precipitation_avg = float(np.mean([item.get('precipitation_24h_mm', item.get('snowfall_24h', 0) * 45) for item in weather_inputs])) if weather_inputs else 0.0
    snow_depth_proxy = float(np.mean([item.get('snowfall_24h_cm', 0.0) for item in weather_inputs])) if weather_inputs else 0.0
    # Story 18: physics-aware Alpha-Beta runout polygons with OOM-guarded DEM
    # crop. Behind RUN_PHYSICS_RUNOUT flag; falls back to analytical Alpha-Beta
    # then to rectangular polygons when DEM / whitebox / rasterio missing.
    runout_polygons = build_runout_polygons(region.key, rows)
    payload = {
        'hazard_type': 'avalanche',
        'region_key': region.key,
        'region_name': region.name,
        'forecast_date': forecast_date.date().isoformat(),
        'horizon_hours': horizon_hours,
        'bbox': list(region.bbox),
        'grid_geojson': rows,
        'runout_polygons': runout_polygons,
        'weather_summary': {
            'snowfall_24h': f'{snowfall_avg:.1f}',
            'wind_speed': f'{wind_avg:.1f}',
            'temperature': f'{temperature_avg:.1f}',
            'precipitation': f'{precipitation_avg:.1f}',
            'snow_depth': f'{snow_depth_proxy:.1f}',
            'generated_at': forecast_date.isoformat(),
            'cell_count': len(rows),
            'source': 'open_meteo_forecast_downscaled_v1',
        },
        'model_metadata': {
            'model_version': bundle['created_at'],
            'selected_features': bundle['selected_features'],
            'feature_columns': bundle['feature_columns'],
            'calibration_profile': bundle['calibration_method'],
            'resampling': bundle['resampling'],
            'tree_variance_policy': bundle.get('tree_variance_policy'),
            'pss_metrics': bundle.get('metrics', {}),
            'cv_metrics': bundle.get('cv_metrics'),
            'threshold_profile': 'heuristic-risk-bands-v1',
            'run_physics_runout': RUN_PHYSICS_RUNOUT,
            'runout_method_sample': next((rp.get('method') for rp in runout_polygons if rp.get('method') and rp.get('method') != 'deferred_oom_guard'), None),
            'dominant_driver_strategy': 'top_absolute_tree_shap_v1',
            'training_dataset_version': bundle.get('training_dataset_version'),
        },
        'status': 'ready',
    }
    if has_supabase_credentials():
        rest_upsert('forecast_grids', [payload], on_conflict='hazard_type,region_key,forecast_date,horizon_hours')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate forecast grids for Avalanche Insight Hub')
    parser.add_argument('--artifact-root', type=Path, default=load_settings().artifact_root)
    parser.add_argument('--forecast-hours', type=int, default=load_settings().forecast_horizon_hours)
    parser.add_argument('--grid-size', type=int, default=load_settings().grid_size)
    parser.add_argument('--dry-run', action='store_true', default=load_settings().dry_run)
    args = parser.parse_args()

    try:
        artifact_dir = latest_artifact_dir(args.artifact_root)
        bundle = load_joblib(artifact_dir / 'model.joblib')
    except FileNotFoundError:
        artifact_dir = create_artifact_dir(args.artifact_root)
        settings = load_settings()
        frame, dataset_manifest = load_training_frame(
            seed=settings.seed,
            samples_per_region=max(50, settings.samples_per_region // 4),
            grid_size=settings.grid_size,
            allow_synthetic_bootstrap=os.getenv('ALLOW_SYNTHETIC_BOOTSTRAP', 'false').lower() in ('1', 'true', 'yes'),
        )
        bundle = fit_model(seed=settings.seed, frame=frame, dataset_manifest=dataset_manifest)
        dump_json(artifact_dir / 'feature_schema.json', {
            'feature_columns': bundle['feature_columns'],
            'selected_features': bundle['selected_features'],
            'feature_means': bundle['feature_means'],
        })
        dump_json(artifact_dir / 'training_metrics.json', {
            'bootstrap_fallback': True,
            'selected_features': bundle['selected_features'],
            'metrics': bundle['metrics'],
        })
        from backend.common.artifacts import dump_joblib
        dump_joblib(artifact_dir / 'model.joblib', bundle)
    forecast_date = pd.Timestamp(datetime.now(timezone.utc))
    regions = load_regions()

    outputs = []
    for region in regions:
        rows = build_cells(region, bundle, grid_size=args.grid_size, forecast_date=forecast_date)
        payload = upsert_forecast_grid(region, bundle, forecast_date, rows, horizon_hours=args.forecast_hours)
        outputs.append(payload)

    dump_json(artifact_dir / 'forecast_grids.json', outputs)

    if has_supabase_credentials():
        patch_first_row('model_status', {
            'version': f"forecast-{artifact_dir.name}",
            'next_run': None,
        })

    print(json.dumps({'artifact_dir': str(artifact_dir), 'regions_written': len(outputs)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
