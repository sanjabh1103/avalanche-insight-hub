"""Smoke test: run verification spine for himalayas_nepal with real data.

Fetches current weather from Open-Meteo (working endpoint), GIBS snow cover,
and SAR summary from Supabase, then builds verification packets and fusion
evidence for a 5x5 grid subset, persists to verification_baselines, and
updates forecast_grids with real verification data.

Usage:
    python -m backend.scripts.verification_spine_smoke
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# Ensure PYTHONPATH includes project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.common.supabase_io import (
    has_supabase_credentials,
    rest_get,
    rest_upsert,
    patch_row_by_id,
)
from backend.common.anomaly_detector import detect_anomalies, SensorReading
from backend.common.fusion_engine import SensorObservation, fuse_observations
from backend.common.gibs_ingestion import fetch_gibs_snow_cover
from backend.common.snow_baselines import build_cell_baselines
from backend.common.regions import load_regions

SUPABASE_URL = os.environ.get('SUPABASE_URL') or os.environ.get('VITE_SUPABASE_URL')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
REGION_KEY = os.environ.get('SMOKE_REGION', 'himalayas_nepal')
GRID_SUBSET = 5  # 5x5 = 25 cells


def _headers():
    return {
        'apikey': SERVICE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
        'Content-Type': 'application/json',
    }


def fetch_current_weather(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo (working endpoint)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        'latitude': lat,
        'longitude': lon,
        'current': 'temperature_2m,snowfall,snow_depth,wind_speed_10m,precipitation',
        'daily': 'snowfall_sum,precipitation_sum,temperature_2m_max,temperature_2m_min',
        'timezone': 'UTC',
        'forecast_days': 3,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_sar_summary(region_key: str) -> dict | None:
    """Fetch latest SAR summary from avalanche_events."""
    if not has_supabase_credentials():
        return None
    try:
        rows = rest_get(
            'avalanche_events',
            params={
                'select': 'id,timestamp,features',
                'source': 'in.(gee_sar,sentinel1_gee)',
                'order': 'timestamp.desc',
                'limit': '10',
            },
        ) or []
        relevant = [row for row in rows if isinstance(row.get('features'), dict)
                    and row['features'].get('region_key') == region_key]
        if not relevant:
            return None
        latest = relevant[0]
        features = latest.get('features') or {}
        return {
            'sar_coverage_state': str(features.get('sar_coverage_state') or 'unknown'),
            'wet_snow_fraction': features.get('wet_snow_fraction'),
            'vh_db': features.get('vh_db'),
            'vv_db': features.get('vv_db'),
            'loading_rate_24h': features.get('loading_rate_24h'),
            'freshness_hours': features.get('freshness_hours'),
            'sar_scene_time': features.get('sar_scene_time'),
            'sar_active': True,
        }
    except Exception as e:
        print(f'  SAR summary fetch failed: {e}')
        return None


def build_verification_for_cell(
    cell_id: str,
    region_key: str,
    lat: float,
    lon: float,
    weather: dict,
    gibs_cover: float | None,
    sar_summary: dict | None,
    baselines: dict | None = None,
) -> tuple[dict, dict]:
    """Build verification packet and fusion evidence for a single cell."""
    readings: dict[str, SensorReading] = {}
    observations: list[SensorObservation] = []

    # Weather reading
    current = weather.get('current', {})
    daily = weather.get('daily', {})
    snow_depth_cm = current.get('snow_depth')
    snowfall_24h = (daily.get('snowfall_sum') or [0])[0] if daily else 0

    readings['weather'] = SensorReading(
        source='weather',
        snow_depth_m=float(snow_depth_cm) / 100.0 if snow_depth_cm is not None else None,
        loading_rate_24h=float(snowfall_24h) / 100.0 if snowfall_24h is not None else None,
        freshness_hours=1.0,
    )
    observations.append(SensorObservation(
        source='weather',
        snow_depth_m=float(snow_depth_cm) / 100.0 if snow_depth_cm is not None else None,
        loading_rate_24h=float(snowfall_24h) / 100.0 if snowfall_24h is not None else None,
        freshness_hours=1.0,
    ))

    # SAR reading
    if sar_summary and isinstance(sar_summary, dict):
        readings['sar'] = SensorReading(
            source='sar',
            snow_cover_fraction=sar_summary.get('wet_snow_fraction'),
            loading_rate_24h=sar_summary.get('loading_rate_24h'),
            freshness_hours=sar_summary.get('freshness_hours'),
        )
        observations.append(SensorObservation(
            source='sar',
            wet_snow_fraction=sar_summary.get('wet_snow_fraction'),
            freshness_hours=sar_summary.get('freshness_hours'),
        ))

    # GIBS reading
    if gibs_cover is not None:
        readings['gibs'] = SensorReading(
            source='gibs',
            snow_cover_fraction=gibs_cover,
            freshness_hours=6.0,
        )
        observations.append(SensorObservation(
            source='gibs',
            snow_cover_fraction=gibs_cover,
            freshness_hours=6.0,
        ))

    # Fetch baselines for this cell if available
    baseline_p25 = None
    baseline_p50 = None
    baseline_p75 = None
    if baselines and 'snowfall_sum_cm' in baselines:
        bp = baselines['snowfall_sum_cm']
        # Convert cm to meters to match loading_rate_24h units
        baseline_p25 = bp.get('p25') / 100.0 if bp.get('p25') is not None else None
        baseline_p50 = bp.get('p50') / 100.0 if bp.get('p50') is not None else None
        baseline_p75 = bp.get('p75') / 100.0 if bp.get('p75') is not None else None

    # Build anomaly detection with baselines
    flags, packet = detect_anomalies(
        cell_id=cell_id,
        region_key=region_key,
        readings=readings,
        baseline_p25=baseline_p25,
        baseline_p50=baseline_p50,
        baseline_p75=baseline_p75,
        weather_snowfall_cm=snowfall_24h,
        physics_method='regional',
    )

    # Build fusion evidence
    fused = fuse_observations(observations)

    return packet.to_dict(), fused.to_dict()


def main():
    if not SUPABASE_URL or not SERVICE_KEY:
        print('ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set')
        sys.exit(1)

    print(f'=== Verification Spine Smoke Test ===')
    print(f'Region: {REGION_KEY}')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}')
    print()

    # Load region config
    regions = load_regions()
    region = next((r for r in regions if r.key == REGION_KEY), None)
    if not region:
        print(f'ERROR: Region {REGION_KEY} not found')
        sys.exit(1)

    print(f'Region center: {region.center}')
    print(f'Region bbox: {region.bbox}')
    print()

    # Fetch SAR summary
    print('Fetching SAR summary from Supabase...')
    sar_summary = fetch_sar_summary(REGION_KEY)
    if sar_summary:
        print(f'  SAR: {sar_summary.get("sar_coverage_state")}, wet_snow_fraction={sar_summary.get("wet_snow_fraction")}')
    else:
        print('  No SAR events found for region')

    # Fetch GIBS snow cover for region center
    print('Fetching GIBS snow cover...')
    from datetime import date as date_cls
    today = date_cls.today()
    gibs_result = None
    try:
        gibs_result = fetch_gibs_snow_cover(region.center[0], region.center[1], today)
        if gibs_result:
            print(f'  GIBS: snow_cover_fraction={gibs_result.snow_cover_fraction:.3f}')
        else:
            print('  GIBS: unavailable')
    except Exception as e:
        print(f'  GIBS fetch failed: {e}')

    gibs_cover = gibs_result.snow_cover_fraction if gibs_result else None

    # Build a 5x5 grid subset around region center
    lat_min, lat_max = region.bbox[0], region.bbox[2]
    lon_min, lon_max = region.bbox[1], region.bbox[3]
    lat_step = (lat_max - lat_min) / GRID_SUBSET
    lon_step = (lon_max - lon_min) / GRID_SUBSET

    cells = []
    sensor_obs_records = []
    verification_packets = {}

    print(f'\nProcessing {GRID_SUBSET}x{GRID_SUBSET} grid subset...')

    for i in range(GRID_SUBSET):
        for j in range(GRID_SUBSET):
            cell_lat = lat_min + (i + 0.5) * lat_step
            cell_lon = lon_min + (j + 0.5) * lon_step
            cell_id = f'{REGION_KEY}_c{i}_{j}'

            # Fetch weather for this cell
            try:
                weather = fetch_current_weather(cell_lat, cell_lon)
            except Exception as e:
                print(f'  {cell_id}: weather fetch failed: {e}')
                continue

            # Fetch baselines for this cell from Supabase
            cell_baselines = None
            try:
                from backend.common.supabase_io import rest_get as _rest_get
                bl_rows = _rest_get(
                    'verification_baselines',
                    params={
                        'region_key': f'eq.{REGION_KEY}',
                        'cell_id': f'eq.{cell_id}',
                        'sensor': 'eq.weather',
                        'window': 'eq.30d',
                        'limit': '1',
                    },
                ) or []
                if bl_rows:
                    cell_baselines = bl_rows[0].get('stats')
                    if i == 0 and j == 0:
                        print(f'  DEBUG: baselines for {cell_id}: {cell_baselines}')
                else:
                    if i == 0 and j == 0:
                        print(f'  DEBUG: no baselines found for {cell_id}')
            except Exception as e:
                if i == 0 and j == 0:
                    print(f'  DEBUG: baseline fetch error: {e}')

            # Build verification data
            vp, fe = build_verification_for_cell(
                cell_id, REGION_KEY, cell_lat, cell_lon,
                weather, gibs_cover, sar_summary,
                baselines=cell_baselines,
            )

            verification_packets[cell_id] = {
                'verification_packet': vp,
                'fusion_evidence': fe,
            }

            # Collect sensor observation for persistence
            current = weather.get('current', {})
            snow_depth_cm = current.get('snow_depth')
            sensor_obs_records.append({
                'region_key': REGION_KEY,
                'cell_id': cell_id,
                'sensor': 'weather_obs',
                'window': '30d',
                'stats': {
                    'snow_depth_m': float(snow_depth_cm) / 100.0 if snow_depth_cm else None,
                    'temperature_2m': current.get('temperature_2m'),
                    'snowfall': current.get('snowfall'),
                },
            })

            if gibs_cover is not None:
                sensor_obs_records.append({
                    'region_key': REGION_KEY,
                    'cell_id': cell_id,
                    'sensor': 'gibs_obs',
                    'window': '30d',
                    'stats': {
                        'snow_cover_fraction': gibs_cover,
                    },
                })

            cells.append({
                'lat': cell_lat,
                'lon': cell_lon,
                'cell_id': cell_id,
                'verification_packet': vp,
                'fusion_evidence': fe,
            })

            # Rate limit: small delay between weather calls
            time.sleep(0.5)

    print(f'\nProcessed {len(cells)} cells')

    if not cells:
        print('ERROR: No cells processed successfully')
        sys.exit(1)

    # Print sample verification packet
    sample = cells[0]
    print(f'\nSample cell {sample["cell_id"]}:')
    print(f'  anomaly_state: {sample["verification_packet"].get("anomaly_state")}')
    print(f'  contributing_sensors: {sample["verification_packet"].get("contributing_sensors")}')
    print(f'  packet_version: {sample["verification_packet"].get("packet_version")}')
    fe = sample['fusion_evidence']
    print(f'  fusion snow_depth_m: {fe.get("snow_depth_m")}')
    print(f'  fusion snow_cover_fraction: {fe.get("snow_cover_fraction")}')
    print(f'  fusion consensus_score: {fe.get("consensus_score")}')

    # Persist sensor observations to verification_baselines
    print(f'\nPersisting {len(sensor_obs_records)} sensor observations to verification_baselines...')
    try:
        rest_upsert(
            'verification_baselines',
            sensor_obs_records,
            on_conflict='region_key,cell_id,sensor,window',
        )
        print('  Persisted successfully')
    except Exception as e:
        print(f'  Persist failed: {e}')

    # Update latest forecast_grids row with verification data
    print('\nUpdating latest forecast_grids row with verification data...')
    try:
        # Get latest row
        rows = rest_get(
            'forecast_grids',
            params={
                'region_key': f'eq.{REGION_KEY}',
                'order': 'forecast_date.desc',
                'limit': '1',
            },
        ) or []
        if rows:
            row = rows[0]
            row_id = row['id']
            # grid_geojson is the array the frontend reads for cell data
            grid_geojson = row.get('grid_geojson') or []
            if isinstance(grid_geojson, str):
                grid_geojson = json.loads(grid_geojson)

            if isinstance(grid_geojson, list) and len(grid_geojson) > 0:
                # Enrich existing cells with verification data
                for cell in grid_geojson:
                    cid = cell.get('cell_id') or cell.get('cellId')
                    if cid and cid in verification_packets:
                        cell['verification_packet'] = verification_packets[cid]['verification_packet']
                        cell['fusion_evidence'] = verification_packets[cid]['fusion_evidence']
                        cell['anomaly_score'] = verification_packets[cid]['verification_packet'].get('anomaly_state') == 'anomaly'
                patch_row_by_id('forecast_grids', row_id, {'grid_geojson': grid_geojson})
                print(f'  Updated forecast_grids row {row_id} grid_geojson with verification data for {len(verification_packets)} cells')
            else:
                # grid_geojson is empty — populate it with our verification cells
                new_cells = []
                for c in cells:
                    new_cells.append({
                        'cell_id': c['cell_id'],
                        'lat': c['lat'],
                        'lon': c['lon'],
                        'verification_packet': c['verification_packet'],
                        'fusion_evidence': c['fusion_evidence'],
                        'anomaly_score': c['verification_packet'].get('anomaly_state') == 'anomaly',
                        'composite_risk_level': 0.3,
                    })
                patch_row_by_id('forecast_grids', row_id, {'grid_geojson': new_cells})
                print(f'  Populated forecast_grids row {row_id} grid_geojson with {len(new_cells)} verification cells')
        else:
            print('  No forecast_grids rows found for region')
    except Exception as e:
        print(f'  Update failed: {e}')

    print('\n=== Smoke test complete ===')
    print(f'Cells processed: {len(cells)}')
    print(f'Sensor observations persisted: {len(sensor_obs_records)}')
    print(f'Verification packets generated: {len(verification_packets)}')


if __name__ == '__main__':
    main()
