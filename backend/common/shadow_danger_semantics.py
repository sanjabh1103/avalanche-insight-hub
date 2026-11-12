"""Transparent, customer-reviewable danger semantics for shadow evidence."""
from __future__ import annotations

import math
from typing import Any, Sequence


SHADOW_DANGER_VERSION = 'open_source_shadow_danger_v1'
DEFAULT_THRESHOLDS = (0.15, 0.30, 0.50, 0.70)


def _bounded(value: float, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f'{name} must be finite')
    return max(0.0, min(1.0, numeric))


def _level(score: float, thresholds: Sequence[float]) -> int:
    if len(thresholds) != 4 or any(
        not math.isfinite(float(value)) for value in thresholds
    ) or tuple(sorted(float(value) for value in thresholds)) != tuple(float(value) for value in thresholds):
        raise ValueError('thresholds must contain four sorted finite values')
    return 1 + sum(score >= float(value) for value in thresholds)


def build_shadow_danger_candidate(
    *,
    probability: float,
    frequency: float,
    duration_hours: float,
    size_class: float,
    instability: float,
    source_attribution: Sequence[str],
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Build a candidate level without asserting EAWS equivalence or authority."""
    attribution = [str(value).strip() for value in source_attribution if str(value).strip()]
    if not attribution:
        raise ValueError('source_attribution is required for shadow danger evidence')
    duration_norm = _bounded(float(duration_hours) / 72.0, 'duration_hours')
    size_norm = _bounded((float(size_class) - 1.0) / 4.0, 'size_class')
    score = (
        0.35 * _bounded(probability, 'probability')
        + 0.20 * _bounded(frequency, 'frequency')
        + 0.15 * duration_norm
        + 0.15 * size_norm
        + 0.15 * _bounded(instability, 'instability')
    )
    score = _bounded(score, 'candidate_score')
    return {
        'version': SHADOW_DANGER_VERSION,
        'status': 'shadow_only',
        'is_shadow_only': True,
        'profile': SHADOW_DANGER_VERSION,
        'candidate_score': score,
        'candidate_level': _level(score, thresholds),
        'factors_used': ['probability', 'frequency', 'duration_hours', 'size_class', 'instability'],
        'factor_values': {
            'probability': _bounded(probability, 'probability'),
            'frequency': _bounded(frequency, 'frequency'),
            'duration_hours': float(duration_hours),
            'duration_normalized': duration_norm,
            'size_class': float(size_class),
            'size_normalized': size_norm,
            'instability': _bounded(instability, 'instability'),
        },
        'source_attribution': attribution,
        'assumptions': [
            'Weights are a transparent research hypothesis, not a customer-approved danger matrix.',
            'The candidate level is not an EAWS warning and cannot authorize public action.',
        ],
    }
