from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from backend.common.runout import build_runout_polygons, runout_polygon_for_cell


class RunoutPolygonTests(unittest.TestCase):
    @staticmethod
    def _write_dem(root: Path, *, region_key: str = 'colorado_rockies') -> Path:
        path = root / f'{region_key}.tif'
        profile = {
            'driver': 'GTiff',
            'height': 256,
            'width': 256,
            'count': 1,
            'dtype': 'float32',
            'crs': 'EPSG:4326',
            'transform': from_bounds(-107.0, 39.0, -106.0, 40.0, 256, 256),
        }
        values = np.linspace(3200.0, 2700.0, num=256 * 256, dtype=np.float32).reshape((256, 256))
        with rasterio.open(path, 'w', **profile) as dataset:
            dataset.write(values, 1)
        return path

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_build_runout_polygons_uses_runout_seed_only(self) -> None:
        rows = [
            {
                'row': 9,
                'col': 9,
                'lat': 39.90,
                'lng': -106.90,
                'lat_end': 39.91,
                'lng_end': -106.89,
                'risk_score': 4,
                'probability': None,
                'runout_seed': True,
                'status': 'unavailable_terrain',
                'terrain_inputs': {},
            },
            {
                'row': 1,
                'col': 1,
                'lat': 39.10,
                'lng': -106.10,
                'lat_end': 39.11,
                'lng_end': -106.09,
                'risk_score': 4,
                'probability': 0.91,
                'runout_seed': False,
                'status': 'ready',
                'terrain_inputs': {'slope_angle_deg': 33.0, 'aspect_deg': 180.0},
            },
            {
                'row': 2,
                'col': 2,
                'lat': 39.20,
                'lng': -106.20,
                'lat_end': 39.21,
                'lng_end': -106.19,
                'risk_score': 4,
                'probability': 0.71,
                'runout_seed': True,
                'status': 'ready',
                'terrain_inputs': {'slope_angle_deg': 31.0, 'aspect_deg': 90.0},
            },
        ]

        polygons = build_runout_polygons('colorado_rockies', rows)

        self.assertEqual([(polygon['row'], polygon['col']) for polygon in polygons], [(2, 2)])

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_build_runout_polygons_allows_runout_seed_when_probability_missing(self) -> None:
        rows = [
            {
                'row': 4,
                'col': 5,
                'lat': 39.40,
                'lng': -106.40,
                'lat_end': 39.41,
                'lng_end': -106.39,
                'risk_score': 5,
                'probability': None,
                'runout_seed': True,
                'status': 'ready',
                'terrain_inputs': {'slope_angle_deg': 37.0, 'aspect_deg': 225.0},
            }
        ]

        polygons = build_runout_polygons('colorado_rockies', rows)

        self.assertEqual(len(polygons), 1)
        self.assertEqual(polygons[0]['row'], 4)
        self.assertEqual(polygons[0]['col'], 5)
        self.assertIn(polygons[0]['method'], {'alpha_beta_elliptical', 'rectangular_footprint'})

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_build_runout_polygons_ignores_malformed_probability_without_raising(self) -> None:
        rows = [
            {
                'row': 7,
                'col': 7,
                'lat': 39.70,
                'lng': -106.70,
                'lat_end': 39.71,
                'lng_end': -106.69,
                'risk_score': 1,
                'probability': 'not-a-number',
                'runout_seed': False,
                'status': 'ready',
                'terrain_inputs': {'slope_angle_deg': 28.0, 'aspect_deg': 15.0},
            }
        ]

        polygons = build_runout_polygons('colorado_rockies', rows)

        self.assertEqual(polygons, [])

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_runout_polygon_for_cell_uses_neutral_probability_fallback(self) -> None:
        cell = {
            'row': 3,
            'col': 4,
            'lat': 39.30,
            'lng': -106.30,
            'lat_end': 39.31,
            'lng_end': -106.29,
            'risk_score': 4,
            'probability': None,
            'terrain_inputs': {'slope_angle_deg': 35.0, 'aspect_deg': 135.0},
        }

        polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell=cell)

        self.assertEqual(polygon.row, 3)
        self.assertEqual(polygon.col, 4)
        self.assertTrue(len(polygon.polygon) >= 4)
        self.assertEqual(polygon.method, 'alpha_beta_elliptical')

    @patch('backend.common.runout._execute_whitebox_flowpath')
    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', True)
    def test_runout_polygon_for_cell_prefers_real_whitebox_output_when_available(
        self,
        execute_whitebox_flowpath_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dem_root = Path(tmpdir)
            self._write_dem(dem_root)

            def _write_flowpath(*, crop_dem, flowpath_raster, **_kwargs):
                with rasterio.open(crop_dem) as dataset:
                    profile = dataset.profile.copy()
                mask = np.zeros((int(profile['height']), int(profile['width'])), dtype=np.uint8)
                mask[2:10, 5] = 1
                with rasterio.open(flowpath_raster, 'w', **profile) as dataset:
                    dataset.write(mask, 1)
                return True

            execute_whitebox_flowpath_mock.side_effect = _write_flowpath

            with patch('backend.common.runout.DEM_ROOT', dem_root):
                polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell={
                    'row': 6,
                    'col': 6,
                    'lat': 39.50,
                    'lng': -106.50,
                    'risk_score': 5,
                    'probability': 0.88,
                    'terrain_inputs': {'slope_angle_deg': 36.0, 'aspect_deg': 180.0},
                })

        self.assertEqual(polygon.method, 'alpha_beta_whitebox')
        self.assertGreaterEqual(len(polygon.polygon), 4)
        execute_whitebox_flowpath_mock.assert_called_once()

    @patch('backend.common.runout._execute_whitebox_flowpath', return_value=False)
    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', True)
    def test_runout_polygon_for_cell_falls_back_when_whitebox_output_fails(
        self,
        _execute_whitebox_flowpath_mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dem_root = Path(tmpdir)
            self._write_dem(dem_root)

            with patch('backend.common.runout.DEM_ROOT', dem_root):
                polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell={
                    'row': 1,
                    'col': 2,
                    'lat': 39.50,
                    'lng': -106.50,
                    'risk_score': 3,
                    'probability': 0.72,
                    'terrain_inputs': {'slope_angle_deg': 30.0, 'aspect_deg': 135.0},
                })

        self.assertEqual(polygon.method, 'alpha_beta_elliptical')


if __name__ == '__main__':
    unittest.main()
