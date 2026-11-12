"""Tests for ml_snow_depth.py."""
from __future__ import annotations

import unittest

import numpy as np

from backend.common.ml_snow_depth import (
    MLSnowDepthResult,
    ML_SNOW_DEPTH_ENABLED,
    ML_DEPTH_FEATURES,
    LABEL_SOURCE,
    build_feature_matrix,
    train_depth_model,
    predict_depth,
    estimate_ml_snow_depth,
)


class TestFeatureMatrix(unittest.TestCase):
    def test_build_matrix(self):
        samples = [
            {'s1_vh_db': -22.0, 's1_vv_db': -18.0, 's2_ndsi': 0.6, 'elevation_m': 3000},
            {'s1_vh_db': -20.0, 's1_vv_db': -16.0, 's2_ndsi': 0.3, 'elevation_m': 2500},
        ]
        X, names = build_feature_matrix(samples)
        self.assertEqual(X.shape, (2, len(ML_DEPTH_FEATURES)))
        self.assertEqual(names, ML_DEPTH_FEATURES)
        # Missing features should be 0.0
        self.assertEqual(X[0, 5], 0.0)  # s2_ndvi not in sample

    def test_empty_samples(self):
        X, _ = build_feature_matrix([])
        self.assertEqual(X.shape, (0, len(ML_DEPTH_FEATURES)))


class TestTrainDepthModel(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        self.X = np.random.randn(50, len(ML_DEPTH_FEATURES))
        self.y = np.random.rand(50) * 2.0

    def test_rf_fallback(self):
        model, model_type = train_depth_model(self.X, self.y, prefer_xgboost=False)
        self.assertEqual(model_type, 'random_forest')
        preds = predict_depth(model, self.X[:5], model_type=model_type)
        self.assertEqual(preds.shape, (5,))
        self.assertTrue(np.all(preds >= 0))

    def test_xgboost_or_rf(self):
        model, model_type = train_depth_model(self.X, self.y, prefer_xgboost=True)
        self.assertIn(model_type, ('xgboost', 'random_forest'))


class TestEstimateMLSnowDepth(unittest.TestCase):
    def setUp(self):
        import backend.common.ml_snow_depth as ml
        self._original = ml.ML_SNOW_DEPTH_ENABLED
        ml.ML_SNOW_DEPTH_ENABLED = True
        np.random.seed(42)
        self.X = np.random.randn(50, len(ML_DEPTH_FEATURES))
        self.y = np.random.rand(50) * 2.0
        self.model, self.model_type = train_depth_model(self.X, self.y, prefer_xgboost=False)

    def tearDown(self):
        import backend.common.ml_snow_depth as ml
        ml.ML_SNOW_DEPTH_ENABLED = self._original

    def test_valid_prediction(self):
        result = estimate_ml_snow_depth(
            cell_id='cell_0',
            features={'s1_vh_db': -22.0, 's1_vv_db': -18.0, 's2_ndsi': 0.6},
            model=self.model,
            model_type=self.model_type,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.snow_depth_m)
        self.assertEqual(result.label_source, LABEL_SOURCE)

    def test_disabled_returns_none(self):
        import backend.common.ml_snow_depth as ml
        ml.ML_SNOW_DEPTH_ENABLED = False
        result = estimate_ml_snow_depth(
            cell_id='cell_0',
            features={'s1_vh_db': -22.0},
            model=self.model,
            model_type=self.model_type,
        )
        self.assertIsNone(result)

    def test_no_model_returns_none(self):
        result = estimate_ml_snow_depth(
            cell_id='cell_0',
            features={'s1_vh_db': -22.0},
            model=None,
        )
        self.assertIsNone(result)

    def test_to_dict(self):
        result = MLSnowDepthResult(cell_id='cell_0', snow_depth_m=0.5, model_type='random_forest')
        d = result.to_dict()
        self.assertEqual(d['label_source'], 'openmeteo_proxy')


if __name__ == '__main__':
    unittest.main()
