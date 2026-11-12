"""Audit an existing training artifact before spending another training run.

The audit is intentionally metadata-only.  It does not query Supabase, call
Open-Meteo, load a joblib model, or mutate an artifact directory.  That makes
it safe to run as a cheap preflight before a scheduled or manual train job.

The report separates evidence that is present in the artifact from evidence
that is still missing.  Current training runs persist the row-level snapshot
and split evidence, while legacy artifacts may predate those fields.  A
passing model metric is not treated as proof of temporal or spatial
generalisation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.common.label_time_contract import (
    EXACT_OCCURRENCE_TIME_REVIEW_STATUS,
    EXACT_OCCURRENCE_TIME_SEMANTICS,
    LABEL_TIME_CONTRACT_EXACT_V1,
    LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
    SUPPORTED_LABEL_TIME_CONTRACTS,
    has_approved_occurrence_time_review,
    inspect_label_time_row,
    normalise_contract,
    validate_label_time_rows,
)
from backend.common.interval_source_adapter import (
    INTERVAL_LABEL_STAGING_SCHEMA_VERSION,
    REVIEWED_LICENSE_STATUSES,
)
from backend.common.interval_training_contract import INTERVAL_TRAINING_PATH_STATUS
from backend.common.interval_training_preparation import (
    validate_interval_training_preparation_manifest,
)
from backend.common.station_free_feature_snapshot import load_station_free_feature_snapshot
from backend.scripts.validate_mvp4_source_manifest import validate_source_manifest


AUDIT_VERSION = 'training_dataset_audit_v1'
PREFLIGHT_VERSION = 'training_preflight_v1'
ROBUSTNESS_PSS_FLOOR = 0.45
MIN_TEMPORAL_SPAN_DAYS = 30.0
MAX_TERRAIN_LOSS_RATE = 0.02
_TIMESTAMPED_ARTIFACT = re.compile(r'^\d{8}T\d{6}Z$')
MINIMUM_POSITIVE_SEASONS = 3
MINIMUM_POSITIVE_SOURCES = 2
MINIMUM_POSITIVE_EVENT_GROUPS = 30
MINIMUM_ORIGIN_SOURCE_FAMILIES = 2
EXACT_TIMESTAMP_PRECISIONS = {'timestamp', 'instant', 'exact_timestamp'}
GEE_SAR_APPROVED_OCCURRENCE_TIME_SEMANTICS = 'independent_observed_occurrence_time'
GEE_SAR_APPROVED_OCCURRENCE_TIME_REVIEW_STATUS = 'approved_occurrence_time'
GEE_SCENE_AWARE_SHADOW_SNAPSHOT_SCHEMA = 'mvp4_gee_scene_aware_interval_snapshot_v1'
SUPPORTED_REVIEWED_SNAPSHOT_SCHEMAS = {
    'mvp4_bipad_candidate_snapshot_v1',
    'mvp4_hiaval_snapshot_v1',
    'mvp4_reviewed_hma_catalog_v1',
    INTERVAL_LABEL_STAGING_SCHEMA_VERSION,
    GEE_SCENE_AWARE_SHADOW_SNAPSHOT_SCHEMA,
}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _count(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number >= 0 else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def _finding(
    finding_id: str,
    severity: str,
    title: str,
    evidence: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    return {
        'id': finding_id,
        'severity': severity,
        'title': title,
        'evidence': evidence,
        'required_action': action,
    }


def _source_shares(source_counts: dict[str, Any], denominator: int | None) -> dict[str, float]:
    total = sum(_count(value) or 0 for value in source_counts.values())
    if not total and denominator:
        total = denominator
    if not total:
        return {}
    return {
        str(source): round((_count(value) or 0) / total, 6)
        for source, value in sorted(source_counts.items())
    }


def _phase_metrics(stage_metrics: dict[str, Any] | None, training_metrics: dict[str, Any] | None) -> dict[str, float]:
    phase = stage_metrics.get('phase_breakdown_seconds') if isinstance(stage_metrics, dict) else None
    if not isinstance(phase, dict):
        summary = training_metrics.get('latest_benchmark_summary') if isinstance(training_metrics, dict) else None
        phase = summary.get('phase_breakdown_seconds') if isinstance(summary, dict) else None
    if not isinstance(phase, dict):
        return {}
    return {
        str(key): float(value)
        for key, value in phase.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) >= 0
    }


def _row_field(row: dict[str, Any], key: str) -> Any:
    """Read a provenance field from the normalized row or its source metadata."""
    direct = row.get(key)
    if direct is not None and str(direct).strip():
        return direct
    for container_key in ('metadata', 'features'):
        container = row.get(container_key)
        if isinstance(container, dict):
            value = container.get(key)
            if value is not None and str(value).strip():
                return value
    return None


def _gee_sar_exact_time_reviewed(
    row: dict[str, Any],
    *,
    source_manifest: dict[str, Any] | None = None,
) -> bool:
    """Require explicit occurrence-time review before treating GEE time as exact."""
    return has_approved_occurrence_time_review(
        row,
        source_manifest=source_manifest,
    )


def _source_manifest_for_row(
    row: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    source_key = str(
        row.get('source_key')
        or row.get('source')
        or row.get('label_source')
        or ''
    ).strip()
    source_manifests = manifest.get('source_manifests')
    if isinstance(source_manifests, dict):
        source_manifest = source_manifests.get(source_key)
        if isinstance(source_manifest, dict):
            return source_manifest
    return manifest


def _source_request_gate(
    source_request_manifest_path: Path | None,
    *,
    source_request_payload_path: Path | None = None,
    source_request_events_path: Path | None = None,
) -> dict[str, Any]:
    """Validate an optional source-owner package before snapshot preflight.

    The existing reviewed-snapshot gate remains authoritative for the training
    frame.  This additional gate is used when a new source-owner package is
    being introduced; it prevents a pending or mismatched raw package from
    being treated as a reviewed source merely because a snapshot path exists.
    """
    supplied_paths = (
        source_request_manifest_path,
        source_request_payload_path,
        source_request_events_path,
    )
    if not any(path is not None for path in supplied_paths):
        return {
            'required': False,
            'passed': True,
            'decision': 'not_supplied',
            'manifest_path': None,
            'payload_path': None,
            'events_path': None,
            'errors': [],
        }

    manifest_path = (
        Path(source_request_manifest_path).expanduser()
        if source_request_manifest_path is not None
        else None
    )
    payload_path = (
        Path(source_request_payload_path).expanduser()
        if source_request_payload_path is not None
        else None
    )
    events_path = (
        Path(source_request_events_path).expanduser()
        if source_request_events_path is not None
        else None
    )
    base = {
        'required': True,
        'passed': False,
        'manifest_path': str(manifest_path) if manifest_path else None,
        'payload_path': str(payload_path) if payload_path else None,
        'events_path': str(events_path) if events_path else None,
    }
    if manifest_path is None:
        return {
            **base,
            'decision': 'blocked_invalid_source_manifest',
            'errors': ['source request manifest is required when a source payload or events JSONL is supplied'],
        }
    manifest = _load_json(manifest_path)
    if manifest is None:
        return {
            **base,
            'decision': 'blocked_invalid_source_manifest',
            'errors': ['source request manifest is missing or invalid JSON'],
        }
    report = validate_source_manifest(
        manifest,
        payload_path=payload_path,
        events_path=events_path,
    )
    return {
        **base,
        **report,
    }


def _reviewed_snapshot_gate(
    snapshot_manifest_path: Path | None,
    *,
    selected_region_keys: list[str] | None = None,
    label_time_contract: str = LABEL_TIME_CONTRACT_EXACT_V1,
    require_feature_cutoff: bool = True,
) -> dict[str, Any]:
    """Validate a reviewed open-source snapshot without network/model I/O."""
    requested_contract = normalise_contract(label_time_contract)
    if snapshot_manifest_path is None:
        return {
            'passed': False,
            'manifest_path': None,
            'label_time_contract': requested_contract or label_time_contract,
            'errors': ['reviewed snapshot manifest is required'],
        }
    path = Path(snapshot_manifest_path).expanduser()
    manifest = _load_json(path)
    if manifest is None:
        return {
            'passed': False,
            'manifest_path': str(path),
            'label_time_contract': requested_contract or label_time_contract,
            'errors': ['reviewed snapshot manifest is missing or invalid JSON'],
        }
    snapshot_schema = str(manifest.get('snapshot_schema_version') or '').strip()
    is_reviewed_catalog = snapshot_schema == 'mvp4_reviewed_hma_catalog_v1'
    is_interval_staging = snapshot_schema == INTERVAL_LABEL_STAGING_SCHEMA_VERSION
    is_gee_scene_shadow = snapshot_schema == GEE_SCENE_AWARE_SHADOW_SNAPSHOT_SCHEMA
    errors: list[str] = []
    if requested_contract is None:
        errors.append(
            f'unsupported label time contract: {label_time_contract}; '
            f'expected one of {sorted(SUPPORTED_LABEL_TIME_CONTRACTS)}'
        )
        requested_contract = str(label_time_contract)
    declared_contract = normalise_contract(manifest.get('label_time_contract'))
    if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
        if declared_contract != requested_contract:
            errors.append(
                'interval-censored preflight requires snapshot label_time_contract='
                f'{LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1}'
            )
    elif declared_contract is not None and declared_contract != requested_contract:
        errors.append(
            f'snapshot label_time_contract {declared_contract} does not match '
            f'the requested contract {requested_contract}'
        )
    if snapshot_schema not in SUPPORTED_REVIEWED_SNAPSHOT_SCHEMAS:
        errors.append('unsupported reviewed snapshot schema')
    if is_reviewed_catalog:
        source_manifests = manifest.get('source_manifests')
        if not isinstance(source_manifests, dict) or not source_manifests:
            errors.append('reviewed catalog source_manifests is missing')
        else:
            for source_key, source_manifest in sorted(source_manifests.items()):
                if not isinstance(source_manifest, dict):
                    errors.append(f'reviewed catalog source manifest is invalid: {source_key}')
                    continue
                if source_manifest.get('license_status') != 'permissive_core_reviewed':
                    errors.append(f'reviewed catalog source license is not core-reviewed: {source_key}')
                if source_manifest.get('training_eligible') is not True:
                    errors.append(f'reviewed catalog source is not training-eligible: {source_key}')
                source_manifest_ref = source_manifest.get('snapshot_manifest')
                if not isinstance(source_manifest_ref, str) or not source_manifest_ref.strip():
                    errors.append(f'reviewed catalog source snapshot reference is missing: {source_key}')
                else:
                    raw_ref = Path(source_manifest_ref).expanduser()
                    candidates = [raw_ref]
                    if not raw_ref.is_absolute():
                        candidates.extend((path.parent / raw_ref, Path.cwd() / raw_ref))
                    nested_path = next((candidate for candidate in candidates if candidate.is_file()), None)
                    nested = _load_json(nested_path) if nested_path is not None else None
                    if nested is None:
                        errors.append(f'reviewed catalog source snapshot is missing or invalid: {source_key}')
                    else:
                        nested_events_ref = nested.get('events_path')
                        nested_events_path = (
                            nested_path.parent / str(nested_events_ref)
                            if isinstance(nested_events_ref, str) and nested_events_ref
                            else None
                        )
                        nested_hash = None
                        if nested_events_path is None or not nested_events_path.is_file():
                            errors.append(f'reviewed catalog source events are missing: {source_key}')
                        else:
                            nested_hash = hashlib.sha256(nested_events_path.read_bytes()).hexdigest()
                            if nested.get('event_rows_sha256') != nested_hash:
                                errors.append(f'reviewed catalog nested source hash is invalid: {source_key}')
                        if source_manifest.get('event_rows_sha256') != nested_hash:
                            errors.append(f'reviewed catalog source hash does not match nested manifest: {source_key}')
        if not str(manifest.get('review_status') or '').lower().startswith('reviewed'):
            errors.append('reviewed catalog review_status is not reviewed')
        bounded_count = _count(manifest.get('bounded_interval_record_count'))
        if (
            bounded_count
            and bounded_count > 0
            and requested_contract == LABEL_TIME_CONTRACT_EXACT_V1
        ):
            errors.append(
                f'reviewed catalog contains {bounded_count} bounded interval records; '
                'exact-time core training requires zero'
            )
    elif is_interval_staging:
        if declared_contract != LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
            errors.append(
                'interval label staging requires label_time_contract='
                f'{LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1}'
            )
        if manifest.get('staging_only') is not True:
            errors.append('interval label staging must remain staging_only')
        if str(manifest.get('review_status') or '').strip().lower() != 'reviewed_interval_staging':
            errors.append('interval label staging review_status is not reviewed_interval_staging')
        source_manifests = manifest.get('source_manifests')
        if not isinstance(source_manifests, dict) or len(source_manifests) < MINIMUM_POSITIVE_SOURCES:
            errors.append('interval label staging needs two reviewed source manifests')
        else:
            for source_key, source_manifest in sorted(source_manifests.items()):
                if not isinstance(source_manifest, dict):
                    errors.append(f'interval staging source manifest is invalid: {source_key}')
                    continue
                if source_manifest.get('license_status') not in REVIEWED_LICENSE_STATUSES:
                    errors.append(f'interval staging source license is not reviewed: {source_key}')
                if not str(source_manifest.get('license_review_id') or '').strip():
                    errors.append(f'interval staging source license_review_id is missing: {source_key}')
                source_hash = str(source_manifest.get('event_rows_sha256') or '').strip()
                if len(source_hash) != 64 or any(character not in '0123456789abcdef' for character in source_hash.lower()):
                    errors.append(f'interval staging source event hash is invalid: {source_key}')
        if manifest.get('interval_training_ready') is not True:
            errors.append('interval staging feature snapshot is not ready for interval training')
    elif is_gee_scene_shadow:
        if requested_contract != LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
            errors.append(
                'GEE scene-aware shadow snapshot is interval-only; '
                'it cannot satisfy the exact-time core contract'
            )
        if manifest.get('shadow_only') is not True:
            errors.append('GEE scene-aware shadow snapshot must declare shadow_only=true')
        if manifest.get('core_training_eligible') is not False:
            errors.append('GEE scene-aware shadow snapshot core_training_eligible must remain false')
        if manifest.get('production_scoring_eligible') is not False:
            errors.append('GEE scene-aware shadow snapshot production_scoring_eligible must remain false')
        if manifest.get('license_status') not in REVIEWED_LICENSE_STATUSES:
            errors.append('GEE scene-aware shadow snapshot license is not reviewed')
        if not str(manifest.get('license_review_id') or '').strip():
            errors.append('GEE scene-aware shadow snapshot license_review_id is missing')
        review_status = str(manifest.get('review_status') or '').strip().lower()
        if not review_status.startswith('reviewed'):
            errors.append('GEE scene-aware shadow snapshot review_status is not reviewed')
        scenes_ref = manifest.get('source_scenes_path')
        scenes_path = path.parent / str(scenes_ref) if isinstance(scenes_ref, str) and scenes_ref else None
        if scenes_path is None or not scenes_path.is_file():
            errors.append('GEE scene-aware shadow snapshot source_scenes_path is missing')
        else:
            declared_scene_hash = str(manifest.get('scene_manifest_sha256') or '').strip()
            actual_scene_hash = hashlib.sha256(scenes_path.read_bytes()).hexdigest()
            if not declared_scene_hash or declared_scene_hash != actual_scene_hash:
                errors.append('GEE scene-aware shadow snapshot scene_manifest_sha256 does not match source_scenes_path')
        if (_count(manifest.get('bounded_interval_record_count')) or 0) <= 0:
            errors.append('GEE scene-aware shadow snapshot must contain bounded interval records')
        if (_count(manifest.get('exact_timestamp_record_count')) or 0) != 0:
            errors.append('GEE scene-aware shadow snapshot must not declare exact occurrence timestamps')
    else:
        if manifest.get('license_status') != 'permissive_core_reviewed':
            errors.append('snapshot license status is not permissive_core_reviewed')
        if not str(manifest.get('license_review_id') or '').strip():
            errors.append('snapshot license_review_id is missing')
    if manifest.get('training_eligible') is not True:
        errors.append('snapshot is not marked training_eligible')
    if manifest.get('production_scoring_eligible') is not False:
        errors.append('snapshot production_scoring_eligible must remain false')

    requested_regions = sorted({str(value).strip() for value in (selected_region_keys or []) if str(value).strip()})
    events_path_value = manifest.get('events_path')
    events_path = path.parent / str(events_path_value) if isinstance(events_path_value, str) and events_path_value else None
    event_records: list[dict[str, Any]] = []
    if events_path is None or not events_path.is_file():
        errors.append('snapshot events_path is missing')
    else:
        expected_hash = str(manifest.get('event_rows_sha256') or '').strip()
        actual_hash = hashlib.sha256(events_path.read_bytes()).hexdigest()
        if not expected_hash or expected_hash != actual_hash:
            errors.append('snapshot event_rows_sha256 does not match events_path')
        try:
            for line in events_path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError('event row is not an object')
                    event_records.append(record)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            errors.append('snapshot events_path is not valid JSONL')

    positive_seasons = manifest.get('positive_season_ids')
    if not isinstance(positive_seasons, list) or len(set(map(str, positive_seasons))) < MINIMUM_POSITIVE_SEASONS:
        errors.append(f'snapshot needs at least {MINIMUM_POSITIVE_SEASONS} positive seasons')
    required_sources = manifest.get('required_independent_positive_sources')
    if not isinstance(required_sources, list) or len(set(map(str, required_sources))) < MINIMUM_POSITIVE_SOURCES:
        errors.append(f'snapshot needs at least {MINIMUM_POSITIVE_SOURCES} independent positive sources')
    positive_records = [row for row in event_records if row.get('label') in (1, True)]
    gee_sar_exact_rows = [
        row
        for row in positive_records
        if str(
            row.get('source_key')
            or row.get('source')
            or row.get('label_source')
            or ''
        ).strip().lower() == 'gee_sar'
        and str(row.get('timestamp_precision') or '').strip().lower() in EXACT_TIMESTAMP_PRECISIONS
    ]
    exact_timestamp_rows = [
        row
        for row in positive_records
        if str(row.get('timestamp_precision') or '').strip().lower() in EXACT_TIMESTAMP_PRECISIONS
    ]
    unreviewed_exact_rows = [
        row
        for row in exact_timestamp_rows
        if not has_approved_occurrence_time_review(
            row,
            source_manifest=_source_manifest_for_row(row, manifest),
        )
    ]
    unreviewed_non_gee_exact_rows = [
        row
        for row in unreviewed_exact_rows
        if str(
            row.get('source_key')
            or row.get('source')
            or row.get('label_source')
            or ''
        ).strip().lower() != 'gee_sar'
    ]
    if unreviewed_non_gee_exact_rows:
        errors.append(
            f'{len(unreviewed_non_gee_exact_rows)} exact timestamp rows lack explicit '
            'occurrence-time review; exact source times require approved occurrence-time '
            'semantics and a review ID'
        )
    gee_sar_unreviewed_exact_rows = [
        row
        for row in gee_sar_exact_rows
        if not _gee_sar_exact_time_reviewed(
            row,
            source_manifest=_source_manifest_for_row(row, manifest),
        )
    ]
    if gee_sar_unreviewed_exact_rows:
        errors.append(
            f'{len(gee_sar_unreviewed_exact_rows)} gee_sar exact timestamp rows lack explicit '
            'occurrence-time review; Sentinel sensing time cannot be treated as avalanche '
            'occurrence time without approved occurrence-time semantics and review ID'
        )
    event_group_ids = {
        str(row.get('event_group_id') or '').strip()
        for row in positive_records
        if str(row.get('event_group_id') or '').strip()
    }
    missing_event_group_count = sum(
        1 for row in positive_records if not str(row.get('event_group_id') or '').strip()
    )
    if missing_event_group_count:
        errors.append(f'{missing_event_group_count} positive snapshot rows are missing event_group_id')
    if len(event_group_ids) < MINIMUM_POSITIVE_EVENT_GROUPS:
        errors.append(
            f'snapshot needs at least {MINIMUM_POSITIVE_EVENT_GROUPS} deduplicated positive event groups; '
            f'found {len(event_group_ids)}'
        )
    origin_source_families = {
        str(row.get('origin_source_family') or '').strip()
        for row in positive_records
        if str(row.get('origin_source_family') or '').strip()
    }
    missing_origin_family_count = sum(
        1 for row in positive_records if not str(row.get('origin_source_family') or '').strip()
    )
    if missing_origin_family_count:
        errors.append(
            f'{missing_origin_family_count} positive snapshot rows are missing origin_source_family'
        )
    if len(origin_source_families) < MINIMUM_ORIGIN_SOURCE_FAMILIES:
        errors.append(
            f'snapshot needs at least {MINIMUM_ORIGIN_SOURCE_FAMILIES} independent origin source families; '
            f'found {len(origin_source_families)}'
        )
    target_regions = manifest.get('target_regions')
    if is_reviewed_catalog and (not isinstance(target_regions, dict) or not target_regions):
        regions_by_season = manifest.get('positive_seasons_by_region')
        season_months = manifest.get('region_season_start_months')
        if isinstance(regions_by_season, dict):
            target_regions = {
                str(region_key): {
                    'season_start_month': int((season_months or {}).get(region_key, 11) or 11)
                    if isinstance(season_months, dict) else 11,
                }
                for region_key in regions_by_season
            }
    if not isinstance(target_regions, dict) or not target_regions:
        errors.append('snapshot target_regions is missing')

    label_time_validation: dict[str, Any] | None = None
    row_inspections: dict[int, dict[str, Any]] = {}
    if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
        label_time_validation = validate_label_time_rows(
            event_records,
            contract=requested_contract,
            require_feature_cutoff=require_feature_cutoff,
            include_row_inspections=True,
        )
        row_inspections = {
            int(inspection['row_index']): inspection
            for inspection in label_time_validation.get('row_inspections', [])
        }
        label_time_validation = {
            key: value
            for key, value in label_time_validation.items()
            if key != 'row_inspections'
        }
        if not label_time_validation['passed']:
            errors.append(
                'label time contract has '
                f"{label_time_validation['invalid_row_count']} invalid rows: "
                f"{', '.join(f'{key}={value}' for key, value in label_time_validation['error_counts'].items())}"
            )

    region_checks: dict[str, Any] = {}
    if requested_regions:
        target_regions = target_regions if isinstance(target_regions, dict) else {}
        season_months = manifest.get('region_season_start_months') if isinstance(manifest.get('region_season_start_months'), dict) else {}
        for region_key in requested_regions:
            region_rows = [
                row for row in event_records
                if str(row.get('region_key') or '').strip() == region_key
                and row.get('label') in (1, True)
            ]
            def _row_source_id(row: dict[str, Any]) -> str:
                return str(
                    row.get('source_key')
                    or row.get('source')
                    or row.get('label_source')
                    or ''
                ).strip()

            row_indices_by_identity = {
                id(row): index for index, row in enumerate(event_records)
            }

            def _row_inspection(row: dict[str, Any]) -> dict[str, Any] | None:
                return row_inspections.get(row_indices_by_identity.get(id(row), -1))

            def _row_precision(row: dict[str, Any]) -> str:
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
                    inspection = _row_inspection(row)
                    return str((inspection or {}).get('precision') or 'unknown')
                return str(row.get('timestamp_precision') or 'unknown').strip().lower() or 'unknown'

            def _has_exact_timestamp(row: dict[str, Any]) -> bool:
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
                    inspection = _row_inspection(row)
                    return bool(inspection and inspection.get('valid') and inspection.get('precision') == 'exact')
                precision = _row_precision(row)
                if precision not in EXACT_TIMESTAMP_PRECISIONS:
                    return False
                return _timestamp(row.get('event_time') or row.get('timestamp')) is not None

            def _has_bounded_interval(row: dict[str, Any]) -> bool:
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
                    inspection = _row_inspection(row)
                    return bool(
                        inspection
                        and inspection.get('valid')
                        and inspection.get('precision') in {'day', 'interval'}
                    )
                start = _timestamp(row.get('event_time_start') or row.get('timestamp_start'))
                end = _timestamp(row.get('event_time_end') or row.get('timestamp_end'))
                precision = _row_precision(row)
                return (
                    start is not None
                    and end is not None
                    and start <= end
                ) or precision.startswith(('bounded', 'interval', 'range'))

            exact_rows = [row for row in region_rows if _has_exact_timestamp(row)]
            bounded_rows = [row for row in region_rows if not _has_exact_timestamp(row) and _has_bounded_interval(row)]
            unusable_rows = [row for row in region_rows if row not in exact_rows and row not in bounded_rows]
            exact_source_ids = sorted({source for source in (_row_source_id(row) for row in exact_rows) if source})
            bounded_source_ids = sorted({source for source in (_row_source_id(row) for row in bounded_rows) if source})
            start_month = int(season_months.get(region_key, 11) or 11)
            season_ids: set[str] = set()
            season_rows = exact_rows + bounded_rows if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1 else exact_rows
            for row in season_rows:
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
                    inspection = _row_inspection(row) or {}
                    parsed = _timestamp(inspection.get('interval_start'))
                else:
                    parsed = _timestamp(row.get('event_time') or row.get('timestamp'))
                if parsed is None:
                    continue
                season_year = parsed.year if parsed.month >= start_month else parsed.year - 1
                season_ids.add(f'{season_year}-{season_year + 1}')
            precision_counts: dict[str, int] = {}
            for row in region_rows:
                precision = _row_precision(row)
                precision_counts[precision] = precision_counts.get(precision, 0) + 1
            eligible_rows = (
                exact_rows + bounded_rows
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
                else exact_rows
            )
            eligible_source_ids = sorted({
                source for source in (_row_source_id(row) for row in eligible_rows) if source
            })
            region_checks[region_key] = {
                'target_region_present': region_key in target_regions,
                'positive_row_count': len(region_rows),
                'exact_positive_row_count': len(exact_rows),
                'bounded_positive_row_count': len(bounded_rows),
                'unusable_positive_row_count': len(unusable_rows),
                'positive_season_ids': sorted(season_ids),
                'positive_source_ids': eligible_source_ids,
                'exact_positive_source_ids': exact_source_ids,
                'bounded_positive_source_ids': bounded_source_ids,
                'interval_positive_source_ids': eligible_source_ids if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1 else [],
                'timestamp_precision_counts': precision_counts,
                'season_start_month': start_month,
                'label_time_contract': requested_contract,
            }
            if region_key not in target_regions:
                errors.append(f'snapshot does not cover selected training region: {region_key}')
            if len(season_ids) < MINIMUM_POSITIVE_SEASONS:
                errors.append(
                    f'selected region {region_key} needs at least {MINIMUM_POSITIVE_SEASONS} positive seasons'
                )
            source_ids_for_contract = (
                eligible_source_ids
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
                else exact_source_ids
            )
            if len(source_ids_for_contract) < MINIMUM_POSITIVE_SOURCES:
                if requested_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
                    errors.append(
                        f'selected region {region_key} needs at least {MINIMUM_POSITIVE_SOURCES} '
                        'independent positive sources under the interval-censored contract'
                    )
                elif bounded_source_ids:
                    errors.append(
                        f'selected region {region_key} has only {len(exact_source_ids)} exact-time '
                        'independent positive sources; bounded interval sources are not eligible for '
                        f'exact-time training: {bounded_source_ids}'
                    )
                else:
                    errors.append(
                        f'selected region {region_key} needs at least {MINIMUM_POSITIVE_SOURCES} '
                        'exact-time independent positive sources'
                    )

    overlap_value = manifest.get('source_overlap_report')
    overlap_path = path.parent / str(overlap_value) if isinstance(overlap_value, str) and overlap_value else None
    overlap = _load_json(overlap_path) if overlap_path is not None else None
    if overlap is None:
        errors.append('source overlap report is missing or invalid')
    elif overlap.get('status') != 'reviewed':
        errors.append(f"source overlap report is not reviewed: {overlap.get('status') or 'unknown'}")
    else:
        declared_overlap_hash = str(manifest.get('source_overlap_report_sha256') or '').strip()
        if declared_overlap_hash and hashlib.sha256(overlap_path.read_bytes()).hexdigest() != declared_overlap_hash:
            errors.append('source_overlap_report_sha256 does not match the overlap report')
        source_a = str(overlap.get('source_a') or '').strip()
        source_b = str(overlap.get('source_b') or '').strip()
        if not source_a or not source_b or source_a == source_b:
            errors.append('source overlap report must identify two different sources')
        required_source_set = {str(value) for value in required_sources} if isinstance(required_sources, list) else set()
        if {source_a, source_b} != required_source_set:
            errors.append('source overlap report sources do not match required independent sources')
        for key in ('source_a_sha256', 'source_b_sha256'):
            value = str(overlap.get(key) or '').strip()
            if len(value) != 64 or any(character not in '0123456789abcdef' for character in value.lower()):
                errors.append(f'{key} is missing or is not a SHA-256 value')
        for key in ('source_a_record_count', 'source_b_record_count'):
            if _count(overlap.get(key)) is None or (_count(overlap.get(key)) or 0) <= 0:
                errors.append(f'{key} must be positive')
        for key in ('source_a_non_overlap_count', 'source_b_non_overlap_count'):
            if _count(overlap.get(key)) is None or (_count(overlap.get(key)) or 0) <= 0:
                errors.append(f'{key} must be positive after deduplication')
        if _count(overlap.get('independent_positive_source_count')) != MINIMUM_POSITIVE_SOURCES:
            errors.append('source overlap report does not prove two independent positive sources after deduplication')
        if overlap.get('same_event_must_not_count_as_independent') is not True:
            errors.append('source overlap report must state that matched events are not independent corroboration')

    return {
        'passed': not errors,
        'manifest_path': str(path),
        'events_path': str(events_path) if events_path is not None else None,
        'overlap_report_path': str(overlap_path) if overlap_path is not None else None,
        'source_key': manifest.get('source_key'),
        'label_time_contract': requested_contract,
        'label_time_validation': label_time_validation,
        'positive_season_count': len(set(map(str, positive_seasons))) if isinstance(positive_seasons, list) else 0,
        'required_independent_positive_sources': required_sources if isinstance(required_sources, list) else [],
        'selected_region_keys': requested_regions,
        'region_checks': region_checks,
        'exact_time_review': {
            'exact_row_count': len(exact_timestamp_rows),
            'unreviewed_exact_row_count': len(unreviewed_exact_rows),
            'required_event_time_semantics': sorted(EXACT_OCCURRENCE_TIME_SEMANTICS),
            'required_review_status': EXACT_OCCURRENCE_TIME_REVIEW_STATUS,
            'review_id_required': True,
        },
        'gee_sar_time_review': {
            'exact_row_count': len(gee_sar_exact_rows),
            'unreviewed_exact_row_count': len(gee_sar_unreviewed_exact_rows),
            'required_event_time_semantics': GEE_SAR_APPROVED_OCCURRENCE_TIME_SEMANTICS,
            'required_review_status': GEE_SAR_APPROVED_OCCURRENCE_TIME_REVIEW_STATUS,
            'review_id_required': True,
        },
        'errors': errors,
    }


def validate_training_snapshot_binding(
    snapshot_manifest_path: Path,
    *,
    open_source_snapshot_path: Path | None,
    source_key: str | None,
    license_review_id: str | None,
) -> dict[str, Any]:
    """Bind the source consumed by training to the reviewed manifest.

    The metadata gate and the training loader receive separate paths.  This
    contract prevents a caller from passing one reviewed manifest while
    loading a different JSONL snapshot (or silently omitting the open-source
    input) during model fitting.
    """
    manifest_path = Path(snapshot_manifest_path).expanduser()
    manifest = _load_json(manifest_path)
    errors: list[str] = []
    if manifest is None:
        return {
            'passed': False,
            'manifest_path': str(manifest_path),
            'open_source_snapshot_path': str(open_source_snapshot_path) if open_source_snapshot_path else None,
            'errors': ['cannot bind training snapshot: reviewed manifest is missing or invalid JSON'],
        }

    declared_events = manifest.get('events_path')
    declared_events_path = (
        (manifest_path.parent / str(declared_events)).resolve()
        if isinstance(declared_events, str) and declared_events.strip()
        else None
    )
    actual_events_path = (
        Path(open_source_snapshot_path).expanduser().resolve()
        if open_source_snapshot_path is not None and str(open_source_snapshot_path).strip()
        else None
    )
    if declared_events_path is None:
        errors.append('reviewed manifest events_path is required for training binding')
    elif actual_events_path is None:
        errors.append('OPEN_SOURCE_LABEL_SNAPSHOT is required and must point to the reviewed events_path')
    elif not declared_events_path.is_file():
        errors.append(f'reviewed manifest events_path does not exist: {declared_events_path}')
    elif actual_events_path != declared_events_path:
        errors.append(
            'OPEN_SOURCE_LABEL_SNAPSHOT does not match reviewed manifest events_path: '
            f'{actual_events_path} != {declared_events_path}'
        )

    declared_source_keys = manifest.get('source_keys')
    if isinstance(declared_source_keys, list):
        source_keys = sorted({str(value).strip() for value in declared_source_keys if str(value).strip()})
    else:
        source_keys = []
    aggregate_source_key = str(manifest.get('source_key') or '').strip()
    if not source_keys and aggregate_source_key:
        source_keys = [aggregate_source_key]
    runtime_source_key = str(source_key or '').strip()
    if len(source_keys) == 1 and runtime_source_key != source_keys[0]:
        errors.append(
            f'OPEN_SOURCE_LABEL_SOURCE_KEY does not match reviewed manifest source_key: '
            f'{runtime_source_key or "<missing>"} != {source_keys[0]}'
        )
    elif len(source_keys) > 1 and runtime_source_key and runtime_source_key not in source_keys and runtime_source_key != aggregate_source_key:
        errors.append(
            'OPEN_SOURCE_LABEL_SOURCE_KEY is not one of the reviewed manifest source keys: '
            f'{runtime_source_key}'
        )

    expected_license_ids: set[str] = set()
    top_level_license_id = str(manifest.get('license_review_id') or '').strip()
    if top_level_license_id:
        expected_license_ids.add(top_level_license_id)
    source_manifests = manifest.get('source_manifests')
    if isinstance(source_manifests, dict):
        for source_manifest in source_manifests.values():
            if isinstance(source_manifest, dict):
                value = str(source_manifest.get('license_review_id') or '').strip()
                if value:
                    expected_license_ids.add(value)
    runtime_license_id = str(license_review_id or '').strip()
    if len(source_keys) <= 1:
        if not expected_license_ids:
            errors.append('reviewed manifest license_review_id is required for training binding')
        elif runtime_license_id not in expected_license_ids:
            errors.append(
                'OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID does not match the reviewed manifest: '
                f'{runtime_license_id or "<missing>"}'
            )
    elif runtime_license_id and runtime_license_id not in expected_license_ids:
        errors.append(
            'OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID is not present in the reviewed source manifests: '
            f'{runtime_license_id}'
        )

    return {
        'passed': not errors,
        'manifest_path': str(manifest_path),
        'declared_events_path': str(declared_events_path) if declared_events_path else None,
        'open_source_snapshot_path': str(actual_events_path) if actual_events_path else None,
        'declared_source_keys': source_keys,
        'runtime_source_key': runtime_source_key or None,
        'expected_license_review_ids': sorted(expected_license_ids),
        'runtime_license_review_id': runtime_license_id or None,
        'errors': errors,
    }


def _interval_feature_evidence_gate(
    label_manifest_path: Path | None,
    *,
    feature_snapshot_manifest: Path | None,
    interval_evidence_manifest: Path | None,
    interval_preparation_manifest: Path | None = None,
    selected_region_keys: list[str] | None = None,
    label_time_contract: str = LABEL_TIME_CONTRACT_EXACT_V1,
) -> dict[str, Any]:
    """Verify a joined interval shadow artifact without promoting it.

    The label snapshot and feature snapshot are intentionally separate.  A
    structurally valid shadow join proves deterministic evidence only; source
    license approval and the cutoff policy remain independent training gates.
    """
    if label_time_contract != LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1:
        return {
            'required': False,
            'status': 'not_required_for_exact_time_contract',
            'passed': True,
            'structural_passed': None,
            'training_ready': None,
            'structural_errors': [],
            'training_errors': [],
            'errors': [],
            'preparation_manifest_path': None,
            'preparation_manifest_hash': None,
        }

    if feature_snapshot_manifest is None and interval_evidence_manifest is None:
        return {
            'required': False,
            'status': 'not_supplied',
            'passed': True,
            'structural_passed': None,
            'training_ready': None,
            'structural_errors': [],
            'training_errors': [],
            'errors': [],
            'preparation_manifest_path': None,
            'preparation_manifest_hash': None,
        }

    structural_errors: list[str] = []
    training_errors: list[str] = []
    feature_manifest: dict[str, Any] | None = None
    feature_manifest_hash: str | None = None
    feature_rows: list[dict[str, Any]] = []
    preparation_manifest_hash: str | None = None

    if label_manifest_path is None:
        structural_errors.append('interval label snapshot manifest is required')

    if feature_snapshot_manifest is None:
        structural_errors.append('interval feature snapshot manifest is required')
    else:
        try:
            feature_rows, feature_manifest = load_station_free_feature_snapshot(
                Path(feature_snapshot_manifest)
            )
            feature_manifest_hash = str(feature_manifest.get('manifest_hash') or '').strip()
        except (OSError, ValueError) as exc:
            structural_errors.append(f'interval feature snapshot is invalid: {exc}')

    if feature_manifest is not None:
        if feature_manifest.get('station_data_used') is not False:
            structural_errors.append('interval feature snapshot must declare station_data_used=false')
        if feature_manifest.get('feature_snapshot_ready') is not True:
            structural_errors.append('interval feature snapshot is not structurally ready')
        if feature_manifest.get('training_eligible') is True:
            structural_errors.append('interval feature snapshot training_eligible must remain false')
        if feature_manifest.get('production_scoring_eligible') is not False:
            structural_errors.append('interval feature snapshot production_scoring_eligible must remain false')
        missing_values = _count(feature_manifest.get('missing_required_feature_value_count'))
        if missing_values is None or missing_values > 0:
            structural_errors.append(
                'interval feature snapshot has missing required feature values'
            )
        available_regions = {
            str(value).strip()
            for value in feature_manifest.get('region_keys', [])
            if str(value).strip()
        } if isinstance(feature_manifest.get('region_keys'), list) else set()
        requested_regions = {
            str(value).strip()
            for value in (selected_region_keys or [])
            if str(value).strip()
        }
        if requested_regions and not requested_regions.issubset(available_regions):
            structural_errors.append(
                'interval feature snapshot does not cover every selected training region'
            )
        source_manifests = feature_manifest.get('source_manifests')
        if not isinstance(source_manifests, dict) or not source_manifests:
            structural_errors.append('interval feature snapshot source_manifests is missing')
        else:
            for source_key, source_manifest in sorted(source_manifests.items()):
                if not isinstance(source_manifest, dict):
                    structural_errors.append(
                        f'interval feature source manifest is invalid: {source_key}'
                    )
                    continue
                if source_manifest.get('station_data_used') is not False:
                    structural_errors.append(
                        f'interval feature source uses station data: {source_key}'
                    )
                license_status = str(source_manifest.get('license_status') or '').strip().lower()
                if license_status != 'permissive_core_reviewed':
                    training_errors.append(
                        f'interval feature source license is not core-reviewed: {source_key}'
                    )
                cutoff_review = str(
                    source_manifest.get('cutoff_policy_review_status')
                    or feature_manifest.get('cutoff_policy_review_status')
                    or ''
                ).strip().lower()
                if cutoff_review != 'approved':
                    training_errors.append(
                        f'interval feature cutoff policy is not approved: {source_key}'
                    )
        if not str(feature_manifest.get('cutoff_rule') or '').strip():
            structural_errors.append('interval feature snapshot cutoff_rule is missing')

    evidence: dict[str, Any] | None = None
    if interval_evidence_manifest is None:
        structural_errors.append('interval shadow join evidence manifest is required')
    else:
        evidence = _load_json(Path(interval_evidence_manifest))
        if evidence is None:
            structural_errors.append('interval shadow join evidence manifest is invalid')
        else:
            if evidence.get('status') != 'shadow_frame_written':
                structural_errors.append(
                    'interval shadow join evidence status is not shadow_frame_written'
                )
            if evidence.get('training_eligible') is not False:
                structural_errors.append('interval shadow join evidence training_eligible must remain false')
            if evidence.get('production_scoring_eligible') is not False:
                structural_errors.append(
                    'interval shadow join evidence production_scoring_eligible must remain false'
                )
            if evidence.get('shadow_only') is not True:
                structural_errors.append('interval shadow join evidence must remain shadow_only')
            summary = evidence.get('join', {}).get('summary') if isinstance(evidence.get('join'), dict) else None
            joined_count = _count(summary.get('joined_count')) if isinstance(summary, dict) else None
            if joined_count is None or joined_count <= 0:
                structural_errors.append('interval shadow join evidence has no joined rows')
            evidence_payload = evidence.get('evidence')
            if not isinstance(evidence_payload, dict):
                structural_errors.append('interval shadow join reproducibility evidence is missing')
            else:
                validation = evidence_payload.get('validation')
                if not isinstance(validation, dict) or validation.get('passed') is not True:
                    structural_errors.append('interval shadow join validation did not pass')
                for field in ('shadow_only', 'core_training_eligible', 'production_scoring_eligible'):
                    if field == 'shadow_only' and evidence_payload.get(field) is not True:
                        structural_errors.append('interval shadow frame must declare shadow_only=true')
                    if field != 'shadow_only' and evidence_payload.get(field) is not False:
                        structural_errors.append(f'interval shadow frame {field} must remain false')
                provenance = evidence_payload.get('snapshot_provenance')
                if not isinstance(provenance, dict):
                    structural_errors.append('interval shadow frame snapshot provenance is missing')
                elif feature_manifest_hash and provenance.get('feature_manifest_hash') != feature_manifest_hash:
                    structural_errors.append('interval shadow frame feature manifest hash does not match')

            expected_label_hash = None
            if label_manifest_path is not None:
                label_manifest = _load_json(Path(label_manifest_path))
                expected_label_hash = str(label_manifest.get('event_rows_sha256') or '').strip() if label_manifest else None
            if expected_label_hash and evidence.get('label_event_rows_sha256') != expected_label_hash:
                structural_errors.append('interval shadow frame label event hash does not match')
            if feature_manifest_hash and evidence.get('feature_manifest_hash') != feature_manifest_hash:
                structural_errors.append('interval shadow frame feature manifest hash does not match')

    if interval_preparation_manifest is not None:
        preparation = _load_json(Path(interval_preparation_manifest))
        if preparation is None:
            structural_errors.append('interval training preparation manifest is invalid')
        else:
            preparation_validation = validate_interval_training_preparation_manifest(preparation)
            if not preparation_validation['passed']:
                structural_errors.extend(
                    f'interval preparation: {error}'
                    for error in preparation_validation['errors']
                )
            preparation_manifest_hash = str(preparation.get('manifest_hash') or '').strip()
            inputs = preparation.get('inputs')
            if isinstance(inputs, dict):
                if feature_manifest_hash and inputs.get('feature_manifest_sha256') != feature_manifest_hash:
                    structural_errors.append(
                        'interval preparation feature manifest hash does not match'
                    )
                if evidence and isinstance(evidence.get('evidence'), dict):
                    expected_frame_hash = evidence['evidence'].get('snapshot_hash')
                    if expected_frame_hash and inputs.get('interval_frame_sha256') != expected_frame_hash:
                        structural_errors.append(
                            'interval preparation frame hash does not match shadow evidence'
                        )
            else:
                structural_errors.append('interval preparation inputs are missing')

    structural_passed = not structural_errors
    training_ready = structural_passed and not training_errors
    return {
        'required': True,
        'status': 'training_ready' if training_ready else (
            'shadow_evidence_verified' if structural_passed else 'blocked'
        ),
        'passed': training_ready,
        'structural_passed': structural_passed,
        'training_ready': training_ready,
        'feature_manifest_path': str(feature_snapshot_manifest) if feature_snapshot_manifest else None,
        'feature_manifest_hash': feature_manifest_hash,
        'feature_row_count': len(feature_rows),
        'interval_evidence_manifest_path': str(interval_evidence_manifest) if interval_evidence_manifest else None,
        'interval_preparation_manifest_path': str(interval_preparation_manifest) if interval_preparation_manifest else None,
        'interval_preparation_manifest_hash': preparation_manifest_hash,
        'structural_errors': structural_errors,
        'training_errors': training_errors,
        'errors': structural_errors + training_errors,
    }


def _reproducibility_integrity(
    training_metrics: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    reproducibility_manifest: dict[str, Any] | None,
    split_manifest: dict[str, Any] | None,
    artifact_dir: Path,
) -> dict[str, bool | str]:
    training = training_metrics or {}
    data = manifest or {}
    reproducibility = reproducibility_manifest or {}
    split_data = split_manifest or {}
    containers = (training, data, reproducibility)
    runtime = data.get('runtime_manifest')
    if not isinstance(runtime, dict):
        runtime = reproducibility.get('runtime') if isinstance(reproducibility.get('runtime'), dict) else {}
    snapshot_ref = any(
        isinstance(container.get(key), str) and container.get(key).strip()
        for container in containers
        for key in ('row_snapshot_ref', 'snapshot_path', 'dataset_uri', 'source_snapshot_uri', 'source_rows_ref')
    )
    snapshot_path = artifact_dir / 'event_rows.jsonl'
    snapshot_file_present = snapshot_path.is_file()
    expected_snapshot_hash = next(
        (
            str(container.get(key)).strip()
            for container in containers
            for key in ('row_snapshot_sha256', 'snapshot_hash')
            if isinstance(container.get(key), str) and container.get(key).strip()
        ),
        None,
    )
    actual_snapshot_hash = None
    if snapshot_file_present:
        try:
            actual_snapshot_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        except OSError:
            actual_snapshot_hash = None
    snapshot_hash_valid = bool(
        expected_snapshot_hash
        and actual_snapshot_hash
        and expected_snapshot_hash == actual_snapshot_hash
    )
    split_ref = any(
        isinstance(container.get(key), (dict, list, str)) and bool(container.get(key))
        for container in (training, data, reproducibility, split_data)
        for key in ('split_boundaries', 'split_manifest', 'split_policy')
    )
    code_sha = any(
        isinstance(container.get(key), str) and container.get(key).strip()
        for container in (training, data, reproducibility, runtime)
        for key in ('git_commit_sha', 'source_commit', 'code_sha')
    )
    environment = any(
        isinstance(container.get(key), (dict, list, str)) and bool(container.get(key))
        for container in (training, data, reproducibility, runtime)
        for key in ('environment', 'dependency_lock_hash', 'runtime_manifest')
    )
    return {
        'dataset_manifest_present': manifest is not None,
        'dataset_snapshot_id_present': bool(training.get('dataset_snapshot_id') or data.get('dataset_snapshot_id')),
        'feature_columns_hash_present': bool(training.get('feature_columns_hash')),
        'label_schema_hash_present': bool(training.get('label_schema_hash')),
        'row_level_snapshot_present': bool(snapshot_ref and snapshot_hash_valid),
        'row_snapshot_file_present': snapshot_file_present,
        'row_snapshot_hash_present': bool(expected_snapshot_hash),
        'row_snapshot_hash_valid': snapshot_hash_valid,
        'split_boundaries_present': split_ref,
        'code_sha_present': code_sha,
        'environment_manifest_present': environment,
        'remote_artifact_status': 'not_checked_by_local_audit',
    }


def build_dataset_audit(
    artifact_dir: Path,
    *,
    snapshot_manifest: Path | None = None,
    source_request_manifest: Path | None = None,
    source_request_payload: Path | None = None,
    source_request_events: Path | None = None,
    feature_snapshot_manifest: Path | None = None,
    interval_evidence_manifest: Path | None = None,
    interval_preparation_manifest: Path | None = None,
    selected_region_keys: list[str] | None = None,
    label_time_contract: str = LABEL_TIME_CONTRACT_EXACT_V1,
) -> dict[str, Any]:
    """Build a deterministic audit from one local training artifact directory."""
    training_metrics = _load_json(artifact_dir / 'training_metrics.json')
    stage_metrics = _load_json(artifact_dir / 'training_stage_metrics.json')
    autonomous_summary = _load_json(artifact_dir / 'autonomous_evidence_summary.json') or {}
    hindcast = _load_json(artifact_dir / 'hindcast_run.json') or {}
    reproducibility_manifest = _load_json(artifact_dir / 'reproducibility_manifest.json')
    split_manifest = _load_json(artifact_dir / 'split_manifest.json')
    training_metrics = training_metrics or {}
    manifest = training_metrics.get('dataset_manifest')
    manifest = manifest if isinstance(manifest, dict) else None
    manifest_present = manifest is not None
    findings: list[dict[str, Any]] = []
    source_request_gate = _source_request_gate(
        source_request_manifest,
        source_request_payload_path=source_request_payload,
        source_request_events_path=source_request_events,
    )
    joined_interval_evidence_supplied = (
        label_time_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
        and feature_snapshot_manifest is not None
        and interval_evidence_manifest is not None
    )
    snapshot_gate = _reviewed_snapshot_gate(
        snapshot_manifest,
        selected_region_keys=selected_region_keys,
        label_time_contract=label_time_contract,
        require_feature_cutoff=not joined_interval_evidence_supplied,
    )
    interval_feature_gate = _interval_feature_evidence_gate(
        snapshot_manifest,
        feature_snapshot_manifest=feature_snapshot_manifest,
        interval_evidence_manifest=interval_evidence_manifest,
        interval_preparation_manifest=interval_preparation_manifest,
        selected_region_keys=selected_region_keys,
        label_time_contract=label_time_contract,
    )
    if source_request_gate['required'] and not source_request_gate['passed']:
        findings.append(_finding(
            'source_manifest_intake_gate_blocked',
            'HIGH',
            'Source-owner manifest has not passed executable intake validation',
            source_request_gate,
            'Provide the approved source-owner manifest, matching immutable payload, and canonical event JSONL before training.',
        ))
    if not snapshot_gate['passed']:
        findings.append(_finding(
            'reviewed_snapshot_gate_blocked',
            'HIGH',
            'Reviewed multi-season independent-source snapshot is not ready',
            snapshot_gate,
            'Provide a hash-verified snapshot manifest with license review, three positive seasons, two independent sources, and a reviewed overlap report before training.',
        ))
    if interval_feature_gate['required'] and not interval_feature_gate['passed']:
        findings.append(_finding(
            'interval_feature_evidence_gate_blocked',
            'HIGH',
            'Interval shadow evidence is not approved for training',
            interval_feature_gate,
            'Keep the interval lane shadow-only until the feature snapshot, join evidence, source license, and cutoff policy are approved.',
        ))

    if manifest is None:
        findings.append(_finding(
            'missing_dataset_manifest',
            'CRITICAL',
            'Training artifact has no dataset manifest',
            {'artifact_dir': str(artifact_dir)},
            'Stop training publication and persist a versioned dataset manifest before retraining.',
        ))
        manifest = {}

    positive_count = _count(manifest.get('positive_count'))
    negative_count = _count(manifest.get('negative_count'))
    training_row_count = _count(manifest.get('training_row_count'))
    if training_row_count is None and positive_count is not None and negative_count is not None:
        training_row_count = positive_count + negative_count
    positive_fraction = (
        round(positive_count / training_row_count, 6)
        if positive_count is not None and training_row_count
        else None
    )

    oldest = _timestamp(manifest.get('oldest_timestamp'))
    newest = _timestamp(manifest.get('newest_timestamp'))
    temporal_span_days = round((newest - oldest).total_seconds() / 86400, 3) if oldest and newest else None
    region_keys = manifest.get('region_keys')
    if not isinstance(region_keys, list):
        region_keys = []
    region_keys = sorted({str(value) for value in region_keys if str(value).strip()})

    source_counts = manifest.get('event_source_counts')
    if not isinstance(source_counts, dict):
        source_counts = autonomous_summary.get('positive_source_counts')
    if not isinstance(source_counts, dict):
        source_counts = {}
    source_counts = {str(key): _count(value) or 0 for key, value in source_counts.items()}
    source_shares = _source_shares(source_counts, positive_count)
    dominant_source = max(source_shares, key=source_shares.get) if source_shares else None
    positive_source_ids = manifest.get('positive_source_ids')
    positive_source_ids = sorted({str(value) for value in positive_source_ids if str(value).strip()}) if isinstance(positive_source_ids, list) else []
    positive_season_ids = manifest.get('positive_season_ids')
    positive_season_ids = sorted({str(value) for value in positive_season_ids if str(value).strip()}) if isinstance(positive_season_ids, list) else []

    if len(positive_source_ids) < MINIMUM_POSITIVE_SOURCES:
        findings.append(_finding(
            'independent_positive_source_count_below_minimum',
            'HIGH',
            'Artifact does not persist two independent positive label sources',
            {
                'positive_source_ids': positive_source_ids,
                'event_source_counts': source_counts,
                'minimum_positive_sources': MINIMUM_POSITIVE_SOURCES,
            },
            'Persist source IDs from the exact training frame and pass the reviewed overlap gate before fitting or publishing.',
        ))
    if len(positive_season_ids) < MINIMUM_POSITIVE_SEASONS:
        findings.append(_finding(
            'positive_season_count_below_minimum',
            'HIGH',
            'Artifact does not persist three positive snow seasons',
            {
                'positive_season_ids': positive_season_ids,
                'minimum_positive_seasons': MINIMUM_POSITIVE_SEASONS,
            },
            'Persist region-aware positive season IDs from the exact training frame and hold out a later season.',
        ))

    debug_stats = manifest.get('debug_stats')
    debug_stats = debug_stats if isinstance(debug_stats, dict) else {}
    raw_rows = _count(debug_stats.get('raw_rows'))
    assembled_ok = _count(debug_stats.get('assembled_ok'))
    assembly_loss = raw_rows - assembled_ok if raw_rows is not None and assembled_ok is not None else None
    assembly_loss_rate = round(assembly_loss / raw_rows, 6) if assembly_loss is not None and raw_rows else None
    terrain_loss_report = debug_stats.get('terrain_loss_report')
    terrain_loss_report = terrain_loss_report if isinstance(terrain_loss_report, dict) else None
    terrain_loss_rate = _number(terrain_loss_report.get('terrain_loss_rate')) if terrain_loss_report else None
    terrain_failure_reasons = terrain_loss_report.get('failure_reasons', {}) if terrain_loss_report else {}
    terrain_failure_reasons = terrain_failure_reasons if isinstance(terrain_failure_reasons, dict) else {}

    phase = _phase_metrics(stage_metrics, training_metrics)
    phase_total = round(sum(phase.values()), 3) if phase else None
    dataset_load_seconds = phase.get('dataset_load_seconds')
    fit_model_seconds = phase.get('fit_model_seconds')
    dataset_load_fraction = round(dataset_load_seconds / phase_total, 6) if dataset_load_seconds is not None and phase_total else None
    bottleneck_phase = max(phase, key=phase.get) if phase else None

    metrics = training_metrics.get('metrics')
    metrics = metrics if isinstance(metrics, dict) else {}
    timeseries_folds = [float(value) for value in metrics.get('pss_timeseries_folds', []) if isinstance(value, (int, float))]
    spatial_folds = [float(value) for value in metrics.get('pss_spatial_folds', []) if isinstance(value, (int, float))]
    fold_metrics_present = bool(timeseries_folds) and bool(spatial_folds)
    robustness_breaches = {
        'timeseries': [value for value in timeseries_folds if value < ROBUSTNESS_PSS_FLOOR],
        'spatial': [value for value in spatial_folds if value < ROBUSTNESS_PSS_FLOOR],
    }

    integrity = _reproducibility_integrity(
        training_metrics,
        manifest if manifest_present else None,
        reproducibility_manifest,
        split_manifest,
        artifact_dir,
    )

    if (
        label_time_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
        and INTERVAL_TRAINING_PATH_STATUS != 'implemented_and_verified'
    ):
        findings.append(_finding(
            'interval_training_path_not_production_verified',
            'HIGH',
            'Interval-censored preparation is implemented, but production training remains shadow-only',
            {
                'label_time_contract': label_time_contract,
                'training_path_status': INTERVAL_TRAINING_PATH_STATUS,
                'structural_contract_passed': snapshot_gate.get('label_time_validation', {}).get('passed'),
            },
            'Keep the interval lane shadow-only until interval loss, negative-sampling, model-quality, and scientist approval gates pass end-to-end.',
        ))

    if temporal_span_days is None:
        findings.append(_finding(
            'missing_temporal_coverage',
            'HIGH',
            'Artifact does not prove its time coverage',
            {'oldest_timestamp': manifest.get('oldest_timestamp'), 'newest_timestamp': manifest.get('newest_timestamp')},
            'Persist valid UTC bounds and a row-level snapshot before evaluating generalisation.',
        ))
    elif temporal_span_days < MIN_TEMPORAL_SPAN_DAYS:
        findings.append(_finding(
            'temporal_coverage_concentrated',
            'HIGH',
            'Positive training data is concentrated in a short time window',
            {'temporal_span_days': temporal_span_days, 'minimum_review_span_days': MIN_TEMPORAL_SPAN_DAYS},
            'Expand the open-source event window across multiple snow seasons and hold out a later season.',
        ))

    if positive_count and (not source_shares or max(source_shares.values(), default=0.0) >= 0.95):
        findings.append(_finding(
            'label_source_concentrated',
            'HIGH',
            'Positive labels are dominated by one source',
            {'positive_count': positive_count, 'event_source_counts': source_counts, 'source_shares': source_shares},
            'Add an independently governed open-source label lane and report per-source holdouts.',
        ))

    manual_positive_count = _count(autonomous_summary.get('manual_positive_count'))
    if positive_count and manual_positive_count == 0:
        findings.append(_finding(
            'no_independent_manual_positive_labels',
            'MEDIUM',
            'The artifact has no independent manual positive labels',
            {'positive_count': positive_count, 'manual_positive_count': manual_positive_count},
            'Keep the model research-only until an independent validation lane is available.',
        ))

    if assembly_loss is not None and assembly_loss > 0:
        findings.append(_finding(
            'terrain_assembly_loss',
            'MEDIUM',
            'Some candidate positive rows were lost during terrain assembly',
            {
                'raw_rows': raw_rows,
                'assembled_ok': assembled_ok,
                'loss_count': assembly_loss,
                'loss_rate': assembly_loss_rate,
                'terrain_failed': debug_stats.get('terrain_failed'),
                'terrain_loss_report': terrain_loss_report,
            },
            'Explain or repair terrain coverage and keep the loss rate in the training manifest.',
        ))

    if terrain_loss_report is None and assembly_loss is not None and assembly_loss > 0:
        findings.append(_finding(
            'terrain_diagnostics_missing',
            'HIGH',
            'Terrain loss is present but not broken down by stable reason code',
            {'assembly_loss_count': assembly_loss, 'assembly_loss_rate': assembly_loss_rate},
            'Persist terrain candidate, success, failure-reason, and per-region counters before retraining.',
        ))
    elif terrain_loss_rate is not None and terrain_loss_rate > MAX_TERRAIN_LOSS_RATE:
        findings.append(_finding(
            'terrain_loss_policy_breach',
            'HIGH',
            'Terrain-stage loss exceeds the release evidence threshold',
            {
                'terrain_loss_rate': terrain_loss_rate,
                'maximum_review_rate': MAX_TERRAIN_LOSS_RATE,
                'terrain_loss_count': terrain_loss_report.get('terrain_loss_count'),
                'candidate_rows': terrain_loss_report.get('candidate_rows'),
                'failure_reasons': terrain_failure_reasons,
                'by_region': terrain_loss_report.get('by_region'),
            },
            'Repair DEM coverage or classify the remaining loss, then rerun the metadata gate before training.',
        ))
    unknown_terrain_loss = _count(terrain_failure_reasons.get('unknown_terrain_error'))
    if unknown_terrain_loss:
        findings.append(_finding(
            'unclassified_terrain_loss',
            'HIGH',
            'Terrain failures include an unknown reason code',
            {'unknown_terrain_error_count': unknown_terrain_loss, 'failure_reasons': terrain_failure_reasons},
            'Add a stable reason classification or repair the failing terrain path before using the rows for training.',
        ))

    if dataset_load_seconds is not None and fit_model_seconds is not None and dataset_load_seconds > fit_model_seconds and (dataset_load_fraction or 0.0) >= 0.8:
        findings.append(_finding(
            'dataset_load_bottleneck',
            'HIGH',
            'Dataset materialisation dominates training runtime',
            {'dataset_load_seconds': dataset_load_seconds, 'fit_model_seconds': fit_model_seconds, 'dataset_load_fraction': dataset_load_fraction, 'bottleneck_phase': bottleneck_phase},
            'Prewarm and reuse bounded regional-day inputs, cache the snapshot, and fail fast before a repeated cold-start build.',
        ))

    if not fold_metrics_present:
        findings.append(_finding(
            'fold_metrics_missing',
            'HIGH',
            'Artifact does not preserve both temporal and spatial fold metrics',
            {
                'timeseries_fold_count': len(timeseries_folds),
                'spatial_fold_count': len(spatial_folds),
            },
            'Persist per-fold temporal and spatial metrics with the artifact before using aggregate scores as evidence.',
        ))

    if robustness_breaches['timeseries'] or robustness_breaches['spatial']:
        findings.append(_finding(
            'cv_fold_robustness_breach',
            'MEDIUM',
            'At least one temporal or spatial validation fold is below the robustness reference floor',
            {'reference_pss_floor': ROBUSTNESS_PSS_FLOOR, 'timeseries_breaches': robustness_breaches['timeseries'], 'spatial_breaches': robustness_breaches['spatial'], 'reported_pss': metrics.get('pss_reported')},
            'Retain fold-level metrics and investigate weak seasons/regions before treating the aggregate score as generalisation proof.',
        ))

    shadow_summary = hindcast.get('summary_metrics') if isinstance(hindcast.get('summary_metrics'), dict) else {}
    shadow_passed = shadow_summary.get('shadow_quality_gate_passed')
    if shadow_passed is False:
        findings.append(_finding(
            'shadow_quality_gate_failed',
            'MEDIUM',
            'The dynamic shadow model did not pass its quality gate',
            {'shadow_quality_gate_passed': shadow_passed, 'brier_score_calibrated': shadow_summary.get('brier_score_calibrated'), 'pss_calibrated': shadow_summary.get('pss_calibrated')},
            'Keep the surrogate active and the dynamic model shadow-only until its independent quality gate passes.',
        ))

    missing_integrity = [key for key in ('row_level_snapshot_present', 'row_snapshot_hash_valid', 'split_boundaries_present', 'code_sha_present', 'environment_manifest_present') if not integrity[key]]
    if missing_integrity:
        findings.append(_finding(
            'reproducibility_evidence_incomplete',
            'HIGH',
            'Artifact provenance is incomplete for exact replay',
            {'missing_fields': missing_integrity, 'dataset_snapshot_id_present': integrity['dataset_snapshot_id_present']},
            'Persist the exact row snapshot, split boundaries, source commit, and locked runtime manifest with every artifact.',
        ))

    decision = 'reviewable'
    if not training_metrics.get('dataset_manifest'):
        decision = 'blocked_missing_dataset_manifest'
    elif source_request_gate['required'] and not source_request_gate['passed']:
        decision = 'blocked_pending_source_manifest_intake'
    elif not snapshot_gate['passed']:
        decision = (
            'blocked_pending_interval_feature_evidence'
            if interval_feature_gate['required']
            and not interval_feature_gate['structural_passed']
            else 'blocked_pending_interval_feature_approval'
            if interval_feature_gate['required']
            and interval_feature_gate['structural_passed']
            and not interval_feature_gate['training_ready']
            else 'blocked_pending_snapshot_evidence'
        )
    elif interval_feature_gate['required'] and not interval_feature_gate['structural_passed']:
        decision = 'blocked_pending_interval_feature_evidence'
    elif interval_feature_gate['required'] and not interval_feature_gate['training_ready']:
        decision = 'blocked_pending_interval_feature_approval'
    elif (
        label_time_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
        and INTERVAL_TRAINING_PATH_STATUS != 'implemented_and_verified'
    ):
        decision = 'blocked_pending_interval_training_support'
    elif any(item['severity'] in {'CRITICAL', 'HIGH'} for item in findings):
        decision = 'blocked_pending_dataset_evidence'

    return {
        'audit_version': AUDIT_VERSION,
        'artifact_dir': str(artifact_dir),
        'dataset': {
            'training_dataset_version': manifest.get('training_dataset_version'),
            'dataset_snapshot_id': training_metrics.get('dataset_snapshot_id') or manifest.get('dataset_snapshot_id'),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'training_row_count': training_row_count,
            'positive_fraction': positive_fraction,
            'negative_to_positive_ratio': round(negative_count / positive_count, 6) if negative_count is not None and positive_count else None,
            'event_source_counts': source_counts,
            'positive_source_ids': positive_source_ids,
            'positive_season_ids': positive_season_ids,
            'source_shares': source_shares,
            'dominant_positive_source': dominant_source,
            'manual_positive_count': manual_positive_count,
        },
        'coverage': {
            'oldest_timestamp': manifest.get('oldest_timestamp'),
            'newest_timestamp': manifest.get('newest_timestamp'),
            'temporal_span_days': temporal_span_days,
            'region_keys': region_keys,
            'region_count': len(region_keys),
        },
        'quality': {
            'raw_candidate_rows': raw_rows,
            'assembled_positive_rows': assembled_ok,
            'assembly_loss_count': assembly_loss,
            'assembly_loss_rate': assembly_loss_rate,
            'terrain_loss_report': terrain_loss_report,
            'debug_stats': debug_stats,
        },
        'runtime': {
            'phase_breakdown_seconds': phase,
            'phase_total_seconds': phase_total,
            'dataset_load_seconds': dataset_load_seconds,
            'fit_model_seconds': fit_model_seconds,
            'dataset_load_fraction': dataset_load_fraction,
            'bottleneck_phase': bottleneck_phase,
        },
        'evaluation': {
            'metrics': metrics,
            'timeseries_fold_pss': timeseries_folds,
            'spatial_fold_pss': spatial_folds,
            'fold_metrics_present': fold_metrics_present,
            'robustness_pss_floor': ROBUSTNESS_PSS_FLOOR,
            'robustness_breaches': robustness_breaches,
            'shadow_quality_gate_passed': shadow_passed,
        },
        'integrity': integrity,
        'source_request_gate': source_request_gate,
        'interval_training_path_status': INTERVAL_TRAINING_PATH_STATUS,
        'snapshot_gate': snapshot_gate,
        'interval_feature_gate': interval_feature_gate,
        'findings': findings,
        'decision': decision,
    }


def build_training_preflight(
    artifact_root: Path,
    *,
    snapshot_manifest: Path | None = None,
    source_request_manifest: Path | None = None,
    source_request_payload: Path | None = None,
    source_request_events: Path | None = None,
    feature_snapshot_manifest: Path | None = None,
    interval_evidence_manifest: Path | None = None,
    interval_preparation_manifest: Path | None = None,
    selected_region_keys: list[str] | None = None,
    label_time_contract: str = LABEL_TIME_CONTRACT_EXACT_V1,
) -> dict[str, Any]:
    """Audit the latest prior training candidate without network or model I/O.

    A fresh checkout has no prior candidate to audit and is ready to start one
    bounded candidate run only after the complete reviewed snapshot gate passes.
    Only timestamped training directories are
    considered; recovery and inference-cache directories are intentionally
    excluded because they are not evidence for the next training attempt.
    """
    root = Path(artifact_root)
    candidates = sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and _TIMESTAMPED_ARTIFACT.fullmatch(path.name)
        and (path / 'training_metrics.json').is_file()
    ) if root.is_dir() else []

    if not candidates:
        source_request_gate = _source_request_gate(
            source_request_manifest,
            source_request_payload_path=source_request_payload,
            source_request_events_path=source_request_events,
        )
        joined_interval_evidence_supplied = (
            label_time_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
            and feature_snapshot_manifest is not None
            and interval_evidence_manifest is not None
        )
        snapshot_gate = _reviewed_snapshot_gate(
            snapshot_manifest,
            selected_region_keys=selected_region_keys,
            label_time_contract=label_time_contract,
            require_feature_cutoff=not joined_interval_evidence_supplied,
        )
        interval_feature_gate = _interval_feature_evidence_gate(
            snapshot_manifest,
            feature_snapshot_manifest=feature_snapshot_manifest,
            interval_evidence_manifest=interval_evidence_manifest,
            interval_preparation_manifest=interval_preparation_manifest,
            selected_region_keys=selected_region_keys,
            label_time_contract=label_time_contract,
        )
        label_time_validation = snapshot_gate.get('label_time_validation') or {}
        return {
            'preflight_version': PREFLIGHT_VERSION,
            'artifact_root': str(root),
            'status': 'no_prior_artifact',
            'decision': (
                'blocked_pending_source_manifest_intake'
                if source_request_gate['required'] and not source_request_gate['passed']
                else 'blocked_pending_interval_feature_evidence'
                if interval_feature_gate['required']
                and not interval_feature_gate['structural_passed']
                else (
                    'blocked_pending_interval_feature_approval'
                    if interval_feature_gate['required']
                    and interval_feature_gate['structural_passed']
                    and not interval_feature_gate['training_ready']
                    else (
                        'blocked_pending_snapshot_evidence'
                        if not snapshot_gate['passed']
                        else (
                            'blocked_pending_interval_training_support'
                            if label_time_contract == LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
                            and INTERVAL_TRAINING_PATH_STATUS != 'implemented_and_verified'
                            else 'ready_for_first_training'
                        )
                    )
                )
            ),
            'reason': 'No timestamped training artifact with training_metrics.json was found.',
            'interval_training_path_status': INTERVAL_TRAINING_PATH_STATUS,
            'structural_contract_passed': label_time_validation.get('passed'),
            'source_request_gate': source_request_gate,
            'snapshot_gate': snapshot_gate,
            'interval_feature_gate': interval_feature_gate,
        }

    latest = candidates[-1]
    audit = build_dataset_audit(
        latest,
        snapshot_manifest=snapshot_manifest,
        source_request_manifest=source_request_manifest,
        source_request_payload=source_request_payload,
        source_request_events=source_request_events,
        feature_snapshot_manifest=feature_snapshot_manifest,
        interval_evidence_manifest=interval_evidence_manifest,
        interval_preparation_manifest=interval_preparation_manifest,
        selected_region_keys=selected_region_keys,
        label_time_contract=label_time_contract,
    )
    return {
        'preflight_version': PREFLIGHT_VERSION,
        'artifact_root': str(root),
        'status': 'prior_artifact_audited',
        'artifact_dir': str(latest),
        'decision': audit['decision'],
        'snapshot_gate': audit['snapshot_gate'],
        'interval_feature_gate': audit['interval_feature_gate'],
        'audit': audit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Audit one local avalanche training artifact without network or model loading')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--artifact-dir', type=Path, help='Audit one exact artifact directory')
    target.add_argument('--artifact-root', type=Path, help='Audit the latest timestamped artifact under this root')
    parser.add_argument('--snapshot-manifest', type=Path, required=False, help='Reviewed open-source snapshot manifest')
    parser.add_argument(
        '--source-request-manifest',
        type=Path,
        required=False,
        help='Optional completed MVP4 source-owner manifest to validate before snapshot preflight',
    )
    parser.add_argument(
        '--source-request-payload',
        type=Path,
        required=False,
        help='Immutable raw payload referenced by --source-request-manifest',
    )
    parser.add_argument(
        '--source-request-events-jsonl',
        type=Path,
        required=False,
        help='Canonical exact-time event JSONL for --source-request-manifest',
    )
    parser.add_argument(
        '--feature-snapshot-manifest',
        type=Path,
        required=False,
        help='Hash-verified station-free feature snapshot manifest for the interval shadow lane',
    )
    parser.add_argument(
        '--interval-evidence-manifest',
        type=Path,
        required=False,
        help='Deterministic interval shadow join report/evidence manifest',
    )
    parser.add_argument(
        '--interval-preparation-manifest',
        type=Path,
        required=False,
        help='Content-addressed, shadow-only interval-training preparation manifest',
    )
    parser.add_argument(
        '--region-keys',
        help='Comma-separated training regions; each selected region must meet the multi-season/source gate',
    )
    parser.add_argument(
        '--label-time-contract',
        choices=sorted(SUPPORTED_LABEL_TIME_CONTRACTS),
        default=LABEL_TIME_CONTRACT_EXACT_V1,
        help='Explicit label occurrence-time contract; exact time remains the default',
    )
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true', help='Return exit code 2 when the audit is blocked')
    args = parser.parse_args(argv)

    selected_region_keys = [
        value.strip() for value in (args.region_keys or '').split(',') if value.strip()
    ]
    report = (
        build_training_preflight(
            args.artifact_root,
            snapshot_manifest=args.snapshot_manifest,
            source_request_manifest=args.source_request_manifest,
            source_request_payload=args.source_request_payload,
            source_request_events=args.source_request_events_jsonl,
            feature_snapshot_manifest=args.feature_snapshot_manifest,
            interval_evidence_manifest=args.interval_evidence_manifest,
            interval_preparation_manifest=args.interval_preparation_manifest,
            selected_region_keys=selected_region_keys,
            label_time_contract=args.label_time_contract,
        )
        if args.artifact_root is not None
        else build_dataset_audit(
            args.artifact_dir,
            snapshot_manifest=args.snapshot_manifest,
            source_request_manifest=args.source_request_manifest,
            source_request_payload=args.source_request_payload,
            source_request_events=args.source_request_events_jsonl,
            feature_snapshot_manifest=args.feature_snapshot_manifest,
            interval_evidence_manifest=args.interval_evidence_manifest,
            interval_preparation_manifest=args.interval_preparation_manifest,
            selected_region_keys=selected_region_keys,
            label_time_contract=args.label_time_contract,
        )
    )
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    allowed_without_prior_artifact = {'reviewable', 'ready_for_first_training'}
    return 2 if args.strict and report['decision'] not in allowed_without_prior_artifact else 0


if __name__ == '__main__':
    raise SystemExit(main())
