from __future__ import annotations

import tempfile
import unittest
import importlib
from pathlib import Path

import numpy as np

from backend.common.real_features import _find_valid_window, compute_dynamic_lapse_profile, extract_cell_terrain


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
