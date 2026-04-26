from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend.common.artifacts import dump_json, latest_artifact_dir, load_joblib
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, build_region_grid
from backend.common.real_features import (
    build_real_feature_row,
    extract_cell_terrain,
    fetch_forecast_weather_profile,
    fetch_historical_weather_window,
    select_hourly_weather_sample,
)
from backend.common.regions import load_regions, repo_root
from backend.common.runout import RUN_PHYSICS_RUNOUT, build_runout_polygons
from backend.common.risk_math import (
    DEFAULT_IPA_WEIGHTS,
    build_hazard_vector,
    chebyshev_ipa,
    legacy_max_risk_level,
    risk_level as ipa_risk_level,
)
from backend.common.supabase_io import has_supabase_credentials, patch_first_row, rest_get, rest_upsert
from backend.common.sequence_features import build_inference_branches
from backend.lstm_model import predict_production_probability


def _fetch_latest_sar_summary(region_key: str) -> dict[str, object]:
    """P2.1: Read the latest SAR scene summary for this region so the voxel
    grid can surface real `sar_coverage_state` and `residual_shadow` flags
    instead of the previous hardcoded 'not_applicable' defaults.

    Returns an empty dict when Supabase is unreachable or no SAR events
    exist \u2014 callers treat that as "SAR not currently active" which is the
    correct semantic when `capabilities.sar_enabled=false`.
    """
    if not has_supabase_credentials():
        return {}
    try:
        rows = rest_get(
            'avalanche_events',
            params={
                'select': 'id,timestamp,features',
                'source': 'in.(gee_sar,sentinel1_gee)',
                'order': 'timestamp.desc',
                'limit': '10',
            },
        ) or []
    except Exception:
        return {}
    relevant = [row for row in rows if isinstance(row.get('features'), dict)
                and row['features'].get('region_key') == region_key]
    if not relevant:
        return {}
    latest = relevant[0]
    features = latest.get('features') or {}
    return {
        'sar_coverage_state': str(features.get('sar_coverage_state') or 'unknown'),
        'ascending_scene_count': int(features.get('ascending_scene_count') or 0),
        'descending_scene_count': int(features.get('descending_scene_count') or 0),
        'sar_scene_time': features.get('sar_scene_time'),
        'sar_active': True,
    }


def _fetch_region_sar_evidence(region_key: str) -> dict[str, object]:
    if not has_supabase_credentials():
        return {'mask_asset_refs': [], 'sar_event_geometries': []}
    try:
        rows = rest_get(
            'avalanche_events',
            params={
                'select': 'id,timestamp,mask_asset_ref,source_scene_ids,geometry_type,source_model,label_confidence,features',
                'source': 'in.(gee_sar,sentinel1_gee,sar_unet)',
                'order': 'timestamp.desc',
                'limit': '20',
            },
        ) or []
    except Exception:
        return {'mask_asset_refs': [], 'sar_event_geometries': []}

    mask_refs: list[str] = []
    geometries: list[dict[str, object]] = []
    for row in rows:
        features = row.get('features') if isinstance(row.get('features'), dict) else {}
        if features.get('region_key') != region_key:
            continue
        mask_ref = row.get('mask_asset_ref')
        if isinstance(mask_ref, str) and mask_ref:
            mask_refs.append(mask_ref)
        geometry = features.get('sar_geometry') if isinstance(features, dict) else None
        centroid = features.get('sar_centroid') if isinstance(features, dict) else None
        if isinstance(geometry, dict):
            geometries.append({
                'event_id': row.get('id'),
                'timestamp': row.get('timestamp'),
                'geometry': geometry,
                'centroid': centroid if isinstance(centroid, dict) else None,
                'geometry_type': row.get('geometry_type'),
                'source_model': row.get('source_model'),
                'label_confidence': row.get('label_confidence'),
                'source_scene_ids': row.get('source_scene_ids') if isinstance(row.get('source_scene_ids'), list) else [],
            })

    return {
        'mask_asset_refs': mask_refs,
        'sar_event_geometries': geometries,
    }


def _compute_cell_coverage_flags(
    terrain: dict[str, float],
    sar_summary: dict[str, object],
) -> dict[str, object]:
    """P2.1: Per-cell residual-shadow flag from terrain vs. Sentinel-1 look
    geometry. Sentinel-1 IW has a ~12\u00b0 heading offset; ascending/descending
    passes view opposite sides. A pixel is considered potentially shadowed
    when:
      * slope > 40\u00b0 AND
      * only one orbital pass observed it (missing ASC or DESC), AND
      * the terrain aspect faces away from that pass's look direction.
    """
    if not sar_summary or not sar_summary.get('sar_active'):
        return {
            'sar_coverage_state': 'not_applicable',
            'residual_shadow': False,
            'data_gaps': [],
        }

    coverage_state = str(sar_summary.get('sar_coverage_state') or 'unknown')
    asc_count = int(sar_summary.get('ascending_scene_count') or 0)
    desc_count = int(sar_summary.get('descending_scene_count') or 0)
    slope_deg = float(terrain.get('slope_angle_deg') or 0.0)
    aspect_deg = float(terrain.get('aspect_deg') or 0.0)

    data_gaps: list[str] = []
    residual_shadow = False
    if slope_deg > 40.0 and coverage_state != 'full_coverage':
        # Ascending pass typically looks east (azimuth ~78\u00b0 relative to
        # heading); descending ~282\u00b0. Cells facing directly away from the
        # only observed pass are the high-risk shadow zone.
        if asc_count > 0 and desc_count == 0:
            facing_away = abs(((aspect_deg - 258.0 + 540.0) % 360.0) - 180.0) < 45.0
            if facing_away:
                residual_shadow = True
                data_gaps.append('desc_pass_missing_steep_west_slope')
        elif desc_count > 0 and asc_count == 0:
            facing_away = abs(((aspect_deg - 78.0 + 540.0) % 360.0) - 180.0) < 45.0
            if facing_away:
                residual_shadow = True
                data_gaps.append('asc_pass_missing_steep_east_slope')

    if coverage_state == 'low_coverage':
        data_gaps.append('low_orbital_coverage')

    return {
        'sar_coverage_state': coverage_state,
        'residual_shadow': residual_shadow,
        'data_gaps': data_gaps,
    }


def risk_level(probability: float) -> int:
    return ipa_risk_level(probability)


def uncertainty_class(span: float) -> str:
    if span > 0.30:
        return 'high'
    if span > 0.18:
        return 'medium'
    return 'low'


def chebyshev_ideal_hazard_distance_legacy(cell_probability: float | np.ndarray, cell_slope_deg: float | np.ndarray, *, w_prob: float = 1.0, w_slope: float = 1.0) -> np.ndarray:
    probability_distance = w_prob * (1.0 - np.asarray(cell_probability, dtype=float))
    slope_distance = w_slope * np.abs(38.0 - np.asarray(cell_slope_deg, dtype=float))
    return np.maximum(probability_distance, slope_distance)


chebyshev_ideal_hazard_distance = chebyshev_ideal_hazard_distance_legacy


def _load_ipa_weights() -> dict[str, float]:
    config_path = Path(os.getenv('RISK_WEIGHTS_PATH', str(repo_root() / 'config' / 'risk_weights.json')))
    try:
        payload = json.loads(config_path.read_text(encoding='utf-8'))
    except Exception:
        return dict(DEFAULT_IPA_WEIGHTS)
    weights = payload.get('weights') if isinstance(payload, dict) else None
    if not isinstance(weights, dict):
        return dict(DEFAULT_IPA_WEIGHTS)
    merged = dict(DEFAULT_IPA_WEIGHTS)
    merged.update({str(key): float(value) for key, value in weights.items()})
    return merged


def terrain_adjusted_risk_level(
    calibrated_probability: float,
    slope_angle_deg: float,
    *,
    aspect_risk: float,
    snowpack_shear_strength: float,
    exposure: float,
    weights: dict[str, float] | None = None,
) -> tuple[int, float, float, dict[str, float], str, float, int]:
    legacy_risk, slope_risk = legacy_max_risk_level(calibrated_probability, slope_angle_deg)
    legacy_distance = float(chebyshev_ideal_hazard_distance_legacy(calibrated_probability, slope_angle_deg))
    vector = build_hazard_vector(
        probability=calibrated_probability,
        slope_deg=slope_angle_deg,
        aspect_risk=aspect_risk,
        snowpack_shear_strength=snowpack_shear_strength,
        exposure=exposure,
    )
    ipa_result = chebyshev_ipa(vector, weights)
    ipa_risk = risk_level(ipa_result.score)
    terrain_adjusted_risk = max(legacy_risk, ipa_risk)
    return (
        terrain_adjusted_risk,
        float(slope_risk),
        legacy_distance,
        vector,
        ipa_result.dominant_criterion,
        ipa_result.score,
        ipa_risk,
    )


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
    history_profile = fetch_historical_weather_window(
        lat=float(region.center[0]),
        lng=float(region.center[1]),
        start=(forecast_date - pd.Timedelta(days=7)).to_pydatetime(),
        end=forecast_date.to_pydatetime(),
    )
    ipa_weights = _load_ipa_weights()
    lstm_head = bundle.get('lstm_head') if isinstance(bundle, dict) else None
    # P2.1: Fetch SAR summary once per region so per-cell coverage flags
    # reflect real orbital coverage instead of the old hardcoded default.
    sar_summary = _fetch_latest_sar_summary(region.key)
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
        rf_probability = float(calibrated_model.predict_proba(selected_frame)[0, 1])
        sequence_branches = None
        if lstm_head is not None and getattr(lstm_head, 'model', None) is not None:
            sequence_branches = build_inference_branches(
                terrain=terrain,
                static_feature_row=feature_row,
                forecast_samples=weather_profile.get('samples') or [],
                history_samples=history_profile.get('samples') or [],
                dynamic_features=getattr(lstm_head, 'dynamic_features', None),
                static_features=getattr(lstm_head, 'static_features', None),
                hourly_steps=int(getattr(lstm_head, 'metadata', {}).get('hourly_steps', 24)),
                daily_steps=int(getattr(lstm_head, 'metadata', {}).get('daily_steps', 7)),
            )
        calibrated_probability, lstm_context = predict_production_probability(rf_probability, lstm_head, sequence_branches)
        mean_probability = float(probabilities.mean()) if probabilities.size else rf_probability
        variance = float(probabilities.var()) if probabilities.size else 0.0
        if lstm_context and isinstance(lstm_context, dict):
            lower_value = lstm_context.get('confidence_lower')
            upper_value = lstm_context.get('confidence_upper')
            if isinstance(lower_value, (int, float)) and isinstance(upper_value, (int, float)):
                confidence_lower = float(lower_value)
                confidence_upper = float(upper_value)
            else:
                confidence_lower = float(max(0.0, mean_probability - 1.96 * np.sqrt(variance)))
                confidence_upper = float(min(1.0, mean_probability + 1.96 * np.sqrt(variance)))
        else:
            confidence_lower = float(max(0.0, mean_probability - 1.96 * np.sqrt(variance)))
            confidence_upper = float(min(1.0, mean_probability + 1.96 * np.sqrt(variance)))
        span = confidence_upper - confidence_lower
        exposure = float(np.clip(feature_row['elevation'] * 0.55 + feature_row['terrain_roughness'] * 0.45, 0, 1))
        risk, terrain_risk_score, chebyshev_distance, hazard_vector, limiting_factor, ipa_score, ipa_risk = terrain_adjusted_risk_level(
            calibrated_probability,
            float(terrain['slope_angle_deg']),
            aspect_risk=float(feature_row['aspect_loading']),
            snowpack_shear_strength=float(assembled['snowpack_proxy'].estimated_shear_strength),
            exposure=exposure,
            weights=ipa_weights,
        )
        probability_risk = risk_level(calibrated_probability)
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
            'probability_risk_score': probability_risk,
            'probability': calibrated_probability,
            'rf_probability': rf_probability,
            'terrain_risk_score': terrain_risk_score,
            'chebyshev_hazard_distance': chebyshev_distance,
            'chebyshev_ipa_score': ipa_score,
            'chebyshev_ipa_risk_score': ipa_risk,
            'hazard_vector': hazard_vector,
            'ipa_weights': ipa_weights,
            'fusion_method': 'chebyshev_ipa_v2',
            'limiting_factor': limiting_factor,
            'lstm_context': lstm_context,
            'confidence_lower': confidence_lower,
            'confidence_upper': confidence_upper,
            'uncertainty_span': span,
            'uncertainty_class': uncertainty_class(span),
            'hazard': calibrated_probability,
            'exposure': exposure,
            'vulnerability': float(np.clip(feature_row['aspect_loading'] * 0.6 + feature_row['wind_loading'] * 0.4, 0, 1)),
            'problem_type': ['Storm Slab', 'Wind Slab', 'Persistent Slab', 'Deep Persistent Slab', 'Wet Loose'][min(4, risk - 1)],
            'shap_values': shap_values,
            'shap_context': {
                'top_features': shap_context,
                'limiting_factor': limiting_factor,
                'hazard_vector': hazard_vector,
                'fusion_method': 'chebyshev_ipa_v2',
            },
            'feature_values': selected_frame.iloc[0].to_dict(),
            'explanation_summary': None,
            'coverage_flags': _compute_cell_coverage_flags(terrain, sar_summary),
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
                'clamped_to_bounds': bool(terrain.get('clamped_to_bounds', 0.0)),
                'window_search_needed': bool(terrain.get('window_search_needed', 0.0)),
            },
            'dominant_driver_feature': dominant_driver,
            'runout_seed': risk >= 4,
            'dynamic_model_type': (lstm_context or {}).get('dynamic_model_type') if isinstance(lstm_context, dict) else None,
            'dynamic_model_version': (lstm_context or {}).get('dynamic_model_version') if isinstance(lstm_context, dict) else None,
            'surrogate_model_version': bundle.get('surrogate_model_version'),
            'uncertainty_method': (lstm_context or {}).get('uncertainty_method') if isinstance(lstm_context, dict) else 'tree_variance_gaussian',
            'inference_backend': (
                'github_actions_shadow'
                if isinstance(lstm_context, dict) and lstm_context.get('shadow_mode_active')
                else 'github_actions_mts_lstm'
                if isinstance(lstm_context, dict) and lstm_context.get('enabled')
                else 'github_actions_surrogate_rf'
            ),
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
    sar_evidence = _fetch_region_sar_evidence(region.key)
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
            'dynamic_model_type': bundle.get('dynamic_model_type'),
            'dynamic_model_version': bundle.get('dynamic_model_version'),
            'surrogate_model_version': bundle.get('surrogate_model_version'),
            'selected_features': bundle['selected_features'],
            'feature_columns': bundle['feature_columns'],
            'calibration_profile': bundle['calibration_method'],
            'resampling': bundle['resampling'],
            'tree_variance_policy': bundle.get('tree_variance_policy'),
            'pss_metrics': bundle.get('metrics', {}),
            'cv_metrics': bundle.get('cv_metrics'),
            'threshold_profile': 'heuristic-risk-bands-v1',
            'fusion_method': 'chebyshev_ipa_v2',
            'risk_weights': _load_ipa_weights(),
            'lstm_head_meta': bundle.get('lstm_head_meta'),
            'uncertainty_method': (
                bundle.get('lstm_head_meta', {}).get('uncertainty_method')
                if isinstance(bundle.get('lstm_head_meta'), dict)
                else 'tree_variance_gaussian'
            ),
            'run_physics_runout': RUN_PHYSICS_RUNOUT,
            'runout_method_sample': next((rp.get('method') for rp in runout_polygons if rp.get('method') and rp.get('method') != 'deferred_oom_guard'), None),
            'dominant_driver_strategy': 'top_absolute_tree_shap_v1',
            'training_dataset_version': bundle.get('training_dataset_version'),
            'label_snapshot_id': (
                f"{bundle.get('training_dataset_version', 'unknown')}:{bundle.get('dataset_manifest', {}).get('newest_timestamp')}"
                if isinstance(bundle.get('dataset_manifest'), dict)
                else bundle.get('created_at')
            ),
            'sar_mask_asset_refs': sar_evidence.get('mask_asset_refs', []),
            'sar_event_geometries': sar_evidence.get('sar_event_geometries', []),
            'stale': False,
        },
        'status': 'ready',
    }
    if has_supabase_credentials():
        rest_upsert('forecast_grids', [payload], on_conflict='hazard_type,region_key,forecast_date,horizon_hours')
        _upsert_shap_cache(region, bundle, forecast_date, rows)
    return payload


def _upsert_shap_cache(region, bundle, forecast_date: pd.Timestamp, rows: list[dict[str, object]]) -> None:
    """Persist per-cell TreeSHAP results to forecast_shap_cache.

    The point lookup is keyed by (forecast_grid_id, cell_row, cell_col,
    forecast_hour, model_version). forecast_grid_id is not known at
    this moment because forecast_grids is upserted via ON CONFLICT, so
    we key via the stable (hazard_type, region_key, forecast_date,
    horizon_hours) tuple and let the UI join back through forecast_grids.
    """
    try:
        from backend.common.supabase_io import rest_get
    except ImportError:
        return
    try:
        rows_for_key = rest_get(
            'forecast_grids',
            params={
                'hazard_type': 'eq.avalanche',
                'region_key': f'eq.{region.key}',
                'forecast_date': f'eq.{forecast_date.date().isoformat()}',
                'select': 'id',
                'order': 'created_at.desc',
                'limit': '1',
            },
        ) or []
    except Exception:
        rows_for_key = []
    forecast_grid_id = rows_for_key[0].get('id') if rows_for_key else None
    if not forecast_grid_id:
        return
    model_version = str(bundle.get('created_at') or 'unknown')
    payload: list[dict[str, object]] = []
    for cell in rows:
        shap_context = cell.get('shap_context') or {}
        top_features = shap_context.get('top_features') if isinstance(shap_context, dict) else None
        if not top_features:
            continue
        payload.append({
            'forecast_grid_id': forecast_grid_id,
            'cell_row': int(cell.get('row', 0)),
            'cell_col': int(cell.get('col', 0)),
            'forecast_hour': 0,
            'model_version': model_version,
            'top_features': top_features,
            'shap_values': cell.get('shap_values') or {},
            'base_value': None,
            'dominant_driver': cell.get('dominant_driver_feature'),
        })
    if not payload:
        return
    try:
        rest_upsert(
            'forecast_shap_cache',
            payload,
            on_conflict='forecast_grid_id,cell_row,cell_col,forecast_hour,model_version',
        )
    except Exception:
        # Cache is best-effort; failure must not break the inference run.
        return


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
        # P2.2: Detect concept drift between the artifact's baked-in feature
        # column set and the currently deployed FEATURE_COLUMNS. If the hash
        # mismatches we don't refuse to run (that would block forecasts), but
        # we emit ::warning:: annotations so the workflow fails visibly in
        # the GitHub Actions UI and an operator is alerted to retrain.
        try:
            from backend.common.schema_drift import detect_drift, feature_columns_hash
            current_hash = feature_columns_hash(FEATURE_COLUMNS)
            stored_hash = bundle.get('feature_columns_hash') if isinstance(bundle, dict) else None
            drift_report = detect_drift(
                stored_feature_hash=stored_hash if isinstance(stored_hash, str) else None,
                current_feature_hash=current_hash,
                stored_label_hash=None,
                current_label_hash='',
            )
            if drift_report['requires_retrain']:
                print(
                    f"::warning title=Schema drift detected::"
                    f"feature_columns_hash mismatch (stored={stored_hash!s}, current={current_hash!s}). "
                    f"Retrain required.",
                    file=sys.stderr,
                )
        except Exception as drift_exc:  # pragma: no cover - drift check is advisory
            print(f"[daily_inference] drift check skipped: {drift_exc}", file=sys.stderr)
    except FileNotFoundError:
        raise RuntimeError(
            'No trained model artifact is available. Run backend.train_model first; '
            'daily inference no longer bootstraps a synthetic fallback model.'
        )
    forecast_date = pd.Timestamp(datetime.now(timezone.utc))
    regions = load_regions()

    outputs = []
    for region in regions:
        rows = build_cells(region, bundle, grid_size=args.grid_size, forecast_date=forecast_date)
        payload = upsert_forecast_grid(region, bundle, forecast_date, rows, horizon_hours=args.forecast_hours)
        outputs.append(payload)

    dump_json(artifact_dir / 'forecast_grids.json', outputs)

    # P0.2: Write a per-region health summary so stale runs are visible in
    # GitHub Actions logs AND in the admin dashboard (via model_status).
    inference_manifest = {
        'artifact_dir': str(artifact_dir),
        'regions_written': len(outputs),
        'regions': [
            {
                'region_key': payload.get('region_key'),
                'region_name': payload.get('region_name'),
                'forecast_date': payload.get('forecast_date'),
                'horizon_hours': payload.get('horizon_hours'),
                'cell_count': len(payload.get('grid_geojson') or []),
                'runout_method_sample': (payload.get('model_metadata') or {}).get('runout_method_sample'),
                'training_dataset_version': (payload.get('model_metadata') or {}).get('training_dataset_version'),
            }
            for payload in outputs
        ],
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    dump_json(artifact_dir / 'inference_manifest.json', inference_manifest)

    if has_supabase_credentials():
        # P0.2: Compute next scheduled run (24h from now) so the admin dashboard
        # can flag staleness instead of showing an indefinite 'null'.
        next_run = (datetime.now(timezone.utc) + pd.Timedelta(hours=24)).isoformat()
        patch_first_row('model_status', {
            'version': f"forecast-{artifact_dir.name}",
            'last_inference': datetime.now(timezone.utc).isoformat(),
            'inference_backend': 'batch_async',
            'feature_version': str(bundle.get('dynamic_model_type') or 'surrogate_rf_v1'),
            'calibration_profile_version': str(bundle.get('dynamic_model_version') or bundle.get('created_at')),
            'threshold_profile_version': 'chebyshev_ipa_v2',
            'next_run': next_run,
        })

    print(json.dumps(inference_manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
