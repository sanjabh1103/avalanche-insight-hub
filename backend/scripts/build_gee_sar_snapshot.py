#!/usr/bin/env python3
"""Export a bounded, provenance-auditable ``gee_sar`` event snapshot.

This exporter is read-only with respect to Supabase.  It intentionally refuses
to call database row IDs ``source_scene_ids``: scene provenance must already be
present in the source row or the resulting snapshot remains blocked for core
training and independent-source review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.common.supabase_io import rest_get


REGION_SEASON_START_MONTHS = {
    'himalayas_nepal': 11,
    'pir_panjal_nw_himalaya': 11,
}
DEFAULT_REGIONS = tuple(REGION_SEASON_START_MONTHS)
DEFAULT_PAGE_SIZE = 1000
_POINT_RE = re.compile(r'POINT\s*\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)', re.IGNORECASE)


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def _parse_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, str):
        return None
    match = _POINT_RE.search(value)
    if match:
        try:
            lng = float(match.group(1))
            lat = float(match.group(2))
        except ValueError:
            return None
    else:
        # PostgREST may serialize a PostGIS point as EWKB hex, e.g.
        # 0101000020E6100000<little-endian-lng><little-endian-lat>.
        try:
            payload = bytes.fromhex(value.strip())
            if len(payload) < 21 or payload[0] not in (0, 1):
                return None
            endian = '<' if payload[0] == 1 else '>'
            geometry_type = struct.unpack_from(f'{endian}I', payload, 1)[0]
            offset = 9 if geometry_type & 0x20000000 else 5
            if len(payload) < offset + 16:
                return None
            lng, lat = struct.unpack_from(f'{endian}dd', payload, offset)
        except (ValueError, struct.error):
            return None
    if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
        return None
    return lat, lng


def _parse_timestamp(value: Any) -> datetime | None:
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


def _season_id(timestamp: datetime, region_key: str) -> str:
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    year = timestamp.year if timestamp.month >= start_month else timestamp.year - 1
    return f'{year}-{year + 1}'


def _scene_ids(row: dict[str, Any]) -> list[str]:
    values = row.get('source_scene_ids')
    if not isinstance(values, list):
        values = []
    if not values and isinstance(row.get('features'), dict):
        features = row['features']
        for key in ('source_scene_ids', 'sar_scene_ids', 'scene_ids'):
            if isinstance(features.get(key), list):
                values = features[key]
                break
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _source_row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(row)).hexdigest()


def _normalise_rows(raw_rows: Iterable[dict[str, Any]], *, region_key: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    normalized: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for row in raw_rows:
        row_id = str(row.get('id') or '').strip()
        if not row_id:
            excluded['missing_row_id'] += 1
            continue
        if row_id in seen_ids:
            excluded['duplicate_row_id'] += 1
            continue
        timestamp = _parse_timestamp(row.get('timestamp'))
        if timestamp is None:
            excluded['invalid_timestamp'] += 1
            continue
        point = _parse_point(row.get('location'))
        if point is None:
            excluded['invalid_location'] += 1
            continue
        features = row.get('features') if isinstance(row.get('features'), dict) else {}
        observed_region = str(features.get('region_key') or region_key).strip()
        if observed_region != region_key:
            excluded['region_mismatch'] += 1
            continue
        scene_ids = _scene_ids(row)
        provenance_review_status = str(
            row.get('source_provenance_review_status')
            or features.get('source_provenance_review_status')
            or ''
        ).strip().lower() or None
        seen_ids.add(row_id)
        normalized.append({
            'source_key': 'gee_sar',
            'external_id': f'gee-sar-{row_id}',
            'source_event_id': row_id,
            'region_key': region_key,
            'event_time': timestamp.isoformat().replace('+00:00', 'Z'),
            'lat': point[0],
            'lng': point[1],
            'label': 1,
            'label_confidence': 0.9,
            'training_weight': 0.9,
            'source_scene_ids': scene_ids,
            'source_provenance_review_status': provenance_review_status,
            'location_precision': 'point_from_event_location',
            'timestamp_precision': 'timestamp',
            'source_row_sha256': _source_row_hash(row),
            'metadata': {
                'source_row_id': row_id,
                'source': str(row.get('source') or 'gee_sar'),
                'ingest_type': features.get('ingest_type'),
                'scene_count': features.get('scene_count'),
                'sar_mean_sensing_time': features.get('sar_mean_sensing_time'),
                'source_table': 'avalanche_events_decayed',
            },
        })
    normalized.sort(key=lambda item: (item['region_key'], item['event_time'], item['external_id']))
    return normalized, dict(sorted(excluded.items()))


def build_snapshot(raw_rows_by_region: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    for region_key in sorted(raw_rows_by_region):
        region_rows, region_excluded = _normalise_rows(raw_rows_by_region[region_key], region_key=region_key)
        rows.extend(region_rows)
        excluded.update(region_excluded)
    rows.sort(key=lambda item: (item['region_key'], item['event_time'], item['external_id']))
    seasons = sorted({
        _season_id(datetime.fromisoformat(row['event_time'].replace('Z', '+00:00')), row['region_key'])
        for row in rows
    })
    seasons_by_region = {
        region_key: sorted({
            _season_id(datetime.fromisoformat(row['event_time'].replace('Z', '+00:00')), region_key)
            for row in rows if row['region_key'] == region_key
        })
        for region_key in sorted(raw_rows_by_region)
    }
    scene_id_count = sum(1 for row in rows if row['source_scene_ids'])
    approved_core_provenance_count = sum(
        1 for row in rows if row.get('source_provenance_review_status') == 'approved_core'
    )
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    manifest = {
        'snapshot_schema_version': 'mvp4_gee_sar_snapshot_v1',
        'source_key': 'gee_sar',
        'source_role': 'internal_sar_derived_label_candidate',
        'source_table': 'avalanche_events_decayed',
        'source_license_status': 'unreviewed_internal_source',
        'region_season_start_months': REGION_SEASON_START_MONTHS,
        'raw_record_count': sum(len(value) for value in raw_rows_by_region.values()),
        'included_record_count': len(rows),
        'excluded_record_counts': dict(sorted(excluded.items())),
        'event_rows_sha256': hashlib.sha256(event_bytes).hexdigest(),
        'positive_season_ids': seasons,
        'positive_season_count': len(seasons),
        'positive_seasons_by_region': seasons_by_region,
        'regions': sorted(raw_rows_by_region),
        'source_scene_id_count': scene_id_count,
        'missing_source_scene_id_count': len(rows) - scene_id_count,
        'approved_core_provenance_count': approved_core_provenance_count,
        'training_eligible': False,
        'production_scoring_eligible': False,
        'review_status': 'blocked_missing_source_scene_provenance' if scene_id_count < len(rows) else 'pending_independence_review',
        'required_next_action': (
            'Repair/export source_scene_ids and add a hash-pinned source-scene manifest before overlap review.'
            if scene_id_count < len(rows)
            else 'Run the source-overlap report and obtain an explicit reviewer approval.'
        ),
    }
    return rows, manifest


def write_snapshot(output_dir: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    (output_dir / 'events.jsonl').write_bytes(event_bytes)
    (output_dir / 'snapshot_manifest.json').write_text(
        json.dumps({**manifest, 'events_path': 'events.jsonl'}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    (output_dir / 'ATTRIBUTION.md').write_text(
        '# gee_sar source snapshot\n\n'
        'This is a bounded, read-only export from the project `avalanche_events_decayed` table. '
        'It is not an open-source license grant and is not eligible for core training until '
        'scene provenance, license, source overlap, and multi-season coverage are reviewed.\n',
        encoding='utf-8',
    )


def _fetch_region(region_key: str, *, page_size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = rest_get('avalanche_events_decayed', params={
            'select': 'id,location,timestamp,source,source_scene_ids,features',
            'hazard_type': 'eq.avalanche',
            'training_eligible': 'eq.true',
            'features->>region_key': f'eq.{region_key}',
            'order': 'timestamp.asc,id.asc',
            'limit': str(page_size),
            'offset': str(offset),
        }) or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('backend/data/open_source_labels/gee_sar_remote_audit'))
    parser.add_argument('--region-keys', default=','.join(DEFAULT_REGIONS))
    parser.add_argument('--page-size', type=int, default=DEFAULT_PAGE_SIZE)
    args = parser.parse_args(argv)
    if args.page_size <= 0:
        raise SystemExit('--page-size must be positive')
    region_keys = tuple(sorted({value.strip() for value in args.region_keys.split(',') if value.strip()}))
    raw_rows = {region_key: _fetch_region(region_key, page_size=args.page_size) for region_key in region_keys}
    rows, manifest = build_snapshot(raw_rows)
    write_snapshot(args.output_dir, rows, manifest)
    print(json.dumps({
        'output_dir': str(args.output_dir),
        'included_record_count': manifest['included_record_count'],
        'positive_season_count': manifest['positive_season_count'],
        'positive_seasons_by_region': manifest['positive_seasons_by_region'],
        'source_scene_id_count': manifest['source_scene_id_count'],
        'review_status': manifest['review_status'],
        'event_rows_sha256': manifest['event_rows_sha256'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
