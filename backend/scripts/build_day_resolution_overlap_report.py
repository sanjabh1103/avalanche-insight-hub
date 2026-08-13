#!/usr/bin/env python3
"""Compare two day/interval avalanche snapshots without inventing timestamps.

This adapter is for provenance and deduplication review only.  It requires an
explicit half-open ``event_time_start``/``event_time_end`` interval in each
row, matches only overlapping intervals in the same region and within the
configured distance, and never derives an ``event_time`` or interval midpoint.
The resulting report cannot make a day-resolution source eligible for exact-
time core training.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_VERSION = 'mvp4_day_resolution_overlap_report_v1'
DEFAULT_DISTANCE_KM = 5.0
SUPPORTED_INTERVAL_PRECISIONS = {
    'day',
    'bounded_interval',
    'bounded_12_day_detection_interval',
    'interval',
}


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    ).encode('utf-8')


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _point(record: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lat = float(record['lat'])
        lng = float(record['lng'])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lng):
        return None
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lng <= 180.0:
        return None
    return lat, lng


def _distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    radius_km = 6371.0088
    lat1, lng1 = first
    lat2, lng2 = second
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    haversine = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def _event_id(record: dict[str, Any], source_key: str, index: int) -> str:
    for key in ('external_id', 'source_event_id', 'event_id', 'id'):
        value = str(record.get(key) or '').strip()
        if value:
            return value
    return f'{source_key}:row-{index + 1}'


def _normalise_records(
    records: list[dict[str, Any]],
    *,
    source_key: str,
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
        precision = str(record.get('timestamp_precision') or '').strip().lower()
        if precision not in SUPPORTED_INTERVAL_PRECISIONS:
            reject('unsupported_or_missing_interval_precision')
            continue
        start = _parse_time(record.get('event_time_start'))
        end = _parse_time(record.get('event_time_end'))
        if start is None or end is None or end <= start:
            reject('missing_or_invalid_interval')
            continue
        point = _point(record)
        if point is None:
            reject('invalid_coordinates')
            continue
        region_key = str(record.get('region_key') or '').strip()
        if not region_key:
            reject('missing_region_key')
            continue
        seen_ids.add(event_id)
        valid.append({
            'event_id': event_id,
            'region_key': region_key,
            'interval_start': start,
            'interval_end': end,
            'point': point,
            'timestamp_precision': precision,
        })
    valid.sort(key=lambda row: (row['region_key'], row['interval_start'], row['event_id']))
    return valid, dict(sorted(excluded.items()))


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

    first, first_excluded = _normalise_records(first_records, source_key=source_a_key)
    second, second_excluded = _normalise_records(second_records, source_key=source_b_key)
    candidates: list[tuple[float, str, str, dict[str, Any], dict[str, Any]]] = []
    for left in first:
        for right in second:
            if left['region_key'] != right['region_key']:
                continue
            intervals_overlap = (
                left['interval_start'] < right['interval_end']
                and right['interval_start'] < left['interval_end']
            )
            if not intervals_overlap:
                continue
            distance = _distance_km(left['point'], right['point'])
            if distance <= max_distance_km:
                candidates.append((distance, left['event_id'], right['event_id'], left, right))
    candidates.sort(key=lambda value: (value[0], value[1], value[2]))
    used_a: set[str] = set()
    used_b: set[str] = set()
    matches: list[dict[str, Any]] = []
    for distance, left_id, right_id, left, right in candidates:
        if left_id in used_a or right_id in used_b:
            continue
        used_a.add(left_id)
        used_b.add(right_id)
        matches.append({
            'source_a_event_id': left_id,
            'source_b_event_id': right_id,
            'region_key': left['region_key'],
            'source_a_interval_start': left['interval_start'].isoformat().replace('+00:00', 'Z'),
            'source_a_interval_end': left['interval_end'].isoformat().replace('+00:00', 'Z'),
            'source_b_interval_start': right['interval_start'].isoformat().replace('+00:00', 'Z'),
            'source_b_interval_end': right['interval_end'].isoformat().replace('+00:00', 'Z'),
            'distance_km': round(distance, 6),
        })
    non_overlap_a = len(first) - len(used_a)
    non_overlap_b = len(second) - len(used_b)
    independent_source_count = int(non_overlap_a > 0) + int(non_overlap_b > 0)
    return {
        'version': REPORT_VERSION,
        'status': 'reviewed' if mark_reviewed else 'computed_pending_review',
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
            'explicit_intervals_only': True,
            'half_open_interval_overlap': True,
            'same_region_required': True,
            'max_spatial_distance_km': max_distance_km,
            'one_to_one_greedy_match_sorted_by_distance': True,
            'midpoint_substitution_used': False,
            'event_time_synthesis_used': False,
        },
        'overlap_count': len(matches),
        'source_a_non_overlap_count': non_overlap_a,
        'source_b_non_overlap_count': non_overlap_b,
        'independent_positive_source_count': independent_source_count,
        'same_event_must_not_count_as_independent': True,
        'review_decision': (
            'approved_shadow_day_resolution_two_source_lane'
            if mark_reviewed and independent_source_count >= 2
            else 'pending_day_resolution_rights_and_overlap_review'
        ),
        'matches': matches,
    }


def _load_records(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    payload = path.read_bytes()
    records = [json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]
    if not records or not all(isinstance(record, dict) for record in records):
        raise ValueError(f'event snapshot must contain JSON objects: {path}')
    return records, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-a', type=Path, required=True)
    parser.add_argument('--source-b', type=Path, required=True)
    parser.add_argument('--source-a-key', default='hiaval_hma')
    parser.add_argument('--source-b-key', default='bipad_nepal_avalanche_candidate')
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
