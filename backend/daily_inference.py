from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend.common.artifacts import create_artifact_dir, dump_json, latest_artifact_dir, load_joblib
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, SampleContext, build_feature_row, build_region_grid
from backend.common.regions import load_regions
from backend.common.supabase_io import has_supabase_credentials, patch_first_row, rest_upsert
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


def build_cells(region, bundle, grid_size: int, forecast_date: pd.Timestamp):
    selector = bundle['selector']
    calibrated_model = bundle['calibrated_model']
    base_model = bundle['base_model']
    selected_features: list[str] = bundle['selected_features']
    feature_means: dict[str, float] = bundle['feature_means']
    feature_importances = getattr(base_model, 'feature_importances_', np.ones(len(selected_features)) / max(1, len(selected_features)))
    region_grid = build_region_grid(region, grid_size=grid_size)
    rng_seed = int(hashlib.sha256(f'{region.key}:{forecast_date.date().isoformat()}'.encode('utf-8')).hexdigest()[:8], 16)
    rng = np.random.default_rng(rng_seed)
    rows = []

    for cell in region_grid:
        context = SampleContext(
            region_key=region.key,
            region_name=region.name,
            timestamp=forecast_date,
            lat=cell['lat'],
            lng=cell['lng'],
            row=int(cell['row']),
            col=int(cell['col']),
        )
        feature_row = build_feature_row(context, rng)
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
        shap = top_feature_contributions(pd.Series(feature_row), selected_features, feature_means, feature_importances)
        rows.append({
            'row': int(cell['row']),
            'col': int(cell['col']),
            'lat': float(cell['lat']),
            'lng': float(cell['lng']),
            'lat_end': float(cell['lat_end']),
            'lng_end': float(cell['lng_end']),
            'risk_score': risk,
            'probability': calibrated_probability,
            'confidence_lower': confidence_lower,
            'confidence_upper': confidence_upper,
            'uncertainty_span': span,
            'uncertainty_class': uncertainty_class(span),
            'hazard': float(np.clip(calibrated_probability * 0.9 + feature_row['snowfall_24h'] * 0.1, 0, 1)),
            'exposure': float(np.clip(feature_row['elevation'] * 0.55 + feature_row['terrain_roughness'] * 0.45, 0, 1)),
            'vulnerability': float(np.clip(feature_row['aspect_loading'] * 0.6 + feature_row['wind_loading'] * 0.4, 0, 1)),
            'problem_type': ['Storm Slab', 'Wind Slab', 'Persistent Slab', 'Deep Persistent Slab', 'Wet Loose'][min(4, risk - 1)],
            'shap_values': shap,
            'selected_features': selected_features,
            'weather_inputs': {
                'snowfall_24h': feature_row['snowfall_24h'],
                'wind_loading': feature_row['wind_loading'],
                'temp_gradient': feature_row['temp_gradient'],
                'freezing_level_proxy': feature_row['freezing_level_proxy'],
            },
            'terrain_inputs': {
                'slope': feature_row['slope'],
                'elevation': feature_row['elevation'],
                'aspect_loading': feature_row['aspect_loading'],
                'terrain_roughness': feature_row['terrain_roughness'],
            },
            'runout_seed': risk >= 4,
            'inference_backend': 'github_actions',
            'model_version': bundle['created_at'],
            'calibration_profile': bundle['calibration_method'],
        })
    return rows


def upsert_forecast_grid(region, bundle, forecast_date: pd.Timestamp, rows: list[dict[str, object]], horizon_hours: int):
    weather_inputs = [row['weather_inputs'] for row in rows if isinstance(row.get('weather_inputs'), dict)]
    terrain_inputs = [row['terrain_inputs'] for row in rows if isinstance(row.get('terrain_inputs'), dict)]
    snowfall_avg = float(np.mean([item.get('snowfall_24h', 0) for item in weather_inputs])) if weather_inputs else 0.0
    wind_avg = float(np.mean([item.get('wind_loading', 0) for item in weather_inputs])) if weather_inputs else 0.0
    temp_gradient_avg = float(np.mean([item.get('temp_gradient', 0) for item in weather_inputs])) if weather_inputs else 0.0
    precipitation_avg = float(np.mean([item.get('snowfall_24h', 0) for item in weather_inputs])) if weather_inputs else 0.0
    snow_depth_proxy = float(np.mean([item.get('elevation', 0) for item in terrain_inputs]) * 1000) if terrain_inputs else 0.0
    runout_polygons = []
    for row in rows:
        if not row.get('runout_seed'):
            continue
        runout_polygons.append({
            'row': row['row'],
            'col': row['col'],
            'risk_score': row['risk_score'],
            'polygon': [
                [row['lng'], row['lat']],
                [row['lng_end'], row['lat']],
                [row['lng_end'], row['lat_end']],
                [row['lng'], row['lat_end']],
                [row['lng'], row['lat']],
            ],
        })
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
            'snowfall_24h': f'{snowfall_avg * 40:.1f}',
            'wind_speed': f'{wind_avg * 55:.1f}',
            'temperature': f'{(temp_gradient_avg - 0.5) * 20:.1f}',
            'precipitation': f'{precipitation_avg * 45:.1f}',
            'snow_depth': f'{snow_depth_proxy:.1f}',
            'generated_at': forecast_date.isoformat(),
            'cell_count': len(rows),
            'source': 'github_actions_synthetic_fallback',
        },
        'model_metadata': {
            'model_version': bundle['created_at'],
            'selected_features': bundle['selected_features'],
            'feature_columns': bundle['feature_columns'],
            'calibration_profile': bundle['calibration_method'],
            'resampling': bundle['resampling'],
            'threshold_profile': 'heuristic-risk-bands-v1',
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
        bundle = fit_model(seed=load_settings().seed, samples_per_region=max(50, load_settings().samples_per_region // 4))
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
