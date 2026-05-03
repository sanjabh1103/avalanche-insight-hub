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

from backend.common.label_governance import materialize_label_governance
from backend.common.regions import load_regions
from backend.common.sar_artifacts import persist_sar_artifacts
from backend.common.supabase_io import has_supabase_credentials, rest_insert


GEE_SERVICE_ACCOUNT_JSON = os.getenv('GEE_SERVICE_ACCOUNT_JSON')
GEE_SERVICE_ACCOUNT_EMAIL = os.getenv('GEE_SERVICE_ACCOUNT_EMAIL')
GEE_LOOKBACK_DAYS = int(os.getenv('GEE_LOOKBACK_DAYS', '7'))
GEE_VV_THRESHOLD_DB = float(os.getenv('GEE_VV_THRESHOLD_DB', '-18'))
GEE_VH_THRESHOLD_DB = float(os.getenv('GEE_VH_THRESHOLD_DB', '-22'))
GEE_MAX_CENTROIDS_PER_REGION = int(os.getenv('GEE_MAX_CENTROIDS_PER_REGION', '50'))
# Vectorization knobs — coarser scale + geometry simplification keep the
# polygon edge count well below Earth Engine's 2M-edges cap for large,
# wet-snow-rich regions (Himalayas, Cascades, Andes).
GEE_VECTORIZE_SCALE_M = int(os.getenv('GEE_VECTORIZE_SCALE_M', '90'))
GEE_SIMPLIFY_MAX_ERROR_M = float(os.getenv('GEE_SIMPLIFY_MAX_ERROR_M', '200'))
GEE_MAX_PIXELS = int(float(os.getenv('GEE_MAX_PIXELS', '1e10')))


def _sar_training_bucket(*, coverage_state: str, scene_count: int) -> tuple[str, bool, str | None, float, float]:
    if coverage_state == 'full_coverage':
        return ('core_training', True, None, 0.72, 0.8)
    if scene_count >= 2:
        return ('weak_training', True, 'sar_low_coverage_weak_training', 0.58, 0.45)
    return ('audit_only', False, 'sar_single_pass_audit_only', 0.35, 0.15)


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


def _process_region(ee, region, start_date: datetime | None = None, end_date: datetime | None = None) -> list[dict]:
    """Edit 4: strict ordered pipeline — terrain mask BEFORE VV/VH threshold.

    ``start_date`` / ``end_date`` override the default N-day lookback, enabling
    the historical backfill script to reuse this exact pipeline.
    """
    lat_min, lng_min, lat_max, lng_max = region.bbox
    region_geom = ee.Geometry.Rectangle([lng_min, lat_min, lng_max, lat_max])

    # 1. Sentinel-1 GRD IW over the requested window, both passes.
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    if start_date is None:
        start_date = end_date - timedelta(days=GEE_LOOKBACK_DAYS)
    s1 = (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(region_geom)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
    )
    scene_count = int(s1.size().getInfo() or 0)
    if scene_count == 0:
        return []
    ascending_count = int(s1.filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING')).size().getInfo() or 0)
    descending_count = int(s1.filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING')).size().getInfo() or 0)
    scene_ids = s1.aggregate_array('system:index').getInfo() or []
    mean_time_ms = s1.aggregate_mean('system:time_start').getInfo()
    mean_scene_time = datetime.fromtimestamp(mean_time_ms / 1000.0, tz=timezone.utc).isoformat() if mean_time_ms else None
    coverage_state = 'full_coverage' if ascending_count > 0 and descending_count > 0 else 'low_coverage'
    training_bucket, training_eligible, training_reason, label_confidence, training_weight = _sar_training_bucket(
        coverage_state=coverage_state,
        scene_count=scene_count,
    )

    # 2. SRTM terrain products MUST be computed first (Edit 4).
    srtm = ee.Image('USGS/SRTMGL1_003').clip(region_geom)
    terrain = ee.Terrain.products(srtm)
    slope = terrain.select('slope')
    aspect = terrain.select('aspect')

    def _mask_and_threshold(scene):
        # 3. Build Layover + Shadow mask from local incidence geometry.
        heading_raw = ee.Number(scene.get('platform_heading'))
        heading = ee.Algorithms.If(heading_raw, heading_raw, ee.Number(-12.0))
        look_angle = scene.select('angle')

        heading_rad = ee.Number(heading).multiply(3.14159265 / 180.0)
        look_rad = look_angle.multiply(3.14159265 / 180.0)
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
        millis = ee.Image(scene.getNumber('system:time_start')).rename('millis').toFloat()
        return wet_snow.updateMask(valid_pixels).rename('wet_snow').addBands(millis)

    masked_collection = s1.map(_mask_and_threshold)
    combined = masked_collection.qualityMosaic('millis').select('wet_snow')

    # 5. Vectorize to centroids (capped) and pull to client.
    # Fix for 'Geometry has too many edges' on large regions: vectorize at a
    # coarser scale and simplify each feature geometry before pulling it to
    # the client. EE's per-geometry edge cap is 2_000_000; at scale=90 with
    # 200 m simplification, our 2°x2° bboxes stay well under that.
    vectors = combined.reduceToVectors(
        geometry=region_geom,
        scale=GEE_VECTORIZE_SCALE_M,
        maxPixels=GEE_MAX_PIXELS,
        geometryType='polygon',
        eightConnected=True,
        reducer=ee.Reducer.countEvery(),
        bestEffort=True,
    ).limit(GEE_MAX_CENTROIDS_PER_REGION)

    def _simplify(feature):
        return feature.simplify(GEE_SIMPLIFY_MAX_ERROR_M)

    vectors = vectors.map(_simplify)

    try:
        features = vectors.getInfo().get('features', []) if vectors else []
    except Exception as exc:
        # Belt-and-braces: if vectorization still blows up on a pathological
        # region, retry once at an even coarser scale with heavier simplify.
        msg = str(exc)
        if 'too many edges' not in msg and 'Geometry' not in msg:
            raise
        print(f'[gee_extractor] {region.key}: vectorize retry after edge-cap: {msg}', file=sys.stderr)
        vectors = combined.reduceToVectors(
            geometry=region_geom,
            scale=GEE_VECTORIZE_SCALE_M * 3,
            maxPixels=GEE_MAX_PIXELS,
            geometryType='polygon',
            eightConnected=True,
            reducer=ee.Reducer.countEvery(),
            bestEffort=True,
        ).limit(GEE_MAX_CENTROIDS_PER_REGION).map(
            lambda f: f.simplify(GEE_SIMPLIFY_MAX_ERROR_M * 3)
        )
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
        event_payload = {
            'source': 'gee_sar',
            'fusion_source': 'sentinel1_gee',
            'hazard_type': 'avalanche',
            'description': f'Sentinel-1 wet-snow candidate over {region.name}',
            'severity': 3,
            'confidence': 0.55,
            'label_confidence': label_confidence,
            'training_weight': training_weight,
            'training_eligible': training_eligible,
            'training_eligible_reason': training_reason,
            'timestamp': mean_scene_time,
            'location': f'SRID=4326;POINT({avg_lng} {avg_lat})',
            'source_model': 'gee_threshold_baseline_v1',
            'source_scene_ids': [str(scene_id) for scene_id in scene_ids],
            'geometry_type': 'polygon',
            'mask_asset_ref': None,
            'features': {
                'vv_threshold_db': GEE_VV_THRESHOLD_DB,
                'vh_threshold_db': GEE_VH_THRESHOLD_DB,
                'scene_count': scene_count,
                'ascending_scene_count': ascending_count,
                'descending_scene_count': descending_count,
                'region_key': region.key,
                'mask': 'layover_shadow_terrain_products',
                'sar_pass': 'fused',
                'sar_scene_time': mean_scene_time,
                'sar_scene_ids': scene_ids,
                'sar_coverage_state': coverage_state,
                'training_bucket': training_bucket,
                'shadow_mask_applied': True,
                'fusion_method': 'quality_mosaic_latest_pixel_v1',
                'sar_geometry': geom,
                'sar_centroid': {'lat': avg_lat, 'lng': avg_lng},
            },
        }
        governance = materialize_label_governance(event_payload)
        event_payload.update({
            'label_confidence': governance['label_confidence'],
            'training_weight': governance['training_weight'],
            'training_eligible': governance['training_eligible'],
            'governance_version': governance['governance_version'],
            'governed_at': governance['governed_at'],
        })
        events.append(event_payload)
    return events


def build_region_sar_summary(
    *,
    region_key: str,
    ascending_count: int,
    descending_count: int,
    coverage_state: str,
    events: list[dict],
) -> dict[str, object]:
    low_coverage_rejects = sum(1 for event in events if str(event.get('training_eligible_reason') or '').startswith('sar_low_coverage'))
    eligible_events = sum(1 for event in events if bool(event.get('training_eligible')))
    core_training_events = sum(
        1 for event in events
        if ((event.get('features') if isinstance(event.get('features'), dict) else {}) or {}).get('training_bucket') == 'core_training'
    )
    weak_training_events = sum(
        1 for event in events
        if ((event.get('features') if isinstance(event.get('features'), dict) else {}) or {}).get('training_bucket') == 'weak_training'
    )
    audit_only_events = sum(
        1 for event in events
        if ((event.get('features') if isinstance(event.get('features'), dict) else {}) or {}).get('training_bucket') == 'audit_only'
    )
    return {
        'region': region_key,
        'ascending_scene_count': ascending_count,
        'descending_scene_count': descending_count,
        'fused_detections': len(events),
        'low_coverage_rejects': low_coverage_rejects,
        'eligible_detections': eligible_events,
        'core_training_detections': core_training_events,
        'weak_training_detections': weak_training_events,
        'audit_only_detections': audit_only_events,
        'sar_coverage_state': coverage_state,
        'fusion_method': 'quality_mosaic_latest_pixel_v1',
    }


def _insert_events(events: Iterable[dict]) -> int:
    batch = list(events)
    if not batch:
        return 0
    if not has_supabase_credentials():
        print(f'[gee_extractor] Supabase creds absent; skipping insert of {len(batch)} events')
        return 0
    inserted_rows = rest_insert('avalanche_events', batch)
    try:
        persist_sar_artifacts(inserted_rows, batch)
    except Exception as exc:
        print(f'[gee_extractor] sar artifact persistence skipped: {exc}', file=sys.stderr)
    return len(inserted_rows)


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
            first_features = next((event.get('features') for event in events if isinstance(event.get('features'), dict)), {})
            ascending_count = int(first_features.get('ascending_scene_count', 0) or 0)
            descending_count = int(first_features.get('descending_scene_count', 0) or 0)
            coverage_state = str(first_features.get('sar_coverage_state') or 'low_coverage')
            per_region_counts.append({
                'inserted': inserted,
                **build_region_sar_summary(
                    region_key=region.key,
                    ascending_count=ascending_count,
                    descending_count=descending_count,
                    coverage_state=coverage_state,
                    events=events,
                ),
            })
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
        'fusion_method': 'quality_mosaic_latest_pixel_v1',
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
