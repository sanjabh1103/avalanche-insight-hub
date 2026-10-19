#!/usr/bin/env python3
"""Build a deterministic, rights-pending BIPAD avalanche candidate snapshot.

This adapter intentionally accepts only a locally pinned JSON response.  It
does not fetch the live API, because a mutable endpoint is not reproducible
training evidence.  BIPAD ``incidentOn`` values at local midnight are kept as
day-resolution intervals; the adapter never turns them into exact event
timestamps.  The resulting snapshot is always shadow/benchmark evidence until
written reuse rights, source-family independence, and overlap review exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.common.regions import load_regions


SOURCE_KEY = 'bipad_nepal_avalanche_candidate'
ORIGIN_SOURCE_FAMILY = 'bipad_drr_api'
BIPAD_API_DOC_URL = 'https://bipadportal.gov.np/api/'
BIPAD_INCIDENT_API_URL = 'https://bipadportal.gov.np/api/v1/incident/?hazard=3&limit=1000'
BIPAD_INCIDENT_DETAIL_URL = 'https://bipadportal.gov.np/api/v1/incident/'
BIPAD_AVALANCHE_HAZARD_ID = 3
TARGET_REGIONS = ('himalayas_nepal',)
REGION_SEASON_START_MONTHS = {'himalayas_nepal': 11}
EXACT_TIME_PRECISION_MARKERS = {'timestamp', 'instant', 'exact_timestamp', 'exact'}


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    ).encode('utf-8')


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float('inf') else None


def _hazard_id(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get('id')
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_incident_on(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    normalized = text[:-1] + '+00:00' if text.endswith('Z') else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _timestamp_precision(raw: dict[str, Any]) -> str:
    """Require an explicit source precision declaration before using clock time."""
    declared = _clean(
        raw.get('incidentTimePrecision')
        or raw.get('timestampPrecision')
        or raw.get('timePrecision')
    ).lower()
    if declared in EXACT_TIME_PRECISION_MARKERS:
        return 'timestamp'
    # BIPAD currently returns midnight placeholders for date-level incidents.
    # Even a future non-midnight value remains day-level unless the payload
    # explicitly states that the clock time is exact.
    return 'day'


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _season_id(event_date: date, region_key: str) -> str:
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    season_year = event_date.year if event_date.month >= start_month else event_date.year - 1
    return f'{season_year}-{season_year + 1}'


def _within_region(lat: float, lng: float, bounds: tuple[float, float, float, float]) -> bool:
    lat_min, lng_min, lat_max, lng_max = bounds
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _target_bounds() -> dict[str, tuple[float, float, float, float]]:
    regions = {region.key: region for region in load_regions()}
    missing = [key for key in TARGET_REGIONS if key not in regions]
    if missing:
        raise ValueError(f'configured target regions are missing: {missing}')
    return {key: regions[key].bbox for key in TARGET_REGIONS}


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get('results'), list):
        records = payload['results']
    else:
        raise ValueError('BIPAD payload must be a list or an object containing results[]')
    if not all(isinstance(record, dict) for record in records):
        raise ValueError('BIPAD results[] must contain JSON objects')
    return records


def build_snapshot(
    raw_payload: bytes,
    *,
    target_regions: dict[str, tuple[float, float, float, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize a pinned BIPAD JSON response without asserting license clearance."""
    payload = json.loads(raw_payload.decode('utf-8'))
    source_records = _records_from_payload(payload)
    source_payload_sha256 = hashlib.sha256(raw_payload).hexdigest()
    rows: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    seen_ids: set[str] = set()

    for raw in source_records:
        source_id = _clean(raw.get('id'))
        if not source_id:
            excluded['missing_incident_id'] += 1
            continue
        if source_id in seen_ids:
            excluded['duplicate_incident_id'] += 1
            continue
        seen_ids.add(source_id)
        if _hazard_id(raw.get('hazard')) != BIPAD_AVALANCHE_HAZARD_ID:
            excluded['unsupported_hazard'] += 1
            continue
        if raw.get('verified') is not True or raw.get('approved') is not True:
            excluded['unverified_or_unapproved'] += 1
            continue
        point = raw.get('point') if isinstance(raw.get('point'), dict) else {}
        coordinates = point.get('coordinates') if isinstance(point.get('coordinates'), list) else []
        if len(coordinates) < 2:
            excluded['invalid_point'] += 1
            continue
        lng = _number(coordinates[0])
        lat = _number(coordinates[1])
        if lat is None or lng is None or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            excluded['invalid_coordinates'] += 1
            continue
        region_key = next(
            (
                key for key, bounds in target_regions.items()
                if _within_region(lat, lng, bounds)
            ),
            None,
        )
        if region_key is None:
            excluded['outside_target_regions'] += 1
            continue
        incident_on = _parse_incident_on(raw.get('incidentOn'))
        if incident_on is None:
            excluded['missing_or_unparseable_incident_on'] += 1
            continue

        precision = _timestamp_precision(raw)
        event_start = incident_on.astimezone(timezone.utc)
        event_end = event_start + timedelta(days=1)
        row_hash = hashlib.sha256(_canonical_bytes(raw)).hexdigest()
        row: dict[str, Any] = {
            'source_key': SOURCE_KEY,
            'origin_source_family': ORIGIN_SOURCE_FAMILY,
            'external_id': f'bipad-{source_id}',
            'source_event_id': source_id,
            'event_group_id': f'bipad:{source_id}',
            'region_key': region_key,
            'event_time_start': _utc_iso(event_start),
            'event_time_end': _utc_iso(event_end),
            'lat': lat,
            'lng': lng,
            'label': 1,
            'label_confidence': 0.6,
            'training_weight': 0.3,
            'training_eligible': False,
            'production_scoring_eligible': False,
            'location_precision': 'point_from_bipad_incident_api',
            'timestamp_precision': precision,
            'source_row_sha256': row_hash,
            'source_reference': f'{BIPAD_INCIDENT_DETAIL_URL}{source_id}/',
            'metadata': {
                'source_url': BIPAD_INCIDENT_API_URL,
                'source_api_docs': BIPAD_API_DOC_URL,
                'hazard_id': BIPAD_AVALANCHE_HAZARD_ID,
                'incident_on_original': _clean(raw.get('incidentOn')),
                'incident_time_precision_declared': _clean(
                    raw.get('incidentTimePrecision')
                    or raw.get('timestampPrecision')
                    or raw.get('timePrecision')
                ) or None,
                'title': _clean(raw.get('title')),
                'source': _clean(raw.get('source')),
                'data_source': _clean(raw.get('dataSource')),
                'data_source_id': raw.get('dataSourceId'),
                'verified': raw.get('verified'),
                'approved': raw.get('approved'),
                'license_status': 'pending_rights_review',
            },
        }
        if precision == 'timestamp':
            row['event_time'] = _utc_iso(event_start)
        rows.append(row)

    rows.sort(key=lambda row: (row['region_key'], row['event_time_start'], row['external_id']))
    seasons = sorted({
        _season_id(
            datetime.fromisoformat(row['metadata']['incident_on_original'].replace('Z', '+00:00')).date(),
            row['region_key'],
        )
        for row in rows
    })
    seasons_by_region = {
        region_key: sorted({
            _season_id(
                datetime.fromisoformat(row['metadata']['incident_on_original'].replace('Z', '+00:00')).date(),
                region_key,
            )
            for row in rows if row['region_key'] == region_key
        })
        for region_key in sorted(target_regions)
    }
    precision_counts = Counter(str(row['timestamp_precision']) for row in rows)
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    manifest = {
        'snapshot_schema_version': 'mvp4_bipad_candidate_snapshot_v1',
        'source_key': SOURCE_KEY,
        'source_keys': [SOURCE_KEY],
        'source_role': 'independent_public_api_candidate_shadow',
        'source_url': BIPAD_API_DOC_URL,
        'source_api_url': BIPAD_INCIDENT_API_URL,
        'hazard_id': BIPAD_AVALANCHE_HAZARD_ID,
        'source_payload_filename': 'raw_api_response.json',
        'source_payload_sha256': source_payload_sha256,
        'license': 'BIPAD API reuse/model-training terms pending written review',
        'license_status': 'pending_rights_review',
        'license_review_id': None,
        'target_regions': target_regions,
        'region_season_start_months': REGION_SEASON_START_MONTHS,
        'raw_record_count': len(source_records),
        'included_record_count': len(rows),
        'excluded_record_counts': dict(sorted(excluded.items())),
        'event_rows_sha256': hashlib.sha256(event_bytes).hexdigest(),
        'positive_season_ids': seasons,
        'positive_season_count': len(seasons),
        'positive_seasons_by_region': seasons_by_region,
        'timestamp_precision_counts': dict(sorted(precision_counts.items())),
        'exact_timestamp_record_count': precision_counts.get('timestamp', 0),
        'required_independent_positive_sources': [SOURCE_KEY, 'hiaval_hma'],
        'required_independent_origin_families': [ORIGIN_SOURCE_FAMILY, 'hiaval_literature_database'],
        'minimum_positive_sources': 2,
        'minimum_positive_seasons': 3,
        'minimum_positive_event_groups': 30,
        'source_overlap_report': 'source_overlap_report.json',
        'snapshot_role': 'shadow_candidate_pending_rights_and_overlap_review',
        'training_eligible': False,
        'production_scoring_eligible': False,
        'review_status': 'pending_rights_and_overlap_review',
        'required_next_action': (
            'Obtain written BIPAD reuse/model-training terms, deduplicate against HiAVAL, '
            'prove an independent origin family, and retain only true exact-time rows for '
            'any future core-training consideration.'
        ),
    }
    return rows, manifest


def write_snapshot(
    output_dir: Path,
    raw_payload: bytes,
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'raw_api_response.json').write_bytes(raw_payload)
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    (output_dir / 'events.jsonl').write_bytes(event_bytes)
    (output_dir / 'snapshot_manifest.json').write_text(
        json.dumps({**manifest, 'events_path': 'events.jsonl'}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    overlap_report = {
        'version': 'mvp4_source_overlap_report_v1',
        'status': 'pending_rights_and_overlap_review',
        'source_a': SOURCE_KEY,
        'source_b': 'hiaval_hma',
        'source_a_sha256': manifest['source_payload_sha256'],
        'source_b_sha256': None,
        'source_a_record_count': manifest['included_record_count'],
        'source_b_record_count': None,
        'source_a_non_overlap_count': None,
        'source_b_non_overlap_count': None,
        'independent_positive_source_count': 0,
        'deduplication_key': [
            'region_key',
            'local_incident_date',
            'spatial_distance_km<=5',
            'source_reference/title review',
        ],
        'same_event_must_not_count_as_independent': True,
        'required_next_input': 'hash-pinned HiAVAL snapshot and human overlap/origin review',
    }
    (output_dir / 'source_overlap_report.json').write_text(
        json.dumps(overlap_report, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    (output_dir / 'ATTRIBUTION.md').write_text(
        '# BIPAD candidate attribution\n\n'
        f'- API documentation: [{BIPAD_API_DOC_URL}]({BIPAD_API_DOC_URL})\n'
        f'- Incident endpoint: `{BIPAD_INCIDENT_API_URL}`\n'
        f'- Pinned payload SHA-256: `{manifest["source_payload_sha256"]}`\n'
        '- Current reuse/model-training terms: pending written rights review.\n\n'
        'This is an offline replayable candidate snapshot. Records are included '
        'only when the API marks them as avalanche, verified, approved, and '
        'coordinate-valid inside the Nepal pilot AOI. Midnight incidentOn values '
        'are day intervals, not exact event timestamps. The snapshot is not '
        'training- or production-scoring-eligible.\n',
        encoding='utf-8',
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-json', type=Path, required=True, help='Pinned local BIPAD API response JSON')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    raw_payload = args.input_json.read_bytes()
    rows, manifest = build_snapshot(raw_payload, target_regions=_target_bounds())
    write_snapshot(args.output_dir, raw_payload, rows, manifest)
    print(json.dumps({
        'output_dir': str(args.output_dir),
        'source_payload_sha256': manifest['source_payload_sha256'],
        'event_rows_sha256': manifest['event_rows_sha256'],
        'included_record_count': manifest['included_record_count'],
        'positive_season_count': manifest['positive_season_count'],
        'exact_timestamp_record_count': manifest['exact_timestamp_record_count'],
        'review_status': manifest['review_status'],
        'training_eligible': manifest['training_eligible'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
