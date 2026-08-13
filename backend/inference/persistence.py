"""Persistence and publication orchestration — extracted from backend/daily_inference.py.

Contains the upsert_forecast_grid and _upsert_shap_cache helpers.
"""
from __future__ import annotations

import json
import os
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
from backend.common.public_eligibility import (
    PUBLIC_ELIGIBILITY_PROFILE,
    SNOW_ELEVATION_PROFILE,
    apply_public_eligibility_metric,
)
from backend.common.real_features import (
    TerrainUnavailableError,
    build_real_feature_row,
    extract_cell_terrain,
    fetch_ensemble_weather_profile,
    fetch_forecast_weather_profile,
    fetch_historical_weather_window,
)
from backend.common.terrain_diagnostics import count_runtime_terrain_failure_reasons
from backend.common.regions import repo_root
from backend.common.risk_math import DEFAULT_IPA_WEIGHTS
from backend.common.runout import RUN_PHYSICS_RUNOUT, build_runout_polygons
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
    winter_season_start,
)
from backend.common.supabase_io import (
    has_supabase_credentials,
    rest_get,
    rest_insert,
    rest_upsert,
)
from backend.common.uncertainty_quantification import apply_uq_to_cells, ConformalCalibrator, load_calibrator_from_csv
from backend.common.verification_contracts import VERIFICATION_SPINE_ENABLED
from backend.inference.options import ProofModeOptions
from backend.daily_inference import (
    _execution_linkage,
    _record_publication_event_best_effort,
    _summarize_snowpack_lineage,
    build_publication_proof,
)
from backend.daily_inference import (
    _load_ipa_weights,
    risk_level,
    terrain_adjusted_risk_level,
    uncertainty_class,
)
from backend.daily_inference import (
    _compute_cell_coverage_flags,
    _fetch_latest_sar_summary,
    _fetch_region_sar_evidence,
)
from backend.inference.utils import _is_truthy_env
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


def _runout_method_counts(runout_polygons: list[dict[str, object]]) -> dict[str, int]:
    """Count runout polygon generation methods."""
    counts: dict[str, int] = {}
    for polygon in runout_polygons:
        method = polygon.get('method') or 'unknown'
        counts[method] = counts.get(method, 0) + 1
    return counts




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
    ensemble_profile: dict[str, object] | None = None,
    seismic_events: list[Any] | None = None,
    cadence_context: Any | None = None,
):
    proof_options = proof_options or ProofModeOptions()
    seismic_events = seismic_events or []
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
    terrain_failure_reason_counts = count_runtime_terrain_failure_reasons(rows)
    ready_cell_count = len(rows) - len(stale_cells)
    if ready_cell_count == len(rows):
        region_status = 'ready'
    elif ready_cell_count > 0:
        region_status = 'partial'
    else:
        region_status = 'stale'
    if hourly_grids is not None:
        forecast_bulletins = build_daypart_forecast_bulletin(
            hourly_grids=hourly_grids,
            region_status=region_status,
            forecast_date=forecast_date,
            timezone_name=str(getattr(region, 'timezone_name', 'UTC') or 'UTC'),
            horizon_hours=horizon_hours,
        )
    else:
        forecast_bulletins = build_forecast_bulletin(rows=rows, region_status=region_status)
    source_health = build_source_health_summary(
        rows=rows,
        weather_inputs=weather_inputs,
        sar_evidence=sar_evidence,
        region_status=region_status,
        generated_at=forecast_date.isoformat(),
        evidence_summary=evidence_summary if isinstance(evidence_summary, dict) else None,
    )
    snowfall_avg = float(np.mean([item.get('snowfall_24h_cm', item.get('snowfall_24h', 0) * 40) for item in weather_inputs])) if weather_inputs else 0.0
    wind_avg = float(np.mean([item.get('windspeed_10m', item.get('wind_loading', 0) * 55) for item in weather_inputs])) if weather_inputs else 0.0
    temperature_avg = float(np.mean([item.get('downscaled_temperature_c', item.get('temperature_2m', 0)) for item in weather_inputs])) if weather_inputs else 0.0
    precipitation_avg = float(np.mean([item.get('precipitation_24h_mm', item.get('snowfall_24h', 0) * 45) for item in weather_inputs])) if weather_inputs else 0.0
    snow_depth_proxy = float(np.mean([item.get('snow_depth_cm', 0.0) for item in weather_inputs])) if weather_inputs else 0.0
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
    ready_explainability_modes = {
        str(row.get('explainability_mode') or 'unavailable')
        for row in rows
        if row.get('status') == 'ready'
    }
    explainability_mode = (
        'tree_shap'
        if ready_explainability_modes == {'tree_shap'}
        else 'heuristic_fallback'
        if 'heuristic_fallback' in ready_explainability_modes
        else 'unavailable'
    )
    explainability_reason = next(
        (
            str(row.get('explainability_reason'))
            for row in rows
            if row.get('status') == 'ready' and row.get('explainability_reason')
        ),
        None,
    )
    decision_provenance = build_decision_provenance(
        threshold_profile='heuristic-risk-bands-v1',
        calibration_profile_version=str(
            bundle.get('calibration_profile_version')
            or bundle.get('calibration_method')
            or bundle.get('created_at')
        ),
        calibration_method=str(bundle.get('calibration_method') or 'unavailable'),
        frequency_threshold_profile=(
            forecast_bulletins.get('frequency_threshold_profile')
            if isinstance(forecast_bulletins, dict)
            else None
        ),
        derived_from=forecast_bulletins.get('derived_from') if isinstance(forecast_bulletins, dict) else None,
        explainability_mode=explainability_mode,
        selected_feature_count=len(bundle.get('selected_features') or []),
    )
    if isinstance(forecast_bulletins, dict):
        forecast_bulletins = {
            **forecast_bulletins,
            'source_health': source_health,
            'decision_provenance': decision_provenance,
        }
    snowpack_lineage = _summarize_snowpack_lineage(rows)
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
        'apt_profile': APT_PROFILE,
        'snow_elevation_profile': SNOW_ELEVATION_PROFILE,
        'public_eligibility_profile': PUBLIC_ELIGIBILITY_PROFILE,
        'public_risk_metric': 'public_eligible_probability_risk_score_v1',
        'problem_classifier_profile': 'avalanche_problem_rules_v1',
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
        'explainability_mode': explainability_mode,
        'tree_shap_status': 'ready' if explainability_mode == 'tree_shap' else explainability_mode,
        'tree_shap_reason': explainability_reason,
        'dominant_driver_strategy': (
            'top_absolute_tree_shap_v1'
            if explainability_mode == 'tree_shap'
            else 'tree_shap_withheld_fallback_v1'
        ),
        'training_dataset_version': bundle.get('training_dataset_version'),
        'forecast_mode': bundle.get('forecast_mode', 'full'),
        'seismic_events_active': len(seismic_events) > 0,
        'seismic_amplification_summary': {
            'events_checked': len(seismic_events),
            'active_windows': sum(
                1 for e in seismic_events
                for _ in check_active_windows(e, forecast_time.to_pydatetime())
            ) if seismic_events else 0,
        },
        'label_snapshot_id': (
            f"{bundle.get('training_dataset_version', 'unknown')}:{bundle.get('dataset_manifest', {}).get('newest_timestamp')}"
            if isinstance(bundle.get('dataset_manifest'), dict)
            else bundle.get('created_at')
        ),
        'sar_mask_asset_refs': sar_evidence.get('mask_asset_refs', []),
        'sar_event_geometries': sar_evidence.get('sar_event_geometries', []),
        'source_composition': {
            'weather_source': 'open_meteo_forecast_downscaled_v1',
            'ensemble_weather_source': 'open_meteo_ensemble_probabilistic_v1' if ensemble_profile else None,
            'sar_mask_asset_count': len(sar_evidence.get('mask_asset_refs', [])),
            'sar_event_geometry_count': len(sar_evidence.get('sar_event_geometries', [])),
            'snowpack_source': 'snowpack_proxy_v1',
            'snowpack_proxy_methods': snowpack_lineage['snowpack_proxy_methods'],
        },
        'data_lineage': snowpack_lineage['data_lineage'],
        'publish_eligible': snowpack_lineage['publish_eligible'],
        'snowpack_proxy_methods': snowpack_lineage['snowpack_proxy_methods'],
        'synthetic_inputs_present': snowpack_lineage['synthetic_inputs_present'],
        'synthetic_input_methods': snowpack_lineage['synthetic_input_methods'],
        'synthetic_cell_count': snowpack_lineage['synthetic_cell_count'],
        'inspected_snowpack_cell_count': snowpack_lineage['inspected_cell_count'],
        'source_health': source_health,
        'terrain_failure_reason_counts': terrain_failure_reason_counts,
        'decision_provenance': decision_provenance,
        'governance_scope': {
            'lineage_mode': 'internal_audit_governance_v1',
            'external_interoperability': 'not_implemented',
            'serving_semantics': 'operator_observability_separate_from_public_products',
        },
        'region_coverage': {
            'region_key': region.key,
            'bbox': list(region.bbox),
            'grid_size': int(grid_size or 1),
            'forecast_hours': int(horizon_hours),
            'timezone_name': str(getattr(region, 'timezone_name', 'UTC') or 'UTC'),
        },
        **execution_linkage,
        **proof_options.as_metadata(),
        'stale': ready_cell_count == 0,
        'ready_cell_count': ready_cell_count,
        'stale_cell_count': len(stale_cells),
        'unavailable_terrain_cell_count': len(unavailable_terrain_cells),
        'unavailable_weather_cell_count': len(unavailable_weather_cells),
        'terrain_failure_reason_counts': terrain_failure_reason_counts,
    }
    payload = {
        'hazard_type': 'avalanche',
        'region_key': region.key,
        'region_name': region.name,
        'forecast_date': forecast_date.date().isoformat(),
        'hindcast': bool(os.getenv('FORECAST_START_DATE')),
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
            'ensemble_available': bool(ensemble_profile),
            'ensemble_source': ensemble_profile.get('source') if ensemble_profile else None,
        },
        'ready_cell_count': ready_cell_count,
        'stale_cell_count': len(stale_cells),
        'unavailable_terrain_cell_count': len(unavailable_terrain_cells),
        'unavailable_weather_cell_count': len(unavailable_weather_cells),
        'terrain_failure_reason_counts': terrain_failure_reason_counts,
        'forecast_bulletins': forecast_bulletins,
        'model_metadata': model_metadata,
        'status': region_status,
    }
    # F13: Apply uncertainty quantification (Brier score + conformal intervals)
    # Load split conformal calibrator with manifest from env var
    import os as _os
    _cal_path = _os.getenv('CONFORMAL_CALIBRATION_ARTIFACT_PATH', '').strip()
    _persistence_calibrator: ConformalCalibrator | None = None
    _calibration_manifest = None
    if _cal_path:
        from backend.common.uncertainty_quantification import load_calibrator_with_manifest
        _persistence_calibrator, _calibration_manifest = load_calibrator_with_manifest(_cal_path)
    else:
        from backend.common.uncertainty_quantification import CalibrationManifest, CONFORMAL_ALPHA
        _calibration_manifest = CalibrationManifest(
            version='1.0.0', sha256='', sample_count=0,
            alpha=CONFORMAL_ALPHA, empirical_coverage=None,
            fit_coverage=None, held_out_coverage=None,
            uq_method='normal_fallback',
        )
    rows, uq_result = apply_uq_to_cells(rows, model_metadata, calibrator=_persistence_calibrator)
    model_metadata['brier_score'] = uq_result.brier_score
    model_metadata['forecast_confidence'] = uq_result.forecast_confidence
    model_metadata['uq_publish_blocked'] = uq_result.publish_blocked
    model_metadata['uq_block_reason'] = uq_result.block_reason
    model_metadata['conformal_calibrator_loaded'] = _persistence_calibrator is not None and _persistence_calibrator.is_calibrated
    model_metadata['calibration_manifest'] = _calibration_manifest.as_dict()
    model_metadata['uq_method'] = _calibration_manifest.uq_method
    payload['model_metadata'] = model_metadata
    payload['grid_geojson'] = rows

    # F10: Safe-Route Re-Computation — compute safest transit path across grid
    safe_route_metadata: dict[str, Any] = {
        'enabled': False,
        'routes': [],
        'error': None,
    }
    try:
        gs = int(len(rows) ** 0.5)
        if gs * gs == len(rows) and gs >= 2:
            start = (0, 0)
            end = (gs - 1, gs - 1)
            route = compute_safe_route(
                rows,
                grid_size=gs,
                start=start,
                end=end,
            )
            route_assessment = assess_route_safety(route)
            safe_route_metadata = {
                'enabled': True,
                'routes': [route_assessment],
                'route_count': 1,
                'route_status': route.status,
                'max_risk_on_route': route_assessment.get('max_risk'),
                'avg_risk_on_route': route_assessment.get('avg_risk'),
                'step_count': route_assessment.get('step_count'),
                'is_safe': route_assessment.get('is_safe'),
                'blocked_cells_count': route_assessment.get('blocked_cells_count'),
            }
    except Exception as route_exc:
        safe_route_metadata['error'] = str(route_exc)
    payload['safe_route'] = safe_route_metadata

    # F14: Multi-Hazard Assessment — assess landslide, flood, rockfall, debris_flow
    multi_hazard_metadata: dict[str, Any] = {
        'enabled': False,
        'hazard_types_assessed': [],
        'cells_assessed': 0,
        'error': None,
    }
    if MULTI_HAZARD_ENABLED:
        try:
            hazard_types = ['avalanche', 'landslide', 'flood', 'rockfall', 'debris_flow']
            cells_assessed = 0
            for cell in rows:
                weather = cell.get('weather_inputs') or {}
                terrain = cell.get('terrain_inputs') or {}
                seismic = cell.get('seismic_amplification') or {}
                slope_deg = float(terrain.get('slope_angle_deg', 0.0))
                precip_mm = float(weather.get('precipitation_24h_mm', 0.0))
                snowfall_cm = float(weather.get('snowfall_24h_cm', 0.0))
                temp_2m = float(weather.get('temperature_2m', 0.0) or 0.0)
                wind_loading = float(weather.get('wind_loading', 0.0))
                temp_gradient = float(weather.get('temp_gradient', 0.0))
                seismic_factor = float(seismic.get('factor', 0.0) if seismic else 0.0)
                snow_depth = float(weather.get('snow_depth_cm', 0.0))
                elevation_m = float(terrain.get('elevation_m', 0.0))

                hazard_factors: dict[str, dict[str, float]] = {
                    'avalanche': {
                        'snow_load': min(snowfall_cm / 100.0, 1.0),
                        'slope_angle': min(slope_deg / 45.0, 1.0),
                        'temperature_delta': min(abs(temp_gradient) / 20.0, 1.0),
                        'wind_transport': min(wind_loading, 1.0),
                        'seismic_amplification': min(seismic_factor, 1.0),
                    },
                    'landslide': {
                        'rainfall_24h': precip_mm,
                        'slope_angle': slope_deg,
                        'soil_saturation': min(precip_mm / 150.0, 1.0),
                        'lithology': 0.5,
                        'seismic_amplification': min(seismic_factor, 1.0),
                    },
                    'flood': {
                        'precipitation_72h': precip_mm * 3.0,
                        'snowmelt_rate': min(max(temp_2m, 0.0) / 10.0, 1.0),
                        'river_proximity': 0.0,
                        'glacial_lake_proximity': 0.0,
                        'upstream_area': 0.3,
                    },
                    'rockfall': {
                        'thermal_stress': min(abs(temp_2m) / 30.0, 1.0),
                        'slope_angle': min(slope_deg / 60.0, 1.0),
                        'seismic_amplification': min(seismic_factor, 1.0),
                        'freeze_thaw_cycles': min(abs(temp_gradient) / 15.0, 1.0),
                        'lithology': 0.5,
                    },
                    'debris_flow': {
                        'rainfall_intensity': precip_mm,
                        'rainfall_duration': 24.0,
                        'slope_angle': slope_deg,
                        'sediment_availability': 0.5,
                    },
                }

                mh_result = assess_multi_hazard(
                    cell_lat=float(cell.get('lat', 0.0)),
                    cell_lng=float(cell.get('lng', 0.0)),
                    hazard_factors=hazard_factors,
                    hazard_types=hazard_types,
                )
                cell['multi_hazard'] = {
                    'dominant_hazard': mh_result.dominant_hazard,
                    'composite_risk': mh_result.composite_risk,
                    'composite_risk_level': mh_result.composite_risk_level,
                    'any_trigger_met': mh_result.any_trigger_met,
                    'hazard_assessments': {
                        htype: {
                            'risk_score': a.risk_score,
                            'risk_level': a.risk_level,
                            'confidence': a.confidence,
                            'trigger_met': a.trigger_met,
                            'contributing_factors': a.contributing_factors,
                        }
                        for htype, a in mh_result.hazard_assessments.items()
                    },
                }
                cell['dominant_hazard'] = mh_result.dominant_hazard
                cell['composite_risk'] = mh_result.composite_risk
                cell['composite_risk_level'] = mh_result.composite_risk_level
                cells_assessed += 1

            multi_hazard_metadata = {
                'enabled': True,
                'hazard_types_assessed': hazard_types,
                'cells_assessed': cells_assessed,
                'error': None,
            }
            print(f'[daily_inference] F14: Multi-hazard assessment completed for {cells_assessed} cells', file=sys.stderr)
        except Exception as mh_exc:
            multi_hazard_metadata['error'] = str(mh_exc)
            print(f'[daily_inference] F14: Multi-hazard assessment failed: {mh_exc}', file=sys.stderr)
    payload['multi_hazard'] = multi_hazard_metadata

    if has_supabase_credentials() and not dry_run:
        if uq_result.publish_blocked:
            print(
                f'[daily_inference] Publication blocked by UQ gate: {uq_result.block_reason} '
                f'(brier={uq_result.brier_score or 0.0:.4f})',
                file=sys.stderr,
            )
            payload['status'] = 'uq_blocked'
            forecast_run_id = 'uq_blocked'
            payload['model_metadata'] = {
                **model_metadata,
                'forecast_run_id': forecast_run_id,
                'manifest_storage_ref': None,
                'runout_storage_ref': None,
            }
        elif bool(model_metadata.get('synthetic_inputs_present')) and not _is_truthy_env('ALLOW_SYNTHETIC_PUBLICATION'):
            methods = model_metadata.get('synthetic_input_methods') or []
            raise RuntimeError(
                'Synthetic inputs cannot be published to the active forecast path '
                f'without ALLOW_SYNTHETIC_PUBLICATION=true: {methods}'
            )
        else:
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
                forecast_bulletins=payload['forecast_bulletins'],
                model_metadata=model_metadata,
                hourly_grids=payload['hourly_grids'],
                runout_polygons=runout_polygons,
            )
            if stage_metrics is not None:
                stage_metrics['publication_seconds'] = round(perf_counter() - publication_started_at, 3)
            if publication is False:
                raise RuntimeError('forecast publication failed — forecast_run_hours insert error')
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
            'grid_geojson': [],
            'hourly_grids': [],
            'runout_polygons': [],
            'weather_summary': payload['weather_summary'],
            'model_metadata': {
                **payload['model_metadata'],
                'compatibility_payload_mode': 'artifact_refs_only_v1',
                'compatibility_payload_legacy_grid_geojson_bytes': 0,
                'compatibility_payload_legacy_hourly_grids_bytes': 0,
                'compatibility_payload_legacy_runout_bytes': 0,
            },
            'status': payload['status'],
            'issue_slot': cadence_context.issue_slot if cadence_context else '06',
            'cadence_hours': cadence_context.cadence_hours if cadence_context else 24,
            'valid_from': cadence_context.valid_from.isoformat() if cadence_context else None,
            'valid_to': cadence_context.valid_to.isoformat() if cadence_context else None,
            'source_as_of': cadence_context.source_as_of.isoformat() if cadence_context else None,
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
                    on_conflict='hazard_type,region_key,forecast_date,horizon_hours,issue_slot',
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
                        'issue_slot': f'eq.{cadence_context.issue_slot if cadence_context else "06"}',
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
        elif compatibility_row_id and explainability_mode != 'tree_shap':
            payload['model_metadata']['shap_cache_write_status'] = 'tree_shap_unavailable'
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
                shap_cache_write_status = _upsert_shap_cache(region, bundle, forecast_date, rows)
                payload['model_metadata']['shap_cache_write_status'] = shap_cache_write_status
                _record_publication_event_best_effort(
                    forecast_run_id=forecast_run_id,
                    stage='shap_cache_completed' if shap_cache_write_status == 'ok' else 'shap_cache_skipped',
                    status='ok' if shap_cache_write_status == 'ok' else 'skipped',
                    artifact_dir=artifact_dir,
                    modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
                    detail={
                        'compatibility_forecast_grid_id': compatibility_row_id,
                        'shap_cache_write_status': shap_cache_write_status,
                    },
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
        try:
            completeness_payload = build_feature_completeness_row(
                source_health=source_health,
                forecast_grid_id=compatibility_row_id,
                forecast_run_id=forecast_run_id,
            )
            rest_insert('feature_completeness_log', [completeness_payload], returning='minimal', timeout_seconds=120)
        except Exception:
            pass
        promotion_started_at = perf_counter()
        _record_publication_event_best_effort(
            forecast_run_id=forecast_run_id,
            stage='promote_started',
            status='started',
            artifact_dir=artifact_dir,
            modal_call_id=modal_call_id if isinstance(modal_call_id, str) else None,
        )
        try:
            if forecast_run_id == 'uq_blocked':
                print('[daily_inference] Skipping promote_forecast_run — publication blocked by UQ gate.', file=sys.stderr)
                promoted_row = None
            else:
                try:
                    promoted_row = promote_forecast_run(
                        forecast_run_id=forecast_run_id,
                        model_type=str(active_state.get('active_model_type') or 'surrogate_rf_v1'),
                        model_version=str(active_state.get('active_model_version') or 'unknown'),
                        publication_gates_passed=not uq_result.publish_blocked,
                    )
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
                    published_at = (
                        promoted_row.get('published_at')
                        if isinstance(promoted_row, dict)
                        else None
                    )
                    if published_at:
                        payload['published_at'] = published_at
                        payload['model_metadata'] = {
                            **payload['model_metadata'],
                            'published_at': published_at,
                            'publication_status': 'published',
                            'active': True,
                        }
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



def _upsert_shap_cache(region, bundle, forecast_date: pd.Timestamp, rows: list[dict[str, object]]) -> str:
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
        return 'rest_unavailable'
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
        return 'missing_compatibility_key'
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
        return 'empty'
    try:
        rest_upsert(
            'forecast_shap_cache',
            payload,
            on_conflict='forecast_grid_id,cell_row,cell_col,forecast_hour,model_version',
        )
    except Exception:
        # Cache is best-effort; failure must not break the inference run.
        return 'failed'
    return 'ok'
