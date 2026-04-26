from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


DEFAULT_IPA_WEIGHTS: dict[str, float] = {
    'probability': 1.0,
    'slope_deviation_from_38deg': 1.0,
    'aspect_risk': 0.8,
    'snowpack_weakness': 0.9,
    'exposure': 0.7,
}


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
    exposure: float,
) -> dict[str, float]:
    return {
        'probability': clamp01(probability),
        'slope_deviation_from_38deg': slope_deviation_from_38deg(slope_deg),
        'aspect_risk': clamp01(aspect_risk),
        'snowpack_weakness': clamp01(1.0 - normalize_shear_strength(snowpack_shear_strength)),
        'exposure': clamp01(exposure),
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
