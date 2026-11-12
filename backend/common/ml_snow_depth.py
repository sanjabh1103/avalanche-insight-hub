"""ML snow depth estimation — XGBoost→RF fallback.

Trains on S1 backscatter + S2 NDSI + terrain features with Open-Meteo
snow depth as proxy labels. XGBoost is optional; falls back to
RandomForestRegressor (sklearn, already a dependency).

All predictions carry an honest `label_source='openmeteo_proxy'` tag.

Env flags:
  ML_SNOW_DEPTH_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

ML_SNOW_DEPTH_ENABLED = os.getenv('ML_SNOW_DEPTH_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

ML_DEPTH_FEATURES = [
    's1_vh_db', 's1_vv_db', 's1_cross_ratio',
    's2_ndsi', 's2_ndvi', 's2_evi',
    'elevation_m', 'slope_deg', 'aspect_deg', 'tpi',
]

LABEL_SOURCE = 'openmeteo_proxy'


@dataclass
class MLSnowDepthResult:
    """ML snow depth prediction result."""

    cell_id: str
    snow_depth_m: float | None = None
    uncertainty_m: float | None = None
    model_type: str = 'unknown'
    label_source: str = LABEL_SOURCE
    feature_values: dict[str, float | None] = field(default_factory=dict)
    source: str = 'ml_snow_depth'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'snow_depth_m': self.snow_depth_m,
            'uncertainty_m': self.uncertainty_m,
            'model_type': self.model_type,
            'label_source': self.label_source,
            'feature_values': self.feature_values,
            'source': self.source,
            'metadata': self.metadata,
        }


def build_feature_matrix(
    samples: list[dict[str, float | None]],
) -> tuple[np.ndarray, list[str]]:
    """Build feature matrix from sample dicts.

    Args:
        samples: List of dicts with ML_DEPTH_FEATURES keys.

    Returns:
        Tuple of (feature_matrix, feature_names).
    """
    features = []
    for sample in samples:
        row = []
        for feat in ML_DEPTH_FEATURES:
            val = sample.get(feat)
            row.append(float(val) if val is not None else 0.0)
        features.append(row)

    if not features:
        return np.empty((0, len(ML_DEPTH_FEATURES))), ML_DEPTH_FEATURES

    return np.array(features), ML_DEPTH_FEATURES


def train_depth_model(
    X: np.ndarray,
    y: np.ndarray,
    *,
    prefer_xgboost: bool = True,
) -> tuple[Any, str]:
    """Train a snow depth regression model.

    Tries XGBoost first (if installed), falls back to RandomForest.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target snow depths (n_samples,).
        prefer_xgboost: Try XGBoost before RF.

    Returns:
        Tuple of (trained_model, model_type).
    """
    if prefer_xgboost:
        try:
            from xgboost import XGBRegressor
            model = XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42,
            )
            model.fit(X, y)
            return model, 'xgboost'
        except ImportError:
            pass

    from sklearn.ensemble import RandomForestRegressor
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)
    return model, 'random_forest'


def predict_depth(
    model: Any,
    X: np.ndarray,
    *,
    model_type: str = 'unknown',
) -> np.ndarray:
    """Predict snow depth from feature matrix.

    Args:
        model: Trained regression model.
        X: Feature matrix.
        model_type: Model type for metadata.

    Returns:
        Array of predicted snow depths.
    """
    predictions = model.predict(X)
    return np.clip(predictions, 0.0, None)


def estimate_ml_snow_depth(
    *,
    cell_id: str,
    features: dict[str, float | None],
    model: Any | None = None,
    model_type: str = 'unknown',
) -> MLSnowDepthResult | None:
    """Estimate snow depth from ML model for a single cell.

    Returns None when ML_SNOW_DEPTH_ENABLED is false or no model provided.
    """
    if not ML_SNOW_DEPTH_ENABLED or model is None:
        return None

    X, feature_names = build_feature_matrix([features])
    predictions = predict_depth(model, X, model_type=model_type)

    return MLSnowDepthResult(
        cell_id=cell_id,
        snow_depth_m=float(predictions[0]),
        uncertainty_m=0.3,  # default uncertainty for proxy-label model
        model_type=model_type,
        feature_values={k: features.get(k) for k in ML_DEPTH_FEATURES},
    )
