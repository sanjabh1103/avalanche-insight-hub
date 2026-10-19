"""Baseline time-series retrieval for verification spine visualization.

Returns per-cell time-series of baseline percentiles, observed values,
residual z-scores, and anomaly state transitions from the verification
observations and baselines tables.

Env flags:
  VERIFICATION_SPINE_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

VERIFICATION_SPINE_ENABLED = os.getenv('VERIFICATION_SPINE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)


@dataclass(frozen=True)
class BaselineTimeseriesPoint:
    """Single time-series data point for a cell's baseline history."""
    date: str
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    observed: float | None = None
    residual_zscore: float | None = None
    anomaly_state: str = 'unverified'
    freshness_hours: float | None = None
    sensor: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'date': self.date,
            'p25': self.p25,
            'p50': self.p50,
            'p75': self.p75,
            'observed': self.observed,
            'residual_zscore': self.residual_zscore,
            'anomaly_state': self.anomaly_state,
            'freshness_hours': self.freshness_hours,
            'sensor': self.sensor,
        }


@dataclass(frozen=True)
class BaselineTimeseriesResult:
    """Complete time-series response for a cell."""
    region_key: str
    cell_id: str
    sensor: str
    points: list[BaselineTimeseriesPoint] = field(default_factory=list)
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def to_dict(self) -> dict[str, Any]:
        return {
            'region_key': self.region_key,
            'cell_id': self.cell_id,
            'sensor': self.sensor,
            'points': [p.to_dict() for p in self.points],
            'disclaimer': self.disclaimer,
        }


def get_baseline_timeseries(
    region_key: str,
    cell_id: str,
    sensor: str,
    *,
    window: str = 'rolling_90d',
    max_points: int = 90,
    observation_rows: list[dict[str, Any]] | None = None,
    baseline_rows: list[dict[str, Any]] | None = None,
) -> BaselineTimeseriesResult:
    """Build a baseline time-series from observation and baseline rows.

    When observation_rows / baseline_rows are provided (e.g. from Supabase),
    joins them by acquisition_time to produce a time-series. When not
    provided, returns an empty result (caller should fetch from DB).

    Args:
        region_key: Region identifier.
        cell_id: Cell identifier.
        sensor: Sensor name (e.g. 'weather', 'sar', 'optical').
        window: Baseline window label (rolling_90d, seasonal, etc.).
        max_points: Maximum number of points to return.
        observation_rows: Pre-fetched observation dicts from verification_observations.
        baseline_rows: Pre-fetched baseline dicts from verification_baselines.

    Returns:
        BaselineTimeseriesResult with joined time-series points.
    """
    if not VERIFICATION_SPINE_ENABLED:
        return BaselineTimeseriesResult(
            region_key=region_key,
            cell_id=cell_id,
            sensor=sensor,
        )

    obs_rows = observation_rows or []
    base_rows = baseline_rows or []

    baseline_by_date: dict[str, dict[str, Any]] = {}
    for row in base_rows:
        if str(row.get('cell_id', '')) != cell_id:
            continue
        if str(row.get('sensor', '')) != sensor:
            continue
        date_key = str(row.get('as_of_date', row.get('created_at', '')))[:10]
        if date_key:
            baseline_by_date[date_key] = row

    points: list[BaselineTimeseriesPoint] = []
    for obs in obs_rows:
        if str(obs.get('cell_id', '')) != cell_id:
            continue
        if str(obs.get('sensor', '')) != sensor:
            continue

        acq_time = obs.get('acquisition_time', '')
        if isinstance(acq_time, str):
            date_key = acq_time[:10]
        elif isinstance(acq_time, datetime):
            date_key = acq_time.strftime('%Y-%m-%d')
        else:
            continue

        baseline = baseline_by_date.get(date_key, {})

        value = obs.get('value')
        p25 = baseline.get('p25')
        p50 = baseline.get('p50')
        p75 = baseline.get('p75')

        residual_zscore = None
        if value is not None and p50 is not None:
            std = baseline.get('std')
            if std and float(std) > 1e-9:
                residual_zscore = (float(value) - float(p50)) / float(std)

        points.append(BaselineTimeseriesPoint(
            date=date_key,
            p25=float(p25) if p25 is not None else None,
            p50=float(p50) if p50 is not None else None,
            p75=float(p75) if p75 is not None else None,
            observed=float(value) if value is not None else None,
            residual_zscore=residual_zscore,
            anomaly_state=str(obs.get('quality_state', 'unverified')),
            freshness_hours=float(obs.get('freshness_hours', 0)) if obs.get('freshness_hours') is not None else None,
            sensor=sensor,
        ))

    points.sort(key=lambda p: p.date)
    if len(points) > max_points:
        points = points[-max_points:]

    return BaselineTimeseriesResult(
        region_key=region_key,
        cell_id=cell_id,
        sensor=sensor,
        points=points,
    )
