"""Direct-vs-GP probability-map comparison kept outside active inference."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


SHADOW_PROBABILITY_MAP_VERSION = 'shadow_probability_map_v1'


def _as_points(points: Sequence[Sequence[float]], *, name: str) -> np.ndarray:
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 2 or array.shape[0] == 0:
        raise ValueError(f'{name} must contain at least one (x, y) point')
    if not np.isfinite(array).all():
        raise ValueError(f'{name} contains non-finite coordinates')
    return array


def _as_probabilities(values: Sequence[float], expected: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) != expected or not np.isfinite(array).all():
        raise ValueError('anchor_probabilities must match anchor_points and be finite')
    return np.clip(array, 0.0, 1.0)


def _direct_probability_map(
    anchors: np.ndarray,
    probabilities: np.ndarray,
    queries: np.ndarray,
    *,
    power: float,
) -> np.ndarray:
    if power <= 0:
        raise ValueError('inverse-distance power must be positive')
    output: list[float] = []
    for query in queries:
        distances = np.linalg.norm(anchors - query, axis=1)
        exact = np.flatnonzero(distances <= 1e-12)
        if len(exact):
            output.append(float(probabilities[exact[0]]))
            continue
        weights = 1.0 / np.maximum(distances, 1e-12) ** power
        output.append(float(np.dot(weights, probabilities) / weights.sum()))
    return np.asarray(output, dtype=float)


def compare_probability_maps(
    *,
    anchor_points: Sequence[Sequence[float]],
    anchor_probabilities: Sequence[float],
    query_points: Sequence[Sequence[float]],
    inverse_distance_power: float = 2.0,
) -> dict[str, Any]:
    """Compare direct inverse-distance values with a non-authoritative GP.

    The direct map is the reference output.  GP interpolation is deliberately
    returned as a shadow diagnostic with uncertainty and error metrics; this
    function has no call path from daily inference or publication.
    """
    anchors = _as_points(anchor_points, name='anchor_points')
    queries = _as_points(query_points, name='query_points')
    probabilities = _as_probabilities(anchor_probabilities, len(anchors))
    direct = _direct_probability_map(
        anchors,
        probabilities,
        queries,
        power=inverse_distance_power,
    )

    result: dict[str, Any] = {
        'version': SHADOW_PROBABILITY_MAP_VERSION,
        'shadow_only': True,
        'reference_method': 'inverse_distance',
        'direct_probabilities': [float(value) for value in direct],
        'gp_status': 'unavailable',
        'gp_probabilities': None,
        'gp_std': None,
        'comparison_metrics': {},
        'anchor_count': int(len(anchors)),
        'query_count': int(len(queries)),
    }
    try:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel

        kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=0.05)
        model = GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=True,
            optimizer=None,
            random_state=42,
        )
        model.fit(anchors, probabilities)
        gp_values, gp_std = model.predict(queries, return_std=True)
        gp_values = np.clip(np.asarray(gp_values, dtype=float), 0.0, 1.0)
        gp_std = np.maximum(np.asarray(gp_std, dtype=float), 0.0)
        difference = gp_values - direct
        result.update({
            'gp_status': 'computed',
            'gp_probabilities': [float(value) for value in gp_values],
            'gp_std': [float(value) for value in gp_std],
            'comparison_metrics': {
                'mae': float(np.mean(np.abs(difference))),
                'rmse': float(np.sqrt(np.mean(difference ** 2))),
                'max_abs_difference': float(np.max(np.abs(difference))),
            },
        })
    except Exception as exc:  # pragma: no cover - depends on optional sklearn runtime
        result['gp_error_type'] = type(exc).__name__
    return result
