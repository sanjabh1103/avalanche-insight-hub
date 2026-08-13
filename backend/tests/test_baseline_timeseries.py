"""Tests for baseline time-series retrieval."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone


class TestBaselineTimeseries(unittest.TestCase):
    def setUp(self) -> None:
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'true'
        import importlib
        import backend.common.baseline_timeseries as mod
        importlib.reload(mod)
        self.mod = mod

    def tearDown(self) -> None:
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'false'
        import importlib
        import backend.common.baseline_timeseries as mod
        importlib.reload(mod)

    def test_disabled_returns_empty(self) -> None:
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'false'
        import importlib
        import backend.common.baseline_timeseries as mod
        importlib.reload(mod)
        result = mod.get_baseline_timeseries('r', 'c', 'weather')
        self.assertEqual(len(result.points), 0)
        self.assertIn('Decision-support', result.disclaimer)

    def test_joins_observations_with_baselines(self) -> None:
        get_baseline_timeseries = self.mod.get_baseline_timeseries
        obs_rows = [
            {'cell_id': 'c1', 'sensor': 'weather', 'value': 1.2, 'acquisition_time': '2026-01-10T00:00:00Z', 'freshness_hours': 3.0, 'quality_state': 'verified'},
            {'cell_id': 'c1', 'sensor': 'weather', 'value': 1.5, 'acquisition_time': '2026-01-11T00:00:00Z', 'freshness_hours': 3.0, 'quality_state': 'verified'},
            {'cell_id': 'c1', 'sensor': 'weather', 'value': 0.8, 'acquisition_time': '2026-01-12T00:00:00Z', 'freshness_hours': 3.0, 'quality_state': 'verified'},
        ]
        baseline_rows = [
            {'cell_id': 'c1', 'sensor': 'weather', 'as_of_date': '2026-01-10', 'p25': 0.9, 'p50': 1.1, 'p75': 1.3, 'std': 0.2},
            {'cell_id': 'c1', 'sensor': 'weather', 'as_of_date': '2026-01-11', 'p25': 0.95, 'p50': 1.15, 'p75': 1.35, 'std': 0.2},
            {'cell_id': 'c1', 'sensor': 'weather', 'as_of_date': '2026-01-12', 'p25': 1.0, 'p50': 1.2, 'p75': 1.4, 'std': 0.2},
        ]
        result = get_baseline_timeseries('r', 'c1', 'weather', observation_rows=obs_rows, baseline_rows=baseline_rows)
        self.assertEqual(len(result.points), 3)
        self.assertEqual(result.points[0].date, '2026-01-10')
        self.assertAlmostEqual(result.points[0].p50, 1.1)
        self.assertAlmostEqual(result.points[0].observed, 1.2)
        self.assertAlmostEqual(result.points[0].residual_zscore or 0, 0.5, places=1)
        self.assertEqual(result.points[2].date, '2026-01-12')

    def test_filters_by_cell_and_sensor(self) -> None:
        get_baseline_timeseries = self.mod.get_baseline_timeseries
        obs_rows = [
            {'cell_id': 'c1', 'sensor': 'weather', 'value': 1.0, 'acquisition_time': '2026-01-10T00:00:00Z'},
            {'cell_id': 'c2', 'sensor': 'weather', 'value': 2.0, 'acquisition_time': '2026-01-10T00:00:00Z'},
            {'cell_id': 'c1', 'sensor': 'sar', 'value': 3.0, 'acquisition_time': '2026-01-10T00:00:00Z'},
        ]
        result = get_baseline_timeseries('r', 'c1', 'weather', observation_rows=obs_rows)
        self.assertEqual(len(result.points), 1)
        self.assertEqual(result.points[0].sensor, 'weather')

    def test_max_points_limit(self) -> None:
        get_baseline_timeseries = self.mod.get_baseline_timeseries
        obs_rows = [
            {'cell_id': 'c1', 'sensor': 'weather', 'value': float(i), 'acquisition_time': f'2026-01-{i+1:02d}T00:00:00Z'}
            for i in range(10)
        ]
        result = get_baseline_timeseries('r', 'c1', 'weather', observation_rows=obs_rows, max_points=5)
        self.assertEqual(len(result.points), 5)
        self.assertEqual(result.points[0].date, '2026-01-06')
        self.assertEqual(result.points[4].date, '2026-01-10')

    def test_to_dict_serialization(self) -> None:
        get_baseline_timeseries = self.mod.get_baseline_timeseries
        result = get_baseline_timeseries('r', 'c1', 'weather')
        d = result.to_dict()
        self.assertEqual(d['region_key'], 'r')
        self.assertEqual(d['cell_id'], 'c1')
        self.assertEqual(d['sensor'], 'weather')
        self.assertIsInstance(d['points'], list)
        self.assertIn('Decision-support', d['disclaimer'])


if __name__ == '__main__':
    unittest.main()
