"""Tests for Federated Learning (FedAvg) framework."""
from __future__ import annotations

import unittest
import json
import os
import tempfile
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

from backend.common.federated_learning import (
    SectorWeights,
    FederatedAggregator,
    export_model_weights,
    load_sector_weights_from_dir,
    validate_sector_weights,
)
from backend.common.fed_avg import (
    fed_avg,
    fed_avg_with_rejection,
    compute_weight_divergence,
    apply_aggregated_weights,
)


def _make_sector_weights(
    sector_id: str,
    sample_count: int,
    *,
    coef: np.ndarray | None = None,
    intercept: np.ndarray | None = None,
) -> SectorWeights:
    """Helper to create SectorWeights with simple linear model params."""
    if coef is None:
        coef = np.random.randn(5, 3).astype(np.float32) * 0.1
    if intercept is None:
        intercept = np.random.randn(3).astype(np.float32) * 0.01
    return SectorWeights(
        sector_id=sector_id,
        sample_count=sample_count,
        weights_dict={
            'coef_': coef,
            'intercept_': intercept,
        },
        training_metrics={'loss': 0.5},
    )


class SectorWeightsTests(unittest.TestCase):
    """Tests for SectorWeights serialization."""

    def test_to_json_and_from_json(self) -> None:
        sw = _make_sector_weights('sector_a', 100)
        json_data = sw.to_json()
        self.assertEqual(json_data['sector_id'], 'sector_a')
        self.assertEqual(json_data['sample_count'], 100)
        self.assertIn('weights', json_data)

        sw2 = SectorWeights.from_json(json_data)
        self.assertEqual(sw2.sector_id, 'sector_a')
        self.assertEqual(sw2.sample_count, 100)
        np.testing.assert_allclose(sw2.weights_dict['coef_'], sw.weights_dict['coef_'])
        np.testing.assert_allclose(sw2.weights_dict['intercept_'], sw.weights_dict['intercept_'])

    def test_save_and_load_file(self) -> None:
        sw = _make_sector_weights('sector_b', 50)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / 'sector_b.json'
            sw.save_to_file(filepath)
            self.assertTrue(filepath.exists())

            loaded = SectorWeights.load_from_file(filepath)
            self.assertEqual(loaded.sector_id, 'sector_b')
            np.testing.assert_allclose(loaded.weights_dict['coef_'], sw.weights_dict['coef_'])

    def test_total_params(self) -> None:
        sw = _make_sector_weights('test', 10)
        expected = sw.weights_dict['coef_'].size + sw.weights_dict['intercept_'].size
        self.assertEqual(sw.total_params, expected)


class FedAvgTests(unittest.TestCase):
    """Tests for FedAvg aggregation."""

    def test_empty_list_returns_none(self) -> None:
        result = fed_avg([])
        self.assertIsNone(result)

    def test_single_sector_returns_own_weights(self) -> None:
        sw = _make_sector_weights('only', 100)
        result = fed_avg([sw])
        self.assertIsNotNone(result)
        np.testing.assert_allclose(result['coef_'], sw.weights_dict['coef_'])

    def test_two_sectors_weighted_average(self) -> None:
        coef_a = np.ones((3, 2), dtype=np.float32) * 1.0
        coef_b = np.ones((3, 2), dtype=np.float32) * 3.0
        sw_a = _make_sector_weights('a', 100, coef=coef_a)
        sw_b = _make_sector_weights('b', 300, coef=coef_b)

        result = fed_avg([sw_a, sw_b])
        # Weighted: (1.0 * 100 + 3.0 * 300) / 400 = (100 + 900) / 400 = 2.5
        np.testing.assert_allclose(result['coef_'], np.ones((3, 2)) * 2.5, atol=1e-5)

    def test_equal_sample_counts(self) -> None:
        coef_a = np.ones((2, 2), dtype=np.float32) * 2.0
        coef_b = np.ones((2, 2), dtype=np.float32) * 4.0
        sw_a = _make_sector_weights('a', 50, coef=coef_a)
        sw_b = _make_sector_weights('b', 50, coef=coef_b)

        result = fed_avg([sw_a, sw_b])
        # Equal weight: (2 + 4) / 2 = 3
        np.testing.assert_allclose(result['coef_'], np.ones((2, 2)) * 3.0, atol=1e-5)

    def test_no_common_keys(self) -> None:
        sw_a = SectorWeights(
            sector_id='a', sample_count=10,
            weights_dict={'param_x': np.ones(3, dtype=np.float32)},
        )
        sw_b = SectorWeights(
            sector_id='b', sample_count=10,
            weights_dict={'param_y': np.ones(3, dtype=np.float32)},
        )
        result = fed_avg([sw_a, sw_b])
        self.assertIsNone(result)

    def test_shape_mismatch_skipped(self) -> None:
        sw_a = SectorWeights(
            sector_id='a', sample_count=10,
            weights_dict={'coef_': np.ones((3, 2), dtype=np.float32)},
        )
        sw_b = SectorWeights(
            sector_id='b', sample_count=10,
            weights_dict={'coef_': np.ones((4, 2), dtype=np.float32)},
        )
        result = fed_avg([sw_a, sw_b])
        # Shape mismatch — coef_ should be skipped
        self.assertNotIn('coef_', result)

    def test_zero_sample_count_equal_weighting(self) -> None:
        coef_a = np.ones((2, 2), dtype=np.float32) * 2.0
        coef_b = np.ones((2, 2), dtype=np.float32) * 4.0
        sw_a = _make_sector_weights('a', 0, coef=coef_a)
        sw_b = _make_sector_weights('b', 0, coef=coef_b)
        result = fed_avg([sw_a, sw_b])
        # Equal weighting: (2 + 4) / 2 = 3
        np.testing.assert_allclose(result['coef_'], np.ones((2, 2)) * 3.0, atol=1e-5)


class FedAvgWithRejectionTests(unittest.TestCase):
    """Tests for FedAvg with outlier rejection."""

    def test_outlier_rejected(self) -> None:
        coef_normal = np.ones((3, 2), dtype=np.float32) * 1.0
        coef_outlier = np.ones((3, 2), dtype=np.float32) * 1000.0
        fixed_intercept = np.ones(2, dtype=np.float32) * 0.1

        sectors = [
            _make_sector_weights('normal1', 100, coef=coef_normal.copy(), intercept=fixed_intercept.copy()),
            _make_sector_weights('normal2', 100, coef=coef_normal.copy(), intercept=fixed_intercept.copy()),
            _make_sector_weights('normal3', 100, coef=coef_normal.copy(), intercept=fixed_intercept.copy()),
            _make_sector_weights('outlier', 100, coef=coef_outlier, intercept=fixed_intercept.copy()),
        ]

        result = fed_avg_with_rejection(sectors, outlier_threshold_sigma=3.0)
        self.assertIsNotNone(result)
        # Outlier should be excluded — result should be ~1.0
        np.testing.assert_allclose(result['coef_'], np.ones((3, 2)), atol=1e-5)

    def test_no_outliers_with_two_sectors(self) -> None:
        # With < 3 sectors, outlier detection is skipped
        coef_a = np.ones((2, 2), dtype=np.float32) * 1.0
        coef_b = np.ones((2, 2), dtype=np.float32) * 100.0
        sectors = [
            _make_sector_weights('a', 100, coef=coef_a),
            _make_sector_weights('b', 100, coef=coef_b),
        ]
        result = fed_avg_with_rejection(sectors)
        # No rejection with < 3 sectors — plain average
        np.testing.assert_allclose(result['coef_'], np.ones((2, 2)) * 50.5, atol=1e-5)


class WeightDivergenceTests(unittest.TestCase):
    """Tests for weight divergence computation."""

    def test_identical_weights_zero_divergence(self) -> None:
        weights = {'coef_': np.ones((3, 3), dtype=np.float32)}
        div = compute_weight_divergence(weights, weights)
        self.assertAlmostEqual(div['coef_'], 0.0, places=5)

    def test_different_weights_nonzero_divergence(self) -> None:
        a = {'coef_': np.ones((3, 3), dtype=np.float32)}
        b = {'coef_': np.zeros((3, 3), dtype=np.float32)}
        div = compute_weight_divergence(a, b)
        self.assertGreater(div['coef_'], 0.0)

    def test_no_common_keys(self) -> None:
        a = {'param_x': np.ones(3, dtype=np.float32)}
        b = {'param_y': np.ones(3, dtype=np.float32)}
        div = compute_weight_divergence(a, b)
        self.assertEqual(len(div), 0)


class ValidateSectorWeightsTests(unittest.TestCase):
    """Tests for sector weight validation."""

    def test_valid_weights(self) -> None:
        sw = _make_sector_weights('test', 100)
        is_valid, msg = validate_sector_weights(sw)
        self.assertTrue(is_valid)

    def test_empty_weights(self) -> None:
        sw = SectorWeights(sector_id='test', sample_count=10, weights_dict={})
        is_valid, msg = validate_sector_weights(sw)
        self.assertFalse(is_valid)

    def test_zero_sample_count(self) -> None:
        sw = _make_sector_weights('test', 0)
        is_valid, msg = validate_sector_weights(sw)
        self.assertFalse(is_valid)

    def test_shape_mismatch_with_reference(self) -> None:
        sw = _make_sector_weights('test', 100)
        is_valid, msg = validate_sector_weights(
            sw,
            reference_shapes={'coef_': (10, 10)},
        )
        self.assertFalse(is_valid)
        self.assertIn('Shape mismatch', msg)


class ExportModelWeightsTests(unittest.TestCase):
    """Tests for model weight export."""

    def test_export_sklearn_model(self) -> None:
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression()
        model.coef_ = np.random.randn(3, 5).astype(np.float32)
        model.intercept_ = np.random.randn(3).astype(np.float32)
        model.classes_ = np.array([0, 1, 2])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_model_weights(
                model,
                sector_id='test_sector',
                sample_count=500,
                output_dir=tmpdir,
            )
            self.assertTrue(path.exists())

            loaded = SectorWeights.load_from_file(path)
            self.assertEqual(loaded.sector_id, 'test_sector')
            self.assertEqual(loaded.sample_count, 500)
            self.assertIn('coef_', loaded.weights_dict)
            self.assertIn('intercept_', loaded.weights_dict)


class LoadSectorWeightsFromDirTests(unittest.TestCase):
    """Tests for loading sector weights from directory."""

    def test_load_multiple_sectors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                sw = _make_sector_weights(f'sector_{i}', (i + 1) * 100)
                sw.save_to_file(Path(tmpdir) / f'sector_{i}.json')

            loaded = load_sector_weights_from_dir(tmpdir)
            self.assertEqual(len(loaded), 3)

    def test_load_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = load_sector_weights_from_dir(tmpdir)
            self.assertEqual(len(loaded), 0)

    def test_load_nonexistent_dir(self) -> None:
        loaded = load_sector_weights_from_dir('/nonexistent/path/xyz')
        self.assertEqual(len(loaded), 0)


class FederatedAggregatorTests(unittest.TestCase):
    """Tests for the FederatedAggregator class."""

    def test_add_and_aggregate(self) -> None:
        agg = FederatedAggregator()
        agg.add_sector(_make_sector_weights('a', 100, coef=np.ones((3, 2), dtype=np.float32) * 1.0))
        agg.add_sector(_make_sector_weights('b', 300, coef=np.ones((3, 2), dtype=np.float32) * 3.0))

        result = agg.aggregate()
        self.assertIsNotNone(result)
        # Weighted: (1*100 + 3*300) / 400 = 2.5
        np.testing.assert_allclose(result['coef_'], np.ones((3, 2)) * 2.5, atol=1e-5)

    def test_outlier_detection(self) -> None:
        agg = FederatedAggregator(outlier_threshold_sigma=3.0)
        fixed_intercept = np.ones(2, dtype=np.float32) * 0.1
        agg.add_sector(_make_sector_weights('normal1', 100, coef=np.ones((3, 2), dtype=np.float32), intercept=fixed_intercept.copy()))
        agg.add_sector(_make_sector_weights('normal2', 100, coef=np.ones((3, 2), dtype=np.float32), intercept=fixed_intercept.copy()))
        agg.add_sector(_make_sector_weights('normal3', 100, coef=np.ones((3, 2), dtype=np.float32), intercept=fixed_intercept.copy()))
        agg.add_sector(_make_sector_weights('outlier', 100, coef=np.ones((3, 2), dtype=np.float32) * 1000.0, intercept=fixed_intercept.copy()))

        rejected = agg.detect_outliers()
        self.assertIn('outlier', rejected)

        valid = agg.get_valid_sectors()
        self.assertEqual(len(valid), 3)

    def test_no_outliers_with_few_sectors(self) -> None:
        agg = FederatedAggregator()
        agg.add_sector(_make_sector_weights('a', 100))
        agg.add_sector(_make_sector_weights('b', 100))
        rejected = agg.detect_outliers()
        self.assertEqual(len(rejected), 0)

    def test_get_status(self) -> None:
        agg = FederatedAggregator()
        agg.add_sector(_make_sector_weights('a', 100))
        agg.add_sector(_make_sector_weights('b', 200))
        status = agg.get_status()
        self.assertEqual(status['total_sectors'], 2)
        self.assertEqual(status['valid_sectors'], 2)

    def test_aggregate_empty_returns_none(self) -> None:
        agg = FederatedAggregator()
        result = agg.aggregate()
        self.assertIsNone(result)


class ApplyAggregatedWeightsTests(unittest.TestCase):
    """Tests for applying aggregated weights to models."""

    def test_apply_to_sklearn_model(self) -> None:
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression()
        model.coef_ = np.zeros((3, 5), dtype=np.float32)
        model.intercept_ = np.zeros(3, dtype=np.float32)

        new_coef = np.ones((3, 5), dtype=np.float32)
        new_intercept = np.ones(3, dtype=np.float32) * 0.5

        apply_aggregated_weights(model, {
            'coef_': new_coef,
            'intercept_': new_intercept,
        })

        np.testing.assert_allclose(model.coef_, new_coef)
        np.testing.assert_allclose(model.intercept_, new_intercept)


if __name__ == '__main__':
    unittest.main()
