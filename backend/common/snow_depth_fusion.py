"""Snow depth fusion — combines S1 cross-ratio, ML, and PINN depth estimates.

Uses the existing fusion_engine inverse-variance weighting to produce
a FusedSnowState from multiple depth sources.

Env flags:
  SNOW_DEPTH_FUSION_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from typing import Any

from backend.common.fusion_engine import (
    SensorObservation,
    fuse_observations,
)
from backend.common.shadow_promotion import evaluate_shadow_promotion
from backend.common.verification_contracts import FusedSnowState

SNOW_DEPTH_FUSION_ENABLED = os.getenv(
    'SNOW_DEPTH_FUSION_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}
PINN_ENABLED = os.getenv('PINN_ENABLED', 'false').lower() in {'1', 'true', 'yes', 'on'}
PINN_EXTERNAL_CALIBRATED = os.getenv('PINN_EXTERNAL_CALIBRATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
PINN_HELD_OUT_VALIDATED = os.getenv('PINN_HELD_OUT_VALIDATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
PINN_PROMOTION_GATE_PASSED = os.getenv('PINN_PROMOTION_GATE_PASSED', 'false').lower() in {'1', 'true', 'yes', 'on'}


def fuse_snow_depths(
    *,
    s1_depth_m: float | None = None,
    s1_uncertainty_m: float = 0.25,
    ml_depth_m: float | None = None,
    ml_uncertainty_m: float = 0.30,
    pinn_depth_m: float | None = None,
    pinn_uncertainty_m: float = 0.35,
    freshness_hours: float = 12.0,
) -> FusedSnowState:
    """Fuse snow depth estimates from multiple sources.

    Uses inverse-variance weighting via fusion_engine.

    Args:
        s1_depth_m: S1 cross-ratio depth estimate.
        s1_uncertainty_m: S1 uncertainty (m).
        ml_depth_m: ML model depth estimate.
        ml_uncertainty_m: ML uncertainty (m).
        pinn_depth_m: PINN depth estimate.
        pinn_uncertainty_m: PINN uncertainty (m).
        freshness_hours: Data freshness in hours.

    Returns:
        FusedSnowState with fused depth and consensus score.
    """
    if not SNOW_DEPTH_FUSION_ENABLED:
        return FusedSnowState()

    observations: list[SensorObservation] = []

    if s1_depth_m is not None:
        observations.append(SensorObservation(
            source='s1_cross_ratio',
            snow_depth_m=s1_depth_m,
            uncertainty=s1_uncertainty_m,
            freshness_hours=freshness_hours,
        ))

    if ml_depth_m is not None:
        observations.append(SensorObservation(
            source='ml_snow_depth',
            snow_depth_m=ml_depth_m,
            uncertainty=ml_uncertainty_m,
            freshness_hours=freshness_hours,
        ))

    pinn_status = evaluate_shadow_promotion(
        'PINN',
        feature_enabled=PINN_ENABLED,
        external_calibrated=PINN_EXTERNAL_CALIBRATED,
        held_out_validated=PINN_HELD_OUT_VALIDATED,
        promotion_gate_passed=PINN_PROMOTION_GATE_PASSED,
    )
    if pinn_depth_m is not None and pinn_status.active:
        observations.append(SensorObservation(
            source='pinn_snowpack',
            snow_depth_m=pinn_depth_m,
            uncertainty=pinn_uncertainty_m,
            freshness_hours=freshness_hours,
        ))

    return fuse_observations(observations)
