from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.common.cold_start_config import (
    ColdStartConfig,
    ForecastMode,
    get_cold_start_config,
    is_cold_start_active,
    resolve_forecast_mode,
    validate_cold_start_eligible,
)
from backend.common.features import (
    FEATURE_COLUMNS,
    generate_cold_start_synthetic_frame,
    generate_training_frame,
)
from backend.common.regions import Region, load_regions
from backend.models.surrogate_rf import fit_cold_start_bundle, fit_surrogate_bundle


def _make_small_frame(n_samples: int = 80, positive_ratio: float = 0.2, seed: int = 42) -> pd.DataFrame:
    """Generate a small synthetic frame for cold-start testing."""
    rng = np.random.default_rng(seed)
    n_positive = max(1, int(n_samples * positive_ratio))
    n_negative = n_samples - n_positive
    rows = []
    timestamps = pd.date_range('2023-11-01', periods=n_samples, freq='12h', tz='UTC')
    for i in range(n_samples):
        label = 1 if i < n_positive else 0
        row = {
            'timestamp': timestamps[i],
            'region_key': 'test_region',
            'region_name': 'Test Region',
            'lat': float(rng.uniform(34.0, 36.0)),
            'lng': float(rng.uniform(74.0, 78.0)),
            'label': label,
        }
        for col in FEATURE_COLUMNS:
            row[col] = float(rng.uniform(0.0, 1.0))
        rows.append(row)
    return pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)


def _make_multi_winter_frame(n_winters: int = 3, samples_per_winter: int = 40, seed: int = 42) -> pd.DataFrame:
    """Generate a frame spanning multiple winter seasons."""
    rng = np.random.default_rng(seed)
    rows = []
    for winter_idx in range(n_winters):
        year = 2023 + winter_idx
        timestamps = pd.date_range(f'{year}-11-01', periods=samples_per_winter, freq='12h', tz='UTC')
        for i in range(samples_per_winter):
            label = 1 if i < max(2, samples_per_winter // 5) else 0
            row = {
                'timestamp': timestamps[i],
                'region_key': 'test_region',
                'region_name': 'Test Region',
                'lat': float(rng.uniform(34.0, 36.0)),
                'lng': float(rng.uniform(74.0, 78.0)),
                'label': label,
            }
            for col in FEATURE_COLUMNS:
                row[col] = float(rng.uniform(0.0, 1.0))
            rows.append(row)
    return pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)


class TestColdStartConfig(unittest.TestCase):

    def test_default_config_values(self):
        config = ColdStartConfig()
        self.assertEqual(config.target_feature_count, 10)
        self.assertAlmostEqual(config.pss_floor, 0.30)
        self.assertAlmostEqual(config.brier_ceiling, 0.20)
        self.assertEqual(config.min_winters_required, 3)
        self.assertEqual(config.min_positive_events, 10)
        self.assertEqual(config.synthetic_augmentation_multiplier, 3)
        self.assertEqual(config.rf_trees, 200)
        self.assertEqual(config.min_samples_leaf, 3)
        self.assertEqual(config.class_weight, {0: 1, 1: 6})

    def test_env_var_overrides(self):
        with patch.dict(os.environ, {
            'COLD_START_FEATURE_COUNT': '7',
            'COLD_START_PSS_FLOOR': '0.25',
            'COLD_START_BRIER_CEILING': '0.18',
            'COLD_START_RF_TREES': '150',
            'COLD_START_MIN_SAMPLES_LEAF': '5',
        }):
            config = get_cold_start_config()
            self.assertEqual(config.target_feature_count, 7)
            self.assertAlmostEqual(config.pss_floor, 0.25)
            self.assertAlmostEqual(config.brier_ceiling, 0.18)
            self.assertEqual(config.rf_trees, 150)
            self.assertEqual(config.min_samples_leaf, 5)

    def test_resolve_forecast_mode_default(self):
        with patch.dict(os.environ, {}, clear=True):
            mode = resolve_forecast_mode()
            self.assertEqual(mode, ForecastMode.FULL)

    def test_resolve_forecast_mode_cold_start(self):
        with patch.dict(os.environ, {'FORECAST_MODE': 'cold_start'}):
            mode = resolve_forecast_mode()
            self.assertEqual(mode, ForecastMode.COLD_START)

    def test_resolve_forecast_mode_invalid_falls_back(self):
        with patch.dict(os.environ, {'FORECAST_MODE': 'invalid_mode'}):
            mode = resolve_forecast_mode()
            self.assertEqual(mode, ForecastMode.FULL)

    def test_is_cold_start_active(self):
        with patch.dict(os.environ, {'FORECAST_MODE': 'cold_start'}):
            self.assertTrue(is_cold_start_active())
        with patch.dict(os.environ, {'FORECAST_MODE': 'full'}):
            self.assertFalse(is_cold_start_active())


class TestColdStartValidation(unittest.TestCase):

    def test_empty_frame_not_eligible(self):
        frame = pd.DataFrame()
        eligible, msg = validate_cold_start_eligible(frame)
        self.assertFalse(eligible)
        self.assertIn('empty', msg)

    def test_insufficient_positive_events(self):
        frame = _make_small_frame(n_samples=80, positive_ratio=0.05, seed=1)
        eligible, msg = validate_cold_start_eligible(frame)
        self.assertFalse(eligible)
        self.assertIn('Insufficient positive events', msg)

    def test_insufficient_winters(self):
        frame = _make_multi_winter_frame(n_winters=2, samples_per_winter=40, seed=2)
        eligible, msg = validate_cold_start_eligible(frame)
        self.assertFalse(eligible)
        self.assertIn('Insufficient winter seasons', msg)

    def test_eligible_frame(self):
        frame = _make_multi_winter_frame(n_winters=3, samples_per_winter=50, seed=3)
        eligible, msg = validate_cold_start_eligible(frame)
        self.assertTrue(eligible)
        self.assertIn('Cold-start eligible', msg)

    def test_no_timestamp_column_skips_winter_check(self):
        frame = _make_small_frame(n_samples=80, positive_ratio=0.2, seed=4)
        frame = frame.drop(columns=['timestamp'])
        eligible, msg = validate_cold_start_eligible(frame)
        self.assertTrue(eligible)


class TestFitColdStartBundle(unittest.TestCase):

    def test_cold_start_bundle_returns_valid_dict(self):
        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=10)
        config = ColdStartConfig(target_feature_count=8)
        bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=42,
            config=config,
        )
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.get('forecast_mode'), 'cold_start')
        self.assertIn('base_model', bundle)
        self.assertIn('calibrated_model', bundle)
        self.assertIn('selected_features', bundle)
        self.assertIn('metrics', bundle)
        self.assertIn('selector', bundle)

    def test_cold_start_feature_count_at_most_target(self):
        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=11)
        config = ColdStartConfig(target_feature_count=7)
        bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=42,
            config=config,
        )
        selected = bundle['selected_features']
        self.assertLessEqual(len(selected), 7)

    def test_cold_start_metrics_include_relaxed_floors(self):
        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=12)
        config = ColdStartConfig(pss_floor=0.25, brier_ceiling=0.22)
        bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=42,
            config=config,
        )
        metrics = bundle['metrics']
        self.assertAlmostEqual(metrics['pss_floor_applied'], 0.25)
        self.assertAlmostEqual(metrics['brier_ceiling_applied'], 0.22)

    def test_cold_start_config_in_bundle(self):
        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=13)
        config = ColdStartConfig(target_feature_count=9, rf_trees=150)
        bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=42,
            config=config,
        )
        cs_config = bundle.get('cold_start_config')
        self.assertIsNotNone(cs_config)
        self.assertEqual(cs_config['target_feature_count'], 9)
        self.assertEqual(cs_config['rf_trees'], 150)

    def test_cold_start_class_weight_stronger_than_full(self):
        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=14)
        config = ColdStartConfig()
        bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=42,
            config=config,
        )
        cs_config = bundle['cold_start_config']
        self.assertEqual(cs_config['class_weight'][1], 6)

    def test_cold_start_backward_compatible_with_more_data(self):
        frame = _make_multi_winter_frame(n_winters=3, samples_per_winter=80, seed=15)
        config = ColdStartConfig()
        bundle = fit_cold_start_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=42,
            config=config,
        )
        self.assertEqual(bundle['forecast_mode'], 'cold_start')
        self.assertGreater(len(bundle['selected_features']), 0)


class TestColdStartSyntheticGeneration(unittest.TestCase):

    def test_correct_sample_count(self):
        regions = load_regions()
        samples_per_region = 10
        multiplier = 3
        frame = generate_cold_start_synthetic_frame(
            regions, samples_per_region=samples_per_region, seed=42, augmentation_multiplier=multiplier,
        )
        expected = samples_per_region * multiplier * len(regions)
        self.assertEqual(len(frame), expected)

    def test_synthetic_timestamps_are_utc(self):
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(regions, samples_per_region=2, seed=42)
        self.assertEqual(str(frame['timestamp'].dt.tz), 'UTC')

    def test_bootstrap_timestamps_are_utc(self):
        regions = load_regions()
        frame = generate_training_frame(regions, samples_per_region=2, seed=42)
        self.assertEqual(str(frame['timestamp'].dt.tz), 'UTC')

    def test_has_zone_type_column(self):
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(regions, samples_per_region=5, seed=42)
        self.assertIn('zone_type', frame.columns)

    def test_himalayan_regions_have_zone_type(self):
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(regions, samples_per_region=5, seed=42)
        himalayan_rows = frame[frame['zone_type'].notna()]
        himalayan_regions = [r for r in regions if getattr(r, 'zone_type', None) is not None]
        if himalayan_regions:
            self.assertGreater(len(himalayan_rows), 0)
            for zone_type in himalayan_rows['zone_type'].unique():
                self.assertIsNotNone(zone_type)

    def test_non_himalayan_regions_have_null_zone_type(self):
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(regions, samples_per_region=5, seed=42)
        non_himalayan_rows = frame[frame['zone_type'].isna()]
        non_himalayan_regions = [r for r in regions if getattr(r, 'zone_type', None) is None]
        if non_himalayan_regions:
            self.assertGreater(len(non_himalayan_rows), 0)

    def test_has_required_columns(self):
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(regions, samples_per_region=5, seed=42)
        # Check columns that build_feature_row produces (not all FEATURE_COLUMNS
        # — some like weak_layer_depth are filled by the training dataset loader)
        from backend.common.features import build_feature_row
        sample_context = type('Ctx', (), {'region_key': 'test', 'region_name': 'Test', 'timestamp': pd.Timestamp('2025-01-01'), 'lat': 34.0, 'lng': 74.5})()
        expected_cols = set(build_feature_row(sample_context, np.random.default_rng(0)).keys())
        for col in expected_cols:
            self.assertIn(col, frame.columns)
        self.assertIn('label', frame.columns)
        self.assertIn('timestamp', frame.columns)
        self.assertIn('region_key', frame.columns)

    def test_default_multiplier_is_3(self):
        regions = load_regions()
        frame_default = generate_cold_start_synthetic_frame(regions, samples_per_region=10, seed=42)
        frame_explicit = generate_cold_start_synthetic_frame(
            regions, samples_per_region=10, seed=42, augmentation_multiplier=3,
        )
        self.assertEqual(len(frame_default), len(frame_explicit))


class TestForecastModeRouting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _lstm_mock = MagicMock()
        _lstm_mock.fit_lstm_head.return_value = None
        cls._lstm_modules_patch = patch.dict('sys.modules', {'backend.lstm_model': _lstm_mock})
        cls._lstm_modules_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls._lstm_modules_patch.stop()

    def test_fit_model_cold_start_calls_fit_cold_start_bundle(self):
        from backend.train_model import fit_model
        from backend.common.cold_start_config import ForecastMode

        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=20)
        dataset_manifest = {'training_dataset_version': 'test_v1'}

        with patch('backend.train_model.fit_cold_start_bundle') as mock_cold, \
             patch('backend.train_model.compute_seed_stability_summary') as mock_stab:
            sys.modules['backend.lstm_model'].split_validation_and_calibration_frame.return_value = (frame.iloc[70:85], frame.iloc[70:85], {})
            mock_cold.return_value = {
                'base_model': None,
                'calibrated_model': None,
                'surrogate_model': None,
                'selected_features': FEATURE_COLUMNS[:10],
                'feature_means': {},
                'resampling': {},
                'calibration_method': 'isotonic',
                'calibration_error': None,
                'tree_variance_policy': {},
                'metrics': {'pss_holdout': 0.3, 'pss_timeseries_mean': 0.3, 'brier_score': 0.2},
                'cv_metrics': {'mean_pss': 0.3, 'fold_pss': [0.3]},
                'spatial_cv_metrics': {'mean_pss': 0.3, 'fold_pss': [0.3]},
                'selector': None,
                'surrogate_model_version': 'test',
                'train_df': frame.iloc[:70],
                'calib_df': frame.iloc[70:85],
                'test_df': frame.iloc[85:],
                'forecast_mode': 'cold_start',
            }
            mock_stab.return_value = {'seed_runs': [], 'primary_seed': 42}
            bundle, test_df = fit_model(
                seed=42, frame=frame, dataset_manifest=dataset_manifest,
                forecast_mode=ForecastMode.COLD_START,
            )
            mock_cold.assert_called_once()
            self.assertEqual(bundle.get('forecast_mode'), 'cold_start')

    def test_fit_model_full_calls_fit_surrogate_bundle(self):
        from backend.train_model import fit_model
        from backend.common.cold_start_config import ForecastMode

        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=21)
        dataset_manifest = {'training_dataset_version': 'test_v1'}

        with patch('backend.train_model.fit_cold_start_bundle') as mock_cold, \
             patch('backend.train_model.fit_surrogate_bundle') as mock_full, \
             patch('backend.train_model.compute_seed_stability_summary') as mock_stab:
            sys.modules['backend.lstm_model'].split_validation_and_calibration_frame.return_value = (frame.iloc[70:85], frame.iloc[70:85], {})
            mock_full.return_value = {
                'base_model': None,
                'calibrated_model': None,
                'surrogate_model': None,
                'selected_features': FEATURE_COLUMNS[:15],
                'feature_means': {},
                'resampling': {},
                'calibration_method': 'isotonic',
                'calibration_error': None,
                'tree_variance_policy': {},
                'metrics': {'pss_holdout': 0.5, 'pss_timeseries_mean': 0.5, 'brier_score': 0.1},
                'cv_metrics': {'mean_pss': 0.5, 'fold_pss': [0.5]},
                'spatial_cv_metrics': {'mean_pss': 0.5, 'fold_pss': [0.5]},
                'selector': None,
                'surrogate_model_version': 'test',
                'train_df': frame.iloc[:70],
                'calib_df': frame.iloc[70:85],
                'test_df': frame.iloc[85:],
            }
            mock_stab.return_value = {'seed_runs': [], 'primary_seed': 42}
            bundle, test_df = fit_model(
                seed=42, frame=frame, dataset_manifest=dataset_manifest,
                forecast_mode=ForecastMode.FULL,
            )
            mock_full.assert_called_once()
            mock_cold.assert_not_called()

    def test_fit_model_default_mode_is_full(self):
        from backend.train_model import fit_model

        frame = _make_small_frame(n_samples=100, positive_ratio=0.2, seed=22)
        dataset_manifest = {'training_dataset_version': 'test_v1'}

        with patch('backend.train_model.fit_surrogate_bundle') as mock_full, \
             patch('backend.train_model.compute_seed_stability_summary') as mock_stab:
            sys.modules['backend.lstm_model'].split_validation_and_calibration_frame.return_value = (frame.iloc[70:85], frame.iloc[70:85], {})
            mock_full.return_value = {
                'base_model': None,
                'calibrated_model': None,
                'surrogate_model': None,
                'selected_features': FEATURE_COLUMNS[:15],
                'feature_means': {},
                'resampling': {},
                'calibration_method': 'isotonic',
                'calibration_error': None,
                'tree_variance_policy': {},
                'metrics': {'pss_holdout': 0.5, 'pss_timeseries_mean': 0.5, 'brier_score': 0.1},
                'cv_metrics': {'mean_pss': 0.5, 'fold_pss': [0.5]},
                'spatial_cv_metrics': {'mean_pss': 0.5, 'fold_pss': [0.5]},
                'selector': None,
                'surrogate_model_version': 'test',
                'train_df': frame.iloc[:70],
                'calib_df': frame.iloc[70:85],
                'test_df': frame.iloc[85:],
            }
            mock_stab.return_value = {'seed_runs': [], 'primary_seed': 42}
            bundle, test_df = fit_model(
                seed=42, frame=frame, dataset_manifest=dataset_manifest,
            )
            mock_full.assert_called_once()


class TestColdStartSyntheticIntegration(unittest.TestCase):
    """Tests for cold-start synthetic data governance columns and merge behavior."""

    def test_cold_start_synthetic_frame_has_governance_columns(self):
        """Verify that generate_cold_start_synthetic_frame output can receive governance columns."""
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(
            regions, samples_per_region=10, seed=42, augmentation_multiplier=2,
        )
        # The frame should have label and timestamp columns
        self.assertIn('label', frame.columns)
        self.assertIn('timestamp', frame.columns)
        self.assertGreater(len(frame), 0)
        # Verify we can assign governance columns (as train_model.py does)
        frame['training_weight'] = np.where(frame['label'] == 1, 0.55, 1.0)
        frame['label_confidence'] = np.where(frame['label'] == 1, 0.55, 1.0)
        frame['confidence_decayed'] = frame['label_confidence']
        frame['label_source'] = 'cold_start_synthetic'
        frame['governance_version'] = 'test_v1'
        frame['review_basis'] = 'synthetic'
        self.assertIn('training_weight', frame.columns)
        self.assertIn('label_confidence', frame.columns)
        self.assertIn('confidence_decayed', frame.columns)
        self.assertTrue((frame['label_source'] == 'cold_start_synthetic').all())

    def test_cold_start_synthetic_frame_has_label_source(self):
        """Verify label_source can be set to cold_start_synthetic."""
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(
            regions, samples_per_region=5, seed=42, augmentation_multiplier=1,
        )
        frame['label_source'] = 'cold_start_synthetic'
        self.assertTrue((frame['label_source'] == 'cold_start_synthetic').all())

    def test_cold_start_merge_preserves_real_data(self):
        """Verify that merging cold-start synthetic with real data preserves real rows."""
        real_frame = _make_multi_winter_frame(n_winters=3, samples_per_winter=20, seed=11)
        real_count = len(real_frame)

        regions = load_regions()
        cold_frame = generate_cold_start_synthetic_frame(
            regions, samples_per_region=10, seed=42, augmentation_multiplier=2,
        )
        # Simulate the merge logic from train_model.py
        merged = pd.concat([real_frame, cold_frame], ignore_index=True).sort_values('timestamp').reset_index(drop=True)

        # Real data rows should be preserved
        self.assertEqual(len(merged), real_count + len(cold_frame))
        self.assertEqual(str(merged['timestamp'].dt.tz), 'UTC')
        # All real region_keys should still be present
        for rk in real_frame['region_key'].unique():
            self.assertIn(rk, merged['region_key'].values)

    def test_cold_start_synthetic_has_positive_and_negative(self):
        """Verify cold-start synthetic frame has both positive and negative labels."""
        regions = load_regions()
        frame = generate_cold_start_synthetic_frame(
            regions, samples_per_region=20, seed=42, augmentation_multiplier=3,
        )
        positive_count = int((frame['label'] == 1).sum())
        negative_count = int((frame['label'] == 0).sum())
        self.assertGreater(positive_count, 0, 'Cold-start synthetic frame should have positive labels')
        self.assertGreater(negative_count, 0, 'Cold-start synthetic frame should have negative labels')


if __name__ == '__main__':
    unittest.main()
