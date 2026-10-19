"""Tests for s1_snow_depth.py."""
from __future__ import annotations

import unittest

from backend.common.s1_snow_depth import (
    S1SnowDepthResult,
    S1_DEPTH_ENABLED,
    compute_cross_ratio,
    apply_wet_snow_mask,
    calibrate_depth,
    estimate_s1_snow_depth,
)


class TestCrossRatio(unittest.TestCase):
    def test_basic(self):
        cr = compute_cross_ratio(-22.0, -18.0)
        self.assertAlmostEqual(cr, -4.0, places=1)

    def test_none_inputs(self):
        self.assertIsNone(compute_cross_ratio(None, -18.0))
        self.assertIsNone(compute_cross_ratio(-22.0, None))


class TestWetSnowMask(unittest.TestCase):
    def test_dry_snow_passes(self):
        result = apply_wet_snow_mask(cross_ratio=-4.0, wet_snow_fraction=0.2)
        self.assertEqual(result, -4.0)

    def test_wet_snow_masked(self):
        result = apply_wet_snow_mask(cross_ratio=-4.0, wet_snow_fraction=0.6)
        self.assertIsNone(result)

    def test_none_cross_ratio(self):
        self.assertIsNone(apply_wet_snow_mask(cross_ratio=None, wet_snow_fraction=0.1))


class TestCalibrateDepth(unittest.TestCase):
    def test_without_weather(self):
        depth, offset = calibrate_depth(cross_ratio=-4.0, weather_snow_depth_m=None)
        self.assertIsNotNone(depth)
        self.assertGreaterEqual(depth, 0.0)

    def test_with_weather(self):
        depth, offset = calibrate_depth(
            cross_ratio=-4.0,
            weather_snow_depth_m=0.5,
            calibration_scale=0.01,
        )
        self.assertAlmostEqual(depth, 0.5, places=2)

    def test_none_cross_ratio(self):
        depth, offset = calibrate_depth(cross_ratio=None, weather_snow_depth_m=0.5)
        self.assertIsNone(depth)


class TestEstimateS1SnowDepth(unittest.TestCase):
    def setUp(self):
        import backend.common.s1_snow_depth as s1
        self._original = s1.S1_DEPTH_ENABLED
        s1.S1_DEPTH_ENABLED = True

    def tearDown(self):
        import backend.common.s1_snow_depth as s1
        s1.S1_DEPTH_ENABLED = self._original

    def test_valid_inputs(self):
        result = estimate_s1_snow_depth(
            cell_id='cell_0',
            vh_db=-22.0,
            vv_db=-18.0,
            wet_snow_fraction=0.1,
            weather_snow_depth_m=0.5,
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.depth_index, -4.0, places=1)
        self.assertFalse(result.wet_snow_masked)

    def test_wet_snow_masked(self):
        result = estimate_s1_snow_depth(
            cell_id='cell_0',
            vh_db=-22.0,
            vv_db=-18.0,
            wet_snow_fraction=0.8,
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.wet_snow_masked)
        self.assertIsNone(result.snow_depth_m)

    def test_disabled_returns_none(self):
        import backend.common.s1_snow_depth as s1
        s1.S1_DEPTH_ENABLED = False
        result = estimate_s1_snow_depth(cell_id='cell_0', vh_db=-22.0, vv_db=-18.0)
        self.assertIsNone(result)

    def test_to_dict(self):
        result = S1SnowDepthResult(cell_id='cell_0', depth_index=-4.0, snow_depth_m=0.5)
        d = result.to_dict()
        self.assertEqual(d['cell_id'], 'cell_0')
        self.assertEqual(d['source'], 'sentinel1_cross_ratio')


if __name__ == '__main__':
    unittest.main()
