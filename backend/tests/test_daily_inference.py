from __future__ import annotations

import unittest
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import types

import numpy as np
import pandas as pd

if 'imblearn.over_sampling' not in sys.modules:
    imblearn_module = types.ModuleType('imblearn')
    over_sampling_module = types.ModuleType('imblearn.over_sampling')

    class _KMeansSMOTEStub:
        def __init__(self, *args, **kwargs) -> None:
            pass

    over_sampling_module.KMeansSMOTE = _KMeansSMOTEStub
    imblearn_module.over_sampling = over_sampling_module
    sys.modules['imblearn'] = imblearn_module
    sys.modules['imblearn.over_sampling'] = over_sampling_module

from backend.common.features import FEATURE_COLUMNS
from backend.common.avalanche_problem_classifier import classify_avalanche_problem
from backend.common.public_eligibility import apply_public_eligibility_metric
from backend.common.snowpack_proxy import SnowpackProxy, SnowpackProxyBatchResult
from backend.daily_inference import ProofModeOptions, build_cells, build_publication_proof, main, upsert_forecast_grid
from backend.models.surrogate_rf import TreeShapUnavailableError


class PublicationProofTests(unittest.TestCase):
    def test_build_publication_proof_marks_same_day_published_region(self) -> None:
        proof = build_publication_proof(
            outputs=[
                {
                    'region_key': 'japanese_alps',
                    'region_name': 'Japanese Alps',
                    'forecast_date': '2026-05-08',
                    'horizon_hours': 72,
                    'status': 'ready',
                    'ready_cell_count': 381,
                    'stale_cell_count': 0,
                    'forecast_bulletins': {'schema_version': 'forecast-bulletin/v1'},
                    'published_at': '2026-05-08T02:00:00+00:00',
                    'hourly_grids': [[] for _ in range(72)],
                    'model_metadata': {
                        'forecast_run_id': 'run-1',
                        'manifest_storage_ref': 'forecast-products/avalanche/japanese_alps/run-1/manifest.json',
                    },
                },
            ],
            generated_at=datetime(2026, 5, 8, 4, 0, tzinfo=timezone.utc),
            dry_run=False,
            supabase_enabled=True,
            expected_forecast_date='2026-05-08',
            artifact_dir=Path('/tmp/artifacts/20260508T040000Z'),
        )

        self.assertEqual(proof['proof_status'], 'passed')
        self.assertEqual(proof['same_day_published_count'], 1)
        region = proof['regions'][0]
        self.assertTrue(region['same_day_published'])
        self.assertEqual(region['publication_status'], 'published')
        self.assertEqual(region['freshness_hours'], 2)
        self.assertEqual(region['hour_count'], 72)
        self.assertFalse(region['full_grid_publication_ready'])

    def test_build_publication_proof_fails_stale_or_unpublished_region(self) -> None:
        proof = build_publication_proof(
            outputs=[
                {
                    'region_key': 'japanese_alps',
                    'region_name': 'Japanese Alps',
                    'forecast_date': '2026-05-07',
                    'horizon_hours': 72,
                    'status': 'ready',
                    'ready_cell_count': 381,
                    'stale_cell_count': 0,
                    'forecast_bulletins': {'schema_version': 'forecast-bulletin/v1'},
                    'model_metadata': {
                        'forecast_run_id': 'run-1',
                        'manifest_storage_ref': 'forecast-products/avalanche/japanese_alps/run-1/manifest.json',
                    },
                },
            ],
            generated_at=datetime(2026, 5, 8, 4, 0, tzinfo=timezone.utc),
            dry_run=False,
            supabase_enabled=True,
            expected_forecast_date='2026-05-08',
            artifact_dir=Path('/tmp/artifacts/20260508T040000Z'),
        )

        self.assertEqual(proof['proof_status'], 'failed')
        self.assertEqual(proof['failures'], ['japanese_alps'])
        self.assertFalse(proof['regions'][0]['same_day_published'])

    def test_build_publication_proof_requires_full_grid_and_structured_bulletin(self) -> None:
        cells = [
            {'status': 'ready', 'risk_score': 2}
            for _ in range(16)
        ]
        proof = build_publication_proof(
            outputs=[
                {
                    'region_key': 'colorado_rockies',
                    'region_name': 'Colorado Rockies',
                    'forecast_date': '2026-05-08',
                    'horizon_hours': 2,
                    'status': 'ready',
                    'ready_cell_count': 16,
                    'stale_cell_count': 0,
                    'forecast_bulletins': {
                        'schema_version': 'forecast-bulletin/v1',
                        'danger_level': 2,
                        'dayparts': [{'window': 'day_1_morning'}],
                    },
                    'published_at': '2026-05-08T02:00:00+00:00',
                    'grid_geojson': cells,
                    'hourly_grids': [cells, cells],
                    'model_metadata': {
                        'forecast_run_id': 'run-1',
                        'manifest_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-1/manifest.json',
                    },
                },
            ],
            generated_at=datetime(2026, 5, 8, 4, 0, tzinfo=timezone.utc),
            dry_run=False,
            supabase_enabled=True,
            expected_forecast_date='2026-05-08',
            artifact_dir=Path('/tmp/artifacts/20260508T040000Z'),
            expected_grid_size=4,
            require_full_grid=True,
        )

        self.assertEqual(proof['proof_status'], 'passed')
        self.assertEqual(proof['full_grid_publication_ready_count'], 1)
        region = proof['regions'][0]
        self.assertTrue(region['full_grid_cells_present'])
        self.assertTrue(region['full_grid_ready'])
        self.assertTrue(region['structured_bulletin'])
        self.assertTrue(region['full_grid_publication_ready'])

    def test_build_publication_proof_rejects_proof_mode_without_bulletin_when_full_grid_required(self) -> None:
        cells = [{'status': 'ready'} for _ in range(25)]
        proof = build_publication_proof(
            outputs=[
                {
                    'region_key': 'colorado_rockies',
                    'region_name': 'Colorado Rockies',
                    'forecast_date': '2026-05-08',
                    'horizon_hours': 72,
                    'status': 'ready',
                    'ready_cell_count': 25,
                    'stale_cell_count': 0,
                    'forecast_bulletins': {},
                    'published_at': '2026-05-08T02:00:00+00:00',
                    'grid_geojson': cells,
                    'hourly_grids': [cells for _ in range(72)],
                    'model_metadata': {
                        'forecast_run_id': 'run-1',
                        'manifest_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-1/manifest.json',
                    },
                },
            ],
            generated_at=datetime(2026, 5, 8, 4, 0, tzinfo=timezone.utc),
            dry_run=False,
            supabase_enabled=True,
            expected_forecast_date='2026-05-08',
            artifact_dir=Path('/tmp/artifacts/20260508T040000Z'),
            expected_grid_size=20,
            require_full_grid=True,
        )

        self.assertEqual(proof['proof_status'], 'failed')
        self.assertEqual(proof['failures'], ['colorado_rockies'])
        region = proof['regions'][0]
        self.assertFalse(region['full_grid_cells_present'])
        self.assertFalse(region['structured_bulletin'])
        self.assertFalse(region['full_grid_publication_ready'])

    def test_build_publication_proof_rejects_synthetic_full_grid_publication(self) -> None:
        cells = [
            {
                'status': 'ready',
                'risk_score': 2,
                'snowpack_proxy': {'method': 'synthetic_full_grid_publication_v1'},
            }
            for _ in range(16)
        ]
        proof = build_publication_proof(
            outputs=[
                {
                    'region_key': 'colorado_rockies',
                    'region_name': 'Colorado Rockies',
                    'forecast_date': '2026-05-08',
                    'horizon_hours': 2,
                    'status': 'ready',
                    'ready_cell_count': 16,
                    'stale_cell_count': 0,
                    'forecast_bulletins': {
                        'schema_version': 'forecast-bulletin/v1',
                        'danger_level': 2,
                        'dayparts': [{'window': 'day_1_morning'}],
                    },
                    'published_at': '2026-05-08T02:00:00+00:00',
                    'grid_geojson': cells,
                    'hourly_grids': [cells, cells],
                    'model_metadata': {
                        'forecast_run_id': 'run-1',
                        'manifest_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-1/manifest.json',
                    },
                },
            ],
            generated_at=datetime(2026, 5, 8, 4, 0, tzinfo=timezone.utc),
            dry_run=False,
            supabase_enabled=True,
            expected_forecast_date='2026-05-08',
            artifact_dir=Path('/tmp/artifacts/20260508T040000Z'),
            expected_grid_size=4,
            require_full_grid=True,
        )

        self.assertEqual(proof['proof_status'], 'failed')
        self.assertEqual(proof['failures'], ['colorado_rockies'])
        region = proof['regions'][0]
        self.assertTrue(region['same_day_published'])
        self.assertTrue(region['full_grid_ready'])
        self.assertTrue(region['structured_bulletin'])
        self.assertTrue(region['synthetic_inputs_present'])
        self.assertEqual(region['synthetic_input_methods'], ['synthetic_full_grid_publication_v1'])
        self.assertFalse(region['publish_eligible'])
        self.assertFalse(region['full_grid_publication_ready'])


class ForecastGridMetadataTests(unittest.TestCase):
    @patch.dict(os.environ, {'ALLOW_SYNTHETIC_PUBLICATION': 'false'}, clear=False)
    @patch('backend.daily_inference.promote_forecast_run')
    @patch(
        'backend.daily_inference.publish_forecast_run',
        return_value={
            'forecast_run_id': 'run-synthetic',
            'manifest_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-synthetic/manifest.json',
            'runout_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-synthetic/runouts.json.gz',
            'hours': [],
        },
    )
    @patch('backend.daily_inference.rest_insert')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_blocks_synthetic_publication(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
        _rest_insert_mock,
        publish_forecast_run_mock,
        promote_forecast_run_mock,
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
        rows = [{
            'row': 0,
            'col': 0,
            'status': 'ready',
            'risk_score': 2,
            'probability_risk_score': 2,
            'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
            'terrain_inputs': {'slope': 0.5, 'slope_angle_deg': 35.0, 'aspect_deg': 15.0, 'elevation_m': 2410.0},
            'snowpack_proxy': {'method': 'synthetic_fallback_v1'},
            'shap_context': {'top_features': []},
        }]

        with self.assertRaisesRegex(RuntimeError, 'Synthetic inputs cannot be published'):
            upsert_forecast_grid(
                region,
                bundle,
                pd.Timestamp('2026-04-25T00:00:00Z'),
                rows=rows,
                horizon_hours=72,
                grid_size=20,
                proof_options=ProofModeOptions(
                    skip_compatibility_write=True,
                    skip_shap_cache=True,
                    skip_runout_generation=True,
                ),
            )

        publish_forecast_run_mock.assert_not_called()
        promote_forecast_run_mock.assert_not_called()

    @patch('backend.daily_inference.publish_forecast_run')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_allows_synthetic_dry_run_with_lineage_metadata(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
        publish_forecast_run_mock,
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
        rows = [{
            'row': 0,
            'col': 0,
            'status': 'ready',
            'risk_score': 2,
            'probability_risk_score': 2,
            'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
            'terrain_inputs': {'slope': 0.5, 'slope_angle_deg': 35.0, 'aspect_deg': 15.0, 'elevation_m': 2410.0},
            'snowpack_proxy': {'method': 'synthetic_fallback_v1'},
            'shap_context': {'top_features': []},
        }]

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=72,
            grid_size=20,
            dry_run=True,
            proof_options=ProofModeOptions(skip_runout_generation=True),
        )

        metadata = payload['model_metadata']
        self.assertTrue(metadata['synthetic_inputs_present'])
        self.assertEqual(metadata['synthetic_input_methods'], ['synthetic_fallback_v1'])
        self.assertEqual(metadata['data_lineage'], 'synthetic_internal')
        self.assertFalse(metadata['publish_eligible'])
        publish_forecast_run_mock.assert_not_called()

    @patch('backend.daily_inference.promote_forecast_run')
    @patch('backend.daily_inference.attach_compatibility_forecast_grid')
    @patch('backend.daily_inference.rest_get')
    @patch(
        'backend.daily_inference.publish_forecast_run',
        return_value={
            'forecast_run_id': 'run-proof-1',
            'manifest_storage_ref': 'forecast-products/avalanche/japanese_alps/run-proof-1/manifest.json',
            'runout_storage_ref': 'forecast-products/avalanche/japanese_alps/run-proof-1/runouts.json.gz',
            'hours': [],
        },
    )
    @patch('backend.daily_inference._upsert_shap_cache', return_value='empty')
    @patch('backend.daily_inference.rest_insert')
    @patch('backend.daily_inference.rest_upsert')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons')
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_proof_mode_skips_compatibility_and_emits_stage_event(
        self,
        _fetch_sar_evidence_mock,
        build_runout_mock,
        _has_creds_mock,
        rest_upsert_mock,
        rest_insert_mock,
        upsert_shap_cache_mock,
        publish_forecast_run_mock,
        rest_get_mock,
        attach_compatibility_forecast_grid_mock,
        promote_forecast_run_mock,
    ) -> None:
        region = SimpleNamespace(
            key='japanese_alps',
            name='Japanese Alps',
            bbox=(36.0, 137.0, 37.0, 138.0),
        )
        bundle = {
            'created_at': '2026-04-25T00:00:00+00:00',
            'dynamic_model_type': 'mts_lstm',
            'dynamic_model_version': 'mts_lstm_shadow_v1',
            'surrogate_model_version': 'rf_surrogate_v1',
            'selected_features': ['snowfall_24h', 'wind_loading'],
            'feature_columns': ['snowfall_24h', 'wind_loading'],
            'calibration_method': 'isotonic_v1',
            'calibration_profile_version': 'calib-shadow-v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'training_dataset_version': 'real_event_join_v1',
        }
        rows = [{
            'row': 0,
            'col': 0,
            'status': 'ready',
            'risk_score': 1,
            'probability_risk_score': 1,
            'problem_type': 'Unknown',
            'probability': 0.18,
            'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
            'terrain_inputs': {'slope': 0.5, 'slope_angle_deg': 35.0, 'aspect_deg': 15.0, 'elevation_m': 2410.0},
            'shap_values': {},
            'shap_context': {'top_features': []},
        }]
        proof_options = ProofModeOptions(
            enabled=True,
            profile='proof72',
            skip_tree_shap=True,
            skip_shap_cache=True,
            skip_runout_generation=True,
            skip_compatibility_write=True,
            emit_stage_metrics=True,
        )

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=72,
            grid_size=5,
            proof_options=proof_options,
            stage_metrics={
                'compute_started_at': '2026-04-25T00:01:02+00:00',
                'snowpack_fetch_seconds': 1.234,
                'hourly_grid_build_seconds': 2.345,
            },
        )

        self.assertEqual(payload['runout_polygons'], [])
        self.assertEqual(payload['model_metadata']['forecast_run_id'], 'run-proof-1')
        self.assertEqual(payload['model_metadata']['compatibility_write_status'], 'skipped')
        self.assertEqual(payload['model_metadata']['shap_cache_write_status'], 'skipped')
        forecast_bulletin = publish_forecast_run_mock.call_args.kwargs['forecast_bulletins']
        self.assertEqual(forecast_bulletin['danger_level'], 1)
        self.assertEqual(forecast_bulletin['coverage'], 'ready')
        self.assertEqual(forecast_bulletin['source_health']['summary_version'], 'source_health_v1')
        self.assertTrue(forecast_bulletin['source_health']['weather_available'])
        self.assertEqual(forecast_bulletin['decision_provenance']['threshold_profile_origin'], 'heuristic_seeded')
        self.assertEqual(forecast_bulletin['decision_provenance']['dominant_mapping'], 'heuristic_thresholds_and_frequency')
        build_runout_mock.assert_not_called()
        rest_upsert_mock.assert_not_called()
        rest_get_mock.assert_not_called()
        attach_compatibility_forecast_grid_mock.assert_not_called()
        upsert_shap_cache_mock.assert_not_called()
        promote_forecast_run_mock.assert_called_once_with(forecast_run_id='run-proof-1')
        stage_names = [
            call.args[1][0]['stage']
            for call in rest_insert_mock.call_args_list
            if 'stage' in call.args[1][0]
        ]
        self.assertIn('prepublication_compute', stage_names)
        self.assertIn('promote_started', stage_names)
        self.assertIn('promote_completed', stage_names)
        event_record = next(
            call.args[1][0]
            for call in rest_insert_mock.call_args_list
            if call.args[1][0]['stage'] == 'prepublication_compute'
        )
        self.assertEqual(event_record['stage'], 'prepublication_compute')
        self.assertEqual(event_record['status'], 'ok')
        self.assertEqual(event_record['created_at'], '2026-04-25T00:01:02+00:00')
        self.assertEqual(event_record['detail']['profile'], 'proof72')
        self.assertEqual(event_record['detail']['grid_size'], 5)
        self.assertEqual(event_record['detail']['forecast_hours'], 72)

    @patch('backend.daily_inference.promote_forecast_run')
    @patch('backend.daily_inference.attach_compatibility_forecast_grid')
    @patch('backend.daily_inference.rest_get', return_value=[{'id': 'fg-compat'}])
    @patch(
        'backend.daily_inference.publish_forecast_run',
        return_value={
            'forecast_run_id': 'run-1',
            'manifest_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-1/manifest.json',
            'runout_storage_ref': 'forecast-products/avalanche/colorado_rockies/run-1/runouts.json.gz',
            'hours': [],
        },
    )
    @patch('backend.daily_inference._upsert_shap_cache', return_value='empty')
    @patch('backend.daily_inference.rest_upsert')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_persists_hourly_grids_contract(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
        rest_upsert_mock,
        _upsert_shap_cache_mock,
        publish_forecast_run_mock,
        rest_get_mock,
        attach_compatibility_forecast_grid_mock,
        promote_forecast_run_mock,
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
        rows = [{
            'row': 0,
            'col': 0,
            'status': 'ready',
            'risk_score': 4,
            'probability_risk_score': 4,
            'terrain_fused_risk_score': 3,
            'problem_type': 'Wind Slab',
            'probability': 0.63,
            'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
            'terrain_inputs': {'slope': 0.5, 'slope_angle_deg': 35.0, 'aspect_deg': 315.0, 'elevation_m': 2810.0},
            'apt_eligible': True,
            'shap_context': {'top_features': []},
            'explainability_mode': 'tree_shap',
        }]
        hourly_grids = [
            rows,
            [{
                **rows[0],
                'probability': 0.73,
            }],
        ]

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=2,
            hourly_grids=hourly_grids,
        )

        persisted = rest_upsert_mock.call_args.args[1][0]
        self.assertEqual(rest_upsert_mock.call_args.kwargs['returning'], 'minimal')
        self.assertEqual(rest_upsert_mock.call_args.kwargs['timeout_seconds'], 300)
        self.assertEqual(payload['hourly_grids'], hourly_grids)
        self.assertEqual(persisted['hourly_grids'], [])
        self.assertEqual(persisted['grid_geojson'], [])
        self.assertEqual(persisted['runout_polygons'], [])
        self.assertNotIn('ready_cell_count', persisted)
        self.assertEqual(payload['model_metadata']['forecast_run_id'], 'run-1')
        self.assertEqual(payload['model_metadata']['compatibility_forecast_grid_id'], 'fg-compat')
        self.assertEqual(payload['model_metadata']['shap_cache_write_status'], 'empty')
        self.assertEqual(persisted['model_metadata']['compatibility_payload_mode'], 'artifact_refs_only_v1')
        publish_forecast_run_mock.assert_called_once()
        rest_get_mock.assert_called_once()
        attach_compatibility_forecast_grid_mock.assert_called_once_with(
            forecast_run_id='run-1',
            compatibility_forecast_grid_id='fg-compat',
        )
        promote_forecast_run_mock.assert_called_once_with(forecast_run_id='run-1')

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
            'calibration_profile_version': 'calib-shadow-v1',
            'resampling': 'kmeanssmote',
            'tree_variance_policy': 'gaussian_95ci',
            'metrics': {'pss': 0.48},
            'cv_metrics': {'folds': 5},
            'lstm_head_meta': {'uncertainty_method': 'seeded_dropout_ensemble_v1'},
            'training_dataset_version': 'real_event_join_v1',
            'dataset_snapshot_id': 'real_event_join_v1:2026-04-24T00:00:00+00:00',
            'requested_dataset_snapshot_id': 'requested-snapshot-v1',
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
        self.assertEqual(metadata['runout_method_counts'], {})
        self.assertEqual(
            metadata['label_snapshot_id'],
            'real_event_join_v1:2026-04-24T00:00:00+00:00',
        )
        self.assertEqual(
            metadata['dataset_snapshot_id'],
            'real_event_join_v1:2026-04-24T00:00:00+00:00',
        )
        self.assertEqual(metadata['requested_dataset_snapshot_id'], 'requested-snapshot-v1')
        self.assertEqual(metadata['calibration_profile_version'], 'calib-shadow-v1')
        self.assertEqual(metadata['source_composition']['weather_source'], 'open_meteo_forecast_downscaled_v1')
        self.assertEqual(metadata['region_coverage']['region_key'], 'colorado_rockies')
        self.assertEqual(metadata['source_health']['summary_version'], 'source_health_v1')
        self.assertEqual(metadata['decision_provenance']['threshold_profile_origin'], 'heuristic_seeded')
        self.assertEqual(metadata['governance_scope']['external_interoperability'], 'not_implemented')

    @patch('backend.daily_inference.promote_forecast_run')
    @patch('backend.daily_inference.attach_compatibility_forecast_grid')
    @patch('backend.daily_inference.rest_get', return_value=[])
    @patch(
        'backend.daily_inference.publish_forecast_run',
        return_value={
            'forecast_run_id': 'run-compat-fail',
            'manifest_storage_ref': 'forecast-products/avalanche/japanese_alps/run-compat-fail/manifest.json',
            'runout_storage_ref': 'forecast-products/avalanche/japanese_alps/run-compat-fail/runouts.json.gz',
            'hours': [],
        },
    )
    @patch('backend.daily_inference._upsert_shap_cache')
    @patch('backend.daily_inference.rest_insert')
    @patch('backend.daily_inference.rest_upsert')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_emits_compatibility_write_failed_event(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
        rest_upsert_mock,
        rest_insert_mock,
        upsert_shap_cache_mock,
        _publish_forecast_run_mock,
        rest_get_mock,
        attach_compatibility_forecast_grid_mock,
        promote_forecast_run_mock,
    ) -> None:
        region = SimpleNamespace(
            key='japanese_alps',
            name='Japanese Alps',
            bbox=(36.0, 137.0, 37.0, 138.0),
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
        rows = [{
            'row': 0,
            'col': 0,
            'status': 'ready',
            'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
            'terrain_inputs': {'slope': 0.5},
            'shap_context': {'top_features': []},
        }]

        payload = upsert_forecast_grid(
            region,
            bundle,
            pd.Timestamp('2026-04-25T00:00:00Z'),
            rows=rows,
            horizon_hours=72,
            grid_size=5,
        )

        self.assertEqual(payload['model_metadata']['compatibility_write_status'], 'failed')
        self.assertEqual(payload['model_metadata']['shap_cache_write_status'], 'not_attempted')
        attach_compatibility_forecast_grid_mock.assert_not_called()
        upsert_shap_cache_mock.assert_not_called()
        promote_forecast_run_mock.assert_called_once_with(forecast_run_id='run-compat-fail')
        stage_names = [
            call.args[1][0]['stage']
            for call in rest_insert_mock.call_args_list
            if 'stage' in call.args[1][0]
        ]
        self.assertIn('compatibility_write_started', stage_names)
        self.assertIn('compatibility_write_failed', stage_names)
        failed_event = next(
            call.args[1][0]
            for call in rest_insert_mock.call_args_list
            if call.args[1][0]['stage'] == 'compatibility_write_failed'
        )
        self.assertEqual(failed_event['detail']['error_class'], 'RuntimeError')
        self.assertIn('missing after upsert', failed_event['detail']['error_message'])
        rest_upsert_mock.assert_called_once()
        rest_get_mock.assert_called_once()

    @patch('backend.daily_inference.promote_forecast_run', side_effect=RuntimeError('promote exploded'))
    @patch(
        'backend.daily_inference.publish_forecast_run',
        return_value={
            'forecast_run_id': 'run-promote-fail',
            'manifest_storage_ref': 'forecast-products/avalanche/japanese_alps/run-promote-fail/manifest.json',
            'runout_storage_ref': 'forecast-products/avalanche/japanese_alps/run-promote-fail/runouts.json.gz',
            'hours': [],
        },
    )
    @patch('backend.daily_inference.rest_insert')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.build_runout_polygons', return_value=[])
    @patch('backend.daily_inference._fetch_region_sar_evidence', return_value={'mask_asset_refs': [], 'sar_event_geometries': []})
    def test_upsert_forecast_grid_emits_promote_failed_event(
        self,
        _fetch_sar_evidence_mock,
        _build_runout_mock,
        _has_creds_mock,
        rest_insert_mock,
        _publish_forecast_run_mock,
        _promote_forecast_run_mock,
    ) -> None:
        region = SimpleNamespace(
            key='japanese_alps',
            name='Japanese Alps',
            bbox=(36.0, 137.0, 37.0, 138.0),
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
        rows = [{
            'row': 0,
            'col': 0,
            'status': 'ready',
            'weather_inputs': {'snowfall_24h_cm': 12.0, 'windspeed_10m': 8.0, 'downscaled_temperature_c': -6.0, 'precipitation_24h_mm': 5.0},
            'terrain_inputs': {'slope': 0.5},
            'shap_values': {},
            'shap_context': {'top_features': []},
        }]
        proof_options = ProofModeOptions(
            enabled=True,
            profile='proof72',
            skip_tree_shap=True,
            skip_shap_cache=True,
            skip_runout_generation=True,
            skip_compatibility_write=True,
            emit_stage_metrics=False,
        )

        with self.assertRaisesRegex(RuntimeError, 'promote exploded'):
            upsert_forecast_grid(
                region,
                bundle,
                pd.Timestamp('2026-04-25T00:00:00Z'),
                rows=rows,
                horizon_hours=72,
                grid_size=5,
                proof_options=proof_options,
            )

        stage_names = [
            call.args[1][0]['stage']
            for call in rest_insert_mock.call_args_list
            if 'stage' in call.args[1][0]
        ]
        self.assertIn('promote_started', stage_names)
        self.assertIn('promote_failed', stage_names)
        failed_event = next(
            call.args[1][0]
            for call in rest_insert_mock.call_args_list
            if 'stage' in call.args[1][0] and call.args[1][0]['stage'] == 'promote_failed'
        )
        self.assertEqual(failed_event['detail']['error_class'], 'RuntimeError')
        self.assertEqual(failed_event['detail']['error_message'], 'promote exploded')

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
                'probability_risk_score': 4,
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

    @patch('backend.daily_inference.patch_latest_model_status_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'davos', 'region_name': 'Davos', 'forecast_date': '2026-04-25', 'horizon_hours': 72, 'grid_geojson': []})
    @patch('backend.daily_inference.build_hourly_grids', return_value=([], None))
    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='davos', name='Davos')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_skips_model_status_publish_in_dry_run(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        _build_hourly_grids_mock,
        upsert_forecast_grid_mock,
        _dump_json_mock,
        _has_creds_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        exit_code = main(['--dry-run'])

        self.assertEqual(exit_code, 0)
        self.assertTrue(upsert_forecast_grid_mock.call_args.kwargs['dry_run'])
        patch_latest_model_status_row_mock.assert_not_called()

    @patch('backend.daily_inference.patch_latest_model_status_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'davos', 'region_name': 'Davos', 'forecast_date': '2026-04-25', 'horizon_hours': 72, 'grid_geojson': []})
    @patch('backend.daily_inference.build_hourly_grids', return_value=([], None))
    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='davos', name='Davos')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_honors_explicit_artifact_dir(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        _build_hourly_grids_mock,
        _upsert_forecast_grid_mock,
        _dump_json_mock,
        _has_creds_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        artifact_dir = Path('/tmp/fake-artifact-dir')
        resolve_artifact_dir_mock.return_value = artifact_dir

        exit_code = main(['--dry-run', '--artifact-dir', str(artifact_dir)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(resolve_artifact_dir_mock.call_args.args[1], artifact_dir)
        self.assertTrue(resolve_artifact_dir_mock.call_args.kwargs['require_model'])
        patch_latest_model_status_row_mock.assert_not_called()

    @patch('backend.daily_inference.patch_latest_model_status_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'davos', 'region_name': 'Davos', 'forecast_date': '2026-04-25', 'horizon_hours': 2, 'grid_geojson': [], 'status': 'ready'})
    @patch('backend.daily_inference.build_hourly_grids', return_value=([[], []], None))
    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='davos', name='Davos')])
    @patch('backend.daily_inference.load_joblib', return_value={
        'created_at': '2026-04-25T00:00:00+00:00',
        'surrogate_model_version': 'rf_surrogate_v1',
        'metrics': {'pss_reported': 0.51, 'pss_gate_passed': True},
        'lstm_head_meta': {
            'enabled': True,
            'promotion_gate_passed': False,
            'dynamic_model_type': 'mts_lstm_v1',
            'dynamic_model_version': 'mts-lstm-shadow-1',
        },
        'dynamic_model_type': 'mts_lstm_v1',
        'dynamic_model_version': 'mts-lstm-shadow-1',
    })
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_publishes_model_status_truth(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        _build_hourly_grids_mock,
        _upsert_forecast_grid_mock,
        _dump_json_mock,
        _has_creds_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        exit_code = main([])

        self.assertEqual(exit_code, 0)
        payload = patch_latest_model_status_row_mock.call_args.args[0]
        self.assertEqual(payload['pss_reported'], 0.51)
        self.assertTrue(payload['pss_gate_passed'])
        self.assertFalse(payload['promotion_gate_passed'])
        self.assertTrue(payload['shadow_mode_active'])
        self.assertEqual(payload['capability_summary'], 'batch-only forecast_grids')
        self.assertEqual(payload['inference_backend'], 'batch_async')
        self.assertEqual(payload['capabilities']['serving_mode'], 'batch_only')
        self.assertEqual(payload['capabilities']['serving_summary'], 'batch-only forecast_grids')
        self.assertEqual(payload['active_model_type'], 'surrogate_rf_v1')
        self.assertEqual(payload['dynamic_model_candidate']['dynamic_model_version'], 'mts-lstm-shadow-1')
        self.assertEqual(payload['dynamic_model_candidate']['blocked_gate'], 'shadow_quality_gate')
        self.assertIn('autonomous_evidence_summary', payload)
        self.assertEqual(payload['drift_mode_state'], 'blocked_by_gate')
        self.assertIn('latest_benchmark_summary', payload)
        self.assertIn('stability_summary', payload)

    @patch('backend.daily_inference.patch_latest_model_status_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=False)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'japanese_alps', 'region_name': 'Japanese Alps', 'forecast_date': '2026-04-25', 'horizon_hours': 72, 'grid_geojson': []})
    @patch('backend.daily_inference.build_hourly_grids', return_value=([], None))
    @patch(
        'backend.daily_inference.load_regions',
        return_value=[
            SimpleNamespace(key='japanese_alps', name='Japanese Alps'),
            SimpleNamespace(key='cascades_wa', name='Cascades (WA)'),
        ],
    )
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_filters_regions_by_region_key(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        build_hourly_grids_mock,
        _upsert_forecast_grid_mock,
        _dump_json_mock,
        _has_creds_mock,
        _patch_latest_model_status_row_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        exit_code = main(['--dry-run', '--region-key', 'japanese_alps'])

        self.assertEqual(exit_code, 0)
        self.assertEqual(build_hourly_grids_mock.call_count, 1)
        self.assertEqual(build_hourly_grids_mock.call_args.args[0].key, 'japanese_alps')

    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='cascades_wa', name='Cascades (WA)')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_fails_fast_for_unknown_region_key(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        with self.assertRaisesRegex(RuntimeError, 'Unknown region_key\\(s\\): japanese_alps'):
            main(['--dry-run', '--region-key', 'japanese_alps'])

    @patch('backend.daily_inference.patch_latest_model_status_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=False)
    @patch('backend.daily_inference.dump_json')
    @patch('backend.daily_inference.upsert_forecast_grid', return_value={'region_key': 'japanese_alps', 'region_name': 'Japanese Alps', 'forecast_date': '2026-04-25', 'horizon_hours': 72, 'grid_geojson': [], 'model_metadata': {'lifeboat_mode': True, 'lifeboat_profile': 'proof72'}})
    @patch('backend.daily_inference.build_hourly_grids', return_value=([[]] * 72, None))
    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='japanese_alps', name='Japanese Alps')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_lifeboat_mode_applies_proof72_defaults_and_writes_stage_metrics(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
        build_hourly_grids_mock,
        upsert_forecast_grid_mock,
        dump_json_mock,
        _has_creds_mock,
        _patch_latest_model_status_row_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        exit_code = main(['--dry-run', '--lifeboat-mode', '--region-key', 'japanese_alps'])

        self.assertEqual(exit_code, 0)
        self.assertEqual(build_hourly_grids_mock.call_args.kwargs['grid_size'], 5)
        self.assertEqual(build_hourly_grids_mock.call_args.kwargs['horizon_hours'], 72)
        proof_options = build_hourly_grids_mock.call_args.kwargs['proof_options']
        self.assertTrue(proof_options.enabled)
        self.assertEqual(proof_options.profile, 'proof72')
        self.assertTrue(proof_options.skip_tree_shap)
        self.assertTrue(proof_options.skip_shap_cache)
        self.assertTrue(proof_options.skip_runout_generation)
        self.assertTrue(proof_options.skip_compatibility_write)
        self.assertTrue(proof_options.emit_stage_metrics)
        dumped_paths = [call.args[0].name for call in dump_json_mock.call_args_list]
        self.assertIn('inference_stage_metrics.json', dumped_paths)
        self.assertIn('inference_manifest.json', dumped_paths)
        self.assertTrue(upsert_forecast_grid_mock.call_args.kwargs['proof_options'].enabled)

    @patch('backend.daily_inference.load_regions', return_value=[SimpleNamespace(key='japanese_alps', name='Japanese Alps')])
    @patch('backend.daily_inference.load_joblib', return_value={'created_at': '2026-04-25T00:00:00+00:00'})
    @patch('backend.daily_inference.resolve_artifact_dir')
    def test_main_lifeboat_mode_requires_region_key(
        self,
        resolve_artifact_dir_mock,
        _load_joblib_mock,
        _load_regions_mock,
    ) -> None:
        resolve_artifact_dir_mock.return_value = Path('/tmp/fake-artifact-dir')

        with self.assertRaisesRegex(RuntimeError, 'lifeboat_mode requires at least one --region-key'):
            main(['--dry-run', '--lifeboat-mode'])

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
        self.assertTrue(cell['apt_eligible'])
        self.assertEqual(cell['apt_profile'], 'apt_30_50_v1')
        self.assertIsNone(cell['apt_mask_reason'])
        self.assertEqual(cell['risk_score'], cell['probability_risk_score'])
        self.assertGreaterEqual(cell['terrain_fused_risk_score'], cell['risk_score'])
        self.assertEqual(cell['surrogate_model_version'], 'rf_surrogate_v1')
        self.assertEqual(cell['dominant_driver_feature'], 'snowfall_24h')
        self.assertEqual(cell['shap_values']['snowfall_24h'], 0.42)
        self.assertEqual(cell['shap_context']['top_features'][0]['feature'], 'snowfall_24h')
        self.assertEqual(cell['explainability_mode'], 'tree_shap')
        self.assertIsNone(cell['explainability_reason'])
        self.assertEqual(cell['inference_backend'], 'github_actions_surrogate_rf')
        self.assertEqual(
            build_feature_row_mock.call_args.kwargs['snowpack_proxy_override'].method,
            'seasonal_cumulative_v1',
        )

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
    def test_build_cells_masks_non_apt_ready_cells(
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
            'elevation_m': 1450.0,
            'slope_angle_deg': 24.0,
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
        self.assertFalse(cell['apt_eligible'])
        self.assertEqual(cell['apt_mask_reason'], 'slope_outside_30_to_50_deg')
        self.assertEqual(cell['risk_score'], 0)
        self.assertGreaterEqual(cell['terrain_fused_risk_score'], 1)
        self.assertEqual(cell['probability_risk_score'], 4)
        self.assertFalse(cell['runout_seed'])

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
    def test_build_cells_proof_mode_skips_tree_shap_but_preserves_payload_contract(
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
            proof_options=ProofModeOptions(enabled=True, profile='proof72', skip_tree_shap=True),
        )

        self.assertEqual(len(rows), 1)
        cell = rows[0]
        self.assertEqual(cell['status'], 'ready')
        self.assertEqual(cell['shap_values'], {})
        self.assertEqual(cell['shap_context']['top_features'], [])
        self.assertIsNone(cell['dominant_driver_feature'])
        self.assertEqual(cell['explainability_mode'], 'heuristic_fallback')
        self.assertEqual(cell['explainability_reason'], 'proof_mode_skip_tree_shap')
        compute_tree_shap_mock.assert_not_called()

    @patch('backend.daily_inference._fetch_latest_sar_summary', return_value={})
    @patch('backend.daily_inference.fetch_historical_weather_window', return_value={'samples': []})
    @patch('backend.daily_inference.select_hourly_weather_sample', return_value={})
    @patch('backend.daily_inference.fetch_forecast_weather_profile', return_value={'samples': []})
    @patch('backend.daily_inference.predict_production_probability', return_value=(0.67, None))
    @patch('backend.daily_inference.collect_tree_probabilities', return_value=np.asarray([[0.4, 0.8]], dtype=np.float32))
    @patch('backend.daily_inference.compute_tree_shap')
    @patch('backend.daily_inference.build_tree_shap_explainer', side_effect=TreeShapUnavailableError('TreeSHAP dependency unavailable'))
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.extract_cell_terrain')
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_marks_tree_shap_dependency_fallback(
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
            'raw_inputs': {},
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

        rows = build_cells(
            region=SimpleNamespace(key='davos', center=(46.8, 9.8)),
            bundle=bundle,
            grid_size=1,
            forecast_date=pd.Timestamp('2026-04-25T00:00:00Z'),
        )

        self.assertEqual(rows[0]['explainability_mode'], 'heuristic_fallback')
        self.assertEqual(rows[0]['explainability_reason'], 'shap_dependency_unavailable')
        self.assertEqual(rows[0]['shap_values'], {})
        compute_tree_shap_mock.assert_not_called()

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
    @patch('backend.daily_inference.predict_production_probability', return_value=(0.9, {'enabled': True}))
    @patch('backend.daily_inference.collect_tree_probabilities', return_value=np.asarray([[0.4, 0.8]], dtype=np.float32))
    @patch('backend.daily_inference.compute_tree_shap', return_value=({'snowfall_24h': 0.42}, [{'feature': 'snowfall_24h', 'shap_value': 0.42, 'feature_value': 0.7, 'rank': 1}]))
    @patch('backend.daily_inference.build_tree_shap_explainer', return_value=object())
    @patch('backend.daily_inference.fetch_batched_cell_snowpack_proxies_partial')
    @patch('backend.daily_inference.build_inference_branches', return_value=SimpleNamespace(hourly=np.zeros((24, 6)), daily=np.zeros((7, 6)), static=np.zeros((6,))))
    @patch('backend.daily_inference.extract_cell_terrain')
    @patch('backend.daily_inference.build_real_feature_row')
    @patch('backend.daily_inference.build_region_grid')
    def test_build_cells_skips_shadow_sequence_inference_when_dynamic_model_is_not_active(
        self,
        build_grid_mock,
        build_feature_row_mock,
        extract_terrain_mock,
        build_inference_branches_mock,
        fetch_snowpack_proxies_mock,
        _build_explainer_mock,
        _compute_tree_shap_mock,
        _collect_tree_probs_mock,
        predict_production_probability_mock,
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
                metadata={
                    'hourly_steps': 24,
                    'daily_steps': 7,
                    'dynamic_model_version': 'mts-lstm-42',
                    'production_eligibility_gate_passed': False,
                },
            ),
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
        self.assertAlmostEqual(cell['probability'], 0.67, places=2)
        self.assertAlmostEqual(cell['rf_probability'], 0.67, places=2)
        self.assertEqual(cell['dynamic_model_type'], 'mts_lstm_v1')
        self.assertEqual(cell['dynamic_model_version'], 'mts-lstm-42')
        self.assertEqual(cell['uncertainty_method'], 'tree_variance_gaussian_shadow')
        self.assertEqual(cell['inference_backend'], 'github_actions_shadow')
        self.assertEqual(cell['lstm_context']['fallback_reason'], 'shadow_inference_skipped')
        build_inference_branches_mock.assert_not_called()
        predict_production_probability_mock.assert_not_called()

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
        self.assertFalse(cell['apt_eligible'])
        self.assertEqual(cell['apt_profile'], 'apt_30_50_v1')
        self.assertEqual(cell['apt_mask_reason'], 'slope_outside_30_to_50_deg')
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


class PublicEligibilityAndClassifierTests(unittest.TestCase):
    def test_public_eligibility_masks_warm_low_elevation_no_snow_support(self) -> None:
        cell = apply_public_eligibility_metric({
            'status': 'ready',
            'risk_score': 4,
            'probability_risk_score': 4,
            'apt_eligible': True,
            'apt_mask_reason': None,
            'weather_inputs': {
                'downscaled_temperature_c': 4.0,
                'snowfall_24h_cm': 0.0,
                'precipitation_24h_mm': 2.0,
                'snow_depth_cm': 0.0,
                'freezing_level_height_m': 1800.0,
            },
            'terrain_inputs': {
                'elevation_m': 900.0,
                'slope_angle_deg': 38.0,
            },
            'snowpack_proxy': {
                'method': 'proxy_v1',
                'estimated_shear_strength': None,
                'snow_settlement_index': None,
            },
        })

        self.assertFalse(cell['public_eligible'])
        self.assertFalse(cell['snow_elevation_eligible'])
        self.assertEqual(cell['snow_elevation_mask_reason'], 'warm_low_elevation_no_snow_support')
        self.assertEqual(cell['public_mask_reasons'], ['warm_low_elevation_no_snow_support'])
        self.assertEqual(cell['risk_score'], 0)
        self.assertFalse(cell['runout_seed'])

    def test_public_eligibility_keeps_ambiguous_proxy_only_cell_public(self) -> None:
        cell = apply_public_eligibility_metric({
            'status': 'ready',
            'risk_score': 3,
            'probability_risk_score': 3,
            'apt_eligible': True,
            'apt_mask_reason': None,
            'weather_inputs': {
                'downscaled_temperature_c': 1.0,
                'snowfall_24h_cm': 0.0,
                'precipitation_24h_mm': 0.0,
                'snow_depth_cm': None,
                'freezing_level_height_m': 2100.0,
            },
            'terrain_inputs': {
                'elevation_m': 1700.0,
                'slope_angle_deg': 38.0,
            },
            'snowpack_proxy': {
                'method': 'proxy_v1',
                'estimated_shear_strength': None,
                'snow_settlement_index': None,
            },
        })

        self.assertTrue(cell['public_eligible'])
        self.assertTrue(cell['snow_elevation_eligible'])
        self.assertEqual(cell['snow_relevance_basis'], ['proxy_ambiguous_keep_public'])
        self.assertAlmostEqual(cell['snow_relevance_score'], 0.25)
        self.assertEqual(cell['risk_score'], 3)

    def test_problem_classifier_requires_snow_evidence_for_wet_snow(self) -> None:
        problem = classify_avalanche_problem(
            weather_inputs={
                'downscaled_temperature_c': 3.5,
                'snowfall_24h_cm': 0.0,
                'precipitation_24h_mm': 8.0,
                'snow_depth_cm': 0.0,
                'wind_loading': 0.1,
            },
            terrain_inputs={'aspect_loading': 0.2, 'aspect_deg': 180.0},
            snowpack_proxy={'method': 'proxy_v1'},
            forecast_time=datetime(2026, 4, 25, 13, 0, 0),
            timezone_name='UTC',
        )

        self.assertEqual(problem['problem_slug'], 'no_distinct_avalanche_problem')

    def test_problem_classifier_prioritizes_wind_slab_over_new_snow_with_loading_signals(self) -> None:
        problem = classify_avalanche_problem(
            weather_inputs={
                'downscaled_temperature_c': -6.0,
                'snowfall_24h_cm': 12.0,
                'precipitation_24h_mm': 12.0,
                'snow_depth_cm': 18.0,
                'wind_loading': 0.8,
            },
            terrain_inputs={'aspect_loading': 0.7, 'aspect_deg': 315.0},
            snowpack_proxy={
                'method': 'seasonal_cumulative_v1',
                'estimated_shear_strength': 6.0,
                'snow_settlement_index': 0.5,
            },
            forecast_time=datetime(2026, 4, 25, 6, 0, 0),
            timezone_name='UTC',
        )

        self.assertEqual(problem['problem_slug'], 'wind_slab')
        self.assertEqual(problem['problem_type'], 'Wind Slab')

    def test_problem_classifier_falls_back_to_utc_for_invalid_timezone(self) -> None:
        problem = classify_avalanche_problem(
            weather_inputs={
                'downscaled_temperature_c': -5.0,
                'snowfall_24h_cm': 8.0,
                'precipitation_24h_mm': 8.0,
                'snow_depth_cm': 12.0,
                'wind_loading': 0.2,
            },
            terrain_inputs={'aspect_loading': 0.2, 'aspect_deg': 90.0},
            snowpack_proxy={'method': 'proxy_v1'},
            forecast_time=datetime(2026, 4, 25, 6, 0, 0),
            timezone_name='Invalid/Timezone',
        )

        self.assertIn('timezone_fallback_to_utc', problem['problem_evidence'])


if __name__ == '__main__':
    unittest.main()
