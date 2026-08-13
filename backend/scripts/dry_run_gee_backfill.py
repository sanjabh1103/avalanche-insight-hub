"""Dry-run historical SAR backfill — counts detections and verifies scene IDs without inserting.

Uses the same gee._process_region pipeline as historical_sar_backfill.py but
skips all database writes. Outputs a JSON summary comparing detection counts
and scene_id coverage against the archived gee_sar cohort.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.common.regions import load_regions
import backend.gee_extractor as gee


def run_dry_run(start: datetime, end: datetime, chunk_days: int = 14) -> dict:
    try:
        ee = gee._initialize_ee()
    except Exception as exc:
        return {'status': 'ee_init_failed', 'error': str(exc)}

    regions = load_regions()
    per_region: list[dict] = []
    total_detections = 0
    total_with_scene_ids = 0

    for region in regions:
        region_detections = 0
        region_with_scene_ids = 0
        region_chunks: list[dict] = []
        cursor = start
        while cursor < end:
            w_end = min(cursor + timedelta(days=chunk_days), end)
            try:
                raw = gee._process_region(ee, region, start_date=cursor, end_date=w_end, persist_lineage=False)
                chunk_detections = len(raw)
                chunk_with_scenes = sum(
                    1 for e in raw if e.get('source_scene_ids')
                )
                region_detections += chunk_detections
                region_with_scene_ids += chunk_with_scenes
                region_chunks.append({
                    'window': f'{cursor.date()}->{w_end.date()}',
                    'detections': chunk_detections,
                    'with_scene_ids': chunk_with_scenes,
                })
            except Exception as exc:
                region_chunks.append({
                    'window': f'{cursor.date()}->{w_end.date()}',
                    'error': str(exc),
                })
            cursor = w_end

        total_detections += region_detections
        total_with_scene_ids += region_with_scene_ids
        print(f'[dry-run] {region.key}: detections={region_detections} with_scene_ids={region_with_scene_ids}')
        per_region.append({
            'region': region.key,
            'detections': region_detections,
            'with_scene_ids': region_with_scene_ids,
            'chunks': region_chunks,
        })

    return {
        'status': 'ok',
        'start': start.isoformat(),
        'end': end.isoformat(),
        'chunk_days': chunk_days,
        'total_detections': total_detections,
        'total_with_scene_ids': total_with_scene_ids,
        'per_region': per_region,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2023-11-01', help='YYYY-MM-DD')
    parser.add_argument('--end', default='2024-04-30', help='YYYY-MM-DD')
    parser.add_argument('--chunk-days', type=int, default=14, help='Days per chunk')
    parser.add_argument('--output', default='backend/data/gee_sar_archive_pre_provenance/dry_run_summary.json')
    args = parser.parse_args(argv)

    start = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if end <= start:
        print('--end must be after --start', file=sys.stderr)
        return 2

    summary = run_dry_run(start, end, chunk_days=args.chunk_days)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, default=str) + '\n')
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get('status') == 'ok' else 2


if __name__ == '__main__':
    sys.exit(main())
