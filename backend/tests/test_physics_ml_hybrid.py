"""Tests for physics-ML hybrid module."""
from __future__ import annotations

import os
import unittest

from backend.common.physics_ml_hybrid import (
    HybridConfig,
    HybridPrediction,
    compute_physics_features,
    compute_ml_residual,
    compute_conformal_interval,
    fuse_hybrid_prediction,
    PHYSICS_ML_HYBRID_ENABLED,
)


class TestComputePhysicsFeatures(unittest.TestCase):
    def test_extracts_known_fields(self):
        output = {'snow_depth_m': 1.5, 'swe_mm': 450.0, 'temperature_c': -5.0, 'extra': 'ignored'}
        features = compute_physics_features(output)
        self.assertEqual(features['snow_depth_m'], 1.5)
        self.assertEqual(features['swe_mm'], 450.0)
        self.assertEqual(features['temperature_c'], -5.0)
        self.assertNotIn('extra', features)

    def test_empty_output(self):
        self.assertEqual(compute_physics_features({}), {})


class TestComputeMlResidual(unittest.TestCase):
    def test_additive_residual(self):
        self.assertAlmostEqual(compute_ml_residual(1.0, 1.5), 0.5)

    def test_negative_residual(self):
        self.assertAlmostEqual(compute_ml_residual(2.0, 1.5), -0.5)

    def test_zero_residual(self):
        self.assertAlmostEqual(compute_ml_residual(1.0, 1.0), 0.0)


class TestConformalInterval(unittest.TestCase):
    def test_empty_residuals(self):
        lower, upper = compute_conformal_interval(1.0, [])
        self.assertAlmostEqual(lower, 1.0)
        self.assertAlmostEqual(upper, 1.0)

    def test_interval_width(self):
        residuals = [0.1, 0.2, 0.3, 0.4, 0.5]
        lower, upper = compute_conformal_interval(1.0, residuals, alpha=0.1)
        self.assertLessEqual(lower, 1.0)
        self.assertGreaterEqual(upper, 1.0)
        self.assertGreater(upper - lower, 0)


class TestFuseHybridPrediction(unittest.TestCase):
    def setUp(self):
        os.environ['PHYSICS_ML_HYBRID_ENABLED'] = 'true'
        import importlib
        import backend.common.physics_ml_hybrid as mod
        importlib.reload(mod)
        self.mod = mod

    def tearDown(self):
        os.environ['PHYSICS_ML_HYBRID_ENABLED'] = 'false'

    def test_disabled_returns_physics_only(self):
        os.environ['PHYSICS_ML_HYBRID_ENABLED'] = 'false'
        import importlib
        import backend.common.physics_ml_hybrid as mod
        importlib.reload(mod)
        result = mod.fuse_hybrid_prediction(1.0, 1.5, [])
        self.assertAlmostEqual(result.fused_value, 1.0)
        self.assertTrue(result.shadow_only)

    def test_additive_fusion(self):
        result = self.mod.fuse_hybrid_prediction(1.0, 1.5, [0.1, 0.2, 0.3])
        self.assertAlmostEqual(result.fused_value, 1.5)
        self.assertAlmostEqual(result.ml_residual, 0.5)
        self.assertIsNotNone(result.conformal_lower)
        self.assertIsNotNone(result.conformal_upper)

    def test_multiplicative_fusion(self):
        config = HybridConfig(residual_mode='multiplicative')
        result = self.mod.fuse_hybrid_prediction(2.0, 3.0, [0.1], config=config)
        self.assertAlmostEqual(result.fused_value, 3.0)

    def test_shadow_only_by_default(self):
        result = self.mod.fuse_hybrid_prediction(1.0, 1.5, [0.1])
        self.assertTrue(result.shadow_only)

    def test_to_dict(self):
        result = self.mod.fuse_hybrid_prediction(1.0, 1.5, [0.1])
        d = result.to_dict()
        self.assertIn('fused_value', d)
        self.assertIn('shadow_only', d)
        self.assertIn('Decision-support', d['disclaimer'])


if __name__ == '__main__':
    unittest.main()
