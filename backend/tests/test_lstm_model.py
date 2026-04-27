from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.common.sequence_features import SequenceBranches
from backend.data.mts_lstm_loader import MTSAvalancheDataset
from backend.lstm_model import (
    MTS_MIN_UNCERTAINTY_STD,
    assess_production_gates,
    build_dataset_snapshot_id,
    fit_lstm_head,
    predict_production_probability,
)
from backend.models.mts_lstm import BranchedMTSLSTM as ExtractedBranchedMTSLSTM


class _DummyHead:
    def __init__(self, *, promoted: bool, std: float, ensemble_std: float) -> None:
        self.model = object()
        self.metadata = {
            'promotion_gate_passed': promoted,
            'dynamic_model_version': 'mts-lstm-test',
            'seed': 17,
        }
        self._std = std
        self._ensemble_std = ensemble_std

    def predict_sequence(self, branches: SequenceBranches, *, mc_samples: int | None = None):
        return np.asarray([0.73], dtype=np.float32), np.asarray([self._std], dtype=np.float32)

    def predict_sequence_seeded_ensemble(self, branches: SequenceBranches, *, ensemble_samples: int, seed_base: int):
        return np.asarray([0.74], dtype=np.float32), np.asarray([self._ensemble_std], dtype=np.float32)


class PredictProductionProbabilityTests(unittest.TestCase):
    @patch('backend.lstm_model.BranchedMTSLSTM', None)
    @patch('backend.lstm_model.torch', None)
    def test_stub_head_metadata_preserves_seed(self) -> None:
        head = fit_lstm_head(
            train_df=pd.DataFrame(),
            test_df=pd.DataFrame(),
            rf_metrics={},
            seed=23,
            selected_features=[],
        )

        self.assertIsNotNone(head)
        self.assertEqual(head.metadata['seed'], 23)

    def test_lstm_model_reexports_extracted_model_class(self) -> None:
        from backend.lstm_model import BranchedMTSLSTM

        self.assertIs(BranchedMTSLSTM, ExtractedBranchedMTSLSTM)

    @patch('backend.lstm_model.load_regions')
    @patch('backend.lstm_model.build_mts_lstm_dataloaders')
    def test_fit_lstm_head_uses_loader_builder(self, build_loaders_mock, load_regions_mock) -> None:
        try:
            import torch
            from torch.utils.data import DataLoader
        except Exception:  # pragma: no cover - optional dependency
            self.skipTest('torch runtime unavailable')

        hourly = np.zeros((2, 24, 6), dtype=np.float32)
        daily = np.zeros((2, 7, 6), dtype=np.float32)
        static = np.zeros((2, 10), dtype=np.float32)
        labels = np.asarray([1.0, 0.0], dtype=np.float32)
        sample_weights = np.asarray([0.9, 1.0], dtype=np.float32)
        train_dataset = MTSAvalancheDataset(
            hourly=hourly,
            daily=daily,
            static=static,
            labels=labels,
            sample_weights=sample_weights,
            hourly_mean=np.zeros((1, 1, 6), dtype=np.float32),
            hourly_std=np.ones((1, 1, 6), dtype=np.float32),
            daily_mean=np.zeros((1, 1, 6), dtype=np.float32),
            daily_std=np.ones((1, 1, 6), dtype=np.float32),
            static_mean=np.zeros((1, 10), dtype=np.float32),
            static_std=np.ones((1, 10), dtype=np.float32),
        )
        validation_dataset = MTSAvalancheDataset(
            hourly=hourly.copy(),
            daily=daily.copy(),
            static=static.copy(),
            labels=labels.copy(),
            sample_weights=sample_weights.copy(),
            hourly_mean=np.zeros((1, 1, 6), dtype=np.float32),
            hourly_std=np.ones((1, 1, 6), dtype=np.float32),
            daily_mean=np.zeros((1, 1, 6), dtype=np.float32),
            daily_std=np.ones((1, 1, 6), dtype=np.float32),
            static_mean=np.zeros((1, 10), dtype=np.float32),
            static_std=np.ones((1, 10), dtype=np.float32),
        )
        build_loaders_mock.return_value = (
            DataLoader(train_dataset, batch_size=2, shuffle=False),
            DataLoader(validation_dataset, batch_size=2, shuffle=False),
            SimpleNamespace(
                hourly_mean=np.zeros((1, 1, 6), dtype=np.float32),
                hourly_std=np.ones((1, 1, 6), dtype=np.float32),
                daily_mean=np.zeros((1, 1, 6), dtype=np.float32),
                daily_std=np.ones((1, 1, 6), dtype=np.float32),
                static_mean=np.zeros((1, 10), dtype=np.float32),
                static_std=np.ones((1, 10), dtype=np.float32),
            ),
        )
        load_regions_mock.return_value = [SimpleNamespace(key='davos', center=(46.8, 9.8))]
        train_df = pd.DataFrame([{'label': 1, 'training_weight': 0.9}, {'label': 0, 'training_weight': 1.0}])
        test_df = pd.DataFrame([{'label': 1, 'training_weight': 0.9}, {'label': 0, 'training_weight': 1.0}])

        with patch('backend.lstm_model.MTS_LSTM_EPOCHS', 1), patch('backend.lstm_model.MTS_VALIDATE_EVERY', 1):
            head = fit_lstm_head(
                train_df=train_df,
                test_df=test_df,
                rf_metrics={'pss_holdout': 0.0, 'brier_score': 1.0},
                seed=13,
                selected_features=[
                    'snowfall_24h',
                    'precipitation_24h',
                    'wind_loading',
                    'wind_directional_loading',
                    'temp_gradient',
                    'freezing_level_proxy',
                ],
            )

        self.assertIsNotNone(head)
        build_loaders_mock.assert_called_once()

    def test_promoted_model_uses_seeded_uncertainty_fallback_when_mc_dropout_collapses(self) -> None:
        head = _DummyHead(promoted=True, std=0.0, ensemble_std=0.012)
        branches = SequenceBranches(
            hourly=np.zeros((24, 6), dtype=np.float32),
            daily=np.zeros((7, 6), dtype=np.float32),
            static=np.zeros((10,), dtype=np.float32),
        )

        active_probability, context = predict_production_probability(0.41, head, branches)

        self.assertAlmostEqual(active_probability, 0.73, places=2)
        self.assertIsNotNone(context)
        self.assertEqual(context['uncertainty_method'], 'seeded_dropout_ensemble_v1')
        self.assertGreaterEqual(float(context['uncertainty_std']), 0.012)
        self.assertIn('confidence_lower', context)
        self.assertIn('confidence_upper', context)

    def test_promoted_model_applies_minimum_uncertainty_floor_when_ensemble_is_also_flat(self) -> None:
        head = _DummyHead(promoted=True, std=0.0, ensemble_std=0.0)
        branches = SequenceBranches(
            hourly=np.zeros((24, 6), dtype=np.float32),
            daily=np.zeros((7, 6), dtype=np.float32),
            static=np.zeros((10,), dtype=np.float32),
        )

        _, context = predict_production_probability(0.41, head, branches)

        self.assertIsNotNone(context)
        self.assertEqual(context['uncertainty_method'], 'seeded_dropout_ensemble_v1')
        self.assertAlmostEqual(float(context['uncertainty_std']), MTS_MIN_UNCERTAINTY_STD, places=6)

    def test_non_promoted_model_keeps_rf_probability_even_if_dynamic_probability_exists(self) -> None:
        head = _DummyHead(promoted=False, std=0.01, ensemble_std=0.02)
        head.metadata.update({
            'shadow_quality_gate_passed': True,
            'sar_release_gate_passed': True,
            'production_eligibility_gate_passed': False,
        })
        branches = SequenceBranches(
            hourly=np.zeros((24, 6), dtype=np.float32),
            daily=np.zeros((7, 6), dtype=np.float32),
            static=np.zeros((10,), dtype=np.float32),
        )

        active_probability, context = predict_production_probability(0.41, head, branches)

        self.assertAlmostEqual(active_probability, 0.41, places=2)
        self.assertIsNotNone(context)
        self.assertTrue(context['shadow_mode_active'])
        self.assertFalse(context['promotion_gate_passed'])


class ProductionGateTests(unittest.TestCase):
    def test_assess_production_gates_requires_model_quality_release_and_volume(self) -> None:
        summary = assess_production_gates(
            lstm_pss=0.52,
            lstm_brier=0.18,
            rf_pss=0.48,
            rf_brier=0.19,
            sar_release_gate_passed=True,
            sar_unet_promoted_count=50,
            sar_unet_promoted_region_count=3,
            sar_unet_promoted_scene_date_count=14,
        )

        self.assertTrue(summary['shadow_quality_gate_passed'])
        self.assertTrue(summary['sar_release_gate_passed'])
        self.assertTrue(summary['sar_volume_gate_passed'])
        self.assertTrue(summary['production_eligibility_gate_passed'])
        self.assertTrue(summary['promotion_gate_passed'])

    def test_assess_production_gates_rejects_insufficient_promoted_sar_volume(self) -> None:
        summary = assess_production_gates(
            lstm_pss=0.52,
            lstm_brier=0.18,
            rf_pss=0.48,
            rf_brier=0.19,
            sar_release_gate_passed=True,
            sar_unet_promoted_count=12,
            sar_unet_promoted_region_count=2,
            sar_unet_promoted_scene_date_count=6,
        )

        self.assertTrue(summary['shadow_quality_gate_passed'])
        self.assertFalse(summary['sar_volume_gate_passed'])
        self.assertFalse(summary['production_eligibility_gate_passed'])

    def test_build_dataset_snapshot_id_uses_version_and_latest_timestamp(self) -> None:
        snapshot_id = build_dataset_snapshot_id({
            'training_dataset_version': 'real_event_join_v1',
            'newest_timestamp': '2026-04-25T00:00:00+00:00',
        })

        self.assertEqual(snapshot_id, 'real_event_join_v1:2026-04-25T00:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
