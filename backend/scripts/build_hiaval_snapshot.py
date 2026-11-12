#!/usr/bin/env python3
"""Materialize a deterministic, reviewed HiAVAL event snapshot.

The source CSV is fetched from a pinned Git commit.  Only exact-date,
coordinate-valid records inside the configured target-region bounding boxes
are emitted.  This script never fabricates dates, never treats glacier
detachments as avalanche-occurrence labels, and writes a rejection ledger so
the resulting small JSONL snapshot is auditable.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from backend.common.label_time_contract import LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1
from backend.common.regions import load_regions


HIAVAL_COMMIT = '0b01fbf33e1874a75b356a9aa9f2a128f1a224a2'
HIAVAL_CSV_URL = (
    'https://raw.githubusercontent.com/fidelsteiner/HiAVAL/'
    f'{HIAVAL_COMMIT}/HiAVALDB.csv'
)
HIAVAL_SOURCE_URL = 'https://github.com/fidelsteiner/HiAVAL'
HIAVAL_CITATION = (
    'Steiner et al. (2023). HiAVAL: A database of avalanche events in High '
    'Mountain Asia. NHESS 23, 2569-2584. '
    'https://doi.org/10.5194/nhess-23-2569-2023'
)
LICENSE_REVIEW_ID = 'mvp4-hiaval-cc-by4-review-20260801'
TARGET_REGIONS = ('himalayas_nepal', 'pir_panjal_nw_himalaya')
REGION_SEASON_START_MONTHS = {
    'himalayas_nepal': 11,
    'pir_panjal_nw_himalaya': 11,
}
EXCLUDED_TYPE_MARKERS = (
    'glacier',
    'ice and rock',
    'rock avalanche',
    'rockfall',
    'debris avalanche',
)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def _clean_text(value: Any) -> str:
    text = unicodedata.normalize('NFKC', str(value or '')).replace('\xa0', ' ').strip()
    return re.sub(r'\s+', ' ', text)


def _number(value: Any) -> float | None:
    text = _clean_text(value)
    if not text or text.upper() in {'NA', 'N/A', 'NULL'}:
        return None
    text = re.sub(r'[^0-9eE+.-]', '', text)
    try:
        result = float(text)
    except ValueError:
        return None
    return result if result == result and abs(result) != float('inf') else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or int(number) != number:
        return None
    return int(number)


def _season_id(event_time: datetime, region_key: str) -> str:
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    season_year = event_time.year if event_time.month >= start_month else event_time.year - 1
    return f'{season_year}-{season_year + 1}'


def _fetch_source(url: str) -> bytes:
    request = Request(url, headers={'Accept': 'text/csv', 'User-Agent': 'avalanche-insight-hub-mvp4/1'})
    with urlopen(request, timeout=45) as response:
        return response.read()


def _target_bounds() -> dict[str, tuple[float, float, float, float]]:
    regions = {region.key: region for region in load_regions()}
    missing = [key for key in TARGET_REGIONS if key not in regions]
    if missing:
        raise SystemExit(f'configured target regions are missing: {missing}')
    return {key: regions[key].bbox for key in TARGET_REGIONS}


def _within_region(lat: float, lng: float, bounds: tuple[float, float, float, float]) -> bool:
    lat_min, lng_min, lat_max, lng_max = bounds
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _row_hash(row: dict[str, str]) -> str:
    return hashlib.sha256(_json_bytes(row)).hexdigest()


def build_snapshot(raw_payload: bytes, *, target_regions: dict[str, tuple[float, float, float, float]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_sha256 = hashlib.sha256(raw_payload).hexdigest()
    text = raw_payload.decode('utf-8', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    rejected = Counter()
    seen_ids: set[str] = set()

    for raw in reader:
        row = {str(key): _clean_text(value) for key, value in raw.items() if key is not None}
        lat = _number(row.get('Latitude'))
        lng = _number(row.get('Longitude'))
        if lat is None or lng is None or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            rejected['invalid_coordinates'] += 1
            continue
        year = _integer(row.get('Year'))
        month = _integer(row.get('Month'))
        day = _integer(row.get('Day'))
        if year is None or month is None or day is None:
            rejected['partial_date'] += 1
            continue
        try:
            event_time = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            rejected['invalid_date'] += 1
            continue
        event_type = _clean_text(row.get('Type'))
        event_remarks = _clean_text(row.get('Remarks'))
        ontology_text = f'{event_type} {event_remarks}'.lower()
        if any(marker in ontology_text for marker in EXCLUDED_TYPE_MARKERS):
            rejected['excluded_glacier_detachment'] += 1
            continue
        reference = _clean_text(row.get('Reference'))
        if not reference:
            rejected['missing_reference'] += 1
            continue
        region_key = next(
            (key for key, bounds in target_regions.items() if _within_region(lat, lng, bounds)),
            None,
        )
        if region_key is None:
            rejected['outside_target_regions'] += 1
            continue
        row_hash = _row_hash(row)
        external_id = f'hiaval-{row_hash[:20]}'
        if external_id in seen_ids:
            rejected['duplicate_source_row'] += 1
            continue
        seen_ids.add(external_id)
        event_time_end = event_time + timedelta(days=1)
        rows.append({
            'source_key': 'hiaval_hma',
            'external_id': external_id,
            'event_group_id': f'hiaval:{external_id}',
            'origin_source_family': 'hiaval_literature_database',
            'region_key': region_key,
            'event_time_start': event_time.isoformat().replace('+00:00', 'Z'),
            'event_time_end': event_time_end.isoformat().replace('+00:00', 'Z'),
            'lat': lat,
            'lng': lng,
            'label': 1,
            'label_confidence': 0.7,
            'training_weight': 0.7,
            'event_type': event_type or None,
            'location_name': _clean_text(row.get('Location')),
            'source_reference': reference,
            'location_precision': 'point_from_source_database',
            'timestamp_precision': 'day',
            'source_row_sha256': row_hash,
            'metadata': {
                'source_url': HIAVAL_SOURCE_URL,
                'source_commit': HIAVAL_COMMIT,
                'license': 'CC BY 4.0',
                'citation': HIAVAL_CITATION,
                'country': _clean_text(row.get('Country')),
                'region_himap': _clean_text(row.get('Region_HiMAP')),
                'impact': _clean_text(row.get('Impact')),
                'remarks': _clean_text(row.get('Remarks')),
            },
        })

    rows.sort(key=lambda item: (item['region_key'], item['event_time_start'], item['external_id']))
    seasons = sorted({_season_id(datetime.fromisoformat(item['event_time_start'].replace('Z', '+00:00')), item['region_key']) for item in rows})
    seasons_by_region = {
        region: sorted({
            _season_id(datetime.fromisoformat(item['event_time_start'].replace('Z', '+00:00')), region)
            for item in rows if item['region_key'] == region
        })
        for region in target_regions
    }
    records_bytes = b''.join(_json_bytes(item) for item in rows)
    manifest = {
        'snapshot_schema_version': 'mvp4_hiaval_snapshot_v1',
        'source_key': 'hiaval_hma',
        'source_url': HIAVAL_SOURCE_URL,
        'source_csv_url': HIAVAL_CSV_URL,
        'source_commit': HIAVAL_COMMIT,
        'source_sha256': source_sha256,
        'license': 'CC BY 4.0',
        'license_review_id': LICENSE_REVIEW_ID,
        'license_status': 'permissive_core_reviewed',
        'citation': HIAVAL_CITATION,
        'independence': {
            'measurement_layer': 'literature_reports_news_local_interactions',
            'independent_from': ['gee_sar', 'sentinel_1_derived_labels'],
            'independence_requires_overlap_audit': True,
        },
        'target_regions': target_regions,
        'region_season_start_months': REGION_SEASON_START_MONTHS,
        'raw_record_count': sum(1 for _ in csv.DictReader(io.StringIO(text))),
        'included_record_count': len(rows),
        'excluded_record_counts': dict(sorted(rejected.items())),
        'event_rows_sha256': hashlib.sha256(records_bytes).hexdigest(),
        'source_keys': ['hiaval_hma'],
        'positive_season_ids': seasons,
        'positive_season_count': len(seasons),
        'positive_seasons_by_region': seasons_by_region,
            'required_independent_positive_sources': ['hiaval_hma', 'second_exact_time_source'],
            'required_independent_origin_families': ['hiaval_literature_database', 'second_exact_time_source'],
            'minimum_positive_sources': 2,
            'minimum_positive_seasons': 3,
        'minimum_positive_event_groups': 30,
        'snapshot_role': 'core_candidate_after_training_join',
        'label_time_contract': LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
        'interval_training_ready': False,
        'training_eligible': False,
        'production_scoring_eligible': False,
        'source_overlap_report': 'source_overlap_report.json',
    }
    return rows, manifest


def write_snapshot(output_dir: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    row_bytes = b''.join(_json_bytes(item) for item in rows)
    (output_dir / 'events.jsonl').write_bytes(row_bytes)
    (output_dir / 'snapshot_manifest.json').write_text(
        json.dumps({**manifest, 'events_path': 'events.jsonl'}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    overlap_report = {
        'version': 'mvp4_source_overlap_report_v1',
        'status': 'pending_gee_sar_snapshot',
        'source_a': 'hiaval_hma',
        'source_b': 'gee_sar',
        'deduplication_key': ['region_key', 'event_date', 'spatial_distance_km<=5'],
        'same_event_must_not_count_as_independent': True,
        'overlap_count': None,
        'required_next_input': 'a hash-pinned gee_sar event snapshot with source_scene_ids',
    }
    (output_dir / 'source_overlap_report.json').write_text(
        json.dumps(overlap_report, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    (output_dir / 'ATTRIBUTION.md').write_text(
        '# HiAVAL attribution\n\n'
        f'- Source: [{HIAVAL_SOURCE_URL}]({HIAVAL_SOURCE_URL})\n'
        f'- Pinned commit: `{HIAVAL_COMMIT}`\n'
        f'- Citation: {HIAVAL_CITATION}\n'
        '- License: CC BY 4.0; retain attribution and source references.\n\n'
        'This snapshot contains only exact-date, coordinate-valid rows in the '
        'configured pilot regions. It is incomplete and is not exhaustive '
        'avalanche occurrence truth.\n',
        encoding='utf-8',
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('backend/data/open_source_labels/hiaval_hma'))
    parser.add_argument('--source-url', default=HIAVAL_CSV_URL)
    args = parser.parse_args(argv)
    payload = _fetch_source(args.source_url)
    rows, manifest = build_snapshot(payload, target_regions=_target_bounds())
    write_snapshot(args.output_dir, rows, manifest)
    print(json.dumps({
        'output_dir': str(args.output_dir),
        'source_sha256': manifest['source_sha256'],
        'event_rows_sha256': manifest['event_rows_sha256'],
        'included_record_count': manifest['included_record_count'],
        'positive_season_count': manifest['positive_season_count'],
        'positive_seasons_by_region': manifest['positive_seasons_by_region'],
        'excluded_record_counts': manifest['excluded_record_counts'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
