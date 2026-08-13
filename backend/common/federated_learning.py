"""Federated Learning: Cross-Sector Model Training Framework.

Enables training across multiple Partner sectors without centralizing data.
Each sector trains locally and shares model weight updates (not raw data).
The central aggregator averages weights with sample-count weighting.

Communication is file-based (JSON weight export/import) — no real-time
networking needed. Sectors export weight files, aggregator imports and
averages them.

Env flags:
  FEDERATED_MODE — enable federated export in train_model.py (default: false)
  FEDERATED_WEIGHTS_DIR — directory for sector weight files (default: ./federated_weights)
"""
from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

FEDERATED_MODE = os.getenv('FEDERATED_MODE', 'false').lower() not in {'0', 'false', 'off', 'no'}
FEDERATED_WEIGHTS_DIR = os.getenv('FEDERATED_WEIGHTS_DIR', 'federated_weights')


@dataclass
class SectorWeights:
    """Model weights from a single sector's local training.

    Attributes:
        sector_id: Identifier for the Partner sector
        sample_count: Number of training samples used (for weighted averaging)
        weights_dict: Mapping of parameter name to numpy array
        training_metrics: Optional metrics (loss, accuracy, etc.)
        timestamp: When weights were exported
        model_version: Optional model version string
    """
    sector_id: str
    sample_count: int
    weights_dict: dict[str, np.ndarray]
    training_metrics: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: str = 'v1'

    @property
    def total_params(self) -> int:
        """Total number of parameters across all weight arrays."""
        return sum(w.size for w in self.weights_dict.values())

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict.

        Numpy arrays are converted to nested lists with shape metadata.
        """
        return {
            'sector_id': self.sector_id,
            'sample_count': self.sample_count,
            'weights': {
                name: {
                    'data': w.tolist(),
                    'shape': list(w.shape),
                    'dtype': str(w.dtype),
                }
                for name, w in self.weights_dict.items()
            },
            'training_metrics': self.training_metrics,
            'timestamp': self.timestamp.isoformat(),
            'model_version': self.model_version,
            'total_params': self.total_params,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SectorWeights:
        """Deserialize from JSON dict.

        Args:
            data: JSON-compatible dict from to_json()

        Returns:
            SectorWeights instance
        """
        weights_dict: dict[str, np.ndarray] = {}
        for name, w_data in data.get('weights', {}).items():
            arr = np.array(w_data['data'], dtype=np.dtype(w_data.get('dtype', 'float32')))
            arr = arr.reshape(w_data['shape'])
            weights_dict[name] = arr

        ts_raw = data.get('timestamp', '')
        try:
            timestamp = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)

        return cls(
            sector_id=data['sector_id'],
            sample_count=int(data['sample_count']),
            weights_dict=weights_dict,
            training_metrics=data.get('training_metrics', {}),
            timestamp=timestamp,
            model_version=data.get('model_version', 'v1'),
        )

    def save_to_file(self, path: str | Path) -> None:
        """Save weights to a JSON file.

        Args:
            path: Output file path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_json(), f, indent=2)
        logger.info('Saved sector weights to %s', path)

    @classmethod
    def load_from_file(cls, path: str | Path) -> SectorWeights:
        """Load weights from a JSON file.

        Args:
            path: Input file path

        Returns:
            SectorWeights instance
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_json(data)


def export_model_weights(
    model: Any,
    *,
    sector_id: str,
    sample_count: int,
    training_metrics: dict[str, float] | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    """Export a trained model's weights for federated aggregation.

    Supports scikit-learn models (joblib/pickle) and models with
    `get_params()` or `coef_`/`intercept_` attributes.

    Args:
        model: Trained model object
        sector_id: Sector identifier
        sample_count: Number of training samples
        training_metrics: Optional metrics dict
        output_dir: Output directory (defaults to FEDERATED_WEIGHTS_DIR)

    Returns:
        Path to saved JSON file
    """
    out_dir = Path(output_dir or FEDERATED_WEIGHTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    weights_dict: dict[str, np.ndarray] = {}

    # Try scikit-learn style attributes
    if hasattr(model, 'coef_'):
        weights_dict['coef_'] = np.asarray(model.coef_, dtype=np.float32)
    if hasattr(model, 'intercept_'):
        weights_dict['intercept_'] = np.asarray(model.intercept_, dtype=np.float32)
    if hasattr(model, 'feature_importances_'):
        weights_dict['feature_importances_'] = np.asarray(model.feature_importances_, dtype=np.float32)
    if hasattr(model, 'classes_'):
        weights_dict['classes_'] = np.asarray(model.classes_)

    # Try PyTorch-style state_dict
    if hasattr(model, 'state_dict'):
        for name, param in model.state_dict().items():
            weights_dict[name] = np.asarray(param.cpu().numpy(), dtype=np.float32)

    # Try get_params (sklearn Pipeline, etc.)
    if not weights_dict and hasattr(model, 'get_params'):
        params = model.get_params()
        for name, val in params.items():
            if isinstance(val, (int, float)):
                weights_dict[name] = np.array([val], dtype=np.float32)

    if not weights_dict:
        logger.warning('No extractable weights from model type %s', type(model).__name__)

    sector_weights = SectorWeights(
        sector_id=sector_id,
        sample_count=sample_count,
        weights_dict=weights_dict,
        training_metrics=training_metrics or {},
    )

    filename = f'{sector_id}_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
    filepath = out_dir / filename
    sector_weights.save_to_file(filepath)
    return filepath


def load_sector_weights_from_dir(weights_dir: str | Path | None = None) -> list[SectorWeights]:
    """Load all sector weight files from a directory.

    Args:
        weights_dir: Directory containing JSON weight files

    Returns:
        List of SectorWeights loaded from all .json files
    """
    directory = Path(weights_dir or FEDERATED_WEIGHTS_DIR)
    if not directory.exists():
        return []

    weights: list[SectorWeights] = []
    for json_path in sorted(directory.glob('*.json')):
        try:
            sw = SectorWeights.load_from_file(json_path)
            weights.append(sw)
            logger.info('Loaded sector weights from %s (sector=%s, samples=%d)',
                        json_path, sw.sector_id, sw.sample_count)
        except Exception as exc:
            logger.warning('Failed to load %s: %s', json_path, exc)

    return weights


def validate_sector_weights(
    sector_weights: SectorWeights,
    *,
    reference_keys: list[str] | None = None,
    reference_shapes: dict[str, tuple[int, ...]] | None = None,
) -> tuple[bool, str]:
    """Validate that sector weights are well-formed and match expected shapes.

    Args:
        sector_weights: Weights to validate
        reference_keys: Expected parameter names
        reference_shapes: Expected parameter shapes

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not sector_weights.weights_dict:
        return False, 'Empty weights dict'

    if sector_weights.sample_count <= 0:
        return False, f'Invalid sample_count: {sector_weights.sample_count}'

    if reference_keys is not None:
        missing = set(reference_keys) - set(sector_weights.weights_dict.keys())
        if missing:
            return False, f'Missing parameters: {missing}'

    if reference_shapes is not None:
        for name, expected_shape in reference_shapes.items():
            if name in sector_weights.weights_dict:
                actual_shape = sector_weights.weights_dict[name].shape
                if actual_shape != tuple(expected_shape):
                    return False, (
                        f'Shape mismatch for {name}: expected {expected_shape}, '
                        f'got {actual_shape}'
                    )

    return True, ''


class FederatedAggregator:
    """Manages federated weight aggregation across multiple sectors.

    Loads sector weight files, validates them, detects outliers,
    and produces aggregated weights via FedAvg.
    """

    def __init__(
        self,
        *,
        weights_dir: str | Path | None = None,
        outlier_threshold_sigma: float = 3.0,
    ) -> None:
        self.weights_dir = weights_dir or FEDERATED_WEIGHTS_DIR
        self.outlier_threshold_sigma = outlier_threshold_sigma
        self.sector_weights: list[SectorWeights] = []
        self.rejected_sectors: list[tuple[str, str]] = []

    def load_sectors(self) -> list[SectorWeights]:
        """Load all sector weight files from the weights directory."""
        self.sector_weights = load_sector_weights_from_dir(self.weights_dir)
        return self.sector_weights

    def add_sector(self, sector_weights: SectorWeights) -> None:
        """Manually add sector weights without loading from file."""
        self.sector_weights.append(sector_weights)

    def detect_outliers(self) -> list[str]:
        """Detect and mark sectors with extreme weight divergence.

        Uses Median Absolute Deviation (MAD) for robust outlier detection.
        MAD is resistant to the outlier itself inflating the scale, unlike
        standard deviation. Sectors with any parameter exceeding
        outlier_threshold_sigma scaled MADs from the median are flagged.

        Returns:
            List of rejected sector IDs
        """
        if len(self.sector_weights) < 3:
            # Need at least 3 sectors for meaningful outlier detection
            return []

        rejected: list[str] = []
        self.rejected_sectors.clear()

        # Get common parameter names
        common_keys = set(self.sector_weights[0].weights_dict.keys())
        for sw in self.sector_weights[1:]:
            common_keys &= set(sw.weights_dict.keys())

        for sector in self.sector_weights:
            is_outlier = False
            reasons: list[str] = []

            for key in common_keys:
                all_values = [sw.weights_dict[key].flatten() for sw in self.sector_weights]
                stacked = np.stack(all_values)

                sector_vals = sector.weights_dict[key].flatten()
                median = np.median(stacked, axis=0)
                # MAD: Median Absolute Deviation
                mad = np.median(np.abs(stacked - median), axis=0)
                # Scale MAD to approximate std: 1.4826 * MAD
                mad_scaled = 1.4826 * mad
                # Avoid division by zero
                mad_safe = np.where(mad_scaled < 1e-10, 1.0, mad_scaled)
                z_scores = np.abs((sector_vals - median) / mad_safe)

                if np.any(z_scores > self.outlier_threshold_sigma):
                    is_outlier = True
                    reasons.append(f'{key}: max MAD z-score {z_scores.max():.2f}')

            if is_outlier:
                rejected.append(sector.sector_id)
                self.rejected_sectors.append((sector.sector_id, '; '.join(reasons)))

        return rejected

    def get_valid_sectors(self) -> list[SectorWeights]:
        """Get sector weights excluding outliers."""
        rejected_ids = set(sid for sid, _ in self.rejected_sectors)
        return [sw for sw in self.sector_weights if sw.sector_id not in rejected_ids]

    def aggregate(self) -> dict[str, np.ndarray] | None:
        """Aggregate weights from all valid sectors using FedAvg.

        Returns:
            Aggregated weights dict, or None if no valid sectors
        """
        from backend.common.fed_avg import fed_avg

        valid = self.get_valid_sectors()
        if not valid:
            logger.warning('No valid sectors to aggregate')
            return None

        return fed_avg(valid)

    def get_status(self) -> dict[str, Any]:
        """Get aggregator status."""
        valid = self.get_valid_sectors()
        return {
            'weights_dir': str(self.weights_dir),
            'total_sectors': len(self.sector_weights),
            'valid_sectors': len(valid),
            'rejected_sectors': len(self.rejected_sectors),
            'rejection_details': [
                {'sector_id': sid, 'reason': reason}
                for sid, reason in self.rejected_sectors
            ],
            'outlier_threshold_sigma': self.outlier_threshold_sigma,
        }
