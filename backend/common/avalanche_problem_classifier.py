from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from backend.common.timezone_utils import resolve_zoneinfo

PROBLEM_CLASSIFIER_PROFILE = 'avalanche_problem_rules_v1'
PROBLEM_LABELS: dict[str, str] = {
    'new_snow': 'New Snow',
    'wind_slab': 'Wind Slab',
    'persistent_weak_layers': 'Persistent Weak Layers',
    'wet_snow': 'Wet Snow',
    'gliding_snow': 'Gliding Snow',
    'no_distinct_avalanche_problem': 'No Distinct Avalanche Problem',
    'unknown': 'Unknown',
}


def _as_finite_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return None


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _seasonal_snow_support(snowpack_proxy: dict[str, Any]) -> bool:
    method = str(snowpack_proxy.get('method') or '')
    shear = _as_finite_float(snowpack_proxy.get('estimated_shear_strength'))
    settlement = _as_finite_float(snowpack_proxy.get('snow_settlement_index'))
    return method == 'seasonal_cumulative_v1' and shear is not None and settlement is not None


def _snow_evidence(
    *,
    snow_depth_cm: float | None,
    snowfall_24h_cm: float,
    seasonal_snow_support: bool,
) -> bool:
    return bool((snow_depth_cm or 0.0) >= 10.0 or snowfall_24h_cm >= 5.0 or seasonal_snow_support)


def _rain_on_snow_proxy(
    *,
    precipitation_24h_mm: float,
    downscaled_temperature_c: float | None,
    snow_depth_cm: float | None,
    seasonal_snow_support: bool,
) -> bool:
    return bool(
        precipitation_24h_mm > 3.0
        and (downscaled_temperature_c or 0.0) > 0.0
        and ((snow_depth_cm or 0.0) >= 10.0 or seasonal_snow_support)
    )


def _sun_warming_window(local_hour: int, aspect_deg: float | None) -> bool:
    if aspect_deg is None:
        return 9 <= local_hour < 17
    normalized = aspect_deg % 360.0
    if 45.0 <= normalized < 135.0:
        return 7 <= local_hour < 14
    if 135.0 <= normalized < 225.0:
        return 9 <= local_hour < 16
    if 225.0 <= normalized < 315.0:
        return 11 <= local_hour < 18
    return 12 <= local_hour < 16


def _result(
    *,
    slug: str,
    confidence: float,
    evidence: list[str],
    dry_wet_domain: str,
) -> dict[str, object]:
    return {
        'problem_slug': slug,
        'problem_type': PROBLEM_LABELS.get(slug, PROBLEM_LABELS['unknown']),
        'problem_confidence': round(confidence, 3),
        'problem_evidence': evidence,
        'problem_classifier_profile': PROBLEM_CLASSIFIER_PROFILE,
        'dry_wet_domain': dry_wet_domain,
    }


def classify_avalanche_problem(
    *,
    weather_inputs: dict[str, Any],
    terrain_inputs: dict[str, Any],
    snowpack_proxy: dict[str, Any] | None,
    forecast_time: datetime,
    timezone_name: str,
) -> dict[str, object]:
    snowpack_proxy = _as_dict(snowpack_proxy)
    weather_inputs = _as_dict(weather_inputs)
    terrain_inputs = _as_dict(terrain_inputs)

    downscaled_temperature_c = _as_finite_float(weather_inputs.get('downscaled_temperature_c'))
    snowfall_24h_cm = _as_finite_float(weather_inputs.get('snowfall_24h_cm')) or 0.0
    precipitation_24h_mm = _as_finite_float(weather_inputs.get('precipitation_24h_mm')) or 0.0
    snow_depth_cm = _as_finite_float(weather_inputs.get('snow_depth_cm'))
    wind_loading = _as_finite_float(weather_inputs.get('wind_loading')) or 0.0
    aspect_loading = _as_finite_float(terrain_inputs.get('aspect_loading')) or 0.0
    aspect_deg = _as_finite_float(terrain_inputs.get('aspect_deg'))
    estimated_shear_strength = _as_finite_float(snowpack_proxy.get('estimated_shear_strength'))
    snow_settlement_index = _as_finite_float(snowpack_proxy.get('snow_settlement_index'))

    seasonal_snow_support = _seasonal_snow_support(snowpack_proxy)
    snow_evidence = _snow_evidence(
        snow_depth_cm=snow_depth_cm,
        snowfall_24h_cm=snowfall_24h_cm,
        seasonal_snow_support=seasonal_snow_support,
    )
    rain_on_snow = _rain_on_snow_proxy(
        precipitation_24h_mm=precipitation_24h_mm,
        downscaled_temperature_c=downscaled_temperature_c,
        snow_depth_cm=snow_depth_cm,
        seasonal_snow_support=seasonal_snow_support,
    )

    zone, _resolved_timezone_name, timezone_fallback = resolve_zoneinfo(timezone_name)
    timezone_evidence = ['timezone_fallback_to_utc'] if timezone_fallback else []
    local_time = _to_aware_utc(forecast_time).astimezone(zone)
    local_hour = local_time.hour
    local_warming = bool(
        snow_evidence
        and (downscaled_temperature_c or 0.0) > 0.0
        and _sun_warming_window(local_hour, aspect_deg)
    )

    if rain_on_snow or local_warming:
        evidence = ['snow_evidence_present']
        if rain_on_snow:
            evidence.append('rain_on_snow_proxy')
        if local_warming:
            evidence.append('heuristic_local_daytime_warming')
        evidence.extend(timezone_evidence)
        return _result(
            slug='wet_snow',
            confidence=0.82 if rain_on_snow else 0.68,
            evidence=evidence,
            dry_wet_domain='wet',
        )

    wind_signal = wind_loading >= 0.55 and aspect_loading >= 0.6
    transportable_snow = snowfall_24h_cm >= 3.0 or (snow_depth_cm or 0.0) >= 10.0 or seasonal_snow_support
    if wind_signal and transportable_snow:
        return _result(
            slug='wind_slab',
            confidence=0.79,
            evidence=['transportable_snow', 'elevated_wind_loading', 'elevated_aspect_loading', *timezone_evidence],
            dry_wet_domain='dry',
        )

    if snowfall_24h_cm >= 5.0 and (downscaled_temperature_c or 0.0) <= 1.5:
        return _result(
            slug='new_snow',
            confidence=0.74,
            evidence=['recent_cold_snowfall', *timezone_evidence],
            dry_wet_domain='dry',
        )

    if (
        seasonal_snow_support
        and estimated_shear_strength is not None
        and snow_settlement_index is not None
        and estimated_shear_strength <= 4.0
        and snow_settlement_index <= 0.35
    ):
        return _result(
            slug='persistent_weak_layers',
            confidence=0.38,
            evidence=['seasonal_snow_support', 'low_shear_strength', 'low_settlement_index', *timezone_evidence],
            dry_wet_domain='dry',
        )

    return _result(
        slug='no_distinct_avalanche_problem',
        confidence=0.2,
        evidence=['no_strong_problem_signal', *timezone_evidence],
        dry_wet_domain='unknown',
    )
