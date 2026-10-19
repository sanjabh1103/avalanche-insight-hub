"""Dependency-free, shadow-only loss semantics for interval-censored labels.

The inputs are conditional discrete-time hazard probabilities for bins that
cover one observed interval.  For an interval known to contain an event, the
likelihood is ``1 - product(1 - hazard)``.  For an interval observed without
an event, the likelihood is ``product(1 - hazard)``.

This module defines and tests the mathematical contract only.  It is not
called by the active timestamp-only model path and does not make a dataset,
model, or artifact eligible for training or production scoring.
"""

from __future__ import annotations

import math
from typing import Iterable


INTERVAL_CENSORED_LOSS_VERSION = "interval_censored_noisy_or_v1"
INTERVAL_CENSORED_LOSS_IMPLEMENTATION_STATUS = "defined_shadow_only"
DEFAULT_NUMERIC_EPSILON = 1e-12


class IntervalCensoredLossError(ValueError):
    """Raised when interval-loss inputs violate the fail-closed contract."""


def _normalise_probabilities(probabilities: Iterable[float]) -> list[float]:
    try:
        values = list(probabilities)
    except TypeError as exc:
        raise IntervalCensoredLossError("hazard probabilities must be iterable") from exc
    if not values:
        raise IntervalCensoredLossError("at least one hazard probability is required")

    normalised: list[float] = []
    for index, value in enumerate(values):
        if isinstance(value, bool):
            raise IntervalCensoredLossError(
                f"hazard probability {index} must be numeric, not boolean"
            )
        try:
            probability = float(value)
        except (TypeError, ValueError) as exc:
            raise IntervalCensoredLossError(
                f"hazard probability {index} must be numeric"
            ) from exc
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise IntervalCensoredLossError(
                f"hazard probability {index} must be finite and within [0, 1]"
            )
        normalised.append(probability)
    return normalised


def _validate_epsilon(epsilon: float) -> float:
    try:
        value = float(epsilon)
    except (TypeError, ValueError) as exc:
        raise IntervalCensoredLossError("epsilon must be numeric") from exc
    if not math.isfinite(value) or not 0.0 < value < 0.5:
        raise IntervalCensoredLossError("epsilon must be finite and in (0, 0.5)")
    return value


def _log_survival_probability(probabilities: Iterable[float]) -> float:
    """Return log(product(1 - p)) without avoidable underflow."""
    log_survival = 0.0
    for probability in probabilities:
        if probability == 1.0:
            return -math.inf
        log_survival += math.log1p(-probability)
    return log_survival


def interval_event_probability(probabilities: Iterable[float]) -> float:
    """Return the probability that an event occurs in the observed interval."""
    values = _normalise_probabilities(probabilities)
    log_survival = _log_survival_probability(values)
    # -expm1(log_survival) is stable when the event probability is small.
    event_probability = -math.expm1(log_survival)
    return min(1.0, max(0.0, event_probability))


def _normalise_label(label: int | bool) -> int:
    if isinstance(label, bool):
        return int(label)
    if isinstance(label, int) and label in (0, 1):
        return label
    if isinstance(label, float) and math.isfinite(label) and label in (0.0, 1.0):
        return int(label)
    raise IntervalCensoredLossError("label must be binary 0/1")


def interval_censored_negative_log_likelihood(
    probabilities: Iterable[float],
    *,
    label: int | bool,
    epsilon: float = DEFAULT_NUMERIC_EPSILON,
) -> float:
    """Return the stable negative log-likelihood for one observed interval.

    ``label=1`` means an event is known to have occurred somewhere in the
    interval. ``label=0`` means no event was observed over the interval.  The
    epsilon floor is applied only when the raw likelihood is exactly zero;
    it keeps shadow diagnostics finite while the raw event probability remains
    available through :func:`interval_event_probability`.
    """
    values = _normalise_probabilities(probabilities)
    normalised_label = _normalise_label(label)
    numeric_epsilon = _validate_epsilon(epsilon)
    log_survival = _log_survival_probability(values)

    if normalised_label == 1:
        event_probability = -math.expm1(log_survival)
        likelihood = max(0.0, min(1.0, event_probability))
    else:
        survival_probability = (
            0.0 if log_survival == -math.inf else math.exp(log_survival)
        )
        likelihood = max(0.0, min(1.0, survival_probability))

    return -math.log(max(likelihood, numeric_epsilon))
