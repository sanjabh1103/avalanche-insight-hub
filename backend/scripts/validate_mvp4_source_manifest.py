#!/usr/bin/env python3
"""Validate one MVP4 source-owner manifest before snapshot normalization.

This is a dependency-free intake gate.  It validates the exact-time source
contract and, for an approved core manifest, compares the declared payload
SHA-256 with the immutable source file supplied by the owner.  It does not
build a training snapshot, establish source independence, assign event groups,
or authorize model fitting; those remain later preflight gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.common.label_time_contract import (
    LABEL_TIME_CONTRACT_EXACT_V1,
    validate_label_time_rows,
)


VALIDATOR_VERSION = 'mvp4_source_manifest_intake_v2'
SCHEMA_VERSION = 'mvp4_source_request_manifest_v1'
CORE_ROLES = {'requested_core', 'core'}
NON_CORE_ROLES = {'shadow', 'benchmark', 'context'}
VALID_ROLES = CORE_ROLES | NON_CORE_ROLES
CORE_EVENT_TIME_KINDS = {
    'observed_avalanche_release_time',
    'source_reported_avalanche_occurrence_time',
}
CORE_COORDINATE_PRECISIONS = {'exact_event_point', 'event_polygon'}
REVIEWED_OVERLAP_STATES = {'reviewed', 'clean'}
TARGET_REGIONS = {'himalayas_nepal', 'pir_panjal_nw_himalaya'}
SHA256_PATTERN = re.compile(r'^[0-9a-fA-F]{64}$')
SOURCE_ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_.-]*$')

REQUIRED_FIELDS = (
    'schema_version',
    'source_id',
    'source_name',
    'source_owner',
    'source_url',
    'source_reference',
    'source_role',
    'review_status',
    'license_review_id',
    'license',
    'coverage',
    'time_semantics',
    'spatial_semantics',
    'event_id_field',
    'provenance',
    'independence',
    'training_eligible',
    'production_scoring_eligible',
    'required_next_action',
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_is_timezone_aware(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return [item.strip() for item in value]


def _check_nonempty(mapping: dict[str, Any], field: str, errors: list[str]) -> None:
    if not _nonempty(mapping.get(field)):
        errors.append(f'{field} must be a non-empty string')


def _validate_event_rows(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate an optional canonical JSONL event-row representation.

    This check proves that a source-owner package can be normalized without
    losing identity, geography, or time precision.  It intentionally does
    not prove source independence or satisfy the reviewed-snapshot gate.
    """
    report: dict[str, Any] = {
        'path': str(path),
        'passed': False,
        'row_count': 0,
        'error_count': 0,
        'errors': [],
    }

    if not path.is_file():
        report['errors'] = [f'events JSONL path does not resolve to a file: {path}']
        report['error_count'] = 1
        return report

    report['event_rows_sha256'] = _sha256(path)
    expected_hash = str(manifest.get('event_rows_sha256') or '').lower()
    report['manifest_event_rows_sha256'] = expected_hash
    report['event_rows_hash_matches_manifest'] = bool(
        SHA256_PATTERN.fullmatch(expected_hash)
        and expected_hash == report['event_rows_sha256']
    )
    errors: list[str] = []
    if not SHA256_PATTERN.fullmatch(expected_hash):
        errors.append('manifest event_rows_sha256 must be a 64-character SHA-256 digest')
    elif expected_hash != report['event_rows_sha256']:
        errors.append('event_rows_sha256 does not match the canonical events JSONL')
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        report['errors'] = errors + [f'events JSONL could not be read: {exc}']
        report['error_count'] = len(report['errors'])
        return report

    rows: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    manifest_source_id = manifest.get('source_id')
    independence = manifest.get('independence')
    expected_source_family = (
        independence.get('origin_source_family')
        if isinstance(independence, dict)
        else None
    )
    coverage = manifest.get('coverage')
    manifest_regions = set(
        _string_list(coverage.get('regions')) or []
        if isinstance(coverage, dict)
        else []
    )

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            errors.append(f'line {line_number}: blank lines are not allowed in events JSONL')
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f'line {line_number}: invalid JSON: {exc.msg}')
            continue
        if not isinstance(value, dict):
            errors.append(f'line {line_number}: event row must be a JSON object')
            continue
        rows.append(value)

    report['row_count'] = len(rows)
    if not rows:
        errors.append('events JSONL must contain at least one event row')

    for row_index, row in enumerate(rows):
        prefix = f'row {row_index}'
        source_event_id = row.get('source_event_id')
        if not _nonempty(source_event_id):
            errors.append(f'{prefix}: source_event_id must be a non-empty string')
        elif source_event_id in seen_event_ids:
            errors.append(f'{prefix}: duplicate source_event_id: {source_event_id}')
        else:
            seen_event_ids.add(source_event_id)

        if not _nonempty(row.get('event_group_id')):
            errors.append(f'{prefix}: event_group_id must be a non-empty string')

        if row.get('origin_source_family') != expected_source_family:
            errors.append(f'{prefix}: origin_source_family does not match the source manifest')

        source_keys = [
            value for value in (row.get('source_key'), row.get('label_source'))
            if value is not None
        ]
        if not source_keys:
            errors.append(f'{prefix}: source_key or label_source is required')
        elif any(value != manifest_source_id for value in source_keys):
            errors.append(f'{prefix}: source_key/label_source does not match source_id')

        region_key = row.get('region_key')
        if not _nonempty(region_key):
            errors.append(f'{prefix}: region_key must be a non-empty string')
        elif region_key not in TARGET_REGIONS or region_key not in manifest_regions:
            errors.append(f'{prefix}: region_key is outside the manifest target coverage')

        latitude = row.get('lat', row.get('latitude'))
        longitude = row.get('lng', row.get('longitude'))
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool) or not math.isfinite(latitude):
            errors.append(f'{prefix}: latitude must be a finite number')
        elif not -90 <= latitude <= 90:
            errors.append(f'{prefix}: latitude is outside [-90, 90]')
        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool) or not math.isfinite(longitude):
            errors.append(f'{prefix}: longitude must be a finite number')
        elif not -180 <= longitude <= 180:
            errors.append(f'{prefix}: longitude is outside [-180, 180]')

        if row.get('label') not in (1, True):
            errors.append(f'{prefix}: label must be positive (1 or true)')

        if not _nonempty(row.get('source_reference', row.get('source_ref'))):
            errors.append(f'{prefix}: source_reference/source_ref must be supplied')

    time_report = validate_label_time_rows(
        rows,
        contract=LABEL_TIME_CONTRACT_EXACT_V1,
        require_feature_cutoff=False,
        include_row_inspections=True,
    )
    report['time_contract'] = time_report
    if not time_report['passed']:
        errors.append('event rows failed the exact_time_core_v1 time contract')

    report['errors'] = errors[:50]
    report['error_count'] = len(errors)
    report['passed'] = not errors
    return report


def _check_core_fields(
    manifest: dict[str, Any],
    errors: list[str],
    checks: dict[str, Any],
) -> None:
    review_status = manifest.get('review_status')
    checks['review_status'] = {'passed': review_status == 'approved', 'value': review_status}
    if review_status != 'approved':
        errors.append('review_status must be approved for exact-time core admission')

    license_review_id = manifest.get('license_review_id')
    checks['license_review_id'] = {
        'passed': _nonempty(license_review_id),
        'present': bool(_nonempty(license_review_id)),
    }
    if not _nonempty(license_review_id):
        errors.append('license_review_id must be supplied for exact-time core admission')

    license_value = manifest.get('license')
    license_data = license_value if isinstance(license_value, dict) else {}
    checks['license'] = {
        'passed': license_data.get('status') == 'permissive_core_reviewed',
        'status': license_data.get('status'),
    }
    if license_data.get('status') != 'permissive_core_reviewed':
        errors.append('license.status must be permissive_core_reviewed for core admission')
    _check_nonempty(license_data, 'reuse_scope', errors)
    if not isinstance(license_data.get('attribution_required'), bool):
        errors.append('license.attribution_required must be boolean')

    training_eligible = manifest.get('training_eligible')
    checks['training_eligible'] = {'passed': training_eligible is True, 'value': training_eligible}
    if training_eligible is not True:
        errors.append('training_eligible must be true only after core source review')
    if manifest.get('production_scoring_eligible') is not False:
        errors.append('production_scoring_eligible must remain false at source intake')

    coverage_value = manifest.get('coverage')
    coverage = coverage_value if isinstance(coverage_value, dict) else {}
    regions = _string_list(coverage.get('regions')) or []
    positive_seasons = _string_list(coverage.get('positive_seasons')) or []
    exact_seasons = _string_list(coverage.get('exact_time_positive_seasons')) or []
    checks['coverage'] = {
        'target_regions': sorted(set(regions) & TARGET_REGIONS),
        'positive_season_count': len(set(positive_seasons)),
        'exact_time_positive_season_count': len(set(exact_seasons)),
    }
    if not regions:
        errors.append('coverage.regions must be a non-empty list')
    elif not set(regions) & TARGET_REGIONS:
        errors.append('coverage.regions must include Nepal or Pir Panjal target coverage')
    if len(set(positive_seasons)) < 3:
        errors.append('coverage.positive_seasons must contain at least three unique seasons')
    if len(set(exact_seasons)) < 3:
        errors.append('coverage.exact_time_positive_seasons must contain at least three unique seasons')
    if not set(exact_seasons).issubset(set(positive_seasons)):
        errors.append('coverage.exact_time_positive_seasons must be a subset of positive_seasons')
    _check_nonempty(coverage, 'coverage_note', errors)

    time_value = manifest.get('time_semantics')
    time_data = time_value if isinstance(time_value, dict) else {}
    exact_time_passed = (
        time_data.get('event_time_kind') in CORE_EVENT_TIME_KINDS
        and time_data.get('precision') == 'exact'
        and time_data.get('release_time_proven') is True
        and time_data.get('source_time_is_avalanche_occurrence_time') is True
        and _nonempty(time_data.get('timezone'))
    )
    checks['time_semantics'] = {
        'passed': exact_time_passed,
        'event_time_kind': time_data.get('event_time_kind'),
        'precision': time_data.get('precision'),
    }
    if not exact_time_passed:
        errors.append(
            'time_semantics must prove an exact observed/source-reported avalanche occurrence time '
            'with a known timezone'
        )
    _check_nonempty(time_data, 'event_time_field', errors)

    event_rows_hash = manifest.get('event_rows_sha256')
    event_rows_hash_passed = (
        isinstance(event_rows_hash, str)
        and bool(SHA256_PATTERN.fullmatch(event_rows_hash))
    )
    checks['event_rows_sha256'] = {
        'passed': event_rows_hash_passed,
        'value_present': event_rows_hash_passed,
    }
    if not event_rows_hash_passed:
        errors.append('event_rows_sha256 must be a 64-character SHA-256 digest for core admission')

    spatial_value = manifest.get('spatial_semantics')
    spatial = spatial_value if isinstance(spatial_value, dict) else {}
    spatial_passed = (
        spatial.get('coordinate_precision') in CORE_COORDINATE_PRECISIONS
        and spatial.get('has_exact_coordinates') is True
        and _nonempty(spatial.get('coordinate_reference'))
    )
    checks['spatial_semantics'] = {
        'passed': spatial_passed,
        'coordinate_precision': spatial.get('coordinate_precision'),
    }
    if not spatial_passed:
        errors.append('spatial_semantics must identify exact event coordinates or polygons in a declared CRS')

    provenance_value = manifest.get('provenance')
    provenance = provenance_value if isinstance(provenance_value, dict) else {}
    source_hash = provenance.get('source_hash')
    provenance_passed = (
        isinstance(source_hash, str)
        and bool(SHA256_PATTERN.fullmatch(source_hash))
        and provenance.get('source_hash_algorithm') == 'sha256'
        and _timestamp_is_timezone_aware(provenance.get('retrieved_at'))
    )
    checks['provenance'] = {
        'passed': provenance_passed,
        'source_hash_algorithm': provenance.get('source_hash_algorithm'),
        'retrieved_at_timezone_aware': _timestamp_is_timezone_aware(provenance.get('retrieved_at')),
    }
    if not isinstance(source_hash, str) or not SHA256_PATTERN.fullmatch(source_hash):
        errors.append('provenance.source_hash must be a 64-character SHA-256 digest')
    if provenance.get('source_hash_algorithm') != 'sha256':
        errors.append('provenance.source_hash_algorithm must be sha256')
    if not _timestamp_is_timezone_aware(provenance.get('retrieved_at')):
        errors.append('provenance.retrieved_at must be a timezone-aware ISO-8601 timestamp')
    _check_nonempty(provenance, 'version_or_commit', errors)

    independence_value = manifest.get('independence')
    independence = independence_value if isinstance(independence_value, dict) else {}
    overlap_status = independence.get('overlap_review_status')
    independence_passed = (
        _nonempty(independence.get('origin_source_family'))
        and overlap_status in REVIEWED_OVERLAP_STATES
    )
    checks['independence'] = {
        'passed': independence_passed,
        'overlap_review_status': overlap_status,
    }
    if not _nonempty(independence.get('origin_source_family')):
        errors.append('independence.origin_source_family must be supplied')
    if overlap_status not in REVIEWED_OVERLAP_STATES:
        errors.append('independence.overlap_review_status must be reviewed or clean')

    evidence_refs = _string_list(manifest.get('evidence_refs')) or []
    checks['evidence_refs'] = {'passed': bool(evidence_refs), 'count': len(evidence_refs)}
    if not evidence_refs:
        errors.append('evidence_refs must contain at least one review artifact reference')


def validate_source_manifest(
    manifest: dict[str, Any],
    *,
    payload_path: Path | None = None,
    events_path: Path | None = None,
) -> dict[str, Any]:
    """Return an evidence report for one source-owner manifest."""
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    if not isinstance(manifest, dict):
        return {
            'validator_version': VALIDATOR_VERSION,
            'passed': False,
            'decision': 'blocked_invalid_source_manifest',
            'errors': ['source manifest must be a JSON object'],
            'warnings': [],
            'checks': {},
        }

    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    checks['required_fields'] = {'passed': not missing, 'missing': missing}
    errors.extend(f'missing required field: {field}' for field in missing)

    checks['schema_version'] = {
        'passed': manifest.get('schema_version') == SCHEMA_VERSION,
        'value': manifest.get('schema_version'),
    }
    if manifest.get('schema_version') != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')

    source_id = manifest.get('source_id')
    if not isinstance(source_id, str) or not SOURCE_ID_PATTERN.fullmatch(source_id):
        errors.append('source_id must match the lowercase source identifier pattern')
    for field in ('source_name', 'source_owner', 'source_url', 'source_reference', 'event_id_field', 'required_next_action'):
        _check_nonempty(manifest, field, errors)

    role = manifest.get('source_role')
    checks['source_role'] = {'passed': role in VALID_ROLES, 'value': role}
    if role not in VALID_ROLES:
        errors.append(f'source_role must be one of {sorted(VALID_ROLES)}')
    if not isinstance(manifest.get('training_eligible'), bool):
        errors.append('training_eligible must be boolean')
    if not isinstance(manifest.get('production_scoring_eligible'), bool):
        errors.append('production_scoring_eligible must be boolean')

    if role in CORE_ROLES:
        _check_core_fields(manifest, errors, checks)
    elif role in NON_CORE_ROLES:
        if manifest.get('training_eligible') is not False:
            errors.append('non-core source roles must have training_eligible=false')
        if manifest.get('production_scoring_eligible') is not False:
            errors.append('non-core source roles must have production_scoring_eligible=false')
        warnings.append('non-core source roles remain shadow/benchmark/context evidence only')

    payload_report: dict[str, Any] = {
        'required': role == 'core',
        'passed': role != 'core',
    }
    if payload_path is not None:
        payload_path = Path(payload_path).expanduser()
        payload_report['path'] = str(payload_path)
        if not payload_path.is_file():
            errors.append(f'payload path does not resolve to a file: {payload_path}')
            payload_report['passed'] = False
        else:
            actual_hash = _sha256(payload_path)
            payload_report['actual_sha256'] = actual_hash
            expected_hash = str((manifest.get('provenance') or {}).get('source_hash') or '').lower()
            payload_report['expected_sha256'] = expected_hash
            payload_report['passed'] = bool(expected_hash) and actual_hash == expected_hash
            if not payload_report['passed']:
                errors.append('payload hash mismatch: provenance.source_hash does not match payload file')
    elif role == 'core':
        payload_report['passed'] = False
        errors.append('payload path is required for exact-time core admission')
    checks['payload_hash'] = payload_report

    if events_path is None:
        checks['event_rows'] = {
            'required': role in CORE_ROLES,
            'passed': role not in CORE_ROLES,
            'not_supplied': True,
        }
        if role in CORE_ROLES:
            errors.append('event rows path is required for exact-time core admission')
    else:
        event_rows_report = _validate_event_rows(Path(events_path).expanduser(), manifest)
        checks['event_rows'] = event_rows_report
        if not event_rows_report['passed']:
            errors.append('event rows failed canonical source-row validation')
            errors.extend(str(error) for error in event_rows_report.get('errors', [])[:50])

    if errors:
        decision = (
            'blocked_source_request_pending'
            if role == 'requested_core'
            else 'blocked_invalid_source_manifest'
        )
        passed = False
    elif role in NON_CORE_ROLES:
        decision = 'shadow_manifest_valid_not_core'
        passed = False
    elif role == 'requested_core':
        decision = 'blocked_source_request_pending'
        passed = False
    else:
        decision = 'source_manifest_accepted_for_normalization'
        passed = True

    return {
        'validator_version': VALIDATOR_VERSION,
        'source_id': source_id,
        'source_role': role,
        'passed': passed,
        'decision': decision,
        'errors': sorted(set(errors)),
        'warnings': warnings,
        'checks': checks,
        'next_gate': 'build a reviewed event snapshot and run strict metadata-only preflight' if passed else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--events-jsonl', type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report = {
            'validator_version': VALIDATOR_VERSION,
            'passed': False,
            'decision': 'blocked_invalid_source_manifest',
            'errors': [f'could not load manifest: {exc}'],
            'warnings': [],
            'checks': {},
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    report = validate_source_manifest(
        manifest,
        payload_path=args.payload,
        events_path=args.events_jsonl,
    )
    report['manifest_path'] = str(args.manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
