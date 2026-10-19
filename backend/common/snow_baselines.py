"""Rolling snow baselines for the continuous verification spine.

Computes per-cell, per-sensor rolling statistics (percentiles, mean, std)
from historical forecast/SAR/weather data. Implements pseudo-control cell
matching inspired by Pachama's dynamic control area baseline: for each cell,
find similar cells by elevation/aspect/slope bands to serve as controls.

Window types:
  - 30d: last 30 days (recent conditions)
  - 90d: last 90 days (seasonal trend)
  - seasonal: same calendar window in previous seasons

The baselines are used by anomaly_detector.py to compute z-scores and
by fusion_engine.py for uncertainty calibration.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import numpy as np

from backend.common.verification_contracts import VERIFICATION_SPINE_ENABLED

WINDOW_30D = '30d'
WINDOW_90D = '90d'
WINDOW_SEASONAL = 'seasonal'

VALID_WINDOWS = frozenset({WINDOW_30D, WINDOW_90D, WINDOW_SEASONAL})

# Pseudo-control matching bands
ELEVATION_BAND_M = 200.0
ASPECT_BAND_DEG = 45.0
SLOPE_BAND_DEG = 5.0


@dataclass
class BaselineStats:
    """Rolling baseline statistics for a cell/sensor/window combination."""

    cell_id: str
    sensor: str
    window: str
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    mean: float | None = None
    std: float | None = None
    count: int = 0
    control_cell_ids: list[str] = field(default_factory=list)
    updated_at: str = ''

    @property
    def is_valid(self) -> bool:
        return self.count >= 5 and self.std is not None and self.std > 1e-9

    def z_score(self, observed: float) -> float | None:
        """Compute z-score of observed value against this baseline."""
        if not self.is_valid or self.mean is None or self.std is None:
            return None
        return (observed - self.mean) / self.std

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'sensor': self.sensor,
            'window': self.window,
            'p25': self.p25,
            'p50': self.p50,
            'p75': self.p75,
            'mean': self.mean,
            'std': self.std,
            'count': self.count,
            'control_cell_ids': self.control_cell_ids,
            'updated_at': self.updated_at,
        }


@dataclass
class CellTerrainSignature:
    """Terrain attributes used for pseudo-control matching."""

    cell_id: str
    elevation_m: float
    aspect_deg: float
    slope_deg: float

    def matches(self, other: CellTerrainSignature) -> bool:
        """Check if another cell is within matching bands."""
        aspect_delta = abs((self.aspect_deg - other.aspect_deg + 180.0) % 360.0 - 180.0)
        return (
            abs(self.elevation_m - other.elevation_m) <= ELEVATION_BAND_M
            and aspect_delta <= ASPECT_BAND_DEG
            and abs(self.slope_deg - other.slope_deg) <= SLOPE_BAND_DEG
        )


def compute_baseline_stats(
    values: Sequence[float],
    cell_id: str,
    sensor: str,
    window: str,
    control_cell_ids: list[str] | None = None,
) -> BaselineStats:
    """Compute baseline statistics from a series of historical values.

    Args:
        values: Historical observations for this cell/sensor/window.
        cell_id: Cell identifier.
        sensor: Sensor name (e.g. 'sar_wet_snow', 'weather_snowpack', 'gibs_snow_cover').
        window: Time window name.
        control_cell_ids: IDs of pseudo-control cells matched by terrain.

    Returns:
        BaselineStats with percentiles and moments.
    """
    if window not in VALID_WINDOWS:
        raise ValueError(f'Invalid window: {window}. Must be one of {VALID_WINDOWS}')

    clean = [float(v) for v in values if v is not None and not math.isnan(v)]
    count = len(clean)

    if count == 0:
        return BaselineStats(
            cell_id=cell_id,
            sensor=sensor,
            window=window,
            count=0,
            control_cell_ids=control_cell_ids or [],
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    arr = np.array(clean, dtype=float)
    percentiles = np.percentile(arr, [25, 50, 75])

    return BaselineStats(
        cell_id=cell_id,
        sensor=sensor,
        window=window,
        p25=float(percentiles[0]),
        p50=float(percentiles[1]),
        p75=float(percentiles[2]),
        mean=float(np.mean(arr)),
        std=float(np.std(arr, ddof=1)) if count > 1 else 0.0,
        count=count,
        control_cell_ids=control_cell_ids or [],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def find_pseudo_controls(
    target: CellTerrainSignature,
    candidates: Sequence[CellTerrainSignature],
    max_controls: int = 5,
) -> list[str]:
    """Find pseudo-control cells matching the target's terrain signature.

    Uses elevation/aspect/slope bands for matching, similar to Pachama's
    dynamic control area baseline approach.

    Args:
        target: The cell to find controls for.
        candidates: Other cells to search.
        max_controls: Maximum number of control cells to return.

    Returns:
        List of cell IDs that match the target's terrain bands.
    """
    matches = [c for c in candidates if c.cell_id != target.cell_id and target.matches(c)]

    def _distance(candidate: CellTerrainSignature) -> tuple[float, str]:
        aspect_delta = abs((target.aspect_deg - candidate.aspect_deg + 180.0) % 360.0 - 180.0)
        score = (
            ((target.elevation_m - candidate.elevation_m) / ELEVATION_BAND_M) ** 2
            + (aspect_delta / ASPECT_BAND_DEG) ** 2
            + ((target.slope_deg - candidate.slope_deg) / SLOPE_BAND_DEG) ** 2
        )
        return score, candidate.cell_id

    matches.sort(key=_distance)
    return [c.cell_id for c in matches[:max_controls]]


def filter_history_by_window(
    history: Sequence[tuple[datetime, float]],
    window: str,
    as_of: datetime,
) -> list[float]:
    """Filter historical observations by time window.

    Args:
        history: List of (timestamp, value) pairs.
        window: Window type ('30d', '90d', 'seasonal').
        as_of: Reference timestamp.

    Returns:
        List of values within the window.
    """
    if window == WINDOW_30D:
        cutoff = as_of - timedelta(days=30)
        return [v for ts, v in history if ts >= cutoff and ts <= as_of]
    elif window == WINDOW_90D:
        cutoff = as_of - timedelta(days=90)
        return [v for ts, v in history if ts >= cutoff and ts <= as_of]
    elif window == WINDOW_SEASONAL:
        # Same calendar window (±15 days) in previous years
        day_of_year = as_of.timetuple().tm_yday
        seasonal_values: list[float] = []
        for ts, v in history:
            ts_doy = ts.timetuple().tm_yday
            if abs(ts_doy - day_of_year) <= 15 and ts.year < as_of.year:
                seasonal_values.append(v)
        return seasonal_values
    else:
        raise ValueError(f'Invalid window: {window}')


def build_cell_baselines(
    cell_id: str,
    sensor: str,
    history: Sequence[tuple[datetime, float]],
    as_of: datetime,
    control_cell_ids: list[str] | None = None,
    windows: Sequence[str] | None = None,
) -> dict[str, BaselineStats]:
    """Build baseline stats for all windows for a cell/sensor pair.

    Args:
        cell_id: Cell identifier.
        sensor: Sensor name.
        history: Historical (timestamp, value) observations.
        as_of: Reference timestamp.
        control_cell_ids: Pseudo-control cell IDs.
        windows: Window types to compute (default: all three).

    Returns:
        Dict mapping window name to BaselineStats.
    """
    if not VERIFICATION_SPINE_ENABLED:
        return {}

    windows = windows or [WINDOW_30D, WINDOW_90D, WINDOW_SEASONAL]
    results: dict[str, BaselineStats] = {}

    for window in windows:
        values = filter_history_by_window(history, window, as_of)
        stats = compute_baseline_stats(
            values=values,
            cell_id=cell_id,
            sensor=sensor,
            window=window,
            control_cell_ids=control_cell_ids,
        )
        results[window] = stats

    return results
