"""Tests for nisar_adapter.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.nisar_adapter import (
    NISARAdapter,
    NisarSweResult,
    NISAR_SHADOW_ENABLED,
)


class TestNISARAdapter(unittest.TestCase):
    def setUp(self):
        import backend.common.nisar_adapter as na
        self._original_flag = na.NISAR_SHADOW_ENABLED
        self._original_token = na.EARTHDATA_TOKEN
        na.NISAR_SHADOW_ENABLED = True
        na.EARTHDATA_TOKEN = 'test_token'
        self.adapter = NISARAdapter()

    def tearDown(self):
        import backend.common.nisar_adapter as na
        na.NISAR_SHADOW_ENABLED = self._original_flag
        na.EARTHDATA_TOKEN = self._original_token

    def test_sensor_name(self):
        self.assertEqual(self.adapter.sensor_name, 'nisar_l_band')

    def test_available_with_creds(self):
        self.assertTrue(self.adapter.available())

    def test_not_available_without_flag(self):
        import backend.common.nisar_adapter as na
        na.NISAR_SHADOW_ENABLED = False
        self.assertFalse(self.adapter.available())

    def test_not_available_without_token(self):
        import backend.common.nisar_adapter as na
        na.EARTHDATA_TOKEN = ''
        self.assertFalse(self.adapter.available())

    def test_query_returns_empty_when_disabled(self):
        import backend.common.nisar_adapter as na
        na.NISAR_SHADOW_ENABLED = False
        results = self.adapter.query(
            region_key='great_himalaya',
            bbox=(30.0, 78.0, 31.0, 79.0),
            date_range=(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)),
        )
        self.assertEqual(results, [])

    def test_retrieve_returns_none(self):
        result = self.adapter.retrieve('NISAR_20260101')
        self.assertIsNone(result)

    def test_normalize(self):
        from backend.common.remote_sensing_adapter import SceneData
        scene = SceneData(scene_id='NISAR_20260101', sensor='nisar_l_band')
        result = self.adapter.normalize(scene)
        self.assertEqual(result['source'], 'nisar_l_band')
        self.assertIsNone(result['snow_depth_m'])

    def test_ionosphere_correction_stub(self):
        result = self.adapter.ionosphere_correction_stub({'phase': 0.5})
        self.assertTrue(result['ionosphere_corrected'])
        self.assertEqual(result['phase'], 0.5)

    def test_phase_unwrap_stub(self):
        result = self.adapter.phase_unwrap_stub({'wrapped': True})
        self.assertEqual(result, {'wrapped': True})

    def test_slope_correlated_swe_change_stub(self):
        result = self.adapter.slope_correlated_swe_change_stub(
            interferogram={'phase': 0.5},
            slope_deg=30.0,
            aspect_deg=180.0,
        )
        self.assertIsNone(result)


class TestNisarSweResult(unittest.TestCase):
    def test_to_dict(self):
        result = NisarSweResult(
            scene_id='test_scene',
            swe_change_mm=12.5,
            coherence=0.85,
            unwrapped_phase=0.5,
            ionosphere_corrected=True,
            slope_corrected=False,
            shadow_only=True,
        )
        d = result.to_dict()
        self.assertEqual(d['scene_id'], 'test_scene')
        self.assertEqual(d['swe_change_mm'], 12.5)
        self.assertTrue(d['shadow_only'])


class TestNisarEnhancedMethods(unittest.TestCase):
    def setUp(self):
        import backend.common.nisar_adapter as na
        self._original_flag = na.NISAR_SHADOW_ENABLED
        na.NISAR_SHADOW_ENABLED = False
        self.adapter = NISARAdapter()

    def tearDown(self):
        import backend.common.nisar_adapter as na
        na.NISAR_SHADOW_ENABLED = self._original_flag

    def test_ionosphere_correction_adds_flags(self):
        result = self.adapter._apply_ionosphere_correction({'phase': 1.0})
        self.assertTrue(result['ionosphere_corrected'])
        self.assertEqual(result['correction_method'], 'range_spectral_split')

    def test_slope_correction_with_slope(self):
        import math
        corrected = self.adapter._slope_corrected_phase(1.0, {'slope_deg': 30.0})
        expected = 1.0 / max(math.cos(math.radians(30.0)), 0.1)
        self.assertAlmostEqual(corrected, expected)

    def test_slope_correction_flat(self):
        corrected = self.adapter._slope_corrected_phase(1.0, {'slope_deg': 0.0})
        self.assertAlmostEqual(corrected, 1.0)

    def test_compute_swe_shadow_only(self):
        result = self.adapter._compute_interferometric_swe(
            {'scene_id': 's1', 'phase': 1.0, 'coherence': 0.9},
            {'phase': 0.5},
        )
        self.assertTrue(result.shadow_only)
        self.assertEqual(result.scene_id, 's1')
        self.assertTrue(result.ionosphere_corrected)
        self.assertFalse(result.slope_corrected)

    def test_compute_swe_with_dem(self):
        result = self.adapter._compute_interferometric_swe(
            {'scene_id': 's2', 'phase': 1.0, 'coherence': 0.8},
            {'phase': 0.3},
            dem={'slope_deg': 25.0},
        )
        self.assertTrue(result.slope_corrected)
        self.assertNotEqual(result.swe_change_mm, 0.0)


if __name__ == '__main__':
    unittest.main()
