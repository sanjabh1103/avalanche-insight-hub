from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from backend.common.avalanche_problem_classifier import classify_avalanche_problem
from backend.common.artifacts import dump_json, load_joblib, resolve_artifact_dir
from backend.common.audit_metadata import (
    build_decision_provenance,
    build_feature_completeness_row,
    build_latest_benchmark_summary,
    build_source_health_summary,
)
from backend.common.avalanche_prone_terrain import APT_PROFILE, apply_apt_unified_metric
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, build_region_grid
from backend.common.forecast_bulletins import build_daypart_forecast_bulletin, build_forecast_bulletin
from backend.common.forecast_publication import (
    attach_compatibility_forecast_grid,
    publish_forecast_run,
    promote_forecast_run,
)
from backend.common.public_eligibility import PUBLIC_ELIGIBILITY_PROFILE, SNOW_ELEVATION_PROFILE, apply_public_eligibility_metric
from backend.common.release_policy import evaluate_release_decision, ReleaseDecision, PublicationEvidence, evaluate_publication_evidence
from backend.common.model_status_state import (
    build_autonomous_evidence_summary,
    build_drift_mode_state,
    build_dynamic_model_candidate,
    resolve_active_candidate_artifact_dir,
    resolve_active_model_state,
)
from backend.common.real_features import (
    TerrainUnavailableError,
    build_real_feature_row,
    extract_cell_terrain,
    fetch_ensemble_weather_profile,
    fetch_forecast_weather_profile,
    fetch_historical_weather_window,
    select_hourly_weather_sample,
)
from backend.common.terrain_diagnostics import count_runtime_terrain_failure_reasons
from backend.common.regions import load_regions, repo_root
from backend.common.runout import RUN_PHYSICS_RUNOUT, build_runout_polygons
from backend.common.ravafcast_cell_input import (
    build_cell_inputs as _build_Partner_contracts,
    normalize_weather_sample as _normalize_Partner_weather,
    to_feature_weather_sample as _to_feature_weather_sample,
)
from backend.common.uncertainty_quantification import apply_uq_to_cells, ConformalCalibrator, load_calibrator_from_csv, load_calibrator_with_manifest, CalibrationManifest
from backend.common.continuous_learning import process_detections_for_learning, CONTINUOUS_LEARNING_ENABLED
from backend.common.risk_math import (
    DEFAULT_IPA_WEIGHTS,
    build_hazard_vector,
    build_impact_vector,
    chebyshev_ipa,
    compute_danger_level,
    compute_canonical_danger,
    DangerAggregationConfig,
    DANGER_AGGREGATION_PROFILE,
    impact_risk_level,
    impact_risk_score,
    legacy_max_risk_level,
    risk_level as ipa_risk_level,
)
from backend.common.snowpack_proxy import (
    SnowpackProxy,
    SnowpackProxyBatchResult,
    compute_region_snowpack_proxy,
    fetch_batched_cell_snowpack_proxies_partial,
    winter_season_start,
)
from backend.common.terrain_diagnostics import classify_terrain_failure
from backend.common.aws_station_adapter import fetch_aws_feed, validate_aws_feed_schema
from backend.common.Partner_snowpack_adapter import load_Partner_snowpack
from backend.common.ravafcast_runtime_gate import check_pipeline_status, emit_gate_metadata
from backend.common.snowpack_physics import (
    SNOWPACK_PHYSICS_ENABLED,
    SnowpackPhysicsResult,
    compute_cell_snowpack_physics,
    compute_grid_snowpack_physics,
    _heuristic_to_physics_result,
)
from backend.common.meteoio_openmeteo import snowpack_binary_available
from backend.common.supabase_io import (
    fetch_latest_model_status_row,
    has_supabase_credentials,
    patch_latest_model_status_row,
    rest_get,
    rest_insert,
    rest_upsert,
)
from backend.common.seismic_integrator import (
    HIMALAYAN_BBOX,
    SEISMIC_MIN_MAGNITUDE,
    SeismicAmplification,
    apply_seismic_amplification,
    check_active_windows,
    compute_seismic_amplification,
    fetch_recent_earthquakes,
)
from backend.common.dual_explainability import (
    build_physics_narrative,
    physics_narrative_to_dict,
)
from backend.common.cap_alert import (
    CAP_ENABLED,
    check_cap_publication_gates,
    generate_multi_language_cap,
    should_trigger_alert,
    validate_cap_xml,
)
from backend.common.sachet_push import (
    SACHET_ENABLED,
    SACHET_RSS_ENABLED,
    SachetConfig,
    build_multi_language_alerts,
    push_sachet_alert,
)
from backend.common.sachet_rss import (
    SachetRssConfig,
    get_sachet_alert_summary,
    ingest_sachet_alerts,
)
from backend.common.route_planner import (
    SafeRoute,
    assess_route_safety,
    compute_safe_route,
)
from backend.common.multi_hazard import (
    MULTI_HAZARD_ENABLED,
    assess_multi_hazard,
)
from backend.common.aavds_adapter import (
    AAVDS_ENABLED,
    AAVDSAdapter,
)
from backend.common.citizen_science import (
    CITIZEN_SCIENCE_ENABLED,
    CitizenReport,
)
from backend.common.sensor_ingestion import (
    SENSOR_ENABLED,
    fetch_sensor_events_rest,
)
from backend.common.sequence_features import build_inference_branches, extract_zone_onehot
from backend.lstm_model import predict_production_probability
from backend.models.surrogate_rf import (
    TreeShapUnavailableError,
    build_tree_shap_explainer,
    collect_tree_probabilities,
    compute_tree_shap,
    compute_tree_shap_batch,
)
from backend.common.verification_contracts import (
    VERIFICATION_SPINE_ENABLED,
    VerificationPacket,
    EvidencePacket,
    FusedSnowState,
    evaluate_publication_gate,
)
from backend.common.anomaly_detector import (
    SensorReading as AnomalySensorReading,
    detect_anomalies,
)
from backend.common.fusion_engine import (
    SensorObservation,
    fuse_observations,
)
from backend.common.snow_baselines import (
    build_cell_baselines,
    BaselineStats,
    WINDOW_30D,
)
from backend.common.gibs_ingestion import (
    GIBS_ENABLED,
    fetch_gibs_snow_cover_batch,
)
from backend.common.s1_snow_depth import (
    S1_DEPTH_ENABLED,
    estimate_s1_snow_depth,
)
from backend.common.snow_depth_fusion import (
    SNOW_DEPTH_FUSION_ENABLED,
    fuse_snow_depths,
)
from backend.common.active_learning import (
    ACTIVE_LEARNING_ENABLED,
    rank_cells_for_observation,
    emit_review_queue_rows,
)
from backend.common.vae_anomaly import (
    VAE_ANOMALY_ENABLED,
    detect_vae_anomaly,
)
from backend.common.observation_contract import (
    ObservationContract,
    QUALITY_PROVISIONAL,
    QUALITY_VERIFIED,
)
from backend.common.scientist_evidence_cases import (
    materialize_published_evidence_cases,
)


DEFAULT_DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'


def _materialize_published_evidence_cases_best_effort(
    *,
    forecast_run_id: str,
    region_key: str,
    region_name: str | None,
    forecast_date: str | None,
    rows: Sequence[Mapping[str, Any]],
    model_metadata: Mapping[str, Any] | None,
    forecast_grid_id: str | None = None,
) -> dict[str, Any]:
    """Best-effort wrapper that never interrupts publication."""
    if not forecast_run_id or forecast_run_id == 'uq_blocked':
        return {'status': 'not_published'}
    if os.getenv('SCIENTIST_EVIDENCE_CASES_ENABLED', 'false').lower() != 'true':
        return {'status': 'disabled'}
    try:
        return materialize_published_evidence_cases(
            forecast_run_id=forecast_run_id,
            region_key=region_key,
            region_name=region_name,
            forecast_date=forecast_date,
            forecast_grid_id=forecast_grid_id,
            rows=rows,
            model_metadata=model_metadata,
            enabled=True,
        )
    except Exception as exc:
        return {'status': 'failed', 'error_class': type(exc).__name__}


def _load_production_calibrator() -> tuple[ConformalCalibrator | None, CalibrationManifest]:
    """Load a ConformalCalibrator with manifest from env var CONFORMAL_CALIBRATION_ARTIFACT_PATH.

    G-07: Falls back to a default calibration artifact in backend/config/ if env var is not set.
    Returns (None, manifest_with_normal_fallback) if no path is set or loading fails.
    """
    from pathlib import Path as _Path
    _default_cal_path = str(_Path(__file__).resolve().parent / 'config' / 'default_conformal_calibration.csv')
    cal_path = os.getenv('CONFORMAL_CALIBRATION_ARTIFACT_PATH', '').strip() or _default_cal_path
    if not cal_path:
        print('[daily_inference] WARNING: CONFORMAL_CALIBRATION_ARTIFACT_PATH not set — using normal_fallback UQ. Prediction intervals are not distribution-free guaranteed.', file=sys.stderr)
        return None, CalibrationManifest(
            version='1.0.0',
            sha256='',
            sample_count=0,
            alpha=float(os.getenv('CONFORMAL_ALPHA', '0.1')),
            empirical_coverage=None,
            fit_coverage=None,
            held_out_coverage=None,
            uq_method='normal_fallback',
        )
    calibrator, manifest = load_calibrator_with_manifest(cal_path)
    if calibrator is not None and calibrator.is_calibrated:
        print(f'[daily_inference] Loaded conformal calibrator from {cal_path} (method={manifest.uq_method}, samples={manifest.sample_count})', file=sys.stderr)
    elif calibrator is not None:
        print(f'[daily_inference] Conformal calibrator from {cal_path} is not calibrated (empty residuals?)', file=sys.stderr)
    else:
        print(f'[daily_inference] Conformal calibrator load failed, using normal_fallback', file=sys.stderr)
    return calibrator, manifest


def _danger_aggregation_config() -> DangerAggregationConfig:
    """Build a DangerAggregationConfig from the DANGER_AGGREGATION_PROFILE env var."""
    return DangerAggregationConfig(profile=DANGER_AGGREGATION_PROFILE)


def _normalize_slope_to_score(slope_deg: float) -> float:
    """G-10: Normalize raw slope degrees to a 0-1 avalanche-prone score.

    Peaks at 38° (most avalanche-prone) and decreases for both gentler and steeper slopes.
    This avoids the saturation bug where raw degrees >1° get clamp01'd to 1.0 in
    compute_danger_level, making all slopes identical.

    - 0° → 0.0 (flat, no avalanche risk)
    - 38° → 1.0 (peak avalanche danger)
    - 45° → ~0.82 (still high but decreasing)
    - 60° → ~0.42 (steeper slopes shed snow)
    """
    slope = max(0.0, float(slope_deg))
    return max(0.0, 1.0 - abs(38.0 - slope) / 38.0)

warnings.filterwarnings(
    'ignore',
    message='`sklearn.utils.parallel.delayed` should be used.*',
    category=UserWarning,
    module='sklearn.utils.parallel',
)


@dataclass(frozen=True)
class ProofModeOptions:
    enabled: bool = False
    profile: str = 'standard'
    skip_tree_shap: bool = False
    approximate_tree_shap: bool = False
    skip_shap_cache: bool = False
    skip_runout_generation: bool = False
    skip_compatibility_write: bool = False
    emit_stage_metrics: bool = False

    def as_metadata(self) -> dict[str, object]:
        return {
            'lifeboat_mode': self.enabled,
            'lifeboat_profile': self.profile if self.enabled else None,
            'skip_tree_shap': self.skip_tree_shap,
            'approximate_tree_shap': self.approximate_tree_shap,
            'skip_shap_cache': self.skip_shap_cache,
            'skip_runout_generation': self.skip_runout_generation,
            'skip_compatibility_write': self.skip_compatibility_write,
            'emit_stage_metrics': self.emit_stage_metrics,
        }


def _coerce_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _freshness_hours(published_at: object, generated_at: datetime) -> float | None:
    published_dt = _coerce_iso_datetime(published_at)
    if published_dt is None:
        return None
    return round(max(0.0, (generated_at - published_dt.astimezone(timezone.utc)).total_seconds() / 3600), 3)


def _is_truthy_env(name: str) -> bool:
    return str(os.getenv(name) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _enforce_ravafcast_reference_write_policy(args: argparse.Namespace) -> dict[str, object]:
    """Keep six-hour RAvaFcast runs research-only unless explicitly approved.

    The six-hour cadence is a technical-reference lane.  It must not inherit
    the normal publication behaviour merely because Supabase credentials are
    present in the environment.  A future staging write requires both an
    explicit target and an explicit approval flag; production is never an
    allowed target for this lane.
    """
    try:
        cadence_hours = int(os.getenv('RAVAFCAST_CADENCE_HOURS', '24'))
    except ValueError:
        cadence_hours = 24
    target = str(os.getenv('RAVAFCAST_REFERENCE_TARGET', 'dry_run')).strip().lower()
    approved = _is_truthy_env('RAVAFCAST_REFERENCE_WRITE_APPROVED')
    write_allowed = cadence_hours == 6 and target == 'staging' and approved
    forced_dry_run = cadence_hours == 6 and not write_allowed
    if forced_dry_run:
        args.dry_run = True
    return {
        'cadence_hours': cadence_hours,
        'target': target,
        'write_approved': approved,
        'write_allowed': write_allowed,
        'forced_dry_run': forced_dry_run,
    }


def _snowpack_method_is_synthetic(method: object) -> bool:
    return str(method or '').strip().lower().startswith('synthetic_')


def _summarize_snowpack_lineage(cells: list[object]) -> dict[str, object]:
    methods: set[str] = set()
    synthetic_methods: set[str] = set()
    inspected_cell_count = 0
    synthetic_cell_count = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        inspected_cell_count += 1
        snowpack_proxy = cell.get('snowpack_proxy')
        if not isinstance(snowpack_proxy, dict):
            continue
        method = str(snowpack_proxy.get('method') or '').strip()
        if not method:
            continue
        methods.add(method)
        if _snowpack_method_is_synthetic(method):
            synthetic_methods.add(method)
            synthetic_cell_count += 1
    synthetic_inputs_present = bool(synthetic_methods)
    data_lineage = (
        'mixed'
        if synthetic_inputs_present and len(methods) > len(synthetic_methods)
        else 'synthetic_internal'
        if synthetic_inputs_present
        else 'observed_or_derived_real'
    )
    return {
        'data_lineage': data_lineage,
        'publish_eligible': not synthetic_inputs_present,
        'snowpack_proxy_methods': sorted(methods),
        'snowpack_physics_methods': sorted({
            str(cell.get('snowpack_physics_method') or '').strip()
            for cell in cells
            if isinstance(cell, dict) and cell.get('snowpack_physics_method')
        }),
        'synthetic_inputs_present': synthetic_inputs_present,
        'synthetic_input_methods': sorted(synthetic_methods),
        'synthetic_cell_count': synthetic_cell_count,
        'inspected_cell_count': inspected_cell_count,
    }


def _merge_lineage_with_metadata(*, cells: list[object], model_metadata: dict[str, object]) -> dict[str, object]:
    lineage = _summarize_snowpack_lineage(cells)
    proxy_methods = {
        str(method)
        for method in lineage.get('snowpack_proxy_methods', [])
        if isinstance(method, str) and method.strip()
    }
    metadata_methods = model_metadata.get('snowpack_proxy_methods')
    if isinstance(metadata_methods, list):
        for method in metadata_methods:
            if isinstance(method, str) and method.strip():
                proxy_methods.add(method.strip())
    synthetic_methods = {
        str(method)
        for method in lineage.get('synthetic_input_methods', [])
        if isinstance(method, str) and method.strip()
    }
    metadata_synthetic_methods = model_metadata.get('synthetic_input_methods')
    if isinstance(metadata_synthetic_methods, list):
        for method in metadata_synthetic_methods:
            if isinstance(method, str) and method.strip():
                synthetic_methods.add(method.strip())
    synthetic_methods = {method for method in synthetic_methods if _snowpack_method_is_synthetic(method)}
    synthetic_inputs_present = bool(model_metadata.get('synthetic_inputs_present')) or bool(synthetic_methods)
    lineage['snowpack_proxy_methods'] = sorted(proxy_methods)
    lineage['synthetic_inputs_present'] = synthetic_inputs_present
    lineage['synthetic_input_methods'] = sorted(set(synthetic_methods))
    if synthetic_inputs_present:
        lineage['data_lineage'] = 'mixed' if proxy_methods - synthetic_methods else 'synthetic_internal'
        lineage['publish_eligible'] = False
    return lineage


def build_publication_proof(
    *,
    outputs: list[dict[str, object]],
    generated_at: datetime,
    dry_run: bool,
    supabase_enabled: bool,
    expected_forecast_date: str,
    artifact_dir: Path,
    expected_grid_size: int | None = None,
    require_full_grid: bool = False,
) -> dict[str, object]:
    regions: list[dict[str, object]] = []
    for payload in outputs:
        model_metadata = payload.get('model_metadata') if isinstance(payload.get('model_metadata'), dict) else {}
        assert isinstance(model_metadata, dict)
        region_coverage = (
            model_metadata.get('region_coverage')
            if isinstance(model_metadata.get('region_coverage'), dict)
            else {}
        )
        forecast_run_id = model_metadata.get('forecast_run_id')
        manifest_storage_ref = model_metadata.get('manifest_storage_ref')
        published_at = payload.get('published_at') or model_metadata.get('published_at')
        forecast_date = payload.get('forecast_date')
        status = str(payload.get('status') or 'unavailable')
        publication_status = (
            'published'
            if forecast_run_id and manifest_storage_ref and supabase_enabled and not dry_run
            else 'dry_run'
            if dry_run
            else 'not_published'
        )
        freshness_hours = _freshness_hours(published_at, generated_at)
        same_day_published = (
            publication_status == 'published'
            and forecast_date == expected_forecast_date
            and status != 'stale'
            and freshness_hours is not None
            and freshness_hours <= 24
        )
        hourly_grids = payload.get('hourly_grids') if isinstance(payload.get('hourly_grids'), list) else []
        grid_cells = payload.get('grid_geojson') if isinstance(payload.get('grid_geojson'), list) else []
        lineage_cells = (
            grid_cells
            if grid_cells
            else hourly_grids[0]
            if hourly_grids and isinstance(hourly_grids[0], list)
            else []
        )
        lineage = _merge_lineage_with_metadata(cells=lineage_cells, model_metadata=model_metadata)
        grid_size = (
            expected_grid_size
            if isinstance(expected_grid_size, int) and expected_grid_size > 0
            else int(region_coverage.get('grid_size') or 0)
            if isinstance(region_coverage.get('grid_size'), (int, float))
            else None
        )
        expected_cell_count = grid_size * grid_size if isinstance(grid_size, int) and grid_size > 0 else None
        hourly_cell_counts = [
            len(cells) for cells in hourly_grids if isinstance(cells, list)
        ]
        hourly_ready_counts = [
            sum(1 for cell in cells if isinstance(cell, dict) and cell.get('status') == 'ready')
            for cells in hourly_grids
            if isinstance(cells, list)
        ]
        hourly_stale_counts = [
            len(cells) - ready_count
            for cells, ready_count in zip(
                [cells for cells in hourly_grids if isinstance(cells, list)],
                hourly_ready_counts,
            )
        ]
        forecast_bulletins = payload.get('forecast_bulletins')
        structured_bulletin = (
            isinstance(forecast_bulletins, dict)
            and forecast_bulletins.get('schema_version') == 'forecast-bulletin/v1'
            and isinstance(forecast_bulletins.get('dayparts'), list)
            and len(forecast_bulletins.get('dayparts') or []) > 0
            and isinstance(forecast_bulletins.get('danger_level'), (int, float))
        )
        first_hour_cell_count = len(grid_cells) or (hourly_cell_counts[0] if hourly_cell_counts else 0)
        min_hourly_cell_count = min(hourly_cell_counts) if hourly_cell_counts else 0
        min_hourly_ready_cell_count = min(hourly_ready_counts) if hourly_ready_counts else 0
        max_hourly_stale_cell_count = max(hourly_stale_counts) if hourly_stale_counts else 0
        full_grid_cells_present = (
            expected_cell_count is not None
            and first_hour_cell_count == expected_cell_count
            and len(hourly_cell_counts) == int(payload.get('horizon_hours') or len(hourly_cell_counts))
            and min_hourly_cell_count == expected_cell_count
        )
        full_grid_ready = (
            full_grid_cells_present
            and int(payload.get('stale_cell_count') or 0) == 0
            and max_hourly_stale_cell_count == 0
            and min_hourly_ready_cell_count == expected_cell_count
        )
        full_grid_publication_ready = bool(
            same_day_published
            and full_grid_ready
            and structured_bulletin
            and bool(lineage.get('publish_eligible'))
        )
        full_grid_compute_ready = bool(
            full_grid_ready
            and structured_bulletin
            and bool(lineage.get('publish_eligible'))
        )
        regions.append({
            'forecast_run_id': forecast_run_id,
            'forecast_date': forecast_date,
            'published_at': published_at,
            'region_key': payload.get('region_key'),
            'region_name': payload.get('region_name'),
            'status': status,
            'publication_status': publication_status,
            'active': publication_status == 'published',
            'same_day_published': same_day_published,
            'freshness_hours': freshness_hours,
            'hour_count': len(hourly_grids) or payload.get('horizon_hours'),
            'manifest_path': manifest_storage_ref,
            'grid_size': grid_size,
            'expected_cell_count': expected_cell_count,
            'first_hour_cell_count': first_hour_cell_count,
            'min_hourly_cell_count': min_hourly_cell_count,
            'min_hourly_ready_cell_count': min_hourly_ready_cell_count,
            'max_hourly_stale_cell_count': max_hourly_stale_cell_count,
            'full_grid_cells_present': full_grid_cells_present,
            'full_grid_ready': full_grid_ready,
            'full_grid_compute_ready': full_grid_compute_ready,
            'full_grid_publication_ready': full_grid_publication_ready,
            'data_lineage': lineage.get('data_lineage'),
            'publish_eligible': lineage.get('publish_eligible'),
            'snowpack_proxy_methods': lineage.get('snowpack_proxy_methods'),
            'snowpack_physics_methods': lineage.get('snowpack_physics_methods'),
            'synthetic_inputs_present': lineage.get('synthetic_inputs_present'),
            'synthetic_input_methods': lineage.get('synthetic_input_methods'),
            'synthetic_cell_count': lineage.get('synthetic_cell_count'),
            'inspected_cell_count': lineage.get('inspected_cell_count'),
            'ready_cell_count': int(payload.get('ready_cell_count') or 0),
            'stale_cell_count': int(payload.get('stale_cell_count') or 0),
            'bulletin_present': isinstance(forecast_bulletins, dict)
            and bool(forecast_bulletins),
            'structured_bulletin': structured_bulletin,
            'bulletin_schema_version': (
                forecast_bulletins.get('schema_version')
                if isinstance(forecast_bulletins, dict)
                else None
            ),
            'bulletin_daypart_count': (
                len(forecast_bulletins.get('dayparts') or [])
                if isinstance(forecast_bulletins, dict)
                and isinstance(forecast_bulletins.get('dayparts'), list)
                else 0
            ),
            'verification_summary': _build_verification_summary(lineage_cells),
        })

    same_day_published_count = sum(1 for region in regions if region.get('same_day_published'))
    full_grid_publication_ready_count = sum(
        1 for region in regions if region.get('full_grid_publication_ready')
    )
    full_grid_compute_ready_count = sum(
        1 for region in regions if region.get('full_grid_compute_ready')
    )
    failures = [
        str(region.get('region_key') or region.get('region_name') or 'unknown')
        for region in regions
        if not region.get('same_day_published')
        or (require_full_grid and not region.get('full_grid_publication_ready'))
    ]
    return {
        'schema_version': 'publication-proof/v1',
        'generated_at': generated_at.isoformat(),
        'expected_forecast_date': expected_forecast_date,
        'expected_grid_size': expected_grid_size,
        'require_full_grid': require_full_grid,
        'artifact_dir': str(artifact_dir),
        'dry_run': dry_run,
        'supabase_enabled': supabase_enabled,
        'region_count': len(regions),
        'same_day_published_count': same_day_published_count,
        'full_grid_compute_ready_count': full_grid_compute_ready_count,
        'full_grid_publication_ready_count': full_grid_publication_ready_count,
        'compute_proof_status': 'passed' if regions and full_grid_compute_ready_count == len(regions) else 'failed',
        'proof_status': 'passed' if not failures and regions else 'failed',
        'failures': failures,
        'regions': regions,
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


def _hourly_samples_to_dicts(samples: object) -> list[dict[str, Any]]:
    """Convert cached real-feature samples to physics input dictionaries."""
    if not isinstance(samples, list):
        return []
    converted: list[dict[str, Any]] = []
    for sample in samples:
        if isinstance(sample, dict):
            record = dict(sample)
        else:
            values = getattr(sample, 'values', None)
            if not isinstance(values, dict):
                continue
            record = dict(values)
            timestamp = getattr(sample, 'timestamp', None)
            if timestamp:
                record['time'] = str(timestamp)
        if record:
            converted.append(record)
    return converted


def _build_cached_physics_forcing(
    *,
    weather_profile: dict[str, Any],
    history_profile: dict[str, Any],
    terrain_by_coord: dict[tuple[float, float], dict[str, float]],
    forecast_time: datetime,
) -> dict[str, Any]:
    """Build deterministic callbacks over already-fetched forcing and terrain.

    The physics engine remains responsible for COSIPY/SNOWPACK selection. This
    helper only supplies cached inputs and makes an unavailable forcing path
    explicit instead of silently passing empty dictionaries.
    """
    history_samples = _hourly_samples_to_dicts(history_profile.get('samples'))
    forecast_sample = select_hourly_weather_sample(weather_profile, forecast_time)
    if not forecast_sample and history_samples:
        forecast_sample = dict(history_samples[-1])

    def _weather_history_fn(_lat: float, _lng: float) -> list[dict[str, Any]]:
        return list(history_samples)

    def _weather_inputs_fn(_lat: float, _lng: float) -> dict[str, float]:
        sample = forecast_sample or {}
        snowfall = sample.get('snowfall_24h_cm')
        if snowfall is None:
            snowfall = sample.get('snowfall_24h')
        if snowfall is None:
            snowfall = sample.get('snowfall', 0.0)
        wind_speed = sample.get('windspeed_10m', 0.0) or 0.0
        temp_gradient = sample.get('temp_gradient', 0.5)
        try:
            snowfall_value = max(0.0, float(snowfall or 0.0))
        except (TypeError, ValueError):
            snowfall_value = 0.0
        try:
            wind_loading = max(0.0, min(float(wind_speed) / 55.0, 1.0))
        except (TypeError, ValueError):
            wind_loading = 0.0
        try:
            gradient_value = max(0.0, min(float(temp_gradient), 1.0))
        except (TypeError, ValueError):
            gradient_value = 0.5
        return {
            'snowfall_24h': snowfall_value,
            'wind_loading': wind_loading,
            'temp_gradient': gradient_value,
        }

    def _terrain_inputs_fn(lat: float, lng: float) -> dict[str, float]:
        key = (round(float(lat), 4), round(float(lng), 4))
        terrain = terrain_by_coord.get(key)
        if terrain is None and terrain_by_coord:
            terrain = next(iter(terrain_by_coord.values()))
        terrain = terrain or {}
        try:
            elevation = max(0.0, min(float(terrain.get('elevation_m', 2500.0)) / 5000.0, 1.0))
        except (TypeError, ValueError):
            elevation = 0.5
        return {
            'elevation': elevation,
            'slope_angle_deg': float(terrain.get('slope_angle_deg', 0.0) or 0.0),
            'aspect_deg': float(terrain.get('aspect_deg', 0.0) or 0.0),
        }

    return {
        'weather_history_fn': _weather_history_fn,
        'weather_inputs_fn': _weather_inputs_fn,
        'terrain_inputs_fn': _terrain_inputs_fn,
        'status': 'cached_weather_history' if history_samples else 'cached_forecast_forcing',
        'history_sample_count': len(history_samples),
        'forecast_sample_available': bool(forecast_sample),
    }


def _native_snowpack_physics_available() -> bool:
    """Return whether grid physics can add value beyond the selected proxy.

    When neither the native SNOWPACK binary nor COSIPY is available, the
    protected physics module falls back to ``compute_cell_snowpack_proxy``.
    Calling that fallback for every grid cell re-fetches seasonal archive data
    after the inference path has already selected a cell or regional proxy.
    The caller can therefore reuse the selected proxy without changing the
    physics module or its fallback semantics.
    """
    if not SNOWPACK_PHYSICS_ENABLED:
        return False
    try:
        if snowpack_binary_available():
            return True
    except Exception:
        pass
    try:
        import cosipymodel  # type: ignore[import-not-found,unused-ignore]
        del cosipymodel
    except Exception:
        return False
    return True


def _reuse_selected_proxy_for_grid_physics() -> bool:
    """Choose proxy reuse unless a real physics backend is available.

    ``SNOWPACK_GRID_PHYSICS_MODE=physics`` is an explicit diagnostic override;
    ``proxy`` is useful for bounded local benchmarks.  The default ``auto``
    mode is safe for production because it only reuses the selected proxy when
    the physics implementation would itself fall back to that proxy.
    """
    mode = str(os.getenv('SNOWPACK_GRID_PHYSICS_MODE', 'auto') or 'auto').strip().lower()
    if mode == 'proxy':
        return True
    if mode == 'physics':
        return False
    return not _native_snowpack_physics_available()


def _force_single_threaded_predictor(model: object) -> None:
    """Disable nested estimator fan-out for one already-batched prediction.

    The loaded calibrated model can contain a ``FrozenEstimator`` wrapping a
    random forest whose persisted ``n_jobs`` is ``-1``.  The inference loop
    already supplies all cells for one hour as a single batch, so creating
    parallel workers for each hourly call adds process/thread lifecycle cost
    without changing the predictions.  This mutates only the in-memory
    scheduling parameters; model weights and calibration remain unchanged.
    """
    pending = [model]
    seen: set[int] = set()
    while pending:
        candidate = pending.pop()
        if candidate is None or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        try:
            if hasattr(candidate, 'n_jobs'):
                candidate.n_jobs = 1
        except Exception:
            pass
        for attribute in ('estimator', 'base_estimator', 'classifier'):
            try:
                child = getattr(candidate, attribute, None)
            except Exception:
                child = None
            if child is not None:
                pending.append(child)
        try:
            calibrated_classifiers = getattr(candidate, 'calibrated_classifiers_', ()) or ()
        except Exception:
            calibrated_classifiers = ()
        if isinstance(calibrated_classifiers, (list, tuple)):
            pending.extend(item for item in calibrated_classifiers if item is not None)


def _predict_calibrated_probabilities(calibrated_model: object, selected_frame: pd.DataFrame) -> np.ndarray:
    """Score one hourly grid without spawning a process pool per hour.

    The loaded Random Forest/calibrator may retain ``n_jobs=-1`` from training.
    On the hourly inference path that caused joblib to create and tear down a
    multiprocessing pool for every hour, even though each call already
    contains the complete cell batch.  A single in-process backend preserves
    model semantics while avoiding that repeated process lifecycle cost.
    """
    _force_single_threaded_predictor(calibrated_model)
    try:
        from joblib import parallel_backend
    except Exception:
        probabilities = calibrated_model.predict_proba(selected_frame)[:, 1]  # type: ignore[attr-defined]
    else:
        with parallel_backend('threading', n_jobs=1):
            probabilities = calibrated_model.predict_proba(selected_frame)[:, 1]  # type: ignore[attr-defined]
    return np.asarray(probabilities, dtype=float)


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
    summary: dict[str, object] = {
        'sar_coverage_state': str(features.get('sar_coverage_state') or 'unknown'),
        'ascending_scene_count': int(features.get('ascending_scene_count') or 0),
        'descending_scene_count': int(features.get('descending_scene_count') or 0),
        'sar_scene_time': features.get('sar_scene_time'),
        'sar_active': True,
        'scene_lineage_persisted': bool(features.get('scene_lineage_persisted', False)),
        'scene_lineage_count': int(features.get('scene_lineage_count') or 0),
    }
    # Enrich with snow-state fields persisted by gee_extractor
    if features.get('wet_snow_fraction') is not None:
        summary['wet_snow_fraction'] = float(features['wet_snow_fraction'])
    if features.get('loading_rate_24h') is not None:
        summary['loading_rate_24h'] = float(features['loading_rate_24h'])
    if features.get('vh_db') is not None:
        summary['vh_db'] = float(features['vh_db'])
    if features.get('vv_db') is not None:
        summary['vv_db'] = float(features['vv_db'])
    if isinstance(features.get('sar_scene_ids'), list):
        summary['sar_scene_ids'] = [str(scene_id) for scene_id in features['sar_scene_ids'] if scene_id]
    # Compute freshness from scene time
    sar_scene_time = features.get('sar_scene_time')
    if sar_scene_time:
        try:
            scene_dt = datetime.fromisoformat(str(sar_scene_time).replace('Z', '+00:00'))
            freshness = (datetime.now(timezone.utc) - scene_dt).total_seconds() / 3600.0
            summary['freshness_hours'] = round(freshness, 1)
        except (ValueError, TypeError):
            pass
    return summary


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
        row = fetch_latest_model_status_row()
    except Exception:
        return None
    return row


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
    terrain_failure_reason: str | None = None,
) -> dict[str, object]:
    proxy_payload = None
    if snowpack_proxy is not None:
        proxy_payload = {
            'estimated_shear_strength': getattr(snowpack_proxy, 'estimated_shear_strength', None),
            'snow_settlement_index': getattr(snowpack_proxy, 'snow_settlement_index', None),
            'season_start': getattr(snowpack_proxy, 'season_start', None),
            'method': getattr(snowpack_proxy, 'method', None),
        }
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


def terrain_adjusted_risk_level(
    calibrated_probability: float,
    slope_angle_deg: float,
    *,
    aspect_risk: float,
    snowpack_shear_strength: float,
    exposure: float,
    vulnerability: float = 0.0,
    weights: dict[str, float] | None = None,
) -> tuple[int, float, float, dict[str, float], str, float, int, float, int]:
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
    ipa_risk = ipa_risk_level(ipa_result.score)
    terrain_adjusted_risk = max(legacy_risk, ipa_risk)

    # Impact-risk layer (separate from hazard per EAWS/WMO)
    impact_vector = build_impact_vector(exposure=exposure, vulnerability=vulnerability)
    impact_score = impact_risk_score(impact_vector)
    impact_level = impact_risk_level(impact_score)

    return (
        terrain_adjusted_risk,
        float(slope_risk),
        legacy_distance,
        vector,
        ipa_result.dominant_criterion,
        ipa_result.score,
        ipa_risk,
        impact_score,
        impact_level,
    )


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
    cadence_context: Any | None = None,
) -> dict[str, object]:
    proof_options = proof_options or ProofModeOptions()
    snowpack_proxy_mode = str(snowpack_proxy_mode or 'cell').strip().lower()
    if snowpack_proxy_mode not in {'cell', 'regional', 'synthetic'}:
        raise ValueError(f'Unsupported snowpack_proxy_mode: {snowpack_proxy_mode}')
    context_started_at = perf_counter()
    _grid_mode = os.getenv('RAVAFCAST_GRID_MODE', 'degree').lower()
    if _grid_mode == 'projected':
        from backend.common.features import build_region_grid_projected as _build_projected
        region_grid = _build_projected(region, cell_size_m=500.0, strict=True)
    else:
        region_grid = build_region_grid(region, grid_size=grid_size)
    _per_cell_weather_mode = os.getenv(
        'RAVAFCAST_PER_CELL_WEATHER_MODE',
        os.getenv('RAVAFCAST_PER_CELL_WEATHER', 'off')
    ).lower()
    if _per_cell_weather_mode not in ('off', 'reference', 'validation'):
        _per_cell_weather_mode = 'off'

    # The validation lane must never use a region-centre forecast as a silent
    # substitute for missing per-cell data. It can still use the centre profile
    # in the off/reference lanes for the legacy fallback ladder.
    weather_profile: dict[str, Any] = {'samples': []}
    if _per_cell_weather_mode != 'validation':
        weather_profile = fetch_forecast_weather_profile(
            region.center, forecast_date.to_pydatetime(), 72
        )

    # Per-cell weather retrieval — additive seam, disabled by default.
    # When enabled, profiles must align one-to-one with the selected grid.
    _cell_weather_map: dict[str, dict] | None = None
    _per_cell_weather_enabled = _per_cell_weather_mode != 'off'
    if _per_cell_weather_enabled:
        try:
            from backend.common.real_features import fetch_batch_weather_profile as _fetch_batch
            _cell_coords = [(c['lat'], c['lng']) for c in region_grid]
            _grid_pixel_ids = [str(c.get('pixel_id') or f'{region.key}_{idx}') for idx, c in enumerate(region_grid)]
            if len(set(_grid_pixel_ids)) != len(_grid_pixel_ids):
                raise ValueError('grid contains duplicate pixel_id values')
            _batch_profiles = _fetch_batch(_cell_coords, forecast_date.to_pydatetime(), 72)
            if len(_batch_profiles) != len(region_grid):
                raise ValueError(
                    f'per-cell weather count mismatch: expected {len(region_grid)}, '
                    f'received {len(_batch_profiles)}'
                )
            _cell_weather_map = {}
            _cell_weather_map['_mode'] = _per_cell_weather_mode
            for idx, profile in enumerate(_batch_profiles):
                if not isinstance(profile, dict) or not isinstance(profile.get('samples'), list):
                    raise ValueError(f'per-cell weather profile {idx} is missing samples')
                expected_lat, expected_lng = _cell_coords[idx]
                profile_lat = profile.get('latitude')
                profile_lng = profile.get('longitude')
                if profile_lat is None or profile_lng is None:
                    raise ValueError(f'per-cell weather profile {idx} is missing coordinate identity')
                if abs(float(profile_lat) - float(expected_lat)) > 1e-4 or abs(float(profile_lng) - float(expected_lng)) > 1e-4:
                    raise ValueError(
                        f'per-cell weather profile {idx} coordinate mismatch: '
                        f'expected ({expected_lat}, {expected_lng}), received ({profile_lat}, {profile_lng})'
                    )
                if not profile['samples']:
                    raise ValueError(f'per-cell weather profile {idx} has no hourly samples')
                _sample_times: list[pd.Timestamp] = []
                for _sample in profile['samples']:
                    _raw_time = getattr(_sample, 'timestamp', None)
                    if _raw_time is None and isinstance(_sample, dict):
                        _raw_time = _sample.get('time') or _sample.get('timestamp')
                    try:
                        _parsed_time = pd.Timestamp(_raw_time)
                        if _parsed_time.tzinfo is None:
                            _parsed_time = _parsed_time.tz_localize('UTC')
                        else:
                            _parsed_time = _parsed_time.tz_convert('UTC')
                        _sample_times.append(_parsed_time)
                    except Exception:
                        continue
                if not _sample_times:
                    raise ValueError(f'per-cell weather profile {idx} has no parseable sample timestamps')
                _start = pd.Timestamp(forecast_date)
                if _start.tzinfo is None:
                    _start = _start.tz_localize('UTC')
                else:
                    _start = _start.tz_convert('UTC')
                _end = _start + pd.Timedelta(hours=72)
                if not any((_start - pd.Timedelta(hours=6)) <= t <= _end for t in _sample_times):
                    raise ValueError(f'per-cell weather profile {idx} is stale for forecast window')
                _pid = _grid_pixel_ids[idx]
                _cell_weather_map[_pid] = profile
            if stage_metrics is not None:
                stage_metrics['per_cell_weather'] = {
                    'enabled': True,
                    'mode': _per_cell_weather_mode,
                    'cell_count': len(region_grid),
                    'profile_count': len(_cell_weather_map) - 1,
                    'source': 'open-meteo-batch',
                    'pixel_ids_unique': len(set(_grid_pixel_ids)) == len(_grid_pixel_ids),
                    'freshness_checked': True,
                }
        except Exception as exc:
            if _per_cell_weather_mode == 'validation':
                raise RuntimeError(
                    f'per-cell weather validation failed for {region.key}: {exc}'
                ) from exc
            if stage_metrics is not None:
                stage_metrics['per_cell_weather'] = {
                    'enabled': True,
                    'error': str(exc),
                    'fallback': 'region-center',
                }
            _cell_weather_map = None
    elif stage_metrics is not None:
        stage_metrics['per_cell_weather'] = {'enabled': False}
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
            'physics_forcing_status': 'pending',
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

    terrain_by_coord = {
        (round(float(item['center_lat']), 4), round(float(item['center_lng']), 4)): item['terrain']
        for item in prepared_cells
        if item.get('availability_reason') is None and isinstance(item.get('terrain'), dict)
    }

    # F5: Batch physics computation for grids with > 10 valid cells.  If no
    # native physics backend is available, reusing the already-selected proxy
    # avoids a second seasonal archive fetch per cell.
    reuse_selected_proxy = _reuse_selected_proxy_for_grid_physics()
    if len(valid_cells_for_physics) > 10 and reuse_selected_proxy:
        physics_started_at = perf_counter()
        for cell_entry in valid_cells_for_physics:
            cell_idx = int(cell_entry['cell_id'].split('_')[1])
            proxy = prepared_cells[cell_idx].get('snowpack_proxy')
            if proxy:
                prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
            prepared_cells[cell_idx]['physics_forcing_status'] = 'selected_proxy_no_duplicate_archive_fetch'
        if stage_metrics is not None:
            stage_metrics['snowpack_physics_batch_seconds'] = round(perf_counter() - physics_started_at, 3)
            stage_metrics['snowpack_physics_mode'] = 'selected_proxy_reuse'
            stage_metrics['snowpack_physics_forcing_status'] = 'selected_proxy_no_duplicate_archive_fetch'
            stage_metrics['snowpack_physics_history_sample_count'] = len(history_profile.get('samples') or [])
    elif len(valid_cells_for_physics) > 10:
        physics_started_at = perf_counter()
        forcing = _build_cached_physics_forcing(
            weather_profile=weather_profile,
            history_profile=history_profile,
            terrain_by_coord=terrain_by_coord,
            forecast_time=forecast_date.to_pydatetime(),
        )
        try:
            physics_results = compute_grid_snowpack_physics(
                grid_cells=valid_cells_for_physics,
                as_of=forecast_date.to_pydatetime(),
                weather_history_fn=forcing['weather_history_fn'],
                weather_inputs_fn=forcing['weather_inputs_fn'],
                terrain_inputs_fn=forcing['terrain_inputs_fn'],
                cache_dir=str(artifact_dir / 'physics_cache') if artifact_dir is not None else None,
            )
            for cell_entry in valid_cells_for_physics:
                cell_id = cell_entry['cell_id']
                cell_idx = int(cell_id.split('_')[1])
                result = physics_results.get(cell_id)
                if result is not None:
                    prepared_cells[cell_idx]['snowpack_physics'] = result
                    method = str(getattr(result, 'method', '') or '').lower()
                    if 'synthetic' in method:
                        forcing_status = 'synthetic_fallback_physics_result'
                    elif 'heuristic' in method:
                        forcing_status = 'heuristic_fallback_cached_forcing'
                    else:
                        forcing_status = str(forcing['status'])
                    prepared_cells[cell_idx]['physics_forcing_status'] = forcing_status
                else:
                    proxy = prepared_cells[cell_idx].get('snowpack_proxy')
                    if proxy:
                        prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
                        prepared_cells[cell_idx]['physics_forcing_status'] = 'heuristic_fallback_missing_result'
            if stage_metrics is not None:
                stage_metrics['snowpack_physics_batch_seconds'] = round(perf_counter() - physics_started_at, 3)
                stage_metrics['snowpack_physics_mode'] = 'grid_batch'
                statuses = {
                    str(prepared_cells[int(cell_entry['cell_id'].split('_')[1])].get('physics_forcing_status'))
                    for cell_entry in valid_cells_for_physics
                }
                stage_metrics['snowpack_physics_forcing_status'] = (
                    next(iter(statuses)) if len(statuses) == 1 else 'mixed'
                )
                stage_metrics['snowpack_physics_history_sample_count'] = forcing['history_sample_count']
        except Exception:
            # Fallback to heuristic for all valid cells
            for cell_entry in valid_cells_for_physics:
                cell_idx = int(cell_entry['cell_id'].split('_')[1])
                proxy = prepared_cells[cell_idx].get('snowpack_proxy')
                if proxy:
                    prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
                prepared_cells[cell_idx]['physics_forcing_status'] = 'heuristic_fallback_batch_error'
            if stage_metrics is not None:
                stage_metrics['snowpack_physics_mode'] = 'heuristic_fallback_batch_error'
                stage_metrics['snowpack_physics_forcing_status'] = 'heuristic_fallback_batch_error'
    else:
        # Small grid: use per-cell heuristic
        for cell_entry in valid_cells_for_physics:
            cell_idx = int(cell_entry['cell_id'].split('_')[1])
            proxy = prepared_cells[cell_idx].get('snowpack_proxy')
            if proxy:
                prepared_cells[cell_idx]['snowpack_physics'] = _heuristic_to_physics_result(proxy)
            prepared_cells[cell_idx]['physics_forcing_status'] = 'heuristic_per_cell_no_batch'
        if stage_metrics is not None:
            stage_metrics['snowpack_physics_mode'] = 'heuristic_per_cell'
            stage_metrics['snowpack_physics_forcing_status'] = 'heuristic_per_cell_no_batch'
    if stage_metrics is not None:
        stage_metrics['region_context_prep_seconds'] = round(perf_counter() - context_started_at, 3)

    explainability_context: dict[str, object] = {
        'mode': 'tree_shap_approximate' if proof_options.approximate_tree_shap else 'tree_shap',
        'reason': (
            'approximate_tree_shap_runtime_mode'
            if proof_options.approximate_tree_shap
            else None
        ),
        'detail': (
            'SHAP approximate traversal requested for bounded runtime.'
            if proof_options.approximate_tree_shap
            else None
        ),
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
        'cell_weather_map': _cell_weather_map,
        'cadence_context': cadence_context,
        'stage_metrics': stage_metrics,
    }


def _assimilate_partner_observations(
    weather_sample: dict[str, object],
    center_lat: float,
    center_lng: float,
    normalized_obs: list[Any],
    *,
    forecast_time: pd.Timestamp | None = None,
    station_registry: set[str] | None = None,
    max_spatial_radius_deg: float = 0.5,
    max_temporal_delta_hours: float = 6.0,
    max_elevation_diff_m: float = 500.0,
    center_elevation_m: float | None = None,
    require_reviewed: bool = False,
) -> tuple[dict[str, object], list[dict[str, Any]]]:
    """Match partner observations to a cell by proximity and override approved weather inputs.

    Only replaces existing weather_sample keys — does NOT add new model columns.
    Returns (assimilated_weather_sample, matched_entries) with original/substituted value
    pairs and observation hash for lineage.

    Gates:
    - Station registry: if provided, only observations from registered stations are accepted.
    - QC status: observations with qc_status='fail' are rejected.
    - Review status: if require_reviewed=True, observations with review_status != 'reviewed' are rejected.
    - Spatial: observations beyond max_spatial_radius_deg are rejected.
    - Temporal: if forecast_time is provided, observations older than max_temporal_delta_hours are rejected.
    - Elevation: if center_elevation_m and obs.elevation_m are both set, reject if difference exceeds max_elevation_diff_m.
    """
    assimilated = dict(weather_sample)
    matched: list[dict[str, Any]] = []
    for obs in normalized_obs:
        if obs.latitude is None or obs.longitude is None:
            continue
        # Station registry gate
        if station_registry is not None and obs.station_id not in station_registry:
            continue
        # QC gate
        if getattr(obs, 'qc_status', 'unchecked') == 'fail':
            continue
        # Review status gate
        if require_reviewed and getattr(obs, 'review_status', 'unreviewed') != 'reviewed':
            continue
        dist = ((center_lat - obs.latitude) ** 2 + (center_lng - obs.longitude) ** 2) ** 0.5
        if dist >= max_spatial_radius_deg:
            continue
        # Temporal gate
        if forecast_time is not None and getattr(obs, 'observed_at', ''):
            try:
                obs_time = pd.Timestamp(obs.observed_at)
                if abs((forecast_time - obs_time).total_seconds()) > max_temporal_delta_hours * 3600:
                    continue
            except Exception:
                continue
        # Elevation gate
        if center_elevation_m is not None and obs.elevation_m is not None:
            if abs(center_elevation_m - obs.elevation_m) > max_elevation_diff_m:
                continue
        substitutions: list[dict[str, Any]] = []
        for key, obs_val in obs.values.items():
            mapped_key = None
            if key == 'air_temp_c':
                mapped_key = 'downscaled_temperature_c'
            elif key == 'snowfall_cm':
                mapped_key = 'snowfall_24h_cm'
            elif key == 'wind_speed_ms':
                mapped_key = 'windspeed_10m'
            elif key == 'precipitation_mm':
                mapped_key = 'precipitation_24h_mm'
            elif key == 'snow_depth_cm':
                mapped_key = 'snow_depth_cm'
            if mapped_key is None:
                continue
            original = assimilated.get(mapped_key)
            if original is not None and original != obs_val:
                substitutions.append({
                    'field': mapped_key,
                    'original': original,
                    'substituted': obs_val,
                    'source_hash': obs.source_hash,
                    'station_id': obs.station_id,
                })
                assimilated[mapped_key] = obs_val
            elif original is None:
                assimilated[mapped_key] = obs_val
                substitutions.append({
                    'field': mapped_key,
                    'original': None,
                    'substituted': obs_val,
                    'source_hash': obs.source_hash,
                    'station_id': obs.station_id,
                })
        if substitutions:
            matched.append({
                'station_id': obs.station_id,
                'station_identity': obs.station_identity,
                'source_hash': obs.source_hash,
                'distance_deg': round(dist, 4),
                'substitutions': substitutions,
            })
    return assimilated, matched


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
    partner_observations: list[Any] | None = None,
) -> list[dict[str, object]]:
    proof_options = proof_options or ProofModeOptions()
    seismic_events = seismic_events or []
    _partner_obs = partner_observations or []
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
        _cell_weather_map = region_context.get('cell_weather_map')
        _pixel_id = prepared.get('pixel_id') or cell.get('pixel_id')
        if _cell_weather_map and _pixel_id and _pixel_id in _cell_weather_map:
            _cell_profile = _cell_weather_map[_pixel_id]
            _cell_weather = select_hourly_weather_sample(_cell_profile, forecast_time.to_pydatetime())
        elif _cell_weather_map and _cell_weather_map.get('_mode') == 'validation':
            raise RuntimeError(
                f"Per-cell weather validation mode: pixel_id '{_pixel_id}' "
                f"missing from cell_weather_map (cell_count mismatch)"
            )
        else:
            _cell_weather = weather_sample or {}
        _partner_matched: list[dict[str, Any]] = []
        if _partner_obs:
            from backend.common.partner_assimilation_config import (
                load_station_registry,
                load_station_registry_with_metadata,
                get_max_temporal_delta_hours,
                get_max_elevation_diff_m,
                get_max_spatial_radius_deg,
                get_require_reviewed,
            )
            from backend.common.partner_observation import validate_observation_against_registry
            try:
                _registry = load_station_registry()
            except Exception as _reg_err:
                print(f'[daily_inference] Station registry load failed: {_reg_err}', file=sys.stderr)
                _registry = None
            # G-06: Load full metadata registry for coordinate/elevation/unit validation
            try:
                _registry_meta = load_station_registry_with_metadata()
            except Exception as _meta_err:
                print(f'[daily_inference] Station metadata registry load failed: {_meta_err}', file=sys.stderr)
                _registry_meta = None
            # G-06: If observations are present but no registry, reject and record reason
            if _partner_obs and _registry_meta is None:
                print('[daily_inference] Partner observations present but no station metadata registry configured — observations will be rejected', file=sys.stderr)
            # G-06: Validate each observation against full metadata registry
            _validated_obs: list[Any] = []
            for _obs in _partner_obs:
                if _registry_meta is not None:
                    _errors = validate_observation_against_registry(_obs, _registry_meta)
                    if _errors:
                        print(f'[daily_inference] Observation from {_obs.station_id if hasattr(_obs, "station_id") else "unknown"} rejected: {_errors}', file=sys.stderr)
                    else:
                        _validated_obs.append(_obs)
                else:
                    print(f'[daily_inference] Observation from {_obs.station_id if hasattr(_obs, "station_id") else "unknown"} rejected: no station metadata registry configured', file=sys.stderr)
            _partner_obs = _validated_obs
            _cell_weather, _partner_matched = _assimilate_partner_observations(
                _cell_weather, center_lat, center_lng, _partner_obs,
                forecast_time=forecast_time,
                station_registry=_registry,
                max_spatial_radius_deg=get_max_spatial_radius_deg(),
                max_temporal_delta_hours=get_max_temporal_delta_hours(),
                max_elevation_diff_m=get_max_elevation_diff_m(),
                require_reviewed=get_require_reviewed(),
            )
        # The Partner cell contract is the input boundary, not a post-scoring
        # annotation. Normalize the selected source sample and validate it
        # before the real feature row reaches the model.
        _weather_mode = _cell_weather_map.get('_mode') if _cell_weather_map else 'off'
        _Partner_input_contract = None
        _feature_weather = _cell_weather
        if _weather_mode in ('reference', 'validation'):
            _cadence_ctx = region_context.get('cadence_context')
            _issue_slot = _cadence_ctx.issue_slot if _cadence_ctx else '06'
            _timestamp_value = forecast_time
            if _timestamp_value.tzinfo is None:
                _timestamp_value = _timestamp_value.tz_localize('UTC')
            else:
                _timestamp_value = _timestamp_value.tz_convert('UTC')
            _timestamp = _timestamp_value.isoformat()
            _fallback_timestamp = (
                _cadence_ctx.source_as_of.isoformat()
                if _cadence_ctx is not None and _cadence_ctx.source_as_of is not None
                else _timestamp
            )
            _normalized_weather = _normalize_Partner_weather(
                _cell_weather if isinstance(_cell_weather, dict) else {},
                fallback_timestamp=_fallback_timestamp,
                source_id='open-meteo-batch',
            )
            if _weather_mode == 'validation' and _normalized_weather.get('missingness') != 'complete':
                raise RuntimeError(
                    f"Per-cell weather validation failed for pixel_id '{_pixel_id}': "
                    f"missing {', '.join(_normalized_weather.get('missing_fields', []))}"
                )
            # The validated canonical sample is the model input boundary. The
            # feature builder still consumes its historical Open-Meteo key
            # names, so adapt only after validation while retaining lineage.
            _feature_weather = _to_feature_weather_sample(
                _normalized_weather,
                original=_cell_weather if isinstance(_cell_weather, dict) else None,
            )
            _contract_cell = {
                **cell,
                'elevation_m': float(terrain.get('elevation_m', 0.0)),
                'slope_deg': float(terrain.get('slope_angle_deg', 0.0)),
                'aspect_deg': float(terrain.get('aspect_deg', 0.0)),
            }
            _Partner_input_contract = _build_Partner_contracts(
                [_contract_cell],
                [_normalized_weather],
                issue_slot=_issue_slot,
                timestamp=_timestamp,
                region_key=str(region_context.get('region_key', 'unknown')),
                window_start=(
                    _cadence_ctx.valid_from.isoformat()
                    if _cadence_ctx is not None else ''
                ),
                window_end=(
                    _cadence_ctx.valid_to.isoformat()
                    if _cadence_ctx is not None else ''
                ),
            )[0]
            # The contract is always structurally validated before scoring.
            # Reference mode may retain ``missingness=partial`` and fallback
            # provenance, while validation mode has already rejected those
            # conditions above.
            _Partner_input_contract.validate()
        assembled = build_real_feature_row(
            weather_sample=_feature_weather,
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
            'physics_forcing_status': prepared.get('physics_forcing_status'),
            'terrain': terrain,
            'assembled': assembled,
            'feature_row': feature_row,
            'partner_matched': _partner_matched,
            'Partner_input_contract': _Partner_input_contract,
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
    rf_probabilities = _predict_calibrated_probabilities(calibrated_model, selected_frame_all)
    tree_shap_packets: list[tuple[dict[str, float], list[dict[str, float | str | int]]]] = []
    if not proof_options.skip_tree_shap and explainer is not None:
        _tree_shap_started_at = perf_counter()
        try:
            tree_shap_packets = compute_tree_shap_batch(
                explainer,
                selected_frame_all,
                selected_features,
                approximate=proof_options.approximate_tree_shap,
            )
        except Exception:
            # Preserve the existing single-row TreeSHAP fallback for mocked
            # explainers and runtimes where batch SHAP fails unexpectedly.
            tree_shap_packets = []
        finally:
            _stage_metrics = region_context.get('stage_metrics')
            if isinstance(_stage_metrics, dict):
                _stage_metrics['tree_shap_seconds_total'] = round(
                    float(_stage_metrics.get('tree_shap_seconds_total') or 0.0)
                    + perf_counter() - _tree_shap_started_at,
                    3,
                )
                _stage_metrics['tree_shap_mode'] = (
                    'approximate' if proof_options.approximate_tree_shap else 'exact'
                )
                _stage_metrics['tree_shap_batch_count'] = int(
                    _stage_metrics.get('tree_shap_batch_count') or 0
                ) + 1

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
                shap_values, shap_context = compute_tree_shap(
                    explainer,
                    selected_frame,
                    selected_features,
                    approximate=proof_options.approximate_tree_shap,
                )
            dominant_driver = shap_context[0]['feature'] if shap_context else None
            explainability_mode = str(explainability_context.get('mode') or 'tree_shap')
            explainability_reason = (
                str(explainability_context.get('reason'))
                if explainability_context.get('reason') is not None
                else None
            )
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
            'danger_level_configurable': compute_danger_level(
                _danger_aggregation_config(),
                score=calibrated_probability,
                hazard=calibrated_probability,
                exposure=exposure,
                impact=impact_score,
            ),
            'danger_level': compute_canonical_danger(
                _danger_aggregation_config(),
                score=calibrated_probability,
                hazard=calibrated_probability,
                exposure=exposure,
                impact=impact_score,
            ).as_dict(),
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
            'snowpack_proxy': {
                'estimated_shear_strength': assembled['snowpack_proxy'].estimated_shear_strength,
                'snow_settlement_index': assembled['snowpack_proxy'].snow_settlement_index,
                'season_start': assembled['snowpack_proxy'].season_start,
                'method': assembled['snowpack_proxy'].method,
            },
            'snowpack_physics_method': raw_inputs.get('snowpack_physics_method', 'unavailable'),
            'physics_forcing_status': ready_item.get('physics_forcing_status'),
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
            'partner_observations': ready_item.get('partner_matched', []),
            'Partner_input_contract': (
                ready_item['Partner_input_contract'].as_dict()
                if ready_item.get('Partner_input_contract') is not None else None
            ),
            'input_contract_status': (
                'validated'
                if _weather_mode == 'validation'
                else 'reference'
                if _weather_mode == 'reference'
                else 'off'
            ),
        }))

    result_rows = [row for row in row_slots if row is not None]

    # The contracts were built and (in validation mode) validated before model
    # scoring above. Retain only a run-level summary here; never reconstruct
    # contracts from scored output rows.
    _cell_weather_map = region_context.get('cell_weather_map')
    _weather_mode = _cell_weather_map.get('_mode') if _cell_weather_map else 'off'
    if _weather_mode in ('reference', 'validation') and result_rows:
        _stage_metrics = region_context.get('stage_metrics')
        _contract_rows = [
            row for row in result_rows
            if isinstance(row, dict) and isinstance(row.get('Partner_input_contract'), dict)
        ]
        if isinstance(_stage_metrics, dict):
            _stage_metrics['Partner_contracts'] = {
                'count': len(_contract_rows),
                'mode': _weather_mode,
                'validated': _weather_mode == 'validation',
                'pre_inference': True,
            }

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


def _build_verification_summary(cells: list) -> dict[str, Any]:
    """Aggregate verification packets from cells into a run-level summary.

    Behind VERIFICATION_SPINE_ENABLED flag (packets only exist when flag is on).
    """
    if not VERIFICATION_SPINE_ENABLED:
        return {}

    anomaly_counts: dict[str, int] = {}
    total_packets = 0
    total_anomalies = 0
    total_watch = 0
    attribution_counts: dict[str, int] = {}

    for cell in cells:
        if not isinstance(cell, dict):
            continue
        pkt = cell.get('verification_packet')
        if not isinstance(pkt, dict):
            continue
        total_packets += 1
        state = pkt.get('anomaly_state', 'unverified')
        if state == 'anomaly':
            total_anomalies += 1
        elif state == 'watch':
            total_watch += 1
        bucket = pkt.get('attribution_bucket', 'unattributed')
        attribution_counts[bucket] = attribution_counts.get(bucket, 0) + 1
        for reason in pkt.get('disagreement_reasons', []):
            anomaly_counts[reason] = anomaly_counts.get(reason, 0) + 1

    return {
        'total_packets': total_packets,
        'anomaly_count': total_anomalies,
        'watch_count': total_watch,
        'discrepancy_type_counts': anomaly_counts,
        'attribution_bucket_counts': attribution_counts,
    }


def _evaluate_verification_cap_gate(cells: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """Evaluate packet evidence before a CAP artifact can be generated.

    The generic CAP helper intentionally remains a small reusable contract. This
    adapter supplies the run-level evidence it cannot infer: every packet must
    have references, verified lineage, complete freshness, and no synthetic
    evidence. Missing or malformed freshness is represented as infinity so the
    existing stale-source gate fails closed.
    """
    if not VERIFICATION_SPINE_ENABLED:
        return check_cap_publication_gates(
            source_freshness_hours={},
            lineage_verified=True,
            has_synthetic_evidence=False,
        )

    packets = [
        cell.get('verification_packet')
        for cell in cells
        if isinstance(cell, dict) and isinstance(cell.get('verification_packet'), dict)
    ]
    if not packets:
        return check_cap_publication_gates(
            source_freshness_hours={'verification_packet': float('inf')},
            lineage_verified=False,
            has_synthetic_evidence=False,
        )

    source_freshness: dict[str, float] = {}
    lineage_verified = True
    has_synthetic_evidence = False

    for packet in packets:
        cell_id = str(packet.get('cell_id') or 'unknown_cell')
        refs = packet.get('evidence_refs')
        if not isinstance(refs, list) or not refs:
            lineage_verified = False

        lineage = packet.get('lineage') if isinstance(packet.get('lineage'), dict) else {}
        source_lineage = lineage.get('source_lineage')
        if not bool(lineage.get('verified')) or not isinstance(source_lineage, dict) or not source_lineage:
            lineage_verified = False
        else:
            for source_name, source in source_lineage.items():
                if not isinstance(source, dict) or not source.get('reference') or not source.get('verified'):
                    lineage_verified = False

        quality = packet.get('data_quality') if isinstance(packet.get('data_quality'), dict) else {}
        if not bool(quality.get('lineage_verified')) or not bool(quality.get('freshness_complete')):
            lineage_verified = False

        has_synthetic_evidence = has_synthetic_evidence or bool(packet.get('has_synthetic_evidence'))
        packet_freshness = packet.get('source_freshness_hours')
        packet_freshness = packet_freshness if isinstance(packet_freshness, dict) else {}
        if not packet_freshness:
            source_freshness[f'{cell_id}:unknown'] = float('inf')
            continue
        for source_name, hours in packet_freshness.items():
            try:
                numeric_hours = float(hours)
                if numeric_hours < 0 or not np.isfinite(numeric_hours):
                    raise ValueError('invalid freshness')
            except (TypeError, ValueError):
                numeric_hours = float('inf')
            source_freshness[f'{cell_id}:{source_name}'] = numeric_hours

    return check_cap_publication_gates(
        source_freshness_hours=source_freshness,
        lineage_verified=lineage_verified,
        has_synthetic_evidence=has_synthetic_evidence,
    )


_REGION_SENSOR_HISTORY_CACHE: dict[
    tuple[str, str], dict[str, list[tuple[datetime, float]]]
] = {}
_HISTORY_PAGE_SIZE = 1000
_MAX_HISTORY_PAGES = 64
_MAX_HISTORY_ROWS_PER_CELL = 90


def _parse_history_timestamp(raw_date: object) -> datetime | None:
    if not raw_date:
        return None
    try:
        return datetime.fromisoformat(str(raw_date).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


def _parse_observation_history_rows(
    rows: list[dict[str, Any]],
) -> dict[str, list[tuple[datetime, float]]]:
    """Parse one page of append-only observations grouped by cell."""
    histories: dict[str, list[tuple[datetime, float]]] = {}
    for row in rows:
        cell_id = str(row.get('cell_id') or '').strip()
        timestamp = _parse_history_timestamp(row.get('acquisition_time'))
        value = row.get('value')
        if not cell_id or timestamp is None or value is None:
            continue
        try:
            numeric = float(value)
            if str(row.get('unit') or 'm') == 'cm':
                numeric /= 100.0
        except (ValueError, TypeError):
            continue
        cell_history = histories.setdefault(cell_id, [])
        if len(cell_history) < _MAX_HISTORY_ROWS_PER_CELL:
            cell_history.append((timestamp, numeric))
    return histories


def _merge_history_maps(
    target: dict[str, list[tuple[datetime, float]]],
    source: dict[str, list[tuple[datetime, float]]],
) -> None:
    for cell_id, values in source.items():
        if cell_id in target:
            continue
        target[cell_id] = list(values[:_MAX_HISTORY_ROWS_PER_CELL])


def _fetch_region_sensor_histories(
    region_key: str,
    sensor: str,
) -> dict[str, list[tuple[datetime, float]]]:
    """Fetch one region's history once and retain the legacy fallback.

    The old path issued one observations query and, when necessary, one
    forecast-grids query for every cell on every forecast hour. The public
    inference job can contain 400 cells and 72 hours, so that pattern turns a
    read-only verification lookup into thousands of network round trips. This
    process-local cache keeps the same per-cell row cap and fallback semantics
    while reducing the lookup to bounded region-level pages.
    """
    cache_key = (str(region_key), str(sensor))
    cached = _REGION_SENSOR_HISTORY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not has_supabase_credentials():
        return {}

    observation_histories: dict[str, list[tuple[datetime, float]]] = {}
    offset = 0
    for _ in range(_MAX_HISTORY_PAGES):
        try:
            page = rest_get(
                'verification_observations',
                params={
                    'select': 'cell_id,acquisition_time,value,unit',
                    'region_key': f'eq.{region_key}',
                    'sensor': f'eq.{sensor}',
                    'variable': 'eq.snow_depth',
                    'order': 'acquisition_time.desc',
                    'limit': str(_HISTORY_PAGE_SIZE),
                    'offset': str(offset),
                },
            ) or []
        except Exception:
            break
        if not isinstance(page, list) or not page:
            break
        page_histories = _parse_observation_history_rows(page)
        for cell_id, values in page_histories.items():
            cell_history = observation_histories.setdefault(cell_id, [])
            remaining = _MAX_HISTORY_ROWS_PER_CELL - len(cell_history)
            if remaining > 0:
                cell_history.extend(values[:remaining])
        if len(page) < _HISTORY_PAGE_SIZE:
            break
        offset += len(page)

    # Preserve the old fallback for cells with no append-only observations.
    legacy_histories: dict[str, list[tuple[datetime, float]]] = {}
    try:
        rows = rest_get(
            'forecast_grids',
            params={
                'select': 'forecast_date,cells',
                'region_key': f'eq.{region_key}',
                'order': 'forecast_date.desc',
                'limit': '30',
            },
        ) or []
    except Exception:
        rows = []

    if isinstance(rows, list):
        for row in rows:
            timestamp = _parse_history_timestamp(row.get('forecast_date'))
            cells = row.get('cells')
            if timestamp is None or not isinstance(cells, list):
                continue
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                cell_id = str(cell.get('cell_id') or '').strip()
                weather = cell.get('weather_inputs') or {}
                depth_cm = weather.get('snow_depth_cm') if isinstance(weather, dict) else None
                if not cell_id or depth_cm is None:
                    continue
                try:
                    numeric = float(depth_cm) / 100.0
                except (ValueError, TypeError):
                    continue
                cell_history = legacy_histories.setdefault(cell_id, [])
                if len(cell_history) < _MAX_HISTORY_ROWS_PER_CELL:
                    cell_history.append((timestamp, numeric))

    _merge_history_maps(observation_histories, legacy_histories)
    _REGION_SENSOR_HISTORY_CACHE[cache_key] = observation_histories
    return observation_histories


def _fetch_cell_sensor_history(
    region_key: str,
    cell_id: str,
    sensor: str,
) -> list[tuple[datetime, float]]:
    """Fetch append-only observations with a cached legacy fallback."""
    if not has_supabase_credentials():
        return []
    histories = _fetch_region_sensor_histories(region_key, sensor)
    return list(histories.get(str(cell_id), []))


def _compute_cell_baselines_from_history(
    *,
    cell_id: str,
    region_key: str,
    as_of: datetime,
) -> tuple[float | None, float | None, float | None]:
    """Compute baseline percentiles for a cell from historical forecast data.

    Returns (p25, p50, p75) for the 30d window of weather snow depth.
    Returns (None, None, None) when insufficient history (<5 data points).
    """
    if not VERIFICATION_SPINE_ENABLED:
        return None, None, None

    history = _fetch_cell_sensor_history(region_key, cell_id, 'weather')
    if len(history) < 5:
        return None, None, None

    baselines = build_cell_baselines(
        cell_id=cell_id,
        sensor='weather',
        history=history,
        as_of=as_of,
        windows=[WINDOW_30D],
    )
    stats_30d = baselines.get(WINDOW_30D)
    if stats_30d is None or not stats_30d.is_valid:
        return None, None, None
    return stats_30d.p25, stats_30d.p50, stats_30d.p75


def _persist_sensor_observations(
    *,
    region_key: str,
    cells: list[dict[str, Any]],
    run_timestamp: datetime,
) -> None:
    """Append sensor evidence and update the legacy derived baseline cache."""
    if not VERIFICATION_SPINE_ENABLED or not has_supabase_credentials():
        return

    observations: list[ObservationContract] = []
    legacy_records: list[dict[str, Any]] = []
    for cell in cells:
        cell_id = cell.get('cell_id', '')
        if not cell_id:
            continue
        packet = cell.get('verification_packet')
        packet = packet if isinstance(packet, dict) else {}
        packet_lineage = packet.get('lineage') if isinstance(packet.get('lineage'), dict) else {}
        source_lineage = packet_lineage.get('source_lineage')
        source_lineage = source_lineage if isinstance(source_lineage, dict) else {}
        source_observations = packet_lineage.get('source_observations')
        source_observations = source_observations if isinstance(source_observations, list) else []
        freshness = packet.get('source_freshness_hours')
        freshness = freshness if isinstance(freshness, dict) else {}
        synthetic = bool(packet.get('has_synthetic_evidence'))
        packet_quality = packet.get('data_quality')
        packet_quality = packet_quality if isinstance(packet_quality, dict) else {}

        for source_observation in source_observations:
            if not isinstance(source_observation, dict):
                continue
            sensor = str(source_observation.get('sensor') or '').strip()
            variable = str(source_observation.get('variable') or '').strip()
            unit = str(source_observation.get('unit') or '').strip()
            value = source_observation.get('value')
            if not sensor or not variable or not unit or value is None:
                continue
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            lineage = source_lineage.get(sensor)
            lineage = lineage if isinstance(lineage, dict) else {}
            evidence_ref = lineage.get('reference')
            verified = bool(lineage.get('verified')) and not synthetic
            try:
                observations.append(ObservationContract(
                    region_key=region_key,
                    cell_id=str(cell_id),
                    sensor=sensor,
                    variable=variable,
                    value=numeric_value,
                    unit=unit,
                    uncertainty=source_observation.get('uncertainty'),
                    acquisition_time=source_observation.get('acquisition_time') or run_timestamp,
                    freshness_hours=freshness.get(sensor),
                    quality_state=QUALITY_VERIFIED if verified else QUALITY_PROVISIONAL,
                    lineage={
                        'verified': verified,
                        'evidence_ref': evidence_ref,
                        'packet_version': packet.get('packet_version'),
                    },
                    synthetic=synthetic,
                    metadata={'observation_kind': packet_quality.get('observation_kind')},
                ))
            except (TypeError, ValueError) as exc:
                print(
                    f'[daily_inference] skipping invalid observation for {region_key}/{cell_id}/{sensor}/{variable}: {exc}',
                    file=sys.stderr,
                )

        weather = cell.get('weather_inputs') or {}
        if isinstance(weather, dict) and weather.get('snow_depth_cm') is not None:
            try:
                depth_m = float(weather['snow_depth_cm']) / 100.0
                legacy_records.append({
                    'region_key': region_key,
                    'cell_id': cell_id,
                    'sensor': 'weather',
                    'window': '30d',
                    'stats': {
                        'snow_depth_m': depth_m,
                        'timestamp': run_timestamp.isoformat(),
                    },
                    'control_cell_ids': [],
                })
            except (ValueError, TypeError):
                pass

    if observations:
        try:
            rest_insert(
                'verification_observations',
                [observation.to_dict() for observation in observations],
                returning='minimal',
            )
        except Exception as exc:
            print(f'[daily_inference] verification observation append failed: {exc}', file=sys.stderr)

    if not legacy_records:
        return

    try:
        rest_upsert(
            'verification_baselines',
            legacy_records,
            on_conflict='region_key,cell_id,sensor,window',
        )
    except Exception as exc:
        print(f'[daily_inference] derived verification baseline cache update failed: {exc}', file=sys.stderr)


def _persist_review_queue(
    *,
    region_key: str,
    cells: list[dict[str, Any]],
) -> None:
    """Rank cells for active learning and persist to verification_review_queue."""
    if not ACTIVE_LEARNING_ENABLED or not has_supabase_credentials():
        return

    ranked = rank_cells_for_observation(cells, region_key=region_key)
    queue_rows = emit_review_queue_rows(ranked)
    if not queue_rows:
        return

    try:
        rest_upsert(
            'verification_review_queue',
            queue_rows,
            on_conflict='region_key,cell_id',
        )
    except Exception as exc:
        print(f'[daily_inference] verification review queue upsert failed: {exc}', file=sys.stderr)


def _build_verification_packet(
    *,
    cell_id: str,
    region_key: str,
    sar_summary: dict[str, Any] | None,
    weather_inputs: dict[str, Any],
    snowpack_method: str,
    gibs_snow_cover: float | None = None,
    s2_snow_cover: float | None = None,
    s2_cloud_cover: float | None = None,
    s2_scene_id: str | None = None,
    s2_acquisition_time: str | None = None,
    s1_depth_m: float | None = None,
    baseline_p25: float | None = None,
    baseline_p50: float | None = None,
    baseline_p75: float | None = None,
) -> dict[str, Any]:
    """Build a verification packet for a cell from available evidence.

    Behind VERIFICATION_SPINE_ENABLED flag. Returns a dict (not dataclass)
    for JSON serialization into forecast grid rows.
    """
    readings: dict[str, AnomalySensorReading] = {}

    if sar_summary and isinstance(sar_summary, dict):
        readings['sar'] = AnomalySensorReading(
            source='sar',
            snow_cover_fraction=sar_summary.get('wet_snow_fraction'),
            snow_depth_m=s1_depth_m,
            loading_rate_24h=sar_summary.get('loading_rate_24h'),
            freshness_hours=sar_summary.get('freshness_hours'),
        )

    if weather_inputs:
        snow_depth_cm = weather_inputs.get('snow_depth_cm')
        readings['weather'] = AnomalySensorReading(
            source='weather',
            snow_depth_m=float(snow_depth_cm) / 100.0 if snow_depth_cm is not None else None,
            loading_rate_24h=float(weather_inputs.get('snowfall_24h_cm', 0)) / 100.0 if weather_inputs.get('snowfall_24h_cm') else None,
            freshness_hours=3.0,
        )

    if gibs_snow_cover is not None:
        readings['gibs'] = AnomalySensorReading(
            source='gibs',
            snow_cover_fraction=gibs_snow_cover,
            freshness_hours=24.0,
        )

    if s2_snow_cover is not None:
        readings['optical'] = AnomalySensorReading(
            source='optical',
            snow_cover_fraction=s2_snow_cover,
            freshness_hours=72.0,
        )

    flags, packet = detect_anomalies(
        cell_id=cell_id,
        region_key=region_key,
        readings=readings,
        baseline_p25=baseline_p25,
        baseline_p50=baseline_p50,
        baseline_p75=baseline_p75,
        weather_snowfall_cm=weather_inputs.get('snowfall_24h_cm') if weather_inputs else None,
        physics_method=snowpack_method or '',
    )

    source_lineage: dict[str, dict[str, Any]] = {}
    evidence_refs: list[str] = []

    if weather_inputs:
        weather_ref = f'openmeteo:{region_key}:{cell_id}'
        source_lineage['weather'] = {
            'reference': weather_ref,
            'source': 'open_meteo_forecast_downscaled_v1',
            'verified': True,
        }
        evidence_refs.append(weather_ref)

    if sar_summary and isinstance(sar_summary, dict):
        scene_ids = [str(scene_id) for scene_id in (sar_summary.get('sar_scene_ids') or []) if scene_id]
        sar_ref = f'sar:{scene_ids[0]}' if scene_ids else None
        source_lineage['sar'] = {
            'reference': sar_ref,
            'scene_ids': scene_ids,
            'acquisition_time': sar_summary.get('sar_scene_time'),
            'lineage_persisted': bool(sar_summary.get('scene_lineage_persisted', bool(sar_ref))),
            'verified': bool(sar_ref) and bool(sar_summary.get('scene_lineage_persisted', True)),
        }
        if sar_ref:
            evidence_refs.extend(f'sar:{scene_id}' for scene_id in scene_ids)

    if gibs_snow_cover is not None:
        gibs_ref = f'gibs:{region_key}:{cell_id}'
        source_lineage['gibs'] = {
            'reference': gibs_ref,
            'source': 'nasa_gibs_modis_terra_snow_cover',
            'verified': True,
        }
        evidence_refs.append(gibs_ref)

    if s2_snow_cover is not None:
        optical_ref = f'sentinel2:{s2_scene_id}' if s2_scene_id else None
        source_lineage['optical'] = {
            'reference': optical_ref,
            'scene_id': s2_scene_id,
            'acquisition_time': s2_acquisition_time,
            'verified': bool(optical_ref),
        }
        if optical_ref:
            evidence_refs.append(optical_ref)

    source_observations: list[dict[str, Any]] = []
    uncertainty_by_sensor = {
        'sar': 0.15,
        'weather': 0.20,
        'gibs': 0.25,
        'optical': 0.10,
    }
    for sensor_name, reading in readings.items():
        for variable, value, unit in (
            ('snow_depth', reading.snow_depth_m, 'm'),
            ('snow_cover_fraction', reading.snow_cover_fraction, 'fraction'),
            ('wet_snow_fraction', reading.wet_snow_fraction, 'fraction'),
            ('loading_rate_24h', reading.loading_rate_24h, 'm'),
        ):
            if value is None:
                continue
            source_observations.append({
                'sensor': sensor_name,
                'variable': variable,
                'value': float(value),
                'unit': unit,
                'uncertainty': uncertainty_by_sensor.get(sensor_name),
                'acquisition_time': (source_lineage.get(sensor_name) or {}).get('acquisition_time'),
            })

    baseline_ids = []
    if baseline_p25 is not None or baseline_p50 is not None or baseline_p75 is not None:
        baseline_id = f'{region_key}:{cell_id}:weather:30d'
        baseline_ids.append(baseline_id)
        evidence_refs.append(f'baseline:{baseline_id}')

    all_lineage_verified = bool(source_lineage) and all(
        bool(source.get('verified')) for source in source_lineage.values()
    )
    synthetic = str(snowpack_method or '').lower().startswith('synthetic_')
    packet.evidence_refs = sorted(set(evidence_refs))
    packet.contributing_sensors = sorted(readings)
    packet.baseline_ids = baseline_ids
    packet.has_synthetic_evidence = synthetic
    packet.lineage = {
        **packet.lineage,
        'source_lineage': source_lineage,
        'source_observations': source_observations,
        'verified': all_lineage_verified,
        'synthetic': synthetic,
    }
    packet.data_quality = {
        **packet.data_quality,
        'lineage_verified': all_lineage_verified,
        'freshness_complete': all(
            reading.freshness_hours is not None for reading in readings.values()
        ),
        'source_count': len(readings),
        'observation_kind': 'advisory_cover_event_evidence',
    }
    packet.attribution = {
        'bucket': packet.attribution_bucket,
        'confidence': packet.confidence,
        'reasons': packet.disagreement_reasons,
    }
    return packet.to_dict()


def _build_fusion_evidence(
    *,
    sar_summary: dict[str, Any] | None,
    weather_inputs: dict[str, Any],
    gibs_snow_cover: float | None = None,
    s2_snow_cover: float | None = None,
    s2_cloud_cover: float | None = None,
    s1_depth_m: float | None = None,
) -> dict[str, Any]:
    """Build fused snow state evidence from available sensors.

    Behind VERIFICATION_SPINE_ENABLED flag.
    """
    observations: list[SensorObservation] = []

    if sar_summary and isinstance(sar_summary, dict):
        observations.append(SensorObservation(
            source='sar',
            wet_snow_fraction=sar_summary.get('wet_snow_fraction'),
            snow_depth_m=s1_depth_m,
            freshness_hours=sar_summary.get('freshness_hours'),
        ))

    if weather_inputs:
        snow_depth_cm = weather_inputs.get('snow_depth_cm')
        observations.append(SensorObservation(
            source='weather',
            snow_depth_m=float(snow_depth_cm) / 100.0 if snow_depth_cm is not None else None,
            loading_rate_24h=float(weather_inputs.get('snowfall_24h_cm', 0)) / 100.0 if weather_inputs.get('snowfall_24h_cm') else None,
            freshness_hours=3.0,
        ))

    if gibs_snow_cover is not None:
        observations.append(SensorObservation(
            source='gibs',
            snow_cover_fraction=gibs_snow_cover,
            freshness_hours=24.0,
        ))

    if s2_snow_cover is not None:
        observations.append(SensorObservation(
            source='optical',
            snow_cover_fraction=s2_snow_cover,
            cloud_cover=s2_cloud_cover,
            freshness_hours=72.0,
        ))

    fused = fuse_observations(observations)
    return fused.to_dict()


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
    cadence_context: Any | None = None,
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
        cadence_context=cadence_context,
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
    partner_observations: list[Any] | None = None,
    cadence_context: Any | None = None,
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
        cadence_context=cadence_context,
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
                partner_observations=partner_observations,
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
    pilot_aws_observations: list[dict[str, Any]] | None = None,
    pilot_Partner_snowpack: list[Any] | None = None,
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
    _active_model_type = str(active_state.get('active_model_type') or 'surrogate_rf_v1')
    _active_model_version = str(active_state.get('active_model_version') or 'unknown')
    _active_model_type_for_release = _active_model_type
    _active_model_version_for_release = _active_model_version
    release_decision = None
    _release_decision_obj = None
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
        else 'tree_shap_approximate'
        if ready_explainability_modes == {'tree_shap_approximate'}
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
        'tree_shap_status': (
            'ready'
            if explainability_mode == 'tree_shap'
            else 'ready_approximate'
            if explainability_mode == 'tree_shap_approximate'
            else explainability_mode
        ),
        'tree_shap_reason': explainability_reason,
        'dominant_driver_strategy': (
            'top_absolute_tree_shap_v1'
            if explainability_mode == 'tree_shap'
            else 'top_absolute_tree_shap_approximate_v1'
            if explainability_mode == 'tree_shap_approximate'
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
    production_calibrator, calibration_manifest = _load_production_calibrator()
    rows, uq_result = apply_uq_to_cells(rows, model_metadata, calibrator=production_calibrator)
    model_metadata['brier_score'] = uq_result.brier_score
    model_metadata['forecast_confidence'] = uq_result.forecast_confidence
    model_metadata['uq_publish_blocked'] = uq_result.publish_blocked
    model_metadata['uq_block_reason'] = uq_result.block_reason
    model_metadata['conformal_calibrator_loaded'] = production_calibrator is not None and production_calibrator.is_calibrated
    model_metadata['calibration_manifest'] = calibration_manifest.as_dict()
    model_metadata['uq_method'] = calibration_manifest.uq_method
    # G-15: Run validation spine gate (EAWS review + calibration drift) in production
    _validation_spine_passed = True
    _eaws_reviewed = False
    try:
        from backend.common.validation_spine_gates import check_gate_d_production_with_validation_spine
        _vs_result = check_gate_d_production_with_validation_spine(
            cells=[c for c in rows if isinstance(c, dict) and c.get('status') == 'ready'],
        )
        model_metadata['validation_spine_gate'] = {
            'passed': _vs_result.passed,
            'blockers': _vs_result.blockers,
            'warnings': _vs_result.warnings,
            'metrics': _vs_result.metrics,
        }
        _validation_spine_passed = _vs_result.passed
        _eaws_reviewed = _vs_result.metrics.get('eaws_review_records', 0) > 0
        if not _vs_result.passed:
            print(f'[daily_inference] Validation spine gate failed: {_vs_result.blockers}', file=sys.stderr)
    except Exception as _vs_exc:
        print(f'[daily_inference] Validation spine gate check failed: {_vs_exc}', file=sys.stderr)
        _validation_spine_passed = False
        model_metadata['validation_spine_gate'] = {'passed': False, 'error': str(_vs_exc)}
    # G-05: Check provenance verification result
    _provenance_verified = model_metadata.get('provenance_verified', False)
    # G-01: Construct composite PublicationEvidence and use canonical evaluation
    _publication_evidence = PublicationEvidence(
        model_type=_active_model_type_for_release,
        model_version=_active_model_version_for_release,
        uq_passed=not uq_result.publish_blocked,
        provenance_verified=_provenance_verified,
        validation_spine_passed=_validation_spine_passed,
        eaws_reviewed=_eaws_reviewed,
    )
    _release_decision_obj = evaluate_publication_evidence(_publication_evidence)
    release_decision = _release_decision_obj.as_dict()
    if not _release_decision_obj.allowed:
        print(f'[daily_inference] Release gate blocked publication: {_release_decision_obj.blocking_reason}', file=sys.stderr)
        if region_status != 'uq_blocked':
            region_status = 'blocked'
    model_metadata['release_decision'] = release_decision
    model_metadata['artifact_mode'] = release_decision.get('artifact_mode', 'blocked')
    model_metadata['warning_authority'] = release_decision.get('warning_authority', 'none')
    model_metadata['movement_advice'] = release_decision.get('movement_advice', 'none')
    # Phase 2: Produce canonical DangerOutput per ready cell
    _artifact_mode = model_metadata.get('artifact_mode', 'blocked')
    _danger_config = _danger_aggregation_config() if _artifact_mode != 'technical_artifact' else DangerAggregationConfig(
        profile='Partner_shadow_v1',
        factor_weights={'slope_angle': 0.3, 'snow_load': 0.3, 'temperature_delta': 0.2, 'wind_transport': 0.2},
        thresholds=(0.15, 0.35, 0.55, 0.75),
    )
    for cell in rows:
        if not isinstance(cell, dict) or cell.get('status') != 'ready':
            continue
        terrain = cell.get('terrain_inputs') or {}
        weather = cell.get('weather_inputs') or {}
        _danger_factors = {
            'slope_angle': _normalize_slope_to_score(float(terrain.get('slope_angle_deg', 0.0))),
            'snow_load': min(float(weather.get('snowfall_24h_cm', 0.0)) / 100.0, 1.0),
            'temperature_delta': min(abs(float(weather.get('temp_gradient', 0.0))) / 20.0, 1.0),
            'wind_transport': min(float(weather.get('wind_loading', 0.0)), 1.0),
        }
        try:
            _danger_out = compute_canonical_danger(_danger_config, **_danger_factors)
            cell['danger_output'] = _danger_out.as_dict()
            if _danger_out.is_shadow_only:
                cell['danger_output']['eaws_semantic_label'] = 'research_shadow'
                cell['danger_output']['eaws_semantic_warning'] = (
                    'Danger level computed using shadow/research profile — '
                    'not authoritative for public warning. EAWS semantics may differ.'
                )
            if 'risk_score' in cell:
                cell['legacy_risk_score'] = cell['risk_score']
        except Exception as danger_exc:
            print(f'[daily_inference] Canonical danger computation failed for cell: {danger_exc}', file=sys.stderr)
            cell['danger_output'] = {'danger_level': 0, 'profile': 'error', 'factors_used': [], 'is_shadow_only': True}
    # Phase 2: Persist calibration lineage
    calibration_lineage = {
        'manifest': calibration_manifest.as_dict(),
        'calibrator_loaded': production_calibrator is not None and production_calibrator.is_calibrated,
        'fallback_active': calibration_manifest.uq_method == 'normal_fallback',
    }
    payload['calibration_lineage'] = calibration_lineage
    if calibration_lineage['fallback_active']:
        payload['uq_fallback_warning'] = (
            'Conformal calibration file missing — using normal approximation fallback. '
            'Prediction intervals are not distribution-free guaranteed.'
        )
        print('[daily_inference] UQ fallback active — calibration file missing, using normal approximation.', file=sys.stderr)
    # Partner observation metadata — cells already have pre-scored partner_observations from assimilation
    pilot_aws_list = pilot_aws_observations or []
    pilot_snowpack_list = pilot_Partner_snowpack or []
    partner_obs_count = 0
    partner_obs_validation_errors: list[str] = []
    if pilot_aws_list or pilot_snowpack_list:
        from backend.common.partner_observation import normalize_aws_record, normalize_snowpack_proxy, validate_partner_observation
        normalized_aws = [normalize_aws_record(r) for r in pilot_aws_list]
        normalized_aws = [o for o in normalized_aws if o is not None]
        normalized_snowpack: list[Any] = []
        for proxy in pilot_snowpack_list:
            station_id = getattr(proxy, 'station_id', '') or 'unknown'
            norm = normalize_snowpack_proxy(proxy, station_id=station_id)
            if norm is not None:
                normalized_snowpack.append(norm)
        all_obs = normalized_aws + normalized_snowpack
        for obs in all_obs:
            errors = validate_partner_observation(obs)
            if errors:
                partner_obs_validation_errors.extend(errors)
                if obs.latitude is None or obs.longitude is None:
                    print(f'[daily_inference] Partner obs {obs.station_id} missing lat/lon — will not match any cell', file=sys.stderr)
        # Count pre-scored partner observations from cells (assimilated during build_hourly_grids)
        for cell in rows:
            if not isinstance(cell, dict) or cell.get('status') != 'ready':
                continue
            matched = cell.get('partner_observations') or []
            if isinstance(matched, list):
                partner_obs_count += len(matched)
    model_metadata['partner_observation_count'] = partner_obs_count
    model_metadata['pilot_aws_observations_loaded'] = len(pilot_aws_list)
    model_metadata['pilot_Partner_snowpack_loaded'] = len(pilot_snowpack_list)
    model_metadata['partner_obs_validation_errors'] = partner_obs_validation_errors
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
            # --- P4: Evaluate publication gate via typed WorkflowContract ---
            pub_evidence = EvidencePacket(
                cell_id=f'{region.key}:publication',
                entries=[],
            )
            pub_eligible = bool(model_metadata.get('publish_eligible', True))
            can_publish, pub_violations, scientist_case_type = evaluate_publication_gate(
                pub_evidence,
                publish_eligible=pub_eligible,
            )
            if pub_violations:
                print(
                    f'[daily_inference] Publication gate violations for {region.key}: {pub_violations}',
                    file=sys.stderr,
                )
            if not can_publish:
                gate_msg = (
                    f'Publication gate blocked for {region.key}: {pub_violations}. '
                    f'Scientist case type: {scientist_case_type}'
                )
                print(f'[daily_inference] {gate_msg}', file=sys.stderr)
                raise RuntimeError(gate_msg)
            # --- End P4 gate ---

            # --- P5: Scientist review gate for explicit exception releases ---
            requires_scientist_review = bool(model_metadata.get('requires_scientist_review'))
            if requires_scientist_review:
                from backend.common.scientist_review_gate import evaluate_scientist_review_gate
                review_decision = evaluate_scientist_review_gate(
                    'publication',
                    pub_evidence,
                    dry_run=dry_run,
                    region_key=region.key,
                    gate_key=str(model_metadata.get('scientist_gate_key') or 'publication_exception'),
                )
                if not review_decision.approved:
                    review_msg = (
                        f'Scientist review gate blocked for {region.key}: {review_decision.reason}'
                    )
                    print(f'[daily_inference] {review_msg}', file=sys.stderr)
                    raise RuntimeError(review_msg)
            # --- End P5 scientist review gate ---
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
                issue_slot=cadence_context.issue_slot if cadence_context else '06',
                cadence_hours=cadence_context.cadence_hours if cadence_context else 24,
                valid_from=cadence_context.valid_from.isoformat() if cadence_context else None,
                valid_to=cadence_context.valid_to.isoformat() if cadence_context else None,
                source_as_of=cadence_context.source_as_of.isoformat() if cadence_context else None,
                issue_time=cadence_context.issue_time.isoformat() if cadence_context else None,
                source_as_of_inferred=bool(cadence_context.source_as_of_inferred) if cadence_context else True,
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
        elif compatibility_row_id and explainability_mode not in {'tree_shap', 'tree_shap_approximate'}:
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
            elif not _release_decision_obj.allowed:
                print(f'[daily_inference] Skipping promote_forecast_run — release gate blocked: {_release_decision_obj.blocking_reason}', file=sys.stderr)
                promoted_row = None
            else:
                try:
                    promoted_row = promote_forecast_run(
                        forecast_run_id=forecast_run_id,
                        model_type=_active_model_type,
                        model_version=_active_model_version,
                        publication_gates_passed=not uq_result.publish_blocked,
                        evidence=_publication_evidence,
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
    # Phase 4: Generate run-derived technical artifact if release decision allows it
    if _release_decision_obj.artifact_mode == 'technical_artifact' and artifact_dir is not None:
        try:
            from backend.scripts.generate_technical_artifact import generate_run_derived_artifact
            _artifact_path = artifact_dir / 'run_derived_artifact.json'
            _run_artifact = generate_run_derived_artifact(
                forecast_run_id=forecast_run_id,
                model_metadata=model_metadata,
                payload=payload,
                calibration_lineage=payload.get('calibration_lineage'),
                output_path=_artifact_path,
            )
            payload['technical_artifact_path'] = str(_artifact_path)
            # Assert artifact file exists after generation
            assert _artifact_path.exists(), f'Run-derived artifact file not found at {_artifact_path}'
            print(f'[daily_inference] Run-derived artifact generated: {_artifact_path}', file=sys.stderr)
            # Publish artifact through forecast manifest path
            _manifest_ref = (payload.get('model_metadata') or {}).get('manifest_storage_ref')
            if _manifest_ref and forecast_run_id:
                try:
                    from backend.common.storage_io import storage_upload_bytes
                    from backend.common.forecast_publication import FORECAST_PRODUCTS_BUCKET
                    _artifact_bytes = _artifact_path.read_bytes()
                    _artifact_storage_ref = storage_upload_bytes(
                        bucket=FORECAST_PRODUCTS_BUCKET,
                        object_path=f'runs/{forecast_run_id}/run_derived_artifact.json',
                        payload=_artifact_bytes,
                        content_type='application/json',
                    )
                    payload['technical_artifact_storage_ref'] = _artifact_storage_ref
                    # Patch forecast_runs row with artifact ref
                    from backend.common.supabase_io import patch_row_by_id
                    from backend.scripts.generate_technical_artifact import build_technical_artifact_asset, build_canonical_manifest, select_regional_asset
                    _meta_update = dict(payload.get('model_metadata') or {})
                    _meta_update['technical_artifact_storage_ref'] = _artifact_storage_ref
                    _meta_update['technical_artifact_path'] = str(_artifact_path)
                    _artifact_asset = build_technical_artifact_asset(
                        artifact_id=_run_artifact['artifact_id'],
                        sha256=_run_artifact['sha256'],
                        storage_ref=_artifact_storage_ref,
                        path=str(_artifact_path),
                        generated_at=_run_artifact.get('generated_at', ''),
                    )
                    _artifact_asset['region'] = payload.get('region_key', 'default')
                    _meta_update['technical_artifact_asset'] = _artifact_asset
                    # G-12: Build canonical manifest with multi-region assets.
                    # Collect assets from all processed region payloads.
                    _all_region_assets = [_artifact_asset]
                    _all_payloads = payload.get('_all_region_payloads') or []
                    for _rp in _all_payloads:
                        if isinstance(_rp, dict) and _rp.get('region_key') and _rp.get('region_key') != payload.get('region_key'):
                            _rp_asset = _rp.get('technical_artifact_asset')
                            if isinstance(_rp_asset, dict):
                                _all_region_assets.append(_rp_asset)
                    _canonical_manifest = build_canonical_manifest(_run_artifact, region_assets=_all_region_assets)
                    _meta_update['canonical_manifest'] = _canonical_manifest
                    _selected_asset = select_regional_asset(_canonical_manifest, preferred_region=payload.get('region_key'))
                    if _selected_asset:
                        _meta_update['selected_regional_asset'] = _selected_asset
                    patch_row_by_id('forecast_runs', forecast_run_id, {
                        'model_metadata': _meta_update,
                    }, returning='minimal')
                    payload['technical_artifact_asset'] = _artifact_asset
                    payload['canonical_manifest'] = _canonical_manifest
                    print(f'[daily_inference] Artifact published to forecast manifest: {_artifact_storage_ref}', file=sys.stderr)
                except Exception as pub_exc:
                    payload['technical_artifact_publish_error'] = str(pub_exc)
                    print(f'[daily_inference] Artifact manifest publication failed: {pub_exc}', file=sys.stderr)
        except Exception as artifact_exc:
            payload['technical_artifact_error'] = str(artifact_exc)
            print(f'[daily_inference] Run-derived artifact generation failed: {artifact_exc}', file=sys.stderr)
    elif _release_decision_obj.artifact_mode != 'technical_artifact':
        payload['technical_artifact_error'] = f'artifact_mode is {_release_decision_obj.artifact_mode}, not technical_artifact'
    # G8: Append calibration record to history (shadow-lane, skip when env unset)
    try:
        from backend.common.calibration_drift import append_calibration_history
        append_calibration_history(record={
            'run_id': str(forecast_run_id),
            'generated_at': str(payload.get('generated_at', '')),
            'empirical_coverage': calibration_manifest.empirical_coverage,
            'held_out_coverage': calibration_manifest.held_out_coverage,
            'alpha': calibration_manifest.alpha,
        })
    except Exception:
        pass
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


def _parse_forecast_start(value: str) -> pd.Timestamp:
    """Parse a hindcast start as a UTC-aware timestamp.

    ``pandas.Timestamp.tz_localize`` rejects RFC-3339 values that already
    carry ``Z`` or an explicit offset.  Normalize aware values with
    ``tz_convert`` so benchmark and replay windows are not silently replaced
    with the current time.
    """
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed.tz_localize('UTC')
    return parsed.tz_convert('UTC')


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
    parser.add_argument('--approximate-tree-shap', action='store_true')
    parser.add_argument('--skip-shap-cache', action='store_true')
    parser.add_argument('--skip-runout-generation', action='store_true')
    parser.add_argument('--skip-compatibility-write', action='store_true')
    parser.add_argument('--emit-stage-metrics', action='store_true')
    parser.add_argument(
        '--snowpack-proxy-mode',
        choices=('cell', 'regional', 'synthetic'),
        default=os.getenv('SNOWPACK_PROXY_MODE', 'cell'),
        help='Snowpack proxy source. Use synthetic only for bounded technical publication proofs.',
    )
    parser.add_argument(
        '--require-same-day-publication',
        action='store_true',
        help='Fail unless every generated region has same-day published forecast_run proof.',
    )
    parser.add_argument(
        '--require-full-grid-publication',
        action='store_true',
        help='Fail unless every generated region has same-day full-grid proof plus structured bulletin content.',
    )
    args = parser.parse_args(raw_argv)
    ravafcast_reference_policy = _enforce_ravafcast_reference_write_policy(args)
    if ravafcast_reference_policy['forced_dry_run']:
        print(
            '[daily_inference] RAvaFcast six-hour reference lane is research-only; '
            'forcing dry-run because staging write approval is absent.',
            file=sys.stderr,
        )

    def _flag_was_explicit(flag: str) -> bool:
        return any(item == flag or item.startswith(f'{flag}=') for item in raw_argv)

    if args.lifeboat_mode:
        if args.require_full_grid_publication:
            raise RuntimeError('lifeboat_mode cannot satisfy --require-full-grid-publication')
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
        approximate_tree_shap=bool(args.approximate_tree_shap and not args.skip_tree_shap),
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

    forecast_start_env = str(os.getenv('FORECAST_START_DATE') or '').strip()
    if forecast_start_env:
        try:
            forecast_date = _parse_forecast_start(forecast_start_env)
        except Exception:
            forecast_date = pd.Timestamp(datetime.now(timezone.utc))
        print(f'[daily_inference] Hindcast mode: forecast_date={forecast_date.isoformat()}', file=sys.stderr)
    else:
        forecast_date = pd.Timestamp(datetime.now(timezone.utc))
    regions = load_regions()

    # F1: Seismic Cascade Integrator — fetch recent earthquakes for Himalayan bbox
    seismic_events: list[Any] = []
    try:
        seismic_events = fetch_recent_earthquakes(HIMALAYAN_BBOX)
        if seismic_events:
            print(f'[seismic] Found {len(seismic_events)} recent earthquakes (M>={SEISMIC_MIN_MAGNITUDE})')
    except Exception as exc:
        print(f'[seismic] Warning: could not fetch seismic data: {exc}', file=sys.stderr)

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
    active_model_state = resolve_active_model_state(current_model_status, candidate_summary, bundle, publication_gates_passed=False)

    outputs = []
    stage_metrics_payload: dict[str, Any] = {
        'artifact_dir': str(artifact_dir),
        'artifact_resolution_seconds': artifact_resolution_seconds,
        'proof_mode': proof_options.as_metadata(),
        'ravafcast_reference_policy': ravafcast_reference_policy,
        'regions': [],
    }

    # RAvaFcast runtime gate — metadata-only, disabled by default.
    # Does NOT modify risk_score, danger, CAP, SACHET, or any active-path output.
    _ravafcast_gate_status = check_pipeline_status()
    stage_metrics_payload['ravafcast_gate'] = emit_gate_metadata(_ravafcast_gate_status)

    # Compute one immutable issue/cadence context for this run.  The context is
    # the source of truth for the grid start, valid window, source snapshot and
    # publication keys; downstream functions must not recompute these values.
    # Default is daily cadence (issue_slot='06', cadence_hours=24).  Six-hour
    # cadence is opt-in and remains a technical-reference lane.
    from backend.common.ravafcast_cadence import build_cadence_context as _build_cadence_context
    _cadence_context = _build_cadence_context(issue_time=forecast_date.to_pydatetime())
    forecast_date = pd.Timestamp(_cadence_context.valid_from)

    # F16: SACHET RSS feed ingestion — fetch national NDMA alerts once before the
    # per-region loop. The SACHET feed is national (all India), not region-specific,
    # so calling it per region was redundant and added ~3 min × 11 regions = ~33 min
    # of unnecessary network calls per CI run.
    global_sachet_rss_summary: dict[str, Any] | None = None
    if SACHET_RSS_ENABLED:
        try:
            rss_cfg = SachetRssConfig()
            rss_alerts, rss_error = ingest_sachet_alerts(rss_cfg)
            global_sachet_rss_summary = get_sachet_alert_summary(
                rss_alerts, fetch_error=rss_error, config=rss_cfg,
            )
            rss_count = len(rss_alerts)
            print(f'[daily_inference] F16: SACHET RSS feed ingested once (national) — {rss_count} current alerts', file=sys.stderr)
        except Exception as rss_exc:
            global_sachet_rss_summary = {'enabled': True, 'ingested': False, 'error': str(rss_exc)}
            print(f'[daily_inference] F16: SACHET RSS feed ingestion failed: {rss_exc}', file=sys.stderr)

    # Pilot data ingestion: AWS station feed + Partner SNOWPACK 1D outputs
    # These are optional pilot-only inputs controlled by env flags.
    pilot_aws_observations: list[dict[str, Any]] = []
    try:
        pilot_aws_observations = fetch_aws_feed()
        if pilot_aws_observations:
            schema_errors = validate_aws_feed_schema(pilot_aws_observations)
            if schema_errors:
                print(f'[daily_inference] AWS feed schema errors: {schema_errors}', file=sys.stderr)
                pilot_aws_observations = []
            else:
                print(f'[daily_inference] Pilot: loaded {len(pilot_aws_observations)} AWS station observations', file=sys.stderr)
    except Exception as aws_exc:
        print(f'[daily_inference] Pilot: AWS feed load skipped: {aws_exc}', file=sys.stderr)
    pilot_Partner_snowpack: list[Any] = []
    try:
        from backend.common.Partner_snowpack_adapter import load_Partner_snowpack_records
        _Partner_records = load_Partner_snowpack_records()
        if _Partner_records:
            print(f'[daily_inference] Pilot: loaded {len(_Partner_records)} Partner SNOWPACK records', file=sys.stderr)
            pilot_Partner_snowpack = _Partner_records
    except Exception as sp_exc:
        print(f'[daily_inference] Pilot: Partner SNOWPACK load skipped: {sp_exc}', file=sys.stderr)
        _Partner_records = []

    # Normalize partner observations for pre-scoring assimilation
    _normalized_partner_obs: list[Any] = []
    if pilot_aws_observations or _Partner_records:
        from backend.common.partner_observation import normalize_aws_record, normalize_snowpack_proxy
        from backend.common.Partner_snowpack_adapter import to_snowpack_proxy
        _normalized_partner_obs = [normalize_aws_record(r) for r in pilot_aws_observations]
        _normalized_partner_obs = [o for o in _normalized_partner_obs if o is not None]
        for record in _Partner_records:
            station_id = getattr(record, 'station_id', '') or 'unknown'
            _proxy = to_snowpack_proxy(record)
            norm = normalize_snowpack_proxy(
                _proxy,
                station_id=station_id,
                latitude=getattr(record, 'latitude', None),
                longitude=getattr(record, 'longitude', None),
                elevation_m=getattr(record, 'elevation_m', None),
            )
            if norm is not None:
                _normalized_partner_obs.append(norm)
        if _normalized_partner_obs:
            print(f'[daily_inference] Pre-scoring assimilation: {len(_normalized_partner_obs)} normalized partner observations ready', file=sys.stderr)

    for region in regions:
        region_stage_metrics: dict[str, Any] = {
            'region_key': region.key,
            'compute_started_at': datetime.now(timezone.utc).isoformat(),
        }
        try:
            hourly_grid_started_at = perf_counter()
            hourly_grids, ensemble_profile = build_hourly_grids(
                region,
                bundle,
                grid_size=args.grid_size,
                forecast_date=forecast_date,
                horizon_hours=args.forecast_hours,
                artifact_dir=artifact_dir,
                use_dynamic_inference=bool(active_model_state.get('use_dynamic_inference')),
                proof_options=proof_options,
                snowpack_proxy_mode=str(args.snowpack_proxy_mode),
                stage_metrics=region_stage_metrics,
                seismic_events=seismic_events,
                partner_observations=_normalized_partner_obs,
                cadence_context=_cadence_context,
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
                ensemble_profile=ensemble_profile,
                seismic_events=seismic_events,
                pilot_aws_observations=pilot_aws_observations,
                pilot_Partner_snowpack=pilot_Partner_snowpack,
                cadence_context=_cadence_context,
            )
            region_stage_metrics['forecast_run_id'] = (payload.get('model_metadata') or {}).get('forecast_run_id')
            region_stage_metrics['status'] = payload.get('status')
            region_stage_metrics['ready_cell_count'] = int(payload.get('ready_cell_count') or 0)
            region_stage_metrics['stale_cell_count'] = int(payload.get('stale_cell_count') or 0)

            # F22: CAP 1.2 Alert Generation — reads canonical danger_output
            _payload_metadata = payload.get('model_metadata') or {}
            max_danger = max(
                (
                    (cell.get('danger_output') or {}).get('danger_level', 0)
                    if isinstance(cell.get('danger_output'), dict)
                    else cell.get('danger_level', 0)
                    if isinstance(cell.get('danger_level'), dict)
                    else cell.get('danger_level', 0)
                    for cell in (payload.get('grid_geojson') or [])
                ),
                default=0,
            )
            max_risk = max(
                (cell.get('risk_score', 0) for cell in (payload.get('grid_geojson') or [])),
                default=0,
            )
            cap_alert_generated = False
            cap_alert_danger_level = 0
            _warning_authority = _payload_metadata.get('warning_authority', 'none')
            _cap_gate_allowed, _cap_gate_reason = _evaluate_verification_cap_gate(
                payload.get('grid_geojson') if isinstance(payload.get('grid_geojson'), list) else [],
            )
            if not VERIFICATION_SPINE_ENABLED and _cap_gate_allowed:
                _cap_gate_reason = 'verification_spine_disabled_legacy_compatibility'
            # Phase 1 gap fix: CAP must trigger on canonical danger_level, not max_risk,
            # warning_authority from the release decision, and evidence gates.
            if CAP_ENABLED and _warning_authority != 'none' and _cap_gate_allowed and should_trigger_alert(max_danger):
                cap_alert_danger_level = int(max_danger)
                try:
                    cap_xml = generate_multi_language_cap(
                        identifier=f'avhub-{region.key}-{forecast_date.strftime("%Y%m%d")}',
                        sender='avalanche-insight-hub@system',
                        region_name=region.name,
                        region_key=region.key,
                        bbox=list(region.bbox),
                        forecast_date=forecast_date.strftime('%Y-%m-%d'),
                        horizon_hours=len(hourly_grids) or args.forecast_hours,
                        max_danger_level=cap_alert_danger_level,
                    )
                    valid, err = validate_cap_xml(cap_xml)
                    if valid:
                        cap_path = artifact_dir / f'cap_alert_{region.key}.xml'
                        cap_path.write_text(cap_xml, encoding='utf-8')
                        cap_alert_generated = True
                        print(f'[daily_inference] F22: CAP alert generated for {region.key} (danger level {cap_alert_danger_level})', file=sys.stderr)
                    else:
                        print(f'[daily_inference] F22: CAP XML validation failed: {err}', file=sys.stderr)
                except Exception as cap_exc:
                    print(f'[daily_inference] F22: CAP alert generation failed: {cap_exc}', file=sys.stderr)
            elif CAP_ENABLED and _warning_authority != 'none' and should_trigger_alert(max_danger) and not _cap_gate_allowed:
                print(f'[daily_inference] F22: CAP evidence gate blocked generation: {_cap_gate_reason}', file=sys.stderr)
            payload.setdefault('model_metadata', {})['cap_alert_generated'] = cap_alert_generated
            payload['model_metadata']['cap_alert_danger_level'] = cap_alert_danger_level
            payload['model_metadata']['cap_uses_danger_level'] = True
            payload['model_metadata']['cap_verification_gate_passed'] = bool(_cap_gate_allowed)
            payload['model_metadata']['cap_verification_gate_reason'] = _cap_gate_reason

            # F16: SACHET Push — disseminate alert via NDMA Sachet RSS feed
            sachet_metadata: dict[str, Any] = {
                'enabled': False,
                'pushed': False,
                'alerts_sent': 0,
                'results': [],
                'error': None,
                'rss_ingest': None,
            }
            # Phase 1 gap fix: SACHET must also be gated by warning_authority
            if (SACHET_ENABLED or SACHET_RSS_ENABLED) and cap_alert_generated and _warning_authority != 'none':
                try:
                    sachet_alerts = build_multi_language_alerts(
                        region_name=region.name,
                        danger_level=cap_alert_danger_level,
                        bbox=list(region.bbox),
                    )
                    sachet_cfg = SachetConfig()
                    push_results = []
                    for sa_alert in sachet_alerts:
                        result = push_sachet_alert(sa_alert, config=sachet_cfg)
                        push_results.append({
                            'language': sa_alert.language,
                            'success': result.success,
                            'message_id': result.message_id,
                            'error': result.error,
                            'channel': result.channel,
                        })
                    sachet_metadata = {
                        'enabled': True,
                        'pushed': any(r['success'] for r in push_results),
                        'alerts_sent': sum(1 for r in push_results if r['success']),
                        'results': push_results,
                        'error': None,
                        'rss_ingest': None,
                    }
                    sent_count = sachet_metadata['alerts_sent']
                    print(f'[daily_inference] F16: SACHET push completed — {sent_count}/{len(sachet_alerts)} alerts sent', file=sys.stderr)
                except Exception as sachet_exc:
                    sachet_metadata['error'] = str(sachet_exc)
                    print(f'[daily_inference] F16: SACHET push failed: {sachet_exc}', file=sys.stderr)

            # F16: SACHET RSS feed ingestion — use pre-fetched national summary
            if global_sachet_rss_summary is not None:
                sachet_metadata['rss_ingest'] = global_sachet_rss_summary

            payload['model_metadata']['sachet_push'] = sachet_metadata

            # F15: AAVDS — fetch victim detection events from feed
            aavds_metadata: dict[str, Any] = {
                'enabled': False,
                'events': [],
                'event_count': 0,
                'error': None,
            }
            if AAVDS_ENABLED:
                try:
                    adapter = AAVDSAdapter()
                    adapter.ingest_rest()
                    bbox = region.bbox
                    region_events = adapter.get_events_in_bounds(
                        min_lat=float(bbox[1]),
                        max_lat=float(bbox[3]),
                        min_lng=float(bbox[0]),
                        max_lng=float(bbox[2]),
                    )
                    aavds_metadata = {
                        'enabled': True,
                        'events': [
                            {
                                'event_id': e.event_id,
                                'timestamp': e.timestamp.isoformat(),
                                'lat': e.lat,
                                'lng': e.lng,
                                'detection_confidence': e.detection_confidence,
                                'signal_type': e.signal_type,
                                'victim_id': e.victim_id,
                                'burial_depth_m': e.burial_depth_m,
                                'signal_strength_db': e.signal_strength_db,
                                'source': e.source,
                            }
                            for e in region_events
                        ],
                        'event_count': len(region_events),
                        'error': None,
                    }
                    print(f'[daily_inference] F15: AAVDS fetched {len(region_events)} events for {region.key}', file=sys.stderr)
                except Exception as aavds_exc:
                    aavds_metadata['error'] = str(aavds_exc)
                    print(f'[daily_inference] F15: AAVDS fetch failed: {aavds_exc}', file=sys.stderr)
            payload['model_metadata']['aavds'] = aavds_metadata

            # F18: Citizen Science — fetch recent community reports
            citizen_metadata: dict[str, Any] = {
                'enabled': False,
                'reports': [],
                'report_count': 0,
                'error': None,
            }
            if CITIZEN_SCIENCE_ENABLED and has_supabase_credentials() and not args.dry_run:
                try:
                    from backend.common.supabase_utils import rest_get
                    reports_data = rest_get(
                        'field_reports',
                        params={
                            'region_key': 'eq.' + region.key,
                            'order': 'created_at.desc',
                            'limit': '20',
                        },
                    )
                    citizen_reports = []
                    for row in (reports_data or []):
                        photo_url = row.get('photo_url')
                        citizen_reports.append({
                            'report_id': str(row.get('report_id', row.get('id', ''))),
                            'lat': float(row.get('lat', 0.0)),
                            'lng': float(row.get('lng', 0.0)),
                            'timestamp': str(row.get('created_at', row.get('timestamp', ''))),
                            'description': str(row.get('description', '')),
                            'status': str(row.get('review_status', row.get('status', 'pending'))),
                            'hazard_type': str(row.get('hazard_type', 'avalanche')),
                            'estimated_size': row.get('estimated_size'),
                            'confidence': float(row.get('confidence', 0.3)),
                            'has_photo': bool(photo_url),
                            'photo_url': photo_url,
                        })
                    citizen_metadata = {
                        'enabled': True,
                        'reports': citizen_reports,
                        'report_count': len(citizen_reports),
                        'error': None,
                    }
                    print(f'[daily_inference] F18: Fetched {len(citizen_reports)} citizen reports for {region.key}', file=sys.stderr)
                except Exception as citizen_exc:
                    citizen_metadata['error'] = str(citizen_exc)
                    print(f'[daily_inference] F18: Citizen science fetch failed: {citizen_exc}', file=sys.stderr)
            payload['model_metadata']['citizen_science'] = citizen_metadata

            # F7: Sensor Ingestion — fetch ground radar events from REST feed
            sensor_metadata: dict[str, Any] = {
                'enabled': False,
                'events': [],
                'event_count': 0,
                'error': None,
            }
            if SENSOR_ENABLED:
                try:
                    sensor_events = fetch_sensor_events_rest()
                    bbox = region.bbox
                    region_sensor_events = [
                        e for e in sensor_events
                        if float(bbox[1]) <= e.lat <= float(bbox[3])
                        and float(bbox[0]) <= e.lng <= float(bbox[2])
                    ]
                    sensor_metadata = {
                        'enabled': True,
                        'events': [e.to_dict() for e in region_sensor_events],
                        'event_count': len(region_sensor_events),
                        'error': None,
                    }
                    print(f'[daily_inference] F7: Fetched {len(region_sensor_events)} sensor events for {region.key}', file=sys.stderr)
                except Exception as sensor_exc:
                    sensor_metadata['error'] = str(sensor_exc)
                    print(f'[daily_inference] F7: Sensor fetch failed: {sensor_exc}', file=sys.stderr)
            payload['model_metadata']['sensor_events'] = sensor_metadata

            # Post-publication metadata update — persist new metadata to forecast_runs
            post_pub_metadata = {
                'sachet_push': sachet_metadata,
                'aavds': aavds_metadata,
                'citizen_science': citizen_metadata,
                'sensor_events': sensor_metadata,
            }
            if has_supabase_credentials() and not args.dry_run:
                try:
                    import requests as _req
                    from backend.common.supabase_io import _base_url, _headers
                    _run_id = (payload.get('model_metadata') or {}).get('forecast_run_id')
                    if _run_id and _run_id != 'uq_blocked':
                        updated_metadata = {**(payload.get('model_metadata') or {}), **post_pub_metadata}
                        _req.patch(
                            f'{_base_url()}/rest/v1/forecast_runs?id=eq.{_run_id}',
                            headers={**_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
                            json={'model_metadata': updated_metadata},
                            timeout=30,
                        )
                except Exception as patch_exc:
                    print(f'[daily_inference] Post-publication metadata PATCH failed: {patch_exc}', file=sys.stderr)

            outputs.append(payload)
        except Exception as region_exc:
            tb_str = traceback.format_exc()
            print(
                f'[daily_inference] Region {region.key} FAILED: {region_exc}\n{tb_str}',
                file=sys.stderr,
            )
            print(
                f'::error::Region {region.key} inference failed: {region_exc}. '
                f'Check logs for full traceback. Continuing to next region.',
                file=sys.stderr,
            )
            region_stage_metrics['status'] = 'failed'
            region_stage_metrics['error'] = str(region_exc)
            region_stage_metrics['traceback'] = tb_str
            outputs.append({
                'hazard_type': 'avalanche',
                'region_key': region.key,
                'region_name': region.name,
                'status': 'failed',
                'model_metadata': {'region_key': region.key, 'error': str(region_exc)},
                'grid_geojson': [],
                'ready_cell_count': 0,
                'stale_cell_count': 0,
            })
        stage_metrics_payload['regions'].append(region_stage_metrics)

    # F19: Continuous Learning Loop — auto-label new detections
    auto_label_count = 0
    if CONTINUOUS_LEARNING_ENABLED:
        for payload in outputs:
            region_key = (payload.get('model_metadata') or {}).get('region_key', 'unknown')
            sar_dets = payload.get('sar_detections') or []
            seismic_events_list = payload.get('seismic_events') or []
            field_reports_list = payload.get('field_reports') or []
            if sar_dets or seismic_events_list or field_reports_list:
                cl_result = process_detections_for_learning(
                    sar_detections=sar_dets,
                    seismic_events=seismic_events_list,
                    field_reports=field_reports_list,
                    region_key=region_key,
                )
                auto_label_count += cl_result.labels_created
        if auto_label_count > 0:
            print(f'[daily_inference] F19: Auto-labeled {auto_label_count} new training labels', file=sys.stderr)
    stage_metrics_payload['auto_labels_created'] = auto_label_count

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
            'snowpack_fetch_seconds_total': round(
                sum(float(region_metric.get('snowpack_fetch_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'runout_generation_seconds_total': round(
                sum(float(region_metric.get('runout_generation_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'hourly_grid_build_seconds_total': round(
                sum(float(region_metric.get('hourly_grid_build_seconds') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'tree_shap_seconds_total': round(
                sum(float(region_metric.get('tree_shap_seconds_total') or 0.0) for region_metric in stage_metrics_payload['regions']),
                3,
            ),
            'tree_shap_mode': next(
                (
                    str(region_metric.get('tree_shap_mode'))
                    for region_metric in stage_metrics_payload['regions']
                    if region_metric.get('tree_shap_mode')
                ),
                'skipped',
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
                'snowpack_proxy_mode': str(args.snowpack_proxy_mode),
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
    latest_benchmark_summary = build_latest_benchmark_summary(
        benchmark_kind='inference_publication',
        phase_breakdown_seconds={
            'artifact_resolution_seconds': artifact_resolution_seconds,
            'snowpack_fetch_seconds_total': float(inference_manifest['stage_metrics_summary']['snowpack_fetch_seconds_total']),
            'runout_generation_seconds_total': float(inference_manifest['stage_metrics_summary']['runout_generation_seconds_total']),
            'hourly_grid_build_seconds_total': float(inference_manifest['stage_metrics_summary']['hourly_grid_build_seconds_total']),
            'publication_seconds_total': float(inference_manifest['stage_metrics_summary']['publication_seconds_total']),
            'compatibility_seconds_total': float(inference_manifest['stage_metrics_summary']['compatibility_seconds_total']),
            'promotion_seconds_total': float(inference_manifest['stage_metrics_summary']['promotion_seconds_total']),
        },
        input_context={
            'forecast_hours': int(args.forecast_hours),
            'grid_size': int(args.grid_size),
            'snowpack_proxy_mode': str(args.snowpack_proxy_mode),
            'region_count': len(outputs),
            'dry_run': bool(args.dry_run),
            'lifeboat_mode': bool(proof_options.enabled),
            'approximate_tree_shap': bool(proof_options.approximate_tree_shap),
        },
        status='ok',
        artifact_ref=str(artifact_dir / 'inference_stage_metrics.json'),
    )
    inference_manifest['latest_benchmark_summary'] = latest_benchmark_summary
    _manifest_artifact_asset = None
    for _out in outputs:
        if isinstance(_out, dict) and _out.get('technical_artifact_asset'):
            _manifest_artifact_asset = _out['technical_artifact_asset']
            break
    if _manifest_artifact_asset:
        inference_manifest['technical_artifact_asset'] = _manifest_artifact_asset
    dump_json(artifact_dir / 'inference_manifest.json', inference_manifest)
    publication_proof_generated_at = datetime.now(timezone.utc)
    publication_proof = build_publication_proof(
        outputs=outputs,
        generated_at=publication_proof_generated_at,
        dry_run=bool(args.dry_run),
        supabase_enabled=has_supabase_credentials(),
        expected_forecast_date=forecast_date.date().isoformat(),
        artifact_dir=artifact_dir,
        expected_grid_size=int(args.grid_size),
        require_full_grid=bool(args.require_full_grid_publication),
    )
    dump_json(artifact_dir / 'publication_proof.json', publication_proof)
    required_proof_status = publication_proof.get('proof_status')
    if (
        bool(args.dry_run)
        and args.require_full_grid_publication
        and not args.require_same_day_publication
    ):
        required_proof_status = publication_proof.get('compute_proof_status')
    if (args.require_same_day_publication or args.require_full_grid_publication) and required_proof_status != 'passed':
        failures = publication_proof.get('failures')
        raise RuntimeError(
            'publication proof failed for region(s): '
            + ', '.join(str(item) for item in failures if item)
        )

    if has_supabase_credentials() and not args.dry_run:
        assert isinstance(active_model_state, dict) and 'release_decision' in active_model_state, (
            'active_model_state must contain an evaluated release_decision before persistence; '
            'cannot bypass release policy'
        )
        next_run = (datetime.now(timezone.utc) + pd.Timedelta(hours=24)).isoformat()
        bundle_metrics = bundle.get('metrics') if isinstance(bundle.get('metrics'), dict) else {}
        patch_latest_model_status_row({
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
            'stability_summary': bundle.get('stability_summary') if isinstance(bundle.get('stability_summary'), dict) else {},
            'drift_mode_state': build_drift_mode_state(candidate_summary if isinstance(candidate_summary, dict) else {}),
            'latest_benchmark_summary': latest_benchmark_summary,
            'next_run': next_run,
        })

    print(json.dumps(inference_manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
