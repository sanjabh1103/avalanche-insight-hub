"""Grid construction helpers — extracted from backend/daily_inference.py.

Functions:
    _build_unavailable_cell
    _prepare_region_context
    _build_rows_for_timestamp
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from backend.common.avalanche_prone_terrain import APT_PROFILE, apply_apt_unified_metric
from backend.common.avalanche_problem_classifier import classify_avalanche_problem
from backend.common.dual_explainability import build_physics_narrative, physics_narrative_to_dict
from backend.common.features import FEATURE_COLUMNS, build_region_grid
from backend.common.public_eligibility import PUBLIC_ELIGIBILITY_PROFILE, SNOW_ELEVATION_PROFILE, apply_public_eligibility_metric
from backend.common.real_features import (
    TerrainUnavailableError,
    build_real_feature_row,
    extract_cell_terrain,
    fetch_ensemble_weather_profile,
    fetch_forecast_weather_profile,
    fetch_historical_weather_window,
    select_hourly_weather_sample,
)
from backend.common.regions import repo_root
from backend.common.risk_math import DEFAULT_IPA_WEIGHTS
from backend.common.runout import RUN_PHYSICS_RUNOUT
from backend.common.seismic_integrator import (
    HIMALAYAN_BBOX,
    SEISMIC_MIN_MAGNITUDE,
    SeismicAmplification,
    apply_seismic_amplification,
    check_active_windows,
    compute_seismic_amplification,
    fetch_recent_earthquakes,
)
from backend.common.snowpack_physics import (
    SnowpackPhysicsResult,
    compute_cell_snowpack_physics,
    compute_grid_snowpack_physics,
    _heuristic_to_physics_result,
)
from backend.common.snowpack_proxy import (
    SnowpackProxy,
    SnowpackProxyBatchResult,
    compute_region_snowpack_proxy,
    fetch_batched_cell_snowpack_proxies_partial,
    snowpack_proxy_to_payload,
    winter_season_start,
)
from backend.common.terrain_diagnostics import classify_terrain_failure
from backend.common.supabase_io import has_supabase_credentials, rest_get, rest_upsert
from backend.common.gibs_ingestion import (
    GIBS_ENABLED,
    fetch_gibs_snow_cover_batch,
)
from backend.common.s1_snow_depth import (
    S1_DEPTH_ENABLED,
    estimate_s1_snow_depth,
)
from backend.common.sequence_features import build_inference_branches, extract_zone_onehot
from backend.common.verification_contracts import VERIFICATION_SPINE_ENABLED
from backend.inference.options import ProofModeOptions
from backend.inference.utils import _dem_path
from backend.daily_inference import (
    _load_ipa_weights,
    risk_level,
    terrain_adjusted_risk_level,
    uncertainty_class,
)
from backend.daily_inference import (
    _compute_cell_coverage_flags,
    _fetch_latest_sar_summary,
)
from backend.daily_inference import (
    _build_fusion_evidence,
    _build_verification_packet,
    _compute_cell_baselines_from_history,
    _persist_review_queue,
    _persist_sensor_observations,
)
from backend.lstm_model import predict_production_probability
from backend.models.surrogate_rf import (
    TreeShapUnavailableError,
    build_tree_shap_explainer,
    collect_tree_probabilities,
    compute_tree_shap,
    compute_tree_shap_batch,
)


def _default_inference_backend(bundle: dict[str, object]) -> str:
    lstm_head = bundle.get('lstm_head') if isinstance(bundle, dict) else None
    if getattr(lstm_head, 'model', None) is not None:
        return 'github_actions_mts_lstm'
    return 'github_actions_surrogate_rf'


def _build_unavailable_cell(
    *,
    cell: dict[str, object],
    center_lat: float,
    center_lng: float,
    bundle: dict[str, object],
    snowpack_proxy: object | None,
    reason: str,
    terrain_failure_reason: str | None = None,
) -> dict[str, object]:
    proxy_payload = snowpack_proxy_to_payload(
        snowpack_proxy if isinstance(snowpack_proxy, SnowpackProxy) else None
    )
    return apply_public_eligibility_metric(apply_apt_unified_metric({
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
            **(
                {'failure_reason': terrain_failure_reason}
                if terrain_failure_reason
                else {}
            ),
        },
        'terrain_failure_reason': terrain_failure_reason,
        'dominant_driver_feature': None,
        'runout_seed': False,
        'dynamic_model_type': bundle.get('dynamic_model_type'),
        'dynamic_model_version': bundle.get('dynamic_model_version'),
        'surrogate_model_version': bundle.get('surrogate_model_version'),
        'forecast_mode': bundle.get('forecast_mode', 'full'),
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
    }))



def _prepare_region_context(
    region,
    bundle,
    grid_size: int,
    forecast_date: pd.Timestamp,
    *,
    artifact_dir: Path | None = None,
    proof_options: ProofModeOptions | None = None,
    snowpack_proxy_mode: str = 'cell',
    stage_metrics: dict[str, Any] | None = None,
) -> dict[str, object]:
    proof_options = proof_options or ProofModeOptions()
    snowpack_proxy_mode = str(snowpack_proxy_mode or 'cell').strip().lower()
    if snowpack_proxy_mode not in {'cell', 'regional', 'synthetic'}:
        raise ValueError(f'Unsupported snowpack_proxy_mode: {snowpack_proxy_mode}')
    context_started_at = perf_counter()
    region_grid = build_region_grid(region, grid_size=grid_size)
    weather_profile = fetch_forecast_weather_profile(region.center, forecast_date.to_pydatetime(), 72)
    ensemble_profile: dict[str, object] | None = None
    try:
        ensemble_profile = fetch_ensemble_weather_profile(region.center, forecast_date.to_pydatetime(), 72)
    except Exception as exc:
        print(f'[daily_inference] ensemble profile skipped: {exc}', file=sys.stderr)
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
    if snowpack_proxy_mode == 'cell':
        snowpack_results = fetch_batched_cell_snowpack_proxies_partial(
            coordinates=cell_centers,
            as_of=forecast_date.to_pydatetime(),
            cache_path=(
                artifact_dir / 'snowpack_proxy_cache' / f'{region.key}-{forecast_date.date().isoformat()}.json'
                if artifact_dir is not None
                else None
            ),
        )
    elif snowpack_proxy_mode == 'regional':
        regional_proxy = compute_region_snowpack_proxy(
            center_lat=float(region.center[0]),
            center_lng=float(region.center[1]),
            as_of=forecast_date.to_pydatetime(),
            cells=[],
        )
        snowpack_results = [
            SnowpackProxyBatchResult(proxy=regional_proxy, status='ready')
            for _ in region_grid
        ]
    else:
        synthetic_proxy = SnowpackProxy(
            estimated_shear_strength=3.0,
            snow_settlement_index=0.3,
            season_start=winter_season_start(forecast_date.to_pydatetime()).isoformat(),
            method='synthetic_full_grid_publication_v1',
        )
        snowpack_results = [
            SnowpackProxyBatchResult(proxy=synthetic_proxy, status='ready')
            for _ in region_grid
        ]
    if len(snowpack_results) != len(region_grid):
        raise RuntimeError(
            f'Snowpack proxy count mismatch for {region.key}: '
            f'expected {len(region_grid)}, received {len(snowpack_results)}'
        )
    if stage_metrics is not None:
        stage_metrics['snowpack_fetch_seconds'] = round(perf_counter() - snowpack_started_at, 3)
        stage_metrics['snowpack_proxy_mode'] = snowpack_proxy_mode

    dem_path = _dem_path(region.key)
    prepared_cells: list[dict[str, object]] = []
    valid_cells_for_physics: list[dict[str, Any]] = []

    for cell, (center_lat, center_lng), snowpack_result in zip(region_grid, cell_centers, snowpack_results):
        snowpack_proxy = snowpack_result.proxy
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=center_lat, lng=center_lng)
        except (TerrainUnavailableError, ValueError, FileNotFoundError, OSError) as exc:
            prepared_cells.append({
                'cell': cell,
                'center_lat': center_lat,
                'center_lng': center_lng,
                'snowpack_proxy': snowpack_proxy,
                'terrain': None,
                'availability_reason': 'unavailable_terrain',
                'terrain_failure_reason': classify_terrain_failure(exc),
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
        cell_index = len(prepared_cells)
        prepared_cells.append({
            'cell': cell,
            'center_lat': center_lat,
            'center_lng': center_lng,
            'snowpack_proxy': snowpack_proxy,
            'snowpack_physics': None,
            'terrain': terrain,
            'availability_reason': None,
        })
        valid_cells_for_physics.append({
            'cell_id': f'cell_{cell_index}',
            'lat': center_lat,
            'lng': center_lng,
            'elevation_m': float(terrain.get('elevation_m', 3000.0)) if isinstance(terrain, dict) else 3000.0,
            'zone_type': getattr(region, 'zone_type', None),
        })

    # F5: Batch physics computation for grids with > 10 valid cells
    if len(valid_cells_for_physics) > 10:
        physics_started_at = perf_counter()
        try:
            zone_type = getattr(region, 'zone_type', None)
            weather_inputs_fn = lambda lat, lng: {}  # lightweight — heuristic fallback used in batch
            terrain_inputs_fn = lambda lat, lng: {}
            physics_results = compute_grid_snowpack_physics(
                grid_cells=valid_cells_for_physics,
                as_of=forecast_date.to_pydatetime(),
                weather_inputs_fn=weather_inputs_fn,
                terrain_inputs_fn=terrain_inputs_fn,
                zone_type=zone_type,
            )
            for cell_entry in valid_cells_for_physics:
                cell_id = cell_entry['cell_id']
                cell_idx = int(cell_id.split('_')[1])
                result = physics_results.get(cell_id)
                if result is not None:
                    prepared_cells[cell_idx]['snowpack_physics'] = result
                else:
                    proxy = prepared_cells[cell_idx].get('snowpack_proxy')
                    if proxy:
                        prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
            if stage_metrics is not None:
                stage_metrics['snowpack_physics_batch_seconds'] = round(perf_counter() - physics_started_at, 3)
                stage_metrics['snowpack_physics_mode'] = 'grid_batch'
        except Exception:
            # Fallback to heuristic for all valid cells
            for cell_entry in valid_cells_for_physics:
                cell_idx = int(cell_entry['cell_id'].split('_')[1])
                proxy = prepared_cells[cell_idx].get('snowpack_proxy')
                if proxy:
                    prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
            if stage_metrics is not None:
                stage_metrics['snowpack_physics_mode'] = 'heuristic_fallback_batch_error'
    else:
        # Small grid: use per-cell heuristic
        for cell_entry in valid_cells_for_physics:
            cell_idx = int(cell_entry['cell_id'].split('_')[1])
            proxy = prepared_cells[cell_idx].get('snowpack_proxy')
            if proxy:
                prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
        if stage_metrics is not None:
            stage_metrics['snowpack_physics_mode'] = 'heuristic_per_cell'
    if stage_metrics is not None:
        stage_metrics['region_context_prep_seconds'] = round(perf_counter() - context_started_at, 3)

    explainability_context: dict[str, object] = {
        'mode': 'tree_shap',
        'reason': None,
        'detail': None,
    }
    explainer = None
    if proof_options.skip_tree_shap:
        explainability_context = {
            'mode': 'heuristic_fallback',
            'reason': 'proof_mode_skip_tree_shap',
            'detail': 'TreeSHAP explicitly skipped by proof mode.',
        }
    else:
        try:
            explainer = build_tree_shap_explainer(bundle['base_model'])
        except TreeShapUnavailableError as exc:
            explainability_context = {
                'mode': 'heuristic_fallback',
                'reason': 'shap_dependency_unavailable',
                'detail': str(exc),
            }
        except Exception as exc:  # pragma: no cover - defensive
            explainability_context = {
                'mode': 'heuristic_fallback',
                'reason': 'tree_shap_initialization_failed',
                'detail': str(exc),
            }

    return {
        'selector': bundle['selector'],
        'calibrated_model': bundle['calibrated_model'],
        'base_model': bundle['base_model'],
        'selected_features': bundle['selected_features'],
        'ipa_weights': _load_ipa_weights(),
        'lstm_head': bundle.get('lstm_head') if isinstance(bundle, dict) else None,
        'sar_summary': _fetch_latest_sar_summary(region.key),
        'explainer': explainer,
        'explainability_context': explainability_context,
        'weather_profile': weather_profile,
        'forecast_samples': weather_profile.get('samples') if isinstance(weather_profile, dict) else [],
        'ensemble_profile': ensemble_profile,
        'ensemble_samples': ensemble_profile.get('samples') if ensemble_profile and isinstance(ensemble_profile, dict) else [],
        'history_samples': history_profile.get('samples') if isinstance(history_profile, dict) else [],
        'prepared_cells': prepared_cells,
        'timezone_name': str(getattr(region, 'timezone_name', 'UTC') or 'UTC'),
        'zone_type': getattr(region, 'zone_type', None),
        'region_key': region.key,
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
    seismic_events: list[Any] | None = None,
) -> list[dict[str, object]]:
    proof_options = proof_options or ProofModeOptions()
    seismic_events = seismic_events or []
    selector = region_context['selector']
    calibrated_model = region_context['calibrated_model']
    base_model = region_context['base_model']
    selected_features: list[str] = region_context['selected_features']  # type: ignore[assignment]
    ipa_weights: dict[str, float] = region_context['ipa_weights']  # type: ignore[assignment]
    lstm_head = region_context['lstm_head']
    sar_summary: dict[str, object] = region_context['sar_summary']  # type: ignore[assignment]
    explainer = region_context['explainer']
    explainability_context: dict[str, object] = region_context['explainability_context']  # type: ignore[assignment]
    history_samples: list[object] = region_context['history_samples']  # type: ignore[assignment]
    timezone_name = str(region_context.get('timezone_name') or 'UTC')
    prepared_cells = list(region_context['prepared_cells'])  # type: ignore[arg-type]
    row_slots: list[dict[str, object] | None] = [None for _ in prepared_cells]
    ready_items: list[dict[str, object]] = []
    bundle_feature_columns = (
        bundle.get('feature_columns')
        if isinstance(bundle.get('feature_columns'), list)
        else FEATURE_COLUMNS
    )

    for slot_index, prepared in enumerate(prepared_cells):
        cell = prepared['cell']
        center_lat = float(prepared['center_lat'])
        center_lng = float(prepared['center_lng'])
        snowpack_proxy = prepared['snowpack_proxy']
        availability_reason = prepared['availability_reason']
        if availability_reason:
            row_slots[slot_index] = _build_unavailable_cell(
                cell=cell,
                center_lat=center_lat,
                center_lng=center_lng,
                bundle=bundle,
                snowpack_proxy=snowpack_proxy,
                reason=str(availability_reason),
                terrain_failure_reason=(
                    str(prepared.get('terrain_failure_reason'))
                    if prepared.get('terrain_failure_reason')
                    else None
                ),
            )
            continue

        terrain = prepared['terrain']
        snowpack_physics = prepared.get('snowpack_physics')
        assembled = build_real_feature_row(
            weather_sample=weather_sample or {},
            terrain=terrain,
            timestamp=forecast_time.to_pydatetime(),
            lat=center_lat,
            lng=center_lng,
            snowpack_proxy_override=snowpack_proxy,
            snowpack_physics_override=snowpack_physics,
        )
        feature_row = assembled['feature_row']
        ready_items.append({
            'slot_index': slot_index,
            'cell': cell,
            'center_lat': center_lat,
            'center_lng': center_lng,
            'snowpack_proxy': snowpack_proxy,
            'snowpack_physics': snowpack_physics,
            'terrain': terrain,
            'assembled': assembled,
            'feature_row': feature_row,
        })

    if not ready_items:
        return [row for row in row_slots if row is not None]

    feature_frame = pd.DataFrame(
        [item['feature_row'] for item in ready_items],
        columns=bundle_feature_columns,
    )
    selected_frame_all = pd.DataFrame(
        selector.transform(feature_frame),
        columns=selected_features,
    )
    probability_matrix = np.asarray(collect_tree_probabilities(base_model, selected_frame_all))
    rf_probabilities = np.asarray(calibrated_model.predict_proba(selected_frame_all)[:, 1], dtype=float)
    tree_shap_packets: list[tuple[dict[str, float], list[dict[str, float | str | int]]]] = []
    if not proof_options.skip_tree_shap and explainer is not None:
        try:
            tree_shap_packets = compute_tree_shap_batch(explainer, selected_frame_all, selected_features)
        except Exception:
            # Preserve the existing single-row TreeSHAP fallback for mocked
            # explainers and runtimes where batch SHAP fails unexpectedly.
            tree_shap_packets = []

    # --- Verification spine: batch-fetch GIBS snow cover for all ready cells ---
    gibs_results: list[float | None] = [None] * len(ready_items)
    if VERIFICATION_SPINE_ENABLED and GIBS_ENABLED:
        cell_coords = [
            (float(item['center_lat']), float(item['center_lng']))
            for item in ready_items
        ]
        try:
            gibs_batch = fetch_gibs_snow_cover_batch(
                cell_coords, target_date=forecast_time.to_pydatetime(),
            )
            gibs_results = [
                r.snow_cover_fraction if r is not None else None
                for r in gibs_batch
            ]
        except Exception:
            gibs_results = [None] * len(ready_items)

    # --- Verification spine: batch-fetch S2 snow cover when enabled ---
    s2_results: dict[str, Any] = {}
    if VERIFICATION_SPINE_ENABLED:
        try:
            from backend.common.sentinel2_snow_mapper import (
                S2_SNOW_ENABLED as _s2_enabled,
                map_s2_snow_batch as _map_s2,
            )
            if _s2_enabled:
                s2_cells = [
                    {'cell_id': f'cell_{int(item["slot_index"])}',
                     'lat': float(item['center_lat']),
                     'lng': float(item['center_lng'])}
                    for item in ready_items
                ]
                s2_results = _map_s2(
                    cells=s2_cells,
                    target_date=forecast_time.to_pydatetime(),
                )
        except Exception:
            s2_results = {}

    # --- Verification spine: compute baselines per cell from history ---
    cell_baselines: dict[str, tuple[float | None, float | None, float | None]] = {}
    if VERIFICATION_SPINE_ENABLED:
        forecast_dt = forecast_time.to_pydatetime()
        for item in ready_items:
            cid = f'cell_{int(item["slot_index"])}'
            cell_baselines[cid] = _compute_cell_baselines_from_history(
                cell_id=cid,
                region_key=region_context['region_key'],
                as_of=forecast_dt,
            )

    for ready_index, ready_item in enumerate(ready_items):
        cell = ready_item['cell']
        center_lat = float(ready_item['center_lat'])
        center_lng = float(ready_item['center_lng'])
        terrain = ready_item['terrain']
        assembled = ready_item['assembled']
        feature_row = ready_item['feature_row']
        selected_frame = selected_frame_all.iloc[[ready_index]]
        if probability_matrix.ndim == 2:
            probabilities = probability_matrix[ready_index]
        elif probability_matrix.ndim == 1 and probability_matrix.shape[0] == len(ready_items):
            probabilities = np.asarray([probability_matrix[ready_index]])
        else:
            probabilities = probability_matrix
        rf_probability = float(rf_probabilities[ready_index])
        dynamic_candidate_available = (
            lstm_head is not None and getattr(lstm_head, 'model', None) is not None
        )
        sequence_branches = None
        zone_type = region_context.get('zone_type')
        zone_onehot = extract_zone_onehot(zone_type) if isinstance(zone_type, str) else None
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
                zone_type=zone_type if isinstance(zone_type, str) else None,
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
                zone_onehot=zone_onehot,
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
        vulnerability = float(np.clip(feature_row['aspect_loading'] * 0.6 + feature_row['wind_loading'] * 0.4, 0, 1))
        risk, terrain_risk_score, chebyshev_distance, hazard_vector, limiting_factor, ipa_score, ipa_risk, impact_score, impact_level = terrain_adjusted_risk_level(
            calibrated_probability,
            float(terrain['slope_angle_deg']),
            aspect_risk=float(feature_row['aspect_loading']),
            snowpack_shear_strength=float(assembled['snowpack_proxy'].estimated_shear_strength),
            exposure=exposure,
            vulnerability=vulnerability,
            weights=ipa_weights,
        )
        probability_risk = risk_level(calibrated_probability)

        # F1: Seismic Cascade Integrator — apply post-tremor risk amplification
        seismic_amplification = None
        if seismic_events:
            seismic_amplification = compute_seismic_amplification(
                center_lat, center_lng, seismic_events, forecast_time.to_pydatetime(),
            )
        if seismic_amplification:
            calibrated_probability = apply_seismic_amplification(calibrated_probability, seismic_amplification)
            risk = max(risk, risk_level(calibrated_probability))
            probability_risk = max(probability_risk, risk_level(calibrated_probability))

        if proof_options.skip_tree_shap or explainer is None:
            shap_values = {}
            shap_context = []
            dominant_driver = None
            explainability_mode = str(explainability_context.get('mode') or 'heuristic_fallback')
            explainability_reason = (
                str(explainability_context.get('reason'))
                if explainability_context.get('reason') is not None
                else None
            )
        else:
            if ready_index < len(tree_shap_packets):
                shap_values, shap_context = tree_shap_packets[ready_index]
            else:
                shap_values, shap_context = compute_tree_shap(explainer, selected_frame, selected_features)
            dominant_driver = shap_context[0]['feature'] if shap_context else None
            explainability_mode = 'tree_shap'
            explainability_reason = None
        raw_inputs = assembled['raw_inputs'] if isinstance(assembled.get('raw_inputs'), dict) else {}
        classifier_weather_inputs = {
            'downscaled_temperature_c': raw_inputs.get('downscaled_temperature_c'),
            'snowfall_24h_cm': raw_inputs.get('snowfall_24h_cm', 0.0),
            'precipitation_24h_mm': raw_inputs.get('precipitation_24h_mm', 0.0),
            'snow_depth_cm': raw_inputs.get('snow_depth_cm'),
            'wind_loading': feature_row['wind_loading'],
        }
        classifier_terrain_inputs = {
            'aspect_loading': feature_row['aspect_loading'],
            'aspect_deg': terrain['aspect_deg'],
        }
        classified_problem = classify_avalanche_problem(
            weather_inputs=classifier_weather_inputs,
            terrain_inputs=classifier_terrain_inputs,
            snowpack_proxy={
                'estimated_shear_strength': assembled['snowpack_proxy'].estimated_shear_strength,
                'snow_settlement_index': assembled['snowpack_proxy'].snow_settlement_index,
                'method': assembled['snowpack_proxy'].method,
            },
            forecast_time=forecast_time.to_pydatetime(),
            timezone_name=timezone_name,
        )
        row_slots[int(ready_item['slot_index'])] = apply_public_eligibility_metric(apply_apt_unified_metric({
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
            'terrain_fused_risk_score': risk,
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
            'vulnerability': vulnerability,
            'impact_risk_score': impact_score,
            'impact_risk_level': impact_level,
            'problem_type': classified_problem['problem_type'],
            'problem_slug': classified_problem['problem_slug'],
            'problem_confidence': classified_problem['problem_confidence'],
            'problem_evidence': classified_problem['problem_evidence'],
            'problem_classifier_profile': classified_problem['problem_classifier_profile'],
            'dry_wet_domain': classified_problem['dry_wet_domain'],
            'shap_values': shap_values,
            'shap_context': {
                'top_features': shap_context,
                'limiting_factor': limiting_factor,
                'hazard_vector': hazard_vector,
                'fusion_method': 'chebyshev_ipa_v2',
            },
            'explainability_mode': explainability_mode,
            'explainability_reason': explainability_reason,
            'feature_values': selected_frame.iloc[0].to_dict(),
            'explanation_summary': None,
            'coverage_flags': _compute_cell_coverage_flags(terrain, sar_summary),
            'selected_features': selected_features,
            'weather_inputs': {
                'snowfall_24h': feature_row['snowfall_24h'],
                'wind_loading': feature_row['wind_loading'],
                'temp_gradient': feature_row['temp_gradient'],
                'freezing_level_proxy': feature_row['freezing_level_proxy'],
                'temperature_2m': raw_inputs.get('temperature_2m'),
                'windspeed_10m': raw_inputs.get('windspeed_10m'),
                'winddirection_10m': raw_inputs.get('winddirection_10m'),
                'downscaled_temperature_c': raw_inputs.get('downscaled_temperature_c'),
                'snowfall_24h_cm': raw_inputs.get('snowfall_24h_cm', 0.0),
                'precipitation_24h_mm': raw_inputs.get('precipitation_24h_mm', 0.0),
                'freezing_level_height_m': raw_inputs.get('freezing_level_height'),
                'snow_depth_cm': raw_inputs.get('snow_depth_cm'),
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
            'forecast_mode': bundle.get('forecast_mode', 'full'),
            'seismic_amplification': (
                {
                    'factor': seismic_amplification.factor,
                    'window_phase': seismic_amplification.window_phase,
                    'hours_since_event': seismic_amplification.hours_since_event,
                    'magnitude': seismic_amplification.magnitude,
                    'epicenter_distance_km': seismic_amplification.epicenter_distance_km,
                    'epicenter_lat': seismic_amplification.epicenter_lat,
                    'epicenter_lng': seismic_amplification.epicenter_lng,
                }
                if seismic_amplification else None
            ),
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
            'snowpack_proxy': snowpack_proxy_to_payload(assembled['snowpack_proxy']),
            'physics_narrative': physics_narrative_to_dict(
                build_physics_narrative(
                    snowpack_physics=ready_item.get('snowpack_physics'),
                    seismic_amplification=seismic_amplification,
                    zone_type=zone_type if isinstance(zone_type, str) else None,
                    risk_score=risk,
                )
            ),
            'status': 'ready',
            'stale': False,
            'disabled': False,
            'availability_reason': None,
            **(
                lambda: (
                    lambda _cell_id, _gibs, _s2_res, _bp25, _bp50, _bp75, _s1_depth: (
                        lambda _vp, _fe: {
                            'verification_packet': _vp,
                            'fusion_evidence': _fe,
                            'anomaly_score': _vp.get('residual_zscore'),
                            'discrepancy_reasons': _vp.get('disagreement_reasons', []),
                        }
                    )(
                        _build_verification_packet(
                            cell_id=_cell_id,
                            region_key=region_context['region_key'],
                            sar_summary=sar_summary,
                            weather_inputs=raw_inputs,
                            snowpack_method=assembled['snowpack_proxy'].method,
                            gibs_snow_cover=_gibs,
                            s2_snow_cover=_s2_res.snow_cover_fraction if _s2_res else None,
                            s2_cloud_cover=_s2_res.cloud_cover if _s2_res else None,
                            s2_scene_id=_s2_res.scene_id if _s2_res else None,
                            s2_acquisition_time=_s2_res.acquisition_time if _s2_res else None,
                            s2_lineage_sha256=(
                                _s2_res.metadata.get('lineage_sha256')
                                if _s2_res and isinstance(_s2_res.metadata, dict) else None
                            ),
                            s1_depth_m=_s1_depth,
                            baseline_p25=_bp25,
                            baseline_p50=_bp50,
                            baseline_p75=_bp75,
                        ),
                        _build_fusion_evidence(
                            sar_summary=sar_summary,
                            weather_inputs=raw_inputs,
                            gibs_snow_cover=_gibs,
                            s2_snow_cover=_s2_res.snow_cover_fraction if _s2_res else None,
                            s2_cloud_cover=_s2_res.cloud_cover if _s2_res else None,
                            s1_depth_m=_s1_depth,
                        ),
                    )
                )(
                    f'cell_{int(ready_item["slot_index"])}',
                    gibs_results[ready_index] if ready_index < len(gibs_results) else None,
                    s2_results.get(f'cell_{int(ready_item["slot_index"])}'),
                    *(cell_baselines.get(f'cell_{int(ready_item["slot_index"])}', (None, None, None))),
                    (
                        lambda _s1r: _s1r.snow_depth_m if _s1r is not None else None
                    )(
                        estimate_s1_snow_depth(
                            cell_id=f'cell_{int(ready_item["slot_index"])}',
                            vh_db=sar_summary.get('vh_db') if isinstance(sar_summary, dict) else None,
                            vv_db=sar_summary.get('vv_db') if isinstance(sar_summary, dict) else None,
                            wet_snow_fraction=sar_summary.get('wet_snow_fraction') if isinstance(sar_summary, dict) else None,
                            weather_snow_depth_m=(
                                float(raw_inputs.get('snow_depth_cm', 0)) / 100.0
                                if raw_inputs.get('snow_depth_cm') is not None else None
                            ),
                        ) if S1_DEPTH_ENABLED and isinstance(sar_summary, dict) else None
                    ),
                )
                if VERIFICATION_SPINE_ENABLED
                else {}
            )(),
        }))

    result_rows = [row for row in row_slots if row is not None]

    # --- Verification spine: persist sensor observations for future baselines ---
    if VERIFICATION_SPINE_ENABLED and result_rows:
        _persist_sensor_observations(
            region_key=region_context['region_key'],
            cells=result_rows,
            run_timestamp=forecast_time.to_pydatetime(),
        )
        # --- Active learning: rank cells and persist to review queue ---
        _persist_review_queue(
            region_key=region_context['region_key'],
            cells=result_rows,
        )

    return result_rows





def build_cells(
    region,
    bundle,
    grid_size: int,
    forecast_date: pd.Timestamp,
    *,
    artifact_dir: Path | None = None,
    use_dynamic_inference: bool = False,
    proof_options: ProofModeOptions | None = None,
    snowpack_proxy_mode: str = 'cell',
    stage_metrics: dict[str, Any] | None = None,
):
    region_context = _prepare_region_context(
        region,
        bundle,
        grid_size,
        forecast_date,
        artifact_dir=artifact_dir,
        proof_options=proof_options,
        snowpack_proxy_mode=snowpack_proxy_mode,
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
    snowpack_proxy_mode: str = 'cell',
    stage_metrics: dict[str, Any] | None = None,
    seismic_events: list[Any] | None = None,
) -> tuple[list[list[dict[str, object]]], dict[str, object] | None]:
    region_context = _prepare_region_context(
        region,
        bundle,
        grid_size,
        forecast_date,
        artifact_dir=artifact_dir,
        proof_options=proof_options,
        snowpack_proxy_mode=snowpack_proxy_mode,
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
                seismic_events=seismic_events,
            )
        )
        if stage_metrics is not None:
            stage_metrics['hourly_grid_progress'] = {
                'completed_hours': hour_offset + 1,
                'total_hours': effective_horizon_hours,
                'latest_hour_offset': hour_offset,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
            if artifact_dir is not None:
                dump_json(
                    artifact_dir / f'{region.key}_hourly_progress.json',
                    {
                        'region_key': region.key,
                        'completed_hours': hour_offset + 1,
                        'total_hours': effective_horizon_hours,
                        'latest_hour_offset': hour_offset,
                        'updated_at': stage_metrics['hourly_grid_progress']['updated_at'],
                    },
                )
            if hour_offset == 0 or (hour_offset + 1) % 6 == 0 or (hour_offset + 1) == effective_horizon_hours:
                print(
                    json.dumps({
                        'stage': 'hourly_grid_progress',
                        'region_key': region.key,
                        'completed_hours': hour_offset + 1,
                        'total_hours': effective_horizon_hours,
                    }),
                    file=sys.stderr,
                    flush=True,
                )
    return hourly_grids, region_context.get('ensemble_profile')
