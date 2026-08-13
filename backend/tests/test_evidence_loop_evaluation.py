"""Tests for the paired baseline-vs-verification-gated evaluator."""
from __future__ import annotations

import unittest

import numpy as np

from backend.common.evidence_loop_evaluation import (
    evaluate_paired,
    label_predictions,
    _compute_metrics,
    _stable_hash,
)


def _pred(
    forecast_date: str,
    lat: float,
    lng: float,
    probability: float,
    evidence_available: bool = True,
) -> dict:
    return {
        'forecast_date': forecast_date,
        'lat': lat,
        'lng': lng,
        'probability': probability,
        'evidence_available': evidence_available,
        'feature_snapshot_sha256': 'a' * 64,
        'evidence_replay_sha256': 'b' * 64,
    }


def _event(date: str, lat: float, lng: float) -> dict:
    return {
        'timestamp': f'{date}T12:00:00Z',
        'location': f'POINT({lng} {lat})',
    }


class TestLabelPredictions(unittest.TestCase):
    def test_labels_match_by_date_and_radius(self) -> None:
        preds = [
            _pred('2026-01-15', 35.0, 76.0, 0.8),
            _pred('2026-01-15', 40.0, 80.0, 0.3),
        ]
        events = [_event('2026-01-15', 35.01, 76.01)]
        labelled = label_predictions(preds, events)
        self.assertEqual(labelled[0]['label'], 1)
        self.assertEqual(labelled[1]['label'], 0)

    def test_no_events_labels_zero(self) -> None:
        preds = [_pred('2026-01-15', 35.0, 76.0, 0.8)]
        labelled = label_predictions(preds, [])
        self.assertEqual(labelled[0]['label'], 0)

    def test_empty_predictions_returns_empty(self) -> None:
        self.assertEqual(label_predictions([], []), [])


class TestPairedEvaluation(unittest.TestCase):
    def test_unavailable_evidence_is_abstention_not_negative(self) -> None:
        """Predictions without evidence must abstain, not be counted as negatives."""
        preds = [
            _pred('2026-01-10', 35.0, 76.0, 0.9, evidence_available=True),
            _pred('2026-01-11', 35.0, 76.0, 0.9, evidence_available=False),
            _pred('2026-01-12', 35.0, 76.0, 0.9, evidence_available=True),
            _pred('2026-01-13', 35.0, 76.0, 0.9, evidence_available=False),
            _pred('2026-01-14', 35.0, 76.0, 0.1, evidence_available=True),
            _pred('2026-01-15', 35.0, 76.0, 0.1, evidence_available=True),
        ]
        events = [_event('2026-01-10', 35.01, 76.01)]
        result = evaluate_paired(preds, events, n_splits=2)

        self.assertNotIn('error', result)
        self.assertEqual(result['n_without_evidence'], 2)
        self.assertGreater(result['overall_abstention_rate'], 0.0)

        for fold_metrics in result['verification_gated_metrics']:
            self.assertIn('n_abstained', fold_metrics)
            self.assertIn('abstention_rate', fold_metrics)
            self.assertIn('coverage', fold_metrics)

    def test_future_leakage_prevention(self) -> None:
        """TimeSeriesSplit must not train on future data — fold boundaries must be ordered."""
        preds = [
            _pred(f'2026-01-{d:02d}', 35.0, 76.0, 0.5 + d * 0.01, evidence_available=True)
            for d in range(1, 11)
        ]
        events = [_event('2026-01-05', 35.01, 76.01)]
        result = evaluate_paired(preds, events, n_splits=3)

        self.assertNotIn('error', result)
        boundaries = result['fold_boundaries']
        self.assertGreater(len(boundaries), 0)
        for i in range(1, len(boundaries)):
            self.assertGreaterEqual(boundaries[i]['test_start'], boundaries[i - 1]['test_start'])

    def test_empty_classes_handled(self) -> None:
        """When all labels are the same class, metrics must report warning not crash."""
        preds = [
            _pred('2026-01-10', 35.0, 76.0, 0.3, evidence_available=True),
            _pred('2026-01-11', 35.0, 76.0, 0.4, evidence_available=True),
            _pred('2026-01-12', 35.0, 76.0, 0.3, evidence_available=True),
            _pred('2026-01-13', 35.0, 76.0, 0.4, evidence_available=True),
        ]
        events: list[dict] = []
        result = evaluate_paired(preds, events, n_splits=2)

        self.assertNotIn('error', result)
        for fold in result['baseline_metrics']:
            self.assertIn('warning', fold)

    def test_insufficient_temporal_history_fails_closed(self) -> None:
        result = evaluate_paired(
            [_pred('2026-01-10', 35.0, 76.0, 0.3)],
            [],
        )
        self.assertIn('error', result)
        self.assertIn('3 unique forecast dates', result['error'])
        self.assertFalse(result['can_promote_model'])

    def test_report_contains_input_and_lineage_hashes(self) -> None:
        preds = [
            _pred(f'2026-01-{day:02d}', 35.0, 76.0, 0.4)
            for day in range(1, 7)
        ]
        result = evaluate_paired(preds, [])
        self.assertEqual(len(result['prediction_source_hash']), 64)
        self.assertEqual(len(result['event_source_hash']), 64)
        self.assertEqual(result['feature_snapshot_hashes'], ['a' * 64])
        self.assertEqual(result['evidence_source_hashes'], ['b' * 64])
        self.assertEqual(result['evidence_completeness'], result['overall_coverage'])

    def test_paired_records_correctness(self) -> None:
        """Baseline and gated metrics must be computed from different subsets."""
        preds = [
            _pred('2026-01-10', 35.0, 76.0, 0.9, evidence_available=True),
            _pred('2026-01-11', 35.0, 76.0, 0.9, evidence_available=False),
            _pred('2026-01-12', 35.0, 76.0, 0.9, evidence_available=True),
            _pred('2026-01-13', 35.0, 76.0, 0.9, evidence_available=True),
            _pred('2026-01-14', 35.0, 76.0, 0.1, evidence_available=True),
            _pred('2026-01-15', 35.0, 76.0, 0.1, evidence_available=True),
        ]
        events = [_event('2026-01-10', 35.01, 76.01)]
        result = evaluate_paired(preds, events, n_splits=2)

        self.assertNotIn('error', result)
        self.assertTrue(result['evaluation_only'])
        self.assertFalse(result['can_promote_model'])
        self.assertIn('source_hash', result)
        self.assertEqual(len(result['source_hash']), 64)

    def test_all_abstain_produces_zero_coverage(self) -> None:
        """When no evidence is available, coverage must be 0 and abstention 1."""
        preds = [
            _pred('2026-01-10', 35.0, 76.0, 0.9, evidence_available=False),
            _pred('2026-01-11', 35.0, 76.0, 0.9, evidence_available=False),
            _pred('2026-01-12', 35.0, 76.0, 0.9, evidence_available=False),
            _pred('2026-01-13', 35.0, 76.0, 0.9, evidence_available=False),
        ]
        events = [_event('2026-01-10', 35.01, 76.01)]
        result = evaluate_paired(preds, events, n_splits=2)

        self.assertEqual(result['overall_coverage'], 0.0)
        self.assertEqual(result['overall_abstention_rate'], 1.0)


class TestComputeMetrics(unittest.TestCase):
    def test_metrics_returned_correctly(self) -> None:
        y_true = np.array([1, 0, 1, 0])
        y_prob = np.array([0.9, 0.1, 0.8, 0.2])
        y_pred = np.array([1, 0, 1, 0])
        m = _compute_metrics(y_true, y_prob, y_pred)
        self.assertEqual(m['true_positives'], 2)
        self.assertEqual(m['false_positives'], 0)
        self.assertEqual(m['false_negatives'], 0)
        self.assertEqual(m['true_negatives'], 2)
        self.assertAlmostEqual(m['precision'], 1.0)
        self.assertAlmostEqual(m['recall'], 1.0)


class TestStableHash(unittest.TestCase):
    def test_hash_is_deterministic(self) -> None:
        payload = {'a': 1, 'b': [2, 3]}
        h1 = _stable_hash(payload)
        h2 = _stable_hash(payload)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


class TestFailClosedEdgeCases(unittest.TestCase):
    """Tests for Codex-added fail-closed paths in evaluate_paired."""

    def test_n_splits_below_2_rejected(self) -> None:
        preds = [
            _pred('2026-01-10', 35.0, 76.0, 0.9),
            _pred('2026-01-11', 35.0, 76.0, 0.8),
            _pred('2026-01-12', 35.0, 76.0, 0.7),
        ]
        result = evaluate_paired(preds, [], n_splits=1)
        self.assertIn('error', result)
        self.assertIn('n_splits must be at least 2', result['error'])
        self.assertTrue(result['evaluation_only'])
        self.assertFalse(result['can_promote_model'])

    def test_insufficient_unique_dates_rejected(self) -> None:
        preds = [
            _pred('2026-01-10', 35.0, 76.0, 0.9),
            _pred('2026-01-10', 36.0, 77.0, 0.8),
        ]
        result = evaluate_paired(preds, [], n_splits=2)
        self.assertIn('error', result)
        self.assertIn('At least 3 unique forecast dates', result['error'])
        self.assertEqual(result['n_unique_forecast_dates'], 1)

    def test_empty_predictions_returns_error_with_hashes(self) -> None:
        result = evaluate_paired([], [])
        self.assertIn('error', result)
        self.assertIn('prediction_source_hash', result)
        self.assertTrue(result['evaluation_only'])

    def test_evidence_completeness_in_output(self) -> None:
        preds = [
            _pred(f'2026-01-{d:02d}', 35.0, 76.0, 0.5 + d * 0.01, evidence_available=(d % 2 == 0))
            for d in range(1, 8)
        ]
        events = [_event('2026-01-03', 35.01, 76.01)]
        result = evaluate_paired(preds, events, n_splits=2)
        self.assertNotIn('error', result)
        self.assertIn('evidence_completeness', result)
        self.assertGreater(result['evidence_completeness'], 0.0)
        self.assertLess(result['evidence_completeness'], 1.0)

    def test_input_hashes_in_output(self) -> None:
        preds = [
            _pred(f'2026-01-{d:02d}', 35.0, 76.0, 0.5, evidence_available=True)
            for d in range(1, 8)
        ]
        events = [_event('2026-01-03', 35.01, 76.01)]
        result = evaluate_paired(preds, events, n_splits=2)
        self.assertNotIn('error', result)
        self.assertIn('prediction_source_hash', result)
        self.assertIn('event_source_hash', result)
        self.assertEqual(len(result['prediction_source_hash']), 64)
        self.assertEqual(len(result['event_source_hash']), 64)


if __name__ == '__main__':
    unittest.main()
