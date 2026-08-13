"""Physics-ML residual hybrid — use physics outputs as constrained features/residual targets with conformal uncertainty.

Combines physics model (COSIPY/PINN/snowpack) predictions with ML model
(MTS-LSTM/RF) predictions using a residual approach:
  fused = physics + ml_residual
where ml_residual = ml_prediction - physics_prediction.

Conformal uncertainty intervals are computed from calibration residuals.

All outputs are shadow-only by default, gated by shadow_promotion.

Env flags:
  PHYSICS_ML_HYBRID_ENABLED — enable hybrid computation (default: false)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

from backend.common.shadow_promotion import evaluate_shadow_promotion

PHYSICS_ML_HYBRID_ENABLED = os.getenv('PHYSICS_ML_HYBRID_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)


@dataclass(frozen=True)
class HybridConfig:
    """Configuration for physics-ML hybrid prediction."""
    physics_model: str = 'cosipy'
    ml_model: str = 'mts_lstm'
    residual_mode: str = 'additive'
    conformal_alpha: float = 0.1


@dataclass
class HybridPrediction:
    """Fused physics-ML prediction with conformal uncertainty."""
    fused_value: float = 0.0
    physics_component: float = 0.0
    ml_component: float = 0.0
    ml_residual: float = 0.0
    conformal_lower: float | None = None
    conformal_upper: float | None = None
    shadow_only: bool = True
    model_name: str = ''
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def to_dict(self) -> dict[str, Any]:
        return {
            'fused_value': self.fused_value,
            'physics_component': self.physics_component,
            'ml_component': self.ml_component,
            'ml_residual': self.ml_residual,
            'conformal_lower': self.conformal_lower,
            'conformal_upper': self.conformal_upper,
            'shadow_only': self.shadow_only,
            'model_name': self.model_name,
            'disclaimer': self.disclaimer,
        }


def compute_physics_features(physics_output: dict[str, Any]) -> dict[str, float]:
    """Extract features from physics model output for ML residual training.

    Args:
        physics_output: Dict with physics model predictions (snow_depth, swe, temperature, etc.)

    Returns:
        Dict of extracted numeric features.
    """
    features: dict[str, float] = {}
    for key in ('snow_depth_m', 'swe_mm', 'temperature_c', 'wind_speed_ms', 'slope_angle_deg', 'elevation_m'):
        val = physics_output.get(key)
        if val is not None and isinstance(val, (int, float)):
            features[key] = float(val)
    return features


def compute_ml_residual(physics_prediction: float, ml_prediction: float) -> float:
    """Compute ML residual: ml_prediction - physics_prediction.

    This represents what the ML model learns beyond what physics captures.
    """
    return ml_prediction - physics_prediction


def compute_conformal_interval(
    point_prediction: float,
    calibration_residuals: list[float],
    alpha: float = 0.1,
) -> tuple[float, float]:
    """Compute conformal prediction interval.

    Uses split conformal: the (1-alpha) quantile of |calibration_residuals|
    as the half-width.

    Args:
        point_prediction: Point prediction value.
        calibration_residuals: Absolute residuals from calibration set.
        alpha: Miscoverage rate (0.1 = 90% intervals).

    Returns:
        (lower, upper) bounds of the conformal interval.
    """
    if not calibration_residuals:
        return point_prediction, point_prediction

    sorted_residuals = sorted(calibration_residuals)
    n = len(sorted_residuals)
    q_idx = int(math.ceil((1 - alpha) * n)) - 1
    q_idx = max(0, min(q_idx, n - 1))
    half_width = sorted_residuals[q_idx]

    return point_prediction - half_width, point_prediction + half_width


def fuse_hybrid_prediction(
    physics_prediction: float,
    ml_prediction: float,
    calibration_residuals: list[float],
    config: HybridConfig | None = None,
) -> HybridPrediction:
    """Fuse physics and ML predictions using residual approach.

    fused = physics_prediction + ml_residual
    where ml_residual = ml_prediction - physics_prediction

    For multiplicative mode:
    fused = physics_prediction * (1 + ml_residual_ratio)

    All outputs are shadow-only unless promotion gates pass.

    Args:
        physics_prediction: Physics model prediction.
        ml_prediction: ML model prediction.
        calibration_residuals: Residuals from calibration set for conformal intervals.
        config: Hybrid configuration.

    Returns:
        HybridPrediction with fused value and conformal uncertainty.
    """
    cfg = config or HybridConfig()
    model_name = f'{cfg.physics_model}_{cfg.ml_model}_hybrid'

    if not PHYSICS_ML_HYBRID_ENABLED:
        return HybridPrediction(
            fused_value=physics_prediction,
            physics_component=physics_prediction,
            ml_component=0.0,
            ml_residual=0.0,
            model_name=model_name,
            shadow_only=True,
        )

    residual = compute_ml_residual(physics_prediction, ml_prediction)

    if cfg.residual_mode == 'multiplicative' and physics_prediction != 0:
        residual_ratio = residual / physics_prediction
        fused = physics_prediction * (1 + residual_ratio)
    else:
        fused = physics_prediction + residual

    lower, upper = compute_conformal_interval(
        fused, calibration_residuals, alpha=cfg.conformal_alpha,
    )

    status = evaluate_shadow_promotion(
        model_name.upper(),
        feature_enabled=PHYSICS_ML_HYBRID_ENABLED,
    )

    return HybridPrediction(
        fused_value=fused,
        physics_component=physics_prediction,
        ml_component=ml_prediction,
        ml_residual=residual,
        conformal_lower=lower,
        conformal_upper=upper,
        shadow_only=status.shadow_only,
        model_name=model_name,
    )
