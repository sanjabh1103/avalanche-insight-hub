from __future__ import annotations

import unittest
import warnings

import numpy as np
import pandas as pd

from backend.common.features import FEATURE_COLUMNS
from backend.models.surrogate_rf import (
    SURROGATE_CLASS_WEIGHT,
    build_tree_shap_explainer,
    collect_tree_probabilities,
    compute_tree_shap,
    fit_surrogate_bundle,
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
        explainer = build_tree_shap_explainer(bundle['base_model'])

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


if __name__ == '__main__':
    unittest.main()
