from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.common.european_shadow_ingest import load_staged_records
from backend.common.european_shadow_sources import (
    ACCIDENT_EVENT_LABELS_LANE,
    BULLETIN_CONTEXT_LANE,
    DANGER_RATING_LABELS_LANE,
    EUROPEAN_SHADOW_EVALUATION_GATE_VERSION,
    SAR_DETECTION_ACTIVITY_LANE,
    SAR_MANIFEST_LANES,
    TERRAIN_PATH_PRIORS_LANE,
    WEATHER_SNOWPACK_FEATURES_LANE,
    build_shadow_evaluation_gate_manifest,
    dataset_family_assessments,
    summarize_dataset_family_assessments,
)


EUROPEAN_SHADOW_BENCHMARK_REPORT_VERSION = 'european_shadow_benchmark_report_v1'
EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION = 'european_sar_prediction_artifact_v1'


def load_staging_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'staging manifest must be a JSON object: {path}')
    return payload


def load_sar_prediction_artifact(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR prediction artifact must be a JSON object: {path}')
    return payload


def build_european_shadow_benchmark_report(
    *,
    staging_manifests: Iterable[dict[str, Any]],
    sar_prediction_artifacts: Iterable[dict[str, Any]] | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    manifests = list(staging_manifests)
    prediction_artifacts = list(sar_prediction_artifacts or [])
    source_reports = []
    all_records: list[dict[str, Any]] = []
    for manifest in manifests:
        records = load_staged_records(manifest)
        all_records.extend(records)
        source_reports.append(_source_report(manifest, records, prediction_artifacts))

    blockers = _promotion_blockers(source_reports)
    families = dataset_family_assessments().values()
    report = {
        'version': EUROPEAN_SHADOW_BENCHMARK_REPORT_VERSION,
        'snapshot_id': snapshot_id or _snapshot_from_manifests(manifests),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'production_scoring_allowed': False,
        'evaluation_gate_version': EUROPEAN_SHADOW_EVALUATION_GATE_VERSION,
        'evaluation_gates': build_shadow_evaluation_gate_manifest(),
        'dataset_family_summary': summarize_dataset_family_assessments(families),
        'staging_manifest_count': len(manifests),
        'record_count': len(all_records),
        'source_reports': source_reports,
        'summary_by_lane': _summary_by_lane(all_records),
        'promotion_gate_report': {
            'allowed': False,
            'decision': 'blocked_shadow_only',
            'blockers': blockers,
        },
    }
    return report


def _source_report(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    sar_prediction_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source = manifest.get('source') if isinstance(manifest.get('source'), dict) else {}
    source_key = str(manifest.get('source_key') or source.get('source_key') or '').strip()
    data_lane = str(source.get('data_lane') or '').strip()
    metadata_items = [record.get('metadata') for record in records if isinstance(record.get('metadata'), dict)]
    sar_prediction_report = _sar_prediction_report(
        source_key=source_key,
        data_lane=data_lane,
        records=records,
        artifacts=sar_prediction_artifacts or [],
    )
    quality = {
        'record_count': len(records),
        'event_time_record_count': sum(1 for record in records if record.get('event_time')),
        'geometry_ref_record_count': sum(1 for record in records if _asset_ref(record, 'geometry_ref')),
        'stack_ref_record_count': sum(1 for record in records if _asset_ref(record, 'stack_ref')),
        'truth_mask_ref_record_count': sum(1 for record in records if _asset_ref(record, 'truth_mask_ref')),
        'feature_ref_record_count': sum(1 for record in records if _asset_ref(record, 'feature_ref')),
        'bulletin_ref_record_count': sum(1 for record in records if _asset_ref(record, 'bulletin_ref')),
        'training_eligible_record_count': sum(1 for record in records if bool(record.get('training_eligible'))),
        'production_eligible_record_count': sum(1 for record in records if bool(record.get('production_eligible'))),
        'region_counts': dict(sorted(Counter(str(record.get('region_key') or 'unknown') for record in records).items())),
    }
    report = {
        'source_key': source_key,
        'label': source.get('label'),
        'data_lane': data_lane,
        'requested_role': manifest.get('requested_role'),
        'license_review_id': manifest.get('license_review_id'),
        'production_scoring_allowed': False,
        'record_count': len(records),
        'data_quality': quality,
        'benchmark_status': _benchmark_status_for_lane(data_lane, sar_prediction_report),
        'bias_audits': _bias_audits(source_key, data_lane, metadata_items),
        'sar_training_manifest_path': manifest.get('sar_training_manifest_path'),
        'sar_training_manifest_scene_count': manifest.get('sar_training_manifest_scene_count') or 0,
    }
    report.update(_lane_specific_metrics(source_key, data_lane, records, metadata_items, sar_prediction_report))
    return report


def _benchmark_status_for_lane(
    data_lane: str,
    sar_prediction_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data_lane in SAR_MANIFEST_LANES:
        if sar_prediction_report is not None and sar_prediction_report.get('status') == 'computed':
            return {
                'status': 'computed',
                'reason': 'SAR detector prediction artifact is attached and validation metrics were computed.',
            }
        if sar_prediction_report is not None:
            return {
                'status': 'pending_predictions',
                'reason': sar_prediction_report.get('reason') or 'SAR prediction artifact did not cover the declared validation scenes.',
            }
        return {
            'status': 'pending_predictions',
            'reason': 'SAR scenes are staged; detector predictions are required before F1/precision/recall can be claimed.',
        }
    if data_lane == DANGER_RATING_LABELS_LANE:
        return {
            'status': 'pending_predictions',
            'reason': 'Danger-rating calibration needs model danger outputs before accuracy or calibration can be claimed.',
        }
    if data_lane in {WEATHER_SNOWPACK_FEATURES_LANE, BULLETIN_CONTEXT_LANE}:
        return {
            'status': 'context_ready',
            'reason': 'Source provides covariates or semantics, not observed occurrence truth.',
        }
    return {
        'status': 'ready_for_shadow_audit',
        'reason': 'Source can be used for shadow validation once paired with model predictions or target slices.',
    }


def _lane_specific_metrics(
    source_key: str,
    data_lane: str,
    records: list[dict[str, Any]],
    metadata_items: list[dict[str, Any]],
    sar_prediction_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data_lane == SAR_DETECTION_ACTIVITY_LANE:
        return {
            'activity_rate_benchmark': {
                'counts_by_month': _counts_by_month(records),
                'false_positive_review_status_counts': _metadata_counts(metadata_items, 'false_positive_review_status'),
                'temporal_uncertainty_record_count': sum(1 for metadata in metadata_items if metadata.get('temporal_uncertainty_hours') not in (None, '')),
            },
        }
    if source_key in {'swiss_spot6_2018', 'swiss_spot6_2019'}:
        return {
            'extreme_event_split': {
                'split_key': source_key,
                'normal_season_validation_allowed': False,
                'geometry_record_count': sum(1 for record in records if _asset_ref(record, 'geometry_ref')),
            },
        }
    if source_key in {'french_epa_historical', 'french_clpa_extent_priors'}:
        return {
            'observability_bias_audit': {
                'site_count': _distinct_metadata_count(metadata_items, ('site_id', 'path_id')),
                'dated_event_count': sum(1 for record in records if record.get('event_time')),
                'spatial_prior_only': data_lane == TERRAIN_PATH_PRIORS_LANE,
            },
        }
    if data_lane in {DANGER_RATING_LABELS_LANE, WEATHER_SNOWPACK_FEATURES_LANE}:
        return {'calibration_slices': _danger_calibration_slices(metadata_items)}
    if data_lane == ACCIDENT_EVENT_LABELS_LANE:
        return {
            'accident_event_audit': {
                'caught_record_count': _metadata_positive_count(metadata_items, ('caught_count',)),
                'fatality_record_count': _metadata_positive_count(metadata_items, ('dead_count', 'fatality_count')),
                'occurrence_frequency_truth_allowed': False,
            },
        }
    if data_lane == BULLETIN_CONTEXT_LANE:
        return {
            'warning_context_audit': {
                'danger_level_counts': _metadata_counts(metadata_items, 'danger_level'),
                'observed_occurrence_label_allowed': False,
            },
        }
    if data_lane in SAR_MANIFEST_LANES:
        payload = {
            'sar_benchmark_readiness': {
                'manifest_compatible_scene_count': sum(
                    1
                    for record in records
                    if _asset_ref(record, 'stack_ref') and _asset_ref(record, 'truth_mask_ref')
                ),
                'missing_stack_ref_count': sum(1 for record in records if not _asset_ref(record, 'stack_ref')),
                'missing_truth_mask_ref_count': sum(1 for record in records if not _asset_ref(record, 'truth_mask_ref')),
            },
        }
        if sar_prediction_report is not None:
            payload['sar_prediction_metrics'] = sar_prediction_report
        return payload
    return {}


def _bias_audits(source_key: str, data_lane: str, metadata_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    if source_key.startswith('swiss_spot6_'):
        audits.append({
            'audit': 'extreme_event_bias',
            'status': 'flagged',
            'detail': 'SPOT6 2018/2019 records represent extreme avalanche periods, not continuous all-season truth.',
        })
    if source_key.startswith('french_'):
        audits.append({
            'audit': 'observability_bias',
            'status': 'flagged',
            'detail': 'EPA/CLPA coverage is path/site or mapped-extent based, not full spatial occurrence coverage.',
        })
    if data_lane == ACCIDENT_EVENT_LABELS_LANE:
        audits.append({
            'audit': 'accident_only_bias',
            'status': 'blocked_for_frequency_training',
            'detail': 'Accident records are high provenance but not representative of all avalanche activity.',
        })
    if data_lane in {BULLETIN_CONTEXT_LANE, DANGER_RATING_LABELS_LANE}:
        audits.append({
            'audit': 'forecast_not_observation',
            'status': 'blocked_for_occurrence_labels',
            'detail': 'Bulletins and danger ratings are forecast/context labels, not observed avalanche debris truth.',
        })
    if any(metadata.get('false_positive_review_status') for metadata in metadata_items):
        audits.append({
            'audit': 'false_positive_review',
            'status': 'tracked',
            'detail': 'Automated detection rows include false-positive review metadata.',
        })
    return audits


def _danger_calibration_slices(metadata_items: list[dict[str, Any]]) -> dict[str, Any]:
    paired: list[tuple[float, float]] = []
    observed_counts: Counter[str] = Counter()
    for metadata in metadata_items:
        observed = _coerce_float(metadata.get('danger_level'))
        predicted = _coerce_float(metadata.get('predicted_danger_level'))
        if observed is not None:
            observed_counts[str(int(observed) if observed.is_integer() else observed)] += 1
        if observed is not None and predicted is not None:
            paired.append((observed, predicted))
    if not paired:
        return {
            'status': 'pending_predictions',
            'observed_danger_level_counts': dict(sorted(observed_counts.items())),
            'paired_prediction_count': 0,
        }
    absolute_errors = [abs(observed - predicted) for observed, predicted in paired]
    exact_matches = sum(1 for observed, predicted in paired if round(observed) == round(predicted))
    return {
        'status': 'computed',
        'paired_prediction_count': len(paired),
        'mean_absolute_error': sum(absolute_errors) / len(absolute_errors),
        'rounded_accuracy': exact_matches / len(paired),
        'observed_danger_level_counts': dict(sorted(observed_counts.items())),
    }


def _sar_prediction_report(
    *,
    source_key: str,
    data_lane: str,
    records: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if data_lane not in SAR_MANIFEST_LANES:
        return None
    matching = [
        normalized
        for artifact in artifacts
        for normalized in [_normalize_sar_prediction_artifact(artifact)]
        if normalized is not None and _prediction_artifact_matches_source(source_key, normalized)
    ]
    if not matching:
        return None
    reports = [_sar_prediction_report_from_artifact(source_key, records, artifact) for artifact in matching]
    for report in reports:
        if report.get('status') == 'computed':
            return report
    return reports[0] if reports else None


def _normalize_sar_prediction_artifact(artifact: dict[str, Any]) -> dict[str, Any] | None:
    nested = artifact.get('sar_prediction_artifact')
    if isinstance(nested, dict):
        return _normalize_sar_prediction_artifact(nested)

    version = str(artifact.get('version') or '').strip()
    if version == EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION:
        return dict(artifact)

    if isinstance(artifact.get('validation_metrics'), dict) and isinstance(artifact.get('dataset_audit'), dict):
        audit = artifact['dataset_audit']
        return {
            'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
            'source_key': _source_key_from_dataset_audit(audit),
            'dataset_version': artifact.get('dataset_version') or audit.get('dataset_version'),
            'model_family': artifact.get('model_family'),
            'model_version': artifact.get('candidate_model_version') or artifact.get('model_version'),
            'candidate_model_version': artifact.get('candidate_model_version'),
            'split': 'val',
            'threshold': artifact.get('best_threshold'),
            'generated_at': artifact.get('generated_at'),
            'license_review_id': artifact.get('license_review_id'),
            'metrics': {
                'threshold': artifact.get('best_threshold'),
                'auprc': artifact.get('validation_auprc'),
                **artifact['validation_metrics'],
            },
            'scene_breakdown': artifact.get('scene_breakdown') or [],
            'region_breakdown': artifact.get('region_breakdown') or {},
            'evaluated_scene_ids': audit.get('val_events') or artifact.get('val_events') or [],
            'train_events': audit.get('train_events') or artifact.get('train_events') or [],
            'val_events': audit.get('val_events') or artifact.get('val_events') or [],
            'quality_gate': artifact.get('quality_gate'),
        }
    return None


def _source_key_from_dataset_audit(audit: dict[str, Any]) -> str | None:
    source_counts = audit.get('source_dataset_scene_counts')
    if isinstance(source_counts, dict) and len(source_counts) == 1:
        return str(next(iter(source_counts))).strip() or None
    return None


def _prediction_artifact_matches_source(source_key: str, artifact: dict[str, Any]) -> bool:
    artifact_source = str(artifact.get('source_key') or '').strip()
    if artifact_source:
        return artifact_source == source_key
    return False


def _sar_prediction_report_from_artifact(
    source_key: str,
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if str(artifact.get('status') or '').strip() in {'blocked_remote_training', 'failed', 'error'}:
        return _pending_sar_prediction_report(
            artifact,
            reason=str(artifact.get('reason') or artifact.get('error') or 'SAR prediction artifact reports a failed or blocked remote run.'),
        )
    if isinstance(artifact.get('metrics'), dict):
        return _sar_prediction_report_from_metrics_artifact(source_key, records, artifact)
    rows = artifact.get('predictions') or artifact.get('scenes')
    if isinstance(rows, list):
        return _sar_prediction_report_from_mask_rows(source_key, records, artifact, rows)
    return _pending_sar_prediction_report(
        artifact,
        reason='SAR prediction artifact has no metrics and no predictions[] rows.',
    )


def _sar_prediction_report_from_metrics_artifact(
    source_key: str,
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    metrics = dict(artifact.get('metrics') or {})
    scene_breakdown = [
        scene for scene in artifact.get('scene_breakdown', [])
        if isinstance(scene, dict)
    ]
    expected_scene_ids = _expected_prediction_scene_ids(artifact)
    actual_scene_ids = sorted({
        str(scene.get('scene_id') or '').strip()
        for scene in scene_breakdown
        if scene.get('scene_id')
    })
    if not actual_scene_ids and expected_scene_ids:
        actual_scene_ids = sorted(expected_scene_ids)

    missing = sorted(set(expected_scene_ids) - set(actual_scene_ids))
    if missing:
        return _pending_sar_prediction_report(
            artifact,
            reason='SAR prediction artifact is missing one or more declared validation scenes.',
            expected_scene_ids=expected_scene_ids,
            actual_scene_ids=actual_scene_ids,
            missing_scene_ids=missing,
        )
    if not _has_confusion_counts(metrics):
        aggregated = _aggregate_scene_counts(scene_breakdown)
        if aggregated is not None:
            metrics = {
                'threshold': metrics.get('threshold'),
                'auprc': metrics.get('auprc'),
                **_metrics_from_counts(aggregated),
            }
    if not _has_confusion_counts(metrics):
        return _pending_sar_prediction_report(
            artifact,
            reason='SAR prediction artifact metrics are missing TP/FP/FN/TN counts.',
            expected_scene_ids=expected_scene_ids,
            actual_scene_ids=actual_scene_ids,
        )

    return {
        'status': 'computed',
        'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
        'source_key': source_key,
        'dataset_version': artifact.get('dataset_version'),
        'model_family': artifact.get('model_family'),
        'model_version': artifact.get('model_version') or artifact.get('candidate_model_version'),
        'split': artifact.get('split') or 'val',
        'threshold': _coerce_float(artifact.get('threshold') or metrics.get('threshold')),
        'license_review_id': artifact.get('license_review_id'),
        'metrics': _json_safe_metrics(metrics),
        'scene_breakdown': scene_breakdown,
        'region_breakdown': artifact.get('region_breakdown') or _region_breakdown_from_scenes(scene_breakdown),
        'coverage': _prediction_coverage(records, expected_scene_ids, actual_scene_ids, missing),
        'quality_gate': artifact.get('quality_gate'),
    }


def _sar_prediction_report_from_mask_rows(
    source_key: str,
    records: list[dict[str, Any]],
    artifact: dict[str, Any],
    rows: list[Any],
) -> dict[str, Any]:
    threshold = float(_coerce_float(artifact.get('threshold')) or 0.5)
    valid_rows = [row for row in rows if isinstance(row, dict)]
    expected_scene_ids = _expected_prediction_scene_ids(artifact) or sorted({
        str(row.get('scene_id') or '').strip()
        for row in valid_rows
        if row.get('scene_id')
    })
    actual_scene_ids = sorted({
        str(row.get('scene_id') or '').strip()
        for row in valid_rows
        if row.get('scene_id') and (row.get('prediction_mask_ref') or row.get('prediction_mask'))
    })
    missing = sorted(set(expected_scene_ids) - set(actual_scene_ids))
    if missing:
        return _pending_sar_prediction_report(
            artifact,
            reason='SAR prediction artifact is missing one or more declared validation scenes.',
            expected_scene_ids=expected_scene_ids,
            actual_scene_ids=actual_scene_ids,
            missing_scene_ids=missing,
        )

    try:
        metrics, scene_breakdown = _compute_mask_row_metrics(valid_rows, threshold=threshold)
    except Exception as exc:
        return _pending_sar_prediction_report(
            artifact,
            reason=f'SAR prediction artifact masks could not be evaluated: {exc}',
            expected_scene_ids=expected_scene_ids,
            actual_scene_ids=actual_scene_ids,
        )

    return {
        'status': 'computed',
        'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
        'source_key': source_key,
        'dataset_version': artifact.get('dataset_version'),
        'model_family': artifact.get('model_family'),
        'model_version': artifact.get('model_version') or artifact.get('candidate_model_version'),
        'split': artifact.get('split') or 'val',
        'threshold': threshold,
        'license_review_id': artifact.get('license_review_id'),
        'metrics': metrics,
        'scene_breakdown': scene_breakdown,
        'region_breakdown': _region_breakdown_from_scenes(scene_breakdown),
        'coverage': _prediction_coverage(records, expected_scene_ids, actual_scene_ids, missing),
    }


def _compute_mask_row_metrics(rows: list[dict[str, Any]], *, threshold: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from backend.sar_unet_worker import _load_mask_array, compute_mask_metrics

    prediction_masks = []
    truth_masks = []
    scene_breakdown = []
    for row in rows:
        prediction_ref = row.get('prediction_mask_ref') or row.get('prediction_mask')
        truth_ref = row.get('truth_mask_ref') or row.get('truth_mask')
        if not prediction_ref or not truth_ref:
            continue
        prediction = _load_mask_array(prediction_ref) >= threshold
        truth = _load_mask_array(truth_ref) >= 0.5
        prediction_masks.append(prediction)
        truth_masks.append(truth)
        scene_metrics = compute_mask_metrics([prediction], [truth])
        scene_breakdown.append({
            'scene_id': str(row.get('scene_id') or row.get('event_id') or ''),
            'region_key': str(row.get('region_key') or 'unknown'),
            **scene_metrics,
        })
    metrics = compute_mask_metrics(prediction_masks, truth_masks)
    return metrics, scene_breakdown


def _expected_prediction_scene_ids(artifact: dict[str, Any]) -> list[str]:
    values = artifact.get('evaluated_scene_ids') or artifact.get('val_events') or artifact.get('validation_scene_ids') or []
    if not isinstance(values, list):
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _pending_sar_prediction_report(
    artifact: dict[str, Any],
    *,
    reason: str,
    expected_scene_ids: list[str] | None = None,
    actual_scene_ids: list[str] | None = None,
    missing_scene_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        'status': 'pending_predictions',
        'reason': reason,
        'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
        'source_key': artifact.get('source_key'),
        'dataset_version': artifact.get('dataset_version'),
        'model_family': artifact.get('model_family'),
        'model_version': artifact.get('model_version') or artifact.get('candidate_model_version'),
        'split': artifact.get('split') or 'val',
        'license_review_id': artifact.get('license_review_id'),
        'coverage': {
            'expected_scene_ids': expected_scene_ids or _expected_prediction_scene_ids(artifact),
            'predicted_scene_ids': actual_scene_ids or [],
            'missing_scene_ids': missing_scene_ids or [],
        },
    }


def _prediction_coverage(
    records: list[dict[str, Any]],
    expected_scene_ids: list[str],
    actual_scene_ids: list[str],
    missing_scene_ids: list[str],
) -> dict[str, Any]:
    staged_scene_ids = sorted({_record_scene_id(record) for record in records if _record_scene_id(record)})
    return {
        'staged_scene_count': len(staged_scene_ids),
        'staged_scene_ids': staged_scene_ids,
        'expected_scene_ids': expected_scene_ids,
        'predicted_scene_ids': actual_scene_ids,
        'missing_scene_ids': missing_scene_ids,
        'coverage_complete': not missing_scene_ids,
    }


def _record_scene_id(record: dict[str, Any]) -> str:
    return str(record.get('external_id') or record.get('event_id') or record.get('id') or '').strip()


def _has_confusion_counts(metrics: dict[str, Any]) -> bool:
    return all(key in metrics for key in ('tp', 'fp', 'fn', 'tn'))


def _aggregate_scene_counts(scene_breakdown: list[dict[str, Any]]) -> dict[str, int] | None:
    if not scene_breakdown:
        return None
    counts = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
    for scene in scene_breakdown:
        if not _has_confusion_counts(scene):
            return None
        for key in counts:
            counts[key] += int(scene.get(key) or 0)
    return counts


def _region_breakdown_from_scenes(scene_breakdown: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    region_counts: dict[str, dict[str, int]] = {}
    for scene in scene_breakdown:
        if not _has_confusion_counts(scene):
            continue
        region = str(scene.get('region_key') or 'unknown')
        counts = region_counts.setdefault(region, {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0})
        for key in counts:
            counts[key] += int(scene.get(key) or 0)
    return {
        region: _metrics_from_counts(counts)
        for region, counts in sorted(region_counts.items())
    }


def _metrics_from_counts(counts: dict[str, int]) -> dict[str, Any]:
    tp = int(counts.get('tp') or 0)
    fp = int(counts.get('fp') or 0)
    fn = int(counts.get('fn') or 0)
    tn = int(counts.get('tn') or 0)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2.0 * precision * recall) / max(precision + recall, 1e-9)
    iou = tp / max(tp + fp + fn, 1)
    false_positive_rate = fp / max(fp + tn, 1)
    return {
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'tn': tn,
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1),
        'iou': float(iou),
        'false_positive_rate': float(false_positive_rate),
    }


def _json_safe_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metrics.items():
        if key in {'tp', 'fp', 'fn', 'tn'}:
            safe[key] = int(value or 0)
        elif isinstance(value, (int, float)):
            safe[key] = float(value)
        elif value is None or isinstance(value, str):
            safe[key] = value
    return safe


def _promotion_blockers(source_reports: list[dict[str, Any]]) -> list[str]:
    blockers = [
        'production scoring is intentionally disabled for European shadow sources',
        'current RF baseline comparison has not been beaten by a reviewed European shadow candidate',
        'non-European local validation non-regression evidence is not attached',
    ]
    if any(report.get('benchmark_status', {}).get('status') == 'pending_predictions' for report in source_reports):
        blockers.append('one or more source families are staged but still missing model prediction benchmarks')
    if any(not str(report.get('license_review_id') or '').strip() for report in source_reports):
        blockers.append('one or more staged sources are missing license_review_id')
    return blockers


def _summary_by_lane(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for record in records:
        lane = str(record.get('data_lane') or 'unknown')
        entry = lanes.setdefault(lane, {
            'record_count': 0,
            'source_keys': set(),
            'training_eligible_record_count': 0,
            'production_eligible_record_count': 0,
        })
        entry['record_count'] += 1
        entry['source_keys'].add(str(record.get('source_key') or 'unknown'))
        if record.get('training_eligible'):
            entry['training_eligible_record_count'] += 1
        if record.get('production_eligible'):
            entry['production_eligible_record_count'] += 1
    return {
        lane: {
            **{key: value for key, value in entry.items() if key != 'source_keys'},
            'source_keys': sorted(entry['source_keys']),
        }
        for lane, entry in sorted(lanes.items())
    }


def _counts_by_month(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        event_time = str(record.get('event_time') or '').strip()
        if len(event_time) >= 7:
            counts[event_time[:7]] += 1
        else:
            counts['unknown'] += 1
    return dict(sorted(counts.items()))


def _metadata_counts(metadata_items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for metadata in metadata_items:
        value = metadata.get(key)
        if value not in (None, ''):
            counts[str(value)] += 1
    return dict(sorted(counts.items()))


def _metadata_positive_count(metadata_items: list[dict[str, Any]], keys: tuple[str, ...]) -> int:
    count = 0
    for metadata in metadata_items:
        for key in keys:
            value = _coerce_float(metadata.get(key))
            if value is not None and value > 0:
                count += 1
                break
    return count


def _distinct_metadata_count(metadata_items: list[dict[str, Any]], keys: tuple[str, ...]) -> int:
    values = set()
    for metadata in metadata_items:
        for key in keys:
            value = metadata.get(key)
            if value not in (None, ''):
                values.add(str(value))
    return len(values)


def _asset_ref(record: dict[str, Any], key: str) -> str:
    asset_refs = record.get('asset_refs') if isinstance(record.get('asset_refs'), dict) else {}
    return str(asset_refs.get(key) or record.get(key) or '').strip()


def _coerce_float(value: Any) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snapshot_from_manifests(manifests: list[dict[str, Any]]) -> str:
    values = [str(manifest.get('snapshot_id') or '').strip() for manifest in manifests if manifest.get('snapshot_id')]
    return values[0] if values else f'european-shadow-benchmark-{datetime.now(timezone.utc).date().isoformat()}'
