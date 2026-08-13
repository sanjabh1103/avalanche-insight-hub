"""Seed 30-day historical baselines into verification_baselines.

Fetches 30 days of daily weather via Open-Meteo forecast API (past_days=30),
computes p25/p50/p75 percentiles, and upserts into verification_baselines.

Usage:
    python -m backend.scripts.seed_baselines
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.common.supabase_io import rest_upsert
from backend.common.regions import load_regions

SUPABASE_URL = os.environ.get('SUPABASE_URL') or os.environ.get('VITE_SUPABASE_URL')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
REGION_KEY = os.environ.get('SEED_REGION', 'himalayas_nepal')
GRID_SUBSET = 5


def fetch_30day_weather(lat: float, lon: float) -> dict:
    """Fetch 30 days of daily weather from Open-Meteo forecast API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        'latitude': lat,
        'longitude': lon,
        'daily': 'snowfall_sum,temperature_2m_max,temperature_2m_min,precipitation_sum',
        'past_days': 30,
        'timezone': 'UTC',
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def compute_percentiles(values: list) -> dict:
    """Compute p25, p50, p75 percentiles for a list of values."""
    arr = np.array([v for v in values if v is not None], dtype=float)
    if len(arr) == 0:
        return {'p25': None, 'p50': None, 'p75': None, 'n': 0}
    return {
        'p25': float(np.percentile(arr, 25)),
        'p50': float(np.percentile(arr, 50)),
        'p75': float(np.percentile(arr, 75)),
        'n': int(len(arr)),
    }


def main():
    if not SUPABASE_URL or not SERVICE_KEY:
        print('ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set')
        sys.exit(1)

    print(f'=== Baseline Seeding ===')
    print(f'Region: {REGION_KEY}')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}')
    print()

    regions = load_regions()
    region = next((r for r in regions if r.key == REGION_KEY), None)
    if not region:
        print(f'ERROR: Region {REGION_KEY} not found')
        sys.exit(1)

    print(f'Region center: {region.center}')
    print(f'Region bbox: {region.bbox}')

    lat_min, lat_max = region.bbox[0], region.bbox[2]
    lon_min, lon_max = region.bbox[1], region.bbox[3]
    lat_step = (lat_max - lat_min) / GRID_SUBSET
    lon_step = (lon_max - lon_min) / GRID_SUBSET

    baseline_records = []

    print(f'\nProcessing {GRID_SUBSET}x{GRID_SUBSET} grid subset...')

    for i in range(GRID_SUBSET):
        for j in range(GRID_SUBSET):
            cell_lat = lat_min + (i + 0.5) * lat_step
            cell_lon = lon_min + (j + 0.5) * lon_step
            cell_id = f'{REGION_KEY}_c{i}_{j}'

            try:
                weather = fetch_30day_weather(cell_lat, cell_lon)
            except Exception as e:
                print(f'  {cell_id}: fetch failed: {e}')
                continue

            daily = weather.get('daily', {})
            snowfall = daily.get('snowfall_sum', [])
            t_max = daily.get('temperature_2m_max', [])
            t_min = daily.get('temperature_2m_min', [])
            precip = daily.get('precipitation_sum', [])

            snow_pct = compute_percentiles(snowfall)
            tmax_pct = compute_percentiles(t_max)
            tmin_pct = compute_percentiles(t_min)
            precip_pct = compute_percentiles(precip)

            stats = {
                'snowfall_sum_cm': snow_pct,
                'temperature_2m_max_c': tmax_pct,
                'temperature_2m_min_c': tmin_pct,
                'precipitation_sum_mm': precip_pct,
            }

            baseline_records.append({
                'region_key': REGION_KEY,
                'cell_id': cell_id,
                'sensor': 'weather',
                'window': '30d',
                'stats': stats,
            })

            print(f'  {cell_id}: snowfall p25={snow_pct["p25"]:.1f} p50={snow_pct["p50"]:.1f} p75={snow_pct["p75"]:.1f} n={snow_pct["n"]}')

            time.sleep(0.5)

    print(f'\nComputed baselines for {len(baseline_records)} cells')

    if not baseline_records:
        print('ERROR: No baselines computed')
        sys.exit(1)

    # Upsert to verification_baselines via REST API
    print(f'\nPersisting {len(baseline_records)} baseline records to verification_baselines...')
    try:
        rest_upsert(
            'verification_baselines',
            baseline_records,
            on_conflict='region_key,cell_id,sensor,window',
        )
        print('  Persisted successfully via REST API')
    except Exception as e:
        print(f'  REST API failed: {e}')
        print('  Falling back to psql...')
        # Fall back to psql without putting the password in the command line.
        db_password = os.environ.get('SUPABASE_DB_PASSWORD')
        if not db_password:
            print('ERROR: SUPABASE_DB_PASSWORD is required for the psql fallback')
            sys.exit(1)

        parsed_url = urlparse(SUPABASE_URL)
        project_host = parsed_url.hostname or ''
        project_ref = project_host.split('.')[0] if project_host else ''
        if not project_ref or not project_host.endswith('.supabase.co'):
            print('ERROR: SUPABASE_URL must be a valid Supabase project URL')
            sys.exit(1)

        psql_env = os.environ.copy()
        psql_env.update({
            'PGDATABASE': 'postgres',
            'PGHOST': os.environ.get('SUPABASE_DB_HOST') or f'db.{project_ref}.supabase.co',
            'PGPASSWORD': db_password,
            'PGPORT': '5432',
            'PGSSLMODE': 'require',
            'PGUSER': os.environ.get('SUPABASE_DB_USER', 'postgres'),
        })
        for rec in baseline_records:
            stats_json = json.dumps(rec['stats']).replace("'", "''")
            sql = (
                f"INSERT INTO verification_baselines (region_key, cell_id, sensor, window, stats) "
                f"VALUES ('{rec['region_key']}', '{rec['cell_id']}', '{rec['sensor']}', '{rec['window']}', "
                f"'{stats_json}'::jsonb) "
                f"ON CONFLICT (region_key, cell_id, sensor, \"window\") DO UPDATE SET stats = EXCLUDED.stats, updated_at = now();"
            )
            result = subprocess.run(
                ['psql', '-c', sql],
                capture_output=True,
                env=psql_env,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                print(f'  psql error for {rec["cell_id"]}: {result.stderr.strip()}')
        print(f'  Persisted {len(baseline_records)} records via psql')

    print('\n=== Seeding complete ===')
    print(f'Baselines seeded: {len(baseline_records)}')


if __name__ == '__main__':
    main()
