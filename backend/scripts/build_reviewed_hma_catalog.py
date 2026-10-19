#!/usr/bin/env python3
"""Build one provenance catalog from the exact and bounded HMA label lanes.

The catalog is intentionally not a core training snapshot: it contains both
exact-date HiAVAL rows and bounded Sentinel-1 interval rows. Keeping them in
one reviewed, hash-addressed catalog makes source coverage and conflicts
auditable without allowing the generic exact-timestamp training adapter to
consume the interval lane accidentally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from backend.common.label_time_contract import LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1

CATALOG_SCHEMA_VERSION = 'mvp4_reviewed_hma_catalog_v1'
REGION_SEASON_START_MONTHS = {
    'himalayas_nepal': 11,
    'pir_panjal_nw_himalaya': 11,
}
_CENSORED_TIME_PRECISIONS = frozenset({
    'day',
    'interval',
    'range',
    'bounded_12_day_detection_interval',
})


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    ).encode('utf-8')


def _load_snapshot(snapshot_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    manifest_path = snapshot_dir / 'snapshot_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    events_path = snapshot_dir / str(manifest.get('events_path') or 'events.jsonl')
    payload = events_path.read_bytes()
    expected_hash = str(manifest.get('event_rows_sha256') or '')
    actual_hash = hashlib.sha256(payload).hexdigest()
    if not expected_hash or expected_hash != actual_hash:
        raise ValueError(f'event snapshot hash mismatch: {events_path}')
    rows = [json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f'event snapshot is not non-empty JSONL: {events_path}')
    for index, row in enumerate(rows):
        precision = str(row.get('timestamp_precision') or '').strip().lower()
        if precision in _CENSORED_TIME_PRECISIONS and any(
            str(row.get(field) or '').strip() for field in ('event_time', 'timestamp')
        ):
            row_id = str(row.get('external_id') or row.get('event_group_id') or index)
            raise ValueError(
                f'exact-looking event_time on censored row: {events_path}:{row_id}'
            )
    return rows, manifest, payload


def _validate_overlap_report(
    overlap: dict[str, Any],
    *,
    exact_manifest: dict[str, Any],
    exact_rows: list[dict[str, Any]],
    exact_payload: bytes,
    bounded_manifest: dict[str, Any],
    bounded_rows: list[dict[str, Any]],
    bounded_payload: bytes,
) -> None:
    """Require overlap evidence to describe these exact input snapshots."""
    source_inputs = {
        str(exact_manifest.get('source_key') or ''): (exact_rows, exact_payload, 'source_a'),
        str(bounded_manifest.get('source_key') or ''): (bounded_rows, bounded_payload, 'source_b'),
    }
    declared_sources = {
        str(overlap.get('source_a') or '').strip(),
        str(overlap.get('source_b') or '').strip(),
    }
    if '' in declared_sources or declared_sources != set(source_inputs):
        raise ValueError('overlap report sources do not match catalog inputs')
    if overlap.get('same_event_must_not_count_as_independent') is not True:
        raise ValueError('overlap report must state that matched events are not independent')
    if overlap.get('independent_positive_source_count') != 2:
        raise ValueError('overlap report must prove two independent positive sources')

    for source_key, (rows, payload, side) in source_inputs.items():
        declared_hash = str(overlap.get(f'{side}_sha256') or '').strip().lower()
        actual_hash = hashlib.sha256(payload).hexdigest()
        if declared_hash != actual_hash:
            raise ValueError(f'{side}_sha256 does not match source snapshot: {source_key}')
        declared_count = overlap.get(f'{side}_record_count')
        if declared_count != len(rows):
            raise ValueError(f'{side}_record_count does not match source snapshot: {source_key}')
        non_overlap_count = overlap.get(f'{side}_non_overlap_count')
        if not isinstance(non_overlap_count, int) or not 0 <= non_overlap_count <= len(rows):
            raise ValueError(f'{side}_non_overlap_count is invalid: {source_key}')


def _sort_time(row: dict[str, Any]) -> str:
    return str(row.get('event_time') or row.get('event_time_start') or '')


def _season_id(row: dict[str, Any]) -> str | None:
    raw = _sort_time(row)
    if len(raw) < 10:
        return None
    try:
        timestamp = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    region_key = str(row.get('region_key') or '').strip()
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    season_year = timestamp.year if timestamp.month >= start_month else timestamp.year - 1
    return f'{season_year}-{season_year + 1}'


def build_catalog(
    exact_snapshot_dir: Path,
    bounded_snapshot_dir: Path,
    overlap_report_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    exact_rows, exact_manifest, exact_payload = _load_snapshot(exact_snapshot_dir)
    bounded_rows, bounded_manifest, bounded_payload = _load_snapshot(bounded_snapshot_dir)
    if exact_manifest.get('source_key') == bounded_manifest.get('source_key'):
        raise ValueError('catalog sources must be different')
    overlap_payload = overlap_report_path.read_bytes()
    overlap = json.loads(overlap_payload)
    if overlap.get('status') != 'reviewed':
        raise ValueError('catalog overlap report must be reviewed')
    _validate_overlap_report(
        overlap,
        exact_manifest=exact_manifest,
        exact_rows=exact_rows,
        exact_payload=exact_payload,
        bounded_manifest=bounded_manifest,
        bounded_rows=bounded_rows,
        bounded_payload=bounded_payload,
    )

    rows = [*exact_rows, *bounded_rows]
    rows.sort(key=lambda row: (
        str(row.get('region_key') or ''),
        _sort_time(row),
        str(row.get('source_key') or ''),
        str(row.get('external_id') or ''),
    ))
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    source_keys = sorted({str(row.get('source_key') or '').strip() for row in rows if row.get('source_key')})
    positive_seasons = sorted({season for row in rows if (season := _season_id(row))})
    seasons_by_region: dict[str, list[str]] = {}
    source_counts = Counter(str(row.get('source_key') or 'unknown') for row in rows)
    precision_counts = Counter(str(row.get('timestamp_precision') or 'unknown') for row in rows)
    for region_key in sorted({str(row.get('region_key') or '').strip() for row in rows if row.get('region_key')}):
        seasons_by_region[region_key] = sorted({
            season for row in rows
            if row.get('region_key') == region_key
            if (season := _season_id(row))
        })

    manifest = {
        'snapshot_schema_version': CATALOG_SCHEMA_VERSION,
        'source_key': 'mvp4_reviewed_hma_catalog',
        'source_keys': source_keys,
        'source_role': 'reviewed_multi_source_shadow_catalog',
        'source_manifests': {
            str(exact_manifest['source_key']): {
                'snapshot_manifest': str((exact_snapshot_dir / 'snapshot_manifest.json')),
                'event_rows_sha256': hashlib.sha256(exact_payload).hexdigest(),
                'source_sha256': exact_manifest.get('source_sha256'),
                'license': exact_manifest.get('license'),
                'license_status': exact_manifest.get('license_status'),
                'training_eligible': exact_manifest.get('training_eligible'),
            },
            str(bounded_manifest['source_key']): {
                'snapshot_manifest': str((bounded_snapshot_dir / 'snapshot_manifest.json')),
                'event_rows_sha256': hashlib.sha256(bounded_payload).hexdigest(),
                'source_archive_sha256': bounded_manifest.get('source_archive_sha256'),
                'license': bounded_manifest.get('license'),
                'license_status': bounded_manifest.get('license_status'),
                'training_eligible': bounded_manifest.get('training_eligible'),
            },
        },
        'source_overlap_report': 'source_overlap_report.json',
        'source_overlap_report_sha256': hashlib.sha256(overlap_payload).hexdigest(),
        'required_independent_positive_sources': source_keys,
        'independent_positive_source_count': int(overlap.get('independent_positive_source_count') or 0),
        'same_event_must_not_count_as_independent': overlap.get('same_event_must_not_count_as_independent') is True,
        'included_record_count': len(rows),
        'source_record_counts': dict(sorted(source_counts.items())),
        'timestamp_precision_counts': dict(sorted(precision_counts.items())),
        'exact_timestamp_record_count': sum(
            precision_counts.get(precision, 0)
            for precision in ('timestamp', 'instant', 'exact_timestamp')
        ),
        'bounded_interval_record_count': precision_counts.get('bounded_12_day_detection_interval', 0),
        'event_rows_sha256': hashlib.sha256(event_bytes).hexdigest(),
        'positive_season_ids': positive_seasons,
        'positive_season_count': len(positive_seasons),
        'positive_seasons_by_region': seasons_by_region,
        'region_season_start_months': REGION_SEASON_START_MONTHS,
        'label_time_contract': LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
        'interval_training_ready': False,
        'training_eligible': False,
        'production_scoring_eligible': False,
        'review_status': 'reviewed_local_source_catalog',
        'required_next_action': (
            'Keep this catalog for source review. Use a homogeneous exact-time '
            'snapshot for core training until interval-aware joins pass their own gate.'
        ),
    }
    return rows, manifest, overlap_payload


def write_catalog(
    output_dir: Path,
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    overlap_payload: bytes,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_bytes = b''.join(_canonical_bytes(row) for row in rows)
    (output_dir / 'events.jsonl').write_bytes(event_bytes)
    (output_dir / 'snapshot_manifest.json').write_text(
        json.dumps({**manifest, 'events_path': 'events.jsonl'}, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    (output_dir / 'source_overlap_report.json').write_bytes(overlap_payload)
    (output_dir / 'ATTRIBUTION.md').write_text(
        '# Reviewed HMA source catalog attribution\n\n'
        '- This catalog combines the exact-date HiAVAL core candidate with the '
        'CC BY 4.0 Everest Sentinel-1 bounded-interval shadow source.\n'
        '- See each source snapshot manifest for its pinned URL, hash, license, '
        'and limitations.\n'
        '- The catalog is review evidence only; `training_eligible` and '
        '`production_scoring_eligible` are both false.\n',
        encoding='utf-8',
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exact-snapshot-dir', type=Path, required=True)
    parser.add_argument('--bounded-snapshot-dir', type=Path, required=True)
    parser.add_argument('--overlap-report', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    rows, manifest, overlap_payload = build_catalog(
        args.exact_snapshot_dir,
        args.bounded_snapshot_dir,
        args.overlap_report,
    )
    write_catalog(args.output_dir, rows, manifest, overlap_payload)
    print(json.dumps({
        'output_dir': str(args.output_dir),
        'event_rows_sha256': manifest['event_rows_sha256'],
        'included_record_count': manifest['included_record_count'],
        'source_keys': manifest['source_keys'],
        'positive_season_count': manifest['positive_season_count'],
        'exact_timestamp_record_count': manifest['exact_timestamp_record_count'],
        'bounded_interval_record_count': manifest['bounded_interval_record_count'],
        'training_eligible': manifest['training_eligible'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
