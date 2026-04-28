from __future__ import annotations

import json
import tempfile
import unittest
import importlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import requests

from backend.common import real_features
from backend.common.real_features import (
    _fetch_open_meteo,
    _find_valid_window,
    compute_dynamic_lapse_profile,
    extract_cell_terrain,
    fetch_historical_weather_window,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object], *, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}', response=self)


class OpenMeteoTests(unittest.TestCase):
    def test_fetch_open_meteo_retries_rate_limits(self) -> None:
        transient = FakeResponse(429, {'error': 'rate limited'}, headers={'Retry-After': '0'})
        success = FakeResponse(200, {'hourly': {'time': []}})

        with patch.object(real_features.requests, 'get', side_effect=[transient, success]) as get_mock:
            with patch.object(real_features.time, 'sleep', return_value=None) as sleep_mock:
                payload = _fetch_open_meteo('https://example.test', params={'latitude': '1.0'})

        self.assertEqual(payload, {'hourly': {'time': []}})
        self.assertEqual(get_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_fetch_historical_weather_window_falls_back_to_archive_after_rate_limits(self) -> None:
        transient = FakeResponse(429, {'error': 'rate limited'}, headers={'Retry-After': '0'})
        archive_success = FakeResponse(
            200,
            {
                'hourly': {
                    'time': ['2026-04-21T00:00'],
                    'temperature_2m': [-6.0],
                    'precipitation': [1.2],
                    'snowfall': [0.8],
                    'snow_depth': [0.4],
                    'windspeed_10m': [18.0],
                    'winddirection_10m': [240.0],
                    'freezing_level_height': [None],
                }
            },
        )

        with patch.object(real_features.requests, 'get', side_effect=[transient, transient, transient, archive_success]) as get_mock:
            with patch.object(real_features.time, 'sleep', return_value=None) as sleep_mock:
                profile = fetch_historical_weather_window(
                    lat=-41.0,
                    lng=-71.0,
                    start=datetime(2026, 4, 21, tzinfo=timezone.utc),
                    end=datetime(2026, 4, 28, tzinfo=timezone.utc),
                )

        self.assertEqual(profile['source'], 'open_meteo_historical_archive_window_fallback_v1')
        self.assertEqual(len(profile['samples']), 1)
        self.assertEqual(profile['samples'][0].values['windspeed_10m'], 18.0)
        self.assertEqual(get_mock.call_count, 4)
        self.assertEqual(get_mock.call_args_list[-1].args[0], real_features.OPEN_METEO_ARCHIVE)
        self.assertEqual(sleep_mock.call_count, 2)


class DynamicLapseProfileTests(unittest.TestCase):
    def test_uses_bracketing_levels_for_standard_lapse(self) -> None:
        profile = {
            'temperature_2m': -2.0,
            'temperature_925hPa': -3.0,
            'temperature_850hPa': -6.0,
            'temperature_700hPa': -12.0,
            'geopotential_height_925hPa': 900.0,
            'geopotential_height_850hPa': 1500.0,
            'geopotential_height_700hPa': 3000.0,
        }

        lapse = compute_dynamic_lapse_profile(profile, terrain_elevation_m=1200.0)

        self.assertEqual(lapse['lower_level'], '925hPa')
        self.assertEqual(lapse['upper_level'], '850hPa')
        self.assertAlmostEqual(lapse['lapse_rate_c_per_m'], (-6.0 - (-3.0)) / (1500.0 - 900.0), places=6)
        self.assertFalse(lapse['is_inversion'])

    def test_preserves_positive_lapse_for_inversion(self) -> None:
        profile = {
            'temperature_2m': -8.0,
            'temperature_925hPa': -7.0,
            'temperature_850hPa': -4.0,
            'geopotential_height_925hPa': 900.0,
            'geopotential_height_850hPa': 1500.0,
        }

        lapse = compute_dynamic_lapse_profile(profile, terrain_elevation_m=1200.0)

        self.assertGreater(lapse['lapse_rate_c_per_m'], 0.0)
        self.assertTrue(lapse['is_inversion'])

    def test_falls_back_when_height_separation_is_too_small(self) -> None:
        profile = {
            'temperature_925hPa': -3.0,
            'temperature_850hPa': -4.0,
            'geopotential_height_925hPa': 1000.0,
            'geopotential_height_850hPa': 1050.0,
        }

        lapse = compute_dynamic_lapse_profile(profile, terrain_elevation_m=1025.0)

        self.assertAlmostEqual(lapse['lapse_rate_c_per_m'], -0.0065, places=6)
        self.assertEqual(lapse['method'], 'fallback_standard_lapse')


class ExtractCellTerrainTests(unittest.TestCase):
    def test_find_valid_window_clamps_out_of_bounds_indices(self) -> None:
        array = np.arange(25, dtype=np.float32).reshape(5, 5)

        row, col, window, radius, adjusted = _find_valid_window(
            array,
            row=0,
            col=0,
            nodata=None,
        )

        self.assertEqual((row, col), (1, 1))
        self.assertEqual(radius, 0)
        self.assertTrue(adjusted)
        self.assertEqual(window.shape, (3, 3))
        self.assertEqual(window[1, 1], 6.0)

    def test_find_valid_window_rejects_points_too_far_outside(self) -> None:
        array = np.arange(25, dtype=np.float32).reshape(5, 5)

        with self.assertRaises(ValueError):
            _find_valid_window(
                array,
                row=100,
                col=100,
                nodata=None,
            )

    def test_find_valid_window_searches_far_enough_to_escape_large_nodata_gap(self) -> None:
        array = np.ones((100, 100), dtype=np.float32)
        array[40:61, 40:61] = np.nan

        row, col, window, radius, adjusted = _find_valid_window(
            array,
            row=50,
            col=50,
            nodata=None,
        )

        self.assertLessEqual(row, 39)
        self.assertLessEqual(col, 39)
        self.assertGreaterEqual(radius, 11)
        self.assertFalse(adjusted)
        self.assertEqual(window.shape, (3, 3))
        self.assertFalse(np.isnan(window).any())

    @unittest.skipIf(importlib.util.find_spec('rasterio') is None, 'rasterio is not installed in the active test environment')
    def test_extracts_elevation_slope_aspect_and_roughness(self) -> None:
        import rasterio
        from rasterio.transform import from_origin

        data = np.array(
            [
                [100, 110, 120],
                [95, 105, 115],
                [90, 100, 110],
            ],
            dtype=np.float32,
        )
        transform = from_origin(-122.0, 47.0, 0.0001, 0.0001)

        with tempfile.TemporaryDirectory() as tmp_dir:
            dem_path = Path(tmp_dir) / 'fixture.tif'
            with rasterio.open(
                dem_path,
                'w',
                driver='GTiff',
                height=3,
                width=3,
                count=1,
                dtype='float32',
                crs='EPSG:4326',
                transform=transform,
            ) as dataset:
                dataset.write(data, 1)

            terrain = extract_cell_terrain(str(dem_path), lat=46.99985, lng=-121.99985)

        self.assertEqual(terrain['elevation_m'], 105.0)
        self.assertGreater(terrain['slope_angle_deg'], 0.0)
        self.assertGreaterEqual(terrain['aspect_deg'], 0.0)
        self.assertLessEqual(terrain['aspect_deg'], 360.0)
        self.assertIn('terrain_roughness', terrain)
        self.assertIn('curvature_proxy', terrain)

    @unittest.skipIf(importlib.util.find_spec('rasterio') is None, 'rasterio is not installed in the active test environment')
    def test_clamps_edge_points_to_nearest_valid_interior_window(self) -> None:
        import rasterio
        from rasterio.transform import from_origin

        data = np.array(
            [
                [80, 90, 100, 110, 120],
                [85, 95, 105, 115, 125],
                [90, 100, 110, 120, 130],
                [95, 105, 115, 125, 135],
                [100, 110, 120, 130, 140],
            ],
            dtype=np.float32,
        )
        transform = from_origin(-122.0, 47.0, 0.0001, 0.0001)

        with tempfile.TemporaryDirectory() as tmp_dir:
            dem_path = Path(tmp_dir) / 'fixture_edge.tif'
            with rasterio.open(
                dem_path,
                'w',
                driver='GTiff',
                height=5,
                width=5,
                count=1,
                dtype='float32',
                crs='EPSG:4326',
                transform=transform,
            ) as dataset:
                dataset.write(data, 1)

            terrain = extract_cell_terrain(str(dem_path), lat=47.00005, lng=-122.00005)

        self.assertEqual(terrain['sample_row'], 1.0)
        self.assertEqual(terrain['sample_col'], 1.0)
        self.assertEqual(terrain['clamped_to_bounds'], 1.0)
        self.assertEqual(terrain['elevation_m'], 95.0)
        self.assertGreaterEqual(terrain['slope_angle_deg'], 0.0)


if __name__ == '__main__':
    unittest.main()
