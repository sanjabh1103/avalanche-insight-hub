from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.data.mts_lstm_loader import (
    MTSAvalancheDataset,
    WeightedRandomSampler,
    build_mts_lstm_dataloaders,
    build_mts_lstm_weighted_sampler,
    torch,
)


def _sample(hour: int) -> dict[str, float | str]:
    return {
        'timestamp': f'2026-04-24T{hour:02d}:00:00+00:00',
        'temperature_2m': -8.0 + hour * 0.1,
        'snowfall': 1.5,
        'precipitation': 1.2,
        'windspeed_10m': 12.0 + hour * 0.2,
        'winddirection_10m': 240.0,
        'freezing_level_height': 2100.0,
        'snow_depth': 0.8,
        'temperature_925hPa': -9.0,
        'temperature_850hPa': -11.0,
        'temperature_700hPa': -15.0,
        'geopotential_height_925hPa': 900.0,
        'geopotential_height_850hPa': 1500.0,
        'geopotential_height_700hPa': 3000.0,
    }


def _frame_row(*, timestamp: str, label: int, training_weight: float) -> dict[str, object]:
    return {
        'timestamp': pd.Timestamp(timestamp),
        'region_key': 'davos',
        'lat': 46.8,
        'lng': 9.8,
        'label': label,
        'training_weight': training_weight,
        'slope': 37.0 / 60.0,
        'elevation': 3200.0 / 5000.0,
        'aspect_loading': 0.7,
        'terrain_roughness': 0.2,
        'curvature_proxy': 0.1,
        'northness': 0.3,
        'eastness': 0.6,
        'ram_hardness': 0.5,
        'shear_strength': 0.5,
        'settlement_rate': 0.4,
        'slope_angle_deg_raw': 37.0,
        'elevation_m_raw': 3200.0,
        'aspect_deg_raw': 210.0,
        'terrain_roughness_raw': 12.0,
        'curvature_proxy_raw': 4.0,
    }


@unittest.skipIf(torch is None, 'torch runtime unavailable')
class MTSAvalancheDatasetTests(unittest.TestCase):
    def test_dataset_sample_shapes_match_model_contract(self) -> None:
        dataset = MTSAvalancheDataset(
            hourly=np.zeros((1, 24, 6), dtype=np.float32),
            daily=np.zeros((1, 7, 6), dtype=np.float32),
            static=np.zeros((1, 10), dtype=np.float32),
            labels=np.asarray([1.0], dtype=np.float32),
            sample_weights=np.asarray([0.8], dtype=np.float32),
        )

        sample = dataset[0]

        self.assertEqual(tuple(sample['hourly'].shape), (24, 6))
        self.assertEqual(tuple(sample['daily'].shape), (7, 6))
        self.assertEqual(tuple(sample['static'].shape), (10,))

    def test_dataset_applies_normalization_stats(self) -> None:
        dataset = MTSAvalancheDataset(
            hourly=np.ones((1, 24, 6), dtype=np.float32) * 3.0,
            daily=np.ones((1, 7, 6), dtype=np.float32) * 5.0,
            static=np.ones((1, 10), dtype=np.float32) * 9.0,
            labels=np.asarray([1.0], dtype=np.float32),
            sample_weights=np.asarray([0.8], dtype=np.float32),
            hourly_mean=np.ones((1, 1, 6), dtype=np.float32),
            hourly_std=np.ones((1, 1, 6), dtype=np.float32) * 2.0,
            daily_mean=np.ones((1, 1, 6), dtype=np.float32),
            daily_std=np.ones((1, 1, 6), dtype=np.float32) * 2.0,
            static_mean=np.ones((1, 10), dtype=np.float32),
            static_std=np.ones((1, 10), dtype=np.float32) * 2.0,
        )

        sample = dataset[0]

        self.assertAlmostEqual(float(sample['hourly'][0, 0].item()), 1.0, places=6)
        self.assertAlmostEqual(float(sample['daily'][0, 0].item()), 2.0, places=6)
        self.assertAlmostEqual(float(sample['static'][0].item()), 4.0, places=6)

    def test_weighted_sampler_combines_governance_and_class_frequency(self) -> None:
        sampler = build_mts_lstm_weighted_sampler(
            labels=np.asarray([1, 0, 0], dtype=np.int64),
            sample_weights=np.asarray([0.5, 1.0, 0.5], dtype=np.float32),
        )

        self.assertIsNotNone(sampler)
        self.assertIsInstance(sampler, WeightedRandomSampler)
        self.assertAlmostEqual(float(sampler.weights[0]), 0.75, places=6)
        self.assertAlmostEqual(float(sampler.weights[1]), 0.75, places=6)
        self.assertAlmostEqual(float(sampler.weights[2]), 0.375, places=6)

    @patch('backend.common.sequence_features._cached_historical_window')
    def test_build_dataloaders_use_weighted_sampler_for_train_only(self, cached_window_mock) -> None:
        cached_window_mock.return_value = {'samples': [_sample(hour) for hour in range(24)]}
        train_df = pd.DataFrame([
            _frame_row(timestamp='2026-04-24T12:00:00Z', label=1, training_weight=0.9),
            _frame_row(timestamp='2026-04-25T12:00:00Z', label=0, training_weight=1.0),
        ])
        validation_df = pd.DataFrame([
            _frame_row(timestamp='2026-04-26T12:00:00Z', label=1, training_weight=0.8),
            _frame_row(timestamp='2026-04-27T12:00:00Z', label=0, training_weight=1.0),
        ])

        train_loader, validation_loader, stats = build_mts_lstm_dataloaders(
            train_df=train_df,
            validation_df=validation_df,
            region_centers={'davos': (46.8, 9.8)},
            dynamic_features=['snowfall_24h', 'precipitation_24h', 'wind_loading', 'wind_directional_loading', 'temp_gradient', 'freezing_level_proxy'],
            static_features=['slope', 'elevation', 'aspect_loading', 'terrain_roughness', 'curvature_proxy', 'northness', 'eastness', 'ram_hardness', 'shear_strength', 'settlement_rate'],
            hourly_steps=24,
            daily_steps=7,
            batch_size=32,
        )

        self.assertIsInstance(train_loader.sampler, WeightedRandomSampler)
        self.assertNotIsInstance(validation_loader.sampler, WeightedRandomSampler)
        self.assertEqual(tuple(stats.hourly_mean.shape), (1, 1, 6))
        batch = next(iter(train_loader))
        self.assertEqual(tuple(batch['hourly'].shape[1:]), (24, 6))
        self.assertEqual(tuple(batch['daily'].shape[1:]), (7, 6))
        self.assertEqual(tuple(batch['static'].shape[1:]), (10,))


if __name__ == '__main__':
    unittest.main()
