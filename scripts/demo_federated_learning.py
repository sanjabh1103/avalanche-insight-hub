#!/usr/bin/env python3
"""Demo: Federated Learning FedAvg aggregation with synthetic sector weights.

Generates 4 synthetic SectorWeights (north/south/east/west), runs
FederatedAggregator, prints aggregation results + outlier detection.
Then adds a 5th deliberately extreme sector to verify MAD outlier detection.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from backend.common.federated_learning import SectorWeights, FederatedAggregator, load_sector_weights_from_dir


def make_synthetic_sector(
    sector_id: str,
    sample_count: int,
    base_weights: dict[str, np.ndarray],
    noise_scale: float = 0.01,
) -> SectorWeights:
    """Create a synthetic sector with weights close to base + noise."""
    weights = {
        name: base + np.random.randn(*base.shape) * noise_scale
        for name, base in base_weights.items()
    }
    return SectorWeights(
        sector_id=sector_id,
        sample_count=sample_count,
        weights_dict=weights,
        training_metrics={'loss': 0.3 + np.random.rand() * 0.1, 'accuracy': 0.75 + np.random.rand() * 0.1},
    )


def main() -> int:
    np.random.seed(42)

    # Define base weights (simulating a small model)
    base_weights = {
        'layer1_w': np.random.randn(10, 8).astype(np.float64) * 0.1,
        'layer1_b': np.zeros(8, dtype=np.float64),
        'layer2_w': np.random.randn(8, 4).astype(np.float64) * 0.1,
        'layer2_b': np.zeros(4, dtype=np.float64),
    }

    # Create 4 normal sectors
    sectors = [
        make_synthetic_sector('north_sector', 150, base_weights, noise_scale=0.01),
        make_synthetic_sector('south_sector', 200, base_weights, noise_scale=0.01),
        make_synthetic_sector('east_sector', 180, base_weights, noise_scale=0.015),
        make_synthetic_sector('west_sector', 120, base_weights, noise_scale=0.012),
    ]

    print('=== Federated Learning Demo: FedAvg Aggregation ===\n')
    print(f'Created {len(sectors)} synthetic sectors:')
    for s in sectors:
        print(f'  {s.sector_id}: {s.sample_count} samples, {s.total_params} params, loss={s.training_metrics["loss"]:.3f}')

    # Test file-based export/import
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        for s in sectors:
            fpath = tmpdir_path / f'{s.sector_id}_weights.json'
            fpath.write_text(json.dumps(s.to_json(), indent=2), encoding='utf-8')

        # Load via aggregator
        loaded_sectors = load_sector_weights_from_dir(str(tmpdir_path))
        agg = FederatedAggregator(outlier_threshold_sigma=10.0)
        for s in loaded_sectors:
            agg.add_sector(s)
        print(f'\nLoaded {len(agg.sector_weights)} sector weight files from {tmpdir}')

        # Detect outliers (should be none)
        rejected = agg.detect_outliers()
        print(f'Outlier detection: {len(rejected)} rejected sectors: {rejected}')

        # Aggregate
        result = agg.aggregate()
        if result is None:
            print('ERROR: Aggregation returned None')
            return 1

        print(f'\nFedAvg aggregation result:')
        for name, arr in result.items():
            print(f'  {name}: shape={arr.shape}, mean={arr.mean():.6f}, std={arr.std():.6f}')

        # Verify weighted averaging: check that result is close to base
        for name, base in base_weights.items():
            diff = np.abs(result[name] - base).max()
            print(f'  {name}: max diff from base = {diff:.6f}')

    # Now test outlier detection with an extreme 5th sector
    print('\n=== Outlier Detection Test ===\n')
    extreme_sector = make_synthetic_sector('rogue_sector', 50, base_weights, noise_scale=5.0)
    print(f'Added rogue sector with 5.0 noise scale (extreme weights)')

    agg2 = FederatedAggregator(outlier_threshold_sigma=10.0)
    for s in sectors:
        agg2.add_sector(s)
    agg2.add_sector(extreme_sector)

    rejected2 = agg2.detect_outliers()
    print(f'Outlier detection: {len(rejected2)} rejected sectors: {rejected2}')
    if 'rogue_sector' in rejected2:
        print('PASS: Rogue sector correctly detected as outlier')
    else:
        print('FAIL: Rogue sector was NOT detected as outlier')
        return 1

    # Aggregate without the rogue
    result2 = agg2.aggregate()
    if result2 is not None:
        print(f'\nFedAvg after outlier removal: {len(result2)} parameter arrays')
        print('PASS: Aggregation succeeded after removing outlier')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
