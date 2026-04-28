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
import time
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import requests


OPEN_METEO_ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'
OPEN_METEO_TIMEOUT = float(os.getenv('OPEN_METEO_TIMEOUT', '8'))
OPEN_METEO_RETRIES = int(os.getenv('OPEN_METEO_RETRIES', '4'))
OPEN_METEO_BATCH_SIZE = 50
OPEN_METEO_MINUTE_BUDGET = int(os.getenv('OPEN_METEO_MINUTE_BUDGET', '480'))
OPEN_METEO_WINDOW_SECONDS = 60.0
OPEN_METEO_RATE_LIMIT_RETRY_SECONDS = float(os.getenv('OPEN_METEO_RATE_LIMIT_RETRY_SECONDS', '60'))
OPEN_METEO_DAILY_VARS = (
    'temperature_2m_mean',
    'temperature_2m_min',
    'snowfall_sum',
    'precipitation_sum',
)


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


def _archive_request_params(
    latitudes: list[float],
    longitudes: list[float],
    season_start: date,
    as_of: datetime,
) -> dict[str, str]:
    return {
        'latitude': ','.join(f'{lat:.4f}' for lat in latitudes),
        'longitude': ','.join(f'{lng:.4f}' for lng in longitudes),
        'start_date': season_start.isoformat(),
        'end_date': as_of.date().isoformat(),
        'daily': ','.join(OPEN_METEO_DAILY_VARS),
        'timezone': 'UTC',
    }


def _fetch_archive_payload(*, params: dict[str, str], retries: int = OPEN_METEO_RETRIES) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        response = None
        try:
            response = requests.get(
                OPEN_METEO_ARCHIVE,
                params=params,
                timeout=OPEN_METEO_TIMEOUT,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f'HTTP {response.status_code}', response=response)
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                raise
            last_error = exc
        if attempt < retries - 1:
            retry_after = 0.0
            if response is not None:
                retry_after_header = response.headers.get('Retry-After')
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        retry_after = 0.0
            default_backoff = (
                OPEN_METEO_RATE_LIMIT_RETRY_SECONDS * (2 ** attempt)
                if response is not None and response.status_code == 429
                else 2 ** attempt
            )
            time.sleep(max(default_backoff, retry_after))
    raise last_error or RuntimeError(f'Failed to fetch from {OPEN_METEO_ARCHIVE} after {retries} attempts')


def _normalize_archive_batch_payload(payload: Any, *, expected_count: int) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = [payload]
    else:
        raise RuntimeError(f'Unexpected Open-Meteo archive payload type: {type(payload).__name__}')
    if len(items) != expected_count:
        raise RuntimeError(
            f'Open-Meteo archive payload count mismatch: expected {expected_count}, received {len(items)}'
        )
    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError('Open-Meteo archive payload contains non-object entries')
    return items


def _estimate_archive_call_units(*, location_count: int, season_start: date, as_of: datetime) -> int:
    day_span = max(1, (as_of.date() - season_start).days + 1)
    duration_multiplier = max(1, math.ceil(day_span / 14.0))
    variable_multiplier = max(1.0, len(OPEN_METEO_DAILY_VARS) / 10.0)
    return max(1, int(math.ceil(location_count * duration_multiplier * variable_multiplier)))


def _cache_key(lat: float, lng: float, as_of: datetime) -> str:
    return f'{lat:.4f},{lng:.4f},{as_of.date().isoformat()}'


def _proxy_to_cache_value(proxy: SnowpackProxy) -> dict[str, Any]:
    return {
        'estimated_shear_strength': proxy.estimated_shear_strength,
        'snow_settlement_index': proxy.snow_settlement_index,
        'season_start': proxy.season_start,
        'method': proxy.method,
    }


def _proxy_from_cache_value(value: Any) -> SnowpackProxy | None:
    if not isinstance(value, dict):
        return None
    try:
        return SnowpackProxy(
            estimated_shear_strength=float(value['estimated_shear_strength']),
            snow_settlement_index=float(value['snow_settlement_index']),
            season_start=str(value['season_start']),
            method=str(value['method']),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _load_proxy_cache(cache_path: Path | None) -> dict[str, Any]:
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_proxy_cache(cache_path: Path | None, cache_payload: dict[str, Any]) -> None:
    if cache_path is None:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(f'{cache_path.suffix}.tmp')
    tmp_path.write_text(json.dumps(cache_payload, sort_keys=True), encoding='utf-8')
    tmp_path.replace(cache_path)


def _fetch_seasonal_weather(lat: float, lng: float, season_start: date, as_of: datetime) -> dict | None:
    try:
        payload = _fetch_archive_payload(
            params=_archive_request_params([lat], [lng], season_start, as_of),
        )
        items = _normalize_archive_batch_payload(payload, expected_count=1)
        return items[0].get('daily') or None
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


def fetch_batched_cell_snowpack_proxies_strict(
    *,
    coordinates: Iterable[tuple[float, float]],
    as_of: datetime,
    batch_size: int = OPEN_METEO_BATCH_SIZE,
    cache_path: Path | None = None,
) -> list[SnowpackProxy]:
    coords = list(coordinates)
    if not coords:
        return []
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')

    season_start = winter_season_start(as_of)
    per_location_units = _estimate_archive_call_units(
        location_count=1,
        season_start=season_start,
        as_of=as_of,
    )
    effective_batch_size = min(
        batch_size,
        max(1, OPEN_METEO_MINUTE_BUDGET // per_location_units),
    )
    cache_payload = _load_proxy_cache(cache_path)
    resolved_proxies: list[SnowpackProxy | None] = [None] * len(coords)
    missing_indices: list[int] = []
    for index, (lat, lng) in enumerate(coords):
        cached_proxy = _proxy_from_cache_value(cache_payload.get(_cache_key(float(lat), float(lng), as_of)))
        if cached_proxy is not None:
            resolved_proxies[index] = cached_proxy
        else:
            missing_indices.append(index)
    window_started = time.monotonic()
    units_used_in_window = 0
    for offset in range(0, len(missing_indices), effective_batch_size):
        if time.monotonic() - window_started >= OPEN_METEO_WINDOW_SECONDS:
            window_started = time.monotonic()
            units_used_in_window = 0
        batch_indices = missing_indices[offset:offset + effective_batch_size]
        batch = [coords[index] for index in batch_indices]
        estimated_units = _estimate_archive_call_units(
            location_count=len(batch),
            season_start=season_start,
            as_of=as_of,
        )
        if units_used_in_window and units_used_in_window + estimated_units > OPEN_METEO_MINUTE_BUDGET:
            sleep_seconds = max(0.0, OPEN_METEO_WINDOW_SECONDS - (time.monotonic() - window_started))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            window_started = time.monotonic()
            units_used_in_window = 0
        latitudes = [float(lat) for lat, _ in batch]
        longitudes = [float(lng) for _, lng in batch]
        payload = _fetch_archive_payload(
            params=_archive_request_params(latitudes, longitudes, season_start, as_of),
        )
        units_used_in_window += estimated_units
        items = _normalize_archive_batch_payload(payload, expected_count=len(batch))
        for resolved_index, item in zip(batch_indices, items):
            daily = item.get('daily')
            if not isinstance(daily, dict):
                raise RuntimeError(
                    f'Missing daily seasonal weather payload for batch cell index {resolved_index}'
                )
            proxy = _proxy_from_seasonal(daily)
            if proxy is None:
                raise RuntimeError(
                    f'Unable to compute seasonal snowpack proxy for batch cell index {resolved_index}'
                )
            strict_proxy = SnowpackProxy(
                estimated_shear_strength=proxy.estimated_shear_strength,
                snow_settlement_index=proxy.snow_settlement_index,
                season_start=season_start.isoformat(),
                method=proxy.method,
            )
            resolved_proxies[resolved_index] = strict_proxy
            lat, lng = coords[resolved_index]
            cache_payload[_cache_key(float(lat), float(lng), as_of)] = _proxy_to_cache_value(strict_proxy)
        _write_proxy_cache(cache_path, cache_payload)
    if any(proxy is None for proxy in resolved_proxies):
        raise RuntimeError('Strict snowpack proxy fetch completed with unresolved coordinates')
    return [proxy for proxy in resolved_proxies if proxy is not None]


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
