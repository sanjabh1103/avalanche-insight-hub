"""Tests for NASA GIBS snow-cover ingestion."""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from backend.common.gibs_ingestion import (
    GibsSnowCoverResult,
    _build_tile_url,
    _lat_lng_to_tile,
    fetch_gibs_snow_cover,
    fetch_gibs_snow_cover_batch,
)


class TileCoordinateTests(unittest.TestCase):
    def test_lat_lng_to_tile_returns_valid_coords(self) -> None:
        x, y = _lat_lng_to_tile(28.0, 86.0, zoom=8)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLess(x, 256)
        self.assertLess(y, 256)

    def test_equator_at_zero_returns_center_tile(self) -> None:
        x, y = _lat_lng_to_tile(0.0, 0.0, zoom=8)
        self.assertEqual(x, 128)
        self.assertEqual(y, 128)


class TileUrlTests(unittest.TestCase):
    def test_build_tile_url_contains_layer_and_date(self) -> None:
        url = _build_tile_url(28.0, 86.0, date(2026, 1, 15), zoom=8)
        self.assertIn('MODIS_Terra_Snow_Cover', url)
        self.assertIn('2026-01-15', url)
        self.assertIn('gibs.earthdata.nasa.gov', url)


class FetchSnowCoverTests(unittest.TestCase):
    def test_returns_none_when_disabled(self) -> None:
        with patch('backend.common.gibs_ingestion.GIBS_ENABLED', False):
            result = fetch_gibs_snow_cover(28.0, 86.0)
        self.assertIsNone(result)

    def test_returns_result_when_enabled(self) -> None:
        fake_png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_response = MagicMock()
        mock_response.read.return_value = fake_png
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('backend.common.gibs_ingestion.GIBS_ENABLED', True):
            with patch('urllib.request.urlopen', return_value=mock_response):
                with patch('backend.common.gibs_ingestion._compute_snow_fraction_from_tile', return_value=0.65):
                    result = fetch_gibs_snow_cover(28.0, 86.0, date(2026, 1, 15))

        self.assertIsNotNone(result)
        self.assertEqual(result.snow_cover_fraction, 0.65)
        self.assertEqual(result.date, '2026-01-15')
        self.assertIn('MODIS_Terra_Snow_Cover', result.tile_url)

    def test_batch_returns_none_for_all_when_disabled(self) -> None:
        with patch('backend.common.gibs_ingestion.GIBS_ENABLED', False):
            results = fetch_gibs_snow_cover_batch([(28.0, 86.0), (34.0, 76.0)])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r is None for r in results))


if __name__ == '__main__':
    unittest.main()
