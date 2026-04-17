"""Story 20: HIM-STRAT Class-II snowpack proxies.

Uses CUMULATIVE weather data from the start of the current winter season
(default Nov 1) rather than a 72h window, so the proxies respect snowpack
memory physics (Challenge on 72h contradiction).

The output is two dimensionally-scaled scalars per cell:
    estimated_shear_strength (kPa)      3 = weak, 5 = moderate, 8+ = strong
    snow_settlement_index    (0..1)     0 = fresh, 1 = highly consolidated

Weather is fetched from Open-Meteo's free historical endpoint. When the fetch
fails we fall back to a deterministic proxy derived from synthetic features so
the pipeline never crashes the release.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

import numpy as np
import requests


OPEN_METEO_ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'
OPEN_METEO_TIMEOUT = float(os.getenv('OPEN_METEO_TIMEOUT', '8'))


@dataclass(frozen=True)
class SnowpackProxy:
    estimated_shear_strength: float
    snow_settlement_index: float
    season_start: str
    method: str


def winter_season_start(as_of: datetime) -> date:
    """Northern-hemisphere winter season convention: Nov 1 of the current
    winter. If we're between Jan 1 and Oct 31 the season start is Nov 1 of
    the previous calendar year, otherwise Nov 1 of the current year.
    """
    if as_of.month >= 11:
        return date(as_of.year, 11, 1)
    return date(as_of.year - 1, 11, 1)


def _fetch_seasonal_weather(lat: float, lng: float, season_start: date, as_of: datetime) -> dict | None:
    try:
        response = requests.get(
            OPEN_METEO_ARCHIVE,
            params={
                'latitude': f'{lat:.4f}',
                'longitude': f'{lng:.4f}',
                'start_date': season_start.isoformat(),
                'end_date': as_of.date().isoformat(),
                'daily': ','.join([
                    'temperature_2m_mean',
                    'temperature_2m_min',
                    'snowfall_sum',
                    'precipitation_sum',
                ]),
                'timezone': 'UTC',
            },
            timeout=OPEN_METEO_TIMEOUT,
        )
        if response.status_code != 200:
            return None
        return response.json().get('daily') or None
    except Exception:  # pragma: no cover - network fallback is intentional
        return None


def _proxy_from_seasonal(daily: dict) -> SnowpackProxy | None:
    temps = np.asarray(daily.get('temperature_2m_mean') or [], dtype=float)
    tmins = np.asarray(daily.get('temperature_2m_min') or [], dtype=float)
    snows = np.asarray(daily.get('snowfall_sum') or [], dtype=float)
    precs = np.asarray(daily.get('precipitation_sum') or [], dtype=float)
    if temps.size == 0 or snows.size == 0:
        return None

    freeze_days = float(np.sum(tmins <= 0))
    cumulative_snow_cm = float(np.nansum(snows))
    cumulative_precip_mm = float(np.nansum(precs))
    mean_temp = float(np.nanmean(temps))

    # Heuristic dimensional scaling — this is intentionally transparent so
    # reviewers can see exactly why a cell scored the way it did.
    # Shear strength grows with freeze days and total precipitation, erodes
    # with warm mean temperatures that keep the snowpack wet.
    shear = 1.5 + 0.06 * freeze_days + 0.04 * cumulative_precip_mm / 10.0
    shear -= max(0.0, mean_temp) * 0.15
    shear = float(np.clip(shear, 0.5, 12.0))

    # Settlement is a saturating function of cumulative mass.
    settlement = 1.0 - math.exp(-max(0.0, cumulative_snow_cm + cumulative_precip_mm) / 250.0)
    settlement = float(np.clip(settlement, 0.0, 1.0))

    return SnowpackProxy(
        estimated_shear_strength=round(shear, 2),
        snow_settlement_index=round(settlement, 3),
        season_start='open_meteo_seasonal',
        method='seasonal_cumulative_v1',
    )


def _fallback_proxy(weather_inputs: dict[str, float], terrain_inputs: dict[str, float]) -> SnowpackProxy:
    snowfall = float(weather_inputs.get('snowfall_24h', 0.0) or 0.0)
    wind = float(weather_inputs.get('wind_loading', 0.0) or 0.0)
    temp_gradient = float(weather_inputs.get('temp_gradient', 0.5) or 0.5)
    elevation = float(terrain_inputs.get('elevation', 0.5) or 0.5)

    shear = 2.0 + elevation * 4.0 - temp_gradient * 2.0 + (1 - wind) * 1.5
    settlement = 0.2 + snowfall * 0.4 + elevation * 0.25
    return SnowpackProxy(
        estimated_shear_strength=round(float(np.clip(shear, 0.5, 12.0)), 2),
        snow_settlement_index=round(float(np.clip(settlement, 0.0, 1.0)), 3),
        season_start='synthetic_fallback',
        method='synthetic_fallback_v1',
    )


def compute_cell_snowpack_proxy(
    *,
    lat: float,
    lng: float,
    as_of: datetime,
    weather_inputs: dict[str, float],
    terrain_inputs: dict[str, float],
) -> SnowpackProxy:
    """Attempt real Open-Meteo seasonal fetch; fall back to synthetic on failure."""
    season_start = winter_season_start(as_of)
    daily = _fetch_seasonal_weather(lat, lng, season_start, as_of)
    if daily is not None:
        proxy = _proxy_from_seasonal(daily)
        if proxy is not None:
            return SnowpackProxy(
                estimated_shear_strength=proxy.estimated_shear_strength,
                snow_settlement_index=proxy.snow_settlement_index,
                season_start=season_start.isoformat(),
                method=proxy.method,
            )
    return _fallback_proxy(weather_inputs, terrain_inputs)


def compute_region_snowpack_proxy(
    *,
    center_lat: float,
    center_lng: float,
    as_of: datetime,
    cells: Iterable[dict],
) -> SnowpackProxy:
    """Single fetch per region at the center; reused across all cells to
    keep the total Open-Meteo call count bounded to ~1 per region per run.
    """
    season_start = winter_season_start(as_of)
    daily = _fetch_seasonal_weather(center_lat, center_lng, season_start, as_of)
    if daily is not None:
        proxy = _proxy_from_seasonal(daily)
        if proxy is not None:
            return SnowpackProxy(
                estimated_shear_strength=proxy.estimated_shear_strength,
                snow_settlement_index=proxy.snow_settlement_index,
                season_start=season_start.isoformat(),
                method=proxy.method,
            )
    # Aggregate synthetic fallback across all cells for a stable regional value.
    cells_list = list(cells)
    if not cells_list:
        return SnowpackProxy(
            estimated_shear_strength=3.0,
            snow_settlement_index=0.3,
            season_start=season_start.isoformat(),
            method='synthetic_fallback_empty',
        )
    weather_agg = {
        'snowfall_24h': float(np.mean([c.get('weather_inputs', {}).get('snowfall_24h', 0.0) for c in cells_list])),
        'wind_loading': float(np.mean([c.get('weather_inputs', {}).get('wind_loading', 0.0) for c in cells_list])),
        'temp_gradient': float(np.mean([c.get('weather_inputs', {}).get('temp_gradient', 0.5) for c in cells_list])),
    }
    terrain_agg = {
        'elevation': float(np.mean([c.get('terrain_inputs', {}).get('elevation', 0.5) for c in cells_list])),
    }
    fallback = _fallback_proxy(weather_agg, terrain_agg)
    return SnowpackProxy(
        estimated_shear_strength=fallback.estimated_shear_strength,
        snow_settlement_index=fallback.snow_settlement_index,
        season_start=season_start.isoformat(),
        method=fallback.method,
    )
