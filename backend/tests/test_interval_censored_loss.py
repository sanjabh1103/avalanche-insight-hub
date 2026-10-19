"""Tests for the shadow-only interval-censored loss contract."""

from __future__ import annotations

import math
import unittest

from backend.common.interval_censored_loss import (
    INTERVAL_CENSORED_LOSS_VERSION,
    IntervalCensoredLossError,
    interval_censored_negative_log_likelihood,
    interval_event_probability,
)


class IntervalCensoredLossTests(unittest.TestCase):
    def test_interval_event_probability_uses_discrete_hazard_survival(self) -> None:
        self.assertAlmostEqual(interval_event_probability([0.1, 0.2]), 0.28)

    def test_positive_interval_loss_matches_event_likelihood(self) -> None:
        self.assertAlmostEqual(
            interval_censored_negative_log_likelihood([0.1, 0.2], label=1),
            -math.log(0.28),
        )

    def test_negative_interval_loss_matches_no_event_likelihood(self) -> None:
        self.assertAlmostEqual(
            interval_censored_negative_log_likelihood([0.1, 0.2], label=0),
            -math.log(0.9) - math.log(0.8),
        )

    def test_single_bin_reduces_to_binary_cross_entropy(self) -> None:
        self.assertAlmostEqual(
            interval_censored_negative_log_likelihood([0.2], label=1),
            -math.log(0.2),
        )
        self.assertAlmostEqual(
            interval_censored_negative_log_likelihood([0.2], label=0),
            -math.log(0.8),
        )

    def test_impossible_boundary_likelihoods_use_explicit_numeric_floor(self) -> None:
        epsilon = 1e-9
        self.assertEqual(interval_event_probability([0.0, 0.0]), 0.0)
        self.assertEqual(interval_event_probability([1.0]), 1.0)
        self.assertAlmostEqual(
            interval_censored_negative_log_likelihood([0.0, 0.0], label=1, epsilon=epsilon),
            -math.log(epsilon),
        )
        self.assertAlmostEqual(
            interval_censored_negative_log_likelihood([1.0], label=0, epsilon=epsilon),
            -math.log(epsilon),
        )

    def test_invalid_inputs_fail_closed(self) -> None:
        invalid_probability_sets = ([], [-0.1], [1.1], [math.nan], [math.inf])
        for probabilities in invalid_probability_sets:
            with self.subTest(probabilities=probabilities):
                with self.assertRaises(IntervalCensoredLossError):
                    interval_event_probability(probabilities)

        with self.assertRaises(IntervalCensoredLossError):
            interval_censored_negative_log_likelihood([0.2], label=2)
        with self.assertRaises(IntervalCensoredLossError):
            interval_censored_negative_log_likelihood([0.2], label=1, epsilon=0.0)

    def test_contract_version_is_explicit(self) -> None:
        self.assertEqual(INTERVAL_CENSORED_LOSS_VERSION, "interval_censored_noisy_or_v1")


if __name__ == "__main__":
    unittest.main()
