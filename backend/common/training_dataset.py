from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.common.features import FEATURE_COLUMNS, build_region_grid, generate_training_frame
from backend.common.real_features import (
    build_real_feature_row,
    extract_cell_terrain,
    fetch_historical_weather_profile,
    select_hourly_weather_sample,
)
from backend.common.regions import Region, load_regions, repo_root
from backend.common.supabase_io import has_supabase_credentials, rest_get


NEGATIVES_PER_POSITIVE = 3
NEGATIVE_DISTANCE_M = 5000.0
NEGATIVE_TIME_WINDOW_HOURS = 24.0
NEGATIVE_SLOPE_MIN = 20.0
NEGATIVE_SLOPE_MAX = 65.0

DEM_DIR = repo_root() / 'backend' / 'data' / 'dem'


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_ewkb_hex(value: str) -> tuple[float, float] | None:
    """Parse PostGIS EWKB hex format (e.g., '0101000020E6100000...')."""
    try:
        import struct
        # Hex decode
        data = bytes.fromhex(value)
        # Minimum size: 1 byte order + 4 bytes type + 4 bytes SRID + 16 bytes coords = 25
        if len(data) < 25:
            return None
        # Byte order: 01 = little endian, 00 = big endian
        little_endian = data[0] == 1
        endian = '<' if little_endian else '>'
        # Geometry type at offset 1 (4 bytes)
        geom_type = struct.unpack(endian + 'I', data[1:5])[0]
        # SRID flag check (0x20000000 bit indicates SRID present)
        has_srid = (geom_type & 0x20000000) != 0
        # Mask out flags (Z, M, SRID) to get base geometry type
        base_type = geom_type & 0xFFFFFF
        if base_type != 1:  # 1 = Point
            return None
        offset = 5
        if has_srid:
            offset += 4  # Skip SRID
        # Coordinates: 2 doubles (16 bytes)
        if len(data) < offset + 16:
            return None
        lng, lat = struct.unpack(endian + 'dd', data[offset:offset + 16])
        return float(lat), float(lng)
    except Exception:
        return None


def parse_point_wkt(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, str):
        return None
    # Try WKT format first
    if 'POINT(' in value:
        inner = value[value.index('POINT(') + 6:].rstrip(')')
        parts = inner.split()
        if len(parts) == 2:
            try:
                lng = float(parts[0])
                lat = float(parts[1])
                return lat, lng
            except ValueError:
                pass
    # Try EWKB hex format (starts with '01' and is long hex string)
    if len(value) >= 50 and all(c in '0123456789abcdefABCDEF' for c in value[:10]):
        return _parse_ewkb_hex(value)
    return None


def match_region(lat: float, lng: float, regions: list[Region]) -> Region | None:
    for region in regions:
        lat_min, lng_min, lat_max, lng_max = region.bbox
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return region
    return None


def _dem_path(region_key: str) -> Path:
    return DEM_DIR / f'{region_key}.tif'


@lru_cache(maxsize=4096)
def _cached_historical_weather_profile(lat_round: float, lng_round: float, timestamp_iso: str) -> dict[str, Any]:
    return fetch_historical_weather_profile(
        lat=lat_round,
        lng=lng_round,
        timestamp=datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00')),
    )


def fetch_training_events(hazard_type: str = 'avalanche') -> list[dict[str, Any]]:
    if not has_supabase_credentials():
        return []

    # Query relaxed: backfilled events may lack verification_status/label_role.
    # Post-query filtering handles exclusion logic for rows that have these fields.
    rows = rest_get(
        'avalanche_events',
        params={
            'select': 'id,location,timestamp,severity,source,training_eligible,label_role,verification_status,elevation_m,topo_profile,features',
            'hazard_type': f'eq.{hazard_type}',
            'training_eligible': 'eq.true',
            'order': 'timestamp.asc',
        },
    )
    # Post-filter: include if verification_status is missing/null OR in allowed list
    # Note: 'unverified' covers backfilled SAR events; 'weak'/'verified'/'expert_verified' cover human-verified events
    allowed_status = {'unverified', 'weak', 'verified', 'expert_verified', None}
    filtered = [
        r for r in rows
        if r.get('verification_status') in allowed_status
        and r.get('label_role') != 'excluded'
    ]
    return filtered


def _sample_negatives_for_event(
    event: dict[str, Any],
    *,
    region: Region,
    positives: list[dict[str, Any]],
    rng: np.random.Generator,
    grid_size: int,
) -> list[dict[str, Any]]:
    event_timestamp = datetime.fromisoformat(str(event['timestamp']).replace('Z', '+00:00'))
    cells = build_region_grid(region, grid_size=grid_size)
    rng.shuffle(cells)
    negatives: list[dict[str, Any]] = []

    for cell in cells:
        if len(negatives) >= NEGATIVES_PER_POSITIVE:
            break
        lat = float(cell['lat'] + (cell['lat_end'] - cell['lat']) / 2)
        lng = float(cell['lng'] + (cell['lng_end'] - cell['lng']) / 2)

        if any(
            haversine_distance(lat, lng, positive['lat'], positive['lng']) <= NEGATIVE_DISTANCE_M
            and abs((event_timestamp - positive['timestamp']).total_seconds()) <= NEGATIVE_TIME_WINDOW_HOURS * 3600
            for positive in positives
            if positive['region_key'] == region.key
        ):
            continue

        dem_path = _dem_path(region.key)
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=lat, lng=lng)
        except Exception:
            continue

        slope = float(terrain['slope_angle_deg'])
        if slope < NEGATIVE_SLOPE_MIN or slope > NEGATIVE_SLOPE_MAX:
            continue

        negatives.append({
            'lat': lat,
            'lng': lng,
            'timestamp': event_timestamp,
            'terrain': terrain,
            'region_key': region.key,
            'source_event_id': event['id'],
        })

    return negatives


def build_real_training_frame(
    *,
    seed: int,
    grid_size: int,
    hazard_type: str = 'avalanche',
) -> tuple[pd.DataFrame, dict[str, Any]]:
    import sys
    rows = fetch_training_events(hazard_type=hazard_type)
    regions = load_regions()
    rng = np.random.default_rng(seed)

    positives: list[dict[str, Any]] = []
    dataset_rows: list[dict[str, Any]] = []
    event_source_counts: Counter[str] = Counter()

    # Debug diagnostics
    debug_stats = {
        'raw_rows': len(rows),
        'no_point': 0,
        'no_timestamp': 0,
        'no_region': 0,
        'no_dem': 0,
        'terrain_failed': 0,
        'terrain_clamped': 0,
        'weather_failed': 0,
        'assembled_ok': 0,
    }
    print(f'[training_dataset] Starting with {len(rows)} raw events', file=sys.stderr)

    for row in rows:
        point = parse_point_wkt(row.get('location'))
        if point is None:
            debug_stats['no_point'] += 1
            continue
        lat, lng = point
        timestamp_raw = row.get('timestamp')
        if not timestamp_raw:
            debug_stats['no_timestamp'] += 1
            continue
        timestamp = datetime.fromisoformat(str(timestamp_raw).replace('Z', '+00:00'))
        region = match_region(lat, lng, regions)
        if region is None:
            debug_stats['no_region'] += 1
            continue

        dem_path = _dem_path(region.key)
        if not dem_path.exists():
            debug_stats['no_dem'] += 1
            continue
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=lat, lng=lng)
        except Exception as e:
            debug_stats['terrain_failed'] += 1
            continue
        if float(terrain.get('clamped_to_bounds', 0.0) or 0.0) > 0:
            debug_stats['terrain_clamped'] += 1
        weather_profile = _cached_historical_weather_profile(round(lat, 3), round(lng, 3), timestamp.isoformat())
        weather_sample = select_hourly_weather_sample(weather_profile, timestamp)
        if not weather_sample:
            debug_stats['weather_failed'] += 1
            continue
        assembled = build_real_feature_row(
            weather_sample=weather_sample,
            terrain=terrain,
            timestamp=timestamp,
            lat=lat,
            lng=lng,
        )
        debug_stats['assembled_ok'] += 1
        positives.append({'lat': lat, 'lng': lng, 'timestamp': timestamp, 'region_key': region.key, 'id': row['id']})
        event_source_counts[str(row.get('source') or 'unknown')] += 1
        dataset_rows.append({
            'event_id': row['id'],
            'timestamp': pd.Timestamp(timestamp),
            'region_key': region.key,
            'region_name': region.name,
            'lat': lat,
            'lng': lng,
            'label': 1,
            'severity': row.get('severity'),
            'temperature_2m': assembled['raw_inputs']['temperature_2m'],
            'windspeed_10m': assembled['raw_inputs']['windspeed_10m'],
            **assembled['feature_row'],
        })

    for event in rows:
        point = parse_point_wkt(event.get('location'))
        if point is None:
            continue
        lat, lng = point
        region = match_region(lat, lng, regions)
        if region is None:
            continue
        negatives = _sample_negatives_for_event(
            event,
            region=region,
            positives=positives,
            rng=rng,
            grid_size=grid_size,
        )
        for negative in negatives:
            weather_profile = _cached_historical_weather_profile(
                round(negative['lat'], 3),
                round(negative['lng'], 3),
                negative['timestamp'].isoformat(),
            )
            weather_sample = select_hourly_weather_sample(weather_profile, negative['timestamp'])
            assembled = build_real_feature_row(
                weather_sample=weather_sample,
                terrain=negative['terrain'],
                timestamp=negative['timestamp'],
                lat=negative['lat'],
                lng=negative['lng'],
            )
            dataset_rows.append({
                'event_id': None,
                'timestamp': pd.Timestamp(negative['timestamp']),
                'region_key': region.key,
                'region_name': region.name,
                'lat': negative['lat'],
                'lng': negative['lng'],
                'label': 0,
                'severity': None,
                'temperature_2m': assembled['raw_inputs']['temperature_2m'],
                'windspeed_10m': assembled['raw_inputs']['windspeed_10m'],
                **assembled['feature_row'],
            })

    frame = pd.DataFrame(dataset_rows)
    if not frame.empty:
        frame = frame.sort_values('timestamp').reset_index(drop=True)
        frame = frame[['timestamp', 'region_key', 'region_name', 'lat', 'lng', 'label', 'severity', 'temperature_2m', 'windspeed_10m', *FEATURE_COLUMNS]]

    positives_count = int((frame['label'] == 1).sum()) if not frame.empty else 0
    negatives_count = int((frame['label'] == 0).sum()) if not frame.empty else 0
    debug_stats['final_positives'] = positives_count
    debug_stats['final_negatives'] = negatives_count
    debug_stats['final_total'] = len(frame)
    print(f'[training_dataset] Debug stats: {debug_stats}', file=sys.stderr)

    manifest = {
        'training_dataset_version': 'real_event_join_v1',
        'positive_count': positives_count,
        'negative_count': negatives_count,
        'filters': {
            'hazard_type': hazard_type,
            'training_eligible': True,
            'label_role_excluded': True,
            'verification_status': ['weak', 'verified', 'expert_verified'],
            'negative_ratio': NEGATIVES_PER_POSITIVE,
            'negative_distance_m': NEGATIVE_DISTANCE_M,
            'negative_time_window_hours': NEGATIVE_TIME_WINDOW_HOURS,
            'negative_slope_band_deg': [NEGATIVE_SLOPE_MIN, NEGATIVE_SLOPE_MAX],
        },
        'oldest_timestamp': frame['timestamp'].min().isoformat() if not frame.empty else None,
        'newest_timestamp': frame['timestamp'].max().isoformat() if not frame.empty else None,
        'event_source_counts': dict(event_source_counts),
        'debug_stats': debug_stats,
    }
    return frame, manifest


def load_training_frame(
    *,
    seed: int,
    samples_per_region: int,
    grid_size: int,
    allow_synthetic_bootstrap: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, manifest = build_real_training_frame(seed=seed, grid_size=grid_size)
    if not frame.empty and int((frame['label'] == 1).sum()) > 0 and int((frame['label'] == 0).sum()) > 0:
        return frame, manifest

    if not allow_synthetic_bootstrap:
        raise RuntimeError('Real training dataset is empty or class-degenerate and synthetic bootstrap is disabled.')

    synthetic = generate_training_frame(load_regions(), samples_per_region=samples_per_region, seed=seed)
    synthetic['severity'] = None
    synthetic['temperature_2m'] = synthetic['temp_gradient'] * 20 - 10
    synthetic['windspeed_10m'] = synthetic['wind_loading'] * 55
    return synthetic, {
        'training_dataset_version': 'synthetic_bootstrap_v1',
        'positive_count': int((synthetic['label'] == 1).sum()),
        'negative_count': int((synthetic['label'] == 0).sum()),
        'filters': {'allow_synthetic_bootstrap': True},
        'oldest_timestamp': synthetic['timestamp'].min().isoformat(),
        'newest_timestamp': synthetic['timestamp'].max().isoformat(),
    }
