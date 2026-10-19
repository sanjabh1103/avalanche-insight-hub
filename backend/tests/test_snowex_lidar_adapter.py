"""Tests for the SnowEx LiDAR raster shadow adapter."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from backend.common.remote_sensing_adapter import SceneData
from backend.common.snowex_lidar_adapter import SnowExLiDARAdapter, SnowExRasterCell


class TestSnowExAdapterAvailability(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        adapter = SnowExLiDARAdapter(enabled=False, data_dir='')
        self.assertFalse(adapter.available())

    def test_enabled_with_valid_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = SnowExLiDARAdapter(enabled=True, data_dir=tmpdir)
            self.assertTrue(adapter.available())

    def test_enabled_with_missing_dir(self) -> None:
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/nonexistent/path')
        self.assertFalse(adapter.available())


class TestSnowExNormalize(unittest.TestCase):
    def test_normalize_valid_raster(self) -> None:
        data = np.array([
            [1.0, 2.0, 3.0, 4.0],
            [0.5, 1.5, 2.5, 3.5],
            [-1.0, 0.0, 1.0, 2.0],
            [np.nan, 1.0, 2.0, 3.0],
        ])
        scene = SceneData(
            scene_id='test.tif',
            sensor='snowex_lidar',
            raw_data=data,
            metadata={},
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        result = adapter.normalize(scene)

        self.assertEqual(result['source'], 'snowex_lidar')
        self.assertGreater(result['snow_depth_mean_m'], 0)
        self.assertGreater(result['n_valid_pixels'], 0)
        self.assertGreaterEqual(result['snow_depth_p25_m'], 0)
        self.assertGreaterEqual(result['snow_depth_p75_m'], result['snow_depth_p25_m'])

    def test_normalize_preserves_provenance_and_shadow_boundary(self) -> None:
        scene = SceneData(
            scene_id='provenance.tif',
            sensor='snowex_lidar',
            raw_data=np.ones((2, 2)),
            metadata={
                'acquisition_time': '2026-01-15T10:00:00Z',
                'source_sha256': 'a' * 64,
                'source_url': 'https://nsidc.org/data/snowex',
                'doi': 'doi:10.1234/example',
                'crs': 'EPSG:4326',
                'metadata_verified': False,
            },
        )
        result = SnowExLiDARAdapter(enabled=True, data_dir='/tmp').normalize(scene)
        self.assertEqual(result['source_sha256'], 'a' * 64)
        self.assertEqual(result['crs'], 'EPSG:4326')
        self.assertFalse(result['synthetic'])
        self.assertEqual(result['quality_state'], 'provisional')

    def test_normalize_empty_raster(self) -> None:
        scene = SceneData(
            scene_id='empty.tif',
            sensor='snowex_lidar',
            raw_data=None,
            metadata={},
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        self.assertEqual(adapter.normalize(scene), {})

    def test_normalize_all_invalid_pixels(self) -> None:
        data = np.full((4, 4), np.nan)
        scene = SceneData(
            scene_id='invalid.tif',
            sensor='snowex_lidar',
            raw_data=data,
            metadata={},
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        self.assertEqual(adapter.normalize(scene), {})


class TestRegridToCells(unittest.TestCase):
    def test_regrid_4x4_grid(self) -> None:
        data = np.random.rand(16, 16) * 2.0
        scene = SceneData(
            scene_id='test.tif',
            sensor='snowex_lidar',
            raw_data=data,
            metadata={'acquisition_time': '2026-01-15T10:00:00Z'},
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        cells = adapter.regrid_to_cells(
            scene,
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            grid_size=4,
            bbox=(76.0, 35.0, 77.0, 36.0),
        )

        self.assertEqual(len(cells), 16)
        for cell in cells:
            self.assertGreater(cell.n_valid_pixels, 0)
            self.assertGreaterEqual(cell.snow_depth_p75_m, cell.snow_depth_p25_m)
            self.assertEqual(len(cell.source_hash), 64)
            self.assertEqual(cell.acquisition_time_utc, '2026-01-15T10:00:00Z')

    def test_regrid_uses_georeferenced_transform_when_available(self) -> None:
        from rasterio.transform import from_bounds

        scene = SceneData(
            scene_id='georeferenced.tif',
            sensor='snowex_lidar',
            raw_data=np.ones((16, 16)),
            metadata={
                'acquisition_time': '2026-01-15T10:00:00Z',
                'source_sha256': 'c' * 64,
                'transform': from_bounds(76.0, 35.0, 77.0, 36.0, 16, 16),
                'crs': 'EPSG:4326',
                'nodata': -9999.0,
            },
        )
        cells = SnowExLiDARAdapter(enabled=True, data_dir='/tmp').regrid_to_cells(
            scene,
            region_key='great_himalaya',
            forecast_date='2026-01-15',
            grid_size=4,
            bbox=(76.0, 35.0, 77.0, 36.0),
        )
        self.assertEqual(len(cells), 16)
        self.assertTrue(all(cell.crs == 'EPSG:4326' for cell in cells))
        self.assertTrue(all(cell.scene_source_hash == 'c' * 64 for cell in cells))

    def test_regrid_with_invalid_pixels_skips_cells(self) -> None:
        data = np.full((8, 8), -1.0)
        data[0:4, 0:4] = 1.5
        scene = SceneData(
            scene_id='partial.tif',
            sensor='snowex_lidar',
            raw_data=data,
            metadata={},
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        cells = adapter.regrid_to_cells(
            scene,
            region_key='test',
            forecast_date='2026-01-15',
            grid_size=2,
            bbox=(76.0, 35.0, 77.0, 36.0),
        )

        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0].cell_row, 0)
        self.assertEqual(cells[0].cell_col, 0)

    def test_regrid_too_small_raster(self) -> None:
        data = np.array([[1.0]])
        scene = SceneData(
            scene_id='tiny.tif',
            sensor='snowex_lidar',
            raw_data=data,
            metadata={},
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        cells = adapter.regrid_to_cells(
            scene,
            region_key='test',
            forecast_date='2026-01-15',
            grid_size=4,
            bbox=(76.0, 35.0, 77.0, 36.0),
        )
        self.assertEqual(len(cells), 0)


class TestShadowFeatureValues(unittest.TestCase):
    def test_to_shadow_feature_values(self) -> None:
        cells = [
            SnowExRasterCell(
                region_key='test',
                cell_row=0,
                cell_col=0,
                forecast_date='2026-01-15',
                snow_depth_mean_m=1.5,
                snow_depth_std_m=0.3,
                snow_depth_p25_m=1.2,
                snow_depth_p50_m=1.5,
                snow_depth_p75_m=1.8,
                n_valid_pixels=100,
                acquisition_time_utc='2026-01-15T10:00:00Z',
                source_hash='a' * 64,
            ),
        ]
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        features = adapter.to_shadow_feature_values(cells)

        self.assertIn('0_0', features)
        self.assertAlmostEqual(features['0_0']['snowex_snow_depth_mean_m'], 1.5)
        self.assertIn('snowex_snow_depth_p25_m', features['0_0'])
        self.assertIn('snowex_snow_depth_p75_m', features['0_0'])

    def test_observation_rows_require_timestamp_and_are_shadow_only(self) -> None:
        cells = [
            SnowExRasterCell(
                region_key='test',
                cell_row=0,
                cell_col=0,
                forecast_date='2026-01-15',
                snow_depth_mean_m=1.5,
                snow_depth_std_m=0.3,
                snow_depth_p25_m=1.2,
                snow_depth_p50_m=1.5,
                snow_depth_p75_m=1.8,
                n_valid_pixels=100,
                acquisition_time_utc='2026-01-15T10:00:00Z',
                source_hash='a' * 64,
            ),
            SnowExRasterCell(
                region_key='test',
                cell_row=0,
                cell_col=1,
                forecast_date='2026-01-15',
                snow_depth_mean_m=1.0,
                snow_depth_std_m=0.2,
                snow_depth_p25_m=0.8,
                snow_depth_p50_m=1.0,
                snow_depth_p75_m=1.2,
                n_valid_pixels=100,
                acquisition_time_utc='',
                source_hash='b' * 64,
            ),
        ]
        rows = SnowExLiDARAdapter(enabled=True, data_dir='/tmp').build_verification_observation_rows(cells)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['variable'], 'snow_depth_m')
        self.assertFalse(rows[0]['synthetic'])
        self.assertTrue(rows[0]['metadata']['shadow_only'])

    def test_persistence_is_explicitly_disabled_without_flag(self) -> None:
        adapter = SnowExLiDARAdapter(enabled=False, data_dir='/tmp')
        result = adapter.persist_shadow_evidence(
            SceneData(scene_id='scene.tif', sensor='snowex_lidar', raw_data=np.ones((2, 2))),
            [],
            region_key='test',
        )
        self.assertEqual(result['status'], 'disabled')


class TestQuery(unittest.TestCase):
    def test_query_returns_empty_when_disabled(self) -> None:
        adapter = SnowExLiDARAdapter(enabled=False, data_dir='')
        results = adapter.query(region_key='test', forecast_date='2026-01-15')
        self.assertEqual(results, [])

    def test_query_finds_matching_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = 'great_himalaya_2026-01-15_lidar.tif'
            with open(os.path.join(tmpdir, fname), 'wb') as f:
                f.write(b'fake-tiff-data')
            adapter = SnowExLiDARAdapter(enabled=True, data_dir=tmpdir)
            results = adapter.query(region_key='great_himalaya', forecast_date='2026-01-15')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['scene_id'], fname)


class TestPersistShadowEvidence(unittest.TestCase):
    """Tests for credential-gated persistence path."""

    def test_disabled_returns_disabled_status(self) -> None:
        adapter = SnowExLiDARAdapter(enabled=False, data_dir='')
        scene = SceneData(scene_id='test.tif', sensor='snowex_lidar', raw_data=None, metadata={})
        result = adapter.persist_shadow_evidence(scene, [], region_key='test')
        self.assertEqual(result['status'], 'disabled')
        self.assertEqual(result['observation_rows'], 0)

    def test_no_credentials_returns_credentials_unavailable(self) -> None:
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        scene = SceneData(scene_id='test.tif', sensor='snowex_lidar', raw_data=None, metadata={})
        with patch('backend.common.snowex_lidar_adapter.has_supabase_credentials', return_value=False):
            result = adapter.persist_shadow_evidence(scene, [], region_key='test')
        self.assertEqual(result['status'], 'credentials_unavailable')
        self.assertEqual(result['observation_rows'], 0)


class TestBuildVerificationObservationRows(unittest.TestCase):
    def test_cells_without_acquisition_time_excluded(self) -> None:
        cell_with_time = SnowExRasterCell(
            region_key='test', cell_row=0, cell_col=0, forecast_date='2026-01-15',
            snow_depth_mean_m=1.5, snow_depth_std_m=0.3, snow_depth_p25_m=1.2,
            snow_depth_p50_m=1.5, snow_depth_p75_m=1.8, n_valid_pixels=100,
            acquisition_time_utc='2026-01-15T10:00:00Z', source_hash='a' * 64,
        )
        cell_no_time = SnowExRasterCell(
            region_key='test', cell_row=1, cell_col=1, forecast_date='2026-01-15',
            snow_depth_mean_m=2.0, snow_depth_std_m=0.4, snow_depth_p25_m=1.7,
            snow_depth_p50_m=2.0, snow_depth_p75_m=2.3, n_valid_pixels=50,
            acquisition_time_utc='', source_hash='b' * 64,
        )
        adapter = SnowExLiDARAdapter(enabled=True, data_dir='/tmp')
        rows = adapter.build_verification_observation_rows([cell_with_time, cell_no_time])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['metadata']['shadow_only'])
        self.assertFalse(rows[0]['synthetic'])


if __name__ == '__main__':
    unittest.main()
