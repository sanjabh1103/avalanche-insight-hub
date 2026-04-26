"""Historical SAR backfill with LOCAL topo extraction (no Edge Function).

Production-ready successor to the previous trivial-solution backfill. Detects
Sentinel-1 wet-snow centroids via Google Earth Engine, then opens local
Git LFS DEMs (``backend/data/dem/<region_key>.tif``) with rasterio to compute
``elevation_m``, ``slope_angle_deg`` and ``aspect_deg`` via Horn's 3x3 method.

Key differences vs the previous version:
    * **No Edge Function** — direct batch POST to ``avalanche_events`` via REST.
      Eliminates the rate-limit crash risk of routing 2,250+ events through
      ``ingest-event``.
    * **Local rasterio topo** — heterogeneous real slope / elevation / aspect
      instead of null-valued poison.
    * **Physics gate** — ``training_eligible = true`` ONLY when
      ``25 <= slope_angle_deg <= 65``. Rows outside that band are still
      inserted (so the UI still renders them) but ``training_eligible=False``
      keeps them out of the KMeansSMOTE feature space.
    * **Historical timestamps preserved** — each centroid is stamped with the
      mean Sentinel-1 sensing time from its window, so Open-Meteo weather
      joins align to the actual storm cycle.

Safety rails:
    * Missing GEE or Supabase credentials → ``exit 0`` (noop, CI-safe).
    * DEM missing for a region → rows from that region are skipped.
    * Out-of-bounds centroids (outside the local DEM) → skipped.
    * Per-chunk errors are logged and the backfill continues.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.common.label_governance import materialize_label_governance
from backend.common.regions import Region, load_regions, repo_root
from backend.common.real_features import extract_cell_terrain
from backend.common.sar_artifacts import persist_sar_artifacts
from backend.common.supabase_io import has_supabase_credentials, rest_insert

import backend.gee_extractor as gee


# --- Physics gate ------------------------------------------------------------
SLOPE_MIN_DEG = float(os.getenv('PHYSICS_SLOPE_MIN_DEG', '25'))
SLOPE_MAX_DEG = float(os.getenv('PHYSICS_SLOPE_MAX_DEG', '65'))

# --- Windowing ---------------------------------------------------------------
DEFAULT_START = os.getenv('BACKFILL_START_DATE', '2023-11-01')
DEFAULT_END = os.getenv('BACKFILL_END_DATE', '2024-04-30')
CHUNK_DAYS = int(os.getenv('BACKFILL_CHUNK_DAYS', '7'))  # weekly ~ Sentinel-1 revisit
BATCH_SIZE = int(os.getenv('BACKFILL_BATCH_SIZE', '200'))

# --- DEM -------------------------------------------------------------------
DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'

def extract_topo(region_key: str, lat: float, lon: float) -> dict | None:
    """Horn's 3x3 slope/aspect from local DEM using the shared robust extractor."""
    try:
        dem_path = DEM_DIR / f'{region_key}.tif'
        if not dem_path.exists():
            raise FileNotFoundError(f'DEM not found: {dem_path}')
        terrain = extract_cell_terrain(str(dem_path), lat=lat, lng=lon)
    except FileNotFoundError as exc:
        print(f'[topo] {exc}', file=sys.stderr)
        return None
    return {
        'elevation_m': int(round(float(terrain['elevation_m']))),
        'slope_angle_deg': round(float(terrain['slope_angle_deg']), 3),
        'aspect_deg': round(float(terrain['aspect_deg']), 3),
        'terrain_roughness': float(terrain.get('terrain_roughness', 0.0)),
        'clamped_to_bounds': bool(terrain.get('clamped_to_bounds', 0.0)),
    }


# --- GEE centroid detection with historical timestamps ----------------------
def _parse_wkt_point(wkt: str) -> tuple[float, float] | None:
    """Parse ``SRID=4326;POINT(lng lat)`` → (lat, lng)."""
    if not wkt or 'POINT(' not in wkt:
        return None
    inner = wkt[wkt.index('POINT(') + 6:].rstrip(')')
    parts = inner.split()
    if len(parts) != 2:
        return None
    try:
        lng, lat = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    return lat, lng


def _scenes_mean_timestamp(ee, region: Region, start: datetime, end: datetime) -> tuple[int, datetime | None]:
    """Return (scene_count, mean_sensing_time) for the window."""
    lat_min, lng_min, lat_max, lng_max = region.bbox
    region_geom = ee.Geometry.Rectangle([lng_min, lat_min, lng_max, lat_max])
    s1 = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(region_geom)
        .filterDate(start.isoformat(), end.isoformat())
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
    )
    n = int(s1.size().getInfo() or 0)
    if n == 0:
        return 0, None
    t_millis = s1.aggregate_mean('system:time_start').getInfo()
    if t_millis is None:
        # Fallback to window midpoint.
        midpoint = start + (end - start) / 2
        return n, midpoint
    return n, datetime.fromtimestamp(t_millis / 1000.0, tz=timezone.utc)


def _enrich_and_gate(region: Region, events: list[dict], scene_ts: datetime) -> list[dict]:
    """Attach local topo, apply physics gate, stamp historical timestamp."""
    enriched: list[dict] = []
    for ev in events:
        latlon = _parse_wkt_point(ev.get('location', ''))
        if not latlon:
            continue
        lat, lng = latlon
        topo = extract_topo(region.key, lat, lng)
        if topo is None:
            continue
        slope = topo['slope_angle_deg']
        source_training_eligible = bool(ev.get('training_eligible', True))
        physics_training_eligible = SLOPE_MIN_DEG <= slope <= SLOPE_MAX_DEG
        training_eligible = source_training_eligible and physics_training_eligible
        ev['elevation_m'] = topo['elevation_m']
        ev['slope_angle_deg'] = topo['slope_angle_deg']
        ev['aspect_deg'] = topo['aspect_deg']
        ev['topo_source'] = 'srtm_local_rasterio'
        ev['topo_resolution_m'] = 30.0
        ev['training_eligible'] = training_eligible
        ev['label_confidence'] = float(ev.get('label_confidence') or (0.72 if training_eligible else 0.48))
        ev['training_weight'] = float(ev.get('training_weight') or (0.85 if training_eligible else 0.35))
        ev['source_model'] = str(ev.get('source_model') or 'gee_threshold_baseline_v1')
        ev['source_scene_ids'] = [str(scene_id) for scene_id in ev.get('source_scene_ids') or ev.get('features', {}).get('sar_scene_ids') or []]
        ev['geometry_type'] = str(ev.get('geometry_type') or 'polygon')
        ev['mask_asset_ref'] = ev.get('mask_asset_ref')
        if not source_training_eligible:
            ev['training_eligible_reason'] = ev.get('training_eligible_reason') or 'sar_low_coverage'
        elif not physics_training_eligible:
            ev['training_eligible_reason'] = f'physics_gate_slope_{slope:.1f}deg_out_of_25_65'
        else:
            ev['training_eligible_reason'] = None
        ev['timestamp'] = scene_ts.isoformat()
        features = ev.setdefault('features', {})
        features['sar_mean_sensing_time'] = scene_ts.isoformat()
        features['ingest_type'] = 'historical_backfill_v2_local_topo'
        features['physics_gate_deg'] = [SLOPE_MIN_DEG, SLOPE_MAX_DEG]
        governance = materialize_label_governance(ev)
        ev['label_confidence'] = governance['label_confidence']
        ev['training_weight'] = governance['training_weight']
        ev['training_eligible'] = governance['training_eligible']
        ev['governance_version'] = governance['governance_version']
        ev['governed_at'] = governance['governed_at']
        enriched.append(ev)
    return enriched


def _insert_batch(events: list[dict]) -> int:
    if not events:
        return 0
    if not has_supabase_credentials():
        print(f'[backfill] Supabase creds absent; would insert {len(events)} events')
        return 0
    inserted = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i:i + BATCH_SIZE]
        inserted_rows = rest_insert('avalanche_events', batch)
        try:
            persist_sar_artifacts(inserted_rows, batch)
        except Exception as exc:
            print(f'[backfill] sar artifact persistence skipped: {exc}', file=sys.stderr)
        inserted += len(inserted_rows)
    return inserted


def run_backfill(start: datetime, end: datetime) -> dict:
    if not gee._has_credentials():
        print('[backfill] GEE credentials absent. This script needs '
              'GEE_SERVICE_ACCOUNT_JSON (only configured under GitHub Actions). '
              'Exiting 0 (safe noop).')
        return {'status': 'skipped_no_gee_creds'}

    try:
        ee = gee._initialize_ee()
    except Exception as exc:
        print(f'[backfill] Earth Engine init failed: {exc}', file=sys.stderr)
        traceback.print_exc()
        return {'status': 'ee_init_failed', 'error': str(exc)}

    regions = load_regions()
    per_region: list[dict] = []
    total_inserted = 0
    total_eligible = 0

    for region in regions:
        region_inserted = 0
        region_eligible = 0
        region_rejected = 0
        chunks: list[dict] = []
        cursor = start
        while cursor < end:
            w_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
            try:
                scene_count, scene_ts = _scenes_mean_timestamp(ee, region, cursor, w_end)
                if scene_count == 0 or scene_ts is None:
                    chunks.append({
                        'window': f'{cursor.date()}->{w_end.date()}',
                        'raw': 0, 'enriched': 0, 'eligible': 0, 'rejected': 0,
                    })
                    cursor = w_end
                    continue

                raw = gee._process_region(ee, region, start_date=cursor, end_date=w_end)
                if raw and raw[0].get('features', {}).get('sar_scene_time'):
                    scene_ts = datetime.fromisoformat(raw[0]['features']['sar_scene_time'].replace('Z', '+00:00'))
                enriched = _enrich_and_gate(region, raw, scene_ts)
                eligible_count = sum(1 for e in enriched if e.get('training_eligible'))
                rejected_count = len(enriched) - eligible_count
                inserted = _insert_batch(enriched)
                region_inserted += inserted
                region_eligible += eligible_count
                region_rejected += rejected_count
                chunks.append({
                    'window': f'{cursor.date()}->{w_end.date()}',
                    'scene_ts': scene_ts.isoformat(),
                    'raw': len(raw), 'enriched': len(enriched),
                    'eligible': eligible_count, 'rejected': rejected_count,
                })
            except Exception as exc:
                print(f'[backfill] {region.key} {cursor.date()}->{w_end.date()} failed: {exc}',
                      file=sys.stderr)
                traceback.print_exc()
                chunks.append({
                    'window': f'{cursor.date()}->{w_end.date()}',
                    'error': str(exc),
                })
            cursor = w_end

        print(f'[backfill] {region.key}: inserted={region_inserted} '
              f'(eligible={region_eligible}, rejected_physics={region_rejected})')
        per_region.append({
            'region': region.key,
            'inserted': region_inserted,
            'eligible': region_eligible,
            'rejected_physics': region_rejected,
            'chunks': chunks,
        })
        total_inserted += region_inserted
        total_eligible += region_eligible

    return {
        'status': 'ok',
        'start': start.date().isoformat(),
        'end': end.date().isoformat(),
        'chunk_days': CHUNK_DAYS,
        'slope_gate_deg': [SLOPE_MIN_DEG, SLOPE_MAX_DEG],
        'total_inserted': total_inserted,
        'total_training_eligible': total_eligible,
        'per_region': per_region,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default=DEFAULT_START, help='YYYY-MM-DD')
    parser.add_argument('--end', default=DEFAULT_END, help='YYYY-MM-DD')
    args = parser.parse_args(argv)

    start = datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if end <= start:
        print('[backfill] end must be after start', file=sys.stderr)
        return 2

    summary = run_backfill(start, end)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get('status') in ('ok', 'skipped_no_gee_creds') else 2


if __name__ == '__main__':
    sys.exit(main())
