from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import requests

from backend.common.snowpack_proxy import SnowpackProxy, compute_cell_snowpack_proxy


OPEN_METEO_FORECAST = 'https://api.open-meteo.com/v1/forecast'
OPEN_METEO_HISTORICAL_FORECAST = 'https://historical-forecast-api.open-meteo.com/v1/forecast'
OPEN_METEO_ARCHIVE = 'https://archive-api.open-meteo.com/v1/archive'
OPEN_METEO_TIMEOUT = 20.0
STANDARD_LAPSE_RATE_C_PER_M = -0.0065
PRESSURE_LEVELS = ('1000hPa', '925hPa', '850hPa', '700hPa')
DEM_MAX_SEARCH_DISTANCE_M = float(os.getenv('DEM_MAX_SEARCH_DISTANCE_M', '50'))

SURFACE_HOURLY_VARS = (
    'temperature_2m',
    'precipitation',
    'snowfall',
    'snow_depth',
    'windspeed_10m',
    'winddirection_10m',
    'freezing_level_height',
)

PRESSURE_HOURLY_VARS = tuple(
    [
        *(f'temperature_{level}' for level in PRESSURE_LEVELS),
        *(f'geopotential_height_{level}' for level in PRESSURE_LEVELS),
    ]
)

ALL_HOURLY_VARS = SURFACE_HOURLY_VARS + PRESSURE_HOURLY_VARS
ARCHIVE_HOURLY_VARS = (
    'temperature_2m',
    'precipitation',
    'snowfall',
    'snow_depth',
    'windspeed_10m',
    'winddirection_10m',
    'freezing_level_height',
)


@dataclass(frozen=True)
class HourlyWeatherSample:
    timestamp: str
    values: dict[str, float]


class TerrainUnavailableError(ValueError):
    """Raised when no physically defensible DEM window exists near a cell."""


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _clamp(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, value)))


def _normalize(value: float, scale: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return _clamp(value / scale, lower, upper)


def _fetch_open_meteo(url: str, *, params: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        response = None
        try:
            response = requests.get(
                url,
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
            time.sleep(max(2 ** attempt, retry_after))
    # All retries exhausted
    raise last_error or RuntimeError(f"Failed to fetch from {url} after {retries} attempts")


def _is_rate_limited(exc: Exception) -> bool:
    return getattr(getattr(exc, 'response', None), 'status_code', None) == 429


def _historical_archive_params(*, lat: float, lng: float, start_date: str, end_date: str) -> dict[str, Any]:
    return {
        'latitude': f'{lat:.4f}',
        'longitude': f'{lng:.4f}',
        'start_date': start_date,
        'end_date': end_date,
        'hourly': ','.join(ARCHIVE_HOURLY_VARS),
        'timezone': 'UTC',
    }


def _hourly_payload_to_samples(payload: dict[str, Any]) -> list[HourlyWeatherSample]:
    hourly = payload.get('hourly') or {}
    times = hourly.get('time') or []
    samples: list[HourlyWeatherSample] = []
    for idx, timestamp in enumerate(times):
        values: dict[str, float] = {}
        for key, series in hourly.items():
            if key == 'time' or not isinstance(series, list) or idx >= len(series):
                continue
            numeric = _safe_float(series[idx])
            if numeric is not None:
                values[key] = numeric
        samples.append(HourlyWeatherSample(timestamp=str(timestamp), values=values))
    return samples


def _nearest_sample(samples: list[HourlyWeatherSample], target: datetime) -> HourlyWeatherSample | None:
    if not samples:
        return None
    target = _to_utc(target)

    def _distance(sample: HourlyWeatherSample) -> float:
        sample_dt = datetime.fromisoformat(sample.timestamp.replace('Z', '+00:00'))
        if sample_dt.tzinfo is None:
            sample_dt = sample_dt.replace(tzinfo=timezone.utc)
        return abs((sample_dt - target).total_seconds())

    return min(samples, key=_distance)


def fetch_forecast_weather_profile(region_center: tuple[float, float], forecast_start: datetime, horizon_hours: int) -> dict[str, Any]:
    start = _to_utc(forecast_start)
    end = start + timedelta(hours=max(1, horizon_hours - 1))
    payload = _fetch_open_meteo(
        OPEN_METEO_FORECAST,
        params={
            'latitude': f'{region_center[0]:.4f}',
            'longitude': f'{region_center[1]:.4f}',
            'hourly': ','.join(ALL_HOURLY_VARS),
            'timezone': 'UTC',
            'forecast_days': max(1, math.ceil(((end - start).total_seconds() / 3600.0) / 24.0)),
        },
    )
    return {
        'source': 'open_meteo_forecast_downscaled_v1',
        'latitude': region_center[0],
        'longitude': region_center[1],
        'samples': _hourly_payload_to_samples(payload),
    }


def fetch_historical_weather_profile(lat: float, lng: float, timestamp: datetime) -> dict[str, Any]:
    target = _to_utc(timestamp)
    start_date = (target - timedelta(hours=12)).date().isoformat()
    end_date = (target + timedelta(hours=12)).date().isoformat()
    payload_source = 'open_meteo_historical_forecast_v1'
    try:
        payload = _fetch_open_meteo(
            OPEN_METEO_HISTORICAL_FORECAST,
            params={
                'latitude': f'{lat:.4f}',
                'longitude': f'{lng:.4f}',
                'start_date': start_date,
                'end_date': end_date,
                'hourly': ','.join(ALL_HOURLY_VARS),
                'timezone': 'UTC',
            },
        )
    except requests.HTTPError as exc:
        if not _is_rate_limited(exc):
            raise
        payload = _fetch_open_meteo(
            OPEN_METEO_ARCHIVE,
            params=_historical_archive_params(
                lat=lat,
                lng=lng,
                start_date=start_date,
                end_date=end_date,
            ),
        )
        payload_source = 'open_meteo_historical_archive_fallback_v1'
    samples = _hourly_payload_to_samples(payload)
    return {
        'source': payload_source,
        'latitude': lat,
        'longitude': lng,
        'samples': samples,
        'sample': _nearest_sample(samples, target),
    }


def fetch_historical_weather_window(lat: float, lng: float, start: datetime, end: datetime) -> dict[str, Any]:
    start_utc = _to_utc(start)
    end_utc = _to_utc(end)
    start_date = start_utc.date().isoformat()
    end_date = end_utc.date().isoformat()
    payload_source = 'open_meteo_historical_forecast_window_v1'
    try:
        payload = _fetch_open_meteo(
            OPEN_METEO_HISTORICAL_FORECAST,
            params={
                'latitude': f'{lat:.4f}',
                'longitude': f'{lng:.4f}',
                'start_date': start_date,
                'end_date': end_date,
                'hourly': ','.join(ALL_HOURLY_VARS),
                'timezone': 'UTC',
            },
        )
    except requests.HTTPError as exc:
        if not _is_rate_limited(exc):
            raise
        payload = _fetch_open_meteo(
            OPEN_METEO_ARCHIVE,
            params=_historical_archive_params(
                lat=lat,
                lng=lng,
                start_date=start_date,
                end_date=end_date,
            ),
        )
        payload_source = 'open_meteo_historical_archive_window_fallback_v1'
    return {
        'source': payload_source,
        'latitude': lat,
        'longitude': lng,
        'samples': _hourly_payload_to_samples(payload),
        'start': start_utc.isoformat(),
        'end': end_utc.isoformat(),
    }


def select_hourly_weather_sample(profile: dict[str, Any], target: datetime) -> dict[str, float]:
    sample = profile.get('sample')
    if sample is None:
        sample = _nearest_sample(profile.get('samples') or [], _to_utc(target))
    if sample is None:
        return {}
    return dict(sample.values)


def compute_dynamic_lapse_profile(profile: dict[str, float], terrain_elevation_m: float) -> dict[str, Any]:
    levels: list[dict[str, Any]] = []
    for level in PRESSURE_LEVELS:
        temp = _safe_float(profile.get(f'temperature_{level}'))
        height = _safe_float(profile.get(f'geopotential_height_{level}'))
        if temp is None or height is None:
            continue
        levels.append({'level': level, 'temperature_c': temp, 'height_m': height})

    if len(levels) < 2:
        return {
            'method': 'fallback_standard_lapse',
            'lapse_rate_c_per_m': STANDARD_LAPSE_RATE_C_PER_M,
            'lower_level': None,
            'upper_level': None,
            'is_inversion': False,
            'downscaled_temperature_c': _safe_float(profile.get('temperature_2m')),
        }

    levels = sorted(levels, key=lambda item: item['height_m'])
    lower = None
    upper = None
    for idx in range(len(levels) - 1):
        candidate_lower = levels[idx]
        candidate_upper = levels[idx + 1]
        if candidate_lower['height_m'] <= terrain_elevation_m <= candidate_upper['height_m']:
            lower, upper = candidate_lower, candidate_upper
            break

    if lower is None or upper is None:
        ordered = sorted(levels, key=lambda item: abs(item['height_m'] - terrain_elevation_m))
        lower, upper = sorted(ordered[:2], key=lambda item: item['height_m'])

    delta_height = upper['height_m'] - lower['height_m']
    if abs(delta_height) < 100:
        lapse_rate = STANDARD_LAPSE_RATE_C_PER_M
        method = 'fallback_standard_lapse'
    else:
        lapse_rate = (upper['temperature_c'] - lower['temperature_c']) / delta_height
        method = 'pressure_level_interpolation'

    offset = terrain_elevation_m - lower['height_m']
    downscaled_temperature = lower['temperature_c'] + offset * lapse_rate
    return {
        'method': method,
        'lapse_rate_c_per_m': lapse_rate,
        'lower_level': lower['level'],
        'upper_level': upper['level'],
        'is_inversion': lapse_rate > 0,
        'downscaled_temperature_c': downscaled_temperature,
    }


@lru_cache(maxsize=32)
def _dem_cache(dem_path: str) -> dict[str, Any]:
    import rasterio

    path = Path(dem_path)
    with rasterio.open(path) as dataset:
        array = dataset.read(1).astype('float64')
        transform = dataset.transform
        center_lon, center_lat = dataset.xy(dataset.height // 2, dataset.width // 2)
        px_deg_x = abs(transform.a)
        px_deg_y = abs(transform.e)
        px_size_x_m = px_deg_x * 111_320.0 * math.cos(math.radians(center_lat))
        px_size_y_m = px_deg_y * 110_540.0
        return {
            'array': array,
            'transform': transform,
            'px_size_x_m': px_size_x_m,
            'px_size_y_m': px_size_y_m,
            'height': dataset.height,
            'width': dataset.width,
            'nodata': dataset.nodata,
        }


def _window_is_valid(window: np.ndarray, nodata: float | None) -> bool:
    if nodata is not None and np.any(np.isclose(window, nodata)):
        return False
    return not np.isnan(window).any()


def _find_valid_window(
    array: np.ndarray,
    *,
    row: int,
    col: int,
    nodata: float | None,
    max_radius: int = 256,
    boundary_buffer: int = 2,
    px_size_x_m: float = 1.0,
    px_size_y_m: float = 1.0,
    max_search_distance_m: float | None = None,
) -> tuple[int, int, np.ndarray, int, bool, float]:
    height, width = array.shape
    if row < -boundary_buffer or row > height - 1 + boundary_buffer or col < -boundary_buffer or col > width - 1 + boundary_buffer:
        raise ValueError('Point lies too far outside the DEM coverage to clamp safely')
    clamped_row = max(1, min(height - 2, row))
    clamped_col = max(1, min(width - 2, col))
    adjusted = clamped_row != row or clamped_col != col
    effective_max_radius = max_radius
    if max_search_distance_m is not None:
        min_px = min(abs(px_size_x_m), abs(px_size_y_m))
        if min_px <= 0:
            raise ValueError('DEM pixel size must be positive')
        effective_max_radius = min(max_radius, max(0, int(math.ceil(max_search_distance_m / min_px))))

    for radius in range(0, effective_max_radius + 1):
        for d_row in range(-radius, radius + 1):
            for d_col in range(-radius, radius + 1):
                if max(abs(d_row), abs(d_col)) != radius:
                    continue
                sample_row = clamped_row + d_row
                sample_col = clamped_col + d_col
                if sample_row < 1 or sample_row >= height - 1 or sample_col < 1 or sample_col >= width - 1:
                    continue
                distance_m = math.hypot(abs(d_col) * px_size_x_m, abs(d_row) * px_size_y_m)
                if max_search_distance_m is not None and distance_m > max_search_distance_m:
                    continue
                window = array[sample_row - 1:sample_row + 2, sample_col - 1:sample_col + 2]
                if _window_is_valid(window, nodata):
                    return sample_row, sample_col, window, radius, adjusted, float(distance_m)

    raise ValueError('Unable to locate a valid 3x3 DEM window near the requested point')


@lru_cache(maxsize=512)
def _cached_snowpack_proxy(
    lat_round: float,
    lng_round: float,
    as_of_iso: str,
    snowfall_norm: float,
    wind_loading_norm: float,
    temp_gradient_norm: float,
    elevation_norm: float,
):
    return compute_cell_snowpack_proxy(
        lat=lat_round,
        lng=lng_round,
        as_of=datetime.fromisoformat(as_of_iso.replace('Z', '+00:00')),
        weather_inputs={
            'snowfall_24h': snowfall_norm,
            'wind_loading': wind_loading_norm,
            'temp_gradient': temp_gradient_norm,
        },
        terrain_inputs={'elevation': elevation_norm},
    )


def extract_cell_terrain(
    dem_path: str,
    lat: float,
    lng: float,
    *,
    max_search_distance_m: float | None = None,
) -> dict[str, float]:
    cache = _dem_cache(dem_path)
    array = cache['array']
    transform = cache['transform']
    px_size_x_m = cache['px_size_x_m']
    px_size_y_m = cache['px_size_y_m']
    strict_radius_m = DEM_MAX_SEARCH_DISTANCE_M if max_search_distance_m is None else max_search_distance_m

    col_f, row_f = (~transform) * (lng, lat)
    try:
        row, col, win, search_radius, adjusted, search_distance_m = _find_valid_window(
            array,
            row=int(round(row_f)),
            col=int(round(col_f)),
            nodata=cache['nodata'],
            px_size_x_m=px_size_x_m,
            px_size_y_m=px_size_y_m,
            max_search_distance_m=strict_radius_m,
        )
    except ValueError as exc:
        raise TerrainUnavailableError(
            f'No valid DEM window found within {strict_radius_m:.1f}m of ({lat:.5f}, {lng:.5f}) in {dem_path}'
        ) from exc
    nodata = cache['nodata']

    dzdx = ((win[0, 2] + 2 * win[1, 2] + win[2, 2]) - (win[0, 0] + 2 * win[1, 0] + win[2, 0])) / (8.0 * px_size_x_m)
    dzdy = ((win[2, 0] + 2 * win[2, 1] + win[2, 2]) - (win[0, 0] + 2 * win[0, 1] + win[0, 2])) / (8.0 * px_size_y_m)
    rise_run = math.hypot(dzdx, dzdy)
    slope_deg = math.degrees(math.atan(rise_run))
    aspect_deg = math.degrees(math.atan2(dzdy, -dzdx))
    if aspect_deg < 0:
        aspect_deg += 360.0

    terrain_roughness = float(np.std(win))
    center = float(win[1, 1])
    curvature_proxy = abs(float((win[0, 1] + win[1, 0] + win[1, 2] + win[2, 1]) / 4.0 - center))

    return {
        'elevation_m': center,
        'slope_angle_deg': slope_deg,
        'aspect_deg': aspect_deg,
        'terrain_roughness': terrain_roughness,
        'curvature_proxy': curvature_proxy,
        'northness': (1 + math.cos(math.radians(aspect_deg))) / 2,
        'eastness': (1 + math.sin(math.radians(aspect_deg))) / 2,
        'sample_row': float(row),
        'sample_col': float(col),
        'clamped_to_bounds': float(1 if adjusted else 0),
        'window_search_needed': float(1 if search_radius > 0 else 0),
        'search_radius_px': float(search_radius),
        'search_radius_m': float(search_distance_m),
        'max_search_radius_m': float(strict_radius_m),
    }


def build_real_feature_row(
    *,
    weather_sample: dict[str, float],
    terrain: dict[str, float],
    timestamp: datetime,
    lat: float,
    lng: float,
    snowpack_proxy_override: SnowpackProxy | None = None,
) -> dict[str, Any]:
    terrain_elevation = float(terrain['elevation_m'])
    lapse = compute_dynamic_lapse_profile(weather_sample, terrain_elevation_m=terrain_elevation)
    downscaled_temp_c = _safe_float(lapse.get('downscaled_temperature_c'))
    if downscaled_temp_c is None:
        downscaled_temp_c = _safe_float(weather_sample.get('temperature_2m')) or 0.0

    wind_speed = _safe_float(weather_sample.get('windspeed_10m')) or 0.0
    wind_direction = _safe_float(weather_sample.get('winddirection_10m')) or 0.0
    snowfall_24h_cm = max(0.0, _safe_float(weather_sample.get('snowfall_24h')) or _safe_float(weather_sample.get('snowfall')) or 0.0)
    precipitation_24h_mm = max(0.0, _safe_float(weather_sample.get('precipitation_24h')) or _safe_float(weather_sample.get('precipitation')) or 0.0)
    snow_depth_cm = max(0.0, (_safe_float(weather_sample.get('snow_depth')) or 0.0) * 100.0)
    freezing_level_height = _safe_float(weather_sample.get('freezing_level_height'))
    if freezing_level_height is None:
        surface_temp = _safe_float(weather_sample.get('temperature_2m')) or downscaled_temp_c
        lapse_rate = lapse['lapse_rate_c_per_m'] if abs(lapse['lapse_rate_c_per_m']) > 1e-6 else STANDARD_LAPSE_RATE_C_PER_M
        freezing_level_height = terrain_elevation if surface_temp == 0 else max(0.0, terrain_elevation - surface_temp / lapse_rate)

    aspect_deg = float(terrain['aspect_deg'])
    directional_cos = (math.cos(math.radians(wind_direction - aspect_deg)) + 1.0) / 2.0
    directional_multiplier = _clamp(0.5 + directional_cos, 0.5, 1.5)
    wind_loading_raw = wind_speed * directional_multiplier

    temp_gradient_norm = _clamp((lapse['lapse_rate_c_per_m'] + 0.01) / 0.02, 0.0, 1.0)
    wind_loading_norm = _normalize(wind_loading_raw, 55.0)
    elevation_norm = _normalize(terrain_elevation, 5000.0)

    if snowpack_proxy_override is not None:
        snowpack_proxy = snowpack_proxy_override
    else:
        snowpack_proxy = _cached_snowpack_proxy(
            round(lat, 3),
            round(lng, 3),
            _to_utc(timestamp).isoformat(),
            _normalize(snowfall_24h_cm, 40.0),
            wind_loading_norm,
            temp_gradient_norm,
            elevation_norm,
        )

    shear_strength_norm = _clamp(snowpack_proxy.estimated_shear_strength / 12.0, 0.0, 1.0)
    settlement_rate_norm = _clamp(snowpack_proxy.snow_settlement_index, 0.0, 1.0)
    freezing_level_margin_m = terrain_elevation - float(freezing_level_height)
    freezing_level_margin_norm = _clamp((freezing_level_margin_m + 1000.0) / 2000.0, 0.0, 1.0)
    cold_support = _clamp(max(0.0, -downscaled_temp_c) / 8.0, 0.0, 1.0)
    elevation_precip_bias_factor = 1.0 + _clamp(
        (terrain_elevation - 1500.0) / 3000.0 * 0.2 + cold_support * 0.15,
        0.0,
        0.35,
    )
    elevation_precip_bias_norm = _clamp((elevation_precip_bias_factor - 1.0) / 0.35, 0.0, 1.0)
    adjusted_precipitation_24h_mm = precipitation_24h_mm * elevation_precip_bias_factor
    adjusted_snowfall_24h_cm = snowfall_24h_cm * elevation_precip_bias_factor
    seasonal_snow_support = str(getattr(snowpack_proxy, 'method', '')) == 'seasonal_cumulative_v1'
    snow_evidence = bool(snow_depth_cm >= 10.0 or adjusted_snowfall_24h_cm >= 5.0 or seasonal_snow_support)
    rain_on_snow_signal = float(
        precipitation_24h_mm > 3.0 and downscaled_temp_c > 0.0 and snow_evidence
    )
    wet_activation_signal = _clamp(
        max(
            rain_on_snow_signal,
            max(0.0, 1.0 - freezing_level_margin_norm) * _clamp(snow_depth_cm / 80.0, 0.0, 1.0),
        ),
        0.0,
        1.0,
    )
    loading_signal = (
        _normalize(adjusted_snowfall_24h_cm, 40.0) * 0.45
        + _normalize(adjusted_precipitation_24h_mm, 45.0) * 0.2
        + wind_loading_norm * 0.25
        + elevation_precip_bias_norm * 0.1
    )
    load_to_shear_ratio = _clamp(loading_signal / max(shear_strength_norm, 0.08), 0.0, 1.0)
    settlement_deficit = _clamp(1.0 - settlement_rate_norm, 0.0, 1.0)

    feature_row = {
        'snowfall_24h': _normalize(snowfall_24h_cm, 40.0),
        'precipitation_24h': _normalize(precipitation_24h_mm, 45.0),
        'wind_loading': wind_loading_norm,
        'wind_directional_loading': _clamp(directional_cos, 0.0, 1.0),
        'slope': _normalize(float(terrain['slope_angle_deg']), 60.0),
        'elevation': elevation_norm,
        'temp_gradient': temp_gradient_norm,
        'freezing_level_proxy': _normalize(float(freezing_level_height), 5000.0),
        'snowpack': _normalize(snow_depth_cm, 60.0),
        'ram_hardness': shear_strength_norm,
        'shear_strength': shear_strength_norm,
        'settlement_rate': settlement_rate_norm,
        'aspect_loading': _clamp(directional_multiplier / 1.5, 0.0, 1.0),
        'terrain_roughness': _normalize(float(terrain['terrain_roughness']), 150.0),
        'curvature_proxy': _normalize(float(terrain['curvature_proxy']), 50.0),
        'northness': _clamp(float(terrain['northness']), 0.0, 1.0),
        'eastness': _clamp(float(terrain['eastness']), 0.0, 1.0),
        'freezing_level_margin': freezing_level_margin_norm,
        'load_to_shear_ratio': load_to_shear_ratio,
        'settlement_deficit': settlement_deficit,
        'rain_on_snow_signal': rain_on_snow_signal,
        'wet_activation_signal': wet_activation_signal,
        'elevation_precip_bias': elevation_precip_bias_norm,
    }

    raw_inputs = {
        'temperature_2m': _safe_float(weather_sample.get('temperature_2m')) or downscaled_temp_c,
        'downscaled_temperature_c': downscaled_temp_c,
        'snowfall_24h_cm': snowfall_24h_cm,
        'elevation_adjusted_snowfall_24h_cm': adjusted_snowfall_24h_cm,
        'precipitation_24h_mm': precipitation_24h_mm,
        'elevation_adjusted_precipitation_24h_mm': adjusted_precipitation_24h_mm,
        'windspeed_10m': wind_speed,
        'winddirection_10m': wind_direction,
        'freezing_level_height': float(freezing_level_height),
        'freezing_level_margin_m': float(freezing_level_margin_m),
        'lapse_rate_c_per_m': float(lapse['lapse_rate_c_per_m']),
        'terrain_elevation_m': terrain_elevation,
        'terrain_slope_deg': float(terrain['slope_angle_deg']),
        'terrain_aspect_deg': aspect_deg,
        'snow_depth_cm': snow_depth_cm,
        'elevation_precip_bias_factor': elevation_precip_bias_factor,
        'load_to_shear_ratio': load_to_shear_ratio,
        'settlement_deficit': settlement_deficit,
        'rain_on_snow_signal': rain_on_snow_signal,
        'wet_activation_signal': wet_activation_signal,
        'snowpack_proxy_method': snowpack_proxy.method,
    }

    return {
        'feature_row': feature_row,
        'raw_inputs': raw_inputs,
        'lapse': lapse,
        'terrain': terrain,
        'snowpack_proxy': snowpack_proxy,
    }
