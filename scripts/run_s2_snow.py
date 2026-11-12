#!/usr/bin/env python3
"""Batch Sentinel-2 snow-cover ingestion for workflow dispatch."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timezone
from typing import Any

from backend.common.observation_contract import ObservationContract, QUALITY_PROVISIONAL
from backend.common.regions import load_regions
from backend.common.sentinel2_snow_mapper import (
    S2_SNOW_ENABLED,
    map_s2_snow_batch,
)
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


def _persist_observations(results: dict[str, Any], regions: list[Any]) -> bool:
    if not results or not has_supabase_credentials():
        return False
    rows = []
    for region in regions:
        cell_id = f'{region.key}:center'
        result = results.get(cell_id)
        if result is None or result.snow_cover_fraction is None:
            continue
        observation = ObservationContract(
            region_key=region.key,
            cell_id=cell_id,
            sensor='sentinel2_optical',
            variable='snow_cover_fraction',
            value=result.snow_cover_fraction,
            unit='fraction',
            uncertainty=0.10,
            acquisition_time=result.acquisition_time or datetime.now(timezone.utc),
            freshness_hours=72.0,
            quality_state=QUALITY_PROVISIONAL,
            lineage={
                'verified': bool(result.scene_id),
                'evidence_ref': result.metadata.get('lineage_ref') if isinstance(result.metadata, dict) else None,
                'scene_id': result.scene_id,
            },
            metadata={
                'cloud_cover_fraction': result.cloud_cover,
                'scene_id': result.scene_id,
                'advisory_only': True,
            },
        )
        rows.append(observation.to_dict())
    if not rows:
        return False
    try:
        rest_insert('verification_observations', rows, returning='minimal')
    except Exception as exc:
        print(f'[run_s2_snow] observation append failed: {exc}', file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Batch Sentinel-2 snow-cover ingestion')
    parser.add_argument('--date', default=datetime.now(timezone.utc).date().isoformat(), type=_parse_date)
    parser.add_argument('--region-key', action='append', default=[])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    try:
        regions = _selected_regions(args.region_key)
    except ValueError as exc:
        parser.error(str(exc))

    cells = [
        {
            'cell_id': f'{region.key}:center',
            'lat': float(region.center[0]),
            'lng': float(region.center[1]),
        }
        for region in regions
    ]
    target_datetime = datetime.combine(args.date, time.min, tzinfo=timezone.utc)
    if args.dry_run:
        summary = {
            'status': 'dry_run',
            'enabled': bool(S2_SNOW_ENABLED),
            'date': args.date.isoformat(),
            'cells': cells,
            'persisted': False,
            'disclaimer': 'Advisory optical snow-cover evidence only; not an official avalanche warning.',
        }
        print(json.dumps(summary, indent=2))
        return 0

    results = map_s2_snow_batch(cells=cells, target_date=target_datetime)
    persisted = _persist_observations(results, regions)
    summary = {
        'status': 'completed',
        'enabled': bool(S2_SNOW_ENABLED),
        'date': args.date.isoformat(),
        'result_count': len(results),
        'results': {cell_id: result.to_dict() for cell_id, result in results.items()},
        'persisted': persisted,
        'disclaimer': 'Advisory optical snow-cover evidence only; not an official avalanche warning.',
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
