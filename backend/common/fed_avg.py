"""FedAvg: Federated Averaging Implementation.

Weighted average of sector model weights, weighted by sample count.
Implements the FedAvg algorithm from McMahan et al. (2017):
"Communication-Efficient Learning of Deep Networks from Decentralized Data"
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from backend.common.federated_learning import SectorWeights

logger = logging.getLogger(__name__)


def fed_avg(sector_weights: list[SectorWeights]) -> dict[str, np.ndarray] | None:
    """Compute FedAvg: weighted average of sector weights.

    Weights are averaged parameter-wise, weighted by each sector's
    sample_count. Only parameters present in ALL sectors are averaged.

    Args:
        sector_weights: List of SectorWeights from different sectors

    Returns:
        Dict of averaged parameter name -> numpy array, or None if empty
    """
    if not sector_weights:
        return None

    if len(sector_weights) == 1:
        # Only one sector — return its weights directly
        logger.info('FedAvg: only one sector, returning weights as-is')
        return dict(sector_weights[0].weights_dict)

    # Find common parameter names across all sectors
    common_keys = set(sector_weights[0].weights_dict.keys())
    for sw in sector_weights[1:]:
        common_keys &= set(sw.weights_dict.keys())

    if not common_keys:
        logger.warning('FedAvg: no common parameters across sectors')
        return None

    # Total samples for weighting
    total_samples = sum(sw.sample_count for sw in sector_weights)
    if total_samples <= 0:
        # Equal weighting fallback
        total_samples = len(sector_weights)
        weights = [1.0 / len(sector_weights)] * len(sector_weights)
    else:
        weights = [sw.sample_count / total_samples for sw in sector_weights]

    logger.info(
        'FedAvg: aggregating %d sectors, %d common params, total_samples=%d',
        len(sector_weights), len(common_keys), total_samples,
    )

    aggregated: dict[str, np.ndarray] = {}

    for key in common_keys:
        # Stack all sector values for this parameter
        arrays = [sw.weights_dict[key] for sw in sector_weights]

        # Verify shapes match
        ref_shape = arrays[0].shape
        shapes_match = all(a.shape == ref_shape for a in arrays)
        if not shapes_match:
            logger.warning('FedAvg: shape mismatch for %s, skipping', key)
            continue

        # Weighted average
        stacked = np.stack(arrays).astype(np.float64)
        weighted_sum = np.zeros_like(stacked[0], dtype=np.float64)
        for i, w in enumerate(weights):
            weighted_sum += stacked[i] * w

        aggregated[key] = weighted_sum.astype(np.float32)

    logger.info('FedAvg: aggregated %d parameters', len(aggregated))
    return aggregated


def fed_avg_with_rejection(
    sector_weights: list[SectorWeights],
    *,
    outlier_threshold_sigma: float = 3.0,
) -> dict[str, np.ndarray] | None:
    """FedAvg with outlier rejection before averaging.

    Sectors with weights diverging more than threshold_sigma standard
    deviations from the median are excluded from the average.

    Args:
        sector_weights: List of sector weights
        outlier_threshold_sigma: Z-score threshold for outlier rejection

    Returns:
        Aggregated weights dict, or None if no valid sectors
    """
    if len(sector_weights) < 3:
        # Not enough for outlier detection — use plain FedAvg
        return fed_avg(sector_weights)

    # Find common keys
    common_keys = set(sector_weights[0].weights_dict.keys())
    for sw in sector_weights[1:]:
        common_keys &= set(sw.weights_dict.keys())

    # Detect outliers using MAD (Median Absolute Deviation)
    rejected_ids: set[str] = set()
    for sector in sector_weights:
        for key in common_keys:
            all_vals = [sw.weights_dict[key].flatten() for sw in sector_weights]
            stacked = np.stack(all_vals)
            sector_vals = sector.weights_dict[key].flatten()
            median = np.median(stacked, axis=0)
            mad = np.median(np.abs(stacked - median), axis=0)
            mad_scaled = 1.4826 * mad
            mad_safe = np.where(mad_scaled < 1e-10, 1.0, mad_scaled)
            z_scores = np.abs((sector_vals - median) / mad_safe)
            if np.any(z_scores > outlier_threshold_sigma):
                rejected_ids.add(sector.sector_id)
                break

    if rejected_ids:
        logger.info('FedAvg: rejecting %d outlier sectors: %s', len(rejected_ids), rejected_ids)

    valid = [sw for sw in sector_weights if sw.sector_id not in rejected_ids]
    if not valid:
        logger.warning('FedAvg: all sectors rejected as outliers, using all')
        valid = sector_weights

    return fed_avg(valid)


def compute_weight_divergence(
    weights_a: dict[str, np.ndarray],
    weights_b: dict[str, np.ndarray],
) -> dict[str, float]:
    """Compute per-parameter divergence between two weight dicts.

    Useful for measuring how much a sector's weights differ from
    the aggregated average.

    Args:
        weights_a: First weight dict
        weights_b: Second weight dict

    Returns:
        Dict of parameter name -> L2 norm of difference
    """
    common_keys = set(weights_a.keys()) & set(weights_b.keys())
    divergence: dict[str, float] = {}

    for key in common_keys:
        a = weights_a[key].astype(np.float64)
        b = weights_b[key].astype(np.float64)
        if a.shape == b.shape:
            diff = np.linalg.norm(a - b)
            norm = max(np.linalg.norm(a), 1e-10)
            divergence[key] = float(diff / norm)  # Normalized divergence

    return divergence


def apply_aggregated_weights(
    model: Any,
    aggregated_weights: dict[str, np.ndarray],
) -> None:
    """Apply aggregated weights to a model in-place.

    Supports scikit-learn models (coef_, intercept_) and PyTorch models
    (state_dict / load_state_dict).

    Args:
        model: Model to update
        aggregated_weights: Aggregated weight dict from fed_avg
    """
    # PyTorch-style
    if hasattr(model, 'load_state_dict'):
        import torch
        state_dict = {}
        for name, arr in aggregated_weights.items():
            state_dict[name] = torch.from_numpy(arr)
        model.load_state_dict(state_dict, strict=False)
        logger.info('Applied aggregated weights via load_state_dict')
        return

    # Scikit-learn style
    if hasattr(model, 'coef_') and 'coef_' in aggregated_weights:
        model.coef_ = aggregated_weights['coef_']
    if hasattr(model, 'intercept_') and 'intercept_' in aggregated_weights:
        model.intercept_ = aggregated_weights['intercept_']
    if hasattr(model, 'feature_importances_') and 'feature_importances_' in aggregated_weights:
        model.feature_importances_ = aggregated_weights['feature_importances_']
        logger.info('Applied aggregated weights via attribute assignment')
