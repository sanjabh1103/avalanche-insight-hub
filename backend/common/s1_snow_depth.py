"""Sentinel-1 cross-ratio snow depth estimation.

Implements the Lievens et al. cross-ratio method using VH/VV backscatter
to estimate snow depth index. Wet-snow-masked and calibrated against
weather-derived snow depth.

Env flags:
  S1_DEPTH_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

S1_DEPTH_ENABLED = os.getenv('S1_DEPTH_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}


@dataclass
class S1SnowDepthResult:
    """S1 cross-ratio snow depth result for a cell."""

    cell_id: str
    depth_index: float | None = None
    snow_depth_m: float | None = None
    vh_db: float | None = None
    vv_db: float | None = None
    wet_snow_masked: bool = False
    calibration_offset: float = 0.0
    source: str = 'sentinel1_cross_ratio'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'depth_index': self.depth_index,
            'snow_depth_m': self.snow_depth_m,
            'vh_db': self.vh_db,
            'vv_db': self.vv_db,
            'wet_snow_masked': self.wet_snow_masked,
            'calibration_offset': self.calibration_offset,
            'source': self.source,
            'metadata': self.metadata,
        }


def compute_cross_ratio(vh_db: float, vv_db: float) -> float | None:
    """Compute the S1 cross-ratio depth index.

    cross_ratio = VH - VV (in dB)
    Higher cross-ratio correlates with deeper dry snow.

    Args:
        vh_db: VH polarized backscatter in dB.
        vv_db: VV polarized backscatter in dB.

    Returns:
        Cross-ratio in dB, or None if inputs are invalid.
    """
    if vh_db is None or vv_db is None:
        return None
    return vh_db - vv_db


def apply_wet_snow_mask(
    *,
    cross_ratio: float | None,
    wet_snow_fraction: float | None,
    threshold: float = 0.5,
) -> float | None:
    """Mask cross-ratio when wet snow is present.

    Wet snow absorbs radar signal, making cross-ratio unreliable.
    Returns None when wet_snow_fraction exceeds threshold.

    Args:
        cross_ratio: Cross-ratio depth index.
        wet_snow_fraction: Fraction of cell with wet snow (0-1).
        threshold: Wet snow fraction above which to mask.

    Returns:
        Cross-ratio if not masked, None if masked.
    """
    if cross_ratio is None:
        return None
    if wet_snow_fraction is not None and wet_snow_fraction > threshold:
        return None
    return cross_ratio


def calibrate_depth(
    *,
    cross_ratio: float | None,
    weather_snow_depth_m: float | None,
    calibration_offset: float = 0.0,
    calibration_scale: float = 0.01,
) -> tuple[float | None, float]:
    """Calibrate cross-ratio to physical snow depth.

    Uses a simple linear calibration: depth = scale * cross_ratio + offset.
    When weather-derived depth is available, adjusts offset to match.

    Args:
        cross_ratio: Cross-ratio depth index (dB).
        weather_snow_depth_m: Weather-derived snow depth for calibration.
        calibration_offset: Base offset.
        calibration_scale: Scale factor (m/dB).

    Returns:
        Tuple of (calibrated_depth_m, adjusted_offset).
    """
    if cross_ratio is None:
        return None, calibration_offset

    if weather_snow_depth_m is not None:
        adjusted_offset = weather_snow_depth_m - calibration_scale * cross_ratio
        depth = calibration_scale * cross_ratio + adjusted_offset
        return max(depth, 0.0), adjusted_offset

    depth = calibration_scale * cross_ratio + calibration_offset
    return max(depth, 0.0), calibration_offset


def estimate_s1_snow_depth(
    *,
    cell_id: str,
    vh_db: float | None,
    vv_db: float | None,
    wet_snow_fraction: float | None = None,
    weather_snow_depth_m: float | None = None,
    calibration_offset: float = 0.0,
) -> S1SnowDepthResult | None:
    """Estimate snow depth from S1 cross-ratio for a single cell.

    Returns None when S1_DEPTH_ENABLED is false.
    """
    if not S1_DEPTH_ENABLED:
        return None

    cr = compute_cross_ratio(vh_db, vv_db)
    if cr is None:
        return S1SnowDepthResult(
            cell_id=cell_id,
            vh_db=vh_db,
            vv_db=vv_db,
            wet_snow_masked=True,
        )

    masked_cr = apply_wet_snow_mask(cross_ratio=cr, wet_snow_fraction=wet_snow_fraction)
    if masked_cr is None:
        return S1SnowDepthResult(
            cell_id=cell_id,
            depth_index=cr,
            vh_db=vh_db,
            vv_db=vv_db,
            wet_snow_masked=True,
        )

    depth, adjusted_offset = calibrate_depth(
        cross_ratio=masked_cr,
        weather_snow_depth_m=weather_snow_depth_m,
        calibration_offset=calibration_offset,
    )

    return S1SnowDepthResult(
        cell_id=cell_id,
        depth_index=cr,
        snow_depth_m=depth,
        vh_db=vh_db,
        vv_db=vv_db,
        wet_snow_masked=False,
        calibration_offset=adjusted_offset,
    )
