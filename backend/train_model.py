from __future__ import annotations

import argparse
import json
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
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.svm import SVC

from backend.common.artifacts import create_artifact_dir, dump_json, dump_joblib
from backend.common.config import load_settings
from backend.common.features import FEATURE_COLUMNS, generate_training_frame
from backend.common.regions import load_regions
from backend.common.supabase_io import has_supabase_credentials, patch_first_row


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
    class_counts = Counter(y_train.tolist())
    min_class = min(class_counts.values()) if class_counts else 0
    if min_class < 2:
        return x_train, y_train, {'strategy': 'class_weight_only', 'note': 'insufficient_minority_samples'}

    k_neighbors = max(1, min(5, min_class - 1))
    try:
        sampler = KMeansSMOTE(random_state=seed, k_neighbors=k_neighbors, cluster_balance_threshold=0.1)
        x_res, y_res = sampler.fit_resample(x_train, y_train)
        return x_res, y_res, {
            'strategy': 'kmeanssmote',
            'k_neighbors': k_neighbors,
            'class_counts_before': dict(class_counts),
            'class_counts_after': dict(Counter(y_res.tolist())),
        }
    except Exception as exc:  # pragma: no cover - fallback is intentional
        return x_train, y_train, {
            'strategy': 'fallback_no_resample',
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


def fit_model(seed: int, samples_per_region: int):
    regions = load_regions()
    frame = generate_training_frame(regions, samples_per_region=samples_per_region, seed=seed)
    train_df, calib_df, test_df = chronological_split(frame)

    x_train = train_df[FEATURE_COLUMNS].astype(float)
    y_train = train_df['label'].astype(int)
    x_cal = calib_df[FEATURE_COLUMNS].astype(float)
    y_cal = calib_df['label'].astype(int)
    x_test = test_df[FEATURE_COLUMNS].astype(float)
    y_test = test_df['label'].astype(int)

    x_res, y_res, resample_meta = try_smote(x_train, y_train, seed)
    selector = RFE(
        estimator=SVC(kernel='linear', class_weight='balanced', random_state=seed),
        n_features_to_select=min(15, x_res.shape[1]),
        step=1,
    )
    selector.fit(x_res, y_res)

    selected_features = [feature for feature, keep in zip(FEATURE_COLUMNS, selector.support_) if keep]
    if not selected_features:
        selected_features = FEATURE_COLUMNS[:15]

    x_res_sel = pd.DataFrame(selector.transform(x_res), columns=selected_features)
    x_cal_sel = pd.DataFrame(selector.transform(x_cal), columns=selected_features)
    x_test_sel = pd.DataFrame(selector.transform(x_test), columns=selected_features)

    rf = RandomForestClassifier(
        n_estimators=300,
        random_state=seed,
        class_weight={0: 1, 1: 4},
        n_jobs=-1,
        min_samples_leaf=2,
    )
    rf.fit(x_res_sel, y_res)

    calibration_method = 'isotonic'
    calibrated_model = rf
    calibration_error = None
    try:
        if len(np.unique(y_cal)) >= 2 and len(y_cal) >= 10:
            calibrator = CalibratedClassifierCV(estimator=rf, method='isotonic', cv='prefit')
            calibrator.fit(x_cal_sel, y_cal)
            calibrated_model = calibrator
        else:
            calibration_method = 'sigmoid'
            calibrator = CalibratedClassifierCV(estimator=rf, method='sigmoid', cv='prefit')
            calibrator.fit(x_cal_sel, y_cal)
            calibrated_model = calibrator
    except Exception as exc:  # pragma: no cover - fallback is intentional
        calibration_error = str(exc)
        calibration_method = 'unavailable'
        calibrated_model = rf

    y_prob = calibrated_model.predict_proba(x_test_sel)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    metrics = {
        'accuracy': float(accuracy_score(y_test, y_pred)),
        'f1': float(f1_score(y_test, y_pred, zero_division=0)),
        'precision': float(precision_score(y_test, y_pred, zero_division=0)),
        'recall': float(recall_score(y_test, y_pred, zero_division=0)),
        'brier_score': float(brier_score_loss(y_test, y_prob)),
        'roc_auc': float(roc_auc_score(y_test, y_prob)) if len(np.unique(y_test)) >= 2 else None,
        'selected_feature_count': len(selected_features),
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
        'metrics': metrics,
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
    metadata = publish_metadata(artifact_dir, bundle)

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
