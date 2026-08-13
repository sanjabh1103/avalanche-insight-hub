"""Tests for active_learning.py."""
from __future__ import annotations

import unittest

from backend.common.active_learning import (
    ActiveLearningQueueRow,
    ACTIVE_LEARNING_ENABLED,
    compute_uncertainty_score,
    compute_anomaly_score,
    compute_sparsity_score,
    rank_cells_for_observation,
    emit_review_queue_rows,
)


class TestUncertaintyScore(unittest.TestCase):
    def test_conformal_span(self):
        cell = {'conformalLower': 0.2, 'conformalUpper': 0.8}
        score = compute_uncertainty_score(cell)
        self.assertAlmostEqual(score, 0.6, places=1)

    def test_uncertainty_span(self):
        cell = {'uncertaintySpan': 0.5}
        score = compute_uncertainty_score(cell)
        self.assertAlmostEqual(score, 0.5, places=1)

    def test_uncertainty_class_high(self):
        cell = {'uncertaintyClass': 'high'}
        score = compute_uncertainty_score(cell)
        self.assertEqual(score, 0.8)

    def test_uncertainty_class_medium(self):
        cell = {'uncertaintyClass': 'medium'}
        score = compute_uncertainty_score(cell)
        self.assertEqual(score, 0.5)

    def test_uncertainty_class_low(self):
        cell = {'uncertaintyClass': 'low'}
        score = compute_uncertainty_score(cell)
        self.assertEqual(score, 0.2)

    def test_no_data(self):
        cell = {}
        score = compute_uncertainty_score(cell)
        self.assertEqual(score, 0.0)

    def test_clamped_to_1(self):
        cell = {'conformalLower': 0.0, 'conformalUpper': 2.0}
        score = compute_uncertainty_score(cell)
        self.assertEqual(score, 1.0)


class TestAnomalyScore(unittest.TestCase):
    def test_direct_score(self):
        cell = {'anomaly_score': 0.7}
        score = compute_anomaly_score(cell)
        self.assertAlmostEqual(score, 0.7, places=1)

    def test_discrepancy_reasons(self):
        cell = {'discrepancy_reasons': ['reason1', 'reason2', 'reason3']}
        score = compute_anomaly_score(cell)
        self.assertAlmostEqual(score, 0.6, places=1)

    def test_no_data(self):
        cell = {}
        score = compute_anomaly_score(cell)
        self.assertEqual(score, 0.0)

    def test_clamped(self):
        cell = {'anomaly_score': 5.0}
        score = compute_anomaly_score(cell)
        self.assertEqual(score, 1.0)


class TestSparsityScore(unittest.TestCase):
    def test_no_coverage(self):
        cell = {'coverageFlags': {'sar_coverage_state': 'no_coverage'}}
        score = compute_sparsity_score(cell)
        self.assertGreaterEqual(score, 0.4)

    def test_full_coverage(self):
        cell = {'coverageFlags': {'sar_coverage_state': 'full_coverage'}}
        score = compute_sparsity_score(cell)
        self.assertLess(score, 0.4)

    def test_data_gaps(self):
        cell = {'coverageFlags': {'sar_coverage_state': 'low_coverage', 'data_gaps': ['gap1', 'gap2']}}
        score = compute_sparsity_score(cell)
        self.assertGreaterEqual(score, 0.6)

    def test_clamped_to_1(self):
        cell = {
            'coverageFlags': {
                'sar_coverage_state': 'no_coverage',
                'data_gaps': ['g1', 'g2', 'g3', 'g4'],
            },
        }
        score = compute_sparsity_score(cell)
        self.assertLessEqual(score, 1.0)


class TestRankCells(unittest.TestCase):
    def setUp(self):
        import backend.common.active_learning as al
        self._original = al.ACTIVE_LEARNING_ENABLED
        al.ACTIVE_LEARNING_ENABLED = True

    def tearDown(self):
        import backend.common.active_learning as al
        al.ACTIVE_LEARNING_ENABLED = self._original

    def test_ranks_by_priority(self):
        cells = [
            {'lat': 39.5, 'lng': -106.5, 'anomaly_score': 0.9, 'uncertaintyClass': 'high',
             'coverageFlags': {'sar_coverage_state': 'no_coverage'}},
            {'lat': 39.6, 'lng': -106.6, 'anomaly_score': 0.1, 'uncertaintyClass': 'low',
             'coverageFlags': {'sar_coverage_state': 'full_coverage'}},
        ]
        rows = rank_cells_for_observation(cells, region_key='colorado_rockies')
        self.assertEqual(len(rows), 2)
        self.assertGreater(rows[0].priority_score, rows[1].priority_score)
        self.assertEqual(rows[0].lat, 39.5)  # higher priority cell

    def test_max_queue_limit(self):
        cells = [{'lat': float(i), 'lng': float(i), 'anomaly_score': 0.5} for i in range(10)]
        rows = rank_cells_for_observation(cells, region_key='test', max_queue=3)
        self.assertEqual(len(rows), 3)

    def test_disabled_returns_empty(self):
        import backend.common.active_learning as al
        al.ACTIVE_LEARNING_ENABLED = False
        cells = [{'lat': 39.5, 'lng': -106.5, 'anomaly_score': 0.9}]
        rows = rank_cells_for_observation(cells, region_key='test')
        self.assertEqual(rows, [])

    def test_row_has_all_fields(self):
        cells = [{'lat': 39.5, 'lng': -106.5, 'anomaly_score': 0.7, 'cell_id': 'cell_0'}]
        rows = rank_cells_for_observation(cells, region_key='test')
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.cell_id, 'cell_0')
        self.assertEqual(row.region_key, 'test')
        self.assertIsNotNone(row.priority_score)
        self.assertIsNotNone(row.uncertainty_score)
        self.assertIsNotNone(row.anomaly_score)
        self.assertIsNotNone(row.sparsity_score)
        self.assertEqual(row.review_state, 'pending')

    def test_to_dict(self):
        row = ActiveLearningQueueRow(
            region_key='test',
            cell_id='cell_0',
            lat=39.5,
            lng=-106.5,
            priority_score=0.8,
            uncertainty_score=0.5,
            anomaly_score=0.7,
            sparsity_score=0.4,
        )
        d = row.to_dict()
        self.assertEqual(d['region_key'], 'test')
        self.assertEqual(d['priority_score'], 0.8)
        self.assertEqual(d['review_state'], 'pending')


class TestEmitReviewQueueRows(unittest.TestCase):
    def setUp(self):
        import backend.common.active_learning as al
        self._original = al.ACTIVE_LEARNING_ENABLED
        al.ACTIVE_LEARNING_ENABLED = True

    def tearDown(self):
        import backend.common.active_learning as al
        al.ACTIVE_LEARNING_ENABLED = self._original

    def test_emit_rows(self):
        rows = [
            ActiveLearningQueueRow(
                region_key='test', cell_id='c0', lat=39.5, lng=-106.5,
                priority_score=0.8, uncertainty_score=0.5, anomaly_score=0.7, sparsity_score=0.4,
            ),
        ]
        queue = emit_review_queue_rows(rows)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]['region_key'], 'test')
        self.assertEqual(queue[0]['review_state'], 'pending')

    def test_disabled_returns_empty(self):
        import backend.common.active_learning as al
        al.ACTIVE_LEARNING_ENABLED = False
        rows = [
            ActiveLearningQueueRow(
                region_key='test', cell_id='c0', lat=39.5, lng=-106.5,
                priority_score=0.8, uncertainty_score=0.5, anomaly_score=0.7, sparsity_score=0.4,
            ),
        ]
        queue = emit_review_queue_rows(rows)
        self.assertEqual(queue, [])


if __name__ == '__main__':
    unittest.main()
