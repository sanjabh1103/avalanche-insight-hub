from __future__ import annotations

import math
from typing import Any

from backend.common.avalanche_prone_terrain import is_apt_eligible_slope, slope_from_cell

SNOW_ELEVATION_PROFILE = 'snow_elevation_proxy_v1'
PUBLIC_ELIGIBILITY_PROFILE = 'apt_then_snow_elevation_public_eligible_v1'
_APT_PROFILE_NAME = 'apt_30_50_v1'
_SNOW_DEPTH_POSITIVE_CM = 10.0
_SNOW_DEPTH_NEGATIVE_CM = 2.0
_SNOWFALL_POSITIVE_CM = 5.0
_RAIN_ON_SNOW_PRECIP_MM = 3.0
_COLD_SNOW_TEMP_C = 1.5
_WARM_NEGATIVE_TEMP_C = 2.0
_DRY_SNOWLINE_OFFSET_M = 300.0
_SEASONAL_SNOWLINE_OFFSET_M = 500.0
_LOW_ELEVATION_BUFFER_M = 200.0
_LOW_CONFIDENCE_RELEVANCE_SCORE = 0.25


def _as_finite_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return None


def _as_risk_score(value: object) -> int:
    if isinstance(value, (int, float)):
        numeric = int(value)
        if numeric > 0:
            return numeric
    return 0


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _seasonal_snow_support(snowpack_proxy: dict[str, Any]) -> bool:
    if str(snowpack_proxy.get('method') or '') != 'seasonal_cumulative_v1':
        return False
    shear = _as_finite_float(snowpack_proxy.get('estimated_shear_strength'))
    settlement = _as_finite_float(snowpack_proxy.get('snow_settlement_index'))
    return shear is not None and settlement is not None


def snow_elevation_inputs(cell: dict[str, Any]) -> dict[str, Any]:
    weather_inputs = _as_dict(cell.get('weather_inputs'))
    terrain_inputs = _as_dict(cell.get('terrain_inputs'))
    snowpack_proxy = _as_dict(cell.get('snowpack_proxy'))
    elevation_m = _as_finite_float(terrain_inputs.get('elevation_m'))
    freezing_level_height_m = _as_finite_float(
        weather_inputs.get('freezing_level_height_m')
        if 'freezing_level_height_m' in weather_inputs
        else weather_inputs.get('freezing_level_height')
    )
    snow_depth_cm = _as_finite_float(weather_inputs.get('snow_depth_cm'))
    snowfall_24h_cm = _as_finite_float(weather_inputs.get('snowfall_24h_cm')) or 0.0
    precipitation_24h_mm = _as_finite_float(weather_inputs.get('precipitation_24h_mm')) or 0.0
    downscaled_temperature_c = _as_finite_float(weather_inputs.get('downscaled_temperature_c'))
    seasonal_support = _seasonal_snow_support(snowpack_proxy)
    observed_snow_support = (snow_depth_cm or 0.0) >= _SNOW_DEPTH_POSITIVE_CM
    snow_evidence = observed_snow_support or seasonal_support
    rain_on_snow_proxy = bool(
        precipitation_24h_mm > _RAIN_ON_SNOW_PRECIP_MM
        and (downscaled_temperature_c or 0.0) > 0.0
        and snow_evidence
    )
    proxy_snowline_m = (
        freezing_level_height_m - _DRY_SNOWLINE_OFFSET_M
        if freezing_level_height_m is not None
        else None
    )
    return {
        'elevation_m': elevation_m,
        'freezing_level_height_m': freezing_level_height_m,
        'snow_depth_cm': snow_depth_cm,
        'snowfall_24h_cm': snowfall_24h_cm,
        'precipitation_24h_mm': precipitation_24h_mm,
        'downscaled_temperature_c': downscaled_temperature_c,
        'seasonal_snow_support': seasonal_support,
        'observed_snow_support': observed_snow_support,
        'snow_evidence': snow_evidence,
        'rain_on_snow_proxy': rain_on_snow_proxy,
        'proxy_snowline_m': proxy_snowline_m,
    }


def evaluate_snow_elevation_eligibility(cell: dict[str, Any]) -> dict[str, Any]:
    status = str(cell.get('status') or '')
    if status != 'ready':
        return {
            'snow_elevation_eligible': False,
            'snow_elevation_profile': SNOW_ELEVATION_PROFILE,
            'snow_elevation_mask_reason': None,
            'snow_relevance_score': 0.0,
            'snow_relevance_basis': [],
            'rain_on_snow_proxy': False,
            'wet_snow_eligible': False,
        }

    inputs = snow_elevation_inputs(cell)
    elevation_m = inputs['elevation_m']
    freezing_level_height_m = inputs['freezing_level_height_m']
    snow_depth_cm = inputs['snow_depth_cm']
    snowfall_24h_cm = inputs['snowfall_24h_cm']
    precipitation_24h_mm = inputs['precipitation_24h_mm']
    downscaled_temperature_c = inputs['downscaled_temperature_c']
    seasonal_support = inputs['seasonal_snow_support']
    observed_snow_support = inputs['observed_snow_support']
    rain_on_snow_proxy = inputs['rain_on_snow_proxy']
    proxy_snowline_m = inputs['proxy_snowline_m']

    basis: list[str] = []
    score = _LOW_CONFIDENCE_RELEVANCE_SCORE

    if observed_snow_support:
        basis.append('observed_snow_depth_ge_10cm')
        score = max(score, 1.0)
    if snowfall_24h_cm >= _SNOWFALL_POSITIVE_CM and (downscaled_temperature_c or 0.0) <= _COLD_SNOW_TEMP_C:
        basis.append('cold_recent_snowfall')
        score = max(score, 0.9)
    if rain_on_snow_proxy:
        basis.append('rain_on_snow_with_snow_evidence')
        score = max(score, 0.95)
    if (
        seasonal_support
        and elevation_m is not None
        and freezing_level_height_m is not None
        and elevation_m >= (freezing_level_height_m - _SEASONAL_SNOWLINE_OFFSET_M)
    ):
        basis.append('seasonal_proxy_above_conservative_snowline')
        score = max(score, 0.65)

    hard_negative = bool(
        elevation_m is not None
        and proxy_snowline_m is not None
        and downscaled_temperature_c is not None
        and downscaled_temperature_c > _WARM_NEGATIVE_TEMP_C
        and (snow_depth_cm or 0.0) <= _SNOW_DEPTH_NEGATIVE_CM
        and snowfall_24h_cm <= 0.0
        and not seasonal_support
        and elevation_m < (proxy_snowline_m - _LOW_ELEVATION_BUFFER_M)
    )

    eligible = bool(basis)
    mask_reason: str | None = None
    if eligible:
        wet_snow_eligible = bool(
            rain_on_snow_proxy
            or (
                (observed_snow_support or seasonal_support)
                and (downscaled_temperature_c or 0.0) > 0.0
            )
        )
    elif hard_negative:
        eligible = False
        wet_snow_eligible = False
        basis = ['hard_negative_warm_low_elevation_no_snow_support']
        score = 0.0
        mask_reason = 'warm_low_elevation_no_snow_support'
    else:
        eligible = True
        wet_snow_eligible = False
        basis = ['proxy_ambiguous_keep_public']
        score = _LOW_CONFIDENCE_RELEVANCE_SCORE

    return {
        'snow_elevation_eligible': eligible,
        'snow_elevation_profile': SNOW_ELEVATION_PROFILE,
        'snow_elevation_mask_reason': mask_reason,
        'snow_relevance_score': round(score, 3),
        'snow_relevance_basis': basis,
        'rain_on_snow_proxy': rain_on_snow_proxy,
        'wet_snow_eligible': wet_snow_eligible,
    }


def apply_public_eligibility_metric(cell: dict[str, Any]) -> dict[str, Any]:
    status = str(cell.get('status') or '')
    evaluation = evaluate_snow_elevation_eligibility(cell)
    cell.update(evaluation)

    if status == 'ready':
        apt_eligible = cell.get('apt_eligible')
        if apt_eligible is None:
            apt_eligible = is_apt_eligible_slope(slope_from_cell(cell))
            cell['apt_eligible'] = apt_eligible
        public_eligible = bool(
            apt_eligible
            and evaluation['snow_elevation_eligible']
        )
        mask_reasons = [
            reason
            for reason in (
                cell.get('apt_mask_reason'),
                evaluation['snow_elevation_mask_reason'],
            )
            if isinstance(reason, str) and reason
        ]
    else:
        public_eligible = False
        mask_reasons = []

    public_risk_score = _as_risk_score(cell.get('probability_risk_score')) if public_eligible else 0
    cell['public_eligible'] = public_eligible
    cell['public_mask_reasons'] = mask_reasons
    cell['public_mask_profile'] = {
        'profile': PUBLIC_ELIGIBILITY_PROFILE,
        'stage_a': _APT_PROFILE_NAME,
        'stage_b': SNOW_ELEVATION_PROFILE,
    }
    cell['risk_score'] = public_risk_score
    cell['runout_seed'] = bool(status == 'ready' and public_eligible and public_risk_score >= 4)

    return cell
