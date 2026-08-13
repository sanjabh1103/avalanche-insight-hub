#!/usr/bin/env python3
"""Demo: ASF (Alaska Satellite Facility) Sentinel-1 coverage awareness.

Queries the ASF Search API (free, no auth) for Sentinel-1 scenes over
Himalayan regions, checks revisit frequency, and reports coverage gaps.

ASF API: https://search.asf.alaska.edu/#/
Endpoint: https://api.daac.asf.alaska.edu/services/search/param
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import requests

ASF_SEARCH_URL = 'https://api.daac.asf.alaska.edu/services/search/param'

# Himalayan region bboxes for coverage check
REGIONS = [
    {'name': 'Pir Panjal', 'bbox': [33.0, 73.5, 35.0, 75.5]},
    {'name': 'Shamshabari', 'bbox': [34.0, 74.5, 35.5, 76.0]},
    {'name': 'Great Himalaya', 'bbox': [34.5, 75.5, 36.5, 78.0]},
    {'name': 'Karakoram & Ladakh', 'bbox': [34.5, 76.5, 36.5, 79.0]},
    {'name': 'Himalayas (Nepal)', 'bbox': [27.0, 85.0, 29.0, 87.5]},
]


def query_asf_coverage(
    bbox: list[float],
    days_back: int = 30,
    max_results: int = 50,
) -> dict:
    """Query ASF Search API for Sentinel-1 scenes in a bbox.

    Returns dict with: count, first_date, last_date, platforms, paths.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)

    params = {
        'platform': 'Sentinel-1',
        'processingLevel': 'SLC',
        'start': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'end': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'bbox': f'{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}',
        'maxResults': max_results,
        'output': 'json',
    }

    try:
        resp = requests.get(ASF_SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        results = resp.json()
        if isinstance(results, list):
            scenes = results
        elif isinstance(results, dict) and 'results' in results:
            scenes = results['results']
        else:
            scenes = []

        if not scenes:
            return {'count': 0, 'error': None}

        dates = []
        paths = set()
        for scene in scenes:
            ts = scene.get('startTime') or scene.get('start')
            if ts:
                dates.append(ts[:10])
            path = scene.get('pathNumber') or scene.get('path')
            if path:
                paths.add(str(path))

        dates.sort()
        return {
            'count': len(scenes),
            'first_date': dates[0] if dates else None,
            'last_date': dates[-1] if dates else None,
            'paths': sorted(paths),
            'error': None,
        }
    except Exception as e:
        return {'count': 0, 'error': str(e)}


def main() -> int:
    print('=== ASF Sentinel-1 Coverage Awareness Demo ===\n')
    print(f'Querying ASF Search API for Sentinel-1 SLC scenes (last 30 days)')
    print(f'API: {ASF_SEARCH_URL}\n')

    total_scenes = 0
    regions_with_coverage = 0
    regions_without_coverage = 0
    regions_with_errors = 0

    for region in REGIONS:
        name = region['name']
        bbox = region['bbox']
        print(f'--- {name} (bbox: {bbox}) ---')

        result = query_asf_coverage(bbox, days_back=30)
        if result['error']:
            print(f'  ERROR: {result["error"]}')
            regions_with_errors += 1
        elif result['count'] == 0:
            print(f'  No scenes found in last 30 days')
            regions_without_coverage += 1
        else:
            print(f'  Scenes found: {result["count"]}')
            print(f'  Date range: {result["first_date"]} to {result["last_date"]}')
            print(f'  Paths: {result["paths"]}')
            total_scenes += result['count']
            regions_with_coverage += 1
        print()

    print('=== Coverage Summary ===\n')
    print(f'  Regions with coverage:  {regions_with_coverage}/{len(REGIONS)}')
    print(f'  Regions without:        {regions_without_coverage}/{len(REGIONS)}')
    print(f'  Regions with errors:    {regions_with_errors}/{len(REGIONS)}')
    print(f'  Total scenes (30 days): {total_scenes}')

    if regions_with_coverage > 0:
        print(f'\nPASS: {regions_with_coverage} regions have Sentinel-1 coverage')
    elif regions_with_errors > 0:
        print(f'\nWARN: API errors prevented coverage check (network or rate limit)')
    else:
        print(f'\nWARN: No coverage found (may be off-season or API issue)')

    # Compute revisit estimate
    if total_scenes > 0 and regions_with_coverage > 0:
        avg_scenes = total_scenes / regions_with_coverage
        estimated_revisit_days = 30 / max(avg_scenes, 1)
        print(f'  Average scenes per region: {avg_scenes:.1f}')
        print(f'  Estimated revisit: ~{estimated_revisit_days:.0f} days')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
