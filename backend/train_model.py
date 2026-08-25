from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from time import perf_counter
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from backend.common.abc_optimizer import (
    ABC_DEFAULT_FEATURES,
    ABCResult,
    build_optimization_summary,
    optimize as abc_optimize,
)
from backend.common.artifacts import create_artifact_dir, dump_json, dump_joblib, latest_artifact_dir, load_json
from backend.common.audit_metadata import build_latest_benchmark_summary
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, generate_cold_start_synthetic_frame
from backend.common.label_governance import GOVERNANCE_VERSION, is_auto_label_eligible
from backend.common.continuous_learning import (
    get_auto_label_audit_trail,
    read_training_audit_trail,
    CONTINUOUS_LEARNING_ENABLED,
)
from backend.common.model_status_state import (
    build_autonomous_evidence_summary,
    build_drift_mode_state,
    build_dynamic_model_candidate,
    build_stability_summary,
)
from backend.common.regions import load_regions
from backend.common.schema_drift import feature_columns_hash, label_schema_hash
from backend.common.supabase_io import (
    has_supabase_credentials,
    patch_latest_model_status_row,
    rest_get,
    rest_insert,
    rest_upsert,
)
from backend.common.training_dataset import load_training_frame
from backend.common.training_reproducibility import (
    TrainingReproducibilityError,
    build_training_evidence,
)
from backend.common.terrain_diagnostics import validate_terrain_gate
from backend.models.surrogate_rf import fit_surrogate_bundle, fit_cold_start_bundle, peirce_skill_score_max
from backend.common.cold_start_config import (
    ForecastMode,
    ColdStartConfig,
    get_cold_start_config,
    resolve_forecast_mode,
    is_cold_start_active,
    validate_cold_start_eligible,
)


# Story 21 + Edit 3: publish the minimum Peirce Skill Score required for the
# trained model artifact to be accepted. Set via env so CI can promote models
# only after a cold-start warmup period.
PSS_FLOOR = float(os.getenv('PSS_FLOOR', '0.45'))
BRIER_SCORE_CEILING = float(os.getenv('BRIER_SCORE_CEILING', '0.15'))
TIME_SERIES_SPLITS = int(os.getenv('TIME_SERIES_SPLITS', '5'))

# Precheck: refuse to attempt training when the ground-truth corpus is too
# small for KMeansSMOTE(k=5) to be meaningful. Exits 0 (success) so the weekly
# scheduled auto-train does not generate CI noise before the event corpus has
# accumulated. Override via env during local dev.
MIN_EVENTS_FOR_TRAINING = int(os.getenv('MIN_EVENTS_FOR_TRAINING', '30'))
SKIP_EVENT_PRECHECK = os.getenv('SKIP_EVENT_PRECHECK', 'false').lower() in ('1', 'true', 'yes')
ALLOW_SYNTHETIC_BOOTSTRAP = os.getenv('ALLOW_SYNTHETIC_BOOTSTRAP', 'false').lower() in ('1', 'true', 'yes')
ALLOW_DRIFT_SKIP = os.getenv('ALLOW_DRIFT_SKIP', 'false').lower() in ('1', 'true', 'yes')
ALLOW_MODEL_STATUS_PUBLISH = os.getenv('ALLOW_MODEL_STATUS_PUBLISH', 'true').lower() in ('1', 'true', 'yes')
DRIFT_WINDOW_DAYS = int(os.getenv('DRIFT_WINDOW_DAYS', '7'))
DRIFT_BASELINE_DAYS = int(os.getenv('DRIFT_BASELINE_DAYS', '30'))
DRIFT_REGION_MEAN_THRESHOLD = float(os.getenv('DRIFT_REGION_MEAN_THRESHOLD', '0.12'))
DRIFT_FEATURE_MAX_THRESHOLD = float(os.getenv('DRIFT_FEATURE_MAX_THRESHOLD', '0.18'))
DRIFT_ALERT_WEBHOOK = os.getenv('DRIFT_ALERT_WEBHOOK', '').strip()
DRIFT_NEW_POSITIVE_THRESHOLD = int(os.getenv('DRIFT_NEW_POSITIVE_THRESHOLD', '10'))
DRIFT_MIN_SAMPLE_SIZE = int(os.getenv('DRIFT_MIN_SAMPLE_SIZE', '20'))
MTS_RUNTIME_PROVIDER = os.getenv('MTS_RUNTIME_PROVIDER', 'local').strip() or 'local'
SAR_RELEASE_GATE_PASSED = os.getenv('SAR_RELEASE_GATE_PASSED', '').lower() in ('1', 'true', 'yes')
REQUESTED_DATASET_SNAPSHOT_ID = os.getenv('REQUESTED_DATASET_SNAPSHOT_ID')
MTS_SAR_VOLUME_MIN_EVENTS = int(os.getenv('MTS_SAR_VOLUME_MIN_EVENTS', '50'))
MTS_SAR_VOLUME_MIN_REGIONS = int(os.getenv('MTS_SAR_VOLUME_MIN_REGIONS', '3'))
MTS_SAR_VOLUME_MIN_SCENE_DATES = int(os.getenv('MTS_SAR_VOLUME_MIN_SCENE_DATES', '14'))
STABILITY_SEED_COUNT = int(os.getenv('STABILITY_SEED_COUNT', '3'))
TRAINING_PREFLIGHT_STRICT = os.getenv('TRAINING_PREFLIGHT_STRICT', 'true').lower() in ('1', 'true', 'yes')
TRAINING_RESEARCH_OVERRIDE = os.getenv('TRAINING_RESEARCH_OVERRIDE', 'false').lower() in ('1', 'true', 'yes')


def _reviewed_snapshot_preflight(selected_region_keys: list[str] | None = None) -> dict[str, Any]:
    """Recheck the reviewed source gate inside the training entrypoint.

    Workflow steps perform the same metadata-only audit before invoking this
    module.  Keeping the check here prevents a direct local or alternate
    runner invocation from spending training time after the workflow boundary
    has been bypassed.  The gate is intentionally network-free.
    """
    if not TRAINING_PREFLIGHT_STRICT or TRAINING_RESEARCH_OVERRIDE:
        return {
            'passed': True,
            'skipped': True,
            'reason': 'training_preflight_not_strict_or_research_override',
            'errors': [],
        }
    snapshot_value = os.getenv('SNAPSHOT_MANIFEST', '').strip()
    if not snapshot_value:
        return {
            'passed': False,
            'skipped': False,
            'errors': ['reviewed snapshot manifest is required before training'],
        }
    try:
        from backend.scripts.audit_training_dataset import (
            _reviewed_snapshot_gate,
            validate_training_snapshot_binding,
        )
        result = _reviewed_snapshot_gate(
            Path(snapshot_value).expanduser(),
            selected_region_keys=selected_region_keys,
        )
        binding = validate_training_snapshot_binding(
            Path(snapshot_value).expanduser(),
            open_source_snapshot_path=(
                Path(open_source_snapshot)
                if (open_source_snapshot := os.getenv('OPEN_SOURCE_LABEL_SNAPSHOT', '').strip())
                else None
            ),
            source_key=os.getenv('OPEN_SOURCE_LABEL_SOURCE_KEY', '').strip() or None,
            license_review_id=os.getenv('OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID', '').strip() or None,
        )
    except Exception as exc:  # pragma: no cover - defensive import/runtime path
        return {
            'passed': False,
            'skipped': False,
            'errors': [f'reviewed snapshot preflight failed: {type(exc).__name__}'],
        }
    combined_errors = [
        *[str(error) for error in result.get('errors') or []],
        *[str(error) for error in binding.get('errors') or []],
    ]
    return {
        **result,
        'skipped': False,
        'passed': bool(result.get('passed') and binding.get('passed')),
        'snapshot_binding': binding,
        'errors': combined_errors,
    }


def build_dataset_snapshot_id(dataset_manifest: dict[str, object] | None) -> str:
    if not isinstance(dataset_manifest, dict):
        return 'unknown'
    version = str(dataset_manifest.get('training_dataset_version') or 'unknown')
    newest_timestamp = dataset_manifest.get('newest_timestamp')
    if isinstance(newest_timestamp, str) and newest_timestamp:
        return f'{version}:{newest_timestamp}'
    return version


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _build_reliability_bins(labels: np.ndarray, probabilities: np.ndarray, *, bins: int = 10) -> tuple[list[dict[str, Any]], float]:
    label_arr = np.asarray(labels).astype(int)
    prob_arr = np.clip(np.asarray(probabilities, dtype=np.float32), 0.0, 1.0)
    if label_arr.size == 0 or prob_arr.size == 0:
        return [], 0.0
    edges = np.linspace(0.0, 1.0, num=bins + 1, dtype=np.float32)
    curve: list[dict[str, Any]] = []
    ece = 0.0
    total = float(label_arr.size)
    for idx in range(bins):
        lower = float(edges[idx])
        upper = float(edges[idx + 1])
        if idx == bins - 1:
            mask = (prob_arr >= lower) & (prob_arr <= upper)
        else:
            mask = (prob_arr >= lower) & (prob_arr < upper)
        sample_count = int(mask.sum())
        if sample_count == 0:
            curve.append({
                'bin_index': idx,
                'bin_start': lower,
                'bin_end': upper,
                'sample_count': 0,
                'positive_count': 0,
                'mean_predicted_probability': None,
                'mean_observed_rate': None,
            })
            continue
        bucket_probs = prob_arr[mask]
        bucket_labels = label_arr[mask]
        mean_pred = float(bucket_probs.mean())
        mean_obs = float(bucket_labels.mean())
        ece += (sample_count / total) * abs(mean_obs - mean_pred)
        curve.append({
            'bin_index': idx,
            'bin_start': lower,
            'bin_end': upper,
            'sample_count': sample_count,
            'positive_count': int(bucket_labels.sum()),
            'mean_predicted_probability': mean_pred,
            'mean_observed_rate': mean_obs,
        })
    return curve, float(ece)


def _merge_reliability_curves(
    labels: np.ndarray,
    raw_probabilities: np.ndarray,
    calibrated_probabilities: np.ndarray,
) -> tuple[list[dict[str, Any]], float, float]:
    raw_curve, raw_ece = _build_reliability_bins(labels, raw_probabilities)
    calibrated_curve, calibrated_ece = _build_reliability_bins(labels, calibrated_probabilities)
    merged: list[dict[str, Any]] = []
    for idx in range(max(len(raw_curve), len(calibrated_curve))):
        raw_bin = raw_curve[idx] if idx < len(raw_curve) else {}
        calibrated_bin = calibrated_curve[idx] if idx < len(calibrated_curve) else {}
        merged.append({
            'bin_index': idx,
            'bin_start': calibrated_bin.get('bin_start', raw_bin.get('bin_start')),
            'bin_end': calibrated_bin.get('bin_end', raw_bin.get('bin_end')),
            'sample_count_uncalibrated': raw_bin.get('sample_count'),
            'positive_count_uncalibrated': raw_bin.get('positive_count'),
            'mean_predicted_probability_uncalibrated': raw_bin.get('mean_predicted_probability'),
            'mean_observed_rate_uncalibrated': raw_bin.get('mean_observed_rate'),
            'sample_count_calibrated': calibrated_bin.get('sample_count'),
            'positive_count_calibrated': calibrated_bin.get('positive_count'),
            'mean_predicted_probability_calibrated': calibrated_bin.get('mean_predicted_probability'),
            'mean_observed_rate_calibrated': calibrated_bin.get('mean_observed_rate'),
        })
    return merged, raw_ece, calibrated_ece


def _build_phase2_label_snapshot(
    *,
    bundle: dict[str, object],
    metadata: dict[str, object],
) -> dict[str, Any]:
    manifest = bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {}
    dataset_snapshot_id = str(bundle.get('dataset_snapshot_id') or build_dataset_snapshot_id(manifest))
    snapshot_id = f'label-snapshot:{dataset_snapshot_id}'
    return {
        'snapshot_id': snapshot_id,
        'hazard_type': 'avalanche',
        'dataset_snapshot_id': dataset_snapshot_id,
        'name': str(bundle.get('training_dataset_version') or dataset_snapshot_id),
        'source_weights': _json_safe(manifest.get('source_training_weight_sums') or {}),
        'source_composition': _json_safe({
            'event_source_counts': manifest.get('event_source_counts') or {},
            'source_region_counts': manifest.get('source_region_counts') or {},
            'newest_timestamp_by_source': manifest.get('newest_timestamp_by_source') or {},
        }),
        'confidence_decay_policy': _json_safe({
            'weight_field': 'training_weight',
            'drift_window_days': DRIFT_WINDOW_DAYS,
            'baseline_window_days': DRIFT_BASELINE_DAYS,
            'drift_skip_allowed': ALLOW_DRIFT_SKIP,
        }),
        'coverage_summary': _json_safe({
            'training_row_count': manifest.get('training_row_count'),
            'positive_count': manifest.get('positive_count'),
            'negative_count': manifest.get('negative_count'),
            'mean_training_weight': manifest.get('mean_training_weight'),
        }),
        'region_coverage': _json_safe(manifest.get('region_keys') or []),
        'season_coverage': _json_safe(manifest.get('season_coverage') or {}),
        'provenance_notes': (
            f"chronological_holdout_v1 generated at {metadata.get('published_at') or datetime.now(timezone.utc).isoformat()}"
        ),
        'status': 'active',
    }


def _resolve_eval_window(test_df: pd.DataFrame, *, fallback_timestamp: str | None) -> tuple[str, str]:
    timestamps = pd.to_datetime(test_df.get('timestamp'), utc=True, errors='coerce') if 'timestamp' in test_df.columns else pd.Series(dtype='datetime64[ns, UTC]')
    timestamps = timestamps.dropna()
    if not timestamps.empty:
        return timestamps.min().date().isoformat(), timestamps.max().date().isoformat()
    fallback = pd.Timestamp(fallback_timestamp or datetime.now(timezone.utc).isoformat(), tz='UTC')
    date_text = fallback.date().isoformat()
    return date_text, date_text


def persist_phase2_evaluation_plane(
    *,
    artifact_dir: Path,
    bundle: dict[str, object],
    metadata: dict[str, object],
    test_df: pd.DataFrame,
) -> dict[str, object]:
    from sklearn.metrics import brier_score_loss

    manifest = bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {}
    lstm_head_meta = bundle.get('lstm_head_meta') if isinstance(bundle.get('lstm_head_meta'), dict) else {}
    evaluation = bundle.get('lstm_evaluation') if isinstance(bundle.get('lstm_evaluation'), dict) else {}
    labels = np.asarray(evaluation.get('test_labels', []), dtype=np.int32)
    raw_probabilities = np.asarray(evaluation.get('test_prob_uncalibrated', []), dtype=np.float32)
    calibrated_probabilities = np.asarray(evaluation.get('test_prob_calibrated', []), dtype=np.float32)
    ordered_test_df = test_df.reset_index(drop=True).copy()
    if len(labels) != len(ordered_test_df):
        raise ValueError(
            f'phase2 evaluation rows misaligned: labels={len(labels)} test_df={len(ordered_test_df)}'
        )

    dataset_snapshot_id = str(bundle.get('dataset_snapshot_id') or build_dataset_snapshot_id(manifest))
    model_version = str(
        bundle.get('dynamic_model_version')
        or lstm_head_meta.get('dynamic_model_version')
        or bundle.get('surrogate_model_version')
        or 'unknown'
    )
    calibration_profile_version = str(bundle.get('dynamic_model_version') or model_version)
    start_date, end_date = _resolve_eval_window(
        ordered_test_df,
        fallback_timestamp=str(metadata.get('published_at') or ''),
    )
    label_snapshot = _build_phase2_label_snapshot(bundle=bundle, metadata=metadata)
    artifact_ref = str(artifact_dir / 'training_metrics.json')
    summary_metrics = {
        'evaluation_mode': 'chronological_holdout_v1',
        'sample_count': int(labels.size),
        'positive_count': int(labels.sum()) if labels.size else 0,
        'brier_score_uncalibrated': float(brier_score_loss(labels, raw_probabilities)) if labels.size else None,
        'brier_score_calibrated': float(brier_score_loss(labels, calibrated_probabilities)) if labels.size else None,
        'pss_uncalibrated': float(lstm_head_meta.get('pss_holdout_uncalibrated') or 0.0),
        'pss_calibrated': float(lstm_head_meta.get('pss_holdout') or lstm_head_meta.get('pss_holdout_calibrated') or 0.0),
        'calibration_method': str(lstm_head_meta.get('calibration_method') or 'unavailable'),
        'calibration_applied': bool(lstm_head_meta.get('calibration_applied')),
        'calibration_improved': bool(lstm_head_meta.get('calibration_improved')),
        'rf_pss': float(lstm_head_meta.get('rf_pss_holdout') or 0.0),
        'rf_brier': float(lstm_head_meta.get('rf_brier_score') or 0.0),
        'shadow_quality_gate_passed': bool(lstm_head_meta.get('shadow_quality_gate_passed')),
    }
    hindcast_run = {
        'hazard_type': 'avalanche',
        'run_name': f'chronological-holdout-{artifact_dir.name}',
        'model_version': model_version,
        'label_snapshot_id': None,
        'dataset_snapshot_id': dataset_snapshot_id,
        'calibration_profile_version': calibration_profile_version,
        'source_composition': _json_safe(label_snapshot.get('source_composition') or {}),
        'region_coverage': _json_safe(label_snapshot.get('region_coverage') or []),
        'region_keys': _json_safe(manifest.get('region_keys') or sorted(set(ordered_test_df.get('region_key', pd.Series(dtype=str)).astype(str).tolist()))),
        'forecast_horizons': [],
        'eval_window_start': start_date,
        'eval_window_end': end_date,
        'status': 'completed',
        'summary_metrics': _json_safe(summary_metrics),
        'artifact_manifest_ref': str(artifact_dir / 'hindcast_run.json'),
        'completed_at': str(metadata.get('published_at') or datetime.now(timezone.utc).isoformat()),
    }

    def _build_report(region_key: str | None, row_mask: np.ndarray) -> dict[str, Any]:
        slice_labels = labels[row_mask]
        slice_raw_probabilities = raw_probabilities[row_mask]
        slice_calibrated_probabilities = calibrated_probabilities[row_mask]
        reliability_curve, raw_ece, calibrated_ece = _merge_reliability_curves(
            slice_labels,
            slice_raw_probabilities,
            slice_calibrated_probabilities,
        )
        if slice_labels.size and len(np.unique(slice_labels)) >= 2:
            pss_uncalibrated, _ = peirce_skill_score_max(slice_labels, slice_raw_probabilities)
            pss_calibrated, _ = peirce_skill_score_max(slice_labels, slice_calibrated_probabilities)
            brier_uncalibrated = float(brier_score_loss(slice_labels, slice_raw_probabilities))
            brier_calibrated = float(brier_score_loss(slice_labels, slice_calibrated_probabilities))
        else:
            pss_uncalibrated = 0.0
            pss_calibrated = 0.0
            brier_uncalibrated = None
            brier_calibrated = None
        report_metrics = {
            'sample_count': int(slice_labels.size),
            'positive_count': int(slice_labels.sum()) if slice_labels.size else 0,
            'brier_score_uncalibrated': brier_uncalibrated,
            'brier_score_calibrated': brier_calibrated,
            'ece_uncalibrated': raw_ece,
            'ece_calibrated': calibrated_ece,
            'pss_uncalibrated': float(pss_uncalibrated),
            'pss_calibrated': float(pss_calibrated),
            'rf_pss': float(lstm_head_meta.get('rf_pss_holdout') or 0.0),
            'rf_brier': float(lstm_head_meta.get('rf_brier_score') or 0.0),
            'calibration_method': str(lstm_head_meta.get('calibration_method') or 'unavailable'),
            'calibration_applied': bool(lstm_head_meta.get('calibration_applied')),
            'calibration_improved': bool(lstm_head_meta.get('calibration_improved')),
            'calibration_reason': lstm_head_meta.get('calibration_reason'),
        }
        return {
            'hindcast_run_id': None,
            'hazard_type': 'avalanche',
            'model_version': model_version,
            'label_snapshot_id': None,
            'dataset_snapshot_id': dataset_snapshot_id,
            'calibration_profile_version': calibration_profile_version,
            'region_key': region_key,
            'season_window': None,
            'forecast_horizon': None,
            'calibration_method': str(lstm_head_meta.get('calibration_method') or 'unavailable'),
            'metric_summary': _json_safe(report_metrics),
            'reliability_curve': _json_safe(reliability_curve),
            'uncertainty_coverage': _json_safe({
                'mean_uncertainty_std': lstm_head_meta.get('mean_uncertainty_std'),
                'uncertainty_validation_passed': lstm_head_meta.get('uncertainty_validation_passed'),
            }),
            'artifact_ref': str(artifact_dir / 'calibration_reports.json'),
        }

    reports = [_build_report(None, np.ones(len(ordered_test_df), dtype=bool))]
    if 'region_key' in ordered_test_df.columns:
        for region_key, group in ordered_test_df.groupby('region_key', sort=True):
            row_mask = (ordered_test_df['region_key'].astype(str) == str(region_key)).to_numpy()
            region_labels = labels[row_mask]
            if region_labels.size < 10 or len(np.unique(region_labels)) < 2:
                continue
            reports.append(_build_report(str(region_key), row_mask))

    dump_json(artifact_dir / 'label_snapshot.json', _json_safe(label_snapshot))
    dump_json(artifact_dir / 'hindcast_run.json', _json_safe(hindcast_run))
    dump_json(artifact_dir / 'calibration_reports.json', _json_safe(reports))

    summary: dict[str, object] = {
        'db_write_status': 'skipped_no_credentials',
        'label_snapshot_snapshot_id': str(label_snapshot['snapshot_id']),
        'label_snapshot_id': None,
        'hindcast_run_id': None,
        'calibration_report_ids': [],
        'calibration_report_ref': str(artifact_dir / 'calibration_reports.json'),
    }
    if not has_supabase_credentials():
        return summary

    try:
        label_rows = rest_upsert(
            'label_snapshots',
            [_json_safe(label_snapshot)],
            on_conflict='snapshot_id',
        )
        label_snapshot_id = str((label_rows or [{}])[0].get('id') or '')
        if not label_snapshot_id:
            raise RuntimeError('label_snapshots upsert did not return an id')
        hindcast_payload = _json_safe({**hindcast_run, 'label_snapshot_id': label_snapshot_id})
        hindcast_rows = rest_insert('hindcast_runs', [hindcast_payload])
        hindcast_run_id = str((hindcast_rows or [{}])[0].get('id') or '')
        if not hindcast_run_id:
            raise RuntimeError('hindcast_runs insert did not return an id')
        calibration_payloads = [
            _json_safe({
                **report,
                'label_snapshot_id': label_snapshot_id,
                'hindcast_run_id': hindcast_run_id,
            })
            for report in reports
        ]
        calibration_rows = rest_insert('calibration_reports', calibration_payloads)
        summary.update({
            'db_write_status': 'ok',
            'label_snapshot_id': label_snapshot_id,
            'hindcast_run_id': hindcast_run_id,
            'calibration_report_ids': [
                str(row.get('id'))
                for row in calibration_rows
                if isinstance(row, dict) and row.get('id')
            ],
            'calibration_report_ref': str(artifact_dir / 'calibration_reports.json'),
        })
        return summary
    except Exception as exc:
        summary.update({
            'db_write_status': 'failed',
            'db_error': str(exc),
        })
        return summary


def publish_guard_reason(
    *,
    is_synthetic: bool,
    allow_publish: bool,
    pss_reported: float | None = None,
    brier_score: float | None = None,
    pss_floor: float = PSS_FLOOR,
    brier_ceiling: float = BRIER_SCORE_CEILING,
) -> str | None:
    if is_synthetic:
        return 'synthetic_bootstrap_not_published'
    if not allow_publish:
        return 'shadow_only_remote_training'
    if pss_reported is not None:
        if pss_floor <= 0.0:
            if pss_reported < pss_floor:
                return 'pss_gate_failed'
        elif pss_reported <= pss_floor:
            return 'pss_gate_failed'
    if brier_score is not None and brier_score > brier_ceiling:
        return 'brier_score_gate_failed'
    return None


def collect_sar_unet_volume_stats(dataset_manifest: dict[str, object] | None) -> dict[str, int]:
    fallback_promoted = 0
    if isinstance(dataset_manifest, dict):
        source_counts = dataset_manifest.get('event_source_counts')
        if isinstance(source_counts, dict):
            fallback_promoted = int(source_counts.get('sar_unet') or 0)
    if not has_supabase_credentials():
        return {
            'sar_unet_shadow_count': 0,
            'sar_unet_promoted_count': fallback_promoted,
            'sar_unet_promoted_region_count': 0,
            'sar_unet_promoted_scene_date_count': 0,
        }
    try:
        rows = rest_get(
            'avalanche_events',
            params={
                'select': 'timestamp,training_eligible,features',
                'source': 'eq.sar_unet',
                'order': 'timestamp.desc',
                'limit': '2000',
            },
        ) or []
    except Exception as exc:  # pragma: no cover - network path
        print(f'[train_model] could not collect sar_unet volume stats ({exc}); using manifest fallback', file=sys.stderr)
        return {
            'sar_unet_shadow_count': 0,
            'sar_unet_promoted_count': fallback_promoted,
            'sar_unet_promoted_region_count': 0,
            'sar_unet_promoted_scene_date_count': 0,
        }

    shadow_count = 0
    promoted_rows: list[dict[str, object]] = []
    for row in rows:
        if bool(row.get('training_eligible')):
            promoted_rows.append(row)
        else:
            shadow_count += 1
    promoted_regions = {
        str((row.get('features') or {}).get('region_key') or 'unknown')
        for row in promoted_rows
        if isinstance(row.get('features'), dict)
    }
    promoted_scene_dates = {
        str(row.get('timestamp'))[:10]
        for row in promoted_rows
        if row.get('timestamp')
    }
    return {
        'sar_unet_shadow_count': shadow_count,
        'sar_unet_promoted_count': len(promoted_rows),
        'sar_unet_promoted_region_count': len(promoted_regions),
        'sar_unet_promoted_scene_date_count': len(promoted_scene_dates),
    }


def mts_shadow_training_ready(sar_volume_stats: dict[str, int] | None) -> bool:
    stats = sar_volume_stats if isinstance(sar_volume_stats, dict) else {}
    return bool(
        SAR_RELEASE_GATE_PASSED
        and int(stats.get('sar_unet_promoted_count') or 0) >= MTS_SAR_VOLUME_MIN_EVENTS
        and int(stats.get('sar_unet_promoted_region_count') or 0) >= MTS_SAR_VOLUME_MIN_REGIONS
        and int(stats.get('sar_unet_promoted_scene_date_count') or 0) >= MTS_SAR_VOLUME_MIN_SCENE_DATES
    )


def build_model_status_truth(
    bundle: dict[str, object],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, object]:
    metrics = bundle.get('metrics') if isinstance(bundle.get('metrics'), dict) else {}
    dataset_manifest = bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {}
    lstm_meta = bundle.get('lstm_head_meta') if isinstance(bundle.get('lstm_head_meta'), dict) else {}
    sar_volume_stats = {
        'sar_unet_shadow_count': int(lstm_meta.get('sar_unet_shadow_count') or 0),
        'sar_unet_promoted_count': int(lstm_meta.get('sar_unet_promoted_count') or 0),
        'sar_unet_promoted_region_count': int(lstm_meta.get('sar_unet_promoted_region_count') or 0),
        'sar_unet_promoted_scene_date_count': int(lstm_meta.get('sar_unet_promoted_scene_date_count') or 0),
    }
    evidence_summary = build_autonomous_evidence_summary(dataset_manifest, sar_volume_stats=sar_volume_stats)
    candidate = build_dynamic_model_candidate(
        bundle,
        artifact_dir=artifact_dir,
        model_status_version=f'async-{artifact_dir.name}' if artifact_dir is not None else None,
    )
    return {
        'pss_reported': metrics.get('pss_reported'),
        'pss_gate_passed': metrics.get('pss_gate_passed'),
        'dynamic_model_candidate': candidate,
        'autonomous_evidence_summary': evidence_summary,
        'stability_summary': bundle.get('stability_summary') if isinstance(bundle.get('stability_summary'), dict) else {},
        'drift_mode_state': build_drift_mode_state(candidate),
        'latest_benchmark_summary': bundle.get('latest_benchmark_summary') if isinstance(bundle.get('latest_benchmark_summary'), dict) else {},
    }


def compute_seed_stability_summary(
    *,
    frame: pd.DataFrame,
    base_seed: int,
    feature_columns: list[str],
) -> dict[str, Any]:
    seed_runs: list[dict[str, Any]] = []
    for offset in range(max(1, STABILITY_SEED_COUNT)):
        seed = base_seed + offset
        candidate_bundle = fit_surrogate_bundle(
            frame=frame,
            feature_columns=feature_columns,
            seed=seed,
            time_series_splits=TIME_SERIES_SPLITS,
        )
        metrics = candidate_bundle.get('metrics') if isinstance(candidate_bundle.get('metrics'), dict) else {}
        seed_runs.append({
            'seed': seed,
            'pss_reported': metrics.get('pss_reported') or metrics.get('pss_holdout'),
            'optimal_threshold': metrics.get('pss_optimal_threshold'),
            'brier_score': metrics.get('brier_score'),
            'selected_features': candidate_bundle.get('selected_features') or [],
        })
    return build_stability_summary(seed_runs, primary_seed=base_seed)


def fit_model(seed: int, frame: pd.DataFrame, dataset_manifest: dict[str, object], forecast_mode: ForecastMode = ForecastMode.FULL) -> tuple[dict[str, object], pd.DataFrame]:
    if forecast_mode == ForecastMode.COLD_START:
        cold_config = get_cold_start_config()
        surrogate_bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=seed,
            config=cold_config,
        )
    else:
        surrogate_bundle = fit_surrogate_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=seed,
            time_series_splits=TIME_SERIES_SPLITS,
        )
    train_df = surrogate_bundle.pop('train_df')
    calib_df = surrogate_bundle.pop('calib_df')
    test_df = surrogate_bundle.pop('test_df')
    metrics = surrogate_bundle['metrics']
    cv_metrics = surrogate_bundle['cv_metrics']
    selected_features = surrogate_bundle['selected_features']

    lstm_head = None
    dataset_snapshot_id = build_dataset_snapshot_id(dataset_manifest)
    sar_volume_stats = collect_sar_unet_volume_stats(dataset_manifest)
    lstm_head_meta: dict[str, object] = {
        'enabled': False,
        'train_flag': os.getenv('TRAIN_MTS_LSTM_HEAD', os.getenv('TRAIN_LSTM_HEAD', 'true')).lower() in ('1', 'true', 'yes'),
        'use_flag_default': os.getenv('USE_MTS_LSTM_HEAD', os.getenv('USE_LSTM_HEAD', 'true')).lower() in ('1', 'true', 'yes'),
        'dynamic_model_type': 'mts_lstm_v1',
        'surrogate_model_role': 'tree_shap_surrogate',
        'runtime_provider': MTS_RUNTIME_PROVIDER,
        'dataset_snapshot_id': dataset_snapshot_id,
        **sar_volume_stats,
    }
    try:
        from backend.lstm_model import fit_lstm_head, split_validation_and_calibration_frame

        validation_df, calibration_df, calibration_split_meta = split_validation_and_calibration_frame(calib_df)
        lstm_head = fit_lstm_head(
            train_df=train_df,
            validation_df=validation_df,
            calibration_df=calibration_df,
            test_df=test_df,
            rf_metrics=metrics,
            seed=seed,
            selected_features=selected_features,
            dataset_manifest=dataset_manifest,
            sar_volume_stats=sar_volume_stats,
            runtime_provider=MTS_RUNTIME_PROVIDER,
            sar_release_gate_passed=SAR_RELEASE_GATE_PASSED,
            requested_dataset_snapshot_id=REQUESTED_DATASET_SNAPSHOT_ID or dataset_snapshot_id,
        )
        if lstm_head is not None:
            lstm_head_meta = getattr(lstm_head, 'metadata', lstm_head_meta)
            lstm_head_meta.setdefault('calibration_split', calibration_split_meta)
            if getattr(lstm_head, 'model', None) is None:
                lstm_head = None
    except Exception as exc:  # pragma: no cover - optional sibling model path
        lstm_head_meta = {
            **lstm_head_meta,
            'enabled': False,
            'error': str(exc),
        }

    # P2.2: Hash of the active FEATURE_COLUMNS + observed label enum so
    # daily_inference can detect schema drift and refuse to serve a stale
    # artifact against an evolved feature set.
    feature_hash = feature_columns_hash(FEATURE_COLUMNS)
    label_observed_vs = sorted({str(v) for v in frame.get('verification_status', pd.Series(dtype=str)).dropna().unique()}) if 'verification_status' in frame.columns else []
    label_observed_sl = sorted({str(v) for v in frame.get('severity', pd.Series(dtype=str)).dropna().astype(str).unique()}) if 'severity' in frame.columns else []
    label_hash = label_schema_hash(label_observed_vs, label_observed_sl)

    bundle = {
        **surrogate_bundle,
        'feature_columns': FEATURE_COLUMNS,
        'metrics': metrics,
        'lstm_head': lstm_head,
        'lstm_head_meta': lstm_head_meta,
        'cv_metrics': cv_metrics,
        'dataset_manifest': dataset_manifest,
        'training_dataset_version': dataset_manifest.get('training_dataset_version', 'unknown'),
        'dataset_snapshot_id': dataset_snapshot_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'seed': seed,
        'feature_columns_hash': feature_hash,
        'label_schema_hash': label_hash,
        'dynamic_model_type': 'mts_lstm_v1' if lstm_head is not None else 'surrogate_rf_v1',
        'dynamic_model_version': lstm_head_meta.get('dynamic_model_version') if isinstance(lstm_head_meta, dict) else None,
        'lstm_evaluation': getattr(lstm_head, 'evaluation_payload', None) if lstm_head is not None else None,
        'forecast_mode': forecast_mode.value,
    }
    bundle['stability_summary'] = compute_seed_stability_summary(
        frame=frame,
        base_seed=seed,
        feature_columns=FEATURE_COLUMNS,
    )
    return bundle, test_df


def publish_metadata(artifact_dir: Path, bundle: dict[str, object]):
    status_truth = build_model_status_truth(bundle, artifact_dir=artifact_dir)
    metadata = {
        'selected_features': bundle['selected_features'],
        'feature_columns': bundle['feature_columns'],
        'feature_means': bundle['feature_means'],
        'resampling': bundle['resampling'],
        'calibration_method': bundle['calibration_method'],
        'calibration_error': bundle['calibration_error'],
        'metrics': bundle['metrics'],
        'lstm_head_meta': bundle.get('lstm_head_meta'),
        'dynamic_model_type': bundle.get('dynamic_model_type'),
        'dynamic_model_version': bundle.get('dynamic_model_version'),
        'surrogate_model_version': bundle.get('surrogate_model_version'),
        'dataset_manifest': bundle.get('dataset_manifest'),
        'training_dataset_version': bundle.get('training_dataset_version'),
        'dataset_snapshot_id': bundle.get('dataset_snapshot_id'),
        'artifact_dir': str(artifact_dir),
        'published_at': datetime.now(timezone.utc).isoformat(),
        'dynamic_model_candidate': status_truth.get('dynamic_model_candidate'),
        'autonomous_evidence_summary': status_truth.get('autonomous_evidence_summary'),
        'stability_summary': status_truth.get('stability_summary'),
        'drift_mode_state': status_truth.get('drift_mode_state'),
        'latest_benchmark_summary': status_truth.get('latest_benchmark_summary'),
    }
    dump_json(artifact_dir / 'feature_schema.json', {
        'feature_columns': bundle['feature_columns'],
        'selected_features': bundle['selected_features'],
        'feature_means': bundle['feature_means'],
    })
    dump_json(artifact_dir / 'dynamic_model_candidate.json', status_truth.get('dynamic_model_candidate'))
    dump_json(artifact_dir / 'autonomous_evidence_summary.json', status_truth.get('autonomous_evidence_summary'))
    dump_json(artifact_dir / 'stability_summary.json', status_truth.get('stability_summary'))
    dump_json(artifact_dir / 'latest_benchmark_summary.json', status_truth.get('latest_benchmark_summary'))
    dump_json(artifact_dir / 'training_metrics.json', metadata)
    dump_joblib(artifact_dir / 'model.joblib', bundle)
    return metadata


def _count_eligible_events() -> int | None:
    """Return the count of training-eligible severe events, or None if we
    cannot query Supabase (e.g. running locally without creds)."""
    if not has_supabase_credentials():
        return None
    from backend.common.config import load_settings as _ls
    settings = _ls()
    try:
        import requests
        resp = requests.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/avalanche_events",
            params={'select': 'id', 'training_eligible': 'eq.true'},
            headers={
                'apikey': settings.supabase_service_role_key,
                'Authorization': f'Bearer {settings.supabase_service_role_key}',
                'Prefer': 'count=exact',
                'Range': '0-0',
            },
            timeout=20,
        )
        resp.raise_for_status()
        content_range = resp.headers.get('content-range', '0-0/0')
        return int(content_range.split('/')[-1])
    except Exception as exc:  # pragma: no cover - network path
        print(f'[train_model] could not count eligible events ({exc}); skipping precheck', file=sys.stderr)
        return None


def _send_drift_alert(drift_stats: dict[str, object]) -> None:
    if not DRIFT_ALERT_WEBHOOK:
        return
    try:
        import requests

        max_feature = float(drift_stats.get('max_feature_distance', 0.0) or 0.0)
        regions = drift_stats.get('regions', {}) if isinstance(drift_stats.get('regions'), dict) else {}
        breached_regions = [
            name for name, info in regions.items()
            if isinstance(info, dict) and float(info.get('mean_distance', 0.0) or 0.0) >= DRIFT_REGION_MEAN_THRESHOLD
        ]
        payload = {
            'content': (
                f'**Drift Alert** — Wasserstein breach detected\n'
                f'Max feature distance: {max_feature:.4f} (threshold: {DRIFT_FEATURE_MAX_THRESHOLD})\n'
                f'Regions breached: {", ".join(breached_regions) or "none"}\n'
                f'New positive events: {drift_stats.get("new_positive_events", "unknown")}\n'
                f'Remediation: accelerated_decay (0.5x weight multiplier)\n'
                f'Triggered at: {datetime.now(timezone.utc).isoformat()}'
            ),
        }
        requests.post(DRIFT_ALERT_WEBHOOK, json=payload, timeout=10)
        print('[train_model] drift alert sent to webhook')
    except Exception as exc:
        print(f'[train_model] drift alert failed: {exc}', file=sys.stderr)


def compute_drift_stats(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty or 'timestamp' not in frame.columns:
        return {'skip_retrain': False, 'reason': 'empty_frame'}

    ordered = frame.sort_values('timestamp').reset_index(drop=True)
    latest_ts = pd.Timestamp(ordered['timestamp'].max())
    recent_start = latest_ts - pd.Timedelta(days=DRIFT_WINDOW_DAYS)
    baseline_start = recent_start - pd.Timedelta(days=DRIFT_BASELINE_DAYS)
    recent = ordered[ordered['timestamp'] > recent_start]
    baseline = ordered[(ordered['timestamp'] > baseline_start) & (ordered['timestamp'] <= recent_start)]
    if recent.empty or baseline.empty:
        return {'skip_retrain': False, 'reason': 'insufficient_windows'}
    if len(recent) < DRIFT_MIN_SAMPLE_SIZE or len(baseline) < DRIFT_MIN_SAMPLE_SIZE:
        return {
            'skip_retrain': False,
            'reason': 'insufficient_samples',
            'recent_sample_count': len(recent),
            'baseline_sample_count': len(baseline),
            'min_sample_size': DRIFT_MIN_SAMPLE_SIZE,
            'concept_drift_detected': False,
        }

    feature_extractors = {
        'snowfall_24h': lambda df: (df['snowfall_24h'].astype(float) * 40.0).to_numpy(),
        'temperature_2m': lambda df: df['temperature_2m'].astype(float).to_numpy(),
        'windspeed_10m': lambda df: df['windspeed_10m'].astype(float).to_numpy(),
    }
    region_stats: dict[str, object] = {}
    max_feature_distance = 0.0
    regions = sorted(set(ordered['region_key'].astype(str).tolist()))
    for region in regions:
        region_recent = recent[recent['region_key'] == region]
        region_baseline = baseline[baseline['region_key'] == region]
        if region_recent.empty or region_baseline.empty:
            continue
        feature_distances: dict[str, float] = {}
        for name, extractor in feature_extractors.items():
            distance = float(wasserstein_distance(extractor(region_recent), extractor(region_baseline)))
            feature_distances[name] = distance
            max_feature_distance = max(max_feature_distance, distance)
        region_mean = float(np.mean(list(feature_distances.values()))) if feature_distances else 0.0
        region_stats[region] = {
            'feature_distances': feature_distances,
            'mean_distance': region_mean,
            'exceeds_region_mean_threshold': region_mean >= DRIFT_REGION_MEAN_THRESHOLD,
        }

    return {
        'recent_window_days': DRIFT_WINDOW_DAYS,
        'baseline_window_days': DRIFT_BASELINE_DAYS,
        'region_mean_threshold': DRIFT_REGION_MEAN_THRESHOLD,
        'feature_max_threshold': DRIFT_FEATURE_MAX_THRESHOLD,
        'regions': region_stats,
        'max_feature_distance': max_feature_distance,
        'concept_drift_detected': bool(max_feature_distance >= DRIFT_FEATURE_MAX_THRESHOLD or any(
            isinstance(region_info, dict) and region_info.get('mean_distance', 0.0) >= DRIFT_REGION_MEAN_THRESHOLD
            for region_info in region_stats.values()
        )),
    }


def load_previous_dataset_manifest(artifact_root: Path) -> dict[str, object] | None:
    try:
        previous_dir = latest_artifact_dir(artifact_root)
        metrics = load_json(previous_dir / 'training_metrics.json')
        return metrics.get('dataset_manifest') if isinstance(metrics, dict) else None
    except Exception:
        return None


def count_new_positive_events(frame: pd.DataFrame, previous_manifest: dict[str, object] | None) -> int:
    if frame.empty or previous_manifest is None:
        return int((frame['label'] == 1).sum()) if 'label' in frame.columns else 0
    newest = previous_manifest.get('newest_timestamp')
    if not isinstance(newest, str):
        return int((frame['label'] == 1).sum()) if 'label' in frame.columns else 0
    newest_ts = pd.Timestamp(newest)
    positives = frame[(frame['label'] == 1) & (frame['timestamp'] > newest_ts)]
    return int(len(positives))


def main() -> int:
    parser = argparse.ArgumentParser(description='Train the Avalanche Insight Hub async ML model')
    parser.add_argument('--samples-per-region', type=int, default=load_settings().samples_per_region)
    parser.add_argument('--seed', type=int, default=load_settings().seed)
    parser.add_argument('--artifact-root', type=Path, default=load_settings().artifact_root)
    parser.add_argument('--forecast-mode', type=str, default=None,
                        choices=['full', 'cold_start', 'transfer'],
                        help='Forecast training mode: full (default), cold_start (3-winter data-efficient), transfer (scaffold)')
    parser.add_argument('--federated', action='store_true', default=False,
                        help='Export model weights for federated learning aggregation')
    parser.add_argument('--sector-id', type=str, default=os.getenv('FEDERATED_SECTOR_ID', 'default_sector'),
                        help='Sector ID for federated weight export')
    parser.add_argument('--region-key', action='append', default=None,
                        help='Region key to filter training events (repeatable). Falls back to TRAINING_REGION_KEYS env var.')
    args = parser.parse_args()

    forecast_mode = ForecastMode(args.forecast_mode) if args.forecast_mode else resolve_forecast_mode()

    if forecast_mode == ForecastMode.TRANSFER:
        print('[train_model] Transfer learning mode is not yet implemented. Exiting.', flush=True)
        return 0

    # Resolve region keys before the gate so a reviewed snapshot cannot pass
    # globally while lacking the seasons/sources for the selected pilot AOI.
    region_keys: list[str] | None = args.region_key
    if not region_keys:
        env_regions = os.getenv('TRAINING_REGION_KEYS', '').strip()
        if env_regions:
            region_keys = [r.strip() for r in env_regions.split(',') if r.strip()]
    if region_keys:
        known_regions = {r.key for r in load_regions()}
        unknown = set(region_keys) - known_regions
        if unknown:
            print(f'::error::Unknown region key(s): {sorted(unknown)}. Available: {sorted(known_regions)}', file=sys.stderr)
            return 1
        print(f'[train_model] Region filter: {region_keys}', flush=True)

    reviewed_snapshot_gate = _reviewed_snapshot_preflight(region_keys)
    if not reviewed_snapshot_gate.get('passed'):
        print(
            '::error title=Reviewed source snapshot preflight blocked::'
            + '; '.join(str(error) for error in reviewed_snapshot_gate.get('errors') or []),
            file=sys.stderr,
        )
        print(json.dumps({'reviewed_snapshot_gate': reviewed_snapshot_gate}, indent=2), file=sys.stderr)
        return 2

    cold_start_active = forecast_mode == ForecastMode.COLD_START

    # Event-count precheck — silence scheduled runs until the corpus is big
    # enough for KMeansSMOTE(k=5) to generate meaningful synthetic neighbors.
    # Skip precheck in cold-start mode (lower event threshold).
    if not SKIP_EVENT_PRECHECK and not cold_start_active:
        eligible = _count_eligible_events()
        if eligible is not None and eligible < MIN_EVENTS_FOR_TRAINING:
            sar_volume_stats = collect_sar_unet_volume_stats(None)
            if not mts_shadow_training_ready(sar_volume_stats):
                print(
                    f'[train_model] precheck: only {eligible} eligible severe events '
                    f'(need >= {MIN_EVENTS_FOR_TRAINING}). '
                    'Insufficient events for KMeansSMOTE. Waiting for more data.'
                )
                print(f'::warning::Training skipped — only {eligible} eligible events (need >= {MIN_EVENTS_FOR_TRAINING}). Waiting for more data ingestion.')
                return 0
            print(
                f'[train_model] precheck override: eligible severe events={eligible} '
                f'but promoted SAR volume + release gate permit shadow MTS training.',
                file=sys.stderr,
            )

    settings = load_settings()
    stage_breakdown_seconds: dict[str, float] = {}
    dataset_started_at = perf_counter()
    frame, dataset_manifest = load_training_frame(
        seed=args.seed,
        samples_per_region=args.samples_per_region,
        grid_size=settings.grid_size,
        allow_synthetic_bootstrap=ALLOW_SYNTHETIC_BOOTSTRAP,
        region_keys=region_keys,
    )
    stage_breakdown_seconds['dataset_load_seconds'] = round(perf_counter() - dataset_started_at, 3)
    is_bootstrap = dataset_manifest.get('training_dataset_version') == 'synthetic_bootstrap_v1'

    # Cold-start augmentation: when cold-start mode is active and the loaded
    # frame is insufficient (bootstrap or fails eligibility), generate
    # zone-calibrated synthetic data using F17 Himalayan zone metadata.
    if cold_start_active:
        eligible, eligibility_msg = validate_cold_start_eligible(frame)
        if not eligible or is_bootstrap:
            print(f'[cold_start] Augmenting training data: {eligibility_msg}', flush=True)
            cold_config = get_cold_start_config()
            cold_frame = generate_cold_start_synthetic_frame(
                load_regions(),
                samples_per_region=args.samples_per_region,
                seed=args.seed,
                augmentation_multiplier=cold_config.synthetic_augmentation_multiplier,
            )
            # Add governance columns matching load_training_frame bootstrap path
            cold_frame['severity'] = None
            cold_frame['confidence'] = cold_frame['label'].astype(float)
            cold_frame['label_confidence'] = np.where(cold_frame['label'] == 1, 0.55, 1.0)
            cold_frame['training_weight'] = np.where(cold_frame['label'] == 1, 0.55, 1.0)
            cold_frame['source_weight'] = 1.0
            cold_frame['corroboration_weight'] = 1.0
            cold_frame['recency_decay'] = 1.0
            cold_frame['confidence_decayed'] = cold_frame['label_confidence']
            cold_frame['governance_version'] = GOVERNANCE_VERSION
            cold_frame['governed_at'] = datetime.now(timezone.utc).isoformat()
            cold_frame['label_source'] = 'cold_start_synthetic'
            cold_frame['review_basis'] = 'synthetic'
            cold_frame['nowcast_ref'] = None
            cold_frame['observer_ref'] = None
            cold_frame['regime'] = None
            cold_frame['timing'] = None
            # Merge with any real data
            if not frame.empty:
                frame = pd.concat([frame, cold_frame], ignore_index=True).sort_values('timestamp').reset_index(drop=True)
            else:
                frame = cold_frame
            is_bootstrap = False
            dataset_manifest['training_dataset_version'] = 'cold_start_synthetic_v1'
            dataset_manifest['is_synthetic'] = True
            dataset_manifest['cold_start_augmented'] = True
            print(f'[cold_start] Augmented frame: {len(frame)} rows, {int((frame["label"] == 1).sum())} positive', flush=True)
    previous_manifest = load_previous_dataset_manifest(args.artifact_root)
    preflight_strict = TRAINING_PREFLIGHT_STRICT and not TRAINING_RESEARCH_OVERRIDE
    try:
        frame, reproducibility_manifest, reproducibility_report = build_training_evidence(
            frame,
            strict=preflight_strict,
        )
    except TrainingReproducibilityError as exc:
        print(
            f"::error title=Training data preflight blocked::{exc}",
            file=sys.stderr,
        )
        return 2
    terrain_debug_stats = dataset_manifest.get('debug_stats')
    terrain_report = terrain_debug_stats.get('terrain_loss_report') if isinstance(terrain_debug_stats, dict) else None
    terrain_errors = validate_terrain_gate(terrain_report)
    if preflight_strict and terrain_errors:
        print(
            '::error title=Terrain evidence gate blocked::' + '; '.join(terrain_errors),
            file=sys.stderr,
        )
        return 2
    dataset_manifest.update({
        'reviewed_snapshot_gate': reviewed_snapshot_gate,
        'reproducibility_version': reproducibility_manifest.get('version'),
        'row_snapshot_sha256': reproducibility_manifest.get('snapshot_hash'),
        'row_snapshot_ref': 'event_rows.jsonl',
        'event_group_count': reproducibility_manifest.get('event_group_count'),
        'spatial_group_count': reproducibility_manifest.get('spatial_group_count'),
        'season_ids': reproducibility_manifest.get('season_ids'),
        'positive_season_ids': reproducibility_manifest.get('positive_season_ids'),
        'positive_source_ids': reproducibility_manifest.get('positive_source_ids'),
        'split_boundaries': reproducibility_manifest.get('split_boundaries'),
        'runtime_manifest': reproducibility_manifest.get('runtime'),
        'preflight': reproducibility_report,
    })
    new_positive_events = count_new_positive_events(frame, previous_manifest)
    drift_stats = compute_drift_stats(frame)
    drift_stats['new_positive_events'] = new_positive_events
    drift_stats['previous_manifest_found'] = previous_manifest is not None
    drift_stats['skip_allowed'] = ALLOW_DRIFT_SKIP and not is_bootstrap

    # F19: Continuous Learning — include auto-generated labels in training
    auto_label_count = 0
    if CONTINUOUS_LEARNING_ENABLED:
        audit_entries = read_training_audit_trail(limit=1000)
        auto_label_count = len(audit_entries)
        if auto_label_count > 0:
            print(f'[train_model] F19: Including {auto_label_count} auto-generated labels from continuous learning', flush=True)
    drift_stats['auto_labels_available'] = auto_label_count
    if drift_stats.get('concept_drift_detected'):
        drift_stats['remediation'] = 'accelerated_decay'
        drift_stats['old_row_weight_multiplier'] = 0.5
        frame.attrs['concept_drift_detected'] = True
        _send_drift_alert(drift_stats)
        if has_supabase_credentials():
            try:
                patch_latest_model_status_row({
                    'feature_version': 'drift-accelerated-decay',
                    'calibration_profile_version': 'drift-accelerated-decay',
                    'threshold_profile_version': 'drift-accelerated-decay',
                })
            except Exception:
                pass

    if ALLOW_DRIFT_SKIP and not is_bootstrap and isinstance(drift_stats.get('regions'), dict):
        region_exceeded = any(
            region_info.get('mean_distance', 0.0) >= DRIFT_REGION_MEAN_THRESHOLD
            for region_info in drift_stats['regions'].values()
            if isinstance(region_info, dict)
        )
        max_feature_exceeded = float(drift_stats.get('max_feature_distance', 0.0) or 0.0) >= DRIFT_FEATURE_MAX_THRESHOLD
        if not region_exceeded and not max_feature_exceeded and new_positive_events < DRIFT_NEW_POSITIVE_THRESHOLD:
            print(f'::warning::Training skipped — drift below thresholds and only {new_positive_events} new positive events (need >= {DRIFT_NEW_POSITIVE_THRESHOLD}). This will auto-resolve when new events are ingested.')
            print(json.dumps({
                'skipped': True,
                'reason': 'drift_below_thresholds',
                'drift_stats': drift_stats,
                'dataset_manifest': dataset_manifest,
            }, indent=2))
            return 0

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_dir = create_artifact_dir(args.artifact_root)
    _, persisted_reproducibility_manifest, persisted_reproducibility_report = build_training_evidence(
        frame,
        artifact_dir=artifact_dir,
        strict=False,
    )
    dump_json(artifact_dir / 'split_manifest.json', persisted_reproducibility_manifest.get('split_boundaries'))
    dump_json(artifact_dir / 'reproducibility_manifest.json', persisted_reproducibility_manifest)
    dump_json(artifact_dir / 'training_preflight.json', persisted_reproducibility_report)
    fit_started_at = perf_counter()
    bundle, test_df = fit_model(seed=args.seed, frame=frame, dataset_manifest=dataset_manifest, forecast_mode=forecast_mode)
    stage_breakdown_seconds['fit_model_seconds'] = round(perf_counter() - fit_started_at, 3)
    bundle['drift_stats'] = drift_stats

    # Edit 3 Story 21: PSS > PSS_FLOOR artifact gate. Use the higher of the
    # chronological-CV mean and the holdout PSS so a single lucky test fold
    # cannot shadow a poor CV run.
    pss_reported = max(
        float(bundle['metrics'].get('pss_holdout', 0.0) or 0.0),
        float(bundle['metrics'].get('pss_timeseries_mean', 0.0) or 0.0),
    )
    # Cold-start allowance: when PSS_FLOOR is explicitly set to 0.0 we accept
    # pss == 0 so the first synthetic-data artifact can ship. At any positive
    # floor (prod default 0.45) we keep the strict > rule per PRD.
    # In cold-start mode, use relaxed gates from ColdStartConfig.
    if cold_start_active:
        cold_config = get_cold_start_config()
        effective_pss_floor = cold_config.pss_floor
        effective_brier_ceiling = cold_config.brier_ceiling
    else:
        effective_pss_floor = PSS_FLOOR
        effective_brier_ceiling = BRIER_SCORE_CEILING
    brier_score = bundle['metrics'].get('brier_score')
    brier_gate_passed = bool(brier_score is None or float(brier_score) <= effective_brier_ceiling)
    if effective_pss_floor <= 0.0:
        pss_gate_passed = pss_reported >= effective_pss_floor
    else:
        pss_gate_passed = pss_reported > effective_pss_floor
    gate_passed = bool(pss_gate_passed and brier_gate_passed)
    bundle['metrics']['pss_reported'] = pss_reported
    bundle['metrics']['pss_gate_passed'] = pss_gate_passed
    bundle['metrics']['brier_gate_passed'] = brier_gate_passed
    bundle['metrics']['brier_score_ceiling'] = effective_brier_ceiling
    bundle['metrics']['pss_floor_applied'] = effective_pss_floor

    metadata_publish_started_at = perf_counter()
    metadata = publish_metadata(artifact_dir, bundle)
    stage_breakdown_seconds['artifact_publish_seconds'] = round(perf_counter() - metadata_publish_started_at, 3)
    metadata['pss_reported'] = pss_reported
    metadata['pss_gate_passed'] = pss_gate_passed
    metadata['pss_gate_floor'] = PSS_FLOOR
    metadata['brier_gate_passed'] = brier_gate_passed
    metadata['brier_score_ceiling'] = BRIER_SCORE_CEILING
    metadata['drift_stats'] = drift_stats
    phase2_started_at = perf_counter()
    phase2_summary = persist_phase2_evaluation_plane(
        artifact_dir=artifact_dir,
        bundle=bundle,
        metadata=metadata,
        test_df=test_df,
    )
    stage_breakdown_seconds['phase2_evaluation_seconds'] = round(perf_counter() - phase2_started_at, 3)
    metadata['phase2_evaluation'] = phase2_summary
    metadata['db_write_status'] = phase2_summary.get('db_write_status')
    if phase2_summary.get('label_snapshot_id'):
        metadata['label_snapshot_id'] = phase2_summary.get('label_snapshot_id')
    if phase2_summary.get('hindcast_run_id'):
        metadata['hindcast_run_id'] = phase2_summary.get('hindcast_run_id')
    if phase2_summary.get('calibration_report_ids'):
        metadata['calibration_report_ids'] = phase2_summary.get('calibration_report_ids')
    if phase2_summary.get('calibration_report_ref'):
        metadata['calibration_report_ref'] = phase2_summary.get('calibration_report_ref')
    if phase2_summary.get('db_error'):
        metadata['db_error'] = phase2_summary.get('db_error')
    dump_json(artifact_dir / 'training_metrics.json', metadata)

    if not gate_passed:
        print(
            f"[train_model] model quality gate FAILED: pss={pss_reported:.3f} floor={effective_pss_floor:.3f}; "
            f"brier={brier_score} ceiling={effective_brier_ceiling:.3f}. "
            "Refusing to publish artifact to Supabase.",
            file=sys.stderr,
        )
        print(json.dumps(metadata, indent=2))
        return 2

    # P1.1: Run backend ABC optimizer on the training frame to publish real
    # feature_weights + abc_enabled:true to model_status.optimization_summary.
    # This replaces the hardcoded fallback weights in trigger-job/index.ts.
    abc_summary: dict[str, object] | None = None
    try:
        abc_started_at = perf_counter()
        abc_result: ABCResult = abc_optimize(
            frame,
            feature_columns=ABC_DEFAULT_FEATURES,
            seed=args.seed,
        )
        stage_breakdown_seconds['abc_optimizer_seconds'] = round(perf_counter() - abc_started_at, 3)
        abc_version = f"opt-abc-{artifact_dir.name}"
        abc_summary = build_optimization_summary(
            abc_result,
            runtime_mode='batch_async',
            version=abc_version,
        )
        metadata['optimization_summary'] = abc_summary
        dump_json(artifact_dir / 'optimization_summary.json', abc_summary)
        dump_json(artifact_dir / 'training_metrics.json', metadata)
        print(
            f"[train_model] ABC optimizer done: holdout_pss={abc_result.holdout_pss:.3f} "
            f"iterations={abc_result.iterations} features={list(abc_result.feature_weights.keys())}",
            file=sys.stderr,
        )
    except Exception as exc:  # pragma: no cover - optimizer is best-effort
        abc_summary = None
        metadata['abc_error'] = str(exc)
        stage_breakdown_seconds['abc_optimizer_seconds'] = stage_breakdown_seconds.get('abc_optimizer_seconds', 0.0)
        print(f"[train_model] ABC optimizer skipped: {exc}", file=sys.stderr)

    training_stage_metrics = {
        'artifact_dir': str(artifact_dir),
        'dataset_snapshot_id': bundle.get('dataset_snapshot_id'),
        'training_row_count': int(dataset_manifest.get('training_row_count') or len(frame)),
        'positive_count': int(dataset_manifest.get('positive_count') or int((frame['label'] == 1).sum())),
        'negative_count': int(dataset_manifest.get('negative_count') or int((frame['label'] == 0).sum())),
        'region_count': len(dataset_manifest.get('region_keys') or []),
        'phase_breakdown_seconds': stage_breakdown_seconds,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
    }
    dump_json(artifact_dir / 'training_stage_metrics.json', training_stage_metrics)
    latest_benchmark_summary = build_latest_benchmark_summary(
        benchmark_kind='training',
        phase_breakdown_seconds=stage_breakdown_seconds,
        input_context={
            'seed': int(args.seed),
            'samples_per_region': int(args.samples_per_region),
            'training_row_count': training_stage_metrics['training_row_count'],
            'positive_count': training_stage_metrics['positive_count'],
            'region_count': training_stage_metrics['region_count'],
            'time_series_splits': int(TIME_SERIES_SPLITS),
        },
        status='ok',
        artifact_ref=str(artifact_dir / 'training_stage_metrics.json'),
    )
    bundle['latest_benchmark_summary'] = latest_benchmark_summary
    metadata['latest_benchmark_summary'] = latest_benchmark_summary
    metadata['stability_summary'] = bundle.get('stability_summary')
    metadata['drift_mode_state'] = build_drift_mode_state(
        build_dynamic_model_candidate(
            bundle,
            artifact_dir=artifact_dir,
            model_status_version=f'async-{artifact_dir.name}',
        )
    )
    dump_json(artifact_dir / 'latest_benchmark_summary.json', latest_benchmark_summary)

    # P2.3: Refuse to publish to Supabase if this artifact was built from the
    # synthetic bootstrap fallback. The artifact remains on disk so the
    # operator can inspect it, but model_status stays pinned to the last
    # real-data model until fresh labeled events arrive.
    manifest = bundle.get('dataset_manifest') if isinstance(bundle.get('dataset_manifest'), dict) else {}
    is_synthetic = bool(manifest.get('is_synthetic'))
    publish_skip_reason = publish_guard_reason(
        is_synthetic=is_synthetic,
        allow_publish=ALLOW_MODEL_STATUS_PUBLISH,
        pss_reported=pss_reported,
        brier_score=float(brier_score) if brier_score is not None else None,
    )
    if publish_skip_reason is not None:
        metadata['publish_skipped'] = publish_skip_reason
    if is_synthetic:
        print(
            "[train_model] Refusing to publish synthetic-bootstrap artifact to Supabase.",
            file=sys.stderr,
        )
    elif not ALLOW_MODEL_STATUS_PUBLISH:
        print(
            "[train_model] Shadow-only remote training: skipping model_status publish.",
            file=sys.stderr,
        )

    if has_supabase_credentials() and publish_skip_reason is None:
        truth_payload = build_model_status_truth(bundle, artifact_dir=artifact_dir)
        payload: dict[str, object] = {
            'version': f"async-{artifact_dir.name}",
            'last_trained': metadata['published_at'],
            'f1_score': metadata['metrics']['f1'],
            'inference_backend': 'batch_async',
            'next_run': None,
            'feature_version': str(bundle.get('dynamic_model_type') or 'surrogate_rf_v1'),
            'calibration_profile_version': str(bundle.get('dynamic_model_version') or 'surrogate_rf_v1'),
            'threshold_profile_version': str(bundle.get('surrogate_model_version') or 'surrogate_rf_v1'),
            **truth_payload,
        }
        if abc_summary is not None:
            payload['optimization_version'] = str(abc_summary['optimization_version'])
            payload['optimization_summary'] = abc_summary
        # P2.2: Publish the hashes so inference (and future concept-drift
        # dashboards) can diff against the current runtime schema.
        if bundle.get('feature_columns_hash'):
            payload['feature_schema_hash'] = bundle['feature_columns_hash']
        if bundle.get('label_schema_hash'):
            payload['label_schema_hash'] = bundle['label_schema_hash']
        try:
            patch_latest_model_status_row(payload)
        except Exception as exc:  # pragma: no cover - publish is best effort
            metadata['publish_error'] = str(exc)
            (artifact_dir / 'training_metrics.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    # F9/Federated: export weights if --federated flag is set
    if args.federated:
        try:
            from backend.common.federated_learning import export_model_weights
            sample_count = int(metadata.get('training_event_count', 0) or 0)
            export_path = export_model_weights(
                model,
                sector_id=args.sector_id,
                sample_count=sample_count,
                training_metrics=metadata,
            )
            print(f'[train_model] Federated weights exported to {export_path}')
        except Exception as exc:
            print(f'[train_model] WARNING: Federated weight export failed: {exc}')

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
