"""One-shot historical Sentinel-1 SAR backfill.

Walks a prior winter season (defaults to 2023-11-01 → 2024-04-30) in monthly
chunks across every region in ``config/regions.json``, runs the standard
``gee_extractor._process_region`` pipeline (SRTM layover/shadow mask BEFORE
VV/VH thresholding — Edit 4), and inserts the resulting wet-snow candidate
events into ``avalanche_events`` with ``source='gee_sar'``.

This accelerates the cold-start clock so KMeansSMOTE has real ground-truth to
cluster, enabling the PSS > 0.45 training gate to be met immediately.

Safety rails:
* Missing GEE or Supabase credentials → ``exit 0`` (noop).
* Monthly chunking avoids giant query responses and spreads the EE load.
* Per-chunk errors are logged and the backfill continues to the next chunk.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Iterable

from backend.common.regions import load_regions
from backend.common.supabase_io import has_supabase_credentials, rest_insert

import backend.gee_extractor as gee


DEFAULT_START = os.getenv('BACKFILL_START_DATE', '2023-11-01')
DEFAULT_END = os.getenv('BACKFILL_END_DATE', '2024-04-30')
CHUNK_DAYS = int(os.getenv('BACKFILL_CHUNK_DAYS', '30'))


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)


def iter_chunks(start: datetime, end: datetime, days: int) -> Iterable[tuple[datetime, datetime]]:
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=days), end)
        yield cursor, chunk_end
        cursor = chunk_end


def _insert(events: list[dict]) -> int:
    if not events:
        return 0
    if not has_supabase_credentials():
        print(f'[backfill] Supabase creds absent; would insert {len(events)} events')
        return 0
    # Insert in batches of 200 to keep request bodies reasonable.
    inserted = 0
    for i in range(0, len(events), 200):
        batch = events[i:i + 200]
        rest_insert('avalanche_events', batch)
        inserted += len(batch)
    return inserted


def run_backfill(start: datetime, end: datetime) -> dict:
    if not gee._has_credentials():
        print('[backfill] GEE credentials absent; skipping (this is safe).')
        return {'status': 'skipped_no_gee_creds'}

    try:
        ee = gee._initialize_ee()
    except Exception as exc:
        print(f'[backfill] Earth Engine init failed: {exc}', file=sys.stderr)
        traceback.print_exc()
        return {'status': 'ee_init_failed', 'error': str(exc)}

    regions = load_regions()
    per_region: list[dict] = []
    grand_total = 0

    for region in regions:
        region_total = 0
        chunk_results: list[dict] = []
        for chunk_start, chunk_end in iter_chunks(start, end, CHUNK_DAYS):
            try:
                events = gee._process_region(ee, region, start_date=chunk_start, end_date=chunk_end)
                # Tag metadata so we can audit / dedupe later.
                for ev in events:
                    ev.setdefault('features', {})
                    ev['features']['backfill_window_start'] = chunk_start.date().isoformat()
                    ev['features']['backfill_window_end'] = chunk_end.date().isoformat()
                    ev['features']['ingest_type'] = 'historical_backfill'
                    ev['timestamp'] = chunk_end.isoformat()
                inserted = _insert(events)
                region_total += inserted
                chunk_results.append({
                    'window': f'{chunk_start.date()}→{chunk_end.date()}',
                    'inserted': inserted,
                })
            except Exception as exc:
                print(f'[backfill] {region.key} {chunk_start.date()}→{chunk_end.date()} failed: {exc}', file=sys.stderr)
                traceback.print_exc()
                chunk_results.append({
                    'window': f'{chunk_start.date()}→{chunk_end.date()}',
                    'error': str(exc),
                })
        per_region.append({
            'region': region.key,
            'inserted': region_total,
            'chunks': chunk_results,
        })
        grand_total += region_total
        print(f'[backfill] {region.key}: {region_total} events inserted across {len(chunk_results)} chunks')

    return {
        'status': 'ok',
        'total_inserted': grand_total,
        'start': start.date().isoformat(),
        'end': end.date().isoformat(),
        'chunk_days': CHUNK_DAYS,
        'per_region': per_region,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default=DEFAULT_START, help='Backfill start date YYYY-MM-DD')
    parser.add_argument('--end', default=DEFAULT_END, help='Backfill end date YYYY-MM-DD')
    args = parser.parse_args(argv)

    start = parse_date(args.start)
    end = parse_date(args.end)
    if end <= start:
        print('[backfill] end must be after start', file=sys.stderr)
        return 2
    summary = run_backfill(start, end)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get('status') in ('ok', 'skipped_no_gee_creds') else 2


if __name__ == '__main__':
    sys.exit(main())
