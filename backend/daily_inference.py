from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from backend.common.artifacts import dump_json, load_joblib, resolve_artifact_dir
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, build_region_grid
from backend.common.forecast_publication import (
    attach_compatibility_forecast_grid,
    publish_forecast_run,
    promote_forecast_run,
)
from backend.common.model_status_state import (
    build_autonomous_evidence_summary,
    build_dynamic_model_candidate,
    resolve_active_candidate_artifact_dir,
    resolve_active_model_state,
)
from backend.common.real_features import (
    TerrainUnavailableError,
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
from backend.common.snowpack_proxy import fetch_batched_cell_snowpack_proxies_partial
from backend.common.supabase_io import (
    has_supabase_credentials,
    patch_first_row,
    rest_get,
    rest_insert,
    rest_upsert,
)
from backend.common.sequence_features import build_inference_branches
from backend.lstm_model import predict_production_probability
from backend.models.surrogate_rf import build_tree_shap_explainer, collect_tree_probabilities, compute_tree_shap


DEFAULT_DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'


@dataclass(frozen=True)
class ProofModeOptions:
    enabled: bool = False
    profile: str = 'standard'
    skip_tree_shap: bool = False
    skip_shap_cache: bool = False
    skip_runout_generation: bool = False
    skip_compatibility_write: bool = False
    emit_stage_metrics: bool = False

    def as_metadata(self) -> dict[str, object]:
        return {
            'lifeboat_mode': self.enabled,
            'lifeboat_profile': self.profile if self.enabled else None,
            'skip_tree_shap': self.skip_tree_shap,
            'skip_shap_cache': self.skip_shap_cache,
            'skip_runout_generation': self.skip_runout_generation,
            'skip_compatibility_write': self.skip_compatibility_write,
            'emit_stage_metrics': self.emit_stage_metrics,
        }


def _execution_linkage(*, artifact_dir: Path | None = None) -> dict[str, object]:
    compute_job_id = str(os.getenv('COMPUTE_JOB_ID') or os.getenv('JOB_ID') or '').strip() or None
    modal_call_id = str(os.getenv('MODAL_CALL_ID') or '').strip() or None
    return {
        'compute_job_id': compute_job_id,
        'modal_call_id': modal_call_id,
        'artifact_dir': str(artifact_dir) if artifact_dir is not None else None,
    }


def _publication_event_detail(
    *,
    forecast_run_id: str,
    artifact_dir: Path | None = None,
    modal_call_id: str | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        'forecast_run_id': forecast_run_id,
        'artifact_dir': str(artifact_dir) if artifact_dir is not None else None,
        'modal_call_id': modal_call_id,
    }
    if extra:
        detail.update(extra)
    return detail


def _record_publication_event_best_effort(
    *,
    forecast_run_id: str,
    stage: str,
    status: str,
    artifact_dir: Path | None = None,
    modal_call_id: str | None = None,
    detail: dict[str, object] | None = None,
) -> None:
    event_record = {
        'forecast_run_id': forecast_run_id,
        'stage': stage,
        'status': status,
        'detail': _publication_event_detail(
            forecast_run_id=forecast_run_id,
            artifact_dir=artifact_dir,
            modal_call_id=modal_call_id,
            extra=detail,
        ),
    }
    try:
        rest_insert('forecast_publication_events', [event_record], returning='minimal', timeout_seconds=120)
    except Exception:
        pass


def _dem_root() -> Path:
    raw = str(os.getenv('DEM_ROOT') or os.getenv('DEM_DIR') or '').strip()
    if not raw:
        return DEFAULT_DEM_DIR
    return Path(raw).expanduser()


def _dem_path(region_key: str) -> Path:
    return _dem_root() / f'{region_key}.tif'


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


def _default_inference_backend(bundle: dict[str, object]) -> str:
    lstm_head = bundle.get('lstm_head') if isinstance(bundle, dict) else None
    if getattr(lstm_head, 'model', None) is not None:
        return 'github_actions_mts_lstm'
    return 'github_actions_surrogate_rf'


def _fetch_current_model_status() -> dict[str, object] | None:
    if not has_supabase_credentials():
        return None
    try:
        rows = rest_get(
            'model_status',
            params={
                'select': '*',
                'limit': '1',
            },
        ) or []
    except Exception:
        return None
    return rows[0] if rows else None


def _runout_method_counts(runout_polygons: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for polygon in runout_polygons:
        method = str(polygon.get('method') or 'unknown')
        counts[method] = counts.get(method, 0) + 1
    return counts


def _build_unavailable_cell(
    *,
    cell: dict[str, object],
    center_lat: float,
    center_lng: float,
    bundle: dict[str, object],
    snowpack_proxy: object | None,
    reason: str,
) -> dict[str, object]:
    proxy_payload = None
    if snowpack_proxy is not None:
        proxy_payload = {
            'estimated_shear_strength': getattr(snowpack_proxy, 'estimated_shear_strength', None),
            'snow_settlement_index': getattr(snowpack_proxy, 'snow_settlement_index', None),
            'season_start': getattr(snowpack_proxy, 'season_start', None),
            'method': getattr(snowpack_proxy, 'method', None),
        }
    return {
        'row': int(cell['row']),
        'col': int(cell['col']),
        'lat': center_lat,
        'lng': center_lng,
        'lat_end': float(cell['lat_end']),
        'lng_end': float(cell['lng_end']),
        'risk_score': 0,
        'probability_risk_score': 0,
        'probability': None,
        'rf_probability': None,
        'terrain_risk_score': None,
        'chebyshev_hazard_distance': None,
        'chebyshev_ipa_score': None,
        'chebyshev_ipa_risk_score': None,
        'hazard_vector': {},
        'ipa_weights': _load_ipa_weights(),
        'fusion_method': 'chebyshev_ipa_v2',
        'limiting_factor': None,
        'lstm_context': None,
        'confidence_lower': None,
        'confidence_upper': None,
        'uncertainty_span': None,
        'uncertainty_class': 'high',
        'hazard': 0.0,
        'exposure': 0.0,
        'vulnerability': 0.0,
        'problem_type': 'Unavailable terrain' if reason == 'unavailable_terrain' else 'Unavailable weather',
        'shap_values': {},
        'shap_context': {'top_features': []},
        'feature_values': {},
        'explanation_summary': None,
        'coverage_flags': {
            'sar_coverage_state': 'not_applicable',
            'residual_shadow': False,
            'data_gaps': [reason],
        },
        'selected_features': bundle['selected_features'],
        'weather_inputs': {},
        'terrain_inputs': {
            'availability_reason': reason,
        },
        'dominant_driver_feature': None,
        'runout_seed': False,
        'dynamic_model_type': bundle.get('dynamic_model_type'),
        'dynamic_model_version': bundle.get('dynamic_model_version'),
        'surrogate_model_version': bundle.get('surrogate_model_version'),
        'uncertainty_method': (
            bundle.get('lstm_head_meta', {}).get('uncertainty_method')
            if isinstance(bundle.get('lstm_head_meta'), dict)
            else 'tree_variance_gaussian'
        ),
        'inference_backend': _default_inference_backend(bundle),
        'model_version': bundle['created_at'],
        'calibration_profile': bundle['calibration_method'],
        'snowpack_proxy': proxy_payload,
        'status': reason,
        'stale': True,
        'disabled': True,
        'availability_reason': reason,
    }


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


def _prepare_region_context(
    region,
    bundle,
    grid_size: int,
    forecast_date: pd.Timestamp,
    *,
    artifact_dir: Path | None = None,
    proof_options: ProofModeOptions | None = None,
    stage_metrics: dict[str, Any] | None = None,
) -> dict[str, object]:
    proof_options = proof_options or ProofModeOptions()
    context_started_at = perf_counter()
    region_grid = build_region_grid(region, grid_size=grid_size)
    weather_profile = fetch_forecast_weather_profile(region.center, forecast_date.to_pydatetime(), 72)
    history_profile = fetch_historical_weather_window(
        lat=float(region.center[0]),
        lng=float(region.center[1]),
        start=(forecast_date - pd.Timedelta(days=7)).to_pydatetime(),
        end=forecast_date.to_pydatetime(),
    )
    cell_centers = [
        (
            float(cell['lat'] + (cell['lat_end'] - cell['lat']) / 2),
            float(cell['lng'] + (cell['lng_end'] - cell['lng']) / 2),
        )
        for cell in region_grid
    ]
    snowpack_started_at = perf_counter()
    snowpack_results = fetch_batched_cell_snowpack_proxies_partial(
        coordinates=cell_centers,
        as_of=forecast_date.to_pydatetime(),
        cache_path=(
            artifact_dir / 'snowpack_proxy_cache' / f'{region.key}-{forecast_date.date().isoformat()}.json'
            if artifact_dir is not None
            else None
        ),
    )
    if len(snowpack_results) != len(region_grid):
        raise RuntimeError(
            f'Snowpack proxy count mismatch for {region.key}: '
            f'expected {len(region_grid)}, received {len(snowpack_results)}'
        )
    if stage_metrics is not None:
        stage_metrics['snowpack_fetch_seconds'] = round(perf_counter() - snowpack_started_at, 3)

    dem_path = _dem_path(region.key)
    prepared_cells: list[dict[str, object]] = []
    for cell, (center_lat, center_lng), snowpack_result in zip(region_grid, cell_centers, snowpack_results):
        snowpack_proxy = snowpack_result.proxy
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=center_lat, lng=center_lng)
        except (TerrainUnavailableError, ValueError):
            prepared_cells.append({
                'cell': cell,
                'center_lat': center_lat,
                'center_lng': center_lng,
                'snowpack_proxy': snowpack_proxy,
                'terrain': None,
                'availability_reason': 'unavailable_terrain',
            })
            continue
        if snowpack_proxy is None:
            prepared_cells.append({
                'cell': cell,
                'center_lat': center_lat,
                'center_lng': center_lng,
                'snowpack_proxy': None,
                'terrain': terrain,
                'availability_reason': 'unavailable_weather',
            })
            continue
        prepared_cells.append({
            'cell': cell,
            'center_lat': center_lat,
            'center_lng': center_lng,
            'snowpack_proxy': snowpack_proxy,
            'terrain': terrain,
            'availability_reason': None,
        })
    if stage_metrics is not None:
        stage_metrics['region_context_prep_seconds'] = round(perf_counter() - context_started_at, 3)

    return {
        'selector': bundle['selector'],
        'calibrated_model': bundle['calibrated_model'],
        'base_model': bundle['base_model'],
        'selected_features': bundle['selected_features'],
        'ipa_weights': _load_ipa_weights(),
        'lstm_head': bundle.get('lstm_head') if isinstance(bundle, dict) else None,
        'sar_summary': _fetch_latest_sar_summary(region.key),
        'explainer': None if proof_options.skip_tree_shap else build_tree_shap_explainer(bundle['base_model']),
        'weather_profile': weather_profile,
        'forecast_samples': weather_profile.get('samples') if isinstance(weather_profile, dict) else [],
        'history_samples': history_profile.get('samples') if isinstance(history_profile, dict) else [],
        'prepared_cells': prepared_cells,
    }


def _build_rows_for_timestamp(
    *,
    region_context: dict[str, object],
    bundle,
    forecast_time: pd.Timestamp,
    weather_sample: dict[str, object] | None,
    forecast_samples: list[object],
    use_dynamic_inference: bool,
    proof_options: ProofModeOptions | None = None,
) -> list[dict[str, object]]:
    proof_options = proof_options or ProofModeOptions()
    selector = region_context['selector']
    calibrated_model = region_context['calibrated_model']
    base_model = region_context['base_model']
    selected_features: list[str] = region_context['selected_features']  # type: ignore[assignment]
    ipa_weights: dict[str, float] = region_context['ipa_weights']  # type: ignore[assignment]
    lstm_head = region_context['lstm_head']
    sar_summary: dict[str, object] = region_context['sar_summary']  # type: ignore[assignment]
    explainer = region_context['explainer']
    history_samples: list[object] = region_context['history_samples']  # type: ignore[assignment]
    rows: list[dict[str, object]] = []

    for prepared in region_context['prepared_cells']:  # type: ignore[index]
        cell = prepared['cell']
        center_lat = float(prepared['center_lat'])
        center_lng = float(prepared['center_lng'])
        snowpack_proxy = prepared['snowpack_proxy']
        availability_reason = prepared['availability_reason']
        if availability_reason:
            rows.append(
                _build_unavailable_cell(
                    cell=cell,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    bundle=bundle,
                    snowpack_proxy=snowpack_proxy,
                    reason=str(availability_reason),
                )
            )
            continue

        terrain = prepared['terrain']
        assembled = build_real_feature_row(
            weather_sample=weather_sample or {},
            terrain=terrain,
            timestamp=forecast_time.to_pydatetime(),
            lat=center_lat,
            lng=center_lng,
            snowpack_proxy_override=snowpack_proxy,
        )
        feature_row = assembled['feature_row']
        feature_frame = pd.DataFrame([feature_row], columns=FEATURE_COLUMNS)
        selected_frame = pd.DataFrame(selector.transform(feature_frame), columns=selected_features)
        probabilities = collect_tree_probabilities(base_model, selected_frame)
        rf_probability = float(calibrated_model.predict_proba(selected_frame)[0, 1])
        dynamic_candidate_available = (
            lstm_head is not None and getattr(lstm_head, 'model', None) is not None
        )
        sequence_branches = None
        if dynamic_candidate_available and use_dynamic_inference:
            sequence_branches = build_inference_branches(
                terrain=terrain,
                static_feature_row=feature_row,
                forecast_samples=forecast_samples or [],
                history_samples=history_samples or [],
                dynamic_features=getattr(lstm_head, 'dynamic_features', None),
                static_features=getattr(lstm_head, 'static_features', None),
                hourly_steps=int(getattr(lstm_head, 'metadata', {}).get('hourly_steps', 24)),
                daily_steps=int(getattr(lstm_head, 'metadata', {}).get('daily_steps', 7)),
            )
        if dynamic_candidate_available and not use_dynamic_inference:
            calibrated_probability = float(rf_probability)
            lstm_context = {
                'enabled': True,
                'dynamic_model_type': 'mts_lstm_v1',
                'dynamic_model_version': getattr(lstm_head, 'metadata', {}).get('dynamic_model_version'),
                'surrogate_model_role': 'tree_shap_surrogate',
                'promotion_gate_passed': False,
                'shadow_mode_active': True,
                'dynamic_probability': None,
                'active_probability': float(rf_probability),
                'uncertainty_method': 'tree_variance_gaussian_shadow',
                'uncertainty_std': None,
                'candidate_ready_for_activation': bool(
                    getattr(lstm_head, 'metadata', {}).get('production_eligibility_gate_passed')
                ),
                'fallback_reason': 'shadow_inference_skipped',
            }
        else:
            calibrated_probability, lstm_context = predict_production_probability(
                rf_probability,
                lstm_head,
                sequence_branches,
                allow_dynamic_inference=use_dynamic_inference,
            )
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
        if proof_options.skip_tree_shap or explainer is None:
            shap_values = {}
            shap_context = []
            dominant_driver = None
        else:
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
            'status': 'ready',
            'stale': False,
            'disabled': False,
            'availability_reason': None,
        })

    return rows


def build_cells(
    region,
    bundle,
    grid_size: int,
    forecast_date: pd.Timestamp,
    *,
    artifact_dir: Path | None = None,
    use_dynamic_inference: bool = False,
    proof_options: ProofModeOptions | None = None,
    stage_metrics: dict[str, Any] | None = None,
):
    region_context = _prepare_region_context(
        region,
        bundle,
        grid_size,
        forecast_date,
        artifact_dir=artifact_dir,
        proof_options=proof_options,
        stage_metrics=stage_metrics,
    )
    weather_profile = region_context['weather_profile']
    weather_sample = select_hourly_weather_sample(weather_profile, forecast_date.to_pydatetime())
    return _build_rows_for_timestamp(
        region_context=region_context,
        bundle=bundle,
        forecast_time=forecast_date,
        weather_sample=weather_sample if isinstance(weather_sample, dict) else {},
        forecast_samples=region_context['forecast_samples'],  # type: ignore[arg-type]
        use_dynamic_inference=use_dynamic_inference,
        proof_options=proof_options,
    )


def build_hourly_grids(
    region,
    bundle,
    grid_size: int,
    forecast_date: pd.Timestamp,
    horizon_hours: int,
    *,
    artifact_dir: Path | None = None,
    use_dynamic_inference: bool = False,
    proof_options: ProofModeOptions | None = None,
    stage_metrics: dict[str, Any] | None = None,
):
    region_context = _prepare_region_context(
        region,
        bundle,
        grid_size,
        forecast_date,
        artifact_dir=artifact_dir,
        proof_options=proof_options,
        stage_metrics=stage_metrics,
    )
    weather_profile = region_context['weather_profile']
    forecast_samples = region_context['forecast_samples']
    effective_horizon_hours = max(1, min(int(horizon_hours or 24), 72))
    hourly_grids: list[list[dict[str, object]]] = []
    for hour_offset in range(effective_horizon_hours):
        forecast_time = forecast_date + pd.Timedelta(hours=hour_offset)
        weather_sample = select_hourly_weather_sample(weather_profile, forecast_time.to_pydatetime())
        shifted_forecast_samples = forecast_samples[hour_offset:] if isinstance(forecast_samples, list) else []
        hourly_grids.append(
            _build_rows_for_timestamp(
                region_context=region_context,
                bundle=bundle,
                forecast_time=forecast_time,
                weather_sample=weather_sample if isinstance(weather_sample, dict) else {},
                forecast_samples=shifted_forecast_samples,
                use_dynamic_inference=use_dynamic_inference,
                proof_options=proof_options,
            )
        )
    return hourly_grids


def upsert_forecast_grid(
    region,
    bundle,
    forecast_date: pd.Timestamp,
    rows: list[dict[str, object]],
    horizon_hours: int,
    hourly_grids: list[list[dict[str, object]]] | None = None,
    *,
    artifact_dir: Path | None = None,
    grid_size: int | None = None,
    dry_run: bool = False,
    active_model_state: dict[str, object] | None = None,
    candidate_summary: dict[str, object] | None = None,
    evidence_summary: dict[str, object] | None = None,
    proof_options: ProofModeOptions | None = None,
    stage_metrics: dict[str, Any] | None = None,
):
    proof_options = proof_options or ProofModeOptions()
    execution_linkage = _execution_linkage(artifact_dir=artifact_dir)
    modal_call_id = execution_linkage.get('modal_call_id')
    weather_inputs = [
        row['weather_inputs']
        for row in rows
        if row.get('status') == 'ready' and isinstance(row.get('weather_inputs'), dict)
    ]
    terrain_inputs = [
        row['terrain_inputs']
        for row in rows
        if row.get('status') == 'ready' and isinstance(row.get('terrain_inputs'), dict)
    ]
    sar_evidence = _fetch_region_sar_evidence(region.key)
    stale_cells = [row for row in rows if row.get('status') != 'ready']
    unavailable_terrain_cells = [row for row in stale_cells if row.get('availability_reason') == 'unavailable_terrain']
    unavailable_weather_cells = [row for row in stale_cells if row.get('availability_reason') == 'unavailable_weather']
    ready_cell_count = len(rows) - len(stale_cells)
    if ready_cell_count == len(rows):
        region_status = 'ready'
    elif ready_cell_count > 0:
        region_status = 'partial'
    else:
        region_status = 'stale'
    snowfall_avg = float(np.mean([item.get('snowfall_24h_cm', item.get('snowfall_24h', 0) * 40) for item in weather_inputs])) if weather_inputs else 0.0
    wind_avg = float(np.mean([item.get('windspeed_10m', item.get('wind_loading', 0) * 55) for item in weather_inputs])) if weather_inputs else 0.0
    temperature_avg = float(np.mean([item.get('downscaled_temperature_c', item.get('temperature_2m', 0)) for item in weather_inputs])) if weather_inputs else 0.0
    precipitation_avg = float(np.mean([item.get('precipitation_24h_mm', item.get('snowfall_24h', 0) * 45) for item in weather_inputs])) if weather_inputs else 0.0
    snow_depth_proxy = float(np.mean([item.get('snowfall_24h_cm', 0.0) for item in weather_inputs])) if weather_inputs else 0.0
    runout_started_at = perf_counter()
    if proof_options.skip_runout_generation:
        runout_polygons = []
        runout_method_counts = {}
        if stage_metrics is not None:
            stage_metrics['runout_generation_seconds'] = 0.0
            stage_metrics['runout_generation_status'] = 'skipped'
    else:
        # Story 18: physics-aware Alpha-Beta runout polygons with OOM-guarded DEM
        # crop. Behind RUN_PHYSICS_RUNOUT flag; falls back to analytical Alpha-Beta
        # then to rectangular polygons when DEM / whitebox / rasterio missing.
        runout_polygons = build_runout_polygons(region.key, rows)
        runout_method_counts = _runout_method_counts(runout_polygons)
        if stage_metrics is not None:
            stage_metrics['runout_generation_seconds'] = round(perf_counter() - runout_started_at, 3)
            stage_metrics['runout_generation_status'] = 'ok'
    active_state = active_model_state if isinstance(active_model_state, dict) else {}
    dataset_snapshot_id = (
        bundle.get('dataset_snapshot_id')
        or (
            bundle.get('lstm_head_meta', {}).get('dataset_snapshot_id')
            if isinstance(bundle.get('lstm_head_meta'), dict)
            else None
        )
        or bundle.get('training_dataset_version')
        or 'latest'
    )
    requested_dataset_snapshot_id = (
        bundle.get('requested_dataset_snapshot_id')
        or (
            bundle.get('lstm_head_meta', {}).get('requested_dataset_snapshot_id')
            if isinstance(bundle.get('lstm_head_meta'), dict)
            else None
        )
        or dataset_snapshot_id
    )
    model_metadata = {
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
        'dataset_snapshot_id': dataset_snapshot_id,
        'requested_dataset_snapshot_id': requested_dataset_snapshot_id,
        'calibration_profile_version': str(
            bundle.get('calibration_profile_version')
            or bundle.get('calibration_method')
            or bundle.get('created_at')
        ),
        'run_physics_runout': RUN_PHYSICS_RUNOUT,
        'runout_method_counts': runout_method_counts,
        'runout_method_sample': next((rp.get('method') for rp in runout_polygons if rp.get('method') and rp.get('method') != 'deferred_oom_guard'), None),
        'active_model_type': active_state.get('active_model_type'),
        'active_model_version': active_state.get('active_model_version'),
        'promotion_gate_passed': active_state.get('promotion_gate_passed'),
        'shadow_mode_active': active_state.get('shadow_mode_active'),
        'dynamic_model_candidate_blocked_gate': (
            candidate_summary.get('blocked_gate')
            if isinstance(candidate_summary, dict)
            else None
        ),
        'autonomous_evidence_summary': evidence_summary,
        'dominant_driver_strategy': 'top_absolute_tree_shap_v1',
        'training_dataset_version': bundle.get('training_dataset_version'),
        'label_snapshot_id': (
            f"{bundle.get('training_dataset_version', 'unknown')}:{bundle.get('dataset_manifest', {}).get('newest_timestamp')}"
            if isinstance(bundle.get('dataset_manifest'), dict)
            else bundle.get('created_at')
        ),
        'sar_mask_asset_refs': sar_evidence.get('mask_asset_refs', []),
        'sar_event_geometries': sar_evidence.get('sar_event_geometries', []),
        'source_composition': {
            'weather_source': 'open_meteo_forecast_downscaled_v1',
            'sar_mask_asset_count': len(sar_evidence.get('mask_asset_refs', [])),
            'sar_event_geometry_count': len(sar_evidence.get('sar_event_geometries', [])),
            'snowpack_source': 'snowpack_proxy_v1',
        },
        'region_coverage': {
            'region_key': region.key,
            'bbox': list(region.bbox),
            'grid_size': int(grid_size or 1),
            'forecast_hours': int(horizon_hours),
        },
        **execution_linkage,
        **proof_options.as_metadata(),
        'stale': ready_cell_count == 0,
        'ready_cell_count': ready_cell_count,
        'stale_cell_count': len(stale_cells),
        'unavailable_terrain_cell_count': len(unavailable_terrain_cells),
        'unavailable_weather_cell_count': len(unavailable_weather_cells),
    }
    payload = {
        'hazard_type': 'avalanche',
        'region_key': region.key,
        'region_name': region.name,
        'forecast_date': forecast_date.date().isoformat(),
        'horizon_hours': horizon_hours,
        'bbox': list(region.bbox),
        'grid_geojson': rows,
        'hourly_grids': hourly_grids if hourly_grids is not None else ([rows] if rows else []),
        'runout_polygons': runout_polygons,
        'weather_summary': {
            'snowfall_24h': f'{snowfall_avg:.1f}',
            'wind_speed': f'{wind_avg:.1f}',
            'temperature': f'{temperature_avg:.1f}',
            'precipitation': f'{precipitation_avg:.1f}',
            'snow_depth': f'{snow_depth_proxy:.1f}',
            'generated_at': forecast_date.isoformat(),
            'cell_count': len(rows),
            'ready_cell_count': ready_cell_count,
            'stale_cell_count': len(stale_cells),
            'unavailable_terrain_cell_count': len(unavailable_terrain_cells),
            'unavailable_weather_cell_count': len(unavailable_weather_cells),
            'source': 'open_meteo_forecast_downscaled_v1',
        },
        'ready_cell_count': ready_cell_count,
        'stale_cell_count': len(stale_cells),
        'unavailable_terrain_cell_count': len(unavailable_terrain_cells),
        'unavailable_weather_cell_count': len(unavailable_weather_cells),
        'model_metadata': model_metadata,
        'status': region_status,
    }
    if has_supabase_credentials() and not dry_run:
        publication_started_at = perf_counter()
        publication = publish_forecast_run(
            hazard_type=str(payload['hazard_type']),
            region_key=region.key,
            region_name=region.name,
            forecast_date=str(payload['forecast_date']),
            horizon_hours=int(payload['horizon_hours']),
            grid_size=int(grid_size or 1),
            bbox=list(region.bbox),
            status=region_status,
            weather_summary=payload['weather_summary'],
            model_metadata=model_metadata,
            hourly_grids=payload['hourly_grids'],
            runout_polygons=runout_polygons,
        )
        if stage_metrics is not None:
            stage_metrics['publication_seconds'] = round(perf_counter() - publication_started_at, 3)
        forecast_run_id = str(publication['forecast_run_id'])
        payload['model_metadata'] = {
            **model_metadata,
            'forecast_run_id': forecast_run_id,
            'manifest_storage_ref': publication['manifest_storage_ref'],
            'runout_storage_ref': publication['runout_storage_ref'],
        }
        if proof_options.emit_stage_metrics and stage_metrics is not None:
            event_detail = {
                **{key: value for key, value in stage_metrics.items() if key != 'compute_started_at'},
                'forecast_hours': int(horizon_hours),
                'grid_size': int(grid_size or 1),
                'profile': proof_options.profile,
            }
            event_record: dict[str, object] = {
                'forecast_run_id': forecast_run_id,
                'stage': 'prepublication_compute',
                'status': 'ok',
                'detail': event_detail,
            }
            created_at = stage_metrics.get('compute_started_at')
            if isinstance(created_at, str) and created_at.strip():
                event_record['created_at'] = created_at
            try:
                rest_insert('forecast_publication_events', [event_record], returning='minimal', timeout_seconds=120)
            except Exception:
                pass
        db_payload = {
            'hazard_type': payload['hazard_type'],
            'region_key': payload['region_key'],
            'region_name': payload['region_name'],
            'forecast_date': payload['forecast_date'],
            'horizon_hours': payload['horizon_hours'],
            'bbox': payload['bbox'],
            'grid_geojson': payload['grid_geojson'],
            'hourly_grids': payload['hourly_grids'],
            'runout_polygons': payload['runout_polygons'],
            'weather_summary': payload['weather_summary'],
            'model_metadata': payload['model_metadata'],
            'status': payload['status'],
        }
        compatibility_row_id: str | None = None
        compatibility_started_at = perf_counter()
        if proof_options.skip_compatibility_write:
            payload['model_metadata']['compatibility_forecast_grid_id'] = None
            payload['model_metadata']['compatibility_write_status'] = 'skipped'
            payload['model_metadata']['shap_cache_write_status'] = 'skipped' if proof_options.skip_shap_cache else 'not_attempted'
        else:
            _record_publication_event_best_effort(
                forecast_run_id=forecast_run_id,
                stage='compatibility_write_started',
                status='started',
                artifact_dir=artifact_dir,
                modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
            )
            try:
                rest_upsert(
                    'forecast_grids',
                    [db_payload],
                    on_conflict='hazard_type,region_key,forecast_date,horizon_hours',
                    returning='minimal',
                    timeout_seconds=300,
                )
                matching_rows = rest_get(
                    'forecast_grids',
                    params={
                        'hazard_type': 'eq.avalanche',
                        'region_key': f'eq.{region.key}',
                        'forecast_date': f'eq.{forecast_date.date().isoformat()}',
                        'horizon_hours': f'eq.{int(horizon_hours)}',
                        'select': 'id',
                        'order': 'created_at.desc',
                        'limit': '1',
                    },
                ) or []
                if matching_rows and matching_rows[0].get('id'):
                    compatibility_row_id = str(matching_rows[0]['id'])
                    attach_compatibility_forecast_grid(
                        forecast_run_id=forecast_run_id,
                        compatibility_forecast_grid_id=compatibility_row_id,
                    )
                    payload['model_metadata']['compatibility_forecast_grid_id'] = compatibility_row_id
                else:
                    raise RuntimeError('compatibility forecast_grids row missing after upsert')
                payload['model_metadata']['compatibility_write_status'] = 'ok'
                _record_publication_event_best_effort(
                    forecast_run_id=forecast_run_id,
                    stage='compatibility_write_completed',
                    status='ok',
                    artifact_dir=artifact_dir,
                    modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                    detail={'compatibility_forecast_grid_id': compatibility_row_id},
                )
            except Exception as exc:
                payload['model_metadata']['compatibility_forecast_grid_id'] = None
                payload['model_metadata']['compatibility_write_status'] = 'failed'
                payload['model_metadata']['shap_cache_write_status'] = 'skipped' if proof_options.skip_shap_cache else 'not_attempted'
                _record_publication_event_best_effort(
                    forecast_run_id=forecast_run_id,
                    stage='compatibility_write_failed',
                    status='failed',
                    artifact_dir=artifact_dir,
                    modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                    detail={
                        'error_class': exc.__class__.__name__,
                        'error_message': str(exc),
                    },
                )
        if compatibility_row_id and proof_options.skip_shap_cache:
            payload['model_metadata']['shap_cache_write_status'] = 'skipped'
        elif compatibility_row_id and not proof_options.skip_shap_cache:
            _record_publication_event_best_effort(
                forecast_run_id=forecast_run_id,
                stage='shap_cache_started',
                status='started',
                artifact_dir=artifact_dir,
                modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                detail={'compatibility_forecast_grid_id': compatibility_row_id},
            )
            try:
                _upsert_shap_cache(region, bundle, forecast_date, rows)
                payload['model_metadata']['shap_cache_write_status'] = 'ok'
                _record_publication_event_best_effort(
                    forecast_run_id=forecast_run_id,
                    stage='shap_cache_completed',
                    status='ok',
                    artifact_dir=artifact_dir,
                    modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                    detail={'compatibility_forecast_grid_id': compatibility_row_id},
                )
            except Exception as exc:
                payload['model_metadata']['shap_cache_write_status'] = 'failed'
                _record_publication_event_best_effort(
                    forecast_run_id=forecast_run_id,
                    stage='shap_cache_failed',
                    status='failed',
                    artifact_dir=artifact_dir,
                    modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                    detail={
                        'error_class': exc.__class__.__name__,
                        'error_message': str(exc),
                        'compatibility_forecast_grid_id': compatibility_row_id,
                    },
                )
        if stage_metrics is not None:
            stage_metrics['compatibility_seconds'] = round(perf_counter() - compatibility_started_at, 3)
        promotion_started_at = perf_counter()
        _record_publication_event_best_effort(
            forecast_run_id=forecast_run_id,
            stage='promote_started',
            status='started',
            artifact_dir=artifact_dir,
            modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
        )
        try:
            promote_forecast_run(forecast_run_id=forecast_run_id)
        except Exception as exc:
            _record_publication_event_best_effort(
                forecast_run_id=forecast_run_id,
                stage='promote_failed',
                status='failed',
                artifact_dir=artifact_dir,
                modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                detail={
                    'error_class': exc.__class__.__name__,
                    'error_message': str(exc),
                },
            )
            raise
        else:
            _record_publication_event_best_effort(
                forecast_run_id=forecast_run_id,
                stage='promote_completed',
                status='ok',
                artifact_dir=artifact_dir,
                modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
            )
        finally:
            if stage_metrics is not None:
                stage_metrics['promotion_seconds'] = round(perf_counter() - promotion_started_at, 3)
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


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description='Generate forecast grids for Avalanche Insight Hub')
    parser.add_argument('--artifact-root', type=Path, default=load_settings().artifact_root)
    parser.add_argument('--artifact-dir', type=Path)
    parser.add_argument('--forecast-hours', type=int, default=load_settings().forecast_horizon_hours)
    parser.add_argument('--grid-size', type=int, default=load_settings().grid_size)
    parser.add_argument('--dry-run', action='store_true', default=load_settings().dry_run)
    parser.add_argument('--region-key', action='append', default=[])
    parser.add_argument('--lifeboat-mode', action='store_true')
    parser.add_argument('--lifeboat-profile', choices=('proof72', 'smoke24'), default='proof72')
    parser.add_argument('--skip-tree-shap', action='store_true')
    parser.add_argument('--skip-shap-cache', action='store_true')
    parser.add_argument('--skip-runout-generation', action='store_true')
    parser.add_argument('--skip-compatibility-write', action='store_true')
    parser.add_argument('--emit-stage-metrics', action='store_true')
    args = parser.parse_args(raw_argv)

    def _flag_was_explicit(flag: str) -> bool:
        return any(item == flag or item.startswith(f'{flag}=') for item in raw_argv)

    if args.lifeboat_mode:
        if not _flag_was_explicit('--forecast-hours'):
            args.forecast_hours = 24 if args.lifeboat_profile == 'smoke24' else 72
        if not _flag_was_explicit('--grid-size'):
            args.grid_size = 5
        args.skip_tree_shap = True
        args.skip_shap_cache = True
        args.skip_runout_generation = True
        args.skip_compatibility_write = True
        args.emit_stage_metrics = True

    proof_options = ProofModeOptions(
        enabled=bool(args.lifeboat_mode),
        profile=str(args.lifeboat_profile if args.lifeboat_mode else 'standard'),
        skip_tree_shap=bool(args.skip_tree_shap),
        skip_shap_cache=bool(args.skip_shap_cache),
        skip_runout_generation=bool(args.skip_runout_generation),
        skip_compatibility_write=bool(args.skip_compatibility_write),
        emit_stage_metrics=bool(args.emit_stage_metrics),
    )

    current_model_status = _fetch_current_model_status()
    requested_artifact_dir = args.artifact_dir
    if requested_artifact_dir is None and current_model_status is not None:
        requested_artifact_dir = resolve_active_candidate_artifact_dir(args.artifact_root, current_model_status)
    artifact_resolution_started_at = perf_counter()
    try:
        artifact_dir = resolve_artifact_dir(
            args.artifact_root,
            requested_artifact_dir,
            require_model=True,
        )
        bundle = load_joblib(artifact_dir / 'model.joblib')
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
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    except FileNotFoundError:
        raise RuntimeError(
            (
                f'No usable trained model artifact is available at {args.artifact_dir}.'
                if args.artifact_dir
                else 'No trained model artifact is available. Run backend.train_model first; '
                'daily inference no longer bootstraps a synthetic fallback model.'
            )
        )
    artifact_resolution_seconds = round(perf_counter() - artifact_resolution_started_at, 3)

    forecast_date = pd.Timestamp(datetime.now(timezone.utc))
    regions = load_regions()
    requested_region_keys = [
        str(region_key).strip()
        for region_key in args.region_key
        if str(region_key).strip()
    ]
    if proof_options.enabled and not requested_region_keys:
        raise RuntimeError('lifeboat_mode requires at least one --region-key')
    if requested_region_keys:
        region_map = {region.key: region for region in regions}
        missing_region_keys = [
            region_key for region_key in requested_region_keys
            if region_key not in region_map
        ]
        if missing_region_keys:
            raise RuntimeError(f'Unknown region_key(s): {", ".join(missing_region_keys)}')
        seen_region_keys: set[str] = set()
        regions = [
            region_map[region_key]
            for region_key in requested_region_keys
            if not (region_key in seen_region_keys or seen_region_keys.add(region_key))
        ]
    candidate_summary = build_dynamic_model_candidate(
        bundle,
        artifact_dir=artifact_dir,
        model_status_version=f'forecast-{artifact_dir.name}',
    )
    evidence_summary = build_autonomous_evidence_summary(
        bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {},
        sar_volume_stats=candidate_summary.get('sar_volume_stats') if isinstance(candidate_summary, dict) else None,
    )
    active_model_state = resolve_active_model_state(current_model_status, candidate_summary, bundle)

    outputs = []
    stage_metrics_payload: dict[str, Any] = {
        'artifact_dir': str(artifact_dir),
        'artifact_resolution_seconds': artifact_resolution_seconds,
        'proof_mode': proof_options.as_metadata(),
        'regions': [],
    }
    for region in regions:
        region_stage_metrics: dict[str, Any] = {
            'region_key': region.key,
            'compute_started_at': datetime.now(timezone.utc).isoformat(),
        }
        hourly_grid_started_at = perf_counter()
        hourly_grids = build_hourly_grids(
            region,
            bundle,
            grid_size=args.grid_size,
            forecast_date=forecast_date,
            horizon_hours=args.forecast_hours,
            artifact_dir=artifact_dir,
            use_dynamic_inference=bool(active_model_state.get('use_dynamic_inference')),
            proof_options=proof_options,
            stage_metrics=region_stage_metrics,
        )
        region_stage_metrics['hourly_grid_build_seconds'] = round(perf_counter() - hourly_grid_started_at, 3)
        rows = hourly_grids[0] if hourly_grids else []
        payload = upsert_forecast_grid(
            region,
            bundle,
            forecast_date,
            rows,
            len(hourly_grids) or args.forecast_hours,
            hourly_grids=hourly_grids,
            artifact_dir=artifact_dir,
            grid_size=args.grid_size,
            dry_run=bool(args.dry_run),
            active_model_state=active_model_state,
            candidate_summary=candidate_summary,
            evidence_summary=evidence_summary,
            proof_options=proof_options,
            stage_metrics=region_stage_metrics,
        )
        region_stage_metrics['forecast_run_id'] = (payload.get('model_metadata') or {}).get('forecast_run_id')
        region_stage_metrics['status'] = payload.get('status')
        region_stage_metrics['ready_cell_count'] = int(payload.get('ready_cell_count') or 0)
        region_stage_metrics['stale_cell_count'] = int(payload.get('stale_cell_count') or 0)
        outputs.append(payload)
        stage_metrics_payload['regions'].append(region_stage_metrics)

    dump_json(artifact_dir / 'forecast_grids.json', outputs)
    dump_json(artifact_dir / 'inference_stage_metrics.json', stage_metrics_payload)

    inference_manifest = {
        'artifact_dir': str(artifact_dir),
        'compute_job_id': str(os.getenv('COMPUTE_JOB_ID') or os.getenv('JOB_ID') or '').strip() or None,
        'modal_call_id': str(os.getenv('MODAL_CALL_ID') or '').strip() or None,
        'regions_written': len(outputs),
        'total_cells_written': sum(len(payload.get('grid_geojson') or []) for payload in outputs),
        'partial_regions': sum(1 for payload in outputs if payload.get('status') == 'partial'),
        'stale_regions': sum(1 for payload in outputs if payload.get('status') == 'stale'),
        'ready_cells': sum(int(payload.get('ready_cell_count') or 0) for payload in outputs),
        'stale_cells': sum(
            1
            for payload in outputs
            for cell in (payload.get('grid_geojson') or [])
            if cell.get('status') != 'ready'
        ),
        'unavailable_terrain_cells': sum(int(payload.get('unavailable_terrain_cell_count') or 0) for payload in outputs),
        'unavailable_weather_cells': sum(int(payload.get('unavailable_weather_cell_count') or 0) for payload in outputs),
        'dry_run': bool(args.dry_run),
        'stage_metrics_summary': {
            'artifact_resolution_seconds': artifact_resolution_seconds,
            'lifeboat_mode': proof_options.enabled,
            'lifeboat_profile': proof_options.profile if proof_options.enabled else None,
            'region_count': len(stage_metrics_payload['regions']),
            'hourly_grid_build_seconds_total': round(
                sum(float(region_metric.get('hourly_grid_build_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'publication_seconds_total': round(
                sum(float(region_metric.get('publication_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'compatibility_seconds_total': round(
                sum(float(region_metric.get('compatibility_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'promotion_seconds_total': round(
                sum(float(region_metric.get('promotion_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
        },
        'forecast_run_id': next(
            (
                (payload.get('model_metadata') or {}).get('forecast_run_id')
                for payload in outputs
                if isinstance(payload.get('model_metadata'), dict) and (payload.get('model_metadata') or {}).get('forecast_run_id')
            ),
            None,
        ),
        'forecast_run_ids': [
            str((payload.get('model_metadata') or {}).get('forecast_run_id'))
            for payload in outputs
            if isinstance(payload.get('model_metadata'), dict) and (payload.get('model_metadata') or {}).get('forecast_run_id')
        ],
        'forecast_run_ids_by_region': {
            str(payload.get('region_key')): str((payload.get('model_metadata') or {}).get('forecast_run_id'))
            for payload in outputs
            if isinstance(payload.get('model_metadata'), dict) and payload.get('region_key') and (payload.get('model_metadata') or {}).get('forecast_run_id')
        },
        'regions': [
            {
                'region_key': payload.get('region_key'),
                'region_name': payload.get('region_name'),
                'forecast_run_id': (payload.get('model_metadata') or {}).get('forecast_run_id'),
                'forecast_date': payload.get('forecast_date'),
                'horizon_hours': payload.get('horizon_hours'),
                'status': payload.get('status'),
                'cell_count': len(payload.get('grid_geojson') or []),
                'ready_cell_count': int(payload.get('ready_cell_count') or 0),
                'stale_cell_count': int(payload.get('stale_cell_count') or 0),
                'unavailable_terrain_cell_count': int(payload.get('unavailable_terrain_cell_count') or 0),
                'unavailable_weather_cell_count': int(payload.get('unavailable_weather_cell_count') or 0),
                'runout_method_sample': (payload.get('model_metadata') or {}).get('runout_method_sample'),
                'runout_method_counts': (payload.get('model_metadata') or {}).get('runout_method_counts'),
                'training_dataset_version': (payload.get('model_metadata') or {}).get('training_dataset_version'),
                'lifeboat_mode': (payload.get('model_metadata') or {}).get('lifeboat_mode'),
                'lifeboat_profile': (payload.get('model_metadata') or {}).get('lifeboat_profile'),
            }
            for payload in outputs
        ],
        'active_model_type': active_model_state.get('active_model_type'),
        'active_model_version': active_model_state.get('active_model_version'),
        'dynamic_model_candidate': candidate_summary,
        'autonomous_evidence_summary': evidence_summary,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    dump_json(artifact_dir / 'inference_manifest.json', inference_manifest)

    if has_supabase_credentials() and not args.dry_run:
        next_run = (datetime.now(timezone.utc) + pd.Timedelta(hours=24)).isoformat()
        bundle_metrics = bundle.get('metrics') if isinstance(bundle.get('metrics'), dict) else {}
        patch_first_row('model_status', {
            'version': f"forecast-{artifact_dir.name}",
            'last_inference': datetime.now(timezone.utc).isoformat(),
            'capability_summary': 'batch-only forecast_grids',
            'inference_backend': 'batch_async',
            'capabilities': {
                'serving_mode': 'batch_only',
                'serving_summary': 'batch-only forecast_grids',
                'runtime_mode': 'batch_async',
                'runtime_summary': 'batch async precompute via forecast_grids',
            },
            'feature_version': str(bundle.get('dynamic_model_type') or 'surrogate_rf_v1'),
            'calibration_profile_version': str(bundle.get('dynamic_model_version') or bundle.get('created_at')),
            'threshold_profile_version': 'chebyshev_ipa_v2',
            'pss_reported': bundle_metrics.get('pss_reported'),
            'pss_gate_passed': bundle_metrics.get('pss_gate_passed'),
            'promotion_gate_passed': active_model_state.get('promotion_gate_passed'),
            'shadow_mode_active': active_model_state.get('shadow_mode_active'),
            'active_model_type': active_model_state.get('active_model_type'),
            'active_model_version': active_model_state.get('active_model_version'),
            'dynamic_model_candidate': candidate_summary,
            'autonomous_evidence_summary': evidence_summary,
            'next_run': next_run,
        })

    print(json.dumps(inference_manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
