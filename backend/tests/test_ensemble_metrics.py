"""Tests for ensemble metric scaffolding (Phase 11-prep)."""
from __future__ import annotations

import unittest

import numpy as np

from backend.common.ensemble_metrics import (
    EnsembleMetricResult,
    brier_score,
    classify_lead_time,
    crps_ensemble,
    energy_score,
    interval_coverage,
    spread_skill_ratio,
    LEAD_TIME_BUCKETS,
)


class TestCRPS(unittest.TestCase):
    """Test CRPS (Continuous Ranked Probability Score)."""

    def test_perfect_forecast_crps_zero(self) -> None:
        """A perfect deterministic forecast has CRPS=0."""
        obs = [1.0, 2.0, 3.0]
        fcst = [[1.0, 2.0, 3.0]]  # Single member = observation
        result = crps_ensemble(obs, fcst)
        self.assertAlmostEqual(result.value, 0.0, places=6)

    def test_spread_reduces_crps(self) -> None:
        """An ensemble with spread should have lower CRPS than a deterministic bias."""
        obs = [1.0]
        # Deterministic forecast with bias
        fcst_det = [[1.5]]
        # Ensemble with spread around the observation
        fcst_ens = [[0.8], [1.0], [1.2]]
        crps_det = crps_ensemble(obs, fcst_det)
        crps_ens = crps_ensemble(obs, fcst_ens)
        self.assertLess(crps_ens.value, crps_det.value)

    def test_shape_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            crps_ensemble([1.0, 2.0], [[1.0]])

    def test_result_has_metadata(self) -> None:
        result = crps_ensemble([1.0], [[1.0]])
        self.assertEqual(result.metric_name, 'crps')
        self.assertEqual(result.n_samples, 1)
        self.assertFalse(result.is_calibrated)


class TestEnergyScore(unittest.TestCase):
    """Test energy score for multivariate forecasts."""

    def test_perfect_forecast_es_zero(self) -> None:
        obs = [[1.0, 2.0]]
        fcst = [[[1.0, 2.0]]]
        result = energy_score(obs, fcst)
        self.assertAlmostEqual(result.value, 0.0, places=6)

    def test_shape_validation(self) -> None:
        with self.assertRaises(ValueError):
            energy_score([1.0], [[1.0]])

    def test_result_has_metadata(self) -> None:
        obs = [[1.0, 2.0]]
        fcst = [[[1.0, 2.0]]]
        result = energy_score(obs, fcst)
        self.assertEqual(result.metric_name, 'energy_score')


class TestSpreadSkillRatio(unittest.TestCase):
    """Test spread-skill ratio."""

    def test_ideal_ratio_near_one(self) -> None:
        """A well-calibrated ensemble has spread/skill ~1.0."""
        np.random.seed(42)
        obs = np.random.randn(100)
        # Ensemble with spread matching the error
        fcst = obs[np.newaxis, :] + np.random.randn(10, 100) * 1.0
        result = spread_skill_ratio(obs.tolist(), fcst.tolist())
        self.assertGreater(result.value, 0.0)
        self.assertLess(result.value, 5.0)  # Generous bound for random data

    def test_underdispersive_ratio_less_than_one(self) -> None:
        """An overconfident ensemble has ratio < 1.0."""
        obs = [1.0, 2.0, 3.0, 4.0]
        # Very tight ensemble with a small bias — spread is tiny relative to skill
        fcst = [[1.11, 2.11, 3.11, 4.11], [1.09, 2.09, 3.09, 4.09]]
        result = spread_skill_ratio(obs, fcst)
        # Spread is 0.01, skill (RMSE) is ~0.1, so ratio should be ~0.1
        self.assertLess(result.value, 1.0)


class TestIntervalCoverage(unittest.TestCase):
    """Test prediction interval coverage."""

    def test_perfect_coverage(self) -> None:
        """All observations within the interval → coverage = 1.0."""
        obs = [1.0, 2.0, 3.0]
        fcst = [[0.5, 1.5, 2.5], [1.5, 2.5, 3.5]]
        result = interval_coverage(obs, fcst, 5.0, 95.0)
        self.assertEqual(result.value, 1.0)

    def test_partial_coverage(self) -> None:
        obs = [1.0, 10.0, 3.0]
        fcst = [[0.5, 1.5, 2.5], [1.5, 2.5, 3.5]]
        result = interval_coverage(obs, fcst, 5.0, 95.0)
        self.assertLess(result.value, 1.0)
        self.assertGreater(result.value, 0.0)

    def test_nominal_coverage_in_notes(self) -> None:
        result = interval_coverage([1.0], [[0.9], [1.1]], 5.0, 95.0)
        self.assertIn('90%', result.notes)


class TestBrierScore(unittest.TestCase):
    """Test Brier score for binary events."""

    def test_perfect_forecast_bs_zero(self) -> None:
        obs = [1, 0, 1]
        probs = [1.0, 0.0, 1.0]
        result = brier_score(obs, probs)
        self.assertAlmostEqual(result.value, 0.0, places=6)

    def test_worst_forecast_bs_one(self) -> None:
        obs = [1, 0]
        probs = [0.0, 1.0]
        result = brier_score(obs, probs)
        self.assertAlmostEqual(result.value, 1.0, places=6)

    def test_non_binary_observations_rejected(self) -> None:
        with self.assertRaises(ValueError):
            brier_score([0, 1, 2], [0.0, 0.5, 1.0])

    def test_out_of_range_probabilities_rejected(self) -> None:
        with self.assertRaises(ValueError):
            brier_score([0, 1], [-0.1, 1.1])

    def test_notes_mention_Partner_approval(self) -> None:
        result = brier_score([0, 1], [0.3, 0.7])
        self.assertIn('Partner', result.notes)


class TestLeadTimeBuckets(unittest.TestCase):
    """Test lead-time bucket classification."""

    def test_0_24h_bucket(self) -> None:
        self.assertEqual(classify_lead_time(0), '0-24h')
        self.assertEqual(classify_lead_time(12), '0-24h')
        self.assertEqual(classify_lead_time(23.9), '0-24h')

    def test_24_48h_bucket(self) -> None:
        self.assertEqual(classify_lead_time(24), '24-48h')
        self.assertEqual(classify_lead_time(36), '24-48h')
        self.assertEqual(classify_lead_time(47.9), '24-48h')

    def test_48_72h_bucket(self) -> None:
        self.assertEqual(classify_lead_time(48), '48-72h')
        self.assertEqual(classify_lead_time(60), '48-72h')
        self.assertEqual(classify_lead_time(71.9), '48-72h')

    def test_out_of_range(self) -> None:
        self.assertEqual(classify_lead_time(72), 'out_of_range')
        self.assertEqual(classify_lead_time(-1), 'out_of_range')

    def test_three_buckets_defined(self) -> None:
        self.assertEqual(len(LEAD_TIME_BUCKETS), 3)


if __name__ == '__main__':
    unittest.main()
