from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from backend.daily_inference import upsert_forecast_grid


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


if __name__ == '__main__':
    unittest.main()
