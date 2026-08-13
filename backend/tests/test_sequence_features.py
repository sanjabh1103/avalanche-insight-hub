from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.common.sequence_features import (
    DEFAULT_DAILY_STEPS,
    DEFAULT_HOURLY_STEPS,
    _aggregate_daily_samples,
    _pad_sequence,
    build_training_branch_arrays,
    sequence_matrix_from_samples,
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


class SequenceFeatureTests(unittest.TestCase):
    def test_sequence_matrix_shapes_and_bounds(self) -> None:
        hourly_samples = [_sample(hour) for hour in range(24)]
        daily_samples = [_sample(hour % 24) | {'timestamp': f'2026-04-{day:02d}T12:00:00+00:00'} for day, hour in zip(range(18, 25), range(7))]
        terrain = {
            'elevation_m': 3200.0,
            'slope_angle_deg': 37.0,
            'aspect_deg': 210.0,
            'terrain_roughness': 12.0,
            'curvature_proxy': 4.0,
            'northness': 0.3,
            'eastness': 0.6,
        }

        hourly_matrix, daily_matrix = sequence_matrix_from_samples(
            hourly_samples=hourly_samples,
            daily_samples=daily_samples,
            terrain=terrain,
        )

        self.assertEqual(hourly_matrix.shape, (DEFAULT_HOURLY_STEPS, 6))
        self.assertEqual(daily_matrix.shape, (DEFAULT_DAILY_STEPS, 6))
        self.assertTrue(np.all(hourly_matrix >= 0.0))
        self.assertTrue(np.all(hourly_matrix <= 1.0))

    def test_daily_aggregation_zero_pads_missing_history(self) -> None:
        samples = [
            _sample(4) | {'timestamp': '2026-04-24T04:00:00+00:00'},
            _sample(8) | {'timestamp': '2026-04-24T08:00:00+00:00'},
        ]

        aggregated = _aggregate_daily_samples(samples, length=3)

        self.assertEqual(len(aggregated), 3)
        self.assertEqual(aggregated[0]['timestamp'], '2026-04-22T12:00:00+00:00')
        self.assertEqual(aggregated[1]['timestamp'], '2026-04-23T12:00:00+00:00')
        self.assertEqual(aggregated[0]['temperature_2m'], 0.0)
        self.assertEqual(aggregated[0]['snowfall_24h'], 0.0)
        self.assertEqual(aggregated[1]['precipitation_24h'], 0.0)
        self.assertGreater(aggregated[2]['snowfall_24h'], 0.0)

    def test_hourly_padding_zero_pads_missing_history(self) -> None:
        padded = _pad_sequence([
            {
                'snowfall_24h': 0.4,
                'precipitation_24h': 0.6,
                'wind_loading': 0.7,
                'wind_directional_loading': 0.8,
                'temp_gradient': 0.9,
                'freezing_level_proxy': 0.3,
            },
        ], length=3)

        self.assertEqual(len(padded), 3)
        self.assertEqual(padded[0]['snowfall_24h'], 0.0)
        self.assertEqual(padded[1]['wind_loading'], 0.0)
        self.assertEqual(padded[2]['temp_gradient'], 0.9)

    @patch('backend.common.sequence_features._cached_historical_window')
    def test_build_training_branch_arrays_uses_region_center_weather(self, cached_window_mock) -> None:
        cached_window_mock.return_value = {'samples': [_sample(hour) for hour in range(24)]}
        frame = pd.DataFrame([
            {
                'timestamp': pd.Timestamp('2026-04-24T12:00:00Z'),
                'region_key': 'colorado_rockies',
                'lat': 39.5,
                'lng': -106.5,
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
            },
        ])

        branches = build_training_branch_arrays(
            frame,
            region_centers={'colorado_rockies': (39.5, -106.5)},
        )

        self.assertEqual(branches.hourly.shape, (1, DEFAULT_HOURLY_STEPS, 6))
        self.assertEqual(branches.daily.shape, (1, DEFAULT_DAILY_STEPS, 6))
        self.assertEqual(branches.static.shape[0], 1)
        cached_window_mock.assert_called_once()


if __name__ == '__main__':
    unittest.main()
