"""GEE server-side regional batching — one regional collection/export instead of per-cell requests.

Earth Engine best practices recommend server-side operations and avoiding
unnecessary client calls. This module builds a single regional ImageCollection
filtered by region + date, then uses reduceRegions over grid cell polygons
to get per-cell stats in one server-side call.

Env flags:
  GEE_REGIONAL_BATCH_ENABLED — use regional batching (default: false → per-cell)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

GEE_REGIONAL_BATCH_ENABLED = os.getenv('GEE_REGIONAL_BATCH_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)


@dataclass(frozen=True)
class RegionalBatchConfig:
    """Configuration for a regional GEE batch operation."""
    region_bbox: tuple[float, float, float, float]  # (min_lng, min_lat, max_lng, max_lat)
    date_start: str
    date_end: str
    collection_id: str
    bands: list[str] = field(default_factory=list)
    scale_m: int = 90
    max_pixels: int = int(1e10)


@dataclass(frozen=True)
class RegionalCellStats:
    """Per-cell statistics from a regional batch operation."""
    cell_id: str
    lat: float
    lng: float
    stats: dict[str, float] = field(default_factory=dict)
    scene_count: int = 0
    eecu_cost: float = 0.0


@dataclass(frozen=True)
class RegionalBatchResult:
    """Complete result of a regional batch operation."""
    region_key: str
    config: RegionalBatchConfig
    cell_stats: list[RegionalCellStats] = field(default_factory=list)
    total_eecu_cost: float = 0.0
    scene_ids: list[str] = field(default_factory=list)
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def to_dict(self) -> dict[str, Any]:
        return {
            'region_key': self.region_key,
            'cell_stats': [
                {
                    'cell_id': cs.cell_id,
                    'lat': cs.lat,
                    'lng': cs.lng,
                    'stats': cs.stats,
                    'scene_count': cs.scene_count,
                    'eecu_cost': cs.eecu_cost,
                }
                for cs in self.cell_stats
            ],
            'total_eecu_cost': self.total_eecu_cost,
            'scene_ids': self.scene_ids,
            'disclaimer': self.disclaimer,
        }


def estimate_eecu_cost(
    collection_size: int,
    scale_m: int = 90,
    band_count: int = 1,
) -> float:
    """Estimate Earth Engine Compute Unit cost for a regional operation.

    Rough heuristic: EECU cost ~ collection_size * pixels_per_scene * band_count * 1e-9.
    pixels_per_scene assumed ~1e8 (typical Sentinel-2 tile at 90m scale).
    """
    if collection_size <= 0:
        return 0.0
    pixels_per_scene = 1e8
    return round(collection_size * pixels_per_scene * band_count * 1e-9, 6)


def build_regional_collection(
    config: RegionalBatchConfig,
    gee_session: Any = None,
) -> Any:
    """Build a single GEE ImageCollection filtered by region + date.

    Returns the GEE ImageCollection object when GEE is available.
    Returns None when GEE_REGIONAL_BATCH_ENABLED is false or GEE not initialized.

    Args:
        config: Regional batch configuration.
        gee_session: Optional authenticated GEE session.

    Returns:
        GEE ImageCollection or None.
    """
    if not GEE_REGIONAL_BATCH_ENABLED:
        return None

    try:
        import ee
        if gee_session is not None:
            ee.Initialize(gee_session)
        elif not ee.data._credentials:
            ee.Initialize()
    except Exception:
        return None

    min_lng, min_lat, max_lng, max_lat = config.region_bbox
    region_geom = ee.Geometry.Rectangle([min_lng, min_lat, max_lng, max_lat])

    collection = (
        ee.ImageCollection(config.collection_id)
        .filterDate(config.date_start, config.date_end)
        .filterBounds(region_geom)
    )

    if config.bands:
        collection = collection.select(config.bands)

    return collection


def export_regional_stats(
    collection: Any,
    grid_cells: list[dict[str, Any]],
    reducer: str = 'mean',
    scale_m: int = 90,
) -> list[RegionalCellStats]:
    """Server-side reduceRegions over grid cell polygons.

    When GEE is available, builds a FeatureCollection of cell polygons and
    runs reduceRegions in one server-side call. When not available, returns
    empty stats (caller should fall back to per-cell).

    Args:
        collection: GEE ImageCollection from build_regional_collection.
        grid_cells: List of cell dicts with cell_id, lat, lng, latEnd, lngEnd.
        reducer: Reducer name ('mean', 'median', 'min', 'max').
        scale_m: Scale in meters for the reduction.

    Returns:
        List of RegionalCellStats per cell.
    """
    if collection is None:
        return []

    try:
        import ee
    except Exception:
        return []

    try:
        image = collection.mean() if reducer == 'mean' else collection.median()

        features = []
        for cell in grid_cells:
            poly = ee.Geometry.Rectangle([
                cell['lng'], cell['lat'],
                cell.get('lngEnd', cell['lng'] + 0.1),
                cell.get('latEnd', cell['lat'] + 0.1),
            ])
            features.append(ee.Feature(poly, {'cell_id': cell['cell_id']}))

        fc = ee.FeatureCollection(features)

        reducer_fn = getattr(image, f'reduceRegions', None)
        if reducer_fn is None:
            return []

        results = reducer_fn(
            collection=fc,
            reducer=getattr(ee.Reducer, reducer)(),
            scale=scale_m,
        )

        info = results.getInfo()
        if not info or 'features' not in info:
            return []

        cell_stats: list[RegionalCellStats] = []
        for feat in info['features']:
            props = feat.get('properties', {})
            cell_id = props.get('cell_id', '')
            stats = {k: float(v) for k, v in props.items() if k != 'cell_id' and isinstance(v, (int, float))}
            cell_stats.append(RegionalCellStats(
                cell_id=cell_id,
                lat=feat.get('geometry', {}).get('coordinates', [[0, 0]])[0][1] if feat.get('geometry') else 0.0,
                lng=feat.get('geometry', {}).get('coordinates', [[0, 0]])[0][0] if feat.get('geometry') else 0.0,
                stats=stats,
            ))

        return cell_stats
    except Exception:
        return []


def run_regional_batch(
    region_key: str,
    config: RegionalBatchConfig,
    grid_cells: list[dict[str, Any]],
    gee_session: Any = None,
) -> RegionalBatchResult:
    """Execute a complete regional batch operation.

    Combines build_regional_collection + export_regional_stats.
    Falls back to empty result when GEE_REGIONAL_BATCH_ENABLED is false.

    Args:
        region_key: Region identifier.
        config: Regional batch configuration.
        grid_cells: List of cell dicts.
        gee_session: Optional GEE session.

    Returns:
        RegionalBatchResult with per-cell stats.
    """
    if not GEE_REGIONAL_BATCH_ENABLED:
        return RegionalBatchResult(
            region_key=region_key,
            config=config,
        )

    collection = build_regional_collection(config, gee_session)
    if collection is None:
        return RegionalBatchResult(
            region_key=region_key,
            config=config,
        )

    cell_stats = export_regional_stats(
        collection,
        grid_cells,
        scale_m=config.scale_m,
    )

    total_cost = sum(cs.eecu_cost for cs in cell_stats)

    return RegionalBatchResult(
        region_key=region_key,
        config=config,
        cell_stats=cell_stats,
        total_eecu_cost=total_cost,
    )
