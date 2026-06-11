from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from backend.reproduction.swiss_ravafcast.constants import RF2_RESOURCE_KEY, USAGE_BOUNDARY
from backend.reproduction.swiss_ravafcast.data_loader import (
    TARGET_ALIASES,
    inspect_swiss_frame,
    validate_swiss_frame,
)
from backend.reproduction.swiss_ravafcast.features import (
    FEATURE_SET_AUTO_NUMERIC_CURRENT,
    FEATURE_SET_NAMES,
    FeatureSetReport,
    select_feature_set,
    validate_no_banned_features,
)


RF4_LABELS = (1, 2, 3, 4)
LEAKAGE_PRONE_FEATURE_COLUMNS = {
    'unnamed: 0',
    'sector_id',
    'warnreg',
    'set',
}


@dataclass(frozen=True)
class SwissRF4Config:
    seed: int = 20260522
    n_estimators: int = 300
    min_samples_leaf: int = 2
    test_season_count: int = 1
    calibration_season_count: int = 1


def winter_season(value: object) -> str:
    dt = pd.to_datetime(value, utc=True, errors='coerce')
    if pd.isna(dt):
        raise ValueError(f'cannot parse winter season from date value: {value!r}')
    start_year = int(dt.year if dt.month >= 11 else dt.year - 1)
    return f'{start_year}-{str(start_year + 1)[-2:]}'


def _target_column(frame: pd.DataFrame, target_column: str | None) -> str:
    if target_column:
        if target_column not in frame.columns:
            raise ValueError(f'target column not found: {target_column}')
        return target_column
    for alias in TARGET_ALIASES[RF2_RESOURCE_KEY]:
        if alias in frame.columns:
            return alias
    raise ValueError('RF4 reproduction requires a D_tidy target column by default')


def infer_feature_columns(
    frame: pd.DataFrame,
    *,
    target_column: str,
    exclude_columns: set[str] | None = None,
) -> list[str]:
    report = select_feature_set(
        frame,
        feature_set_name=FEATURE_SET_AUTO_NUMERIC_CURRENT,
        target_column=target_column,
        exclude_columns=set(exclude_columns or set()) | LEAKAGE_PRONE_FEATURE_COLUMNS,
    )
    return list(report.selected_columns)


def _split_by_winter_season(
    frame: pd.DataFrame,
    *,
    date_column: str,
    config: SwissRF4Config,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    working = frame.copy()
    parsed_dates = pd.to_datetime(working[date_column], utc=True, errors='coerce')
    invalid_count = int(parsed_dates.isna().sum())
    if invalid_count:
        raise ValueError(f'cannot parse winter season for {invalid_count} row(s) from {date_column}')
    season_start_year = np.where(parsed_dates.dt.month >= 11, parsed_dates.dt.year, parsed_dates.dt.year - 1)
    working['_winter_season'] = [
        f'{int(start_year)}-{str(int(start_year) + 1)[-2:]}'
        for start_year in season_start_year
    ]
    seasons = sorted(str(value) for value in working['_winter_season'].dropna().unique())
    min_required = config.test_season_count + config.calibration_season_count + 1
    if len(seasons) < min_required:
        ordered = working.sort_values(date_column).reset_index(drop=True)
        train_end = max(1, int(len(ordered) * 0.7))
        calib_end = max(train_end + 1, int(len(ordered) * 0.85))
        return (
            ordered.iloc[:train_end].drop(columns=['_winter_season']).copy(),
            ordered.iloc[train_end:calib_end].drop(columns=['_winter_season']).copy(),
            ordered.iloc[calib_end:].drop(columns=['_winter_season']).copy(),
        )

    test_seasons = set(seasons[-config.test_season_count:])
    calib_start = -(config.test_season_count + config.calibration_season_count)
    calib_end = -config.test_season_count
    calibration_seasons = set(seasons[calib_start:calib_end])
    train_mask = ~working['_winter_season'].isin(test_seasons | calibration_seasons)
    calib_mask = working['_winter_season'].isin(calibration_seasons)
    test_mask = working['_winter_season'].isin(test_seasons)
    return (
        working.loc[train_mask].drop(columns=['_winter_season']).copy(),
        working.loc[calib_mask].drop(columns=['_winter_season']).copy(),
        working.loc[test_mask].drop(columns=['_winter_season']).copy(),
    )


def _prepare_xy(frame: pd.DataFrame, *, feature_columns: list[str], target_column: str) -> tuple[pd.DataFrame, np.ndarray]:
    x = frame[feature_columns].astype(float).copy()
    medians = x.median(numeric_only=True).fillna(0.0)
    x = x.fillna(medians)
    y = frame[target_column].astype(float).round().clip(1, 4).astype(int).to_numpy()
    return x, y


def _proba_for_labels(raw_proba: np.ndarray, classes: np.ndarray, labels: tuple[int, ...] = RF4_LABELS) -> np.ndarray:
    class_index = {int(label): idx for idx, label in enumerate(classes)}
    aligned = np.zeros((raw_proba.shape[0], len(labels)), dtype=float)
    for label_idx, label in enumerate(labels):
        raw_idx = class_index.get(int(label))
        if raw_idx is not None:
            aligned[:, label_idx] = raw_proba[:, raw_idx]
    row_sums = aligned.sum(axis=1, keepdims=True)
    return np.divide(aligned, row_sums, out=np.full_like(aligned, 1.0 / len(labels)), where=row_sums > 0)


def _normalize_probabilities(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities.astype(float), 0.0, 1.0)
    row_sums = clipped.sum(axis=1, keepdims=True)
    return np.divide(clipped, row_sums, out=np.full_like(clipped, 1.0 / clipped.shape[1]), where=row_sums > 0)


def _one_hot(y: np.ndarray, labels: tuple[int, ...] = RF4_LABELS) -> np.ndarray:
    encoded = np.zeros((len(y), len(labels)), dtype=float)
    label_index = {label: idx for idx, label in enumerate(labels)}
    for row_idx, label in enumerate(y):
        idx = label_index.get(int(label))
        if idx is not None:
            encoded[row_idx, idx] = 1.0
    return encoded


def _multiclass_brier_score(y: np.ndarray, probabilities: np.ndarray) -> float:
    return float(np.mean(np.sum((probabilities - _one_hot(y)) ** 2, axis=1)))


def _ece_summary(y: np.ndarray, probabilities: np.ndarray, *, bin_count: int = 10) -> dict[str, Any]:
    confidences = probabilities.max(axis=1)
    predicted_labels = np.asarray(RF4_LABELS)[probabilities.argmax(axis=1)]
    correct = (predicted_labels == y).astype(float)
    bins = []
    total = max(1, len(y))
    ece = 0.0
    for idx in range(bin_count):
        lower = idx / bin_count
        upper = (idx + 1) / bin_count
        mask = (confidences >= lower) & (confidences < upper if idx < bin_count - 1 else confidences <= upper)
        count = int(mask.sum())
        if count:
            accuracy = float(correct[mask].mean())
            confidence = float(confidences[mask].mean())
            ece += (count / total) * abs(accuracy - confidence)
        else:
            accuracy = None
            confidence = None
        bins.append(
            {
                'lower': float(lower),
                'upper': float(upper),
                'count': count,
                'accuracy': accuracy,
                'mean_confidence': confidence,
            }
        )
    return {'ece': float(ece), 'bin_count': bin_count, 'bins': bins}


def _classwise_calibration_bins(
    y: np.ndarray,
    probabilities: np.ndarray,
    *,
    bin_count: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    payload: dict[str, list[dict[str, Any]]] = {}
    for class_idx, label in enumerate(RF4_LABELS):
        observed = (y == label).astype(float)
        predicted = probabilities[:, class_idx]
        rows = []
        for idx in range(bin_count):
            lower = idx / bin_count
            upper = (idx + 1) / bin_count
            mask = (predicted >= lower) & (predicted < upper if idx < bin_count - 1 else predicted <= upper)
            count = int(mask.sum())
            rows.append(
                {
                    'lower': float(lower),
                    'upper': float(upper),
                    'count': count,
                    'mean_predicted_probability': float(predicted[mask].mean()) if count else None,
                    'observed_frequency': float(observed[mask].mean()) if count else None,
                }
            )
        payload[str(label)] = rows
    return payload


def _fit_calibrated_probabilities(
    *,
    calibration_probabilities: np.ndarray,
    y_calibration: np.ndarray,
    test_probabilities: np.ndarray,
) -> tuple[np.ndarray, list[dict[str, Any]], str]:
    calibrated = np.zeros_like(test_probabilities, dtype=float)
    class_reports: list[dict[str, Any]] = []
    methods: set[str] = set()
    for class_idx, label in enumerate(RF4_LABELS):
        y_binary = (y_calibration == label).astype(int)
        positives = int(y_binary.sum())
        negatives = int(len(y_binary) - positives)
        raw_calibration = calibration_probabilities[:, class_idx]
        raw_test = test_probabilities[:, class_idx]
        if positives >= 2 and negatives >= 2:
            calibrator = IsotonicRegression(out_of_bounds='clip')
            calibrator.fit(raw_calibration, y_binary)
            calibrated[:, class_idx] = calibrator.predict(raw_test)
            method = 'isotonic'
        elif positives >= 1 and negatives >= 1:
            calibrator = LogisticRegression(random_state=20260522)
            calibrator.fit(raw_calibration.reshape(-1, 1), y_binary)
            calibrated[:, class_idx] = calibrator.predict_proba(raw_test.reshape(-1, 1))[:, 1]
            method = 'sigmoid'
        else:
            calibrated[:, class_idx] = raw_test
            method = 'identity_insufficient_class_support'
        methods.add(method)
        class_reports.append(
            {
                'class_label': int(label),
                'method': method,
                'calibration_positive_count': positives,
                'calibration_negative_count': negatives,
            }
        )
    normalized = _normalize_probabilities(calibrated)
    if methods == {'isotonic'}:
        method_summary = 'isotonic'
    elif 'sigmoid' in methods:
        method_summary = 'mixed_with_sigmoid_fallback'
    elif 'isotonic' in methods:
        method_summary = 'mixed_isotonic_identity'
    else:
        method_summary = 'identity_insufficient_class_support'
    return normalized, class_reports, method_summary


def _calibration_payload(
    *,
    y_test: np.ndarray,
    uncalibrated_probabilities: np.ndarray,
    calibrated_probabilities: np.ndarray,
    y_calibration: np.ndarray,
    class_reports: list[dict[str, Any]],
    method_summary: str,
) -> dict[str, Any]:
    return {
        'schema_version': 'swiss_rf4_probability_calibration_v1',
        'method': method_summary,
        'calibration_rows': int(len(y_calibration)),
        'class_calibrators': class_reports,
        'preferred_probability_source_for_gpxyz': 'calibrated'
        if method_summary != 'identity_insufficient_class_support'
        else 'uncalibrated',
        'uncalibrated': {
            'brier_score': _multiclass_brier_score(y_test, uncalibrated_probabilities),
            'ece': _ece_summary(y_test, uncalibrated_probabilities),
            'classwise_bins': _classwise_calibration_bins(y_test, uncalibrated_probabilities),
        },
        'calibrated': {
            'brier_score': _multiclass_brier_score(y_test, calibrated_probabilities),
            'ece': _ece_summary(y_test, calibrated_probabilities),
            'classwise_bins': _classwise_calibration_bins(y_test, calibrated_probabilities),
        },
    }


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _column_value(row: pd.Series, *names: str) -> object:
    for name in names:
        if name in row.index:
            return _json_value(row[name])
    return None


def _evaluation_rows(
    test_df: pd.DataFrame,
    *,
    y_test: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray,
    uncalibrated_y_proba: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(test_df.reset_index(drop=True).iterrows()):
        probabilities = {str(label): float(y_proba[idx, label_idx]) for label_idx, label in enumerate(RF4_LABELS)}
        uncalibrated_probabilities = {
            str(label): float(uncalibrated_y_proba[idx, label_idx])
            for label_idx, label in enumerate(RF4_LABELS)
        }
        expected_danger = sum(float(label) * probabilities[str(label)] for label in RF4_LABELS)
        uncalibrated_expected_danger = sum(
            float(label) * uncalibrated_probabilities[str(label)] for label in RF4_LABELS
        )
        rows.append(
            {
                'date': _column_value(row, 'datum', 'date'),
                'station_code': _column_value(row, 'station_code', 'station_id', 'station'),
                'warnreg': _column_value(row, 'warnreg'),
                'elevation_station': _column_value(row, 'elevation_station', 'elevation_m', 'elevation'),
                'true_danger': int(y_test[idx]),
                'predicted_danger': int(y_pred[idx]),
                'expected_danger': float(expected_danger),
                'uncalibrated_expected_danger': float(uncalibrated_expected_danger),
                'class_probabilities': probabilities,
                'uncalibrated_class_probabilities': uncalibrated_probabilities,
            }
        )
    return rows


def train_rf4_danger(
    frame: pd.DataFrame,
    *,
    config: SwissRF4Config | None = None,
    target_column: str | None = None,
    feature_columns: list[str] | None = None,
    feature_set_name: str = FEATURE_SET_AUTO_NUMERIC_CURRENT,
) -> dict[str, Any]:
    config = config or SwissRF4Config()
    report = validate_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY)
    target = _target_column(frame, target_column)
    date_column = report.date_column
    if date_column is None:
        raise ValueError('RF4 reproduction requires a date column for winter-season splitting')
    exclude_columns = {report.station_column or '', report.date_column or ''}
    if feature_columns:
        validate_no_banned_features(feature_columns, extra_banned_columns=exclude_columns)
        features = feature_columns
        feature_report = FeatureSetReport(
            name='explicit_feature_columns',
            selected_columns=tuple(feature_columns),
            dropped_banned_columns=tuple(),
            missing_whitelist_columns=tuple(),
        )
    else:
        feature_report = select_feature_set(
            frame,
            feature_set_name=feature_set_name,
            target_column=target,
            exclude_columns=exclude_columns,
        )
        features = list(feature_report.selected_columns)
    train_df, calib_df, test_df = _split_by_winter_season(frame, date_column=date_column, config=config)
    if train_df.empty or test_df.empty:
        raise ValueError('RF4 reproduction split produced empty train or test frame')

    x_train, y_train = _prepare_xy(train_df, feature_columns=features, target_column=target)
    x_calib, y_calib = _prepare_xy(calib_df, feature_columns=features, target_column=target) if not calib_df.empty else (None, np.array([]))
    x_test, y_test = _prepare_xy(test_df, feature_columns=features, target_column=target)

    model = RandomForestClassifier(
        n_estimators=config.n_estimators,
        random_state=config.seed,
        class_weight='balanced',
        min_samples_leaf=config.min_samples_leaf,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    uncalibrated_y_pred = model.predict(x_test)
    uncalibrated_y_proba = _proba_for_labels(model.predict_proba(x_test), model.classes_)
    if x_calib is not None and len(y_calib):
        calibration_probabilities = _proba_for_labels(model.predict_proba(x_calib), model.classes_)
        y_proba, class_reports, method_summary = _fit_calibrated_probabilities(
            calibration_probabilities=calibration_probabilities,
            y_calibration=y_calib,
            test_probabilities=uncalibrated_y_proba,
        )
    else:
        y_proba = uncalibrated_y_proba
        class_reports = [
            {
                'class_label': int(label),
                'method': 'identity_no_calibration_rows',
                'calibration_positive_count': 0,
                'calibration_negative_count': 0,
            }
            for label in RF4_LABELS
        ]
        method_summary = 'identity_insufficient_class_support'
    y_pred = np.asarray(RF4_LABELS)[y_proba.argmax(axis=1)]

    per_class_f1 = f1_score(y_test, y_pred, labels=list(RF4_LABELS), average=None, zero_division=0)
    uncalibrated_per_class_f1 = f1_score(
        y_test,
        uncalibrated_y_pred,
        labels=list(RF4_LABELS),
        average=None,
        zero_division=0,
    )
    class_support = {str(label): int((y_test == label).sum()) for label in RF4_LABELS}
    payload = {
        'schema_version': 'swiss_rf4_reproduction_result_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'model_key': 'rf4_danger_v0',
        'target_column': target,
        'feature_columns': features,
        'feature_set': feature_report.as_dict(),
        'split': {
            'strategy': 'winter_season_grouped_with_chronological_fallback',
            'train_rows': int(len(train_df)),
            'calibration_rows': int(len(calib_df)),
            'test_rows': int(len(test_df)),
        },
        'metrics': {
            'accuracy': float(accuracy_score(y_test, y_pred)),
            'macro_f1': float(f1_score(y_test, y_pred, labels=list(RF4_LABELS), average='macro', zero_division=0)),
            'per_class_f1': {str(label): float(score) for label, score in zip(RF4_LABELS, per_class_f1)},
            'class_support': class_support,
            'confusion_matrix_labels': list(RF4_LABELS),
            'confusion_matrix': confusion_matrix(y_test, y_pred, labels=list(RF4_LABELS)).astype(int).tolist(),
        },
        'uncalibrated_metrics': {
            'accuracy': float(accuracy_score(y_test, uncalibrated_y_pred)),
            'macro_f1': float(
                f1_score(y_test, uncalibrated_y_pred, labels=list(RF4_LABELS), average='macro', zero_division=0)
            ),
            'per_class_f1': {str(label): float(score) for label, score in zip(RF4_LABELS, uncalibrated_per_class_f1)},
            'class_support': class_support,
            'confusion_matrix_labels': list(RF4_LABELS),
            'confusion_matrix': confusion_matrix(y_test, uncalibrated_y_pred, labels=list(RF4_LABELS)).astype(int).tolist(),
        },
        'calibration': _calibration_payload(
            y_test=y_test,
            uncalibrated_probabilities=uncalibrated_y_proba,
            calibrated_probabilities=y_proba,
            y_calibration=y_calib,
            class_reports=class_reports,
            method_summary=method_summary,
        ),
        'evaluation_rows': _evaluation_rows(
            test_df,
            y_test=y_test,
            y_pred=y_pred,
            y_proba=y_proba,
            uncalibrated_y_proba=uncalibrated_y_proba,
        ),
        'schema_report': inspect_swiss_frame(frame, resource_key=RF2_RESOURCE_KEY).as_dict(),
    }
    return payload


def build_rf4_feature_audit(
    frame: pd.DataFrame,
    *,
    config: SwissRF4Config | None = None,
    feature_sets: tuple[str, ...] = FEATURE_SET_NAMES,
) -> dict[str, Any]:
    config = config or SwissRF4Config()
    variants = []
    for feature_set_name in feature_sets:
        result = train_rf4_danger(frame, config=config, feature_set_name=feature_set_name)
        metrics = result['metrics']
        variants.append(
            {
                'feature_set': result['feature_set'],
                'metrics': metrics,
                'split': result['split'],
                'calibration': {
                    'method': result['calibration']['method'],
                    'preferred_probability_source_for_gpxyz': result['calibration']['preferred_probability_source_for_gpxyz'],
                    'uncalibrated_brier_score': result['calibration']['uncalibrated']['brier_score'],
                    'calibrated_brier_score': result['calibration']['calibrated']['brier_score'],
                    'uncalibrated_ece': result['calibration']['uncalibrated']['ece']['ece'],
                    'calibrated_ece': result['calibration']['calibrated']['ece']['ece'],
                },
                'published_rf2_accuracy_range': {'lower': 0.72, 'upper': 0.78},
                'accuracy_delta_vs_published_upper': float(metrics['accuracy'] - 0.78),
            }
        )
    return {
        'schema_version': 'swiss_rf4_feature_parity_audit_v1',
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'decision': 'initial_reproduction_signal_pending_parity_audit',
        'variants': variants,
    }


def markdown_feature_audit(payload: dict[str, Any]) -> str:
    lines = [
        '# Swiss RF4 Feature Parity Audit',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        '| Feature set | Features | Accuracy | Macro F1 | Class 4 F1 | Calibrated Brier | Accuracy delta vs RF2 upper |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for variant in payload['variants']:
        metrics = variant['metrics']
        feature_set = variant['feature_set']
        per_class = metrics.get('per_class_f1') or {}
        lines.append(
            '| {name} | {count} | {accuracy:.4f} | {macro_f1:.4f} | {class4:.4f} | {brier:.4f} | {delta:.4f} |'.format(
                name=feature_set['name'],
                count=feature_set['feature_count'],
                accuracy=float(metrics['accuracy']),
                macro_f1=float(metrics['macro_f1']),
                class4=float(per_class.get('4') or 0.0),
                brier=float(variant['calibration']['calibrated_brier_score']),
                delta=float(variant['accuracy_delta_vs_published_upper']),
            )
        )
    lines.extend(
        [
            '',
            '## Claim Boundary',
            '',
            'This audit compares feature-set behavior only. It does not establish RAvaFcast paper parity, production readiness, or Himalayan transfer validity.',
            '',
        ]
    )
    return '\n'.join(lines)
