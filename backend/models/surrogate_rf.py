from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from imblearn.over_sampling import KMeansSMOTE
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import RFE
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score, roc_curve
from sklearn.model_selection import TimeSeriesSplit
from sklearn.svm import SVC

SURROGATE_CLASS_WEIGHT = {0: 1, 1: 4}
SURROGATE_TARGET_FEATURE_COUNT = 15
SURROGATE_KMEANS_SMOTE_K_NEIGHBORS = 5
SURROGATE_RF_TREES = 300
SURROGATE_CV_RF_TREES = 200
SURROGATE_MIN_SAMPLES_LEAF = 2


class TreeShapUnavailableError(RuntimeError):
    """Raised when the runtime cannot construct a TreeSHAP explainer."""


def peirce_skill_score_max(y_true: np.ndarray, y_prob: np.ndarray) -> tuple[float, float]:
    """Threshold-free PSS = max(TPR - FPR) over all probability thresholds."""
    y_true_arr = np.asarray(y_true).astype(int)
    y_prob_arr = np.asarray(y_prob).astype(float)
    if y_true_arr.size == 0 or len(np.unique(y_true_arr)) < 2:
        return 0.0, 0.5
    try:
        fpr, tpr, thresholds = roc_curve(y_true_arr, y_prob_arr)
    except Exception:
        return 0.0, 0.5
    j_scores = tpr - fpr
    idx = int(np.argmax(j_scores))
    return float(j_scores[idx]), float(thresholds[idx])


def peirce_skill_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """PSS = TPR - FPR. Returns 0.0 on degenerate inputs."""
    y_true_arr = np.asarray(y_true).astype(int)
    y_pred_arr = np.asarray(y_pred).astype(int)
    if y_true_arr.size == 0:
        return 0.0
    try:
        tn, fp, fn, tp = confusion_matrix(y_true_arr, y_pred_arr, labels=[0, 1]).ravel()
    except ValueError:
        return 0.0
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return float(tpr - fpr)


def chronological_split(frame: pd.DataFrame, train_ratio: float = 0.7, calib_ratio: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ordered = frame.sort_values('timestamp').reset_index(drop=True)
    train_end = max(1, int(len(ordered) * train_ratio))
    calib_end = max(train_end + 1, int(len(ordered) * (train_ratio + calib_ratio)))
    train_df = ordered.iloc[:train_end].copy()
    calib_df = ordered.iloc[train_end:calib_end].copy()
    test_df = ordered.iloc[calib_end:].copy()
    if test_df.empty:
        test_df = ordered.iloc[-max(1, len(ordered) // 10):].copy()
    if calib_df.empty:
        calib_df = ordered.iloc[train_end:train_end + max(1, len(ordered) // 10)].copy()
    return train_df, calib_df, test_df


def event_sample_weights(frame: pd.DataFrame, *, decay_floor: float = 0.3, drift_multiplier: float = 1.0) -> np.ndarray:
    if frame.empty:
        return np.array([], dtype=float)
    if 'training_weight' in frame.columns:
        weights = frame['training_weight'].astype(float).to_numpy()
    elif 'confidence_decayed' in frame.columns:
        weights = frame['confidence_decayed'].astype(float).to_numpy()
    elif 'label_confidence' in frame.columns:
        weights = frame['label_confidence'].astype(float).to_numpy()
    elif 'confidence' in frame.columns:
        weights = frame['confidence'].astype(float).to_numpy()
    else:
        weights = np.ones(len(frame), dtype=float)
    if weights.size == 0:
        return np.array([], dtype=float)
    weights = np.clip(weights, 0.0, 1.0)
    if 'label' in frame.columns:
        label_mask = frame['label'].astype(int).to_numpy() == 1
        weights = np.where(label_mask, np.maximum(weights, decay_floor), 1.0)
    if drift_multiplier != 1.0:
        cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(days=730)
        timestamps = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
        old_mask = (timestamps < cutoff).fillna(False).to_numpy()
        weights = np.where(old_mask, weights * drift_multiplier, weights)
    return weights


def resampled_sample_weights(original_frame: pd.DataFrame, resampled_y: np.ndarray, base_weights: np.ndarray) -> np.ndarray:
    if base_weights.size == 0:
        return np.ones(len(resampled_y), dtype=float)
    if len(base_weights) >= len(resampled_y):
        return base_weights[:len(resampled_y)]
    synthetic_count = len(resampled_y) - len(base_weights)
    if 'label' in original_frame.columns:
        minority_weights = base_weights[original_frame['label'].astype(int).to_numpy() == 1]
        synthetic_weight = float(np.mean(minority_weights)) if minority_weights.size else 1.0
    else:
        synthetic_weight = float(np.mean(base_weights)) if base_weights.size else 1.0
    synthetic_weight = float(np.clip(synthetic_weight, 0.3, 1.0))
    return np.concatenate([base_weights, np.full(synthetic_count, synthetic_weight, dtype=float)])


def try_smote(x_train: pd.DataFrame, y_train: pd.Series, seed: int) -> tuple[pd.DataFrame, pd.Series, dict[str, object]]:
    """Use the locked KMeansSMOTE config for the tabular surrogate path."""
    class_counts = Counter(y_train.tolist())
    min_class = min(class_counts.values()) if class_counts else 0

    if min_class <= SURROGATE_KMEANS_SMOTE_K_NEIGHBORS:
        return x_train, y_train, {
            'strategy': 'class_weight_only',
            'note': (
                'insufficient_minority_samples '
                f'(min_class={min_class}, required>{SURROGATE_KMEANS_SMOTE_K_NEIGHBORS})'
            ),
            'k_neighbors_target': SURROGATE_KMEANS_SMOTE_K_NEIGHBORS,
            'class_counts_before': dict(class_counts),
        }

    try:
        sampler = KMeansSMOTE(
            random_state=seed,
            k_neighbors=SURROGATE_KMEANS_SMOTE_K_NEIGHBORS,
            cluster_balance_threshold=0.1,
        )
        x_res, y_res = sampler.fit_resample(x_train, y_train)
        return x_res, y_res, {
            'strategy': 'kmeanssmote',
            'k_neighbors': SURROGATE_KMEANS_SMOTE_K_NEIGHBORS,
            'class_counts_before': dict(class_counts),
            'class_counts_after': dict(Counter(y_res.tolist())),
        }
    except Exception as exc:  # pragma: no cover - intentional fallback
        return x_train, y_train, {
            'strategy': 'fallback_no_resample',
            'k_neighbors_target': SURROGATE_KMEANS_SMOTE_K_NEIGHBORS,
            'error': str(exc),
            'class_counts_before': dict(class_counts),
        }


def selected_feature_contributions(
    model: RandomForestClassifier,
    selected_features: list[str],
    feature_means: dict[str, float],
    row: pd.Series,
) -> dict[str, float]:
    importances = getattr(model, 'feature_importances_', np.ones(len(selected_features)) / max(1, len(selected_features)))
    contributions = {
        feature: float((row[feature] - feature_means.get(feature, 0.0)) * importance)
        for feature, importance in zip(selected_features, importances)
    }
    return dict(sorted(contributions.items(), key=lambda item: abs(item[1]), reverse=True)[:5])


def timeseries_cv_pss(frame: pd.DataFrame, seed: int, n_splits: int, feature_columns: list[str]) -> dict[str, Any]:
    """Evaluate PSS across chronological folds without random shuffle."""
    ordered = frame.sort_values('timestamp').reset_index(drop=True)
    x = ordered[feature_columns].astype(float).values
    y = ordered['label'].astype(int).values
    if len(y) < n_splits * 2 or len(np.unique(y)) < 2:
        return {'mean_pss': 0.0, 'fold_pss': [], 'note': 'insufficient_folds_or_classes'}

    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_scores: list[float] = []
    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(x)):
        y_train_fold = y[train_idx]
        if len(np.unique(y_train_fold)) < 2:
            continue
        rf_fold = RandomForestClassifier(
            n_estimators=SURROGATE_CV_RF_TREES,
            random_state=seed + fold_idx,
            class_weight=SURROGATE_CLASS_WEIGHT,
            n_jobs=-1,
            min_samples_leaf=SURROGATE_MIN_SAMPLES_LEAF,
        )
        rf_fold.fit(x[train_idx], y_train_fold)
        y_prob_fold = rf_fold.predict_proba(x[test_idx])[:, 1]
        fold_pss, _ = peirce_skill_score_max(y[test_idx], y_prob_fold)
        fold_scores.append(fold_pss)

    mean_pss = float(np.mean(fold_scores)) if fold_scores else 0.0
    return {'mean_pss': mean_pss, 'fold_pss': fold_scores, 'n_splits': n_splits}


def calibrate_surrogate_model(
    base_model: RandomForestClassifier,
    x_cal_sel: pd.DataFrame,
    y_cal: pd.Series,
) -> tuple[object, str, str | None]:
    calibration_method = 'isotonic'
    calibrated_model: object = base_model
    calibration_error: str | None = None

    def _build_calibrator(method: str):
        try:
            from sklearn.frozen import FrozenEstimator  # sklearn >= 1.6
            return CalibratedClassifierCV(estimator=FrozenEstimator(base_model), method=method, cv=None)
        except Exception:
            return CalibratedClassifierCV(estimator=base_model, method=method, cv='prefit')

    try:
        if len(np.unique(y_cal)) >= 2 and len(y_cal) >= 10:
            calibrator = _build_calibrator('isotonic')
            calibrator.fit(x_cal_sel, y_cal)
            calibrated_model = calibrator
        else:
            calibration_method = 'sigmoid'
            calibrator = _build_calibrator('sigmoid')
            calibrator.fit(x_cal_sel, y_cal)
            calibrated_model = calibrator
    except Exception as exc:  # pragma: no cover - intentional fallback
        calibration_error = str(exc)
        calibration_method = 'unavailable'
        calibrated_model = base_model

    return calibrated_model, calibration_method, calibration_error


def collect_tree_probabilities(base_model: object, x_sel: pd.DataFrame | np.ndarray) -> np.ndarray:
    trees = getattr(base_model, 'estimators_', [])
    if not trees:
        return np.zeros(len(x_sel))
    if isinstance(x_sel, pd.DataFrame):
        tree_input = x_sel.to_numpy(dtype=np.float32, copy=False)
    else:
        tree_input = np.asarray(x_sel, dtype=np.float32)
    return np.column_stack([tree.predict_proba(tree_input)[:, 1] for tree in trees])


def build_tree_shap_explainer(base_model: object) -> object:
    try:
        import shap
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via patched tests/runtime
        raise TreeShapUnavailableError(
            'TreeSHAP dependency unavailable: install backend/requirements.txt before running explainability paths.'
        ) from exc

    return shap.TreeExplainer(base_model)


def compute_tree_shap(
    explainer: object,
    selected_frame: pd.DataFrame,
    selected_features: list[str],
) -> tuple[dict[str, float], list[dict[str, float | str | int]]]:
    shap_values = explainer.shap_values(selected_frame)
    if isinstance(shap_values, list):
        shap_vector = np.asarray(shap_values[-1])[0]
    else:
        shap_array = np.asarray(shap_values)
        if shap_array.ndim == 3:
            shap_vector = shap_array[0, :, -1]
        else:
            shap_vector = shap_array[0]

    feature_values = selected_frame.iloc[0].to_dict()
    ordered = sorted(
        [
            {
                'feature': feature,
                'shap_value': float(value),
                'feature_value': float(feature_values[feature]),
            }
            for feature, value in zip(selected_features, shap_vector)
        ],
        key=lambda item: abs(float(item['shap_value'])),
        reverse=True,
    )[:5]
    for rank, item in enumerate(ordered, start=1):
        item['rank'] = rank
    return ({item['feature']: float(item['shap_value']) for item in ordered}, ordered)


def compute_tree_shap_batch(
    explainer: object,
    selected_frame: pd.DataFrame,
    selected_features: list[str],
) -> list[tuple[dict[str, float], list[dict[str, float | str | int]]]]:
    """Compute TreeSHAP for many inference rows in one explainer call."""
    shap_values = explainer.shap_values(selected_frame)
    if isinstance(shap_values, list):
        shap_matrix = np.asarray(shap_values[-1])
    else:
        shap_array = np.asarray(shap_values)
        if shap_array.ndim == 3:
            shap_matrix = shap_array[:, :, -1]
        else:
            shap_matrix = shap_array
    if shap_matrix.ndim == 1:
        shap_matrix = shap_matrix.reshape(1, -1)

    packets: list[tuple[dict[str, float], list[dict[str, float | str | int]]]] = []
    for row_index, shap_vector in enumerate(shap_matrix):
        feature_values = selected_frame.iloc[row_index].to_dict()
        ordered = sorted(
            [
                {
                    'feature': feature,
                    'shap_value': float(value),
                    'feature_value': float(feature_values[feature]),
                }
                for feature, value in zip(selected_features, shap_vector)
            ],
            key=lambda item: abs(float(item['shap_value'])),
            reverse=True,
        )[:5]
        for rank, item in enumerate(ordered, start=1):
            item['rank'] = rank
        packets.append(({item['feature']: float(item['shap_value']) for item in ordered}, ordered))
    return packets


def fit_surrogate_bundle(
    *,
    frame: pd.DataFrame,
    feature_columns: list[str],
    seed: int,
    time_series_splits: int,
) -> dict[str, Any]:
    cv_metrics = timeseries_cv_pss(frame, seed=seed, n_splits=time_series_splits, feature_columns=feature_columns)

    train_df, calib_df, test_df = chronological_split(frame)

    x_train = train_df[feature_columns].astype(float)
    y_train = train_df['label'].astype(int)
    x_cal = calib_df[feature_columns].astype(float)
    y_cal = calib_df['label'].astype(int)
    x_test = test_df[feature_columns].astype(float)
    y_test = test_df['label'].astype(int)

    x_res, y_res, resample_meta = try_smote(x_train, y_train, seed)
    drift_multiplier = 0.5 if bool(frame.attrs.get('concept_drift_detected')) else 1.0
    base_weights = event_sample_weights(train_df, decay_floor=0.3, drift_multiplier=drift_multiplier)
    resampled_weights = resampled_sample_weights(train_df, y_res, base_weights)

    effective_n_features = min(SURROGATE_TARGET_FEATURE_COUNT, x_res.shape[1])
    selector = RFE(
        estimator=SVC(kernel='linear', class_weight='balanced', random_state=seed),
        n_features_to_select=effective_n_features,
        step=1,
    )
    selector.fit(x_res, y_res)

    selected_features = [feature for feature, keep in zip(feature_columns, selector.support_) if keep]
    if not selected_features:
        selected_features = feature_columns[:SURROGATE_TARGET_FEATURE_COUNT]

    x_res_sel = pd.DataFrame(selector.transform(x_res), columns=selected_features)
    x_cal_sel = pd.DataFrame(selector.transform(x_cal), columns=selected_features)
    x_test_sel = pd.DataFrame(selector.transform(x_test), columns=selected_features)

    base_model = RandomForestClassifier(
        n_estimators=SURROGATE_RF_TREES,
        random_state=seed,
        class_weight=SURROGATE_CLASS_WEIGHT,
        n_jobs=-1,
        min_samples_leaf=SURROGATE_MIN_SAMPLES_LEAF,
    )
    base_model.fit(x_res_sel, y_res, sample_weight=resampled_weights)

    try:
        test_tree_probs = collect_tree_probabilities(base_model, x_test_sel)
        tree_variance_policy = {
            'mean_tree_std_on_test': float(test_tree_probs.std(axis=1).mean()),
            'max_tree_std_on_test': float(test_tree_probs.std(axis=1).max()),
            'extracted_before_calibration': True,
        }
        raw_mean_prob = test_tree_probs.mean(axis=1)
    except Exception as exc:  # pragma: no cover - defensive
        tree_variance_policy = {'error': str(exc), 'extracted_before_calibration': False}
        raw_mean_prob = base_model.predict_proba(x_test_sel)[:, 1]

    calibrated_model, calibration_method, calibration_error = calibrate_surrogate_model(base_model, x_cal_sel, y_cal)
    y_prob = calibrated_model.predict_proba(x_test_sel)[:, 1]
    holdout_pss, optimal_threshold = peirce_skill_score_max(y_test, y_prob)
    y_pred = (y_prob >= 0.5).astype(int)
    y_pred_optimal = (y_prob >= optimal_threshold).astype(int)

    metrics = {
        'accuracy': float(accuracy_score(y_test, y_pred)),
        'f1': float(f1_score(y_test, y_pred, zero_division=0)),
        'precision': float(precision_score(y_test, y_pred, zero_division=0)),
        'recall': float(recall_score(y_test, y_pred, zero_division=0)),
        'brier_score': float(brier_score_loss(y_test, y_prob)),
        'roc_auc': float(roc_auc_score(y_test, y_prob)) if len(np.unique(y_test)) >= 2 else None,
        'selected_feature_count': len(selected_features),
        'target_feature_count': SURROGATE_TARGET_FEATURE_COUNT,
        'pss_holdout': holdout_pss,
        'pss_optimal_threshold': optimal_threshold,
        'pss_holdout_at_threshold_0p5': peirce_skill_score(y_test, y_pred),
        'f1_at_optimal_threshold': float(f1_score(y_test, y_pred_optimal, zero_division=0)),
        'precision_at_optimal_threshold': float(precision_score(y_test, y_pred_optimal, zero_division=0)),
        'recall_at_optimal_threshold': float(recall_score(y_test, y_pred_optimal, zero_division=0)),
        'pss_timeseries_mean': cv_metrics.get('mean_pss', 0.0),
        'pss_timeseries_folds': cv_metrics.get('fold_pss', []),
        'raw_mean_prob_p99': float(np.quantile(raw_mean_prob, 0.99)) if raw_mean_prob.size else None,
    }

    return {
        'base_model': base_model,
        'calibrated_model': calibrated_model,
        'surrogate_model': calibrated_model,
        'selected_features': selected_features,
        'feature_means': x_res_sel.mean().to_dict(),
        'resampling': resample_meta,
        'calibration_method': calibration_method,
        'calibration_error': calibration_error,
        'tree_variance_policy': tree_variance_policy,
        'metrics': metrics,
        'cv_metrics': cv_metrics,
        'selector': selector,
        'surrogate_model_version': datetime.now(timezone.utc).isoformat(),
        'train_df': train_df,
        'calib_df': calib_df,
        'test_df': test_df,
    }
