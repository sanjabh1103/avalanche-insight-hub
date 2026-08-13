"""Hazard and impact-risk scoring utilities.

Hazard factors (probability, slope, aspect, snowpack weakness) feed into
EAWS danger level (1-5) via ``risk_level()``. Impact-risk factors
(exposure, vulnerability) are scored separately via
``impact_risk_score()`` and ``impact_risk_level()`` per EAWS Matrix and
WMO Impact-Based Forecasting standards.

The ``DangerAggregationConfig`` dataclass allows configurable danger
methodology beyond the default fixed-threshold mapping, enabling future
Partner-approved multi-factor aggregation (stability, path frequency,
avalanche size, altitude, operational actions).

See: docs/METHODOLOGY_BOUNDARY.md for the full hazard vs impact-risk
separation framework per EAWS Matrix and WMO Impact-Based Forecasting.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np


# HAZARD FACTORS — these feed into EAWS danger level (1-5) via risk_level()
DEFAULT_IPA_WEIGHTS: dict[str, float] = {
    'probability': 1.0,
    'slope_deviation_from_38deg': 1.0,
    'aspect_risk': 0.8,
    'snowpack_weakness': 0.9,
}

# IMPACT-RISK FACTORS — scored separately from hazard per EAWS/WMO standards
DEFAULT_IMPACT_WEIGHTS: dict[str, float] = {
    'exposure': 1.0,
    'vulnerability': 0.8,
}

# Configurable danger methodology profile (default: fixed-threshold heuristic)
DANGER_AGGREGATION_PROFILE = os.getenv('DANGER_AGGREGATION_PROFILE', 'heuristic-risk-bands-v1')


@dataclass(frozen=True)
class DangerAggregationConfig:
    """Configurable danger level aggregation.

    Default profile ``heuristic-risk-bands-v1`` uses fixed thresholds
    via ``risk_level()``. Custom profiles can incorporate multi-factor
    inputs (stability, path frequency, avalanche size, altitude) per
    Partner-approved methodology.
    """
    profile: str = 'heuristic-risk-bands-v1'
    thresholds: tuple[float, float, float, float] = (0.15, 0.30, 0.50, 0.70)
    factor_weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ChebyshevIPAResult:
    score: float
    weighted_criteria: dict[str, float]
    dominant_criterion: str


def clamp01(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(np.clip(value, 0.0, 1.0))


def risk_level(probability_or_score: float) -> int:
    score = clamp01(probability_or_score)
    if score < 0.15:
        return 1
    if score < 0.30:
        return 2
    if score < 0.50:
        return 3
    if score < 0.70:
        return 4
    return 5


def slope_deviation_from_38deg(slope_deg: float) -> float:
    """Avalanche-prone slope score, peaking at 38 degrees and staying high above it."""
    slope = max(0.0, float(slope_deg))
    effective_slope = min(slope, 38.0)
    return clamp01(1.0 - abs(38.0 - effective_slope) / 38.0)


def normalize_shear_strength(shear_strength: float) -> float:
    """Normalize kPa-like shear strength where ~12 kPa is a strong snowpack."""
    return clamp01(float(shear_strength) / 12.0)


def build_hazard_vector(
    *,
    probability: float,
    slope_deg: float,
    aspect_risk: float,
    snowpack_shear_strength: float,
    exposure: float | None = None,
) -> dict[str, float]:
    """Build hazard-only vector (exposure excluded per EAWS/WMO).

    The ``exposure`` parameter is accepted for backward compatibility
    but is NOT included in the returned hazard vector.
    """
    return {
        'probability': clamp01(probability),
        'slope_deviation_from_38deg': slope_deviation_from_38deg(slope_deg),
        'aspect_risk': clamp01(aspect_risk),
        'snowpack_weakness': clamp01(1.0 - normalize_shear_strength(snowpack_shear_strength)),
    }


def chebyshev_ipa(
    vector: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> ChebyshevIPAResult:
    active_weights = dict(DEFAULT_IPA_WEIGHTS)
    if weights:
        active_weights.update({key: float(value) for key, value in weights.items()})

    weighted = {
        key: clamp01(float(vector.get(key, 0.0))) * max(0.0, float(active_weights.get(key, 0.0)))
        for key in active_weights
    }
    if not weighted:
        return ChebyshevIPAResult(score=0.0, weighted_criteria={}, dominant_criterion='unknown')

    dominant = max(weighted, key=weighted.get)
    max_weight = max(max(active_weights.values()), 1.0)
    return ChebyshevIPAResult(
        score=clamp01(weighted[dominant] / max_weight),
        weighted_criteria=weighted,
        dominant_criterion=dominant,
    )


def legacy_max_risk_level(probability: float, slope_deg: float) -> tuple[int, int]:
    probability_risk = risk_level(probability)
    slope_risk = risk_level(clamp01(float(slope_deg) / 38.0))
    return max(probability_risk, slope_risk), slope_risk


# ---------------------------------------------------------------------------
# Impact-risk scoring (separate from hazard per EAWS/WMO)
# ---------------------------------------------------------------------------

def build_impact_vector(
    *,
    exposure: float,
    vulnerability: float = 0.0,
) -> dict[str, float]:
    """Build impact-risk vector from exposure and vulnerability factors.

    These factors describe the *consequence* of a hazard, not the hazard
    itself. They should NOT feed into EAWS danger level (1-5).
    """
    return {
        'exposure': clamp01(exposure),
        'vulnerability': clamp01(vulnerability),
    }


def impact_risk_score(
    vector: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> float:
    """Chebyshev max-weighted impact-risk score (mirrors hazard IPA logic).

    Returns a score in [0, 1] representing the worst-case weighted
    impact-risk factor.
    """
    active_weights = dict(DEFAULT_IMPACT_WEIGHTS)
    if weights:
        active_weights.update({key: float(value) for key, value in weights.items()})

    weighted = {
        key: clamp01(float(vector.get(key, 0.0))) * max(0.0, float(active_weights.get(key, 0.0)))
        for key in active_weights
    }
    if not weighted:
        return 0.0

    dominant = max(weighted, key=weighted.get)
    max_weight = max(max(active_weights.values()), 1.0)
    return clamp01(weighted[dominant] / max_weight)


def impact_risk_level(score: float) -> int:
    """Map impact-risk score to 1-5 level using same thresholds as risk_level()."""
    return risk_level(score)


# ---------------------------------------------------------------------------
# Configurable danger methodology
# ---------------------------------------------------------------------------

def compute_danger_level(
    config: DangerAggregationConfig,
    **factors: float,
) -> int:
    """Compute danger level using configurable aggregation.

    For the default ``heuristic-risk-bands-v1`` profile, delegates to
    ``risk_level()`` using the ``score`` factor (or the max weighted
    factor if factor_weights are configured).

    Custom profiles can implement Partner-approved multi-factor aggregation
    incorporating stability, path frequency, avalanche size, altitude
    and operational actions.
    """
    if config.profile == 'heuristic-risk-bands-v1':
        if config.factor_weights and factors:
            weighted = sum(
                clamp01(float(v)) * max(0.0, float(config.factor_weights.get(k, 0.0)))
                for k, v in factors.items()
            )
            max_w = max(max(config.factor_weights.values()), 1.0) if config.factor_weights else 1.0
            return risk_level(weighted / max_w)
        score = factors.get('score', 0.0)
        return risk_level(float(score))

    # Custom profiles: use configured thresholds on the max weighted factor
    if config.factor_weights and factors:
        weighted = sum(
            clamp01(float(v)) * max(0.0, float(config.factor_weights.get(k, 0.0)))
            for k, v in factors.items()
        )
        max_w = max(max(config.factor_weights.values()), 1.0) if config.factor_weights else 1.0
        score = clamp01(weighted / max_w)
    else:
        score = clamp01(float(factors.get('score', 0.0)))

    t = config.thresholds
    if score < t[0]:
        return 1
    if score < t[1]:
        return 2
    if score < t[2]:
        return 3
    if score < t[3]:
        return 4
    return 5


# ---------------------------------------------------------------------------
# Canonical danger output contract
# ---------------------------------------------------------------------------

SHADOW_PROFILES = {'Partner_shadow_v1'}


@dataclass(frozen=True)
class DangerOutput:
    """Canonical danger level output separate from legacy risk_score.

    Attributes:
        danger_level: Integer danger level (1-5).
        profile: The aggregation profile used.
        factors_used: List of factor names that were inputs.
        is_shadow_only: True if this danger level is shadow-only (not authoritative).
    """
    danger_level: int
    profile: str
    factors_used: tuple[str, ...]
    is_shadow_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            'danger_level': self.danger_level,
            'profile': self.profile,
            'factors_used': list(self.factors_used),
            'is_shadow_only': self.is_shadow_only,
        }


def compute_canonical_danger(
    config: DangerAggregationConfig,
    **factors: float,
) -> DangerOutput:
    """Compute a canonical DangerOutput wrapping compute_danger_level.

    Marks is_shadow_only=True when the profile is a shadow profile.
    """
    level = compute_danger_level(config, **factors)
    return DangerOutput(
        danger_level=level,
        profile=config.profile,
        factors_used=tuple(sorted(factors.keys())),
        is_shadow_only=config.profile in SHADOW_PROFILES,
    )
