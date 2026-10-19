"""Multi-sensor fusion engine with inverse-variance weighting and consensus scoring.

Fuses snow state observations from multiple sensors (SAR, optical, weather,
GIBS/MODIS, physics model) into a single FusedSnowState with uncertainty
propagation and a consensus score.

Fusion method: inverse-variance weighting
  w_i = 1 / sigma_i^2
  fused = sum(w_i * x_i) / sum(w_i)
  sigma_fused = sqrt(1 / sum(w_i))

Consensus score (0–1): measures agreement between sensors.
  - 1.0 = all sensors agree within their uncertainty
  - 0.0 = sensors disagree beyond uncertainty bounds

Freshness-aware: sensors with stale data (>72h) are downweighted.
Cloud-aware: optical sensors under cloud cover are downweighted.

References:
  - Dunmire et al. 2026 (TC): dynamic observation uncertainty in EnKF snow DA
  - EGU26-21040: S1+S2 fusion at 10m for all-weather snow monitoring
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from backend.common.verification_contracts import (
    VERIFICATION_SPINE_ENABLED,
    FusedSnowState,
)

# Freshness thresholds (hours)
FRESH_THRESHOLD_H = 24.0
STALE_THRESHOLD_H = 72.0
MAX_FRESHNESS_PENALTY = 0.5  # max weight reduction for stale data

# Cloud cover threshold for optical downweighting
CLOUD_COVER_THRESHOLD = 0.7

# Default sensor uncertainties (1-sigma)
DEFAULT_UNCERTAINTIES = {
    'sar': 0.15,       # ~15cm for S1 cross-ratio depth
    'optical': 0.10,   # ~10cm for S2 NDSI-derived
    'weather': 0.20,   # ~20cm for weather model snow depth
    'gibs': 0.25,      # ~25cm for MODIS coarse resolution
    'physics': 0.18,   # ~18cm for physics model output
}

# Dynamic uncertainty scaling factor per Dunmire et al. 2026 (TC)
# σ_obs = base_uncertainty × (1 + |snow_depth_m| × k)
DYNAMIC_UNCERTAINTY_K = 0.3
SNOW_DEPTH_FUSION_FLAG = os.getenv('SNOW_DEPTH_FUSION_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}


@dataclass
class SensorObservation:
    """A single sensor's snow state observation for fusion."""

    source: str
    snow_depth_m: float | None = None
    snow_cover_fraction: float | None = None
    wet_snow_fraction: float | None = None
    loading_rate_24h: float | None = None
    uncertainty: float | None = None
    freshness_hours: float | None = None
    cloud_cover: float | None = None
    weight_override: float | None = None

    @property
    def effective_uncertainty(self) -> float:
        if self.uncertainty is not None:
            base = max(self.uncertainty, 1e-6)
        else:
            base = DEFAULT_UNCERTAINTIES.get(self.source, 0.20)
        # Dynamic uncertainty: scale σ_obs with snow depth magnitude
        # per Dunmire et al. 2026 (TC): σ = base × (1 + |depth| × k)
        if SNOW_DEPTH_FUSION_FLAG and self.snow_depth_m is not None:
            return base * (1.0 + abs(self.snow_depth_m) * DYNAMIC_UNCERTAINTY_K)
        return base

    @property
    def freshness_weight(self) -> float:
        """Weight multiplier based on data freshness (0.5–1.0)."""
        if self.freshness_hours is None:
            return 1.0
        if self.freshness_hours <= FRESH_THRESHOLD_H:
            return 1.0
        if self.freshness_hours >= STALE_THRESHOLD_H:
            return MAX_FRESHNESS_PENALTY
        # Linear interpolation between fresh and stale
        ratio = (self.freshness_hours - FRESH_THRESHOLD_H) / (STALE_THRESHOLD_H - FRESH_THRESHOLD_H)
        return 1.0 - ratio * (1.0 - MAX_FRESHNESS_PENALTY)

    @property
    def cloud_weight(self) -> float:
        """Weight multiplier for optical sensors under cloud cover."""
        if self.source != 'optical' or self.cloud_cover is None:
            return 1.0
        if self.cloud_cover >= CLOUD_COVER_THRESHOLD:
            return 0.1  # nearly zero weight
        return 1.0 - (self.cloud_cover / CLOUD_COVER_THRESHOLD) * 0.5

    @property
    def effective_weight(self) -> float:
        """Combined weight from uncertainty, freshness, and cloud cover."""
        if self.weight_override is not None:
            return max(self.weight_override, 1e-6)
        u = self.effective_uncertainty
        w = 1.0 / (u * u)
        return w * self.freshness_weight * self.cloud_weight


def fuse_snow_depth(observations: Sequence[SensorObservation]) -> tuple[float | None, float | None]:
    """Fuse snow depth from multiple sensors using inverse-variance weighting.

    Args:
        observations: Sensor observations with snow_depth_m values.

    Returns:
        Tuple of (fused_depth_m, fused_uncertainty_m).
    """
    valid = [o for o in observations if o.snow_depth_m is not None]
    if not valid:
        return None, None
    if len(valid) == 1:
        return valid[0].snow_depth_m, valid[0].effective_uncertainty

    weights = [o.effective_weight for o in valid]
    values = [o.snow_depth_m for o in valid]

    total_weight = sum(weights)
    if total_weight < 1e-12:
        return None, None

    fused = sum(w * v for w, v in zip(weights, values)) / total_weight
    fused_unc = math.sqrt(1.0 / total_weight)

    return float(fused), float(fused_unc)


def fuse_snow_cover(observations: Sequence[SensorObservation]) -> float | None:
    """Fuse snow cover fraction from multiple sensors.

    Uses weighted average with same weights as depth fusion.
    """
    valid = [o for o in observations if o.snow_cover_fraction is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return float(valid[0].snow_cover_fraction)

    weights = [o.effective_weight for o in valid]
    values = [o.snow_cover_fraction for o in valid]
    total = sum(weights)
    if total < 1e-12:
        return None
    return float(sum(w * v for w, v in zip(weights, values)) / total)


def fuse_wet_snow(observations: Sequence[SensorObservation]) -> float | None:
    """Fuse wet snow fraction from multiple sensors."""
    valid = [o for o in observations if o.wet_snow_fraction is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return float(valid[0].wet_snow_fraction)
    weights = [o.effective_weight for o in valid]
    values = [o.wet_snow_fraction for o in valid]
    total = sum(weights)
    if total < 1e-12:
        return None
    return float(sum(w * v for w, v in zip(weights, values)) / total)


def fuse_loading_rate(observations: Sequence[SensorObservation]) -> float | None:
    """Fuse 24h loading rate from multiple sensors."""
    valid = [o for o in observations if o.loading_rate_24h is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return float(valid[0].loading_rate_24h)
    weights = [o.effective_weight for o in valid]
    values = [o.loading_rate_24h for o in valid]
    total = sum(weights)
    if total < 1e-12:
        return None
    return float(sum(w * v for w, v in zip(weights, values)) / total)


def _variable_consensus(
    observations: Sequence[SensorObservation],
    attribute: str,
) -> float | None:
    """Compute agreement for one variable without mixing incompatible units."""
    valid = [
        observation for observation in observations
        if getattr(observation, attribute) is not None
    ]
    if not valid:
        return None
    if len(valid) == 1:
        return 1.0

    agreeing_pairs = 0
    total_pairs = 0
    for i, first in enumerate(valid):
        for second in valid[i + 1:]:
            total_pairs += 1
            diff = abs(float(getattr(first, attribute)) - float(getattr(second, attribute)))
            combined_unc = math.sqrt(
                first.effective_uncertainty ** 2 + second.effective_uncertainty ** 2
            )
            if diff <= 2.0 * combined_unc:
                agreeing_pairs += 1
    return float(agreeing_pairs / total_pairs) if total_pairs else 0.0


def compute_consensus(observations: Sequence[SensorObservation]) -> float:
    """Compute consensus score (0–1) between sensors.

    Measures how well sensors agree within their uncertainty bounds.
    1.0 = all sensors agree; 0.0 = complete disagreement.

    Method: for each pair of sensors, check if their values overlap
    within 2-sigma uncertainty. Consensus = fraction of agreeing pairs.
    """
    scores = [
        score for attribute in (
            'snow_depth_m',
            'snow_cover_fraction',
            'wet_snow_fraction',
            'loading_rate_24h',
        )
        if (score := _variable_consensus(observations, attribute)) is not None
    ]
    return float(sum(scores) / len(scores)) if scores else 0.0


def fuse_observations(observations: Sequence[SensorObservation]) -> FusedSnowState:
    """Fuse all snow state variables from multiple sensors.

    Args:
        observations: List of SensorObservation from different sources.

    Returns:
        FusedSnowState with fused values, uncertainty, and consensus.
    """
    if not VERIFICATION_SPINE_ENABLED:
        return FusedSnowState()

    if not observations:
        return FusedSnowState()

    fused_depth, fused_unc = fuse_snow_depth(observations)
    fused_cover = fuse_snow_cover(observations)
    fused_wet = fuse_wet_snow(observations)
    fused_loading = fuse_loading_rate(observations)
    consensus = compute_consensus(observations)

    contributing = [o.source for o in observations if o.snow_depth_m is not None or o.snow_cover_fraction is not None]

    return FusedSnowState(
        snow_depth_m=fused_depth,
        snow_cover_fraction=fused_cover,
        wet_snow_fraction=fused_wet,
        loading_rate_24h=fused_loading,
        uncertainty=fused_unc,
        consensus_score=consensus,
        contributing_sensors=contributing,
    )
