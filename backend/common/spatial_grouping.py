"""Deterministic spatial grouping shared by labels and feature snapshots."""

from __future__ import annotations

import math
from typing import Any


class SpatialGroupingError(ValueError):
    """Raised when a coordinate cannot be assigned to a deterministic group."""


def spatial_feature_join_key(
    latitude: Any,
    longitude: Any,
    region_key: str,
    *,
    bin_km: float = 5.0,
) -> str:
    """Return the stable coarse spatial key used for interval joins.

    The key is a grouping identity, not an assertion that the forcing source
    has 5 km native resolution.  Source resolution and effective information
    scale remain separate manifest fields.
    """

    region = str(region_key or "").strip()
    if not region:
        raise SpatialGroupingError("region_key is required")
    try:
        lat = float(latitude)
        lng = float(longitude)
        width = float(bin_km)
    except (TypeError, ValueError) as exc:
        raise SpatialGroupingError("latitude, longitude, and bin_km must be numeric") from exc
    if not math.isfinite(lat) or not -90.0 <= lat <= 90.0:
        raise SpatialGroupingError("latitude is invalid")
    if not math.isfinite(lng) or not -180.0 <= lng <= 180.0:
        raise SpatialGroupingError("longitude is invalid")
    if not math.isfinite(width) or width <= 0.0:
        raise SpatialGroupingError("bin_km must be positive and finite")

    lat_step = width / 111.0
    bounded_latitude = max(-89.0, min(89.0, lat))
    longitude_step = width / max(1.0, 111.0 * math.cos(math.radians(bounded_latitude)))
    latitude_bin = math.floor(lat / lat_step)
    longitude_bin = math.floor(lng / longitude_step)
    return f"{region}:{latitude_bin}:{longitude_bin}"
