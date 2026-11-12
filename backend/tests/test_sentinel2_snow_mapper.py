"""Tests for sentinel2_snow_mapper.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.common.sentinel2_snow_mapper import (
    S2SnowResult,
    S2_SNOW_ENABLED,
    S2_NDSI_SNOW_THRESHOLD,
    compute_ndsi,
    compute_ndvi,
    compute_evi,
    is_snow,
    map_s2_snow_for_cell,
    map_s2_snow_batch,
    _has_credentials,
    _scene_lineage_sha256,
)


class TestNDSI(unittest.TestCase):
    def test_snow_ndsi(self):
        ndsi = compute_ndsi(0.5, 0.1)
        self.assertAlmostEqual(ndsi, 0.6667, places=3)
        self.assertTrue(is_snow(ndsi))

    def test_no_snow_ndsi(self):
        ndsi = compute_ndsi(0.2, 0.3)
        self.assertAlmostEqual(ndsi, -0.2, places=1)
        self.assertFalse(is_snow(ndsi))

    def test_none_inputs(self):
        self.assertIsNone(compute_ndsi(None, 0.1))
        self.assertIsNone(compute_ndsi(0.5, None))

    def test_zero_denominator(self):
        self.assertIsNone(compute_ndsi(0.0, 0.0))


class TestNDVI(unittest.TestCase):
    def test_high_ndvi(self):
        ndvi = compute_ndvi(0.8, 0.2)
        self.assertAlmostEqual(ndvi, 0.6, places=1)

    def test_none_inputs(self):
        self.assertIsNone(compute_ndvi(None, 0.2))


class TestEVI(unittest.TestCase):
    def test_evi(self):
        evi = compute_evi(0.5, 0.1, 0.05)
        # EVI = 2.5 * (0.5 - 0.1) / (0.5 + 6*0.1 - 7.5*0.05 + 1) = 1.0 / 1.725
        self.assertAlmostEqual(evi, 0.5797, places=3)

    def test_none_inputs(self):
        self.assertIsNone(compute_evi(None, 0.1, 0.05))


class TestS2SnowResult(unittest.TestCase):
    def test_to_dict(self):
        result = S2SnowResult(
            cell_id='cell_0',
            ndsi=0.6,
            snow_cover_fraction=0.8,
            ndvi=0.3,
            evi=0.2,
            scene_id='S2A_MSIL2A_20260101',
            acquisition_time='2026-01-01T10:00:00Z',
        )
        d = result.to_dict()
        self.assertEqual(d['cell_id'], 'cell_0')
        self.assertEqual(d['ndsi'], 0.6)
        self.assertEqual(d['source'], 'sentinel2_sr')

    def test_scene_lineage_hash_requires_scene_and_time(self) -> None:
        lineage_hash = _scene_lineage_sha256('S2A_TEST', '2026-01-01T10:00:00+00:00')
        self.assertEqual(len(lineage_hash), 64)
        self.assertIsNone(_scene_lineage_sha256('S2A_TEST', None))
        self.assertIsNone(_scene_lineage_sha256(None, '2026-01-01T10:00:00+00:00'))


class TestCredentialGated(unittest.TestCase):
    def test_cloud_probability_mask_uses_official_band_and_threshold(self) -> None:
        import backend.common.sentinel2_snow_mapper as s2

        ee = MagicMock()
        image = MagicMock()
        cloud_image = MagicMock()
        cloud_probability = MagicMock()
        scl = MagicMock()
        ee.Image.side_effect = lambda value: value
        image.get.return_value = cloud_image
        image.select.return_value = scl
        cloud_image.select.return_value = cloud_probability
        cloud_probability.rename.return_value = cloud_probability
        cloud_probability.lt.return_value = MagicMock()
        scl.neq.return_value = MagicMock()
        image.addBands.return_value = image
        image.updateMask.return_value = image

        result = s2._mask_cloud_probability(ee, image)

        self.assertIs(result, image)
        cloud_image.select.assert_called_once_with('probability')
        cloud_probability.lt.assert_called_once_with(40)
        image.updateMask.assert_called_once()

    def test_disabled_returns_none(self):
        import backend.common.sentinel2_snow_mapper as s2
        original = s2.S2_SNOW_ENABLED
        try:
            s2.S2_SNOW_ENABLED = False
            result = map_s2_snow_for_cell(
                cell_id='cell_0',
                lat=39.5,
                lng=-106.5,
                target_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            )
            self.assertIsNone(result)
        finally:
            s2.S2_SNOW_ENABLED = original

    def test_batch_disabled_returns_empty(self):
        import backend.common.sentinel2_snow_mapper as s2
        original = s2.S2_SNOW_ENABLED
        try:
            s2.S2_SNOW_ENABLED = False
            results = map_s2_snow_batch(
                cells=[{'cell_id': 'c0', 'lat': 39.5, 'lng': -106.5}],
                target_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            )
            self.assertEqual(results, {})
        finally:
            s2.S2_SNOW_ENABLED = original

    def test_enabled_no_creds_returns_none(self):
        import backend.common.sentinel2_snow_mapper as s2
        original_flag = s2.S2_SNOW_ENABLED
        original_creds = s2._has_credentials
        try:
            s2.S2_SNOW_ENABLED = True
            s2._has_credentials = lambda: False
            result = map_s2_snow_for_cell(
                cell_id='cell_0',
                lat=39.5,
                lng=-106.5,
                target_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            )
            self.assertIsNone(result)
        finally:
            s2.S2_SNOW_ENABLED = original_flag
            s2._has_credentials = original_creds


if __name__ == '__main__':
    unittest.main()
