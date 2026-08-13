"""Deterministic candidate geometry extraction for the Pir Panjal POC.

The repository-bound terrain asset is a compressed one-arc-second SRTM HGT
tile.  Rasterio does not read the compressed fixture directly, so this module
implements the small, explicit HGT read needed by the candidate contract.
It is intentionally limited to WGS84 SRTM tiles and Horn's 3x3 terrain
derivative.  The result is candidate geometry, not an approved survey or a
claim of site-specific validation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any


_HGT_SIDE = 3601
_HGT_SAMPLES = _HGT_SIDE * _HGT_SIDE
_HGT_BYTES = _HGT_SAMPLES * 2
_HGT_NODATA = -32768
_TILE_RE = re.compile(r"^([NS])(\d{2})([EW])(\d{3})\.hgt(?:\.gz)?$", re.IGNORECASE)


class PirPanjalGeometryError(ValueError):
    """Raised when candidate terrain cannot be derived without guessing."""


def _sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PirPanjalGeometryError(f"DEM tile is not a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tile_bounds(path: Path) -> tuple[float, float]:
    match = _TILE_RE.fullmatch(path.name)
    if match is None:
        raise PirPanjalGeometryError(
            f"DEM tile must use an SRTM HGT filename, got {path.name!r}"
        )
    lat_sign, lat_value, lon_sign, lon_value = match.groups()
    latitude = float(lat_value) * (1.0 if lat_sign.upper() == "N" else -1.0)
    longitude = float(lon_value) * (1.0 if lon_sign.upper() == "E" else -1.0)
    return latitude, longitude


def _read_hgt(path: Path) -> list[int]:
    opener = gzip.open if path.suffix.lower() == ".gz" else Path.open
    with opener(path, "rb") as stream:
        raw = stream.read()
    if len(raw) != _HGT_BYTES:
        raise PirPanjalGeometryError(
            f"DEM tile has {len(raw)} bytes; expected {_HGT_BYTES} for 1-arc-second HGT"
        )
    return list(struct.unpack(f">{_HGT_SAMPLES}h", raw))


def _meters_per_degree(latitude: float) -> tuple[float, float]:
    """Return deterministic WGS84 metres per degree at the target latitude."""

    radians = math.radians(latitude)
    latitude_m = (
        111132.92
        - 559.82 * math.cos(2 * radians)
        + 1.175 * math.cos(4 * radians)
        - 0.0023 * math.cos(6 * radians)
    )
    longitude_m = (
        111412.84 * math.cos(radians)
        - 93.5 * math.cos(3 * radians)
        + 0.118 * math.cos(5 * radians)
    )
    return latitude_m, longitude_m


def derive_hgt_terrain(*, dem_path: Path, latitude: float, longitude: float) -> dict[str, Any]:
    """Derive one deterministic HGT cell and Horn 3x3 terrain geometry."""

    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise PirPanjalGeometryError("target coordinates must be finite")
    tile_latitude, tile_longitude = _tile_bounds(dem_path)
    if not tile_latitude <= latitude <= tile_latitude + 1.0:
        raise PirPanjalGeometryError("latitude falls outside the DEM tile")
    if not tile_longitude <= longitude <= tile_longitude + 1.0:
        raise PirPanjalGeometryError("longitude falls outside the DEM tile")

    values = _read_hgt(dem_path)
    row = int(round((tile_latitude + 1.0 - latitude) * 3600.0))
    column = int(round((longitude - tile_longitude) * 3600.0))
    if not 1 <= row < _HGT_SIDE - 1 or not 1 <= column < _HGT_SIDE - 1:
        raise PirPanjalGeometryError("target is too close to the DEM tile boundary for a 3x3 window")

    window = [
        [values[(row + row_offset) * _HGT_SIDE + column + column_offset]
         for column_offset in (-1, 0, 1)]
        for row_offset in (-1, 0, 1)
    ]
    if any(value == _HGT_NODATA for line in window for value in line):
        raise PirPanjalGeometryError("DEM 3x3 window contains nodata")

    latitude_m, longitude_m = _meters_per_degree(latitude)
    pixel_y_m = latitude_m / 3600.0
    pixel_x_m = longitude_m / 3600.0
    dzdx = (
        (window[0][2] + 2 * window[1][2] + window[2][2])
        - (window[0][0] + 2 * window[1][0] + window[2][0])
    ) / (8.0 * pixel_x_m)
    dzdy = (
        (window[2][0] + 2 * window[2][1] + window[2][2])
        - (window[0][0] + 2 * window[0][1] + window[0][2])
    ) / (8.0 * pixel_y_m)
    slope_deg = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    aspect_deg = math.degrees(math.atan2(dzdy, -dzdx))
    if aspect_deg < 0.0:
        aspect_deg += 360.0

    record: dict[str, Any] = {
        "schema_version": "pir_panjal_geometry_v1",
        "method": "srtm_hgt_horn_3x3_v1",
        "dem_path": dem_path.as_posix(),
        "dem_sha256": _sha256_file(dem_path),
        "latitude": round(float(latitude), 9),
        "longitude": round(float(longitude), 9),
        "sample_row": row,
        "sample_column": column,
        "window_m": window,
        "elevation_m": float(window[1][1]),
        "slope_deg": round(slope_deg, 6),
        "aspect_deg": round(aspect_deg, 6),
        "aspect_label": _aspect_label(aspect_deg),
        "pixel_spacing_m": {
            "north_south": round(pixel_y_m, 6),
            "east_west": round(pixel_x_m, 6),
        },
        "quality_status": "derived_candidate_geometry",
    }
    record["geometry_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return record


def _aspect_label(aspect_deg: float) -> str:
    labels = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    index = int(((aspect_deg + 22.5) % 360.0) // 45.0)
    return labels[index]
