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


def load_staging_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'staging manifest must be a JSON object: {path}')
    return payload


def build_european_shadow_benchmark_report(
    *,
    staging_manifests: Iterable[dict[str, Any]],
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    manifests = list(staging_manifests)
    source_reports = []
    all_records: list[dict[str, Any]] = []
    for manifest in manifests:
        records = load_staged_records(manifest)
        all_records.extend(records)
        source_reports.append(_source_report(manifest, records))

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


def _source_report(manifest: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    source = manifest.get('source') if isinstance(manifest.get('source'), dict) else {}
    source_key = str(manifest.get('source_key') or source.get('source_key') or '').strip()
    data_lane = str(source.get('data_lane') or '').strip()
    metadata_items = [record.get('metadata') for record in records if isinstance(record.get('metadata'), dict)]
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
        'benchmark_status': _benchmark_status_for_lane(data_lane),
        'bias_audits': _bias_audits(source_key, data_lane, metadata_items),
        'sar_training_manifest_path': manifest.get('sar_training_manifest_path'),
        'sar_training_manifest_scene_count': manifest.get('sar_training_manifest_scene_count') or 0,
    }
    report.update(_lane_specific_metrics(source_key, data_lane, records, metadata_items))
    return report


def _benchmark_status_for_lane(data_lane: str) -> dict[str, Any]:
    if data_lane in SAR_MANIFEST_LANES:
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
                'caught_record_count': _metadata_present_count(metadata_items, ('caught_count',)),
                'fatality_record_count': _metadata_present_count(metadata_items, ('dead_count', 'fatality_count')),
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
        return {
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


def _metadata_present_count(metadata_items: list[dict[str, Any]], keys: tuple[str, ...]) -> int:
    return sum(1 for metadata in metadata_items if any(metadata.get(key) not in (None, '') for key in keys))


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
