"""Tests for cross-sensor calibration module."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.common.cross_sensor_calibration import (
    CalibrationPair,
    CalibrationMetrics,
    load_calibration_pairs,
    compute_calibration_metrics,
    apply_calibration_correction,
    CROSS_SENSOR_CALIBRATION_ENABLED,
)


class TestCalibrationMetrics(unittest.TestCase):
    def test_empty_pairs(self):
        metrics = compute_calibration_metrics([])
        self.assertEqual(metrics, [])

    def test_single_pair(self):
        pairs = [CalibrationPair('sar', 'reference', 'snow_depth', 'c1', 't1', 0.5, 0.5)]
        metrics = compute_calibration_metrics(pairs)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].count, 1)

    def test_bias_and_rmse(self):
        pairs = [
            CalibrationPair('sar', 'reference', 'snow_depth', 'c1', 't1', 0.52, 0.50),
            CalibrationPair('sar', 'reference', 'snow_depth', 'c2', 't2', 0.48, 0.50),
        ]
        metrics = compute_calibration_metrics(pairs)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].count, 2)
        self.assertAlmostEqual(metrics[0].bias, 0.0, places=5)
        self.assertAlmostEqual(metrics[0].rmse, 0.02, places=5)

    def test_correlation(self):
        pairs = [
            CalibrationPair('sar', 'reference', 'snow_depth', 'c1', 't1', 0.52, 0.50),
            CalibrationPair('sar', 'reference', 'snow_depth', 'c2', 't2', 0.48, 0.45),
            CalibrationPair('sar', 'reference', 'snow_depth', 'c3', 't3', 0.61, 0.58),
            CalibrationPair('sar', 'reference', 'snow_depth', 'c4', 't4', 0.55, 0.52),
        ]
        metrics = compute_calibration_metrics(pairs)
        self.assertGreater(metrics[0].correlation, 0.5)

    def test_slope_and_intercept(self):
        pairs = [
            CalibrationPair('sar', 'reference', 'snow_depth', 'c1', 't1', 1.0, 1.0),
            CalibrationPair('sar', 'reference', 'snow_depth', 'c2', 't2', 2.0, 2.0),
            CalibrationPair('sar', 'reference', 'snow_depth', 'c3', 't3', 3.0, 3.0),
        ]
        metrics = compute_calibration_metrics(pairs)
        self.assertAlmostEqual(metrics[0].slope, 1.0, places=3)
        self.assertAlmostEqual(metrics[0].intercept, 0.0, places=3)


class TestLoadCalibrationPairs(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        pairs = load_calibration_pairs('/nonexistent/path.csv')
        self.assertEqual(pairs, [])

    def test_loads_from_csv(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
            f.write('sensor_a,sensor_b,variable,cell_id,timestamp,value_a,value_b,reference_source\n')
            f.write('sar,reference,snow_depth,c1,t1,0.5,0.48,snowex\n')
            f.write('sar,reference,snow_depth,c2,t2,0.6,0.58,snowex\n')
            f.flush()
            pairs = load_calibration_pairs(f.name)
        os.unlink(f.name)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0].sensor_a, 'sar')
        self.assertAlmostEqual(pairs[0].value_a, 0.5)


class TestApplyCalibrationCorrection(unittest.TestCase):
    def setUp(self):
        os.environ['CROSS_SENSOR_CALIBRATION_ENABLED'] = 'true'
        import importlib
        import backend.common.cross_sensor_calibration as mod
        importlib.reload(mod)
        self.mod = mod

    def tearDown(self):
        os.environ['CROSS_SENSOR_CALIBRATION_ENABLED'] = 'false'
        import importlib
        import backend.common.cross_sensor_calibration as mod
        importlib.reload(mod)

    def test_applies_correction(self):
        metrics = [self.mod.CalibrationMetrics(
            sensor_a='sar', sensor_b='reference', variable='snow_depth',
            count=5, bias=0.02, rmse=0.03, correlation=0.95,
            slope=1.04, intercept=-0.01,
        )]
        corrected = self.mod.apply_calibration_correction(0.5, 'sar', metrics)
        self.assertAlmostEqual(corrected, 1.04 * 0.5 - 0.01, places=5)

    def test_no_correction_when_no_match(self):
        metrics = [self.mod.CalibrationMetrics(
            sensor_a='optical', sensor_b='reference', variable='snow_cover',
            count=5, slope=0.98, intercept=0.02,
        )]
        corrected = self.mod.apply_calibration_correction(0.5, 'sar', metrics)
        self.assertEqual(corrected, 0.5)

    def test_disabled_returns_original(self):
        os.environ['CROSS_SENSOR_CALIBRATION_ENABLED'] = 'false'
        import importlib
        import backend.common.cross_sensor_calibration as mod
        importlib.reload(mod)
        metrics = [mod.CalibrationMetrics(
            sensor_a='sar', sensor_b='reference', variable='snow_depth',
            slope=2.0, intercept=0.1,
        )]
        corrected = mod.apply_calibration_correction(0.5, 'sar', metrics)
        self.assertEqual(corrected, 0.5)


if __name__ == '__main__':
    unittest.main()
