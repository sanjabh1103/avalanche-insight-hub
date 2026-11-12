"""Tests for active-learning feedback module."""
from __future__ import annotations

import unittest

from backend.common.active_learning_feedback import (
    ScientistFeedback,
    DriftSignal,
    RetrainingCandidate,
    record_feedback,
    compute_drift_signals,
    generate_retraining_candidates,
)


class TestRecordFeedback(unittest.TestCase):
    def test_valid_feedback(self):
        fb = ScientistFeedback(
            cell_id='c1',
            region_key='r1',
            scientist_id='sci_1',
            decision='confirmed',
        )
        result = record_feedback(fb)
        self.assertEqual(result['cell_id'], 'c1')
        self.assertEqual(result['decision'], 'confirmed')
        self.assertEqual(result['version'], 1)

    def test_invalid_decision_raises(self):
        fb = ScientistFeedback(decision='invalid')
        with self.assertRaises(ValueError):
            record_feedback(fb)


class TestComputeDriftSignals(unittest.TestCase):
    def test_no_feedback(self):
        signals = compute_drift_signals('r1', [], {})
        self.assertEqual(signals, [])

    def test_all_agree(self):
        feedback = [
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'confirmed'},
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'confirmed'},
        ]
        preds = {'c1': [0.3, 0.2]}
        signals = compute_drift_signals('r1', feedback, preds)
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].drift_score, 0.0)

    def test_all_disagree(self):
        feedback = [
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'anomaly'},
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'anomaly'},
        ]
        preds = {'c1': [0.2, 0.1]}
        signals = compute_drift_signals('r1', feedback, preds)
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].drift_score, 1.0)

    def test_partial_disagreement(self):
        feedback = [
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'confirmed'},
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'anomaly'},
        ]
        preds = {'c1': [0.3, 0.3]}
        signals = compute_drift_signals('r1', feedback, preds)
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].drift_score, 0.5)

    def test_filters_by_region(self):
        feedback = [
            {'cell_id': 'c1', 'region_key': 'r1', 'decision': 'confirmed'},
            {'cell_id': 'c2', 'region_key': 'r2', 'decision': 'confirmed'},
        ]
        signals = compute_drift_signals('r1', feedback, {})
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].cell_id, 'c1')


class TestRetrainingCandidates(unittest.TestCase):
    def test_above_threshold(self):
        signals = [
            DriftSignal(cell_id='c1', region_key='r1', drift_score=0.5),
            DriftSignal(cell_id='c2', region_key='r1', drift_score=0.1),
        ]
        candidates = generate_retraining_candidates('r1', signals, drift_threshold=0.3)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].cell_id, 'c1')

    def test_sorted_by_drift(self):
        signals = [
            DriftSignal(cell_id='c1', region_key='r1', drift_score=0.4),
            DriftSignal(cell_id='c2', region_key='r1', drift_score=0.8),
        ]
        candidates = generate_retraining_candidates('r1', signals, drift_threshold=0.3)
        self.assertEqual(candidates[0].cell_id, 'c2')
        self.assertEqual(candidates[1].cell_id, 'c1')

    def test_none_above_threshold(self):
        signals = [
            DriftSignal(cell_id='c1', region_key='r1', drift_score=0.1),
        ]
        candidates = generate_retraining_candidates('r1', signals, drift_threshold=0.3)
        self.assertEqual(candidates, [])


class TestSerialization(unittest.TestCase):
    def test_feedback_to_dict(self):
        fb = ScientistFeedback(cell_id='c1', region_key='r1', scientist_id='s1', decision='anomaly')
        d = fb.to_dict()
        self.assertEqual(d['cell_id'], 'c1')
        self.assertIn('created_at', d)

    def test_drift_signal_to_dict(self):
        ds = DriftSignal(cell_id='c1', region_key='r1', drift_score=0.5)
        d = ds.to_dict()
        self.assertEqual(d['drift_score'], 0.5)

    def test_retraining_candidate_to_dict(self):
        rc = RetrainingCandidate(cell_id='c1', region_key='r1', drift_score=0.5, reason='test')
        d = rc.to_dict()
        self.assertEqual(d['reason'], 'test')


if __name__ == '__main__':
    unittest.main()
