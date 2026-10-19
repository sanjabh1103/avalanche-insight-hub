"""AWS/eDMRG validation pipeline — cross-validate station observations vs forecast.

Compares eDMRG station telemetry (temperature, wind, snow depth) against
Open-Meteo forecast data for the same coordinates and timestamps. Produces
validation metrics (bias, RMSE, correlation) and anomaly flags that can
feed back into the ML pipeline for calibration.

Environment variables:
  EDMRG_VALIDATION_THRESHOLD_TEMP_C: Max acceptable temp bias (default: 3.0)
  EDMRG_VALIDATION_THRESHOLD_WIND_MS: Max acceptable wind bias (default: 5.0)
  EDMRG_VALIDATION_THRESHOLD_SNOW_CM: Max acceptable snow depth bias (default: 20.0)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from backend.common.edmrg_adapter import EdmrgRecord, EDMRG_TO_PIPELINE

EDMRG_VALIDATION_THRESHOLD_TEMP_C = float(os.getenv('EDMRG_VALIDATION_THRESHOLD_TEMP_C', '3.0'))
EDMRG_VALIDATION_THRESHOLD_WIND_MS = float(os.getenv('EDMRG_VALIDATION_THRESHOLD_WIND_MS', '5.0'))
EDMRG_VALIDATION_THRESHOLD_SNOW_CM = float(os.getenv('EDMRG_VALIDATION_THRESHOLD_SNOW_CM', '20.0'))


@dataclass(frozen=True)
class StationValidationResult:
    """Validation result for a single station."""
    station_id: str
    n_observations: int
    temp_bias_c: float
    temp_rmse_c: float
    wind_bias_ms: float
    wind_rmse_ms: float
    snow_depth_bias_cm: float
    snow_depth_rmse_cm: float
    anomalies: list[str] = field(default_factory=list)
    passed: bool = True


@dataclass(frozen=True)
class ValidationReport:
    """Aggregated validation report across all stations."""
    stations: list[StationValidationResult]
    total_observations: int
    total_anomalies: int
    overall_passed: bool
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _safe_get(fields: dict[str, float], key: str) -> float | None:
    val = fields.get(key)
    if val is None or not math.isfinite(float(val)):
        return None
    return float(val)


def _nearest_forecast_value(
    forecast_samples: list[dict[str, Any]],
    target_time: datetime,
    var_name: str,
) -> float | None:
    """Find the nearest forecast sample value for a target time."""
    if not forecast_samples:
        return None

    target = target_time.astimezone(timezone.utc)
    best_dist = float('inf')
    best_val: float | None = None

    for sample in forecast_samples:
        ts = sample.get('timestamp') or sample.get('time')
        if ts is None:
            continue
        if isinstance(ts, str):
            try:
                sample_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except ValueError:
                continue
        elif isinstance(ts, datetime):
            sample_dt = ts
        else:
            continue

        if sample_dt.tzinfo is None:
            sample_dt = sample_dt.replace(tzinfo=timezone.utc)

        dist = abs((sample_dt - target).total_seconds())
        if dist < best_dist and dist <= 7200:
            best_dist = dist
            val = sample.get(var_name) if isinstance(sample, dict) else None
            if isinstance(sample, dict):
                values = sample.get('values', sample)
                val = values.get(var_name) if isinstance(values, dict) else None
            if val is not None:
                try:
                    best_val = float(val)
                except (ValueError, TypeError):
                    pass

    return best_val


def validate_station_observations(
    records: list[EdmrgRecord],
    forecast_samples: list[dict[str, Any]],
    station_id: str | None = None,
) -> StationValidationResult:
    """Validate eDMRG station observations against forecast data.

    Args:
        records: EdmrgRecord list for a single station
        forecast_samples: Open-Meteo forecast samples (list of dicts with timestamp + values)
        station_id: Optional station ID override

    Returns:
        StationValidationResult with bias, RMSE, and anomaly flags
    """
    sid = station_id or (records[0].station_id if records else 'unknown')

    temp_obs: list[float] = []
    temp_fcst: list[float] = []
    wind_obs: list[float] = []
    wind_fcst: list[float] = []
    snow_obs: list[float] = []
    snow_fcst: list[float] = []

    for rec in records:
        edmrg_temp = _safe_get(rec.fields, 'temperature_c')
        edmrg_wind = _safe_get(rec.fields, 'wind_speed_ms')
        edmrg_snow = _safe_get(rec.fields, 'snow_depth_cm')

        if edmrg_temp is not None:
            fcst_temp = _nearest_forecast_value(forecast_samples, rec.timestamp, 'temperature_2m')
            if fcst_temp is not None:
                temp_obs.append(edmrg_temp)
                temp_fcst.append(fcst_temp)

        if edmrg_wind is not None:
            fcst_wind = _nearest_forecast_value(forecast_samples, rec.timestamp, 'windspeed_10m')
            if fcst_wind is not None:
                wind_obs.append(edmrg_wind)
                wind_fcst.append(fcst_wind)

        if edmrg_snow is not None:
            fcst_snow = _nearest_forecast_value(forecast_samples, rec.timestamp, 'snow_depth')
            if fcst_snow is not None:
                snow_obs.append(edmrg_snow)
                snow_fcst.append(fcst_snow)

    def _bias(obs: list[float], fcst: list[float]) -> float:
        if not obs:
            return 0.0
        return float(np.mean(np.array(fcst) - np.array(obs)))

    def _rmse(obs: list[float], fcst: list[float]) -> float:
        if not obs:
            return 0.0
        return float(np.sqrt(np.mean((np.array(fcst) - np.array(obs)) ** 2)))

    temp_bias = _bias(temp_obs, temp_fcst)
    temp_rmse = _rmse(temp_obs, temp_fcst)
    wind_bias = _bias(wind_obs, wind_fcst)
    wind_rmse = _rmse(wind_obs, wind_fcst)
    snow_bias = _bias(snow_obs, snow_fcst)
    snow_rmse = _rmse(snow_obs, snow_fcst)

    anomalies: list[str] = []
    passed = True

    if abs(temp_bias) > EDMRG_VALIDATION_THRESHOLD_TEMP_C:
        anomalies.append(f'temp_bias_{temp_bias:.1f}C_exceeds_{EDMRG_VALIDATION_THRESHOLD_TEMP_C}C')
        passed = False

    if abs(wind_bias) > EDMRG_VALIDATION_THRESHOLD_WIND_MS:
        anomalies.append(f'wind_bias_{wind_bias:.1f}ms_exceeds_{EDMRG_VALIDATION_THRESHOLD_WIND_MS}ms')
        passed = False

    if abs(snow_bias) > EDMRG_VALIDATION_THRESHOLD_SNOW_CM:
        anomalies.append(f'snow_depth_bias_{snow_bias:.1f}cm_exceeds_{EDMRG_VALIDATION_THRESHOLD_SNOW_CM}cm')
        passed = False

    n_obs = max(len(temp_obs), len(wind_obs), len(snow_obs))

    return StationValidationResult(
        station_id=sid,
        n_observations=n_obs,
        temp_bias_c=round(temp_bias, 2),
        temp_rmse_c=round(temp_rmse, 2),
        wind_bias_ms=round(wind_bias, 2),
        wind_rmse_ms=round(wind_rmse, 2),
        snow_depth_bias_cm=round(snow_bias, 2),
        snow_depth_rmse_cm=round(snow_rmse, 2),
        anomalies=anomalies,
        passed=passed,
    )


def run_validation_pipeline(
    records: list[EdmrgRecord],
    forecast_samples: list[dict[str, Any]],
) -> ValidationReport:
    """Run the full AWS/eDMRG validation pipeline.

    Groups records by station, validates each against forecast data,
    and produces an aggregated report.

    Args:
        records: All EdmrgRecord entries from the ingest
        forecast_samples: Open-Meteo forecast samples for the region

    Returns:
        ValidationReport with per-station and overall results
    """
    stations: dict[str, list[EdmrgRecord]] = {}
    for rec in records:
        stations.setdefault(rec.station_id, []).append(rec)

    station_results: list[StationValidationResult] = []
    for sid, station_records in stations.items():
        result = validate_station_observations(station_records, forecast_samples, sid)
        station_results.append(result)

    total_obs = sum(s.n_observations for s in station_results)
    total_anomalies = sum(len(s.anomalies) for s in station_results)
    overall_passed = all(s.passed for s in station_results)

    return ValidationReport(
        stations=station_results,
        total_observations=total_obs,
        total_anomalies=total_anomalies,
        overall_passed=overall_passed,
    )
