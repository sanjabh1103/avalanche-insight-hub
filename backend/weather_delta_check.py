"""Weather delta check — triggers inference if significant weather change detected.

Compares latest Open-Meteo forecast against the last published forecast for each
region. If any threshold is exceeded, sets GitHub Actions step outputs for
conditional inference execution.

Exit code 0 + stdout JSON: {"trigger": true/false, "regions": [...], "reasons": [...]}

Thresholds (configurable via env vars):
  WEATHER_DELTA_SNOWFALL_CM  — new snow accumulation delta (default: 10 cm)
  WEATHER_DELTA_WIND_KMH     — wind speed delta (default: 15 km/h)
  WEATHER_DELTA_TEMP_C       — temperature delta (default: 5°C)
  WEATHER_DELTA_RAIN_MM      — rain precipitation delta (default: 2 mm)
  WEATHER_DELTA_HOURS        — max hours since last forecast before auto-trigger (default: 6)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from backend.common.real_features import OPEN_METEO_FORECAST, _fetch_open_meteo
from backend.common.regions import load_regions
from backend.common.seismic_integrator import (
    HIMALAYAN_BBOX,
    check_active_windows,
    fetch_recent_earthquakes,
)
from backend.common.supabase_io import has_supabase_credentials, rest_get

WEATHER_DELTA_SNOWFALL_CM = float(os.getenv('WEATHER_DELTA_SNOWFALL_CM', '10'))
WEATHER_DELTA_WIND_KMH = float(os.getenv('WEATHER_DELTA_WIND_KMH', '15'))
WEATHER_DELTA_TEMP_C = float(os.getenv('WEATHER_DELTA_TEMP_C', '5'))
WEATHER_DELTA_RAIN_MM = float(os.getenv('WEATHER_DELTA_RAIN_MM', '2'))
WEATHER_DELTA_HOURS = float(os.getenv('WEATHER_DELTA_HOURS', '6'))

FORECAST_VARS = (
    'temperature_2m',
    'precipitation',
    'snowfall',
    'snow_depth',
    'windspeed_10m',
    'rain',
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_latest_forecast_summary(region_key: str) -> dict[str, Any] | None:
    """Fetch the most recent published forecast_run for a region from Supabase."""
    if not has_supabase_credentials():
        return None
    try:
        rows = rest_get(
            'forecast_runs',
            {
                'select': 'region_key,issue_time,horizon_hours',
                'region_key': f'eq.{region_key}',
                'order': 'issue_time.desc',
                'limit': '1',
            },
        )
        return rows[0] if rows else None
    except Exception as exc:
        print(f'[weather_delta_check] Could not fetch last forecast for {region_key}: {exc}', file=sys.stderr)
        return None


def _fetch_current_forecast(region_center: tuple[float, float], hours: int = 24) -> dict[str, float]:
    """Fetch latest Open-Meteo forecast and summarize key variables over the window."""
    payload = _fetch_open_meteo(
        OPEN_METEO_FORECAST,
        params={
            'latitude': f'{region_center[0]:.4f}',
            'longitude': f'{region_center[1]:.4f}',
            'hourly': ','.join(FORECAST_VARS),
            'timezone': 'UTC',
            'forecast_days': max(1, hours // 24 + 1),
        },
    )
    hourly = payload.get('hourly', {})
    times = hourly.get('time', [])
    n = min(len(times), hours)

    def _sum(var: str) -> float:
        vals = hourly.get(var, [])[:n]
        return float(sum(v for v in vals if v is not None)) if vals else 0.0

    def _mean(var: str) -> float:
        vals = [v for v in hourly.get(var, [])[:n] if v is not None]
        return float(sum(vals) / len(vals)) if vals else 0.0

    def _max(var: str) -> float:
        vals = [v for v in hourly.get(var, [])[:n] if v is not None]
        return float(max(vals)) if vals else 0.0

    return {
        'snowfall_sum_cm': _sum('snowfall'),
        'precipitation_sum_mm': _sum('precipitation'),
        'rain_sum_mm': _sum('rain'),
        'temperature_mean_c': _mean('temperature_2m'),
        'temperature_max_c': _max('temperature_2m'),
        'windspeed_max_kmh': _max('windspeed_10m'),
        'snow_depth_max_cm': _max('snow_depth'),
    }


def _compare_and_decide(
    region_key: str,
    current: dict[str, float],
    last_forecast: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Compare current forecast against last published forecast. Return (trigger, reason)."""
    reasons: list[str] = []

    if last_forecast is None:
        return True, 'no_previous_forecast'

    issue_time_str = last_forecast.get('issue_time')
    if issue_time_str:
        try:
            issue_time = datetime.fromisoformat(issue_time_str.replace('Z', '+00:00'))
            hours_since = (_utc_now() - issue_time).total_seconds() / 3600.0
            if hours_since >= WEATHER_DELTA_HOURS:
                return True, f'stale_forecast_{int(hours_since)}h'
        except Exception:
            pass

    return False, None


def _check_thresholds(current: dict[str, float]) -> list[str]:
    """Check if current forecast values exceed dangerous thresholds."""
    reasons: list[str] = []
    if current['snowfall_sum_cm'] >= WEATHER_DELTA_SNOWFALL_CM:
        reasons.append(f"snowfall_{current['snowfall_sum_cm']:.1f}cm>={WEATHER_DELTA_SNOWFALL_CM}cm")
    if current['windspeed_max_kmh'] >= WEATHER_DELTA_WIND_KMH:
        reasons.append(f"wind_{current['windspeed_max_kmh']:.1f}kmh>={WEATHER_DELTA_WIND_KMH}kmh")
    if current['rain_sum_mm'] >= WEATHER_DELTA_RAIN_MM:
        reasons.append(f"rain_{current['rain_sum_mm']:.1f}mm>={WEATHER_DELTA_RAIN_MM}mm")
    temp_abs = abs(current['temperature_max_c'])
    if temp_abs >= WEATHER_DELTA_TEMP_C and current['temperature_max_c'] > 0:
        reasons.append(f"warming_{current['temperature_max_c']:.1f}c>0")
    return reasons


def _check_seismic_activity() -> tuple[bool, str | None]:
    """Check if any recent seismic events have active post-tremor windows.

    Returns (trigger, reason).
    """
    try:
        events = fetch_recent_earthquakes(HIMALAYAN_BBOX)
        if not events:
            return False, None
        now = _utc_now()
        active_count = 0
        for event in events:
            windows = check_active_windows(event, now)
            if windows:
                active_count += 1
        if active_count > 0:
            return True, f'seismic_active_windows:{active_count}'
    except Exception as exc:
        print(f'[weather_delta_check] Seismic check failed: {exc}', file=sys.stderr)
    return False, None


def main() -> int:
    regions = load_regions()
    triggered_regions: list[str] = []
    all_reasons: list[str] = []
    per_region_details: list[dict[str, Any]] = []

    for region in regions:
        try:
            current = _fetch_current_forecast(region.center, hours=24)
            last_forecast = _fetch_latest_forecast_summary(region.key)
            stale_trigger, stale_reason = _compare_and_decide(region.key, current, last_forecast)
            threshold_reasons = _check_thresholds(current)

            region_reasons: list[str] = []
            if stale_trigger and stale_reason:
                region_reasons.append(stale_reason)
            region_reasons.extend(threshold_reasons)

            is_triggered = len(region_reasons) > 0
            if is_triggered:
                triggered_regions.append(region.key)
                all_reasons.extend(region_reasons)

            per_region_details.append({
                'region': region.key,
                'triggered': is_triggered,
                'reasons': region_reasons,
                'current_forecast': current,
                'last_forecast_issue_time': last_forecast.get('issue_time') if last_forecast else None,
            })
        except Exception as exc:
            print(f'[weather_delta_check] Region {region.key} check failed: {exc}', file=sys.stderr)
            per_region_details.append({
                'region': region.key,
                'triggered': False,
                'error': str(exc),
            })

    trigger = len(triggered_regions) > 0
    regions_str = ','.join(triggered_regions) if triggered_regions else ''
    reasons_str = '; '.join(sorted(set(all_reasons))) if all_reasons else ''

    # F1: Seismic trigger — force inference if active post-tremor windows exist
    seismic_trigger, seismic_reason = _check_seismic_activity()
    if seismic_trigger:
        trigger = True
        if seismic_reason:
            all_reasons.append(seismic_reason)
            reasons_str = '; '.join(sorted(set(all_reasons))) if all_reasons else ''

    result = {
        'trigger': trigger,
        'regions': regions_str,
        'reasons': reasons_str,
        'details': per_region_details,
        'thresholds': {
            'snowfall_cm': WEATHER_DELTA_SNOWFALL_CM,
            'wind_kmh': WEATHER_DELTA_WIND_KMH,
            'temp_c': WEATHER_DELTA_TEMP_C,
            'rain_mm': WEATHER_DELTA_RAIN_MM,
            'stale_hours': WEATHER_DELTA_HOURS,
        },
    }

    print(json.dumps(result, indent=2))

    if trigger:
        print(f'::set-output name=trigger::true')
        print(f'::set-output name=regions::{regions_str}')
        print(f'::set-output name=reasons::{reasons_str}')
    else:
        print(f'::set-output name=trigger::false')
        print(f'::set-output name=regions::')
        print(f'::set-output name=reasons::')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
