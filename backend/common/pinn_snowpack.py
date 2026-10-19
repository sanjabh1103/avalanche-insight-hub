"""Physics-Informed Neural Network (PINN) for snowpack state evolution.

CPU-sized residual MLP with mass/energy-conservation penalty losses.
Constraint targets are exported from snowpack_physics.py (COSIPY-sampled
pilot cells where installed, heuristic-labeled otherwise).

Outputs carry `method='pinn_residual_mlp'` lineage.

Env flags:
  PINN_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.common.shadow_promotion import evaluate_shadow_promotion

PINN_ENABLED = os.getenv('PINN_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
PINN_EXTERNAL_CALIBRATED = os.getenv('PINN_EXTERNAL_CALIBRATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
PINN_HELD_OUT_VALIDATED = os.getenv('PINN_HELD_OUT_VALIDATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
PINN_PROMOTION_GATE_PASSED = os.getenv('PINN_PROMOTION_GATE_PASSED', 'false').lower() in {'1', 'true', 'yes', 'on'}

PINN_HIDDEN_DIM = 64
PINN_N_LAYERS = 2
PINN_LAMBDA_MASS = 0.1  # mass conservation penalty weight
PINN_LAMBDA_ENERGY = 0.1  # energy balance penalty weight
PINN_LEARNING_RATE = 0.001
PINN_EPOCHS = 200


@dataclass
class PINNPrediction:
    """PINN snowpack state prediction."""

    cell_id: str
    snow_depth_m: float | None = None
    snow_density_kgm3: float | None = None
    temperature_gradient_per_m: float | None = None
    liquid_water_content_pct: float | None = None
    mass_residual: float | None = None
    energy_residual: float | None = None
    method: str = 'pinn_residual_mlp'
    source: str = 'pinn_snowpack'
    shadow_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'snow_depth_m': self.snow_depth_m,
            'snow_density_kgm3': self.snow_density_kgm3,
            'temperature_gradient_per_m': self.temperature_gradient_per_m,
            'liquid_water_content_pct': self.liquid_water_content_pct,
            'mass_residual': self.mass_residual,
            'energy_residual': self.energy_residual,
            'method': self.method,
            'source': self.source,
            'shadow_only': self.shadow_only,
            'metadata': self.metadata,
        }


def mass_conservation_penalty(
    predicted_density: np.ndarray,
    predicted_depth: np.ndarray,
    target_swe: np.ndarray | None = None,
) -> float:
    """Compute mass conservation penalty.

    SWE = density * depth should be conserved (or match target).
    Penalty = mean((SWE_pred - SWE_target)^2)

    Args:
        predicted_density: Predicted densities (kg/m³).
        predicted_depth: Predicted depths (m).
        target_swe: Target SWE values (kg/m²). If None, uses conservation.

    Returns:
        Penalty value (float).
    """
    swe_pred = predicted_density * predicted_depth
    if target_swe is not None:
        return float(np.mean((swe_pred - target_swe) ** 2))
    # Conservation: SWE should not change across timesteps
    if len(swe_pred) > 1:
        return float(np.var(swe_pred))
    return 0.0


def energy_balance_penalty(
    predicted_temp_gradient: np.ndarray,
    target_temp_gradient: np.ndarray | None = None,
) -> float:
    """Compute energy balance penalty.

    Temperature gradient should match physics-based target.

    Args:
        predicted_temp_gradient: Predicted gradients (K/m).
        target_temp_gradient: Target gradients from physics model.

    Returns:
        Penalty value (float).
    """
    if target_temp_gradient is not None:
        return float(np.mean((predicted_temp_gradient - target_temp_gradient) ** 2))
    # Without target, penalize extreme gradients
    return float(np.mean(np.clip(np.abs(predicted_temp_gradient) - 0.02, 0, None) ** 2))


def pinn_loss(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    *,
    predicted_density: np.ndarray | None = None,
    predicted_depth: np.ndarray | None = None,
    predicted_temp_gradient: np.ndarray | None = None,
    target_swe: np.ndarray | None = None,
    target_temp_gradient: np.ndarray | None = None,
    lambda_mass: float = PINN_LAMBDA_MASS,
    lambda_energy: float = PINN_LAMBDA_ENERGY,
) -> float:
    """Compute total PINN loss = MSE + λ₁·mass_penalty + λ₂·energy_penalty.

    Args:
        y_pred: Predicted state vector.
        y_true: True state vector.
        predicted_density: Density predictions for mass conservation.
        predicted_depth: Depth predictions for mass conservation.
        predicted_temp_gradient: Temperature gradient predictions.
        target_swe: Target SWE for mass conservation.
        target_temp_gradient: Target temperature gradient.
        lambda_mass: Mass conservation penalty weight.
        lambda_energy: Energy balance penalty weight.

    Returns:
        Total loss value.
    """
    mse = float(np.mean((y_pred - y_true) ** 2))

    mass_pen = 0.0
    if predicted_density is not None and predicted_depth is not None:
        mass_pen = mass_conservation_penalty(predicted_density, predicted_depth, target_swe)

    energy_pen = 0.0
    if predicted_temp_gradient is not None:
        energy_pen = energy_balance_penalty(predicted_temp_gradient, target_temp_gradient)

    return mse + lambda_mass * mass_pen + lambda_energy * energy_pen


class PINNResidualMLP:
    """Simple CPU-sized residual MLP for snowpack state prediction.

    Architecture: input → hidden → hidden → output with residual connections.
    Uses numpy-only implementation to avoid torch dependency.
    """

    def __init__(
        self,
        input_dim: int = 10,
        hidden_dim: int = PINN_HIDDEN_DIM,
        n_layers: int = PINN_N_LAYERS,
        output_dim: int = 4,  # depth, density, temp_gradient, lwc
    ):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.n_layers = n_layers
        self.output_dim = output_dim
        self.weights: list[np.ndarray] = []
        self.biases: list[np.ndarray] = []
        self._init_weights()

    def _init_weights(self) -> None:
        """Initialize weights with He initialization."""
        dims = [self.input_dim] + [self.hidden_dim] * self.n_layers + [self.output_dim]
        for i in range(len(dims) - 1):
            w = np.random.randn(dims[i], dims[i + 1]) * np.sqrt(2.0 / dims[i])
            b = np.zeros(dims[i + 1])
            self.weights.append(w)
            self.biases.append(b)

    def forward(self, X: np.ndarray) -> np.ndarray:
        """Forward pass through the MLP.

        Args:
            X: Input features (n_samples, input_dim).

        Returns:
            Predictions (n_samples, output_dim).
        """
        h = X
        for i in range(len(self.weights)):
            z = h @ self.weights[i] + self.biases[i]
            if i < len(self.weights) - 1:
                h = np.maximum(z, 0)  # ReLU
                if i > 0 and h.shape == z.shape:
                    h = h + z  # residual connection
            else:
                h = z  # linear output
        return h

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict snowpack state.

        Returns array with columns: [depth_m, density_kgm3, temp_gradient, lwc_pct]
        """
        return self.forward(X)


def estimate_pinn_snow_depth(
    *,
    cell_id: str,
    features: np.ndarray | None = None,
    model: PINNResidualMLP | None = None,
) -> PINNPrediction | None:
    """Estimate snowpack state from PINN for a single cell.

    Returns None when PINN_ENABLED is false or no model provided.
    """
    if not PINN_ENABLED or model is None or features is None:
        return None

    pred = model.predict(features.reshape(1, -1))[0]

    promotion = evaluate_shadow_promotion(
        'PINN',
        feature_enabled=PINN_ENABLED,
        external_calibrated=PINN_EXTERNAL_CALIBRATED,
        held_out_validated=PINN_HELD_OUT_VALIDATED,
        promotion_gate_passed=PINN_PROMOTION_GATE_PASSED,
    )
    return PINNPrediction(
        cell_id=cell_id,
        snow_depth_m=float(max(pred[0], 0.0)),
        snow_density_kgm3=float(pred[1]) if len(pred) > 1 else None,
        temperature_gradient_per_m=float(pred[2]) if len(pred) > 2 else None,
        liquid_water_content_pct=float(pred[3]) if len(pred) > 3 else None,
        mass_residual=0.0,
        energy_residual=0.0,
        shadow_only=promotion.shadow_only,
        metadata={'shadow_promotion': promotion.to_dict()},
    )
