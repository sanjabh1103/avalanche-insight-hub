from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from backend.common.features import FEATURE_COLUMNS
from backend.common.regions import Region
from backend.common.training_dataset import NEGATIVE_TRAINING_WEIGHT, _dem_path, build_real_training_frame


class TrainingDatasetBuilderTests(unittest.TestCase):
    @patch.dict(os.environ, {'DEM_ROOT': '/artifacts/dem'}, clear=False)
    def test_dem_path_prefers_dem_root_environment_variable(self) -> None:
        self.assertEqual(_dem_path('colorado_rockies'), Path('/artifacts/dem/colorado_rockies.tif'))

    @patch.dict(os.environ, {'DEM_DIR': '/compat/dem'}, clear=False)
    def test_dem_path_uses_dem_dir_compat_alias_when_dem_root_missing(self) -> None:
        with patch.dict(os.environ, {'DEM_ROOT': ''}, clear=False):
            self.assertEqual(_dem_path('swiss_alps'), Path('/compat/dem/swiss_alps.tif'))

    @patch('backend.common.training_dataset._sample_negatives_for_event')
    @patch('backend.common.training_dataset.build_real_feature_row')
    @patch('backend.common.training_dataset.select_hourly_weather_sample')
    @patch('backend.common.training_dataset._cached_historical_weather_profile')
    @patch('backend.common.training_dataset.extract_cell_terrain')
    @patch('backend.common.training_dataset.load_regions')
    @patch('backend.common.training_dataset.fetch_training_events')
    def test_real_training_frame_preserves_manifest_and_counts(
        self,
        fetch_training_events_mock,
        load_regions_mock,
        extract_cell_terrain_mock,
        cached_weather_mock,
        select_weather_mock,
        build_feature_row_mock,
        sample_negatives_mock,
    ) -> None:
        region = Region(name='Colorado Rockies', bbox=(38.5, -107.5, 40.5, -105.5), center=(39.5, -106.5), zoom=9)
        load_regions_mock.return_value = [region]
        fetch_training_events_mock.return_value = [
            {
                'id': 'evt-1',
                'location': 'SRID=4326;POINT(-106.5 39.5)',
                'timestamp': '2024-01-01T00:00:00Z',
                'severity': 4,
                'source': 'gee_sar',
                'training_eligible': True,
                'label_role': 'core',
                'verification_status': 'unverified',
                'label_confidence': 0.8,
                'training_weight': 0.95,
            }
        ]
        extract_cell_terrain_mock.return_value = {
            'elevation_m': 3200.0,
            'slope_angle_deg': 37.0,
            'aspect_deg': 210.0,
            'terrain_roughness': 12.0,
            'curvature_proxy': 4.0,
            'northness': 0.3,
            'eastness': 0.6,
            'clamped_to_bounds': 0.0,
            'window_search_needed': 0.0,
        }
        cached_weather_mock.return_value = {'sample': {'temperature_2m': -6.0}}
        select_weather_mock.return_value = {'temperature_2m': -6.0, 'windspeed_10m': 12.0, 'winddirection_10m': 240.0}
        build_feature_row_mock.return_value = {
            'feature_row': {name: 0.5 for name in FEATURE_COLUMNS},
            'raw_inputs': {
                'temperature_2m': -6.0,
                'downscaled_temperature_c': -7.0,
                'snowfall_24h_cm': 6.0,
                'precipitation_24h_mm': 5.0,
                'windspeed_10m': 12.0,
                'winddirection_10m': 240.0,
                'freezing_level_height': 2600.0,
                'lapse_rate_c_per_m': -0.0065,
                'terrain_elevation_m': 3200.0,
                'terrain_slope_deg': 37.0,
                'terrain_aspect_deg': 210.0,
                'snow_depth_cm': 80.0,
                'snowpack_proxy_method': 'synthetic_fallback_v1',
            },
            'lapse': {'lapse_rate_c_per_m': -0.0065},
            'terrain': extract_cell_terrain_mock.return_value,
            'snowpack_proxy': SimpleNamespace(
                estimated_shear_strength=4.0,
                snow_settlement_index=0.6,
                season_start='2024-11-01',
                method='seasonal_cumulative_v1',
            ),
        }
        sample_negatives_mock.return_value = [
            {
                'lat': 39.6,
                'lng': -106.4,
                'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),
                'terrain': extract_cell_terrain_mock.return_value,
                'region_key': region.key,
                'source_event_id': 'evt-1',
            }
        ]

        frame, manifest = build_real_training_frame(seed=42, grid_size=2)

        self.assertEqual(int((frame['label'] == 1).sum()), 1)
        self.assertEqual(int((frame['label'] == 0).sum()), 1)
        self.assertEqual(manifest['training_dataset_version'], 'real_event_join_v1')
        self.assertEqual(manifest['positive_count'], 1)
        self.assertEqual(manifest['negative_count'], 1)
        self.assertIn('debug_stats', manifest)
        self.assertIn('mean_training_weight', manifest)
        self.assertEqual(manifest['debug_stats']['assembled_ok'], 1)
        self.assertEqual(manifest['debug_stats']['terrain_failed'], 0)
        self.assertEqual(frame.iloc[0]['timestamp'], pd.Timestamp('2024-01-01T00:00:00Z'))
        self.assertIn('training_weight', frame.columns)
        self.assertIn('label_confidence', frame.columns)
        self.assertLess(frame.iloc[0]['training_weight'], 0.95)
        self.assertEqual(frame.iloc[0]['governance_version'], 'autonomous_label_governance_v2')
        negative_row = frame.loc[frame['label'] == 0].iloc[0]
        self.assertAlmostEqual(float(negative_row['training_weight']), NEGATIVE_TRAINING_WEIGHT, places=6)


if __name__ == '__main__':
    unittest.main()
