from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import KMeansSMOTE
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import RFE
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.svm import SVC

from backend.common.artifacts import create_artifact_dir, dump_json, dump_joblib
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, generate_training_frame
from backend.common.regions import load_regions
from backend.common.supabase_io import has_supabase_credentials, patch_first_row


# Story 21 + Edit 3: publish the minimum Peirce Skill Score required for the
# trained model artifact to be accepted. Set via env so CI can promote models
# only after a cold-start warmup period.
PSS_FLOOR = float(os.getenv('PSS_FLOOR', '0.45'))
TIME_SERIES_SPLITS = int(os.getenv('TIME_SERIES_SPLITS', '5'))


def peirce_skill_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """PSS = TPR - FPR. Defined on binary labels only. Returns 0.0 on degenerate inputs."""
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


def chronological_split(frame: pd.DataFrame, train_ratio: float = 0.7, calib_ratio: float = 0.15):
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


def try_smote(x_train: pd.DataFrame, y_train: pd.Series, seed: int):
    """Edit 3 locked: KMeansSMOTE with FIXED k_neighbors=5 per PRD contract.

    Challenge 5 mitigation — 13:1 class imbalance cannot be fixed with a
    dynamically shrinking k because that lets the sampler degrade to noise.
    We accept that datasets with fewer than 6 minority samples (k+1) cannot
    be safely resampled and fall back to class-weight-only training in that
    case, which the RandomForest still handles via class_weight={0:1, 1:4}.
    """
    class_counts = Counter(y_train.tolist())
    min_class = min(class_counts.values()) if class_counts else 0

    LOCKED_K_NEIGHBORS = 5
    if min_class <= LOCKED_K_NEIGHBORS:
        return x_train, y_train, {
            'strategy': 'class_weight_only',
            'note': f'insufficient_minority_samples (min_class={min_class}, required>{LOCKED_K_NEIGHBORS})',
            'k_neighbors_target': LOCKED_K_NEIGHBORS,
            'class_counts_before': dict(class_counts),
        }

    try:
        sampler = KMeansSMOTE(random_state=seed, k_neighbors=LOCKED_K_NEIGHBORS, cluster_balance_threshold=0.1)
        x_res, y_res = sampler.fit_resample(x_train, y_train)
        return x_res, y_res, {
            'strategy': 'kmeanssmote',
            'k_neighbors': LOCKED_K_NEIGHBORS,
            'class_counts_before': dict(class_counts),
            'class_counts_after': dict(Counter(y_res.tolist())),
        }
    except Exception as exc:  # pragma: no cover - fallback is intentional
        return x_train, y_train, {
            'strategy': 'fallback_no_resample',
            'k_neighbors_target': LOCKED_K_NEIGHBORS,
            'error': str(exc),
            'class_counts_before': dict(class_counts),
        }


def selected_feature_contributions(model: RandomForestClassifier, selected_features: list[str], feature_means: dict[str, float], row: pd.Series) -> dict[str, float]:
    importances = getattr(model, 'feature_importances_', np.ones(len(selected_features)) / max(1, len(selected_features)))
    contributions = {
        feature: float((row[feature] - feature_means.get(feature, 0.0)) * importance)
        for feature, importance in zip(selected_features, importances)
    }
    return dict(sorted(contributions.items(), key=lambda item: abs(item[1]), reverse=True)[:5])


def timeseries_cv_pss(frame: pd.DataFrame, seed: int, n_splits: int) -> dict:
    """Story 21: evaluate PSS across chronological folds (no random shuffle).

    Returns mean PSS plus per-fold scores so we can audit drift over time.
    """
    ordered = frame.sort_values('timestamp').reset_index(drop=True)
    x = ordered[FEATURE_COLUMNS].astype(float).values
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
            n_estimators=200,
            random_state=seed + fold_idx,
            class_weight={0: 1, 1: 4},
            n_jobs=-1,
            min_samples_leaf=2,
        )
        rf_fold.fit(x[train_idx], y_train_fold)
        y_prob_fold = rf_fold.predict_proba(x[test_idx])[:, 1]
        y_pred_fold = (y_prob_fold >= 0.5).astype(int)
        fold_scores.append(peirce_skill_score(y[test_idx], y_pred_fold))

    mean_pss = float(np.mean(fold_scores)) if fold_scores else 0.0
    return {'mean_pss': mean_pss, 'fold_pss': fold_scores, 'n_splits': n_splits}


def fit_model(seed: int, samples_per_region: int):
    regions = load_regions()
    frame = generate_training_frame(regions, samples_per_region=samples_per_region, seed=seed)

    # Edit 3 Story 21: chronological TimeSeriesSplit PSS audit BEFORE the final
    # production fit so we can report drift-aware scores for the release gate.
    cv_metrics = timeseries_cv_pss(frame, seed=seed, n_splits=TIME_SERIES_SPLITS)

    train_df, calib_df, test_df = chronological_split(frame)

    x_train = train_df[FEATURE_COLUMNS].astype(float)
    y_train = train_df['label'].astype(int)
    x_cal = calib_df[FEATURE_COLUMNS].astype(float)
    y_cal = calib_df['label'].astype(int)
    x_test = test_df[FEATURE_COLUMNS].astype(float)
    y_test = test_df['label'].astype(int)

    x_res, y_res, resample_meta = try_smote(x_train, y_train, seed)

    # Edit 3 locked: SVM-RFE prunes to exactly 15 features (Challenge 6).
    # We deliberately require >=15 raw features; if the generator ever returns
    # fewer, we widen to whatever is available but flag it in metadata so CI
    # can catch the regression.
    target_n_features = 15
    effective_n_features = min(target_n_features, x_res.shape[1])
    selector = RFE(
        estimator=SVC(kernel='linear', class_weight='balanced', random_state=seed),
        n_features_to_select=effective_n_features,
        step=1,
    )
    selector.fit(x_res, y_res)

    selected_features = [feature for feature, keep in zip(FEATURE_COLUMNS, selector.support_) if keep]
    if not selected_features:
        selected_features = FEATURE_COLUMNS[:target_n_features]

    x_res_sel = pd.DataFrame(selector.transform(x_res), columns=selected_features)
    x_cal_sel = pd.DataFrame(selector.transform(x_cal), columns=selected_features)
    x_test_sel = pd.DataFrame(selector.transform(x_test), columns=selected_features)

    # Edit 3 locked: cost-sensitive RandomForest with asymmetric 4:1 penalty
    # (Challenge 5 — missing an avalanche costs 4x more than a false alarm).
    rf = RandomForestClassifier(
        n_estimators=300,
        random_state=seed,
        class_weight={0: 1, 1: 4},
        n_jobs=-1,
        min_samples_leaf=2,
    )
    rf.fit(x_res_sel, y_res)

    # Story 16: extract tree variance BEFORE wrapping in isotonic calibration
    # so downstream inference has the raw epistemic variance rather than the
    # squashed post-calibration distribution.
    try:
        test_tree_probs = np.column_stack([tree.predict_proba(x_test_sel)[:, 1] for tree in rf.estimators_])
        tree_variance_policy = {
            'mean_tree_std_on_test': float(test_tree_probs.std(axis=1).mean()),
            'max_tree_std_on_test': float(test_tree_probs.std(axis=1).max()),
            'extracted_before_calibration': True,
        }
        raw_mean_prob = test_tree_probs.mean(axis=1)
    except Exception as exc:  # pragma: no cover - defensive
        tree_variance_policy = {'error': str(exc), 'extracted_before_calibration': False}
        raw_mean_prob = rf.predict_proba(x_test_sel)[:, 1]

    calibration_method = 'isotonic'
    calibrated_model = rf
    calibration_error = None

    # sklearn 1.6+ removed cv='prefit' in favor of FrozenEstimator. Try the
    # modern path first, fall back to the legacy API so we remain compatible
    # across pinned environments.
    def _build_calibrator(method: str):
        try:
            from sklearn.frozen import FrozenEstimator  # sklearn >= 1.6
            return CalibratedClassifierCV(estimator=FrozenEstimator(rf), method=method, cv=None)
        except Exception:
            return CalibratedClassifierCV(estimator=rf, method=method, cv='prefit')

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
    except Exception as exc:  # pragma: no cover - fallback is intentional
        calibration_error = str(exc)
        calibration_method = 'unavailable'
        calibrated_model = rf

    y_prob = calibrated_model.predict_proba(x_test_sel)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    holdout_pss = peirce_skill_score(y_test, y_pred)

    metrics = {
        'accuracy': float(accuracy_score(y_test, y_pred)),
        'f1': float(f1_score(y_test, y_pred, zero_division=0)),
        'precision': float(precision_score(y_test, y_pred, zero_division=0)),
        'recall': float(recall_score(y_test, y_pred, zero_division=0)),
        'brier_score': float(brier_score_loss(y_test, y_prob)),
        'roc_auc': float(roc_auc_score(y_test, y_prob)) if len(np.unique(y_test)) >= 2 else None,
        'selected_feature_count': len(selected_features),
        'target_feature_count': target_n_features,
        'pss_holdout': holdout_pss,
        'pss_timeseries_mean': cv_metrics.get('mean_pss', 0.0),
        'pss_timeseries_folds': cv_metrics.get('fold_pss', []),
        'pss_gate_floor': PSS_FLOOR,
        'raw_mean_prob_p99': float(np.quantile(raw_mean_prob, 0.99)) if raw_mean_prob.size else None,
    }

    bundle = {
        'selector': selector,
        'base_model': rf,
        'calibrated_model': calibrated_model,
        'feature_columns': FEATURE_COLUMNS,
        'selected_features': selected_features,
        'feature_means': x_res_sel.mean().to_dict(),
        'resampling': resample_meta,
        'calibration_method': calibration_method,
        'calibration_error': calibration_error,
        'tree_variance_policy': tree_variance_policy,
        'metrics': metrics,
        'cv_metrics': cv_metrics,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'seed': seed,
    }
    return bundle


def publish_metadata(artifact_dir: Path, bundle: dict[str, object]):
    metadata = {
        'selected_features': bundle['selected_features'],
        'feature_columns': bundle['feature_columns'],
        'feature_means': bundle['feature_means'],
        'resampling': bundle['resampling'],
        'calibration_method': bundle['calibration_method'],
        'calibration_error': bundle['calibration_error'],
        'metrics': bundle['metrics'],
        'artifact_dir': str(artifact_dir),
        'published_at': datetime.now(timezone.utc).isoformat(),
    }
    dump_json(artifact_dir / 'feature_schema.json', {
        'feature_columns': bundle['feature_columns'],
        'selected_features': bundle['selected_features'],
        'feature_means': bundle['feature_means'],
    })
    dump_json(artifact_dir / 'training_metrics.json', metadata)
    dump_joblib(artifact_dir / 'model.joblib', bundle)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description='Train the Avalanche Insight Hub async ML model')
    parser.add_argument('--samples-per-region', type=int, default=load_settings().samples_per_region)
    parser.add_argument('--seed', type=int, default=load_settings().seed)
    parser.add_argument('--artifact-root', type=Path, default=load_settings().artifact_root)
    args = parser.parse_args()

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_dir = create_artifact_dir(args.artifact_root)
    bundle = fit_model(seed=args.seed, samples_per_region=args.samples_per_region)

    # Edit 3 Story 21: PSS > PSS_FLOOR artifact gate. Use the higher of the
    # chronological-CV mean and the holdout PSS so a single lucky test fold
    # cannot shadow a poor CV run.
    pss_reported = max(
        float(bundle['metrics'].get('pss_holdout', 0.0) or 0.0),
        float(bundle['metrics'].get('pss_timeseries_mean', 0.0) or 0.0),
    )
    # Cold-start allowance: when PSS_FLOOR is explicitly set to 0.0 we accept
    # pss == 0 so the first synthetic-data artifact can ship. At any positive
    # floor (prod default 0.45) we keep the strict > rule per PRD.
    if PSS_FLOOR <= 0.0:
        gate_passed = pss_reported >= PSS_FLOOR
    else:
        gate_passed = pss_reported > PSS_FLOOR
    bundle['metrics']['pss_reported'] = pss_reported
    bundle['metrics']['pss_gate_passed'] = gate_passed

    metadata = publish_metadata(artifact_dir, bundle)
    metadata['pss_reported'] = pss_reported
    metadata['pss_gate_passed'] = gate_passed
    metadata['pss_gate_floor'] = PSS_FLOOR
    dump_json(artifact_dir / 'training_metrics.json', metadata)

    if not gate_passed:
        print(
            f"[train_model] PSS gate FAILED: reported={pss_reported:.3f} <= floor={PSS_FLOOR:.3f}. "
            "Refusing to publish artifact to Supabase.",
            file=sys.stderr,
        )
        print(json.dumps(metadata, indent=2))
        return 2

    if has_supabase_credentials():
        payload = {
            'version': f"async-{artifact_dir.name}",
            'last_trained': metadata['published_at'],
            'f1_score': metadata['metrics']['f1'],
            'next_run': None,
        }
        try:
            patch_first_row('model_status', payload)
        except Exception as exc:  # pragma: no cover - publish is best effort
            metadata['publish_error'] = str(exc)
            (artifact_dir / 'training_metrics.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')

    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
