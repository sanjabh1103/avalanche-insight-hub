"""Standalone evaluation module for Avalanche Insight Hub.

Computes PSS, Brier Score, ROC-AUC, F1, precision, and recall by comparing
forecast predictions against known avalanche events in the Supabase
``avalanche_events`` table.

Usage:
    python3 -m backend.evaluation --start 2024-11-01 --end 2025-02-28
    python3 -m backend.evaluation --start 2024-12-15 --end 2024-12-16 --region pir_panjal

Requires Supabase credentials (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) and
at least one published forecast_run with forecast_grids in the date range.
Also requires avalanche event labels in the avalanche_events table for the
same date range. Without labels, the module will report zero events and exit
with a warning.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from backend.common.supabase_io import has_supabase_credentials, rest_get
from backend.models.surrogate_rf import peirce_skill_score, peirce_skill_score_max


def _parse_date(s: str) -> str:
    """Validate and normalize a date string to YYYY-MM-DD."""
    return pd.Timestamp(s).strftime('%Y-%m-%d')


def fetch_forecast_grids(start: str, end: str, region_key: str | None = None) -> list[dict[str, Any]]:
    """Fetch published forecast_grids rows within the date range."""
    params: dict[str, str] = {
        'select': 'id,region_key,forecast_date,grid_geojson,hourly_grids',
        'forecast_date': f'gte.{start}',
        'forecast_date': f'lte.{end}',
        'order': 'forecast_date.asc',
    }
    if region_key:
        params['region_key'] = f'eq.{region_key}'
    return rest_get('forecast_grids', params=params)


def fetch_avalanche_events(start: str, end: str, region_key: str | None = None) -> list[dict[str, Any]]:
    """Fetch avalanche_events rows within the date range."""
    params: dict[str, str] = {
        'select': 'id,location,timestamp,severity,source,region_key',
        'timestamp': f'gte.{start}',
        'timestamp': f'lte.{end}',
        'order': 'timestamp.asc',
    }
    if region_key:
        params['region_key'] = f'eq.{region_key}'
    return rest_get('avalanche_events', params=params)


def extract_predictions(grids: list[dict[str, Any]]) -> pd.DataFrame:
    """Extract per-cell predictions from forecast grid GeoJSON.

    Returns DataFrame with columns: region_key, forecast_date, cell_id,
    probability, risk_level, lat, lng.
    """
    rows: list[dict[str, Any]] = []
    for grid in grids:
        region_key = grid.get('region_key', 'unknown')
        forecast_date = grid.get('forecast_date', '')
        geojson = grid.get('grid_geojson') or []
        hourly = grid.get('hourly_grids') or []
        for cell in geojson:
            props = cell.get('properties', cell) if isinstance(cell, dict) else {}
            lat = float(props.get('lat', props.get('latitude', 0)))
            lng = float(props.get('lng', props.get('longitude', props.get('lon', 0))))
            prob = float(props.get('probability', props.get('calibrated_probability', 0)))
            risk = int(props.get('risk_level', props.get('terrain_adjusted_risk_level', 0)))
            cell_id = props.get('cell_id', props.get('id', f'{lat:.4f}_{lng:.4f}'))
            rows.append({
                'region_key': region_key,
                'forecast_date': forecast_date,
                'cell_id': str(cell_id),
                'lat': lat,
                'lng': lng,
                'probability': prob,
                'risk_level': risk,
            })
    return pd.DataFrame(rows)


def label_predictions(
    predictions: pd.DataFrame,
    events: list[dict[str, Any]],
    match_radius_km: float = 15.0,
) -> pd.DataFrame:
    """Label predictions: 1 if an avalanche event occurred within match_radius_km.

    Uses haversine distance to match events to grid cells by date + location.
    """
    if predictions.empty:
        predictions['label'] = 0
        return predictions

    if not events:
        predictions['label'] = 0
        return predictions

    events_df = pd.DataFrame(events)
    if 'timestamp' not in events_df.columns:
        predictions['label'] = 0
        return predictions

    events_df['event_date'] = pd.to_datetime(events_df['timestamp'], utc=True, errors='coerce').dt.strftime('%Y-%m-%d')
    predictions['label'] = 0

    for _, event in events_df.iterrows():
        event_date = event.get('event_date')
        if not event_date:
            continue
        loc = event.get('location')
        if isinstance(loc, str) and loc.startswith('POINT'):
            parts = loc.replace('POINT(', '').replace(')', '').split()
            if len(parts) >= 2:
                event_lng, event_lat = float(parts[0]), float(parts[1])
            else:
                continue
        elif isinstance(loc, dict):
            coords = loc.get('coordinates', [0, 0])
            event_lng, event_lat = float(coords[0]), float(coords[1])
        else:
            continue

        same_date = predictions['forecast_date'] == event_date
        if not same_date.any():
            continue
        mask = same_date.values
        for idx in predictions.index[mask]:
            lat = predictions.at[idx, 'lat']
            lng = predictions.at[idx, 'lng']
            dist = _haversine_km(lat, lng, event_lat, event_lng)
            if dist <= match_radius_km:
                predictions.at[idx, 'label'] = 1

    return predictions


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in km."""
    r = 6371.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return float(r * 2 * np.arcsin(np.sqrt(a)))


def compute_metrics(y_true: np.ndarray, y_prob: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Compute evaluation metrics."""
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
    return {
        'n_predictions': int(len(y_true)),
        'n_positive': int(y_true.sum()),
        'n_negative': int((y_true == 0).sum()),
        'accuracy': float(accuracy_score(y_true, y_pred)),
        'f1': float(f1_score(y_true, y_pred, zero_division=0)),
        'precision': float(precision_score(y_true, y_pred, zero_division=0)),
        'recall': float(recall_score(y_true, y_pred, zero_division=0)),
        'brier_score': float(brier_score_loss(y_true, y_prob)),
        'roc_auc': float(roc_auc_score(y_true, y_prob)),
        'pss': float(pss),
        'pss_optimal_threshold': float(optimal_threshold),
        'pss_at_0p5': float(peirce_skill_score(y_true, y_pred)),
        'confusion_matrix': confusion_matrix(y_true, y_pred).tolist(),
    }


def evaluate(
    start: str,
    end: str,
    region_key: str | None = None,
    match_radius_km: float = 15.0,
) -> dict[str, Any]:
    """Run full evaluation: fetch grids + events, label, compute metrics."""
    if not has_supabase_credentials():
        return {'error': 'Supabase credentials not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.'}

    print(f'[evaluation] Fetching forecast grids: {start} to {end}' + (f' region={region_key}' if region_key else ''))
    grids = fetch_forecast_grids(start, end, region_key)
    if not grids:
        return {'error': 'No forecast grids found in date range', 'start': start, 'end': end}

    print(f'[evaluation] Found {len(grids)} forecast grid(s)')
    predictions = extract_predictions(grids)
    print(f'[evaluation] Extracted {len(predictions)} cell predictions')

    print(f'[evaluation] Fetching avalanche events: {start} to {end}')
    events = fetch_avalanche_events(start, end, region_key)
    print(f'[evaluation] Found {len(events)} avalanche event(s)')

    if not events:
        print('[evaluation] WARNING: No avalanche event labels found. Without labels, only pipeline '
              'outputs (predictions, features, maps, SHAP) can be demonstrated, not accuracy.',
              file=sys.stderr)

    predictions = label_predictions(predictions, events, match_radius_km=match_radius_km)

    y_true = predictions['label'].to_numpy()
    y_prob = predictions['probability'].to_numpy()
    y_pred = (y_prob >= 0.5).astype(int)

    metrics = compute_metrics(y_true, y_prob, y_pred)
    result = {
        'start': start,
        'end': end,
        'region_key': region_key,
        'match_radius_km': match_radius_km,
        'n_grids': len(grids),
        'n_events': len(events),
        'n_predictions': len(predictions),
        'metrics': metrics,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Evaluate avalanche forecast predictions against known events')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--region', default=None, help='Region key filter (e.g. pir_panjal)')
    parser.add_argument('--match-radius-km', type=float, default=15.0, help='Event-to-cell match radius in km')
    parser.add_argument('--output', default=None, help='Output JSON file path (default: stdout)')
    args = parser.parse_args(argv)

    start = _parse_date(args.start)
    end = _parse_date(args.end)
    result = evaluate(start, end, region_key=args.region, match_radius_km=args.match_radius_km)

    output = json.dumps(result, indent=2, default=str)
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f'[evaluation] Results written to {args.output}')
    else:
        print(output)

    return 0 if 'error' not in result else 1


if __name__ == '__main__':
    raise SystemExit(main())
