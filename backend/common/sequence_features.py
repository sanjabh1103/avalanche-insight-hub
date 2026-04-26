from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from backend.common.real_features import (
    compute_dynamic_lapse_profile,
    fetch_historical_weather_window,
)


DEFAULT_HOURLY_STEPS = 24
DEFAULT_DAILY_STEPS = 7

DYNAMIC_SEQUENCE_FEATURES = [
    'snowfall_24h',
    'precipitation_24h',
    'wind_loading',
    'wind_directional_loading',
    'temp_gradient',
    'freezing_level_proxy',
]

STATIC_SEQUENCE_FEATURES = [
    'slope',
    'elevation',
    'aspect_loading',
    'terrain_roughness',
    'curvature_proxy',
    'northness',
    'eastness',
    'ram_hardness',
    'shear_strength',
    'settlement_rate',
]


@dataclass(frozen=True)
class SequenceBranches:
    hourly: np.ndarray
    daily: np.ndarray
    static: np.ndarray


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    if not np.isfinite(numeric):
        return fallback
    return numeric


def _clamp(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, value)))


def _normalize(value: float, scale: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return _clamp(value / scale, lower, upper)


def _to_utc(value: datetime | str | pd.Timestamp) -> datetime:
    if isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def infer_terrain_payload(row: pd.Series | dict[str, Any]) -> dict[str, float]:
    data = row if isinstance(row, dict) else row.to_dict()
    slope_angle_deg = _safe_float(data.get('slope_angle_deg_raw'), _safe_float(data.get('slope'), 0.0) * 60.0)
    elevation_m = _safe_float(data.get('elevation_m_raw'), _safe_float(data.get('elevation'), 0.0) * 5000.0)
    terrain_roughness = _safe_float(data.get('terrain_roughness_raw'), _safe_float(data.get('terrain_roughness'), 0.0) * 150.0)
    curvature_proxy = _safe_float(data.get('curvature_proxy_raw'), _safe_float(data.get('curvature_proxy'), 0.0) * 50.0)
    northness = _clamp(_safe_float(data.get('northness'), 0.5), 0.0, 1.0)
    eastness = _clamp(_safe_float(data.get('eastness'), 0.5), 0.0, 1.0)
    aspect_deg = _safe_float(data.get('aspect_deg_raw'))
    if not np.isfinite(aspect_deg) or aspect_deg == 0.0 and 'aspect_deg_raw' not in data:
        aspect_rad = float(np.arctan2((eastness * 2.0) - 1.0, (northness * 2.0) - 1.0))
        aspect_deg = (np.degrees(aspect_rad) + 360.0) % 360.0

    return {
        'elevation_m': elevation_m,
        'slope_angle_deg': slope_angle_deg,
        'aspect_deg': aspect_deg,
        'terrain_roughness': terrain_roughness,
        'curvature_proxy': curvature_proxy,
        'northness': northness,
        'eastness': eastness,
    }


def extract_static_vector(
    row: pd.Series | dict[str, Any],
    *,
    static_features: list[str] | None = None,
) -> np.ndarray:
    features = static_features or STATIC_SEQUENCE_FEATURES
    data = row if isinstance(row, dict) else row.to_dict()
    return np.asarray([_safe_float(data.get(feature)) for feature in features], dtype=np.float32)


def _dynamic_feature_snapshot(weather_sample: dict[str, Any], terrain: dict[str, float]) -> dict[str, float]:
    terrain_elevation = float(terrain['elevation_m'])
    lapse = compute_dynamic_lapse_profile(weather_sample, terrain_elevation_m=terrain_elevation)
    surface_temp = _safe_float(weather_sample.get('temperature_2m'))
    downscaled_temp = _safe_float(lapse.get('downscaled_temperature_c'), surface_temp)
    if downscaled_temp == 0.0 and surface_temp is not None:
        downscaled_temp = surface_temp

    wind_speed = _safe_float(weather_sample.get('windspeed_10m'))
    wind_direction = _safe_float(weather_sample.get('winddirection_10m'))
    snowfall_cm = max(0.0, _safe_float(weather_sample.get('snowfall_24h'), _safe_float(weather_sample.get('snowfall'))))
    precipitation_mm = max(0.0, _safe_float(weather_sample.get('precipitation_24h'), _safe_float(weather_sample.get('precipitation'))))
    freezing_level_height = _safe_float(weather_sample.get('freezing_level_height'))
    if freezing_level_height == 0.0:
        lapse_rate = float(lapse.get('lapse_rate_c_per_m') or -0.0065)
        if abs(lapse_rate) < 1e-6:
            lapse_rate = -0.0065
        temp_for_freezing = surface_temp if surface_temp is not None else downscaled_temp
        freezing_level_height = max(0.0, terrain_elevation - temp_for_freezing / lapse_rate) if temp_for_freezing != 0.0 else terrain_elevation

    aspect_deg = float(terrain['aspect_deg'])
    directional_cos = (np.cos(np.radians(wind_direction - aspect_deg)) + 1.0) / 2.0
    directional_multiplier = _clamp(0.5 + directional_cos, 0.5, 1.5)
    wind_loading_raw = wind_speed * directional_multiplier

    return {
        'snowfall_24h': _normalize(snowfall_cm, 40.0),
        'precipitation_24h': _normalize(precipitation_mm, 45.0),
        'wind_loading': _normalize(wind_loading_raw, 55.0),
        'wind_directional_loading': _clamp(float(directional_cos), 0.0, 1.0),
        'temp_gradient': _clamp((float(lapse.get('lapse_rate_c_per_m') or -0.0065) + 0.01) / 0.02, 0.0, 1.0),
        'freezing_level_proxy': _normalize(float(freezing_level_height), 5000.0),
    }


def _hourly_sample_dicts(samples: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for sample in samples:
        if isinstance(sample, dict):
            payload = dict(sample)
        else:
            payload = {
                'timestamp': getattr(sample, 'timestamp', None),
                **dict(getattr(sample, 'values', {}) or {}),
            }
        if payload:
            normalized.append(payload)
    return normalized


def _pad_sequence(sequence: list[dict[str, float]], *, length: int) -> list[dict[str, float]]:
    if not sequence:
        zero = {feature: 0.0 for feature in DYNAMIC_SEQUENCE_FEATURES}
        return [zero.copy() for _ in range(length)]
    if len(sequence) >= length:
        return sequence[-length:]
    zero = {feature: 0.0 for feature in DYNAMIC_SEQUENCE_FEATURES}
    pad = [zero.copy() for _ in range(length - len(sequence))]
    return pad + sequence


def _aggregate_daily_samples(samples: list[dict[str, Any]], *, length: int) -> list[dict[str, Any]]:
    daily: dict[str, dict[str, list[float]]] = {}
    for sample in samples:
        timestamp_raw = sample.get('timestamp')
        if not timestamp_raw:
            continue
        day_key = _to_utc(timestamp_raw).date().isoformat()
        bucket = daily.setdefault(day_key, {})
        for key, value in sample.items():
            if key == 'timestamp':
                continue
            bucket.setdefault(key, []).append(_safe_float(value))

    ordered_days = sorted(daily.keys())
    aggregated: list[dict[str, Any]] = []
    for day_key in ordered_days[-length:]:
        bucket = daily[day_key]
        aggregated.append({
            'timestamp': f'{day_key}T12:00:00+00:00',
            'temperature_2m': float(np.mean(bucket.get('temperature_2m', [0.0]))),
            'snowfall_24h': float(np.sum(bucket.get('snowfall', bucket.get('snowfall_24h', [0.0])))),
            'precipitation_24h': float(np.sum(bucket.get('precipitation', bucket.get('precipitation_24h', [0.0])))),
            'windspeed_10m': float(np.mean(bucket.get('windspeed_10m', [0.0]))),
            'winddirection_10m': float(np.mean(bucket.get('winddirection_10m', [0.0]))),
            'freezing_level_height': float(np.mean(bucket.get('freezing_level_height', [0.0]))),
            'snow_depth': float(np.mean(bucket.get('snow_depth', [0.0]))),
            'temperature_925hPa': float(np.mean(bucket.get('temperature_925hPa', [0.0]))),
            'temperature_850hPa': float(np.mean(bucket.get('temperature_850hPa', [0.0]))),
            'temperature_700hPa': float(np.mean(bucket.get('temperature_700hPa', [0.0]))),
            'geopotential_height_925hPa': float(np.mean(bucket.get('geopotential_height_925hPa', [0.0]))),
            'geopotential_height_850hPa': float(np.mean(bucket.get('geopotential_height_850hPa', [0.0]))),
            'geopotential_height_700hPa': float(np.mean(bucket.get('geopotential_height_700hPa', [0.0]))),
        })
    if not aggregated:
        return [{
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'temperature_2m': 0.0,
            'snowfall_24h': 0.0,
            'precipitation_24h': 0.0,
            'windspeed_10m': 0.0,
            'winddirection_10m': 0.0,
            'freezing_level_height': 0.0,
            'snow_depth': 0.0,
        }] * length
    if len(aggregated) < length:
        first_timestamp = _to_utc(aggregated[0]['timestamp'])
        zero_template = {key: 0.0 for key in aggregated[0] if key != 'timestamp'}
        pad = [
            {
                'timestamp': (first_timestamp - timedelta(days=offset)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat(),
                **zero_template,
            }
            for offset in range(length - len(aggregated), 0, -1)
        ]
        aggregated = pad + aggregated
    return aggregated[-length:]


def sequence_matrix_from_samples(
    *,
    hourly_samples: list[Any],
    daily_samples: list[Any],
    terrain: dict[str, float],
    dynamic_features: list[str] | None = None,
    hourly_steps: int = DEFAULT_HOURLY_STEPS,
    daily_steps: int = DEFAULT_DAILY_STEPS,
) -> tuple[np.ndarray, np.ndarray]:
    feature_names = dynamic_features or DYNAMIC_SEQUENCE_FEATURES
    normalized_hourly = _hourly_sample_dicts(hourly_samples)
    normalized_daily = _hourly_sample_dicts(daily_samples)

    hourly_vectors = [
        _dynamic_feature_snapshot(sample, terrain)
        for sample in _pad_sequence(normalized_hourly, length=hourly_steps)
    ]
    daily_vectors = [
        _dynamic_feature_snapshot(sample, terrain)
        for sample in _aggregate_daily_samples(normalized_daily, length=daily_steps)
    ]

    hourly_matrix = np.asarray(
        [[float(vector.get(feature, 0.0)) for feature in feature_names] for vector in hourly_vectors],
        dtype=np.float32,
    )
    daily_matrix = np.asarray(
        [[float(vector.get(feature, 0.0)) for feature in feature_names] for vector in daily_vectors],
        dtype=np.float32,
    )
    return hourly_matrix, daily_matrix


@lru_cache(maxsize=512)
def _cached_historical_window(
    lat_round: float,
    lng_round: float,
    start_iso: str,
    end_iso: str,
) -> dict[str, Any]:
    return fetch_historical_weather_window(
        lat=lat_round,
        lng=lng_round,
        start=_to_utc(start_iso),
        end=_to_utc(end_iso),
    )


def build_training_branch_arrays(
    frame: pd.DataFrame,
    *,
    region_centers: dict[str, tuple[float, float]],
    dynamic_features: list[str] | None = None,
    static_features: list[str] | None = None,
    hourly_steps: int = DEFAULT_HOURLY_STEPS,
    daily_steps: int = DEFAULT_DAILY_STEPS,
) -> SequenceBranches:
    feature_names = dynamic_features or DYNAMIC_SEQUENCE_FEATURES
    static_names = static_features or STATIC_SEQUENCE_FEATURES

    hourly_rows: list[np.ndarray] = []
    daily_rows: list[np.ndarray] = []
    static_rows: list[np.ndarray] = []

    for _, row in frame.iterrows():
        region_key = str(row.get('region_key') or '')
        center_lat, center_lng = region_centers.get(region_key, (float(row.get('lat', 0.0)), float(row.get('lng', 0.0))))
        timestamp = _to_utc(row['timestamp'])
        history_start = (timestamp - timedelta(days=max(daily_steps, 1))).replace(minute=0, second=0, microsecond=0)
        history_end = timestamp.replace(minute=0, second=0, microsecond=0)
        window_profile = _cached_historical_window(
            round(center_lat, 3),
            round(center_lng, 3),
            history_start.isoformat(),
            history_end.isoformat(),
        )
        samples = _hourly_sample_dicts(window_profile.get('samples') or [])
        terrain = infer_terrain_payload(row)
        hourly_matrix, daily_matrix = sequence_matrix_from_samples(
            hourly_samples=samples[-hourly_steps:],
            daily_samples=samples,
            terrain=terrain,
            dynamic_features=feature_names,
            hourly_steps=hourly_steps,
            daily_steps=daily_steps,
        )
        hourly_rows.append(hourly_matrix)
        daily_rows.append(daily_matrix)
        static_rows.append(extract_static_vector(row, static_features=static_names))

    return SequenceBranches(
        hourly=np.asarray(hourly_rows, dtype=np.float32),
        daily=np.asarray(daily_rows, dtype=np.float32),
        static=np.asarray(static_rows, dtype=np.float32),
    )


def build_inference_branches(
    *,
    terrain: dict[str, float],
    static_feature_row: dict[str, float],
    forecast_samples: list[Any],
    history_samples: list[Any],
    dynamic_features: list[str] | None = None,
    static_features: list[str] | None = None,
    hourly_steps: int = DEFAULT_HOURLY_STEPS,
    daily_steps: int = DEFAULT_DAILY_STEPS,
) -> SequenceBranches:
    feature_names = dynamic_features or DYNAMIC_SEQUENCE_FEATURES
    static_names = static_features or STATIC_SEQUENCE_FEATURES
    hourly_matrix, daily_matrix = sequence_matrix_from_samples(
        hourly_samples=forecast_samples[:hourly_steps],
        daily_samples=history_samples,
        terrain=terrain,
        dynamic_features=feature_names,
        hourly_steps=hourly_steps,
        daily_steps=daily_steps,
    )
    static_vector = extract_static_vector(static_feature_row, static_features=static_names)
    return SequenceBranches(hourly=hourly_matrix, daily=daily_matrix, static=static_vector)
