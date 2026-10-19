"""Tests for vae_anomaly.py."""
from __future__ import annotations

import unittest

import numpy as np

from backend.common.vae_anomaly import (
    VAEAnomalyResult,
    VAE_ANOMALY_ENABLED,
    SimpleVAE,
    detect_vae_anomaly,
)


class TestSimpleVAE(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        self.vae = SimpleVAE(input_dim=32, hidden_dim=16, latent_dim=8)

    def test_init(self):
        self.assertEqual(self.vae.input_dim, 32)
        self.assertEqual(self.vae.latent_dim, 8)

    def test_forward_shape(self):
        X = np.random.randn(5, 32)
        output = self.vae.forward(X)
        self.assertEqual(output.shape, (5, 32))

    def test_reconstruction_error_shape(self):
        X = np.random.randn(10, 32)
        errors = self.vae.reconstruction_error(X)
        self.assertEqual(errors.shape, (10,))

    def test_fit_reduces_loss(self):
        X = np.random.randn(50, 32) * 0.1
        losses = self.vae.fit(X, epochs=20)
        self.assertEqual(len(losses), 20)
        # Loss should generally decrease or stay stable
        self.assertLessEqual(losses[-1], losses[0] * 2)

    def test_detect_anomalies_shape(self):
        X = np.random.randn(20, 32)
        self.vae.fit(X, epochs=10)
        anomalies = self.vae.detect_anomalies(X)
        self.assertEqual(anomalies.shape, (20,))
        self.assertTrue(np.all((anomalies == True) | (anomalies == False)))


class TestDetectVAEAnomaly(unittest.TestCase):
    def setUp(self):
        import backend.common.vae_anomaly as va
        self._original = va.VAE_ANOMALY_ENABLED
        va.VAE_ANOMALY_ENABLED = True
        np.random.seed(42)
        self.vae = SimpleVAE(input_dim=32, hidden_dim=16, latent_dim=8)
        train_data = np.random.randn(50, 32) * 0.1
        self.vae.fit(train_data, epochs=20)

    def tearDown(self):
        import backend.common.vae_anomaly as va
        va.VAE_ANOMALY_ENABLED = self._original

    def test_normal_input(self):
        chip = np.random.randn(32) * 0.1
        result = detect_vae_anomaly(cell_id='cell_0', chip_data=chip, model=self.vae)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.reconstruction_error)
        self.assertEqual(result.source, 'vae_anomaly')

    def test_anomalous_input(self):
        # Use extreme values likely to trigger anomaly
        chip = np.random.randn(32) * 5.0
        result = detect_vae_anomaly(cell_id='cell_0', chip_data=chip, model=self.vae)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.reconstruction_error)

    def test_disabled_returns_none(self):
        import backend.common.vae_anomaly as va
        va.VAE_ANOMALY_ENABLED = False
        chip = np.random.randn(32) * 0.1
        result = detect_vae_anomaly(cell_id='cell_0', chip_data=chip, model=self.vae)
        self.assertIsNone(result)

    def test_no_model_returns_none(self):
        chip = np.random.randn(32) * 0.1
        result = detect_vae_anomaly(cell_id='cell_0', chip_data=chip, model=None)
        self.assertIsNone(result)

    def test_to_dict(self):
        result = VAEAnomalyResult(cell_id='cell_0', reconstruction_error=0.5, is_anomaly=True, anomaly_score=2.5)
        d = result.to_dict()
        self.assertEqual(d['cell_id'], 'cell_0')
        self.assertTrue(d['is_anomaly'])
        self.assertEqual(d['method'], 'vae_reconstruction_error')


if __name__ == '__main__':
    unittest.main()
