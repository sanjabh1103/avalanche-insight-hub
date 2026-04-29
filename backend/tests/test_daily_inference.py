from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.common.features import FEATURE_COLUMNS
from backend.common.snowpack_proxy import SnowpackProxy, SnowpackProxyBatchResult
from backend.daily_inference import build_cells, main, upsert_forecast_grid


class ForecastGridMetadataTests(unittest.TestCase):
    @patch('backend.daily_inference.has_supabase_credentials', return_value=False)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence')
    def test_upsert_forecast_grid_keeps_required_model_metadata(
        self,
        fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
    ) -> None:
        fetch_sar_evidence_mock.return_value = {
            'mask_asset_refs': ['sar-masks/2026-04-25/colorado_rockies/test-scene.tif'],
            'sar_event_geometries': [{'event_id': 'evt-1', 'geometry': {'type': 'Polygon', 'coordinates': []}}],
        }
        region = SimpleNamespace(
            key='colorado_rockies',
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
        )
        bundle = {
            'created_at': '2026-04-25T00:00:00+00:00',
            'dynamic_model_type': 'mts_lstm',
            'dynamic_model_version': 'mts_lstm_shadow_v1',
            'surrogate_model_version': 'rf_surrogate_v1',
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': ['snowfall_24h', 'wind_loading'],
            'calibration_method': 'isotonic_v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'lstm_head_meta': {'uncertainty_method': 'seeded_dropout_ensemble_v1'},
            'training_dataset_version': 'real_event_join_v1',
            'dataset_manifest': {'newest_timestamp': '2026-04-24T00:00:00+00:00'},
        }

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=[],
            horizon_hours=72,
        )

        metadata = payload['model_metadata']
        self.assertEqual(metadata['uncertainty_method'], 'seeded_dropout_ensemble_v1')
        self.assertEqual(metadata['sar_mask_asset_refs'], ['sar-masks/2026-04-25/colorado_rockies/test-scene.tif'])
        self.assertEqual(len(metadata['sar_event_geometries']), 1)
        self.assertEqual(
            metadata['label_snapshot_id'],
            'real_event_join_v1:2026-04-24T00:00:00+00:00',
        )

    @patch('backend.daily_inference._upsert_shap_cache')
    @patch('backend.daily_inference.rest_upsert')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_skips_remote_writes_in_dry_run(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
        rest_upsert_mock,
        upsert_shap_cache_mock,
    ) -> None:
        region = SimpleNamespace(
            key='colorado_rockies',
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
        )
        bundle = {
            'created_at': '2026-04-25T00:00:00+00:00',
            'dynamic_model_type': 'mts_lstm',
            'dynamic_model_version': 'mts_lstm_shadow_v1',
            'surrogate_model_version': 'rf_surrogate_v1',
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': ['snowfall_24h', 'wind_loading'],
            'calibration_method': 'isotonic_v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'training_dataset_version': 'real_event_join_v1',
        }

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=[],
            horizon_hours=72,
            dry_run=True,
        )

        self.assertEqual(payload['status'], 'ready')
        rest_upsert_mock.assert_not_called()
        upsert_shap_cache_mock.assert_not_called()

    @patch('backend.daily_inference.has_supabase_credentials', return_value=False)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_marks_mixed_regions_partial(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
    ) -> None:
        region = SimpleNamespace(
            key='colorado_rockies',
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
        )
        bundle = {
            'created_at': '2026-04-25T00:00:00+00:00',
            'dynamic_model_type': 'mts_lstm',
            'dynamic_model_version': 'mts_lstm_shadow_v1',
            'surrogate_model_version': 'rf_surrogate_v1',
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': ['snowfall_24h', 'wind_loading'],
            'calibration_method': 'isotonic_v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'training_dataset_version': 'real_event_join_v1',
        }
        rows = [
            {
                'row': 0,
                'col': 0,
                'status': 'ready',
                'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
                'terrain_inputs': {'slope': 0.5},
                'shap_context': {'top_features': []},
            },
            {
                'row': 0,
                'col': 1,
                'status': 'unavailable_terrain',
                'availability_reason': 'unavailable_terrain',
                'weather_inputs': {},
                'terrain_inputs': {},
                'shap_context': {'top_features': []},
            },
            {
                'row': 0,
                'col': 2,
                'status': 'unavailable_weather',
                'availability_reason': 'unavailable_weather',
                'weather_inputs': {},
                'terrain_inputs': {},
                'shap_context': {'top_features': []},
            },
        ]

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=72,
        )

        self.assertEqual(payload['status'], 'partial')
        self.assertEqual(payload['ready_cell_count'], 1)
        self.assertEqual(payload['stale_cell_count'], 2)
        self.assertEqual(payload['unavailable_terrain_cell_count'], 1)
        self.assertEqual(payload['unavailable_weather_cell_count'], 1)
        self.assertFalse(payload['model_metadata']['stale'])

    @patch('backend.daily_inference.has_supabase_credentials', return_value=False)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_marks_all_unavailable_regions_stale(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
    ) -> None:
        region = SimpleNamespace(
            key='colorado_rockies',
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
        )
        bundle = {
            'created_at': '2026-04-25T00:00:00+00:00',
            'dynamic_model_type': 'mts_lstm',
            'dynamic_model_version': 'mts_lstm_shadow_v1',
            'surrogate_model_version': 'rf_surrogate_v1',
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': ['snowfall_24h', 'wind_loading'],
            'calibration_method': 'isotonic_v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'training_dataset_version': 'real_event_join_v1',
        }
        rows = [
            {'row': 0, 'col': 0, 'status': 'unavailable_terrain', 'availability_reason': 'unavailable_terrain', 'weather_inputs': {}, 'terrain_inputs': {}},
            {'row': 0, 'col': 1, 'status': 'unavailable_weather', 'availability_reason': 'unavailable_weather', 'weather_inputs': {}, 'terrain_inputs': {}},
        ]

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=72,
        )

        self.assertEqual(payload['status'], 'stale')
        self.assertEqual(payload['ready_cell_count'], 0)
        self.assertEqual(payload['stale_cell_count'], 2)
        self.assertTrue(payload['model_metadata']['stale'])

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    @patch('backend.daily_inference.has_supabase_credentials', return_value=False)
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_tolerates_unavailable_cells_during_runout_generation(
        self,
        _fetch_sar_evidence_mock,
        _has_creds_mock,
    ) -> None:
        region = SimpleNamespace(
            key='colorado_rockies',
            name='Colorado Rockies',
            bbox=(38.5, -107.5, 40.5, -105.5),
        )
        bundle = {
            'created_at': '2026-04-25T00:00:00+00:00',
            'dynamic_model_type': 'mts_lstm',
            'dynamic_model_version': 'mts_lstm_shadow_v1',
            'surrogate_model_version': 'rf_surrogate_v1',
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': ['snowfall_24h', 'wind_loading'],
            'calibration_method': 'isotonic_v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'training_dataset_version': 'real_event_join_v1',
        }
        rows = [
            {
                'row': 0,
                'col': 0,
                'lat': 39.10,
                'lng': -106.10,
                'lat_end': 39.11,
                'lng_end': -106.09,
                'risk_score': 4,
                'probability': 0.72,
                'runout_seed': True,
                'status': 'ready',
                'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
                'terrain_inputs': {'slope_deg': 34.0, 'aspect_deg': 180.0, 'slope': 0.5},
                'shap_context': {'top_features': []},
            },
            {
                'row': 0,
                'col': 1,
                'lat': 39.20,
                'lng': -106.20,
                'lat_end': 39.21,
                'lng_end': -106.19,
                'risk_score': 0,
                'probability': None,
                'runout_seed': False,
                'status': 'unavailable_terrain',
                'availability_reason': 'unavailable_terrain',
                'weather_inputs': {},
                'terrain_inputs': {},
                'shap_context': {'top_features': []},
            },
        ]

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=72,
        )

        self.assertEqual(payload['status'], 'partial')
        self.assertEqual(payload['ready_cell_count'], 1)
        self.assertEqual(len(payload['runout_polygons']), 1)
        self.assertEqual(payload['runout_polygons'][0]['row'], 0)
        self.assertEqual(payload['runout_polygons'][0]['col'], 0)

    @patch('backend.daily_inference.patch_first_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'davos', 'region_name': 'Davos', 'forecast_date': '2026-04-25', 'horizon_hours': 72, 'grid_geojson': []})
    @patch('backend.daily_inference.build_cells', return_value=[])
    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='davos', name='Davos')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_skips_model_status_publish_in_dry_run(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        _build_cells_mock,
        upsert_forecast_grid_mock,
        _dump_json_mock,
        _has_creds_mock,
        patch_first_row_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        exit_code = main(['--dry-run'])

        self.assertEqual(exit_code, 0)
        self.assertTrue(upsert_forecast_grid_mock.call_args.kwargs['dry_run'])
        patch_first_row_mock.assert_not_called()

    @patch('backend.daily_inference.patch_first_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'davos', 'region_name': 'Davos', 'forecast_date': '2026-04-25', 'horizon_hours': 72, 'grid_geojson': []})
    @patch('backend.daily_inference.build_cells', return_value=[])
    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='davos', name='Davos')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_honors_explicit_artifact_dir(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        _build_cells_mock,
        _upsert_forecast_grid_mock,
        _dump_json_mock,
        _has_creds_mock,
        patch_first_row_mock,
    ) -> None:
        artifact_dir = Path('/tmp/fake-artifact-dir')
        resolve_artifact_dir_mock.return_value = artifact_dir

        exit_code = main(['--dry-run', '--artifact-dir', str(artifact_dir)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(resolve_artifact_dir_mock.call_args.args[1], artifact_dir)
        self.assertTrue(resolve_artifact_dir_mock.call_args.kwargs['require_model'])
        patch_first_row_mock.assert_not_called()

    @patch('backend.daily_inference._fetch_latest_sar_summary', return_value={})
    @patch('backend.daily_inference.fetch_historical_weather_window', return_value={'samples': []})
    @patch('backend.daily_inference.select_hourly_weather_sample', return_value={})
    @patch('backend.daily_inference.fetch_forecast_weather_profile', return_value={'samples': []})
    @patch('backend.daily_inference.predict_production_probability', return_value=(0.67, None))
    @patch('backend.daily_inference.collect_tree_probabilities', return_value=np.asarray([[0.4, 0.8]], dtype=np.float32))
    @patch('backend.daily_inference.compute_tree_shap')
    @patch('backend.daily_inference.build_tree_shap_explainer', return_value=object())
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.extract_cell_terrain')
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_preserves_surrogate_explanation_contract(
        self,
        build_grid_mock,
        build_feature_row_mock,
        extract_terrain_mock,
        fetch_snowpack_proxies_mock,
        _build_explainer_mock,
        compute_tree_shap_mock,
        _collect_tree_probs_mock,
        _predict_production_probability_mock,
        _forecast_weather_mock,
        _select_hourly_mock,
        _history_mock,
        _sar_summary_mock,
    ) -> None:
        compute_tree_shap_mock.return_value = (
            {'snowfall_24h': 0.42, 'wind_loading': -0.21},
            [
                {'feature': 'snowfall_24h', 'shap_value': 0.42, 'feature_value': 0.7, 'rank': 1},
                {'feature': 'wind_loading', 'shap_value': -0.21, 'feature_value': 0.3, 'rank': 2},
            ],
        )
        build_grid_mock.return_value = [{
            'row': 0,
            'col': 0,
            'lat': 46.8,
            'lng': 9.8,
            'lat_end': 46.81,
            'lng_end': 9.81,
        }]
        fetch_snowpack_proxies_mock.return_value = [
            SnowpackProxyBatchResult(
                proxy=SnowpackProxy(
                    estimated_shear_strength=0.42,
                    snow_settlement_index=0.16,
                    season_start='2025-11-01',
                    method='seasonal_cumulative_v1',
                ),
                status='ready',
            )
        ]
        extract_terrain_mock.return_value = {
            'elevation_m': 2450.0,
            'slope_angle_deg': 38.0,
            'aspect_deg': 180.0,
            'clamped_to_bounds': 0.0,
            'window_search_needed': 0.0,
        }
        feature_row = {feature: 0.1 for feature in FEATURE_COLUMNS}
        feature_row.update({
            'snowfall_24h': 0.7,
            'wind_loading': 0.3,
            'temp_gradient': 0.2,
            'freezing_level_proxy': 0.4,
            'elevation': 0.6,
            'terrain_roughness': 0.5,
            'aspect_loading': 0.25,
            'slope': 0.45,
        })
        build_feature_row_mock.return_value = {
            'feature_row': feature_row,
            'raw_inputs': {
                'temperature_2m': -8.0,
                'windspeed_10m': 11.0,
                'winddirection_10m': 180.0,
                'downscaled_temperature_c': -9.0,
                'snowfall_24h_cm': 18.0,
                'precipitation_24h_mm': 9.0,
            },
            'snowpack_proxy': SimpleNamespace(
                estimated_shear_strength=0.42,
                snow_settlement_index=0.16,
                season_start='2025-11-01',
                method='proxy_v1',
            ),
        }

        class _DummySelector:
            def transform(self, frame: pd.DataFrame) -> np.ndarray:
                return np.asarray([[0.7, 0.3]], dtype=np.float32)

        class _DummyCalibratedModel:
            def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
                return np.asarray([[0.33, 0.67]], dtype=np.float32)

        bundle = {
            'selector': _DummySelector(),
            'calibrated_model': _DummyCalibratedModel(),
            'base_model': object(),
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_means': {'snowfall_24h': 0.2, 'wind_loading': 0.1},
            'surrogate_model_version': 'rf_surrogate_v1',
            'created_at': '2026-04-25T00:00:00+00:00',
            'calibration_method': 'isotonic_v1',
        }
        region = SimpleNamespace(key='davos', center=(46.8, 9.8))

        rows = build_cells(
            region=region,
            bundle=bundle,
            grid_size=1,
            forecast_date=pd.Timestamp('2026-04-25T00:00:00Z'),
        )

        self.assertEqual(len(rows), 1)
        cell = rows[0]
        self.assertEqual(cell['status'], 'ready')
        self.assertFalse(cell['stale'])
        self.assertFalse(cell['disabled'])
        self.assertEqual(cell['surrogate_model_version'], 'rf_surrogate_v1')
        self.assertEqual(cell['dominant_driver_feature'], 'snowfall_24h')
        self.assertEqual(cell['shap_values']['snowfall_24h'], 0.42)
        self.assertEqual(cell['shap_context']['top_features'][0]['feature'], 'snowfall_24h')
        self.assertEqual(cell['inference_backend'], 'github_actions_surrogate_rf')
        self.assertEqual(
            build_feature_row_mock.call_args.kwargs['snowpack_proxy_override'].method,
            'seasonal_cumulative_v1',
        )

    @patch('backend.daily_inference._fetch_latest_sar_summary', return_value={})
    @patch('backend.daily_inference.fetch_historical_weather_window', side_effect=RuntimeError('HTTP 429'))
    @patch('backend.daily_inference.select_hourly_weather_sample', return_value={})
    @patch('backend.daily_inference.fetch_forecast_weather_profile', return_value={'samples': []})
    @patch('backend.daily_inference.predict_production_probability', return_value=(0.67, {'enabled': True, 'dynamic_model_type': 'mts_lstm_v1', 'dynamic_model_version': 'mts-lstm-42'}))
    @patch('backend.daily_inference.collect_tree_probabilities', return_value=np.asarray([[0.4, 0.8]], dtype=np.float32))
    @patch('backend.daily_inference.compute_tree_shap', return_value=({'snowfall_24h': 0.42}, [{'feature': 'snowfall_24h', 'shap_value': 0.42, 'feature_value': 0.7, 'rank': 1}]))
    @patch('backend.daily_inference.build_tree_shap_explainer', return_value=object())
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.build_inference_branches', return_value=SimpleNamespace(hourly=np.zeros((24, 6)), daily=np.zeros((7, 6)), static=np.zeros((6,))))
    @patch('backend.daily_inference.extract_cell_terrain')
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_fails_closed_when_history_is_unavailable(
        self,
        build_grid_mock,
        build_feature_row_mock,
        extract_terrain_mock,
        _build_branches_mock,
        fetch_snowpack_proxies_mock,
        _build_explainer_mock,
        _compute_tree_shap_mock,
        _collect_tree_probs_mock,
        _predict_production_probability_mock,
        _forecast_weather_mock,
        _select_hourly_mock,
        history_mock,
        _sar_summary_mock,
    ) -> None:
        build_grid_mock.return_value = [{
            'row': 0,
            'col': 0,
            'lat': 46.8,
            'lng': 9.8,
            'lat_end': 46.81,
            'lng_end': 9.81,
        }]
        fetch_snowpack_proxies_mock.return_value = [
            SnowpackProxyBatchResult(
                proxy=SnowpackProxy(
                    estimated_shear_strength=0.42,
                    snow_settlement_index=0.16,
                    season_start='2025-11-01',
                    method='seasonal_cumulative_v1',
                ),
                status='ready',
            )
        ]
        extract_terrain_mock.return_value = {
            'elevation_m': 2450.0,
            'slope_angle_deg': 38.0,
            'aspect_deg': 180.0,
            'clamped_to_bounds': 0.0,
            'window_search_needed': 0.0,
        }
        feature_row = {feature: 0.1 for feature in FEATURE_COLUMNS}
        feature_row.update({
            'snowfall_24h': 0.7,
            'wind_loading': 0.3,
            'temp_gradient': 0.2,
            'freezing_level_proxy': 0.4,
            'elevation': 0.6,
            'terrain_roughness': 0.5,
            'aspect_loading': 0.25,
            'slope': 0.45,
        })
        build_feature_row_mock.return_value = {
            'feature_row': feature_row,
            'raw_inputs': {
                'temperature_2m': -8.0,
                'windspeed_10m': 11.0,
                'winddirection_10m': 180.0,
                'downscaled_temperature_c': -9.0,
                'snowfall_24h_cm': 18.0,
                'precipitation_24h_mm': 9.0,
            },
            'snowpack_proxy': SimpleNamespace(
                estimated_shear_strength=0.42,
                snow_settlement_index=0.16,
                season_start='2025-11-01',
                method='proxy_v1',
            ),
        }

        class _DummySelector:
            def transform(self, frame: pd.DataFrame) -> np.ndarray:
                return np.asarray([[0.7, 0.3]], dtype=np.float32)

        class _DummyCalibratedModel:
            def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
                return np.asarray([[0.33, 0.67]], dtype=np.float32)

        bundle = {
            'selector': _DummySelector(),
            'calibrated_model': _DummyCalibratedModel(),
            'base_model': object(),
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_means': {'snowfall_24h': 0.2, 'wind_loading': 0.1},
            'surrogate_model_version': 'rf_surrogate_v1',
            'created_at': '2026-04-25T00:00:00+00:00',
            'calibration_method': 'isotonic_v1',
            'lstm_head': SimpleNamespace(
                model=object(),
                dynamic_features=['snowfall_24h', 'precipitation_24h', 'wind_loading', 'wind_directional_loading', 'temp_gradient', 'freezing_level_proxy'],
                static_features=['slope', 'elevation', 'aspect_loading', 'terrain_roughness', 'curvature_proxy', 'northness'],
                metadata={'hourly_steps': 24, 'daily_steps': 7},
            ),
        }
        region = SimpleNamespace(key='davos', center=(46.8, 9.8))

        with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
            build_cells(
                region=region,
                bundle=bundle,
                grid_size=1,
                forecast_date=pd.Timestamp('2026-04-25T00:00:00Z'),
            )

        history_mock.assert_called_once()
        build_feature_row_mock.assert_not_called()

    @patch('backend.daily_inference._fetch_latest_sar_summary', return_value={})
    @patch('backend.daily_inference.fetch_historical_weather_window', return_value={'samples': []})
    @patch('backend.daily_inference.select_hourly_weather_sample', return_value={})
    @patch('backend.daily_inference.fetch_forecast_weather_profile', return_value={'samples': []})
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.build_tree_shap_explainer', return_value=object())
    @patch('backend.daily_inference.extract_cell_terrain')
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_marks_unavailable_weather_cells_without_aborting_region(
        self,
        build_grid_mock,
        build_feature_row_mock,
        _extract_terrain_mock,
        _build_explainer_mock,
        fetch_snowpack_proxies_mock,
        _forecast_weather_mock,
        _select_hourly_mock,
        _history_mock,
        _sar_summary_mock,
    ) -> None:
        build_grid_mock.return_value = [{
            'row': 0,
            'col': 0,
            'lat': 46.8,
            'lng': 9.8,
            'lat_end': 46.81,
            'lng_end': 9.81,
        }]
        bundle = {
            'selector': SimpleNamespace(transform=lambda frame: np.asarray([[0.7, 0.3]], dtype=np.float32)),
            'calibrated_model': SimpleNamespace(predict_proba=lambda frame: np.asarray([[0.33, 0.67]], dtype=np.float32)),
            'base_model': object(),
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_means': {'snowfall_24h': 0.2, 'wind_loading': 0.1},
            'surrogate_model_version': 'rf_surrogate_v1',
            'created_at': '2026-04-25T00:00:00+00:00',
            'calibration_method': 'isotonic_v1',
        }
        region = SimpleNamespace(key='davos', center=(46.8, 9.8))

        fetch_snowpack_proxies_mock.return_value = [
            SnowpackProxyBatchResult(
                proxy=None,
                status='unavailable_weather',
                error='missing seasonal payload',
            )
        ]

        rows = build_cells(
            region=region,
            bundle=bundle,
            grid_size=1,
            forecast_date=pd.Timestamp('2026-04-25T00:00:00Z'),
        )

        self.assertEqual(len(rows), 1)
        cell = rows[0]
        self.assertEqual(cell['status'], 'unavailable_weather')
        self.assertTrue(cell['stale'])
        self.assertTrue(cell['disabled'])
        self.assertEqual(cell['availability_reason'], 'unavailable_weather')
        build_feature_row_mock.assert_not_called()

    @patch('backend.daily_inference._fetch_latest_sar_summary', return_value={})
    @patch('backend.daily_inference.fetch_historical_weather_window', return_value={'samples': []})
    @patch('backend.daily_inference.select_hourly_weather_sample', return_value={})
    @patch('backend.daily_inference.fetch_forecast_weather_profile', return_value={'samples': []})
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.build_tree_shap_explainer', return_value=object())
    @patch('backend.daily_inference.extract_cell_terrain', side_effect=ValueError('no terrain within 50m'))
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_marks_unavailable_terrain_cells_stale(
        self,
        build_grid_mock,
        build_feature_row_mock,
        _extract_terrain_mock,
        _build_explainer_mock,
        fetch_snowpack_proxies_mock,
        _forecast_weather_mock,
        _select_hourly_mock,
        _history_mock,
        _sar_summary_mock,
    ) -> None:
        build_grid_mock.return_value = [{
            'row': 0,
            'col': 0,
            'lat': 46.8,
            'lng': 9.8,
            'lat_end': 46.81,
            'lng_end': 9.81,
        }]
        fetch_snowpack_proxies_mock.return_value = [
            SnowpackProxyBatchResult(
                proxy=SnowpackProxy(
                    estimated_shear_strength=0.42,
                    snow_settlement_index=0.16,
                    season_start='2025-11-01',
                    method='seasonal_cumulative_v1',
                ),
                status='ready',
            )
        ]
        bundle = {
            'selector': SimpleNamespace(transform=lambda frame: np.asarray([[0.7, 0.3]], dtype=np.float32)),
            'calibrated_model': SimpleNamespace(predict_proba=lambda frame: np.asarray([[0.33, 0.67]], dtype=np.float32)),
            'base_model': object(),
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_means': {'snowfall_24h': 0.2, 'wind_loading': 0.1},
            'surrogate_model_version': 'rf_surrogate_v1',
            'dynamic_model_type': 'mts_lstm_v1',
            'dynamic_model_version': 'mts-lstm-42',
            'created_at': '2026-04-25T00:00:00+00:00',
            'calibration_method': 'isotonic_v1',
        }
        region = SimpleNamespace(key='davos', center=(46.8, 9.8))

        rows = build_cells(
            region=region,
            bundle=bundle,
            grid_size=1,
            forecast_date=pd.Timestamp('2026-04-25T00:00:00Z'),
        )

        self.assertEqual(len(rows), 1)
        cell = rows[0]
        self.assertEqual(cell['status'], 'unavailable_terrain')
        self.assertTrue(cell['stale'])
        self.assertTrue(cell['disabled'])
        self.assertEqual(cell['availability_reason'], 'unavailable_terrain')
        self.assertEqual(cell['risk_score'], 0)
        self.assertEqual(cell['surrogate_model_version'], 'rf_surrogate_v1')
        self.assertEqual(cell['dynamic_model_version'], 'mts-lstm-42')
        self.assertEqual(cell['shap_values'], {})
        build_feature_row_mock.assert_not_called()

    @patch.dict('os.environ', {'DEM_ROOT': '/artifacts/dem'}, clear=False)
    @patch('backend.daily_inference._fetch_latest_sar_summary', return_value={})
    @patch('backend.daily_inference.fetch_historical_weather_window', return_value={'samples': []})
    @patch('backend.daily_inference.select_hourly_weather_sample', return_value={})
    @patch('backend.daily_inference.fetch_forecast_weather_profile', return_value={'samples': []})
    @patch('backend.daily_inference.predict_production_probability', return_value=(0.67, None))
    @patch('backend.daily_inference.collect_tree_probabilities', return_value=np.asarray([[0.4, 0.8]], dtype=np.float32))
    @patch('backend.daily_inference.compute_tree_shap', return_value=({}, []))
    @patch('backend.daily_inference.build_tree_shap_explainer', return_value=object())
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.extract_cell_terrain')
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_reads_dem_from_env_root(
        self,
        build_grid_mock,
        build_feature_row_mock,
        extract_terrain_mock,
        fetch_snowpack_proxies_mock,
        _build_explainer_mock,
        _compute_tree_shap_mock,
        _collect_tree_probs_mock,
        _predict_production_probability_mock,
        _forecast_weather_mock,
        _select_hourly_mock,
        _history_mock,
        _sar_summary_mock,
    ) -> None:
        build_grid_mock.return_value = [{
            'row': 0,
            'col': 0,
            'lat': 46.8,
            'lng': 9.8,
            'lat_end': 46.81,
            'lng_end': 9.81,
        }]
        fetch_snowpack_proxies_mock.return_value = [
            SnowpackProxyBatchResult(
                proxy=SnowpackProxy(
                    estimated_shear_strength=0.42,
                    snow_settlement_index=0.16,
                    season_start='2025-11-01',
                    method='seasonal_cumulative_v1',
                ),
                status='ready',
            )
        ]
        extract_terrain_mock.return_value = {
            'elevation_m': 2450.0,
            'slope_angle_deg': 38.0,
            'aspect_deg': 180.0,
            'clamped_to_bounds': 0.0,
            'window_search_needed': 0.0,
        }
        feature_row = {feature: 0.1 for feature in FEATURE_COLUMNS}
        build_feature_row_mock.return_value = {
            'feature_row': feature_row,
            'raw_inputs': {
                'temperature_2m': -8.0,
                'windspeed_10m': 11.0,
                'winddirection_10m': 180.0,
                'downscaled_temperature_c': -9.0,
                'snowfall_24h_cm': 18.0,
                'precipitation_24h_mm': 9.0,
            },
            'snowpack_proxy': SimpleNamespace(
                estimated_shear_strength=0.42,
                snow_settlement_index=0.16,
                season_start='2025-11-01',
                method='proxy_v1',
            ),
        }

        class _DummySelector:
            def transform(self, frame: pd.DataFrame) -> np.ndarray:
                return np.asarray([[0.7, 0.3]], dtype=np.float32)

        class _DummyCalibratedModel:
            def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
                return np.asarray([[0.33, 0.67]], dtype=np.float32)

        bundle = {
            'selector': _DummySelector(),
            'calibrated_model': _DummyCalibratedModel(),
            'base_model': object(),
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_means': {'snowfall_24h': 0.2, 'wind_loading': 0.1},
            'surrogate_model_version': 'rf_surrogate_v1',
            'created_at': '2026-04-25T00:00:00+00:00',
            'calibration_method': 'isotonic_v1',
        }
        region = SimpleNamespace(key='davos', center=(46.8, 9.8))

        build_cells(
            region=region,
            bundle=bundle,
            grid_size=1,
            forecast_date=pd.Timestamp('2026-04-25T00:00:00Z'),
        )

        terrain_call = extract_terrain_mock.call_args.args[0]
        self.assertEqual(terrain_call, '/artifacts/dem/davos.tif')


if __name__ == '__main__':
    unittest.main()
