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
    TerrainUnavailableError,
    _fetch_open_meteo,
    _find_valid_window,
    build_real_feature_row,
    compute_dynamic_lapse_profile,
    extract_cell_terrain,
    fetch_ensemble_weather_profile,
    fetch_historical_weather_window,
)
from backend.common.snowpack_proxy import SnowpackProxy


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


class EnsembleApiTests(unittest.TestCase):
    def test_fetch_ensemble_returns_percentiles(self) -> None:
        ensemble_payload = FakeResponse(
            200,
            {
                'hourly': {
                    'time': ['2026-06-24T00:00', '2026-06-24T01:00'],
                    'temperature_2m': [[-5.0, -3.0, -1.0], [-4.0, -2.0, 0.0]],
                    'precipitation': [[0.0, 0.5, 2.0], [0.0, 0.2, 1.0]],
                    'snowfall': [[0.0, 0.3, 1.0], [0.0, 0.1, 0.5]],
                    'snow_depth': [[10.0, 12.0, 15.0], [10.0, 12.0, 14.0]],
                    'windspeed_10m': [[5.0, 10.0, 20.0], [4.0, 8.0, 16.0]],
                },
            },
        )

        with patch.object(real_features.requests, 'get', return_value=ensemble_payload):
            profile = fetch_ensemble_weather_profile(
                region_center=(27.0, 88.0),
                forecast_start=datetime(2026, 6, 24, tzinfo=timezone.utc),
                horizon_hours=2,
            )

        self.assertEqual(profile['source'], 'open_meteo_ensemble_probabilistic_v1')
        self.assertEqual(len(profile['samples']), 2)
        sample0 = profile['samples'][0]
        self.assertIn('temperature_2m_p10', sample0)
        self.assertIn('temperature_2m_p50', sample0)
        self.assertIn('temperature_2m_p90', sample0)
        self.assertAlmostEqual(sample0['temperature_2m_p10'], -4.6, places=1)
        self.assertAlmostEqual(sample0['temperature_2m_p50'], -3.0, places=1)
        self.assertAlmostEqual(sample0['temperature_2m_p90'], -1.4, places=1)

    def test_fetch_ensemble_uses_ensemble_endpoint(self) -> None:
        ensemble_payload = FakeResponse(
            200,
            {'hourly': {'time': [], 'temperature_2m': []}},
        )

        with patch.object(real_features.requests, 'get', return_value=ensemble_payload) as get_mock:
            fetch_ensemble_weather_profile(
                region_center=(27.0, 88.0),
                forecast_start=datetime(2026, 6, 24, tzinfo=timezone.utc),
                horizon_hours=1,
            )

        self.assertEqual(get_mock.call_args.args[0], real_features.OPEN_METEO_ENSEMBLE)


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

    def test_build_real_feature_row_emits_derived_physics_features(self) -> None:
        assembled = build_real_feature_row(
            weather_sample={
                'temperature_2m': 1.5,
                'precipitation': 7.0,
                'snowfall': 3.0,
                'snow_depth': 0.75,
                'windspeed_10m': 14.0,
                'winddirection_10m': 300.0,
                'freezing_level_height': 2600.0,
            },
            terrain={
                'elevation_m': 3100.0,
                'slope_angle_deg': 38.0,
                'aspect_deg': 315.0,
                'terrain_roughness': 22.0,
                'curvature_proxy': 6.0,
                'northness': 0.85,
                'eastness': 0.25,
            },
            timestamp=datetime(2026, 4, 25, tzinfo=timezone.utc),
            lat=46.0,
            lng=7.0,
            snowpack_proxy_override=SnowpackProxy(
                estimated_shear_strength=3.0,
                snow_settlement_index=0.2,
                season_start='2025-11-01',
                method='seasonal_cumulative_v1',
            ),
        )

        feature_row = assembled['feature_row']
        raw_inputs = assembled['raw_inputs']
        self.assertIn('freezing_level_margin', feature_row)
        self.assertIn('load_to_shear_ratio', feature_row)
        self.assertIn('settlement_deficit', feature_row)
        self.assertIn('rain_on_snow_signal', feature_row)
        self.assertIn('wet_activation_signal', feature_row)
        self.assertIn('elevation_precip_bias', feature_row)
        self.assertGreater(feature_row['load_to_shear_ratio'], 0.0)
        self.assertGreater(feature_row['settlement_deficit'], 0.0)
        self.assertEqual(feature_row['rain_on_snow_signal'], 1.0)
        self.assertGreater(feature_row['wet_activation_signal'], 0.0)
        self.assertGreater(raw_inputs['elevation_adjusted_precipitation_24h_mm'], raw_inputs['precipitation_24h_mm'])
        self.assertGreater(raw_inputs['elevation_adjusted_snowfall_24h_cm'], raw_inputs['snowfall_24h_cm'])


class ExtractCellTerrainTests(unittest.TestCase):
    def test_find_valid_window_clamps_out_of_bounds_indices(self) -> None:
        array = np.arange(25, dtype=np.float32).reshape(5, 5)

        row, col, window, radius, adjusted, distance_m = _find_valid_window(
            array,
            row=0,
            col=0,
            nodata=None,
        )

        self.assertEqual((row, col), (1, 1))
        self.assertEqual(radius, 0)
        self.assertTrue(adjusted)
        self.assertEqual(distance_m, 0.0)
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

        row, col, window, radius, adjusted, distance_m = _find_valid_window(
            array,
            row=50,
            col=50,
            nodata=None,
        )

        self.assertLessEqual(row, 39)
        self.assertLessEqual(col, 39)
        self.assertGreaterEqual(radius, 11)
        self.assertFalse(adjusted)
        self.assertGreater(distance_m, 0.0)
        self.assertEqual(window.shape, (3, 3))
        self.assertFalse(np.isnan(window).any())

    def test_find_valid_window_respects_strict_max_search_distance(self) -> None:
        array = np.ones((20, 20), dtype=np.float32)
        array[7:14, 7:14] = np.nan

        with self.assertRaises(ValueError):
            _find_valid_window(
                array,
                row=10,
                col=10,
                nodata=None,
                px_size_x_m=30.0,
                px_size_y_m=30.0,
                max_search_distance_m=50.0,
            )

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

    @unittest.skipIf(importlib.util.find_spec('rasterio') is None, 'rasterio is not installed in the active test environment')
    def test_extract_cell_terrain_fails_when_valid_window_is_beyond_strict_radius(self) -> None:
        import rasterio
        from rasterio.transform import from_origin

        data = np.full((9, 9), np.nan, dtype=np.float32)
        data[0:3, 0:3] = np.array(
            [
                [100, 110, 120],
                [95, 105, 115],
                [90, 100, 110],
            ],
            dtype=np.float32,
        )
        transform = from_origin(-122.0, 47.0, 0.00027, 0.00027)

        with tempfile.TemporaryDirectory() as tmp_dir:
            dem_path = Path(tmp_dir) / 'fixture_gap.tif'
            with rasterio.open(
                dem_path,
                'w',
                driver='GTiff',
                height=9,
                width=9,
                count=1,
                dtype='float32',
                crs='EPSG:4326',
                transform=transform,
            ) as dataset:
                dataset.write(data, 1)

            with self.assertRaises(TerrainUnavailableError):
                extract_cell_terrain(str(dem_path), lat=46.998785, lng=-121.998785, max_search_distance_m=50.0)


class TemporalPersistenceTests(unittest.TestCase):
    def test_no_history_returns_zeros(self) -> None:
        from backend.common.real_features import _compute_temporal_persistence_features
        result = _compute_temporal_persistence_features(None, 5.0, -3.0, 6.0)
        self.assertEqual(result['snowfall_72h'], 0.0)
        self.assertEqual(result['snow_loading_persistence'], 0.0)
        self.assertEqual(result['temp_persistence'], 0.0)
        self.assertEqual(result['snowfall_rate_change'], 0.0)

    def test_empty_history_returns_zeros(self) -> None:
        from backend.common.real_features import _compute_temporal_persistence_features
        result = _compute_temporal_persistence_features([], 5.0, -3.0, 6.0)
        self.assertEqual(result['snowfall_72h'], 0.0)

    def test_snow_loading_persistence_with_continuous_snowfall(self) -> None:
        from backend.common.real_features import _compute_temporal_persistence_features
        history = [{'snowfall_24h': 2.0, 'temperature_2m': -5.0} for _ in range(24)]
        result = _compute_temporal_persistence_features(history, 2.0, -5.0, 2.5)
        self.assertAlmostEqual(result['snow_loading_persistence'], 1.0)
        self.assertAlmostEqual(result['temp_persistence'], 1.0)
        self.assertGreater(result['snowfall_72h'], 0.0)

    def test_temp_persistence_with_warm_temps(self) -> None:
        from backend.common.real_features import _compute_temporal_persistence_features
        history = [{'snowfall_24h': 0.0, 'temperature_2m': 5.0} for _ in range(24)]
        result = _compute_temporal_persistence_features(history, 0.0, 5.0, 0.0)
        self.assertAlmostEqual(result['temp_persistence'], 0.0)
        self.assertAlmostEqual(result['snow_loading_persistence'], 0.0)

    def test_snowfall_rate_change_increasing(self) -> None:
        from backend.common.real_features import _compute_temporal_persistence_features
        history = [{'snowfall_24h': float(i), 'temperature_2m': -3.0} for i in range(24)]
        result = _compute_temporal_persistence_features(history, 23.0, -3.0, 23.0)
        self.assertGreater(result['snowfall_rate_change'], 0.0)

    def test_build_real_feature_row_includes_persistence(self) -> None:
        terrain = {
            'elevation_m': 2000.0,
            'slope_angle_deg': 30.0,
            'aspect_deg': 180.0,
            'terrain_roughness': 20.0,
            'curvature_proxy': 5.0,
            'northness': 0.5,
            'eastness': 0.3,
        }
        weather = {
            'temperature_2m': -5.0,
            'windspeed_10m': 15.0,
            'winddirection_10m': 270.0,
            'snowfall_24h': 10.0,
            'precipitation_24h': 12.0,
            'snow_depth': 0.4,
            'freezing_level_height': 1500.0,
        }
        history = [{'snowfall_24h': 5.0, 'temperature_2m': -3.0} for _ in range(24)]
        result = build_real_feature_row(
            weather_sample=weather,
            terrain=terrain,
            timestamp=datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc),
            lat=27.0,
            lng=88.0,
            history_samples=history,
        )
        feature_row = result['feature_row']
        self.assertIn('snowfall_72h', feature_row)
        self.assertIn('snow_loading_persistence', feature_row)
        self.assertIn('temp_persistence', feature_row)
        self.assertIn('snowfall_rate_change', feature_row)
        self.assertGreater(feature_row['snowfall_72h'], 0.0)


if __name__ == '__main__':
    unittest.main()
