from __future__ import annotations

from dataclasses import dataclass
from math import exp, sin, cos, ceil
from typing import Iterable

import numpy as np
import pandas as pd

from backend.common.regions import Region

import os as _os

SNOW_DEPTH_FEATURES_ENABLED = _os.getenv('SNOW_DEPTH_FEATURES_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

_BASE_FEATURE_COLUMNS = [
    'snowfall_24h',
    'precipitation_24h',
    'wind_loading',
    'wind_directional_loading',
    'slope',
    'elevation',
    'temp_gradient',
    'freezing_level_proxy',
    'snowpack',
    'ram_hardness',
    'shear_strength',
    'settlement_rate',
    'aspect_loading',
    'terrain_roughness',
    'curvature_proxy',
    'northness',
    'eastness',
    'freezing_level_margin',
    'load_to_shear_ratio',
    'settlement_deficit',
    'rain_on_snow_signal',
    'wet_activation_signal',
    'elevation_precip_bias',
    'weak_layer_depth',
    'grain_type_faceted',
    'grain_type_depth_hoar',
    'stability_index',
    'temp_gradient_profile',
    'liquid_water_content',
]

_SNOW_DEPTH_FEATURE_COLUMNS = [
    'snow_depth_fused',
    'snow_depth_uncertainty',
    'sensor_consensus',
]

FEATURE_COLUMNS = (
    _BASE_FEATURE_COLUMNS + _SNOW_DEPTH_FEATURE_COLUMNS
    if SNOW_DEPTH_FEATURES_ENABLED
    else _BASE_FEATURE_COLUMNS
)


@dataclass(frozen=True)
class SampleContext:
    region_key: str
    region_name: str
    timestamp: pd.Timestamp
    lat: float
    lng: float
    row: int | None = None
    col: int | None = None


def _sigmoid(value: float) -> float:
    return 1 / (1 + exp(-value))


def build_feature_row(context: SampleContext, rng: np.random.Generator) -> dict[str, float]:
    season = (context.timestamp.dayofyear / 365.0) * 2 * np.pi
    lat_band = abs(context.lat) * 0.02
    lng_band = abs(context.lng) * 0.01
    slope = np.clip(18 + lat_band * 18 + sin(context.lng * 0.11) * 6 + rng.normal(0, 2), 0, 60)
    elevation = np.clip(1200 + lat_band * 800 + cos(context.lat * 0.09) * 180 + rng.normal(0, 80), 0, 5000)
    snowfall_24h = np.clip(4 + 2.5 * sin(season + context.lat * 0.1) + rng.normal(0, 1.5), 0, 40)
    precipitation_24h = np.clip(snowfall_24h + rng.normal(0, 1.1), 0, 45)
    wind_loading = np.clip(10 + 8 * cos(season + context.lng * 0.08) + rng.normal(0, 3), 0, 55)
    wind_directional_loading = np.clip(0.3 + abs(sin(context.lng * 0.03)) * 0.6 + rng.normal(0, 0.05), 0, 1)
    temp_gradient = np.clip(0.25 + 0.15 * sin(season * 1.5) + rng.normal(0, 0.03), 0, 1)
    freezing_level_proxy = np.clip(0.5 + (context.lat / 90) * 0.2 + rng.normal(0, 0.04), 0, 1)
    snowpack = np.clip(15 + snowfall_24h * 1.1 - max(0, temp_gradient - 0.2) * 18 + rng.normal(0, 2), 0, 60)
    ram_hardness = np.clip(0.4 + snowfall_24h / 60 + rng.normal(0, 0.05), 0, 1)
    shear_strength = np.clip(0.35 + (elevation / 5000) * 0.25 + rng.normal(0, 0.05), 0, 1)
    settlement_rate = np.clip(0.2 + max(0, 0.7 - temp_gradient) * 0.4 + rng.normal(0, 0.04), 0, 1)
    aspect_loading = np.clip(0.25 + abs(sin((context.lng + context.lat) * np.pi / 180)) * 0.5 + rng.normal(0, 0.03), 0, 1)
    terrain_roughness = np.clip(0.2 + abs(sin(context.lat * 0.17) * cos(context.lng * 0.13)) * 0.7 + rng.normal(0, 0.04), 0, 1)
    curvature_proxy = np.clip(0.15 + abs(cos(context.lat * 0.09)) * 0.5 + rng.normal(0, 0.03), 0, 1)
    northness = np.clip((1 + cos(context.lat * np.pi / 180)) / 2, 0, 1)
    eastness = np.clip((1 + sin(context.lng * np.pi / 180)) / 2, 0, 1)
    freezing_level_margin = np.clip(0.5 + (elevation - 2500) / 2500 + rng.normal(0, 0.05), 0, 1)
    elevation_precip_bias = np.clip(0.2 + elevation * 0.45 + rng.normal(0, 0.05), 0, 1)
    rain_on_snow_signal = np.clip(
        max(0.0, precipitation_24h / 45.0 - 0.1) * max(0.0, freezing_level_proxy - 0.35) + rng.normal(0, 0.03),
        0,
        1,
    )
    wet_activation_signal = np.clip(
        max(rain_on_snow_signal, max(0.0, 0.7 - freezing_level_margin) * max(0.0, snowpack / 60.0))
        + rng.normal(0, 0.03),
        0,
        1,
    )
    settlement_deficit = np.clip(1.0 - settlement_rate + rng.normal(0, 0.02), 0, 1)
    loading_signal = np.clip(
        snowfall_24h / 40.0 + wind_loading / 55.0 + precipitation_24h / 45.0 + elevation_precip_bias * 0.3,
        0,
        3,
    )
    load_to_shear_ratio = np.clip(loading_signal / max(shear_strength + 0.05, 0.1) / 3.0, 0, 1)

    return {
        'snowfall_24h': float(snowfall_24h / 40),
        'precipitation_24h': float(precipitation_24h / 45),
        'wind_loading': float(wind_loading / 55),
        'wind_directional_loading': float(wind_directional_loading),
        'slope': float(slope / 60),
        'elevation': float(elevation / 5000),
        'temp_gradient': float(temp_gradient),
        'freezing_level_proxy': float(freezing_level_proxy),
        'snowpack': float(snowpack / 60),
        'ram_hardness': float(ram_hardness),
        'shear_strength': float(shear_strength),
        'settlement_rate': float(settlement_rate),
        'aspect_loading': float(aspect_loading),
        'terrain_roughness': float(terrain_roughness),
        'curvature_proxy': float(curvature_proxy),
        'northness': float(northness),
        'eastness': float(eastness),
        'freezing_level_margin': float(freezing_level_margin),
        'load_to_shear_ratio': float(load_to_shear_ratio),
        'settlement_deficit': float(settlement_deficit),
        'rain_on_snow_signal': float(rain_on_snow_signal),
        'wet_activation_signal': float(wet_activation_signal),
        'elevation_precip_bias': float(elevation_precip_bias),
    }


def compute_label(features: dict[str, float], rng: np.random.Generator) -> int:
    score = (
        1.8 * features['snowfall_24h']
        + 0.7 * features['precipitation_24h']
        + 1.2 * features['wind_loading']
        + 0.6 * features['wind_directional_loading']
        + 1.5 * features['slope']
        + 0.7 * features['snowpack']
        + 0.8 * features['aspect_loading']
        + 0.4 * features['terrain_roughness']
        + 0.35 * features['curvature_proxy']
        - 1.1 * features['shear_strength']
        - 0.7 * features['ram_hardness']
        + 0.35 * features['temp_gradient']
        + 0.2 * features['freezing_level_proxy']
        + 0.5 * features['load_to_shear_ratio']
        + 0.35 * features['wet_activation_signal']
        + 0.2 * features['rain_on_snow_signal']
        + 0.15 * features['settlement_deficit']
        + rng.normal(0, 0.25)
    )
    return int(_sigmoid(score - 2.7) > 0.5)


def generate_training_frame(regions: Iterable[Region], samples_per_region: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    region_list = list(regions)
    timestamps = pd.date_range(
        '2025-01-01',
        periods=max(1, samples_per_region * len(region_list)),
        freq='12h',
        tz='UTC',
    )
    rows: list[dict[str, object]] = []

    for region_index, region in enumerate(region_list):
        lat_min, lng_min, lat_max, lng_max = region.bbox
        for sample_index in range(samples_per_region):
            timestamp = timestamps[(region_index * samples_per_region + sample_index) % len(timestamps)]
            lat = float(rng.uniform(lat_min, lat_max))
            lng = float(rng.uniform(lng_min, lng_max))
            context = SampleContext(
                region_key=region.key,
                region_name=region.name,
                timestamp=timestamp,
                lat=lat,
                lng=lng,
            )
            features = build_feature_row(context, rng)
            label = compute_label(features, rng)
            row = {
                'timestamp': timestamp,
                'region_key': region.key,
                'region_name': region.name,
                'lat': lat,
                'lng': lng,
                'label': label,
                **features,
            }
            rows.append(row)

    frame = pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)
    return frame


def build_region_grid(region: Region, grid_size: int = 20) -> list[dict[str, float]]:
    lat_min, lng_min, lat_max, lng_max = region.bbox
    lat_step = (lat_max - lat_min) / grid_size
    lng_step = (lng_max - lng_min) / grid_size
    cells: list[dict[str, float]] = []
    for row in range(grid_size):
        for col in range(grid_size):
            lat = lat_min + row * lat_step
            lng = lng_min + col * lng_step
            cells.append({
                'row': row,
                'col': col,
                'lat': lat,
                'lng': lng,
                'lat_end': lat + lat_step,
                'lng_end': lng + lng_step,
                'pixel_id': f'{region.key}_{row}_{col}',
                'crs': 'EPSG:4326',
                'grid_mode': 'degree',
                'cell_size_degrees_lat': lat_step,
                'cell_size_degrees_lng': lng_step,
            })
    import hashlib
    import json as _json
    manifest_for_hash = {
        'region_key': region.key,
        'mode': 'degree',
        'crs': 'EPSG:4326',
        'bounds': list(region.bbox),
        'grid_rows': grid_size,
        'grid_cols': grid_size,
        'cell_size_degrees_lat': lat_step,
        'cell_size_degrees_lng': lng_step,
        'coords': sorted(
            [{'lat': round(c['lat'], 10), 'lng': round(c['lng'], 10)} for c in cells],
            key=lambda p: (p['lat'], p['lng']),
        ),
    }
    manifest_hash = hashlib.sha256(
        _json.dumps(manifest_for_hash, sort_keys=True).encode('utf-8')
    ).hexdigest()
    for cell in cells:
        cell['grid_manifest_hash'] = manifest_hash
    return cells


def _utm_epsg_from_bbox(bbox: tuple[float, float, float, float]) -> int:
    """Compute UTM EPSG code from a bounding box."""
    lat_min, lng_min, lat_max, lng_max = bbox
    lat_center = (lat_min + lat_max) / 2.0
    lng_center = (lng_min + lng_max) / 2.0
    utm_zone = int((lng_center + 180.0) / 6.0) + 1
    hemisphere = 'north' if lat_center >= 0 else 'south'
    return 32600 + utm_zone if hemisphere == 'north' else 32700 + utm_zone


def build_region_grid_projected(
    region: Region,
    cell_size_m: float = 500.0,
    strict: bool = False,
) -> list[dict[str, float]]:
    """Build a UTM-projected grid with fixed cell size in meters.

    Projects the region bbox to the appropriate UTM zone, creates a
    regular grid at the specified cell size (default 500m), and
    converts cell centers back to lat/lng.

    Args:
        region: Region with bbox
        cell_size_m: Grid cell size in meters (default 500m)
        strict: When True, raises RuntimeError if pyproj is unavailable
                instead of silently falling back to degree grid.

    Returns:
        List of cell dicts with row, col, lat, lng, lat_end, lng_end,
        plus projected x, y, cell_size_m, grid_rows/grid_cols,
        pixel_id, and grid_manifest_hash.

    Raises:
        RuntimeError: If strict=True and pyproj is not available.
    """
    try:
        from pyproj import Transformer, CRS
    except ImportError:
        if strict:
            raise RuntimeError(
                "Projected grid requested in strict mode but pyproj is not available. "
                "Install pyproj or use strict=False for fallback to degree grid."
            )
        return build_region_grid(region, grid_size=20)

    lat_min, lng_min, lat_max, lng_max = region.bbox
    lat_center = (lat_min + lat_max) / 2.0
    lng_center = (lng_min + lng_max) / 2.0

    epsg_code = _utm_epsg_from_bbox(region.bbox)
    utm_crs = CRS.from_epsg(epsg_code)
    wgs84_crs = CRS.from_epsg(4326)

    to_utm = Transformer.from_crs(wgs84_crs, utm_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(utm_crs, wgs84_crs, always_xy=True)

    x_min, y_min = to_utm.transform(lng_min, lat_min)
    x_max, y_max = to_utm.transform(lng_max, lat_max)

    grid_cols = max(1, int(ceil((x_max - x_min) / cell_size_m)))
    grid_rows = max(1, int(ceil((y_max - y_min) / cell_size_m)))

    cells: list[dict[str, float]] = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            x = x_min + col * cell_size_m + cell_size_m / 2.0
            y = y_min + row * cell_size_m + cell_size_m / 2.0
            lng, lat = to_wgs84.transform(x, y)

            x_end = x_min + (col + 1) * cell_size_m
            y_end = y_min + (row + 1) * cell_size_m
            lng_end, lat_end = to_wgs84.transform(x_end, y_end)

            cells.append({
                'row': row,
                'col': col,
                'lat': lat,
                'lng': lng,
                'lat_end': lat_end,
                'lng_end': lng_end,
                'x_m': x,
                'y_m': y,
                'cell_size_m': cell_size_m,
                'grid_rows': grid_rows,
                'grid_cols': grid_cols,
                'pixel_id': f'{region.key}_{row}_{col}',
                'crs': f'EPSG:{epsg_code}',
                'grid_mode': 'projected',
            })

    # Compute deterministic grid manifest hash from complete grid metadata
    import hashlib
    import json as _json
    manifest_for_hash = {
        'region_key': region.key,
        'mode': 'projected',
        'crs': f'EPSG:{_utm_epsg_from_bbox(region.bbox)}',
        'cell_size_m': cell_size_m,
        'bounds': list(region.bbox),
        'grid_rows': grid_rows,
        'grid_cols': grid_cols,
        'coords': sorted(
            [{'lat': round(c['lat'], 10), 'lng': round(c['lng'], 10)} for c in cells],
            key=lambda p: (p['lat'], p['lng']),
        ),
    }
    manifest_hash = hashlib.sha256(
        _json.dumps(manifest_for_hash, sort_keys=True).encode('utf-8')
    ).hexdigest()
    for cell in cells:
        cell['grid_manifest_hash'] = manifest_hash

    return cells


def _build_zone_aware_feature_row(
    context: SampleContext,
    rng: np.random.Generator,
    *,
    elevation_min: float = 1200.0,
    elevation_max: float = 5000.0,
    lapse_rate_c_per_m: float = -0.0065,
) -> dict[str, float]:
    """Build a feature row with zone-specific elevation and temperature calibration."""
    season = (context.timestamp.dayofyear / 365.0) * 2 * np.pi
    lat_band = abs(context.lat) * 0.02
    lng_band = abs(context.lng) * 0.01
    slope = np.clip(18 + lat_band * 18 + sin(context.lng * 0.11) * 6 + rng.normal(0, 2), 0, 60)
    elevation_range = elevation_max - elevation_min
    elevation = np.clip(
        elevation_min + elevation_range * (0.3 + 0.4 * abs(sin(context.lat * 0.09)) + rng.normal(0, 0.1)),
        elevation_min,
        elevation_max,
    )
    snowfall_24h = np.clip(4 + 2.5 * sin(season + context.lat * 0.1) + rng.normal(0, 1.5), 0, 40)
    precipitation_24h = np.clip(snowfall_24h + rng.normal(0, 1.1), 0, 45)
    wind_loading = np.clip(10 + 8 * cos(season + context.lng * 0.08) + rng.normal(0, 3), 0, 55)
    wind_directional_loading = np.clip(0.3 + abs(sin(context.lng * 0.03)) * 0.6 + rng.normal(0, 0.05), 0, 1)
    # Zone-specific temperature gradient: higher elevation → steeper gradient
    base_temp_gradient = 0.25 + 0.15 * sin(season * 1.5) + rng.normal(0, 0.03)
    elevation_factor = (elevation - elevation_min) / max(elevation_range, 1.0)
    temp_gradient = np.clip(base_temp_gradient + elevation_factor * abs(lapse_rate_c_per_m) * 0.5, 0, 1)
    freezing_level_proxy = np.clip(0.5 + (context.lat / 90) * 0.2 + rng.normal(0, 0.04), 0, 1)
    snowpack = np.clip(15 + snowfall_24h * 1.1 - max(0, temp_gradient - 0.2) * 18 + rng.normal(0, 2), 0, 60)
    ram_hardness = np.clip(0.4 + snowfall_24h / 60 + rng.normal(0, 0.05), 0, 1)
    shear_strength = np.clip(0.35 + (elevation / elevation_max) * 0.25 + rng.normal(0, 0.05), 0, 1)
    settlement_rate = np.clip(0.2 + max(0, 0.7 - temp_gradient) * 0.4 + rng.normal(0, 0.04), 0, 1)
    aspect_loading = np.clip(0.25 + abs(sin((context.lng + context.lat) * np.pi / 180)) * 0.5 + rng.normal(0, 0.03), 0, 1)
    terrain_roughness = np.clip(0.2 + abs(sin(context.lat * 0.17) * cos(context.lng * 0.13)) * 0.7 + rng.normal(0, 0.04), 0, 1)
    curvature_proxy = np.clip(0.15 + abs(cos(context.lat * 0.09)) * 0.5 + rng.normal(0, 0.03), 0, 1)
    northness = np.clip((1 + cos(context.lat * np.pi / 180)) / 2, 0, 1)
    eastness = np.clip((1 + sin(context.lng * np.pi / 180)) / 2, 0, 1)
    freezing_level_margin = np.clip(0.5 + (elevation - 2500) / 2500 + rng.normal(0, 0.05), 0, 1)
    elevation_precip_bias = np.clip(0.2 + elevation * 0.45 + rng.normal(0, 0.05), 0, 1)
    rain_on_snow_signal = np.clip(
        max(0.0, precipitation_24h / 45.0 - 0.1) * max(0.0, freezing_level_proxy - 0.35) + rng.normal(0, 0.03),
        0,
        1,
    )
    wet_activation_signal = np.clip(
        max(rain_on_snow_signal, max(0.0, 0.7 - freezing_level_margin) * max(0.0, snowpack / 60.0))
        + rng.normal(0, 0.03),
        0,
        1,
    )
    settlement_deficit = np.clip(1.0 - settlement_rate + rng.normal(0, 0.02), 0, 1)
    loading_signal = np.clip(
        snowfall_24h / 40.0 + wind_loading / 55.0 + precipitation_24h / 45.0 + elevation_precip_bias * 0.3,
        0,
        3,
    )
    load_to_shear_ratio = np.clip(loading_signal / max(shear_strength + 0.05, 0.1) / 3.0, 0, 1)

    return {
        'snowfall_24h': float(snowfall_24h / 40),
        'precipitation_24h': float(precipitation_24h / 45),
        'wind_loading': float(wind_loading / 55),
        'wind_directional_loading': float(wind_directional_loading),
        'slope': float(slope / 60),
        'elevation': float(elevation / 5000),
        'temp_gradient': float(temp_gradient),
        'freezing_level_proxy': float(freezing_level_proxy),
        'snowpack': float(snowpack / 60),
        'ram_hardness': float(ram_hardness),
        'shear_strength': float(shear_strength),
        'settlement_rate': float(settlement_rate),
        'aspect_loading': float(aspect_loading),
        'terrain_roughness': float(terrain_roughness),
        'curvature_proxy': float(curvature_proxy),
        'northness': float(northness),
        'eastness': float(eastness),
        'freezing_level_margin': float(freezing_level_margin),
        'load_to_shear_ratio': float(load_to_shear_ratio),
        'settlement_deficit': float(settlement_deficit),
        'rain_on_snow_signal': float(rain_on_snow_signal),
        'wet_activation_signal': float(wet_activation_signal),
        'elevation_precip_bias': float(elevation_precip_bias),
    }


def generate_cold_start_synthetic_frame(
    regions: list[Region],
    samples_per_region: int,
    seed: int,
    augmentation_multiplier: int = 3,
) -> pd.DataFrame:
    """Generate zone-calibrated synthetic samples for cold-start training.

    For Himalayan regions (zone_type is not None), uses zone-specific
    elevation ranges, lapse rates, and season start dates from F17 config.
    Non-Himalayan regions use default elevation ranges (backward compatible).
    """
    rng = np.random.default_rng(seed)
    region_list = list(regions)
    total_samples = samples_per_region * augmentation_multiplier
    timestamps = pd.date_range(
        '2025-01-01',
        periods=max(1, total_samples * len(region_list)),
        freq='12h',
        tz='UTC',
    )
    rows: list[dict[str, object]] = []

    for region_index, region in enumerate(region_list):
        lat_min, lng_min, lat_max, lng_max = region.bbox
        is_himalayan = getattr(region, 'zone_type', None) is not None
        elevation_min = float(getattr(region, 'elevation_min', 1200) or 1200)
        elevation_max = float(getattr(region, 'elevation_max', 5000) or 5000)
        lapse_rate = float(getattr(region, 'lapse_rate_c_per_m', -0.0065) or -0.0065)

        for sample_index in range(total_samples):
            timestamp = timestamps[(region_index * total_samples + sample_index) % len(timestamps)]
            lat = float(rng.uniform(lat_min, lat_max))
            lng = float(rng.uniform(lng_min, lng_max))
            context = SampleContext(
                region_key=region.key,
                region_name=region.name,
                timestamp=timestamp,
                lat=lat,
                lng=lng,
            )
            if is_himalayan:
                features = _build_zone_aware_feature_row(
                    context, rng,
                    elevation_min=elevation_min,
                    elevation_max=elevation_max,
                    lapse_rate_c_per_m=lapse_rate,
                )
                row_zone_type = getattr(region, 'zone_type', None)
            else:
                features = build_feature_row(context, rng)
                row_zone_type = None
            label = compute_label(features, rng)
            row = {
                'timestamp': timestamp,
                'region_key': region.key,
                'region_name': region.name,
                'lat': lat,
                'lng': lng,
                'label': label,
                'zone_type': row_zone_type,
                **features,
            }
            rows.append(row)

    frame = pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)
    return frame
