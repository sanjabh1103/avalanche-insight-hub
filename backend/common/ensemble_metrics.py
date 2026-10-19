"""Ensemble metric scaffolding (Phase 11-prep).

Implements probabilistic verification metrics for ensemble forecasts:
  - CRPS (Continuous Ranked Probability Score)
  - Energy score (multivariate/spatial)
  - Spread-skill ratio
  - Interval coverage

Per Imp_plan.md Phase 11:
  - Use CRPS for continuous ensembles.
  - Use energy score for multivariate/spatial forecasts.
  - Use spread-skill ratio and interval coverage.
  - Use Brier, reliability, recall/POD, false-alarm rate for approved event labels.
  - Evaluate 0-24, 24-48 and 48-72 hours separately.
  - Do not import Alpine performance values as acceptance floors.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class EnsembleMetricResult:
    """Result of an ensemble metric calculation."""
    metric_name: str
    value: float
    n_samples: int
    lead_time_bucket: str = ''   # '0-24h', '24-48h', '48-72h', ''
    is_calibrated: bool = False  # False until calibration is proven
    notes: str = ''


# ---------------------------------------------------------------------------
# CRPS (Continuous Ranked Probability Score)
# ---------------------------------------------------------------------------

def crps_ensemble(
    observations: Sequence[float],
    ensemble_forecasts: Sequence[Sequence[float]],
) -> EnsembleMetricResult:
    """Compute CRPS for an ensemble forecast.

    CRPS measures the distance between the predicted cumulative distribution
    and the observed value. Lower is better. CRPS=0 means a perfect deterministic
    forecast.

    Uses the ensemble approximation of CRPS:
    CRPS = (1/n) * sum_i |x_i - y| - (1/(2n^2)) * sum_i sum_j |x_i - x_j|

    Args:
        observations: Observed values (n_samples,)
        ensemble_forecasts: Ensemble member forecasts (n_members, n_samples)

    Returns:
        EnsembleMetricResult with mean CRPS.
    """
    obs = np.asarray(observations, dtype=float)
    fcst = np.asarray(ensemble_forecasts, dtype=float)

    if obs.ndim != 1:
        raise ValueError(f'observations must be 1D, got shape {obs.shape}')
    if fcst.ndim != 2:
        raise ValueError(f'ensemble_forecasts must be 2D (n_members, n_samples), got shape {fcst.shape}')

    n_samples = len(obs)
    n_members = fcst.shape[0]

    if fcst.shape[1] != n_samples:
        raise ValueError(
            f'ensemble_forecasts has {fcst.shape[1]} samples, observations has {n_samples}'
        )

    # First term: mean absolute error between each member and observation
    mae_term = np.mean(np.abs(fcst - obs[np.newaxis, :]))

    # Second term: spread term (pairwise absolute differences between members)
    spread_term = 0.0
    for i in range(n_members):
        for j in range(n_members):
            spread_term += np.mean(np.abs(fcst[i] - fcst[j]))
    spread_term /= (2 * n_members * n_members)

    crps = mae_term - spread_term

    return EnsembleMetricResult(
        metric_name='crps',
        value=float(crps),
        n_samples=n_samples,
        is_calibrated=False,
        notes='Ensemble CRPS. Lower is better. Not calibrated until proven.',
    )


# ---------------------------------------------------------------------------
# Energy Score (multivariate)
# ---------------------------------------------------------------------------

def energy_score(
    observations: Sequence[Sequence[float]],
    ensemble_forecasts: Sequence[Sequence[Sequence[float]]],
    beta: float = 1.0,
) -> EnsembleMetricResult:
    """Compute the energy score for multivariate/spatial forecasts.

    ES = (1/n) * sum_i ||x_i - y_i||^beta
       - (1/(2n^2)) * sum_i sum_j ||x_i - x_j||^beta

    where ||.|| is the Euclidean norm and beta is typically 1.

    Args:
        observations: Observed vectors (n_samples, n_dims)
        ensemble_forecasts: Ensemble member forecasts (n_members, n_samples, n_dims)
        beta: Power parameter (typically 1.0)

    Returns:
        EnsembleMetricResult with mean energy score.
    """
    obs = np.asarray(observations, dtype=float)
    fcst = np.asarray(ensemble_forecasts, dtype=float)

    if obs.ndim != 2:
        raise ValueError(f'observations must be 2D (n_samples, n_dims), got shape {obs.shape}')
    if fcst.ndim != 3:
        raise ValueError(
            f'ensemble_forecasts must be 3D (n_members, n_samples, n_dims), got shape {fcst.shape}'
        )

    n_samples = obs.shape[0]
    n_members = fcst.shape[0]

    if fcst.shape[1] != n_samples:
        raise ValueError(
            f'ensemble_forecasts has {fcst.shape[1]} samples, observations has {n_samples}'
        )

    # First term
    es_first = 0.0
    for m in range(n_members):
        diff = fcst[m] - obs
        norms = np.sqrt(np.sum(diff ** 2, axis=1))
        es_first += np.mean(norms ** beta)
    es_first /= n_members

    # Second term
    es_second = 0.0
    for i in range(n_members):
        for j in range(n_members):
            diff = fcst[i] - fcst[j]
            norms = np.sqrt(np.sum(diff ** 2, axis=1))
            es_second += np.mean(norms ** beta)
    es_second /= (2 * n_members * n_members)

    es = es_first - es_second

    return EnsembleMetricResult(
        metric_name='energy_score',
        value=float(es),
        n_samples=n_samples,
        is_calibrated=False,
        notes=f'Energy score (beta={beta}). Lower is better. Not calibrated until proven.',
    )


# ---------------------------------------------------------------------------
# Spread-Skill Ratio
# ---------------------------------------------------------------------------

def spread_skill_ratio(
    observations: Sequence[float],
    ensemble_forecasts: Sequence[Sequence[float]],
) -> EnsembleMetricResult:
    """Compute the spread-skill ratio.

    Spread = mean standard deviation of ensemble members.
    Skill = RMSE of ensemble mean vs observations.
    Ratio = Spread / Skill (ideal ~1.0).

    < 1.0: ensemble is underdispersive (too confident)
    > 1.0: ensemble is overdispersive (too spread out)

    Args:
        observations: Observed values (n_samples,)
        ensemble_forecasts: Ensemble member forecasts (n_members, n_samples)

    Returns:
        EnsembleMetricResult with spread-skill ratio.
    """
    obs = np.asarray(observations, dtype=float)
    fcst = np.asarray(ensemble_forecasts, dtype=float)

    n_samples = len(obs)

    # Ensemble spread: mean std across members
    spread = np.mean(np.std(fcst, axis=0))

    # Ensemble skill: RMSE of ensemble mean
    ensemble_mean = np.mean(fcst, axis=0)
    skill = np.sqrt(np.mean((ensemble_mean - obs) ** 2))

    if skill == 0:
        ratio = float('inf')
    else:
        ratio = float(spread / skill)

    return EnsembleMetricResult(
        metric_name='spread_skill_ratio',
        value=ratio,
        n_samples=n_samples,
        is_calibrated=False,
        notes='Spread/skill ratio. ~1.0 is ideal. <1.0 underdispersive, >1.0 overdispersive.',
    )


# ---------------------------------------------------------------------------
# Interval Coverage
# ---------------------------------------------------------------------------

def interval_coverage(
    observations: Sequence[float],
    ensemble_forecasts: Sequence[Sequence[float]],
    lower_percentile: float = 5.0,
    upper_percentile: float = 95.0,
) -> EnsembleMetricResult:
    """Compute the coverage of a prediction interval.

    Checks what fraction of observations fall within the [lower, upper]
    percentile range of the ensemble. For a 90% interval, ideal coverage is 0.90.

    Args:
        observations: Observed values (n_samples,)
        ensemble_forecasts: Ensemble member forecasts (n_members, n_samples)
        lower_percentile: Lower bound percentile (default 5.0)
        upper_percentile: Upper bound percentile (default 95.0)

    Returns:
        EnsembleMetricResult with coverage fraction.
    """
    obs = np.asarray(observations, dtype=float)
    fcst = np.asarray(ensemble_forecasts, dtype=float)

    n_samples = len(obs)

    lower = np.percentile(fcst, lower_percentile, axis=0)
    upper = np.percentile(fcst, upper_percentile, axis=0)

    covered = np.sum((obs >= lower) & (obs <= upper))
    coverage = float(covered) / n_samples

    nominal = (upper_percentile - lower_percentile) / 100.0

    return EnsembleMetricResult(
        metric_name='interval_coverage',
        value=coverage,
        n_samples=n_samples,
        is_calibrated=False,
        notes=f'{upper_percentile - lower_percentile:.0f}% interval. '
              f'Nominal coverage={nominal:.2f}. Actual={coverage:.3f}. '
              f'Not calibrated until proven.',
    )


# ---------------------------------------------------------------------------
# Brier Score (for binary events)
# ---------------------------------------------------------------------------

def brier_score(
    observations: Sequence[int],
    forecast_probabilities: Sequence[float],
) -> EnsembleMetricResult:
    """Compute the Brier score for binary event forecasts.

    BS = (1/n) * sum (f_i - o_i)^2

    where f_i is the forecast probability and o_i is the observed outcome (0 or 1).
    Lower is better. BS=0 is perfect.

    Args:
        observations: Binary observations (0 or 1), shape (n_samples,)
        forecast_probabilities: Forecast probabilities [0, 1], shape (n_samples,)

    Returns:
        EnsembleMetricResult with Brier score.
    """
    obs = np.asarray(observations, dtype=float)
    probs = np.asarray(forecast_probabilities, dtype=float)

    n_samples = len(obs)

    # Validate binary observations
    if not np.all(np.isin(obs, [0, 1])):
        raise ValueError('observations must be binary (0 or 1)')

    # Validate probability range
    if np.any(probs < 0) or np.any(probs > 1):
        raise ValueError('forecast_probabilities must be in [0, 1]')

    bs = np.mean((probs - obs) ** 2)

    return EnsembleMetricResult(
        metric_name='brier_score',
        value=float(bs),
        n_samples=n_samples,
        is_calibrated=False,
        notes='Brier score. Lower is better. 0=perfect, 1=worst. '
              'Requires Partner label approval for event labels.',
    )


# ---------------------------------------------------------------------------
# Lead-time bucketing
# ---------------------------------------------------------------------------

LEAD_TIME_BUCKETS = {
    '0-24h': (0, 24),
    '24-48h': (24, 48),
    '48-72h': (48, 72),
}

def classify_lead_time(lead_time_h: float) -> str:
    """Classify a lead time into a bucket string."""
    for bucket, (lo, hi) in LEAD_TIME_BUCKETS.items():
        if lo <= lead_time_h < hi:
            return bucket
    return 'out_of_range'
