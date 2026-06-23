from __future__ import annotations

import unittest
import warnings
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.common.features import FEATURE_COLUMNS
from backend.models.surrogate_rf import (
    SURROGATE_CLASS_WEIGHT,
    TreeShapUnavailableError,
    build_tree_shap_explainer,
    build_shap_narrative,
    collect_tree_probabilities,
    compute_tree_shap,
    compute_tree_shap_batch,
    fit_surrogate_bundle,
    physically_valid_surrogate_rows,
    try_smote,
)


def _build_training_frame(rows: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(17)
    labels = np.asarray([1 if idx % 7 == 0 else 0 for idx in range(rows)], dtype=int)
    frame = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=rows, freq='D', tz='UTC'),
        'label': labels,
        'training_weight': np.where(labels == 1, 0.9, 1.0),
    })
    for feature_idx, feature in enumerate(FEATURE_COLUMNS):
        signal = labels * (0.35 + (feature_idx * 0.01))
        frame[feature] = rng.normal(loc=signal, scale=0.12, size=rows)
    return frame


class TrySmoteTests(unittest.TestCase):
    def test_try_smote_falls_back_to_class_weight_only_when_minority_is_too_small(self) -> None:
        x_train = pd.DataFrame({'snowfall_24h': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]})
        y_train = pd.Series([0, 0, 0, 0, 0, 1])

        _, _, meta = try_smote(x_train, y_train, seed=17)

        self.assertEqual(meta['strategy'], 'class_weight_only')
        self.assertEqual(meta['k_neighbors_target'], 5)

    def test_try_smote_filters_unphysical_synthetic_weather_rows(self) -> None:
        x_train = pd.DataFrame({
            'temperature_2m': [-6.0, -5.5, -7.0, -4.5, -8.0, -6.5, -3.0, -2.5, -4.0, -3.5, -5.0, -4.8],
            'elevation_m': [3100.0, 3000.0, 3200.0, 3050.0, 3300.0, 3150.0, 2100.0, 2200.0, 2050.0, 2150.0, 2250.0, 2300.0],
            'snowfall_24h': [0.2] * 12,
            'precipitation_24h': [0.2] * 12,
            'snow_settlement_index': [0.4] * 12,
        })
        y_train = pd.Series([0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1])

        class FakeSampler:
            def __init__(self, **_kwargs: object) -> None:
                pass

            def fit_resample(self, _x: pd.DataFrame, _y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
                synthetic = pd.DataFrame([
                    {
                        'temperature_2m': 11.0,
                        'elevation_m': 3400.0,
                        'snowfall_24h': 0.1,
                        'precipitation_24h': 0.1,
                        'snow_settlement_index': 0.4,
                    },
                    {
                        'temperature_2m': -3.0,
                        'elevation_m': 2800.0,
                        'snowfall_24h': 0.2,
                        'precipitation_24h': 0.2,
                        'snow_settlement_index': 0.5,
                    },
                ])
                return pd.concat([x_train, synthetic], ignore_index=True), pd.Series([*y_train.tolist(), 1, 1])

        with patch('backend.models.surrogate_rf.KMeansSMOTE', FakeSampler):
            x_res, y_res, meta = try_smote(x_train, y_train, seed=17)

        self.assertEqual(meta['strategy'], 'kmeanssmote')
        self.assertEqual(meta['synthetic_generated'], 2)
        self.assertEqual(meta['synthetic_rejected_physical'], 1)
        self.assertEqual(len(x_res), len(y_res))
        self.assertEqual(len(x_res), len(x_train) + 1)
        self.assertTrue(physically_valid_surrogate_rows(x_res).all())


class SurrogateRfBundleTests(unittest.TestCase):
    def test_fit_surrogate_bundle_preserves_rf_policy_and_metadata(self) -> None:
        bundle = fit_surrogate_bundle(
            frame=_build_training_frame(),
            feature_columns=FEATURE_COLUMNS,
            seed=17,
            time_series_splits=3,
        )

        self.assertEqual(bundle['base_model'].class_weight, SURROGATE_CLASS_WEIGHT)
        self.assertIn(bundle['resampling']['strategy'], {'class_weight_only', 'kmeanssmote', 'fallback_no_resample'})
        self.assertIsInstance(bundle['surrogate_model_version'], str)
        self.assertTrue(bundle['surrogate_model_version'])
        self.assertTrue(bundle['selected_features'])

    def test_tree_shap_returns_ranked_top_features(self) -> None:
        bundle = fit_surrogate_bundle(
            frame=_build_training_frame(),
            feature_columns=FEATURE_COLUMNS,
            seed=23,
            time_series_splits=3,
        )
        selected_frame = pd.DataFrame(
            bundle['selector'].transform(_build_training_frame().iloc[[0]][FEATURE_COLUMNS].astype(float)),
            columns=bundle['selected_features'],
        )
        try:
            explainer = build_tree_shap_explainer(bundle['base_model'])
        except TreeShapUnavailableError as exc:
            self.skipTest(str(exc))

        shap_values, top_features = compute_tree_shap(explainer, selected_frame, bundle['selected_features'])

        self.assertTrue(shap_values)
        self.assertGreaterEqual(len(top_features), 1)
        self.assertLessEqual(len(top_features), 5)
        self.assertEqual(top_features[0]['rank'], 1)
        self.assertEqual(
            [item['rank'] for item in top_features],
            list(range(1, len(top_features) + 1)),
        )
        ordered_magnitudes = [abs(float(item['shap_value'])) for item in top_features]
        self.assertEqual(ordered_magnitudes, sorted(ordered_magnitudes, reverse=True))

    def test_tree_shap_batch_matches_single_row_shape(self) -> None:
        bundle = fit_surrogate_bundle(
            frame=_build_training_frame(),
            feature_columns=FEATURE_COLUMNS,
            seed=24,
            time_series_splits=3,
        )
        selected_frame = pd.DataFrame(
            bundle['selector'].transform(_build_training_frame().iloc[:3][FEATURE_COLUMNS].astype(float)),
            columns=bundle['selected_features'],
        )
        try:
            explainer = build_tree_shap_explainer(bundle['base_model'])
        except TreeShapUnavailableError as exc:
            self.skipTest(str(exc))

        packets = compute_tree_shap_batch(explainer, selected_frame, bundle['selected_features'])

        self.assertEqual(len(packets), 3)
        for shap_values, top_features in packets:
            self.assertTrue(shap_values)
            self.assertGreaterEqual(len(top_features), 1)
            self.assertLessEqual(len(top_features), 5)
            self.assertEqual(top_features[0]['rank'], 1)

    def test_tree_shap_unavailable_error_is_explicit(self) -> None:
        bundle = fit_surrogate_bundle(
            frame=_build_training_frame(),
            feature_columns=FEATURE_COLUMNS,
            seed=29,
            time_series_splits=3,
        )
        real_import = __import__

        def _missing_shap(name, *args, **kwargs):
            if name == 'shap':
                raise ModuleNotFoundError("No module named 'shap'")
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=_missing_shap):
            with self.assertRaises(TreeShapUnavailableError):
                build_tree_shap_explainer(bundle['base_model'])

    def test_collect_tree_probabilities_avoids_dataframe_feature_name_warning(self) -> None:
        frame = _build_training_frame()
        bundle = fit_surrogate_bundle(
            frame=frame,
            feature_columns=FEATURE_COLUMNS,
            seed=31,
            time_series_splits=3,
        )
        selected_frame = pd.DataFrame(
            bundle['selector'].transform(frame.iloc[[0]][FEATURE_COLUMNS].astype(float)),
            columns=bundle['selected_features'],
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            probabilities = collect_tree_probabilities(bundle['base_model'], selected_frame)

        expected = np.column_stack([
            tree.predict_proba(selected_frame.to_numpy(dtype=np.float32, copy=False))[:, 1]
            for tree in bundle['base_model'].estimators_
        ])
        np.testing.assert_allclose(probabilities, expected)
        self.assertFalse(any('feature names' in str(w.message) for w in caught))


class ShapNarrativeTests(unittest.TestCase):
    def test_empty_features_returns_default(self) -> None:
        result = build_shap_narrative([])
        self.assertEqual(result, 'No SHAP feature attributions available.')

    def test_narrative_with_drivers_only(self) -> None:
        features = [
            {'feature': 'elevation', 'shap_value': 0.15, 'feature_value': 0.8, 'rank': 1},
            {'feature': 'snowfall_24h', 'shap_value': 0.10, 'feature_value': 0.6, 'rank': 2},
            {'feature': 'wind_loading', 'shap_value': 0.05, 'feature_value': 0.7, 'rank': 3},
        ]
        result = build_shap_narrative(features, danger_label=3)
        self.assertIn('Considerable', result)
        self.assertIn('elevation', result)
        self.assertIn('24-hour snowfall', result)
        self.assertIn('increases risk', result)
        self.assertNotIn('reduces risk', result)

    def test_narrative_with_suppressors(self) -> None:
        features = [
            {'feature': 'elevation', 'shap_value': 0.15, 'feature_value': 0.8, 'rank': 1},
            {'feature': 'settlement_rate', 'shap_value': -0.08, 'feature_value': 0.5, 'rank': 2},
            {'feature': 'shear_strength', 'shap_value': -0.05, 'feature_value': 0.6, 'rank': 3},
        ]
        result = build_shap_narrative(features, danger_label=2)
        self.assertIn('Moderate', result)
        self.assertIn('Risk suppressors', result)
        self.assertIn('snow settlement rate', result)
        self.assertIn('reduces risk', result)

    def test_narrative_without_danger_label(self) -> None:
        features = [
            {'feature': 'snowfall_24h', 'shap_value': 0.12, 'feature_value': 0.6, 'rank': 1},
        ]
        result = build_shap_narrative(features)
        self.assertNotIn('Predicted danger level', result)
        self.assertIn('24-hour snowfall', result)


if __name__ == '__main__':
    unittest.main()
