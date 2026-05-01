from __future__ import annotations

from pathlib import Path
from typing import Any


AUTONOMOUS_TRAINING_CLAIM = (
    'minimal local manual-history dependence via external SAR bootstrap + weighted autonomous labels.'
)
MANUAL_EVENT_SOURCES = {
    'field_report',
    'manual_field_report',
    'observer_report',
    'human_observer',
    'expert_review',
}


def _coerce_bool(value: object) -> bool:
    return bool(value)


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: object) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_manual_event_source(source: str) -> bool:
    return source.strip().lower() in MANUAL_EVENT_SOURCES


def build_autonomous_evidence_summary(
    dataset_manifest: dict[str, Any] | None,
    *,
    sar_volume_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = _as_dict(dataset_manifest)
    source_counts = {
        str(key): _coerce_int(value)
        for key, value in _as_dict(manifest.get('event_source_counts')).items()
    }
    source_training_weight_sums = {
        str(key): round(float(value), 6)
        for key, value in _as_dict(manifest.get('source_training_weight_sums')).items()
        if _coerce_float(value) is not None
    }
    source_region_counts = {
        str(key): _coerce_int(value)
        for key, value in _as_dict(manifest.get('source_region_counts')).items()
    }
    newest_timestamp_by_source = {
        str(key): str(value)
        for key, value in _as_dict(manifest.get('newest_timestamp_by_source')).items()
        if value
    }
    positive_count = _coerce_int(manifest.get('positive_count'))
    manual_positive_count = sum(
        count for source, count in source_counts.items() if is_manual_event_source(source)
    )
    autonomous_positive_count = max(0, positive_count - manual_positive_count)
    total_source_weight = sum(source_training_weight_sums.values())
    weighted_source_contributions = {
        source: round(weight / total_source_weight, 6) if total_source_weight > 0 else 0.0
        for source, weight in source_training_weight_sums.items()
    }
    promoted_sar_volume = {
        'sar_unet_shadow_count': _coerce_int(
            _as_dict(sar_volume_stats).get('sar_unet_shadow_count')
            or _as_dict(manifest.get('promoted_sar_volume')).get('sar_unet_shadow_count')
        ),
        'sar_unet_promoted_count': _coerce_int(
            _as_dict(sar_volume_stats).get('sar_unet_promoted_count')
            or _as_dict(manifest.get('promoted_sar_volume')).get('sar_unet_promoted_count')
            or source_counts.get('sar_unet')
        ),
        'sar_unet_promoted_region_count': _coerce_int(
            _as_dict(sar_volume_stats).get('sar_unet_promoted_region_count')
            or _as_dict(manifest.get('promoted_sar_volume')).get('sar_unet_promoted_region_count')
        ),
        'sar_unet_promoted_scene_date_count': _coerce_int(
            _as_dict(sar_volume_stats).get('sar_unet_promoted_scene_date_count')
            or _as_dict(manifest.get('promoted_sar_volume')).get('sar_unet_promoted_scene_date_count')
        ),
    }
    region_keys = manifest.get('region_keys') if isinstance(manifest.get('region_keys'), list) else []
    return {
        'summary_version': 'autonomous_evidence_summary_v1',
        'claim': AUTONOMOUS_TRAINING_CLAIM,
        'training_dataset_version': str(manifest.get('training_dataset_version') or 'unknown'),
        'positive_count': positive_count,
        'negative_count': _coerce_int(manifest.get('negative_count')),
        'training_row_count': _coerce_int(manifest.get('training_row_count')),
        'manual_positive_count': manual_positive_count,
        'autonomous_positive_count': autonomous_positive_count,
        'manual_positive_fraction': round(manual_positive_count / positive_count, 6) if positive_count > 0 else 0.0,
        'autonomous_positive_fraction': round(autonomous_positive_count / positive_count, 6) if positive_count > 0 else 0.0,
        'positive_source_counts': source_counts,
        'source_region_counts': source_region_counts,
        'region_coverage_count': len(region_keys),
        'region_keys': [str(value) for value in region_keys],
        'newest_timestamp': manifest.get('newest_timestamp'),
        'oldest_timestamp': manifest.get('oldest_timestamp'),
        'newest_timestamp_by_source': newest_timestamp_by_source,
        'mean_training_weight': _coerce_float(manifest.get('mean_training_weight')),
        'weighted_source_contributions': weighted_source_contributions,
        'source_training_weight_sums': source_training_weight_sums,
        'promoted_sar_volume': promoted_sar_volume,
    }


def _blocked_gate(
    *,
    dynamic_enabled: bool,
    pss_gate_passed: bool,
    shadow_quality_gate_passed: bool,
    sar_release_gate_passed: bool,
    sar_volume_gate_passed: bool,
) -> str | None:
    if not dynamic_enabled:
        return 'mts_head_unavailable'
    if not pss_gate_passed:
        return 'pss_gate'
    if not shadow_quality_gate_passed:
        return 'shadow_quality_gate'
    if not sar_release_gate_passed:
        return 'sar_release_gate'
    if not sar_volume_gate_passed:
        return 'sar_volume_gate'
    return None


def build_dynamic_model_candidate(
    bundle: dict[str, Any],
    *,
    artifact_dir: Path | None = None,
    model_status_version: str | None = None,
) -> dict[str, Any]:
    metrics = _as_dict(bundle.get('metrics'))
    lstm_meta = _as_dict(bundle.get('lstm_head_meta'))
    dynamic_enabled = _coerce_bool(lstm_meta.get('enabled'))
    pss_gate_passed = _coerce_bool(metrics.get('pss_gate_passed'))
    shadow_quality_gate_passed = _coerce_bool(lstm_meta.get('shadow_quality_gate_passed'))
    sar_release_gate_passed = _coerce_bool(lstm_meta.get('sar_release_gate_passed'))
    sar_volume_gate_passed = _coerce_bool(lstm_meta.get('sar_volume_gate_passed'))
    production_eligibility_gate_passed = _coerce_bool(lstm_meta.get('production_eligibility_gate_passed'))
    promotion_gate_passed = _coerce_bool(lstm_meta.get('promotion_gate_passed'))
    blocked_gate = _blocked_gate(
        dynamic_enabled=dynamic_enabled,
        pss_gate_passed=pss_gate_passed,
        shadow_quality_gate_passed=shadow_quality_gate_passed,
        sar_release_gate_passed=sar_release_gate_passed,
        sar_volume_gate_passed=sar_volume_gate_passed,
    )
    dynamic_model_type = str(
        lstm_meta.get('dynamic_model_type') or bundle.get('dynamic_model_type') or 'mts_lstm_v1'
    )
    dynamic_model_version = str(
        lstm_meta.get('dynamic_model_version') or bundle.get('dynamic_model_version') or bundle.get('created_at') or 'unknown'
    )
    artifact_ref = {
        'artifact_dir': str(artifact_dir) if artifact_dir is not None else None,
        'artifact_run_id': artifact_dir.name if artifact_dir is not None else None,
        'model_status_version': model_status_version,
    }
    return {
        'candidate_version': 'dynamic_model_candidate_v1',
        'enabled': dynamic_enabled,
        'dynamic_model_type': dynamic_model_type,
        'dynamic_model_version': dynamic_model_version,
        'dataset_snapshot_id': str(lstm_meta.get('dataset_snapshot_id') or bundle.get('dataset_snapshot_id') or 'unknown'),
        'training_dataset_version': str(bundle.get('training_dataset_version') or 'unknown'),
        'surrogate_model_version': str(bundle.get('surrogate_model_version') or bundle.get('created_at') or 'unknown'),
        'runtime_provider': str(lstm_meta.get('runtime_provider') or 'local'),
        'artifact_ref': artifact_ref,
        'metrics': {
            'f1_score': _coerce_float(metrics.get('f1')),
            'pss_reported': _coerce_float(metrics.get('pss_reported')),
            'pss_gate_passed': pss_gate_passed,
            'lstm_pss_holdout': _coerce_float(lstm_meta.get('pss_holdout')),
            'rf_pss_holdout': _coerce_float(lstm_meta.get('rf_pss_holdout')),
            'lstm_brier_score': _coerce_float(lstm_meta.get('brier_score')),
            'rf_brier_score': _coerce_float(lstm_meta.get('rf_brier_score')),
            'mean_uncertainty_std': _coerce_float(lstm_meta.get('mean_uncertainty_std')),
        },
        'gates': {
            'pss_gate_passed': pss_gate_passed,
            'shadow_quality_gate_passed': shadow_quality_gate_passed,
            'sar_release_gate_passed': sar_release_gate_passed,
            'sar_volume_gate_passed': sar_volume_gate_passed,
            'production_eligibility_gate_passed': production_eligibility_gate_passed,
            'promotion_gate_passed': promotion_gate_passed,
            'shadow_quality_rule': lstm_meta.get('shadow_quality_rule'),
            'promotion_rule': lstm_meta.get('promotion_rule'),
            'production_eligibility_rule': lstm_meta.get('production_eligibility_rule'),
            'sar_volume_thresholds': _as_dict(lstm_meta.get('sar_volume_thresholds')),
        },
        'sar_volume_stats': {
            'sar_unet_shadow_count': _coerce_int(lstm_meta.get('sar_unet_shadow_count')),
            'sar_unet_promoted_count': _coerce_int(lstm_meta.get('sar_unet_promoted_count')),
            'sar_unet_promoted_region_count': _coerce_int(lstm_meta.get('sar_unet_promoted_region_count')),
            'sar_unet_promoted_scene_date_count': _coerce_int(lstm_meta.get('sar_unet_promoted_scene_date_count')),
        },
        'shadow_mode_default': _coerce_bool(
            lstm_meta.get('shadow_mode_default')
            if 'shadow_mode_default' in lstm_meta
            else not production_eligibility_gate_passed
        ),
        'blocked_gate': blocked_gate,
        'ready_for_activation': dynamic_enabled and blocked_gate is None and production_eligibility_gate_passed,
        'last_trained_at': bundle.get('created_at'),
    }


def resolve_active_model_state(
    current_status: dict[str, Any] | None,
    candidate: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    current = _as_dict(current_status)
    candidate_type = str(candidate.get('dynamic_model_type') or 'mts_lstm_v1')
    candidate_version = str(candidate.get('dynamic_model_version') or 'unknown')
    candidate_ready = _coerce_bool(candidate.get('ready_for_activation'))
    current_active_type = str(current.get('active_model_type') or 'surrogate_rf_v1')
    current_active_version = str(current.get('active_model_version') or '')
    surrogate_version = str(bundle.get('surrogate_model_version') or bundle.get('created_at') or 'unknown')
    candidate_is_active = (
        current_active_type == candidate_type
        and current_active_version == candidate_version
        and candidate_ready
    )
    if candidate_is_active:
        return {
            'active_model_type': candidate_type,
            'active_model_version': candidate_version,
            'promotion_gate_passed': True,
            'shadow_mode_active': False,
            'use_dynamic_inference': True,
            'active_candidate_matches_bundle': True,
        }
    return {
        'active_model_type': 'surrogate_rf_v1',
        'active_model_version': surrogate_version,
        'promotion_gate_passed': False,
        'shadow_mode_active': _coerce_bool(candidate.get('enabled')),
        'use_dynamic_inference': False,
        'active_candidate_matches_bundle': False,
    }


def resolve_active_candidate_artifact_dir(
    artifact_root: Path,
    current_status: dict[str, Any] | None,
) -> Path | None:
    current = _as_dict(current_status)
    candidate = _as_dict(current.get('dynamic_model_candidate'))
    if not candidate:
        return None
    candidate_type = str(candidate.get('dynamic_model_type') or 'mts_lstm_v1')
    candidate_version = str(candidate.get('dynamic_model_version') or '')
    active_type = str(current.get('active_model_type') or '')
    active_version = str(current.get('active_model_version') or '')
    if active_type != candidate_type or active_version != candidate_version:
        return None
    if not _coerce_bool(candidate.get('ready_for_activation')):
        return None
    artifact_ref = _as_dict(candidate.get('artifact_ref'))
    artifact_dir_raw = artifact_ref.get('artifact_dir')
    if not isinstance(artifact_dir_raw, str) or not artifact_dir_raw.strip():
        return None
    artifact_root_resolved = artifact_root.expanduser().resolve()
    artifact_dir = Path(artifact_dir_raw).expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = artifact_root_resolved / artifact_dir
    artifact_dir = artifact_dir.resolve()
    try:
        artifact_dir.relative_to(artifact_root_resolved)
    except ValueError:
        return None
    if not artifact_dir.exists() or not (artifact_dir / 'model.joblib').is_file():
        return None
    return artifact_dir
