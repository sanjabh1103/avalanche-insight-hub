#!/usr/bin/env python3
"""Materialize the reviewed Everest Sentinel-1 avalanche-outline snapshot.

The Zenodo Everest bundle contains manually updated polygon outlines whose
filenames identify the two Sentinel-1 acquisition dates surrounding a
detection. The actual avalanche time is therefore bounded by an interval;
this adapter preserves both bounds and deliberately does not invent a point
timestamp. The output is an independent shadow/benchmark source, not an
exact-date core training snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import shapefile
from rasterio.warp import transform

from backend.common.regions import load_regions


SOURCE_KEY = 'everest_sentinel1'
ORIGIN_SOURCE_FAMILY = 'everest_sentinel1_satellite_detection'
ZENODO_RECORD_URL = 'https://zenodo.org/records/10895011'
ZENODO_ARCHIVE_URL = 'https://zenodo.org/api/records/10895011/files/Everest.zip/content'
ZENODO_ARCHIVE_MD5 = '2491f98493d0fd40824b57a41b2fdb90'
ZENODO_DOI = '10.5281/zenodo.10895011'
SOURCE_CITATION = (
    "Kneib et al. (2024). Data for 'Mapping and characterization of avalanches "
    "on mountain glaciers with Sentinel-1 satellite imagery'. Zenodo. "
    f"{ZENODO_DOI}"
)
LICENSE_REVIEW_ID = 'mvp4-everest-sentinel1-cc-by4-shadow-review-20260801'
SOURCE_CRS = 'EPSG:32645'
SOURCE_MEMBER_PREFIX = 'Everest/Automated_outlines_dates_ManualUpd/'
INTERVAL_RE = re.compile(r'^(?:ASC|DESC)_(?P<start>\d{8})-(?P<end>\d{8})\.shp$')
REGION_SEASON_START_MONTHS = {
    'himalayas_nepal': 11,
    'pir_panjal_nw_himalaya': 11,
}


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    ).encode('utf-8')


def _json_datetime(value: date) -> str:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')


def _parse_date(raw: str) -> date:
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _season_id(value: date, region_key: str) -> str:
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    season_year = value.year if value.month >= start_month else value.year - 1
    return f'{season_year}-{season_year + 1}'


def _within_region(lat: float, lng: float, bounds: tuple[float, float, float, float]) -> bool:
    lat_min, lng_min, lat_max, lng_max = bounds
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _target_bounds() -> dict[str, tuple[float, float, float, float]]:
    regions = {region.key: region for region in load_regions()}
    if 'himalayas_nepal' not in regions:
        raise ValueError('configured target region himalayas_nepal is missing')
    return {'himalayas_nepal': regions['himalayas_nepal'].bbox}


def _archive_hashes(archive_payload: bytes) -> dict[str, str | bool]:
    md5 = hashlib.md5(archive_payload, usedforsecurity=False).hexdigest()
    return {
        'source_archive_md5': md5,
        'source_archive_sha256': hashlib.sha256(archive_payload).hexdigest(),
        'source_archive_md5_matches_zenodo': md5 == ZENODO_ARCHIVE_MD5,
    }


def _bbox_center(shape: shapefile.Shape) -> tuple[float, float] | None:
    if not shape.points or len(shape.bbox) != 4:
        return None
    xmin, ymin, xmax, ymax = (float(value) for value in shape.bbox)
    lng_values, lat_values = transform(
        SOURCE_CRS,
        'EPSG:4326',
        [(xmin + xmax) / 2.0],
        [(ymin + ymax) / 2.0],
    )
    lat = float(lat_values[0])
    lng = float(lng_values[0])
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return lat, lng


def _source_row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(row)).hexdigest()


def build_snapshot(
    archive_payload: bytes,
    *,
    target_regions: dict[str, tuple[float, float, float, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build stable interval rows from a pinned Everest zip payload."""
    archive_hashes = _archive_hashes(archive_payload)
    rows: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    member_count = 0
    prj_member_count = 0

    with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
        names = set(archive.namelist())
        shp_names = sorted(
            name for name in names
            if name.startswith(SOURCE_MEMBER_PREFIX) and name.endswith('.shp')
        )
        for member_name in shp_names:
            match = INTERVAL_RE.match(member_name.removeprefix(SOURCE_MEMBER_PREFIX))
            if match is None:
                excluded['unparseable_interval_filename'] += 1
                continue
            stem = member_name[:-4]
            required_members = (stem + '.dbf', stem + '.shx')
            if any(required not in names for required in required_members):
                excluded['missing_shapefile_sidecar'] += 1
                continue
            member_count += 1
            if stem + '.prj' in names:
                prj_member_count += 1
                prj_text = archive.read(stem + '.prj').decode('utf-8', errors='replace')
                if 'UTM zone 45N' not in prj_text and 'EPSG",32645' not in prj_text:
                    excluded['unexpected_source_crs'] += 1
                    continue
            start = _parse_date(match.group('start'))
            end = _parse_date(match.group('end'))
            orbit = member_name.rsplit('/', 1)[-1].split('_', 1)[0]
            with (
                archive.open(member_name) as shp_file,
                archive.open(stem + '.shx') as shx_file,
                archive.open(stem + '.dbf') as dbf_file,
            ):
                reader = shapefile.Reader(
                    shp=io.BytesIO(shp_file.read()),
                    shx=io.BytesIO(shx_file.read()),
                    dbf=io.BytesIO(dbf_file.read()),
                )
                for shape_index, shape in enumerate(reader.shapes()):
                    point = _bbox_center(shape)
                    if point is None:
                        excluded['invalid_geometry'] += 1
                        continue
                    lat, lng = point
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
                    identity = {
                        'member_name': member_name,
                        'shape_index': shape_index,
                        'start': start.isoformat(),
                        'end': end.isoformat(),
                        'lat': round(lat, 9),
                        'lng': round(lng, 9),
                    }
                    row_hash = _source_row_hash(identity)
                    rows.append({
                        'source_key': SOURCE_KEY,
                        'origin_source_family': ORIGIN_SOURCE_FAMILY,
                        'external_id': f'everest-s1-{row_hash[:20]}',
                        'source_event_id': f'{member_name}#shape-{shape_index + 1:04d}',
                        'event_group_id': f'everest-s1:{row_hash[:20]}',
                        'region_key': region_key,
                        'lat': lat,
                        'lng': lng,
                        'event_time_start': _json_datetime(start),
                        'event_time_end': _json_datetime(end),
                        'label': 1,
                        'label_confidence': 0.75,
                        'training_weight': 0.4,
                        'training_eligible': False,
                        'production_scoring_eligible': False,
                        'location_precision': 'polygon_bbox_center_in_utm45n',
                        'timestamp_precision': 'bounded_12_day_detection_interval',
                        'source_row_sha256': row_hash,
                        'source_reference': f'{ZENODO_RECORD_URL}#{member_name}',
                        'geometry_ref': f'{ZENODO_RECORD_URL}#{member_name}#shape-{shape_index + 1:04d}',
                        'metadata': {
                            'source_url': ZENODO_RECORD_URL,
                            'source_archive_url': ZENODO_ARCHIVE_URL,
                            'source_archive_member': member_name,
                            'source_archive_member_shape_index': shape_index,
                            'orbit_direction': orbit,
                            'source_crs': SOURCE_CRS,
                            'manual_update_variant': 'Automated_outlines_dates_ManualUpd',
                            'event_window_days': (end - start).days,
                            'license': 'CC BY 4.0',
                            'citation': SOURCE_CITATION,
                        },
                    })

    rows.sort(key=lambda row: (row['region_key'], row['event_time_start'], row['external_id']))
    seasons = sorted({
        _season_id(date.fromisoformat(row['event_time_start'][:10]), row['region_key'])
        for row in rows
    })
    seasons_by_region = {
        region_key: sorted({
            _season_id(date.fromisoformat(row['event_time_start'][:10]), region_key)
            for row in rows if row['region_key'] == region_key
        })
        for region_key in sorted(target_regions)
    }
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    manifest = {
        'snapshot_schema_version': 'mvp4_bounded_sar_snapshot_v1',
        'source_key': SOURCE_KEY,
        'source_role': 'independent_satellite_derived_shadow_benchmark',
        'source_url': ZENODO_RECORD_URL,
        'source_archive_url': ZENODO_ARCHIVE_URL,
        'source_archive_record_doi': ZENODO_DOI,
        'source_archive_member_prefix': SOURCE_MEMBER_PREFIX,
        'source_archive_member_count': member_count,
        'source_archive_prj_member_count': prj_member_count,
        **archive_hashes,
        'license': 'CC BY 4.0',
        'license_review_id': LICENSE_REVIEW_ID,
        'license_status': 'permissive_shadow_reviewed',
        'citation': SOURCE_CITATION,
        'measurement_layer': 'manually_updated_sentinel1_avalanche_deposit_outlines',
        'source_crs': SOURCE_CRS,
        'region_season_start_months': REGION_SEASON_START_MONTHS,
        'target_regions': target_regions,
        'included_record_count': len(rows),
        'excluded_record_counts': dict(sorted(excluded.items())),
        'event_rows_sha256': hashlib.sha256(event_bytes).hexdigest(),
        'positive_season_ids': seasons,
        'positive_season_count': len(seasons),
        'positive_seasons_by_region': seasons_by_region,
        'exact_timestamp_record_count': 0,
        'bounded_interval_record_count': len(rows),
        'source_keys': [SOURCE_KEY],
        'origin_source_families': [ORIGIN_SOURCE_FAMILY],
        'source_overlap_report': 'source_overlap_report.json',
        'snapshot_role': 'shadow_benchmark',
        'training_eligible': False,
        'production_scoring_eligible': False,
        'review_status': 'reviewed_shadow_bounded_interval',
        'required_next_action': (
            'Implement and validate interval-aware feature joins before any core training use; '
            'do not substitute event_time_start for an exact event timestamp.'
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
        '# Everest Sentinel-1 attribution\n\n'
        f'- Source: [{ZENODO_RECORD_URL}]({ZENODO_RECORD_URL})\n'
        f'- Archive member: `Everest.zip` (`{ZENODO_DOI}`)\n'
        f'- Citation: {SOURCE_CITATION}\n'
        '- License: CC BY 4.0; retain attribution and source references.\n\n'
        'This snapshot contains manually updated Sentinel-1 avalanche-deposit '
        'polygons. Each filename bounds detection between two acquisition dates; '
        'it does not identify the exact avalanche time. It is therefore a '
        'reviewed independent shadow/benchmark source and is not eligible for '
        'exact-date core training.\n',
        encoding='utf-8',
    )


def _fetch_source(url: str) -> bytes:
    from urllib.request import Request, urlopen

    request = Request(url, headers={'Accept': 'application/zip', 'User-Agent': 'avalanche-insight-hub-mvp4/1'})
    with urlopen(request, timeout=90) as response:
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--source-url', default=ZENODO_ARCHIVE_URL)
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('backend/data/open_source_labels/everest_sentinel1'),
    )
    args = parser.parse_args(argv)
    payload = args.source_archive.read_bytes() if args.source_archive else _fetch_source(args.source_url)
    rows, manifest = build_snapshot(payload, target_regions=_target_bounds())
    write_snapshot(args.output_dir, rows, manifest)
    print(json.dumps({
        'output_dir': str(args.output_dir),
        'source_archive_sha256': manifest['source_archive_sha256'],
        'source_archive_md5_matches_zenodo': manifest['source_archive_md5_matches_zenodo'],
        'event_rows_sha256': manifest['event_rows_sha256'],
        'included_record_count': manifest['included_record_count'],
        'positive_season_count': manifest['positive_season_count'],
        'positive_seasons_by_region': manifest['positive_seasons_by_region'],
        'review_status': manifest['review_status'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
