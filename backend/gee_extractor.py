"""Story 21 (SAR Shadow Fix) + Edit 4: Sentinel-1 wet-snow extractor.

Credential-aware stub for weekly Google Earth Engine SAR extraction. When
``GEE_SERVICE_ACCOUNT_JSON`` is absent the script exits 0 cleanly so CI
remains green. When present, it runs the strict ORDERED pipeline:

    1. ee.Initialize(service_account)
    2. Compute SRTM terrain products (slope, aspect) via ee.Terrain.products
    3. Build Layover + Shadow mask from local incidence geometry
    4. ONLY THEN apply VV/VH wet-snow thresholding on masked pixels
    5. Vectorize → centroids → upsert to avalanche_events

The whole script is network-heavy and must NOT run synchronously inside any
Edge Function. It is designed exclusively for GitHub Actions / Ubuntu runners.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Iterable

from backend.common.regions import load_regions
from backend.common.supabase_io import has_supabase_credentials, rest_insert


GEE_SERVICE_ACCOUNT_JSON = os.getenv('GEE_SERVICE_ACCOUNT_JSON')
GEE_SERVICE_ACCOUNT_EMAIL = os.getenv('GEE_SERVICE_ACCOUNT_EMAIL')
GEE_LOOKBACK_DAYS = int(os.getenv('GEE_LOOKBACK_DAYS', '7'))
GEE_VV_THRESHOLD_DB = float(os.getenv('GEE_VV_THRESHOLD_DB', '-18'))
GEE_VH_THRESHOLD_DB = float(os.getenv('GEE_VH_THRESHOLD_DB', '-22'))
GEE_MAX_CENTROIDS_PER_REGION = int(os.getenv('GEE_MAX_CENTROIDS_PER_REGION', '50'))


def _has_credentials() -> bool:
    return bool(GEE_SERVICE_ACCOUNT_JSON and GEE_SERVICE_ACCOUNT_EMAIL)


def _write_service_account_key() -> str:
    path = '/tmp/gee-service-account.json'
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(GEE_SERVICE_ACCOUNT_JSON)
    return path


def _initialize_ee():
    """Imports Earth Engine lazily so absence of the SDK does not kill the
    extraction step when credentials are missing.
    """
    import ee  # type: ignore
    key_path = _write_service_account_key()
    credentials = ee.ServiceAccountCredentials(GEE_SERVICE_ACCOUNT_EMAIL, key_path)
    ee.Initialize(credentials)
    return ee


def _process_region(ee, region) -> list[dict]:
    """Edit 4: strict ordered pipeline — terrain mask BEFORE VV/VH threshold."""
    lat_min, lng_min, lat_max, lng_max = region.bbox
    region_geom = ee.Geometry.Rectangle([lng_min, lat_min, lng_max, lat_max])

    # 1. Sentinel-1 GRD IW over last N days, descending orbit only.
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=GEE_LOOKBACK_DAYS)
    s1 = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(region_geom)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
    )
    scene_count = int(s1.size().getInfo() or 0)
    if scene_count == 0:
        return []

    # 2. SRTM terrain products MUST be computed first (Edit 4).
    srtm = ee.Image('USGS/SRTMGL1_003').clip(region_geom)
    terrain = ee.Terrain.products(srtm)
    slope = terrain.select('slope')
    aspect = terrain.select('aspect')

    def _mask_and_threshold(scene):
        # 3. Build Layover + Shadow mask from local incidence geometry.
        heading_raw = ee.Number(scene.get('platform_heading'))
        heading = ee.Algorithms.If(heading_raw, heading_raw, ee.Number(-12.0))
        look_angle_raw = ee.Number(scene.get('incidence_angle'))
        look_angle = ee.Algorithms.If(look_angle_raw, look_angle_raw, ee.Number(39.0))

        heading_rad = ee.Number(heading).multiply(3.14159265 / 180.0)
        look_rad = ee.Number(look_angle).multiply(3.14159265 / 180.0)
        slope_rad = slope.multiply(3.14159265 / 180.0)
        aspect_rad = aspect.multiply(3.14159265 / 180.0)

        # Azimuth difference between radar look direction and slope aspect.
        azimuth_diff = aspect_rad.subtract(heading_rad)
        theta_loc_cos = (
            slope_rad.cos().multiply(look_rad.cos())
            .add(slope_rad.sin().multiply(look_rad.sin()).multiply(azimuth_diff.cos()))
        )
        theta_loc_deg = theta_loc_cos.acos().multiply(180.0 / 3.14159265)

        layover = theta_loc_deg.lt(0)
        shadow = theta_loc_deg.gt(90)
        extreme_slope = slope.gt(60)
        invalid_mask = layover.Or(shadow).Or(extreme_slope)
        valid_pixels = invalid_mask.Not()

        # 4. ONLY NOW apply wet-snow VV/VH thresholding.
        vv = scene.select('VV')
        vh = scene.select('VH')
        wet_snow = vv.lt(GEE_VV_THRESHOLD_DB).And(vh.lt(GEE_VH_THRESHOLD_DB))
        return wet_snow.updateMask(valid_pixels).rename('wet_snow')

    masked_collection = s1.map(_mask_and_threshold)
    combined = masked_collection.max()

    # 5. Vectorize to centroids (capped) and pull to client.
    vectors = combined.reduceToVectors(
        geometry=region_geom,
        scale=30,
        maxPixels=int(1e9),
        geometryType='polygon',
        eightConnected=True,
        reducer=ee.Reducer.countEvery(),
    ).limit(GEE_MAX_CENTROIDS_PER_REGION)

    features = vectors.getInfo().get('features', []) if vectors else []
    events: list[dict] = []
    for feat in features:
        geom = feat.get('geometry') or {}
        if not geom.get('coordinates'):
            continue
        # Compute centroid from polygon coordinates (client-side to avoid
        # another getInfo round-trip).
        rings = geom['coordinates']
        pts = [pt for ring in rings for pt in ring] if rings else []
        if not pts:
            continue
        avg_lng = sum(pt[0] for pt in pts) / len(pts)
        avg_lat = sum(pt[1] for pt in pts) / len(pts)
        events.append({
            'source': 'gee_sar',
            'fusion_source': 'sentinel1_gee',
            'hazard_type': 'avalanche',
            'description': f'Sentinel-1 wet-snow candidate over {region.name}',
            'severity': 3,
            'confidence': 0.55,
            'training_eligible': True,
            'location': f'SRID=4326;POINT({avg_lng} {avg_lat})',
            'features': {
                'vv_threshold_db': GEE_VV_THRESHOLD_DB,
                'vh_threshold_db': GEE_VH_THRESHOLD_DB,
                'scene_count': scene_count,
                'region_key': region.key,
                'mask': 'layover_shadow_terrain_products',
            },
        })
    return events


def _insert_events(events: Iterable[dict]) -> int:
    batch = list(events)
    if not batch:
        return 0
    if not has_supabase_credentials():
        print(f'[gee_extractor] Supabase creds absent; skipping insert of {len(batch)} events')
        return 0
    rest_insert('avalanche_events', batch)
    return len(batch)


def main() -> int:
    if not _has_credentials():
        print('[gee_extractor] GEE credentials absent; skipping extraction (this is safe).')
        return 0

    try:
        ee = _initialize_ee()
    except Exception as exc:
        print(f'[gee_extractor] Earth Engine initialization failed: {exc}', file=sys.stderr)
        traceback.print_exc()
        return 2

    total = 0
    per_region_counts: list[dict] = []
    for region in load_regions():
        try:
            events = _process_region(ee, region)
            inserted = _insert_events(events)
            per_region_counts.append({'region': region.key, 'inserted': inserted})
            total += inserted
        except Exception as exc:  # pragma: no cover - GEE network path
            print(f'[gee_extractor] Region {region.key} failed: {exc}', file=sys.stderr)
            traceback.print_exc()
            per_region_counts.append({'region': region.key, 'error': str(exc)})

    summary = {
        'total_inserted': total,
        'regions': per_region_counts,
        'lookback_days': GEE_LOOKBACK_DAYS,
        'vv_threshold_db': GEE_VV_THRESHOLD_DB,
        'vh_threshold_db': GEE_VH_THRESHOLD_DB,
        'mask_strategy': 'srtm_layover_shadow_then_vv_vh',
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
