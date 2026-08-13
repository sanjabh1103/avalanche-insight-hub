"""Paired baseline-vs-verification-gated evaluation.

Evaluates the same forecast/event universe twice:
  (a) no-verification baseline — all predictions count
  (b) evidence-gated — predictions without grounded evidence abstain

Unavailable evidence is reported as abstention, not silently converted to a
negative label.  Uses fixed temporal holdouts or ``TimeSeriesSplit`` — random
splits are prohibited because they can leak future information.

The output is a reproducible JSON report.  It is evaluation-only and cannot
promote a model.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_curve,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit


def peirce_skill_score_max(y_true: np.ndarray, y_prob: np.ndarray) -> tuple[float, float]:
    """Return threshold-free PSS without importing the training stack."""
    y_true_arr = np.asarray(y_true).astype(int)
    y_prob_arr = np.asarray(y_prob).astype(float)
    if y_true_arr.size == 0 or len(np.unique(y_true_arr)) < 2:
        return 0.0, 0.5
    try:
        fpr, tpr, thresholds = roc_curve(y_true_arr, y_prob_arr)
    except Exception:
        return 0.0, 0.5
    scores = tpr - fpr
    index = int(np.argmax(scores))
    return float(scores[index]), float(thresholds[index])


def peirce_skill_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Return PSS = TPR - FPR, with a safe degenerate-input fallback."""
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


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return float(r * 2 * math.asin(math.sqrt(a)))


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _input_hashes(
    predictions: Sequence[dict[str, Any]],
    events: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Capture deterministic input and lineage hashes in the report."""
    feature_hashes: set[str] = set()
    evidence_hashes: set[str] = set()
    for prediction in predictions:
        for key in ('feature_snapshot_sha256', 'feature_snapshot_hash'):
            value = prediction.get(key)
            if isinstance(value, str) and value.strip():
                feature_hashes.add(value.strip())
        for key in ('evidence_replay_sha256', 'replay_snapshot_sha256', 'source_hash'):
            value = prediction.get(key)
            if isinstance(value, str) and value.strip():
                evidence_hashes.add(value.strip())
        lineage = prediction.get('evidence_lineage')
        if isinstance(lineage, dict):
            source_hashes = lineage.get('source_hashes')
            if isinstance(source_hashes, dict):
                evidence_hashes.update(
                    str(value).strip()
                    for value in source_hashes.values()
                    if isinstance(value, str) and value.strip()
                )
    return {
        'prediction_source_hash': _stable_hash(predictions),
        'event_source_hash': _stable_hash(events),
        'feature_snapshot_hashes': sorted(feature_hashes),
        'evidence_source_hashes': sorted(evidence_hashes),
    }


def label_predictions(
    predictions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    match_radius_km: float = 15.0,
) -> list[dict[str, Any]]:
    """Attach binary labels to predictions based on spatial/temporal event matching."""
    if not predictions:
        return []
    predictions = [dict(prediction) for prediction in predictions]
    if not events:
        for pred in predictions:
            pred['label'] = 0
        return predictions

    parsed_events: list[dict[str, Any]] = []
    for event in events:
        loc = event.get('location')
        event_lat: float | None = None
        event_lng: float | None = None
        if isinstance(loc, str) and loc.startswith('POINT'):
            parts = loc.replace('POINT(', '').replace(')', '').split()
            if len(parts) >= 2:
                event_lng, event_lat = float(parts[0]), float(parts[1])
        elif isinstance(loc, dict):
            coords = loc.get('coordinates', [0, 0])
            if len(coords) >= 2:
                event_lng, event_lat = float(coords[0]), float(coords[1])
        if event_lat is None or event_lng is None:
            continue
        ts = event.get('timestamp', '')
        event_date = str(ts)[:10] if ts else None
        if event_date:
            parsed_events.append({
                'date': event_date,
                'lat': event_lat,
                'lng': event_lng,
            })

    for pred in predictions:
        pred['label'] = 0
        pred_date = pred.get('forecast_date')
        pred_lat = pred.get('lat', 0)
        pred_lng = pred.get('lng', 0)
        for event in parsed_events:
            if event['date'] != pred_date:
                continue
            dist = _haversine_km(pred_lat, pred_lng, event['lat'], event['lng'])
            if dist <= match_radius_km:
                pred['label'] = 1
                break

    return predictions


def _compute_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, Any]:
    if len(y_true) == 0:
        return {'error': 'No predictions to evaluate'}
    if len(np.unique(y_true)) < 2:
        return {
            'warning': 'Only one class present in labels — metrics undefined',
            'n_predictions': int(len(y_true)),
            'n_positive': int(y_true.sum()),
            'n_negative': int((y_true == 0).sum()),
        }

    pss, optimal_threshold = peirce_skill_score_max(y_true, y_prob)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    return {
        'n_predictions': int(len(y_true)),
        'n_positive': int(y_true.sum()),
        'n_negative': int((y_true == 0).sum()),
        'true_positives': tp,
        'false_positives': fp,
        'false_negatives': fn,
        'true_negatives': tn,
        'precision': float(precision_score(y_true, y_pred, zero_division=0)),
        'recall': float(recall_score(y_true, y_pred, zero_division=0)),
        'f1': float(f1_score(y_true, y_pred, zero_division=0)),
        'brier_score': float(brier_score_loss(y_true, y_prob)),
        'roc_auc': float(roc_auc_score(y_true, y_prob)),
        'pss': float(pss),
        'pss_optimal_threshold': float(optimal_threshold),
        'pss_at_0p5': float(peirce_skill_score(y_true, y_pred)),
    }


def evaluate_paired(
    predictions: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    match_radius_km: float = 15.0,
    n_splits: int = 3,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Run paired baseline-vs-verification-gated evaluation with temporal holdout.

    Each prediction must have:
      - forecast_date (str)
      - lat, lng (float)
      - probability (float)
      - evidence_available (bool) — whether grounded evidence exists

    Returns a reproducible JSON report with paired metrics, fold boundaries,
    coverage, abstention rate, and source hashes.
    """
    input_hashes = _input_hashes(predictions, events)
    labelled = label_predictions(predictions, events, match_radius_km=match_radius_km)

    if not labelled:
        return {
            'error': 'No predictions to evaluate',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            **input_hashes,
            'evaluation_only': True,
            'can_promote_model': False,
        }

    labelled.sort(key=lambda r: r.get('forecast_date', ''))

    dates = sorted({r.get('forecast_date', '') for r in labelled})
    if n_splits < 2:
        return {
            'error': 'n_splits must be at least 2',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'n_predictions': len(labelled),
            'n_unique_forecast_dates': len(dates),
            **input_hashes,
            'evaluation_only': True,
            'can_promote_model': False,
        }
    if len(dates) < 3:
        return {
            'error': 'At least 3 unique forecast dates are required for temporal holdout',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'n_predictions': len(labelled),
            'n_unique_forecast_dates': len(dates),
            **input_hashes,
            'evaluation_only': True,
            'can_promote_model': False,
        }
    effective_splits = min(int(n_splits), len(dates) - 1)
    tscv = TimeSeriesSplit(n_splits=effective_splits)

    fold_boundaries: list[dict[str, str]] = []
    baseline_metrics_list: list[dict[str, Any]] = []
    gated_metrics_list: list[dict[str, Any]] = []

    date_array = np.array(dates)
    for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(date_array)):
        test_dates = set(date_array[test_idx])
        fold_boundaries.append({
            'fold': fold_idx,
            'test_start': min(test_dates),
            'test_end': max(test_dates),
            'n_test_dates': len(test_dates),
        })

        fold_preds = [r for r in labelled if r.get('forecast_date') in test_dates]
        if not fold_preds:
            continue

        y_true_all = np.array([r.get('label', 0) for r in fold_preds], dtype=int)
        y_prob_all = np.array([float(r.get('probability', 0)) for r in fold_preds])
        y_pred_all = (y_prob_all >= threshold).astype(int)

        baseline_metrics_list.append(_compute_metrics(y_true_all, y_prob_all, y_pred_all))

        gated_preds = [r for r in fold_preds if r.get('evidence_available') is True]
        abstained = [r for r in fold_preds if r.get('evidence_available') is not True]

        if gated_preds:
            y_true_gated = np.array([r.get('label', 0) for r in gated_preds], dtype=int)
            y_prob_gated = np.array([float(r.get('probability', 0)) for r in gated_preds])
            y_pred_gated = (y_prob_gated >= threshold).astype(int)
            gated_metrics = _compute_metrics(y_true_gated, y_prob_gated, y_pred_gated)
        else:
            gated_metrics = {
                'warning': 'No gated predictions with evidence in this fold',
                'n_predictions': 0,
            }

        gated_metrics['n_abstained'] = len(abstained)
        gated_metrics['abstention_rate'] = float(len(abstained) / len(fold_preds)) if fold_preds else 0.0
        gated_metrics['coverage'] = float(len(gated_preds) / len(fold_preds)) if fold_preds else 0.0
        gated_metrics_list.append(gated_metrics)

    source_hash = _stable_hash({
        **input_hashes,
        'n_predictions': len(labelled),
        'n_events': len(events),
        'match_radius_km': match_radius_km,
        'threshold': threshold,
        'n_splits': effective_splits,
        'dates': dates,
    })

    n_evidence = sum(1 for r in labelled if r.get('evidence_available') is True)
    n_no_evidence = len(labelled) - n_evidence

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'threshold': threshold,
        'match_radius_km': match_radius_km,
        'n_splits': effective_splits,
        'n_predictions': len(labelled),
        'n_events': len(events),
        'n_with_evidence': n_evidence,
        'n_without_evidence': n_no_evidence,
        'overall_coverage': float(n_evidence / len(labelled)) if labelled else 0.0,
        'evidence_completeness': float(n_evidence / len(labelled)) if labelled else 0.0,
        'overall_abstention_rate': float(n_no_evidence / len(labelled)) if labelled else 0.0,
        'fold_boundaries': fold_boundaries,
        'baseline_metrics': baseline_metrics_list,
        'verification_gated_metrics': gated_metrics_list,
        **input_hashes,
        'source_hash': source_hash,
        'evaluation_only': True,
        'can_promote_model': False,
    }
