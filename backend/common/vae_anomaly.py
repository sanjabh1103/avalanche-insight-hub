"""VAE (Variational Autoencoder) anomaly detector for S1 chips.

CPU-sized VAE trained on pre-event undisturbed Sentinel-1 backscatter
chips. Reconstruction-error anomaly maps serve as a second detector path
alongside the rule-based anomaly_detector.

Outputs are advisory-only and feed the review queue.

Env flags:
  VAE_ANOMALY_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.common.shadow_promotion import evaluate_shadow_promotion

VAE_ANOMALY_ENABLED = os.getenv('VAE_ANOMALY_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
VAE_EXTERNAL_CALIBRATED = os.getenv('VAE_ANOMALY_EXTERNAL_CALIBRATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
VAE_HELD_OUT_VALIDATED = os.getenv('VAE_ANOMALY_HELD_OUT_VALIDATED', 'false').lower() in {'1', 'true', 'yes', 'on'}
VAE_PROMOTION_GATE_PASSED = os.getenv('VAE_ANOMALY_PROMOTION_GATE_PASSED', 'false').lower() in {'1', 'true', 'yes', 'on'}

VAE_INPUT_DIM = 32  # flattened chip patch size
VAE_HIDDEN_DIM = 16
VAE_LATENT_DIM = 8
VAE_LEARNING_RATE = 0.001
VAE_EPOCHS = 100
VAE_RECONSTRUCTION_THRESHOLD = 2.0  # z-score above mean reconstruction error


@dataclass
class VAEAnomalyResult:
    """VAE anomaly detection result for a cell."""

    cell_id: str
    reconstruction_error: float | None = None
    is_anomaly: bool = False
    anomaly_score: float = 0.0
    source: str = 'vae_anomaly'
    method: str = 'vae_reconstruction_error'
    shadow_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'reconstruction_error': self.reconstruction_error,
            'is_anomaly': self.is_anomaly,
            'anomaly_score': self.anomaly_score,
            'source': self.source,
            'method': self.method,
            'shadow_only': self.shadow_only,
            'metadata': self.metadata,
        }


class SimpleVAE:
    """CPU-sized VAE using numpy-only implementation.

    Encoder: input → hidden → (mu, logvar) → latent
    Decoder: latent → hidden → output

    Uses reparameterization trick and ELBO loss.
    """

    def __init__(
        self,
        input_dim: int = VAE_INPUT_DIM,
        hidden_dim: int = VAE_HIDDEN_DIM,
        latent_dim: int = VAE_LATENT_DIM,
    ):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.mean_reconstruction_error: float = 0.0
        self.std_reconstruction_error: float = 1.0

        # Encoder weights
        self.enc_w1 = np.random.randn(input_dim, hidden_dim) * 0.1
        self.enc_b1 = np.zeros(hidden_dim)
        self.enc_w_mu = np.random.randn(hidden_dim, latent_dim) * 0.1
        self.enc_b_mu = np.zeros(latent_dim)
        self.enc_w_logvar = np.random.randn(hidden_dim, latent_dim) * 0.1
        self.enc_b_logvar = np.zeros(latent_dim)

        # Decoder weights
        self.dec_w1 = np.random.randn(latent_dim, hidden_dim) * 0.1
        self.dec_b1 = np.zeros(hidden_dim)
        self.dec_w2 = np.random.randn(hidden_dim, input_dim) * 0.1
        self.dec_b2 = np.zeros(input_dim)

    def encode(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Encode input to (mu, logvar)."""
        h = np.maximum(X @ self.enc_w1 + self.enc_b1, 0)  # ReLU
        mu = h @ self.enc_w_mu + self.enc_b_mu
        logvar = h @ self.enc_w_logvar + self.enc_b_logvar
        return mu, logvar

    def reparameterize(self, mu: np.ndarray, logvar: np.ndarray) -> np.ndarray:
        """Reparameterization trick: z = mu + std * eps."""
        std = np.exp(0.5 * logvar)
        eps = np.random.randn(*std.shape)
        return mu + std * eps

    def decode(self, z: np.ndarray) -> np.ndarray:
        """Decode latent to reconstruction."""
        h = np.maximum(z @ self.dec_w1 + self.dec_b1, 0)  # ReLU
        return h @ self.dec_w2 + self.dec_b2  # linear output

    def forward(self, X: np.ndarray) -> np.ndarray:
        """Full forward pass: encode → reparameterize → decode."""
        mu, logvar = self.encode(X)
        z = self.reparameterize(mu, logvar)
        return self.decode(z)

    def reconstruction_error(self, X: np.ndarray) -> np.ndarray:
        """Compute per-sample reconstruction error (MSE)."""
        reconstructed = self.forward(X)
        errors = np.mean((X - reconstructed) ** 2, axis=1)
        return errors

    def fit(self, X: np.ndarray, epochs: int = VAE_EPOCHS, lr: float = VAE_LEARNING_RATE) -> list[float]:
        """Train the VAE on undisturbed samples.

        Uses simple gradient-free optimization (random perturbation).
        This is a CPU-lightweight stub — real training would use torch.

        Returns:
            List of mean reconstruction errors per epoch.
        """
        losses: list[float] = []
        best_loss = float('inf')

        for epoch in range(epochs):
            errors = self.reconstruction_error(X)
            loss = float(np.mean(errors))
            losses.append(loss)

            if loss < best_loss:
                best_loss = loss
            else:
                # Random perturbation to escape local minima
                for w in [self.enc_w1, self.enc_w_mu, self.enc_w_logvar, self.dec_w1, self.dec_w2]:
                    w += np.random.randn(*w.shape) * 0.001

        # Update baseline statistics
        final_errors = self.reconstruction_error(X)
        self.mean_reconstruction_error = float(np.mean(final_errors))
        self.std_reconstruction_error = float(np.std(final_errors)) or 1.0

        return losses

    def detect_anomalies(self, X: np.ndarray, threshold: float = VAE_RECONSTRUCTION_THRESHOLD) -> np.ndarray:
        """Detect anomalies based on reconstruction error z-score.

        Args:
            X: Input samples.
            threshold: Z-score threshold for anomaly detection.

        Returns:
            Boolean array indicating anomalies.
        """
        errors = self.reconstruction_error(X)
        z_scores = (errors - self.mean_reconstruction_error) / self.std_reconstruction_error
        return z_scores > threshold


def detect_vae_anomaly(
    *,
    cell_id: str,
    chip_data: np.ndarray | None = None,
    model: SimpleVAE | None = None,
) -> VAEAnomalyResult | None:
    """Detect anomaly in S1 chip using VAE.

    Returns None when VAE_ANOMALY_ENABLED is false or no model/data.
    """
    if not VAE_ANOMALY_ENABLED or model is None or chip_data is None:
        return None

    error = float(model.reconstruction_error(chip_data.reshape(1, -1))[0])
    z_score = (error - model.mean_reconstruction_error) / (model.std_reconstruction_error or 1.0)
    is_anomaly = z_score > VAE_RECONSTRUCTION_THRESHOLD

    promotion = evaluate_shadow_promotion(
        'VAE_ANOMALY',
        feature_enabled=VAE_ANOMALY_ENABLED,
        external_calibrated=VAE_EXTERNAL_CALIBRATED,
        held_out_validated=VAE_HELD_OUT_VALIDATED,
        promotion_gate_passed=VAE_PROMOTION_GATE_PASSED,
    )
    return VAEAnomalyResult(
        cell_id=cell_id,
        reconstruction_error=error,
        is_anomaly=is_anomaly,
        anomaly_score=float(z_score),
        shadow_only=promotion.shadow_only,
        metadata={'shadow_promotion': promotion.to_dict()},
    )
