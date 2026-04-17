from __future__ import annotations

from dataclasses import dataclass
from math import exp, sin, cos
from typing import Iterable

import numpy as np
import pandas as pd

from backend.common.regions import Region

FEATURE_COLUMNS = [
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
]


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
        + rng.normal(0, 0.25)
    )
    return int(_sigmoid(score - 2.7) > 0.5)


def generate_training_frame(regions: Iterable[Region], samples_per_region: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    region_list = list(regions)
    timestamps = pd.date_range('2025-01-01', periods=max(1, samples_per_region * len(region_list)), freq='12h')
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
            })
    return cells
