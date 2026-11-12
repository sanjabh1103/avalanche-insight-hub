"""Shared utility helpers for the inference pipeline."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.common.supabase_io import fetch_latest_model_status_row, has_supabase_credentials, rest_get
from backend.common.vae_anomaly import VAE_ANOMALY_ENABLED, detect_vae_anomaly


def _is_truthy_env(name: str) -> bool:
    value = str(os.getenv(name) or '').strip().lower()
    return value in ('1', 'true', 'yes', 'on')


def _dem_root() -> Path:
    """Return the root directory for DEM terrain tiles."""
    raw = os.getenv('DEM_ROOT')
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / 'data' / 'dem'


def _dem_path(region_key: str) -> Path:
    """Return the DEM tile path for a given region."""
    return _dem_root() / f'{region_key}.tif'


def _default_inference_backend(bundle: dict[str, object]) -> str:
    """Select the inference backend for the bundle."""
    lstm_head = bundle.get('lstm_head') if isinstance(bundle, dict) else None
    if getattr(lstm_head, 'model', None) is not None:
        return 'github_actions_mts_lstm'
    return 'github_actions_surrogate_rf'


def _fetch_current_model_status() -> dict[str, object] | None:
    """Fetch the current active model status from Supabase."""
    if not has_supabase_credentials():
        return None
    try:
        return fetch_latest_model_status_row()
    except Exception:
        return None


def _runout_method_counts(runout_polygons: list[dict[str, object]]) -> dict[str, int]:
    """Count runout polygon generation methods."""
    counts: dict[str, int] = {}
    for polygon in runout_polygons:
        method = polygon.get('method') or 'unknown'
        counts[method] = counts.get(method, 0) + 1
    return counts

