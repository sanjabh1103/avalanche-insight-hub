"""Tests for icesat2_calibration.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.icesat2_calibration import (
    ICESat2Adapter,
    ICESat2CalibrationResult,
    ICESAT2_CALIBRATION_ENABLED,
)


class TestICESat2Adapter(unittest.TestCase):
    def setUp(self):
        import backend.common.icesat2_calibration as ic
        self._original_flag = ic.ICESAT2_CALIBRATION_ENABLED
        self._original_token = ic.EARTHDATA_TOKEN
        ic.ICESAT2_CALIBRATION_ENABLED = True
        ic.EARTHDATA_TOKEN = 'test_token'
        self.adapter = ICESat2Adapter()

    def tearDown(self):
        import backend.common.icesat2_calibration as ic
        ic.ICESAT2_CALIBRATION_ENABLED = self._original_flag
        ic.EARTHDATA_TOKEN = self._original_token

    def test_sensor_name(self):
        self.assertEqual(self.adapter.sensor_name, 'icesat2_atl06')

    def test_available_with_creds(self):
        self.assertTrue(self.adapter.available())

    def test_not_available_without_flag(self):
        import backend.common.icesat2_calibration as ic
        ic.ICESAT2_CALIBRATION_ENABLED = False
        self.assertFalse(self.adapter.available())

    def test_query_returns_empty_when_disabled(self):
        import backend.common.icesat2_calibration as ic
        ic.ICESAT2_CALIBRATION_ENABLED = False
        results = self.adapter.query(
            region_key='colorado_rockies',
            bbox=(38.0, -107.0, 39.0, -106.0),
            date_range=(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)),
        )
        self.assertEqual(results, [])

    def test_retrieve_returns_none(self):
        result = self.adapter.retrieve('ATL06_20260115')
        self.assertIsNone(result)

    def test_normalize(self):
        from backend.common.remote_sensing_adapter import SceneData
        scene = SceneData(scene_id='ATL06_20260115', sensor='icesat2_atl06')
        result = self.adapter.normalize(scene)
        self.assertEqual(result['source'], 'icesat2_atl06')

    def test_compute_snow_depth(self):
        depth = self.adapter.compute_snow_depth(atl06_height_m=3500.5, dem_height_m=3499.8)
        self.assertAlmostEqual(depth, 0.7, places=1)

    def test_compute_snow_depth_negative(self):
        depth = self.adapter.compute_snow_depth(atl06_height_m=3499.0, dem_height_m=3500.0)
        self.assertEqual(depth, 0.0)

    def test_compute_snow_depth_unrealistic(self):
        depth = self.adapter.compute_snow_depth(atl06_height_m=3510.5, dem_height_m=3499.8)
        self.assertIsNone(depth)  # 10.7m > 10.0 threshold, filtered

    def test_compute_snow_depth_none_inputs(self):
        self.assertIsNone(self.adapter.compute_snow_depth(atl06_height_m=None, dem_height_m=3500.0))


class TestICESat2CalibrationResult(unittest.TestCase):
    def test_to_dict(self):
        result = ICESat2CalibrationResult(
            track_id='ATL06_gt1l_20260115',
            snow_depth_m=0.85,
            uncertainty_m=0.08,
            lat=39.5,
            lng=-106.5,
        )
        d = result.to_dict()
        self.assertEqual(d['track_id'], 'ATL06_gt1l_20260115')
        self.assertEqual(d['snow_depth_m'], 0.85)
        self.assertEqual(d['source'], 'icesat2_atl06')


if __name__ == '__main__':
    unittest.main()
