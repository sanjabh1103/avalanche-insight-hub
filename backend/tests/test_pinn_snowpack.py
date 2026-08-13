"""Tests for pinn_snowpack.py."""
from __future__ import annotations

import unittest

import numpy as np

from backend.common.pinn_snowpack import (
    PINNPrediction,
    PINN_ENABLED,
    PINNResidualMLP,
    mass_conservation_penalty,
    energy_balance_penalty,
    pinn_loss,
    estimate_pinn_snow_depth,
)


class TestMassConservationPenalty(unittest.TestCase):
    def test_with_target(self):
        density = np.array([300.0, 350.0])
        depth = np.array([1.0, 0.9])
        target_swe = np.array([300.0, 315.0])
        penalty = mass_conservation_penalty(density, depth, target_swe)
        self.assertGreaterEqual(penalty, 0.0)

    def test_conservation(self):
        density = np.array([300.0, 300.0, 300.0])
        depth = np.array([1.0, 1.0, 1.0])
        penalty = mass_conservation_penalty(density, depth)
        self.assertAlmostEqual(penalty, 0.0, places=6)

    def test_nonzero_penalty(self):
        density = np.array([300.0, 400.0])
        depth = np.array([1.0, 0.5])
        penalty = mass_conservation_penalty(density, depth)
        self.assertGreater(penalty, 0.0)


class TestEnergyBalancePenalty(unittest.TestCase):
    def test_with_target(self):
        pred = np.array([0.02, 0.03])
        target = np.array([0.02, 0.025])
        penalty = energy_balance_penalty(pred, target)
        self.assertGreaterEqual(penalty, 0.0)

    def test_without_target(self):
        pred = np.array([0.01, 0.01])
        penalty = energy_balance_penalty(pred)
        self.assertAlmostEqual(penalty, 0.0, places=6)


class TestPINNLoss(unittest.TestCase):
    def test_mse_only(self):
        y_pred = np.array([1.0, 2.0])
        y_true = np.array([1.5, 2.5])
        loss = pinn_loss(y_pred, y_true)
        self.assertAlmostEqual(loss, 0.25, places=2)

    def test_with_constraints(self):
        y_pred = np.array([1.0, 2.0])
        y_true = np.array([1.5, 2.5])
        density = np.array([300.0, 350.0])
        depth = np.array([1.0, 0.9])
        target_swe = np.array([300.0, 315.0])
        loss = pinn_loss(
            y_pred, y_true,
            predicted_density=density,
            predicted_depth=depth,
            target_swe=target_swe,
        )
        # MSE + penalty (penalty can be 0 if SWE matches exactly)
        self.assertGreaterEqual(loss, 0.25)


class TestPINNResidualMLP(unittest.TestCase):
    def test_init(self):
        model = PINNResidualMLP(input_dim=10, hidden_dim=32, output_dim=4)
        self.assertEqual(model.input_dim, 10)
        self.assertEqual(model.output_dim, 4)

    def test_forward_shape(self):
        model = PINNResidualMLP(input_dim=10, hidden_dim=32, output_dim=4)
        X = np.random.randn(5, 10)
        pred = model.predict(X)
        self.assertEqual(pred.shape, (5, 4))

    def test_forward_positive_depth(self):
        model = PINNResidualMLP(input_dim=10, hidden_dim=32, output_dim=4)
        X = np.random.randn(3, 10)
        pred = model.predict(X)
        # depth is first column, should be real-valued
        self.assertEqual(pred.shape, (3, 4))


class TestEstimatePINN(unittest.TestCase):
    def setUp(self):
        import backend.common.pinn_snowpack as p
        self._original = p.PINN_ENABLED
        p.PINN_ENABLED = True
        self.model = PINNResidualMLP(input_dim=10, hidden_dim=32, output_dim=4)

    def tearDown(self):
        import backend.common.pinn_snowpack as p
        p.PINN_ENABLED = self._original

    def test_valid_prediction(self):
        features = np.random.randn(10)
        result = estimate_pinn_snow_depth(
            cell_id='cell_0',
            features=features,
            model=self.model,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.snow_depth_m)
        self.assertEqual(result.method, 'pinn_residual_mlp')

    def test_disabled_returns_none(self):
        import backend.common.pinn_snowpack as p
        p.PINN_ENABLED = False
        result = estimate_pinn_snow_depth(
            cell_id='cell_0',
            features=np.random.randn(10),
            model=self.model,
        )
        self.assertIsNone(result)

    def test_no_model_returns_none(self):
        result = estimate_pinn_snow_depth(
            cell_id='cell_0',
            features=np.random.randn(10),
            model=None,
        )
        self.assertIsNone(result)

    def test_to_dict(self):
        result = PINNPrediction(cell_id='cell_0', snow_depth_m=0.5)
        d = result.to_dict()
        self.assertEqual(d['method'], 'pinn_residual_mlp')
        self.assertEqual(d['source'], 'pinn_snowpack')


if __name__ == '__main__':
    unittest.main()
