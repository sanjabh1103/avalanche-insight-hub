"""Tests for snow_baselines.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from backend.common.snow_baselines import (
    BaselineStats,
    CellTerrainSignature,
    WINDOW_30D,
    WINDOW_90D,
    WINDOW_SEASONAL,
    compute_baseline_stats,
    find_pseudo_controls,
    filter_history_by_window,
    build_cell_baselines,
    ELEVATION_BAND_M,
    ASPECT_BAND_DEG,
    SLOPE_BAND_DEG,
)


class TestBaselineStats(unittest.TestCase):
    def test_empty_values(self):
        stats = compute_baseline_stats([], 'cell_0', 'sar', WINDOW_30D)
        self.assertEqual(stats.count, 0)
        self.assertFalse(stats.is_valid)
        self.assertIsNone(stats.z_score(0.5))

    def test_single_value(self):
        stats = compute_baseline_stats([0.5], 'cell_0', 'sar', WINDOW_30D)
        self.assertEqual(stats.count, 1)
        self.assertEqual(stats.p50, 0.5)
        self.assertEqual(stats.std, 0.0)
        self.assertFalse(stats.is_valid)  # std=0 → not valid

    def test_multiple_values(self):
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        stats = compute_baseline_stats(values, 'cell_0', 'sar', WINDOW_90D)
        self.assertEqual(stats.count, 10)
        self.assertTrue(stats.is_valid)
        self.assertAlmostEqual(stats.mean, 0.55, places=2)
        self.assertAlmostEqual(stats.p50, 0.55, places=1)
        z = stats.z_score(0.55)
        self.assertAlmostEqual(z, 0.0, places=2)

    def test_z_score(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        stats = compute_baseline_stats(values, 'cell_0', 'weather', WINDOW_30D)
        self.assertTrue(stats.is_valid)
        z = stats.z_score(5.0)
        self.assertAlmostEqual(z, 1.2649, places=3)

    def test_invalid_window_raises(self):
        with self.assertRaises(ValueError):
            compute_baseline_stats([1.0], 'cell_0', 'sar', 'bogus')

    def test_to_dict(self):
        stats = compute_baseline_stats([0.1, 0.2, 0.3], 'cell_0', 'sar', WINDOW_30D, control_cell_ids=['cell_1'])
        d = stats.to_dict()
        self.assertEqual(d['cell_id'], 'cell_0')
        self.assertEqual(d['sensor'], 'sar')
        self.assertIn('cell_1', d['control_cell_ids'])


class TestPseudoControls(unittest.TestCase):
    def test_matching_cells(self):
        target = CellTerrainSignature(cell_id='cell_0', elevation_m=3000, aspect_deg=180, slope_deg=30)
        candidates = [
            CellTerrainSignature(cell_id='cell_1', elevation_m=3100, aspect_deg=190, slope_deg=32),
            CellTerrainSignature(cell_id='cell_2', elevation_m=3500, aspect_deg=90, slope_deg=45),
            CellTerrainSignature(cell_id='cell_3', elevation_m=2950, aspect_deg=175, slope_deg=28),
        ]
        controls = find_pseudo_controls(target, candidates)
        self.assertIn('cell_1', controls)
        self.assertIn('cell_3', controls)
        self.assertNotIn('cell_2', controls)

    def test_max_controls_limit(self):
        target = CellTerrainSignature(cell_id='cell_0', elevation_m=3000, aspect_deg=180, slope_deg=30)
        candidates = [
            CellTerrainSignature(cell_id=f'cell_{i}', elevation_m=3000, aspect_deg=180, slope_deg=30)
            for i in range(1, 10)
        ]
        controls = find_pseudo_controls(target, candidates, max_controls=3)
        self.assertEqual(len(controls), 3)

    def test_excludes_self(self):
        target = CellTerrainSignature(cell_id='cell_0', elevation_m=3000, aspect_deg=180, slope_deg=30)
        candidates = [target]
        controls = find_pseudo_controls(target, candidates)
        self.assertEqual(controls, [])


class TestFilterHistoryByWindow(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
        self.history = [
            (self.now - timedelta(days=5), 0.5),
            (self.now - timedelta(days=20), 0.3),
            (self.now - timedelta(days=60), 0.4),
            (self.now - timedelta(days=100), 0.2),
        ]

    def test_30d_window(self):
        values = filter_history_by_window(self.history, WINDOW_30D, self.now)
        self.assertEqual(len(values), 2)  # 5d and 20d

    def test_90d_window(self):
        values = filter_history_by_window(self.history, WINDOW_90D, self.now)
        self.assertEqual(len(values), 3)  # 5d, 20d, 60d

    def test_seasonal_window(self):
        seasonal_history = [
            (datetime(2025, 7, 1, tzinfo=timezone.utc), 0.6),
            (datetime(2025, 7, 10, tzinfo=timezone.utc), 0.7),
            (datetime(2025, 12, 1, tzinfo=timezone.utc), 0.1),
        ]
        values = filter_history_by_window(seasonal_history, WINDOW_SEASONAL, self.now)
        self.assertEqual(len(values), 2)  # July 1 and July 10 are within ±15 days


class TestBuildCellBaselines(unittest.TestCase):
    def test_returns_empty_when_disabled(self):
        import backend.common.snow_baselines as sb
        original = sb.VERIFICATION_SPINE_ENABLED
        try:
            sb.VERIFICATION_SPINE_ENABLED = False
            result = build_cell_baselines('cell_0', 'sar', [], datetime.now(timezone.utc))
            self.assertEqual(result, {})
        finally:
            sb.VERIFICATION_SPINE_ENABLED = original


if __name__ == '__main__':
    unittest.main()
