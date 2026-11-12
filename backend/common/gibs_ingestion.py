"""NASA GIBS raster ingestion for snow-cover overlay and nudging.

Fetches MODIS snow-cover tiles from NASA GIBS WMTS/TMS endpoint.
Uses the open TMS tile API (no auth required) to download tiles
for a given bbox and date, then computes a snow-cover fraction
per grid cell for use as a feature nudge in the ML pipeline.

GIBS layers used:
  - MODIS_Terra_Snow_Cover (daily, 500m at native zoom)
  - MODIS_Aqua_Snow_Cover (daily, 500m, fallback)

Environment variables:
  GIBS_ENABLED: Set to '1' to enable (default: '0')
  GIBS_TILE_SIZE: Tile size in pixels (default: 256)
  GIBS_ZOOM_LEVEL: TMS zoom level (default: 8, ~1.5km at equator)
"""
from __future__ import annotations

import io
import math
import os
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Any

GIBS_BASE_URL = 'https://gibs.earthdata.nasa.gov/wmts/epsg4326/best'
GIBS_SNOW_LAYER = 'MODIS_Terra_Snow_Cover'
GIBS_TILE_MATRIX_SET = '250m'
GIBS_TILE_FORMAT = 'image/png'
GIBS_ENABLED = os.getenv('GIBS_ENABLED', '0').strip().lower() in ('1', 'true', 'yes')
GIBS_BASELINE_ENABLED = os.getenv('GIBS_BASELINE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
GIBS_ZOOM_LEVEL = int(os.getenv('GIBS_ZOOM_LEVEL', '8'))
GIBS_TIMEOUT = int(os.getenv('GIBS_TIMEOUT', '15'))
_GIBS_TILE_CACHE: dict[str, 'GibsSnowCoverResult'] = {}


@dataclass(frozen=True)
class GibsSnowCoverResult:
    """Result of GIBS snow-cover tile fetch."""
    lat: float
    lng: float
    date: str
    snow_cover_fraction: float
    tile_url: str
    source: str = 'gibs_modis_terra_snow_cover'


def _coerce_target_date(target_date: date | datetime | str | None = None) -> date:
    """Normalize workflow dates to a UTC calendar date."""
    if target_date is None:
        return datetime.now(timezone.utc).date()
    if isinstance(target_date, datetime):
        return target_date.astimezone(timezone.utc).date() if target_date.tzinfo else target_date.date()
    if isinstance(target_date, date):
        return target_date
    if isinstance(target_date, str) and target_date.strip():
        raw = target_date.strip()
        try:
            return date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError('target_date must be YYYY-MM-DD or ISO-8601') from exc
    raise ValueError('target_date must be a date, datetime, ISO string, or None')


def _lat_lng_to_tile(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lng to TMS tile coordinates (EPSG:4326).

    GIBS uses EPSG:4326 tile matrix set where:
      x = (lng + 180) / 360 * 2^zoom
      y = (90 - lat) / 180 * 2^zoom
    """
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((90.0 - lat) / 180.0 * n)
    return x, y


def _build_tile_url(
    lat: float,
    lng: float,
    target_date: date | datetime | str,
    zoom: int = GIBS_ZOOM_LEVEL,
) -> str:
    """Build GIBS WMTS tile URL for a given coordinate and date."""
    x, y = _lat_lng_to_tile(lat, lng, zoom)
    date_str = _coerce_target_date(target_date).isoformat()
    return (
        f'{GIBS_BASE_URL}/{GIBS_SNOW_LAYER}/default/{date_str}/'
        f'{GIBS_TILE_MATRIX_SET}/{zoom}/{y}/{x}.{GIBS_TILE_FORMAT.split("/")[1]}'
    )


def _compute_snow_fraction_from_tile(tile_data: bytes) -> float:
    """Compute snow-cover fraction from a GIBS snow-cover PNG tile.

    GIBS MODIS snow cover uses a color ramp:
      - White (255,255,255) = snow
      - Green (0,200,0) = land (no snow)
      - Blue (0,0,255) = water
      - Transparent = no data

    We count pixels that are predominantly white/bright as snow.
    """
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(io.BytesIO(tile_data)).convert('RGBA')
        arr = np.array(img)

        if arr.size == 0:
            return 0.0

        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3]

        valid_mask = alpha > 128
        if not valid_mask.any():
            return 0.0

        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        snow_mask = (r > 200) & (g > 200) & (b > 200) & valid_mask
        snow_fraction = float(snow_mask.sum()) / float(valid_mask.sum())
        return round(snow_fraction, 4)

    except ImportError:
        return 0.0
    except Exception:
        return 0.0


def fetch_gibs_snow_cover(
    lat: float,
    lng: float,
    target_date: date | datetime | str | None = None,
) -> GibsSnowCoverResult | None:
    """Fetch snow-cover fraction for a single coordinate from NASA GIBS.

    Args:
        lat: Cell latitude
        lng: Cell longitude
        target_date: Date for snow cover (defaults to today UTC)

    Returns:
        GibsSnowCoverResult or None on failure
    """
    if not GIBS_ENABLED:
        return None

    target_date = _coerce_target_date(target_date)

    tile_url = _build_tile_url(lat, lng, target_date)
    cached = _GIBS_TILE_CACHE.get(tile_url)
    if cached is not None:
        return replace(cached, lat=lat, lng=lng)

    try:
        req = urllib.request.Request(tile_url, headers={'User-Agent': 'AvalancheInsightHub/1.0'})
        with urllib.request.urlopen(req, timeout=GIBS_TIMEOUT) as response:
            tile_data = response.read()

        snow_fraction = _compute_snow_fraction_from_tile(tile_data)

        result = GibsSnowCoverResult(
            lat=lat,
            lng=lng,
            date=target_date.isoformat(),
            snow_cover_fraction=snow_fraction,
            tile_url=tile_url,
        )
        _GIBS_TILE_CACHE[tile_url] = result
        return result

    except Exception:
        return None


def fetch_gibs_snow_cover_batch(
    cell_coords: list[tuple[float, float]],
    target_date: date | datetime | str | None = None,
) -> list[GibsSnowCoverResult | None]:
    """Fetch snow-cover for multiple grid cells from NASA GIBS.

    Args:
        cell_coords: List of (lat, lng) tuples
        target_date: Date for snow cover

    Returns:
        List of GibsSnowCoverResult or None (same order as input)
    """
    if not GIBS_ENABLED:
        return [None] * len(cell_coords)

    target_date = _coerce_target_date(target_date)
    tile_cache: dict[str, GibsSnowCoverResult | None] = {}
    results: list[GibsSnowCoverResult | None] = []
    for lat, lng in cell_coords:
        tile_url = _build_tile_url(lat, lng, target_date)
        if tile_url not in tile_cache:
            tile_cache[tile_url] = fetch_gibs_snow_cover(lat, lng, target_date)
        result = tile_cache[tile_url]
        # The raster value is tile-level, but retain the requested coordinate
        # in the result so downstream cell lineage remains unambiguous.
        results.append(replace(result, lat=lat, lng=lng) if result is not None else None)
    return results


def emit_baseline_compatible_rows(
    results: list[GibsSnowCoverResult | None],
    *,
    region_key: str,
    cell_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert GIBS results into verification-spine baseline-compatible rows.

    Each row has: region_key, cell_id, sensor, snow_cover_fraction,
    source, date, freshness_hours.

    Returns empty list when GIBS_BASELINE_ENABLED is false.
    """
    if not GIBS_BASELINE_ENABLED:
        return []

    rows: list[dict[str, Any]] = []
    for idx, result in enumerate(results):
        if result is None:
            continue
        cell_id = cell_ids[idx] if cell_ids and idx < len(cell_ids) else f'cell_{idx}'
        rows.append({
            'region_key': region_key,
            'cell_id': cell_id,
            'sensor': 'gibs_modis',
            'snow_cover_fraction': result.snow_cover_fraction,
            'source': result.source,
            'date': result.date,
            'freshness_hours': 24.0,  # MODIS daily
            'tile_url': result.tile_url,
        })
    return rows
