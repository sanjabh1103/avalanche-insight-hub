#!/usr/bin/env python3
"""Batch NASA GIBS snow-cover ingestion for workflow dispatch.

This entry point is deliberately small: it fetches one center cell per
selected configured region, emits tile lineage, and optionally appends
provisional observations with the service role. It is advisory evidence only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from typing import Any

from backend.common.gibs_ingestion import (
    GIBS_ENABLED,
    _build_tile_url,
    fetch_gibs_snow_cover_batch,
)
from backend.common.observation_contract import ObservationContract, QUALITY_PROVISIONAL
from backend.common.regions import load_regions
from backend.common.supabase_io import has_supabase_credentials, rest_insert


def _selected_regions(raw_keys: list[str]) -> list[Any]:
    regions = load_regions()
    requested = {
        item.strip()
        for raw in raw_keys
        for item in raw.split(',')
        if item.strip()
    }
    if not requested:
        return regions
    known = {region.key for region in regions}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f'Unknown region key(s): {", ".join(unknown)}')
    return [region for region in regions if region.key in requested]


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('date must be YYYY-MM-DD') from exc


def _persist_observations(results: list[Any], regions: list[Any], target_date: date) -> bool:
    if not results or not has_supabase_credentials():
        return False
    acquisition_time = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    rows = []
    for result, region in zip(results, regions):
        if result is None:
            continue
        observation = ObservationContract(
            region_key=region.key,
            cell_id=f'{region.key}:center',
            sensor='gibs_modis',
            variable='snow_cover_fraction',
            value=result.snow_cover_fraction,
            unit='fraction',
            uncertainty=0.25,
            acquisition_time=acquisition_time,
            freshness_hours=24.0,
            quality_state=QUALITY_PROVISIONAL,
            lineage={
                'verified': bool(result.tile_url),
                'evidence_ref': result.tile_url,
                'source': result.source,
            },
            metadata={'tile_url': result.tile_url, 'advisory_only': True},
        )
        rows.append(observation.to_dict())
    if not rows:
        return False
    try:
        rest_insert('verification_observations', rows, returning='minimal')
    except Exception as exc:
        print(f'[run_gibs_snow] observation append failed: {exc}', file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Batch NASA GIBS snow-cover ingestion')
    parser.add_argument('--date', default=datetime.now(timezone.utc).date().isoformat(), type=_parse_date)
    parser.add_argument('--region-key', action='append', default=[])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    try:
        regions = _selected_regions(args.region_key)
    except ValueError as exc:
        parser.error(str(exc))

    coordinates = [(float(region.center[0]), float(region.center[1])) for region in regions]
    if args.dry_run:
        summary = {
            'status': 'dry_run',
            'enabled': bool(GIBS_ENABLED),
            'date': args.date.isoformat(),
            'regions': [region.key for region in regions],
            'planned_tiles': [
                _build_tile_url(lat, lng, args.date)
                for lat, lng in coordinates
            ],
            'persisted': False,
            'disclaimer': 'Advisory satellite cover evidence only; not an official avalanche warning.',
        }
        print(json.dumps(summary, indent=2))
        return 0

    results = fetch_gibs_snow_cover_batch(coordinates, target_date=args.date)
    persisted = _persist_observations(results, regions, args.date)
    summary = {
        'status': 'completed',
        'enabled': bool(GIBS_ENABLED),
        'date': args.date.isoformat(),
        'regions': [region.key for region in regions],
        'result_count': sum(result is not None for result in results),
        'results': [result.to_dict() if result is not None else None for result in results],
        'persisted': persisted,
        'disclaimer': 'Advisory satellite cover evidence only; not an official avalanche warning.',
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
