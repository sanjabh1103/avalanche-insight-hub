#!/usr/bin/env python3
"""Compare two positive-event snapshots without querying a live service.

The report is deliberately conservative: records are matched only when their
region and UTC calendar date agree and their coordinates are within the
configured distance threshold.  A match is consumed at most once per source
so the same event cannot be counted as independent corroboration twice.

The default output is ``computed_pending_review``.  A caller must explicitly
pass ``--mark-reviewed --reviewed-by ...`` after reviewing the source hashes,
match list, and license evidence before the metadata preflight can accept it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_VERSION = 'mvp4_source_overlap_report_v2'
DEFAULT_DISTANCE_KM = 5.0
_POINT_RE = re.compile(r'POINT\s*\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)', re.IGNORECASE)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def _load_records(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    payload = path.read_bytes()
    if not payload.strip():
        raise ValueError(f'event snapshot is empty: {path}')
    if path.suffix.lower() == '.jsonl':
        records = [json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]
    else:
        decoded = json.loads(payload.decode('utf-8'))
        if isinstance(decoded, dict) and isinstance(decoded.get('records'), list):
            records = decoded['records']
        elif isinstance(decoded, list):
            records = decoded
        else:
            records = [decoded]
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ValueError(f'event snapshot must contain JSON objects: {path}')
    return records, payload


def _parse_time(raw: Any) -> datetime | None:
    value = str(raw or '').strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coordinates(record: dict[str, Any]) -> tuple[float, float] | None:
    lat = record.get('lat', record.get('latitude'))
    lng = record.get('lng', record.get('lon', record.get('longitude')))
    location = record.get('location')
    if (lat is None or lng is None) and isinstance(location, dict):
        coordinates = location.get('coordinates')
        if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
            lng, lat = coordinates[0], coordinates[1]
    if (lat is None or lng is None) and isinstance(location, str):
        match = _POINT_RE.search(location)
        if match:
            lng, lat = match.group(1), match.group(2)
    try:
        lat_value = float(lat)
        lng_value = float(lng)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat_value) or not math.isfinite(lng_value):
        return None
    if not -90.0 <= lat_value <= 90.0 or not -180.0 <= lng_value <= 180.0:
        return None
    return lat_value, lng_value


def _scene_ids(record: dict[str, Any]) -> list[str]:
    values = record.get('source_scene_ids')
    if not isinstance(values, list):
        features = record.get('features')
        values = features.get('sar_scene_ids') if isinstance(features, dict) else None
    if not isinstance(values, list):
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _event_id(record: dict[str, Any], source_key: str, index: int) -> str:
    for key in ('external_id', 'source_event_id', 'event_id', 'id', 'detection_id'):
        value = str(record.get(key) or '').strip()
        if value:
            return value
    return f'{source_key}:row-{index + 1}'


def _normalise_records(
    records: list[dict[str, Any]],
    *,
    source_key: str,
    require_scene_ids: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    valid: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    seen_ids: set[str] = set()

    def reject(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for index, record in enumerate(records):
        event_id = _event_id(record, source_key, index)
        if event_id in seen_ids:
            reject('duplicate_event_id')
            continue
        event_time = _parse_time(record.get('event_time') or record.get('timestamp') or record.get('event_date') or record.get('date'))
        if event_time is None:
            reject('invalid_event_time')
            continue
        coordinates = _coordinates(record)
        if coordinates is None:
            reject('invalid_coordinates')
            continue
        region_key = str(record.get('region_key') or record.get('region') or '').strip()
        if not region_key:
            reject('missing_region_key')
            continue
        scene_ids = _scene_ids(record)
        if require_scene_ids and not scene_ids:
            reject('missing_source_scene_ids')
            continue
        seen_ids.add(event_id)
        valid.append({
            'event_id': event_id,
            'source_key': source_key,
            'event_date': event_time.date().isoformat(),
            'event_time': event_time.isoformat().replace('+00:00', 'Z'),
            'region_key': region_key,
            'lat': round(coordinates[0], 9),
            'lng': round(coordinates[1], 9),
            'source_scene_ids': scene_ids,
        })
    valid.sort(key=lambda row: (row['region_key'], row['event_date'], row['event_id']))
    return valid, dict(sorted(excluded.items()))


def _distance_km(first: dict[str, Any], second: dict[str, Any]) -> float:
    radius_km = 6371.0088
    lat1 = math.radians(float(first['lat']))
    lat2 = math.radians(float(second['lat']))
    dlat = lat2 - lat1
    dlng = math.radians(float(second['lng']) - float(first['lng']))
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return radius_km * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def _match_records(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
    *,
    max_distance_km: float,
) -> list[dict[str, Any]]:
    candidates: list[tuple[float, str, str, dict[str, Any], dict[str, Any]]] = []
    for left in first:
        for right in second:
            if left['region_key'] != right['region_key'] or left['event_date'] != right['event_date']:
                continue
            distance = _distance_km(left, right)
            if distance <= max_distance_km:
                candidates.append((distance, left['event_id'], right['event_id'], left, right))
    candidates.sort(key=lambda value: (value[0], value[1], value[2]))
    used_first: set[str] = set()
    used_second: set[str] = set()
    matches: list[dict[str, Any]] = []
    for distance, left_id, right_id, left, right in candidates:
        if left_id in used_first or right_id in used_second:
            continue
        used_first.add(left_id)
        used_second.add(right_id)
        matches.append({
            'source_a_event_id': left_id,
            'source_b_event_id': right_id,
            'region_key': left['region_key'],
            'event_date': left['event_date'],
            'distance_km': round(distance, 6),
            'source_b_scene_ids': right['source_scene_ids'],
        })
    return matches


def build_overlap_report(
    first_payload: bytes,
    second_payload: bytes,
    first_records: list[dict[str, Any]],
    second_records: list[dict[str, Any]],
    *,
    source_a_key: str,
    source_b_key: str,
    max_distance_km: float = DEFAULT_DISTANCE_KM,
    mark_reviewed: bool = False,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    if source_a_key == source_b_key:
        raise ValueError('source_a_key and source_b_key must be different')
    if max_distance_km <= 0 or not math.isfinite(max_distance_km):
        raise ValueError('max_distance_km must be finite and greater than zero')
    if mark_reviewed and not str(reviewed_by or '').strip():
        raise ValueError('--mark-reviewed requires --reviewed-by')

    first, first_excluded = _normalise_records(first_records, source_key=source_a_key, require_scene_ids=False)
    second, second_excluded = _normalise_records(second_records, source_key=source_b_key, require_scene_ids=True)
    matches = _match_records(first, second, max_distance_km=max_distance_km)
    matched_first = {match['source_a_event_id'] for match in matches}
    matched_second = {match['source_b_event_id'] for match in matches}
    non_overlap_a = len(first) - len(matched_first)
    non_overlap_b = len(second) - len(matched_second)
    independent_source_count = int(non_overlap_a > 0) + int(non_overlap_b > 0)
    status = 'reviewed' if mark_reviewed else 'computed_pending_review'
    report: dict[str, Any] = {
        'version': REPORT_VERSION,
        'status': status,
        'reviewed_by': str(reviewed_by).strip() if mark_reviewed else None,
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z') if mark_reviewed else None,
        'source_a': source_a_key,
        'source_b': source_b_key,
        'source_a_sha256': hashlib.sha256(first_payload).hexdigest(),
        'source_b_sha256': hashlib.sha256(second_payload).hexdigest(),
        'source_a_record_count': len(first),
        'source_b_record_count': len(second),
        'source_a_excluded_counts': first_excluded,
        'source_b_excluded_counts': second_excluded,
        'matching_policy': {
            'same_event_requires_same_region_and_utc_date': True,
            'max_spatial_distance_km': max_distance_km,
            'one_to_one_greedy_match_sorted_by_distance': True,
        },
        'deduplication_key': ['region_key', 'event_date', f'spatial_distance_km<={max_distance_km:g}'],
        'overlap_count': len(matches),
        'source_a_non_overlap_count': non_overlap_a,
        'source_b_non_overlap_count': non_overlap_b,
        'independent_positive_source_count': independent_source_count,
        'same_event_must_not_count_as_independent': True,
        'review_decision': 'approved_two_source_lane' if independent_source_count >= 2 else 'blocked_duplicate_only_or_empty_source',
        'matches': matches,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-a', type=Path, required=True)
    parser.add_argument('--source-b', type=Path, required=True)
    parser.add_argument('--source-a-key', default='hiaval_hma')
    parser.add_argument('--source-b-key', default='gee_sar')
    parser.add_argument('--max-distance-km', type=float, default=DEFAULT_DISTANCE_KM)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mark-reviewed', action='store_true')
    parser.add_argument('--reviewed-by')
    args = parser.parse_args(argv)

    first_records, first_payload = _load_records(args.source_a)
    second_records, second_payload = _load_records(args.source_b)
    report = build_overlap_report(
        first_payload,
        second_payload,
        first_records,
        second_records,
        source_a_key=args.source_a_key,
        source_b_key=args.source_b_key,
        max_distance_km=args.max_distance_km,
        mark_reviewed=args.mark_reviewed,
        reviewed_by=args.reviewed_by,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(report))
    print(json.dumps({
        'output': str(args.output),
        'status': report['status'],
        'overlap_count': report['overlap_count'],
        'source_a_non_overlap_count': report['source_a_non_overlap_count'],
        'source_b_non_overlap_count': report['source_b_non_overlap_count'],
        'independent_positive_source_count': report['independent_positive_source_count'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
