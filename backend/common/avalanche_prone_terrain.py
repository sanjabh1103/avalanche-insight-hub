from __future__ import annotations

import math
from typing import Any

APT_PROFILE = 'apt_30_50_v1'
APT_MIN_SLOPE_DEG = 30.0
APT_MAX_SLOPE_DEG = 50.0
APT_MASK_REASON = 'slope_outside_30_to_50_deg'


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


def is_apt_eligible_slope(slope_deg: object) -> bool:
    slope_value = _as_finite_float(slope_deg)
    if slope_value is None:
        return False
    return APT_MIN_SLOPE_DEG <= slope_value <= APT_MAX_SLOPE_DEG


def slope_from_cell(cell: dict[str, Any]) -> float | None:
    terrain_inputs = cell.get('terrain_inputs')
    if isinstance(terrain_inputs, dict):
        slope_value = _as_finite_float(terrain_inputs.get('slope_angle_deg'))
        if slope_value is not None:
            return slope_value
        slope_value = _as_finite_float(terrain_inputs.get('slope_deg'))
        if slope_value is not None:
            return slope_value
    return _as_finite_float(cell.get('slope_angle_deg') or cell.get('slope_deg'))


def apt_mask_reason_for_slope(slope_deg: object) -> str | None:
    return None if is_apt_eligible_slope(slope_deg) else APT_MASK_REASON


def unified_public_risk_score(*, probability_risk_score: object, slope_deg: object) -> int:
    if not is_apt_eligible_slope(slope_deg):
        return 0
    return _as_risk_score(probability_risk_score)


def apply_apt_unified_metric(cell: dict[str, Any]) -> dict[str, Any]:
    slope_deg = slope_from_cell(cell)
    apt_eligible = is_apt_eligible_slope(slope_deg)
    terrain_fused_risk_score = _as_risk_score(cell.get('terrain_fused_risk_score', cell.get('risk_score')))
    public_risk_score = unified_public_risk_score(
        probability_risk_score=cell.get('probability_risk_score'),
        slope_deg=slope_deg,
    )
    status = str(cell.get('status') or '')
    cell['terrain_fused_risk_score'] = terrain_fused_risk_score
    cell['risk_score'] = public_risk_score
    cell['apt_eligible'] = apt_eligible
    cell['apt_profile'] = APT_PROFILE
    cell['apt_mask_reason'] = None if apt_eligible else APT_MASK_REASON
    cell['runout_seed'] = bool(status == 'ready' and apt_eligible and public_risk_score >= 4)
    return cell
