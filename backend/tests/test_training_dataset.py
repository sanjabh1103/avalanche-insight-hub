from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import backend.common.real_features as real_features
import backend.common.training_dataset as training_dataset_module
from backend.common.features import FEATURE_COLUMNS
from backend.common.regions import Region
from backend.common.terrain_diagnostics import validate_terrain_gate
from backend.common.training_dataset import (
    NEGATIVE_TRAINING_WEIGHT,
    _dem_path,
    _prewarm_training_snowpack_proxies,
    build_real_training_frame,
    fetch_training_events,
)


class TrainingDatasetBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._training_proxy_mode_patch = patch.dict(
            os.environ,
            {'TRAINING_SNOWPACK_PROXY_MODE': 'cell'},
            clear=False,
        )
        self._training_proxy_mode_patch.start()
        self.addCleanup(self._training_proxy_mode_patch.stop)

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
                'training_eligible_reason': 'sar_low_coverage_weak_training',
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

        regional_proxy = SimpleNamespace(
            estimated_shear_strength=4.0,
            snow_settlement_index=0.6,
            season_start='2024-11-01',
            method='seasonal_cumulative_v1',
        )
        with patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'regional_day'}, clear=False):
            with patch(
                'backend.common.training_dataset.compute_region_snowpack_proxy',
                return_value=regional_proxy,
            ) as compute_proxy_mock:
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
        self.assertEqual(manifest['debug_stats']['terrain_loss_report']['terrain_loss_count'], 0)
        self.assertEqual(manifest['debug_stats']['terrain_loss_report']['terrain_success'], 1)
        self.assertEqual(frame.iloc[0]['timestamp'], pd.Timestamp('2024-01-01T00:00:00Z'))
        self.assertIn('training_weight', frame.columns)
        self.assertIn('label_confidence', frame.columns)
        self.assertIn('training_eligible_reason', frame.columns)
        self.assertLess(frame.iloc[0]['training_weight'], 0.95)
        self.assertEqual(frame.iloc[0]['governance_version'], 'autonomous_label_governance_v2')
        self.assertEqual(frame.iloc[0]['training_eligible_reason'], 'sar_low_coverage_weak_training')
        negative_row = frame.loc[frame['label'] == 0].iloc[0]
        self.assertAlmostEqual(float(negative_row['training_weight']), NEGATIVE_TRAINING_WEIGHT, places=6)
        self.assertTrue(pd.isna(negative_row['training_eligible_reason']))
        self.assertEqual(compute_proxy_mock.call_count, 1)
        self.assertEqual(manifest['snowpack_proxy_mode'], 'regional_day')
        self.assertEqual(manifest['snowpack_proxy_stats']['requested_pairs'], 1)
        self.assertIs(build_feature_row_mock.call_args_list[0].kwargs['snowpack_proxy_override'], regional_proxy)
        self.assertIs(build_feature_row_mock.call_args_list[1].kwargs['snowpack_proxy_override'], regional_proxy)

    def test_terrain_exception_persists_reason_and_region_breakdown(self) -> None:
        region = Region(
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
            center=(39.5, -106.5),
            zoom=9,
        )
        event = {
            'id': 'evt-terrain-failure',
            'location': 'SRID=4326;POINT(-106.5 39.5)',
            'timestamp': '2024-01-01T00:00:00Z',
            'severity': 4,
            'source': 'gee_sar',
            'training_eligible': True,
            'label_role': 'core',
            'verification_status': 'unverified',
            'label_confidence': 0.8,
            'training_weight': 0.95,
            'training_eligible_reason': 'sar_low_coverage_weak_training',
        }

        with patch.object(training_dataset_module, 'fetch_training_events', return_value=[event]), \
             patch.object(training_dataset_module, 'load_regions', return_value=[region]), \
             patch.object(
                 training_dataset_module,
                 '_cached_region_day_weather_profile',
                 return_value={},
             ), \
             patch.object(
                 training_dataset_module,
                 'extract_cell_terrain',
                 side_effect=real_features.TerrainUnavailableError('No valid 3x3 DEM window found'),
             ), \
             patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'cell'}, clear=False):
            frame, manifest = build_real_training_frame(seed=42, grid_size=2)

        self.assertTrue(frame.empty)
        debug_stats = manifest['debug_stats']
        self.assertEqual(debug_stats['terrain_failed'], 1)
        self.assertEqual(
            debug_stats['terrain_failure_reasons'],
            {'invalid_or_nodata_window': 1},
        )
        report = debug_stats['terrain_loss_report']
        self.assertEqual(report['terrain_loss_count'], 1)
        self.assertEqual(
            report['failure_reasons_by_region']['colorado_rockies'],
            {'invalid_or_nodata_window': 1},
        )
        self.assertEqual(
            report['failure_reasons_by_source']['gee_sar'],
            {'invalid_or_nodata_window': 1},
        )
        self.assertEqual(
            report['failure_reasons_by_season']['2023-2024'],
            {'invalid_or_nodata_window': 1},
        )
        self.assertEqual(report['by_region']['colorado_rockies']['loss_count'], 1)
        self.assertEqual(report['by_source']['gee_sar']['loss_count'], 1)
        self.assertEqual(report['by_season']['2023-2024']['loss_count'], 1)
        self.assertEqual(report['by_stage']['terrain_assembly']['loss_count'], 1)
        self.assertTrue(any('exceeds' in error for error in validate_terrain_gate(report)))

    def test_fetch_training_events_unknown_region_raises(self) -> None:
        with patch('backend.common.training_dataset.has_supabase_credentials', return_value=True):
            with patch('backend.common.training_dataset.rest_get', return_value=[]):
                with self.assertRaises(ValueError) as ctx:
                    fetch_training_events(region_keys=['nonexistent_region'])
                self.assertIn('Unknown region key(s)', str(ctx.exception))

    def test_fetch_training_events_excludes_unproven_gee_sar_rows(self) -> None:
        rows = [
            {
                'id': 'unproven',
                'location': 'SRID=4326;POINT(-106.5 39.5)',
                'timestamp': '2024-01-01T00:00:00Z',
                'source': 'gee_sar',
                'source_scene_ids': [],
            },
            {
                'id': 'wrong-review',
                'location': 'SRID=4326;POINT(-106.5 39.5)',
                'timestamp': '2024-01-02T00:00:00Z',
                'source': 'gee_sar',
                'source_scene_ids': ['S1_WRONG_REVIEW'],
                'features': {'source_provenance_review_status': 'pending'},
            },
            {
                'id': 'approved',
                'location': 'SRID=4326;POINT(-106.5 39.5)',
                'timestamp': '2024-01-03T00:00:00Z',
                'source': 'gee_sar',
                'source_scene_ids': ['S1_APPROVED'],
                'features': {'source_provenance_review_status': 'approved_core'},
            },
            {
                'id': 'field-event',
                'location': 'SRID=4326;POINT(-106.5 39.5)',
                'timestamp': '2024-01-04T00:00:00Z',
                'source': 'field_report',
            },
        ]
        with patch('backend.common.training_dataset.has_supabase_credentials', return_value=True), \
             patch('backend.common.training_dataset.rest_get', return_value=rows):
            result = fetch_training_events()

        self.assertEqual([row['id'] for row in result], ['approved', 'field-event'])

    def test_regional_day_prewarm_blocks_per_cell_archive_fallback(self) -> None:
        """A hit prewarm must never issue one seasonal request per negative cell."""
        region = Region(
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
            center=(39.5, -106.5),
            zoom=9,
        )
        event = {
            'id': 'evt-1',
            'location': 'SRID=4326;POINT(-106.5 39.5)',
            # Deliberately omit the Z suffix to exercise UTC normalization.
            # The UTC date is 2023-12-31; prewarm and feature assembly must
            # derive the same key instead of using the literal local date.
            'timestamp': '2024-01-01T00:00:00+05:30',
            'severity': 4,
            'source': 'gee_sar',
            'training_eligible': True,
            'label_role': 'core',
            'verification_status': 'unverified',
            'label_confidence': 0.8,
            'training_weight': 0.95,
            'training_eligible_reason': 'sar_low_coverage_weak_training',
        }
        terrain = {
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
        negative = {
            'lat': 39.6,
            'lng': -106.4,
            'timestamp': datetime(2023, 12, 31, tzinfo=timezone.utc),
            'terrain': terrain,
            'region_key': region.key,
            'source_event_id': event['id'],
        }
        proxy = SimpleNamespace(
            estimated_shear_strength=4.0,
            snow_settlement_index=0.6,
            season_start='2024-01-01',
            method='seasonal_cumulative_v1',
        )
        weather_sample = {
            'temperature_2m': -6.0,
            'windspeed_10m': 12.0,
            'winddirection_10m': 240.0,
            'snowfall': 6.0,
            'precipitation': 5.0,
            'snow_depth': 0.8,
        }

        with patch.object(training_dataset_module, 'fetch_training_events', return_value=[event]), \
             patch.object(training_dataset_module, 'load_regions', return_value=[region]), \
             patch.object(training_dataset_module, 'extract_cell_terrain', return_value=terrain), \
             patch.object(training_dataset_module, '_cached_region_day_weather_profile', return_value={}), \
             patch.object(training_dataset_module, 'select_hourly_weather_sample', return_value=weather_sample), \
             patch.object(training_dataset_module, '_sample_negatives_for_event', return_value=[negative]), \
             patch.object(training_dataset_module, 'compute_region_snowpack_proxy', return_value=proxy) as region_proxy_mock, \
             patch.object(real_features, '_cached_snowpack_proxy', side_effect=AssertionError('per-cell proxy call')), \
             patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'regional_day'}, clear=False):
            frame, manifest = build_real_training_frame(seed=42, grid_size=2)

        self.assertEqual(region_proxy_mock.call_count, 1)
        self.assertEqual(int((frame['label'] == 1).sum()), 1)
        self.assertEqual(int((frame['label'] == 0).sum()), 1)
        self.assertEqual(str(frame['timestamp'].dt.tz), 'UTC')
        self.assertEqual(manifest['snowpack_proxy_stats']['missing_pairs'], 0)
        self.assertEqual(manifest['snowpack_proxy_stats']['fallbacks'], 0)
        self.assertGreaterEqual(manifest['timing_seconds']['negative_build'], 0.0)

    def test_regional_day_missing_prewarm_key_fails_closed(self) -> None:
        region = Region(
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
            center=(39.5, -106.5),
            zoom=9,
        )
        event = {
            'id': 'evt-1',
            'location': 'SRID=4326;POINT(-106.5 39.5)',
            'timestamp': '2024-01-01T00:00:00Z',
            'training_eligible': True,
            'label_role': 'core',
            'verification_status': 'unverified',
            'label_confidence': 0.8,
        }

        with patch.object(training_dataset_module, 'fetch_training_events', return_value=[event]), \
             patch.object(training_dataset_module, 'load_regions', return_value=[region]), \
             patch.object(training_dataset_module, '_cached_region_day_weather_profile', return_value={}), \
             patch.object(
                 training_dataset_module,
                 '_prewarm_training_snowpack_proxies',
                 return_value=({}, {'mode': 'regional_day'}),
             ), \
             patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'regional_day'}, clear=False):
            with self.assertRaisesRegex(RuntimeError, 'prewarm is incomplete'):
                build_real_training_frame(seed=42, grid_size=2)

    def test_regional_day_fallback_is_a_hard_training_error(self) -> None:
        region = Region(
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
            center=(39.5, -106.5),
            zoom=9,
        )
        event = {
            'id': 'evt-1',
            'location': 'SRID=4326;POINT(-106.5 39.5)',
            'timestamp': '2024-01-01T00:00:00Z',
            'training_eligible': True,
            'label_role': 'core',
            'verification_status': 'unverified',
            'label_confidence': 0.8,
        }
        fallback_proxy = SimpleNamespace(
            estimated_shear_strength=3.0,
            snow_settlement_index=0.3,
            season_start='2024-01-01',
            method='synthetic_fallback_empty',
        )

        with patch.object(training_dataset_module, 'fetch_training_events', return_value=[event]), \
             patch.object(training_dataset_module, 'load_regions', return_value=[region]), \
             patch.object(training_dataset_module, '_cached_region_day_weather_profile', return_value={}), \
             patch.object(
                 training_dataset_module,
                 '_prewarm_training_snowpack_proxies',
                 return_value=(
                     {('colorado_rockies', '2024-01-01'): fallback_proxy},
                     {'mode': 'regional_day', 'fallbacks': 1},
                 ),
             ), \
             patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'regional_day'}, clear=False):
            with self.assertRaisesRegex(RuntimeError, 'source-incomplete training'):
                build_real_training_frame(seed=42, grid_size=2)


class TrainingSnowpackPrefetchTests(unittest.TestCase):
    def test_regional_day_prefetch_deduplicates_region_days(self) -> None:
        region = Region(
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
            center=(39.5, -106.5),
            zoom=9,
        )
        proxy = SimpleNamespace(
            estimated_shear_strength=4.0,
            snow_settlement_index=0.6,
            season_start='2024-11-01',
            method='seasonal_cumulative_v1',
        )
        pairs = {
            ('colorado_rockies', '2024-01-01'),
            ('colorado_rockies', '2024-01-01'),
            ('colorado_rockies', '2024-01-02'),
        }

        with patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'regional_day'}, clear=False):
            with patch('backend.common.training_dataset.compute_region_snowpack_proxy', return_value=proxy) as compute_mock:
                proxy_map, stats = _prewarm_training_snowpack_proxies(pairs, [region])

        self.assertEqual(compute_mock.call_count, 2)
        self.assertEqual(len(proxy_map), 2)
        self.assertEqual(stats['requested_pairs'], 2)
        self.assertEqual(stats['proxy_calls'], 2)
        self.assertEqual(stats['remote_fetches'], 2)
        self.assertEqual(stats['fallbacks'], 0)

    def test_regional_day_prefetch_records_deterministic_fallback(self) -> None:
        region = Region(
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
            center=(39.5, -106.5),
            zoom=9,
        )

        with patch.dict(os.environ, {'TRAINING_SNOWPACK_PROXY_MODE': 'regional_day'}, clear=False):
            with patch(
                'backend.common.training_dataset.compute_region_snowpack_proxy',
                side_effect=RuntimeError('synthetic network failure'),
            ):
                proxy_map, stats = _prewarm_training_snowpack_proxies(
                    {('colorado_rockies', '2024-01-01')},
                    [region],
                )

        self.assertEqual(stats['requested_pairs'], 1)
        self.assertEqual(stats['proxy_calls'], 1)
        self.assertEqual(stats['remote_fetches'], 0)
        self.assertEqual(stats['fallbacks'], 1)
        self.assertEqual(proxy_map[('colorado_rockies', '2024-01-01')].method, 'synthetic_fallback_empty')


class RegionFilterAndSampleCapTests(unittest.TestCase):
    """Phase H: Tests for region filtering, sample caps, and manifest fields."""

    def setUp(self) -> None:
        self._training_proxy_mode_patch = patch.dict(
            os.environ,
            {'TRAINING_SNOWPACK_PROXY_MODE': 'cell'},
            clear=False,
        )
        self._training_proxy_mode_patch.start()
        self.addCleanup(self._training_proxy_mode_patch.stop)

    @patch('backend.common.training_dataset._sample_negatives_for_event')
    @patch('backend.common.training_dataset.build_real_feature_row')
    @patch('backend.common.training_dataset.select_hourly_weather_sample')
    @patch('backend.common.training_dataset._cached_region_day_weather_profile')
    @patch('backend.common.training_dataset._cached_historical_weather_profile')
    @patch('backend.common.training_dataset.extract_cell_terrain')
    @patch('backend.common.training_dataset.load_regions')
    @patch('backend.common.training_dataset.fetch_training_events')
    def test_sample_cap_reduces_events(
        self,
        fetch_mock,
        load_regions_mock,
        extract_terrain_mock,
        cached_hist_mock,
        cached_region_day_mock,
        select_weather_mock,
        build_feature_mock,
        sample_neg_mock,
    ) -> None:
        region = Region(name='Colorado Rockies', bbox=(38.5, -107.5, 40.5, -105.5), center=(39.5, -106.5), zoom=9)
        load_regions_mock.return_value = [region]
        fetch_mock.return_value = [
            {'id': f'evt-{i}', 'location': 'SRID=4326;POINT(-106.5 39.5)',
             'timestamp': f'2024-01-{i:02d}T00:00:00Z', 'severity': 4,
             'source': 'gee_sar', 'training_eligible': True, 'label_role': 'core',
             'verification_status': 'unverified', 'label_confidence': 0.8,
             'training_weight': 0.95, 'training_eligible_reason': 'sar_low_coverage_weak_training'}
            for i in range(1, 11)
        ]
        extract_terrain_mock.return_value = {
            'elevation_m': 3200.0, 'slope_angle_deg': 37.0, 'aspect_deg': 210.0,
            'terrain_roughness': 12.0, 'curvature_proxy': 4.0, 'northness': 0.3,
            'eastness': 0.6, 'clamped_to_bounds': 0.0, 'window_search_needed': 0.0,
        }
        cached_region_day_mock.return_value = {'sample': {'temperature_2m': -6.0}}
        cached_hist_mock.return_value = {'sample': {'temperature_2m': -6.0}}
        select_weather_mock.return_value = {'temperature_2m': -6.0, 'windspeed_10m': 12.0, 'winddirection_10m': 240.0}
        build_feature_mock.return_value = {
            'feature_row': {name: 0.5 for name in FEATURE_COLUMNS},
            'raw_inputs': {'temperature_2m': -6.0, 'windspeed_10m': 12.0, 'winddirection_10m': 240.0,
                           'downscaled_temperature_c': -7.0, 'snowfall_24h_cm': 6.0, 'precipitation_24h_mm': 5.0,
                           'freezing_level_height': 2600.0, 'lapse_rate_c_per_m': -0.0065,
                           'terrain_elevation_m': 3200.0, 'terrain_slope_deg': 37.0, 'terrain_aspect_deg': 210.0,
                           'snow_depth_cm': 80.0, 'snowpack_proxy_method': 'synthetic_fallback_v1'},
            'lapse': {'lapse_rate_c_per_m': -0.0065},
            'terrain': extract_terrain_mock.return_value,
            'snowpack_proxy': SimpleNamespace(estimated_shear_strength=4.0, snow_settlement_index=0.6,
                                              season_start='2024-11-01', method='seasonal_cumulative_v1'),
        }
        sample_neg_mock.return_value = []

        frame, manifest = build_real_training_frame(
            seed=42, grid_size=2, region_keys=['colorado_rockies'], samples_per_region=3,
        )

        self.assertLessEqual(int((frame['label'] == 1).sum()), 3)
        self.assertEqual(manifest['raw_event_count'], 10)
        self.assertLessEqual(manifest['capped_event_count'], 3)
        self.assertEqual(manifest['samples_per_region_applied'], 3)
        self.assertIn('colorado_rockies', manifest['selected_region_keys'])
        self.assertEqual(manifest['filters']['region_keys_filter'], ['colorado_rockies'])
        self.assertFalse(manifest['is_synthetic'])

    @patch('backend.common.training_dataset._sample_negatives_for_event')
    @patch('backend.common.training_dataset.build_real_feature_row')
    @patch('backend.common.training_dataset.select_hourly_weather_sample')
    @patch('backend.common.training_dataset._cached_region_day_weather_profile')
    @patch('backend.common.training_dataset._cached_historical_weather_profile')
    @patch('backend.common.training_dataset.extract_cell_terrain')
    @patch('backend.common.training_dataset.load_regions')
    @patch('backend.common.training_dataset.fetch_training_events')
    def test_manifest_records_new_fields(
        self,
        fetch_mock,
        load_regions_mock,
        extract_terrain_mock,
        cached_hist_mock,
        cached_region_day_mock,
        select_weather_mock,
        build_feature_mock,
        sample_neg_mock,
    ) -> None:
        region = Region(name='Colorado Rockies', bbox=(38.5, -107.5, 40.5, -105.5), center=(39.5, -106.5), zoom=9)
        load_regions_mock.return_value = [region]
        fetch_mock.return_value = [
            {'id': 'evt-1', 'location': 'SRID=4326;POINT(-106.5 39.5)',
             'timestamp': '2024-01-01T00:00:00Z', 'severity': 4, 'source': 'gee_sar',
             'training_eligible': True, 'label_role': 'core', 'verification_status': 'unverified',
             'label_confidence': 0.8, 'training_weight': 0.95,
             'training_eligible_reason': 'sar_low_coverage_weak_training'},
        ]
        extract_terrain_mock.return_value = {
            'elevation_m': 3200.0, 'slope_angle_deg': 37.0, 'aspect_deg': 210.0,
            'terrain_roughness': 12.0, 'curvature_proxy': 4.0, 'northness': 0.3,
            'eastness': 0.6, 'clamped_to_bounds': 0.0, 'window_search_needed': 0.0,
        }
        cached_region_day_mock.return_value = {'sample': {'temperature_2m': -6.0}}
        cached_hist_mock.return_value = {'sample': {'temperature_2m': -6.0}}
        select_weather_mock.return_value = {'temperature_2m': -6.0, 'windspeed_10m': 12.0, 'winddirection_10m': 240.0}
        build_feature_mock.return_value = {
            'feature_row': {name: 0.5 for name in FEATURE_COLUMNS},
            'raw_inputs': {'temperature_2m': -6.0, 'windspeed_10m': 12.0, 'winddirection_10m': 240.0,
                           'downscaled_temperature_c': -7.0, 'snowfall_24h_cm': 6.0, 'precipitation_24h_mm': 5.0,
                           'freezing_level_height': 2600.0, 'lapse_rate_c_per_m': -0.0065,
                           'terrain_elevation_m': 3200.0, 'terrain_slope_deg': 37.0, 'terrain_aspect_deg': 210.0,
                           'snow_depth_cm': 80.0, 'snowpack_proxy_method': 'synthetic_fallback_v1'},
            'lapse': {'lapse_rate_c_per_m': -0.0065},
            'terrain': extract_terrain_mock.return_value,
            'snowpack_proxy': SimpleNamespace(estimated_shear_strength=4.0, snow_settlement_index=0.6,
                                              season_start='2024-11-01', method='seasonal_cumulative_v1'),
        }
        sample_neg_mock.return_value = [
            {'lat': 39.6, 'lng': -106.4, 'timestamp': datetime(2024, 1, 1, tzinfo=timezone.utc),
             'terrain': extract_terrain_mock.return_value, 'region_key': region.key, 'source_event_id': 'evt-1'}
        ]

        frame, manifest = build_real_training_frame(seed=42, grid_size=2)

        self.assertIn('selected_region_keys', manifest)
        self.assertIn('raw_event_count', manifest)
        self.assertIn('capped_event_count', manifest)
        self.assertIn('samples_per_region_applied', manifest)
        self.assertIn('unique_weather_pairs', manifest)
        self.assertFalse(manifest['is_synthetic'])


if __name__ == '__main__':
    unittest.main()
