#!/usr/bin/env python3
"""Demo: GNN runout dynamics with heuristic fallback.

Uses the existing GNNRunoutEngine from backend/models/gnn_runout.py.
When pre-trained GNN weights are unavailable, the engine falls back to
a kinematic heuristic model that computes velocity, depth, and pressure
fields from slope and avalanche probability.
"""
from __future__ import annotations

import sys
import math
import numpy as np

from backend.models.gnn_runout import (
    GNNRunoutConfig,
    DEMGraphConverter,
    GNNRunoutEngine,
    _heuristic_runout_fields,
)


def generate_synthetic_dem(size: int = 20, seed: int = 42) -> np.ndarray:
    """Generate a synthetic DEM with a mountain slope."""
    rng = np.random.RandomState(seed)
    x = np.linspace(0, 500, size)
    y = np.linspace(0, 500, size)
    xx, yy = np.meshgrid(x, y)
    elevation = 3000.0 - (yy / 500.0) * 800.0 + rng.randn(size, size) * 20.0
    return elevation.astype(np.float32)


class FakeTransform:
    """Minimal affine transform mimicking rasterio's Affine API.

    rasterio Affine has: a, b, c, d, e, f where:
      x = a*col + b*row + c  (lng = a*col + c)
      y = d*col + e*row + f  (lat = e*row + f)
    """
    def __init__(self, cell_size: float = 25.0, origin_x: float = 76.0, origin_y: float = 35.0):
        m_per_deg = 111320.0
        self.a = cell_size / m_per_deg  # lng per pixel
        self.b = 0.0
        self.c = origin_x               # origin lng
        self.d = 0.0
        self.e = -cell_size / m_per_deg  # lat per pixel (negative = north-up)
        self.f = origin_y                # origin lat


def main() -> int:
    print('=== GNN Runout Dynamics Demo (Heuristic Fallback) ===\n')

    dem = generate_synthetic_dem(size=20, seed=42)
    print(f'Generated synthetic DEM: shape={dem.shape}, range=[{dem.min():.0f}, {dem.max():.0f}]m')

    transform = FakeTransform(cell_size=25.0, origin_x=76.0, origin_y=35.0)
    config = GNNRunoutConfig.from_env()
    engine = GNNRunoutEngine(config)

    print(f'Engine initialized. Weights loaded: {engine._weights_loaded}')
    print(f'  (Using heuristic kinematic fallback)')

    # Convert DEM to graph
    graph = engine._converter.convert(
        dem, transform, lat=35.0, lng=76.0, snow_depth_proxy=0.5,
    )
    print(f'\nGraph: {graph.num_nodes} nodes, {graph.num_edges} edges')
    slopes = graph.node_features[:, 1]
    print(f'Slope range: [{slopes.min():.1f}, {slopes.max():.1f}] degrees')
    print(f'Mean slope: {slopes.mean():.1f} degrees')

    # Run heuristic for different probabilities
    for prob in [0.3, 0.6, 0.9]:
        print(f'\n--- Runout simulation with probability={prob} ---')
        result = _heuristic_runout_fields(graph, prob)
        print(f'  Method: {result.method}')
        print(f'  Velocity: max={result.velocity_field.max():.2f} m/s, mean={result.velocity_field.mean():.2f} m/s')
        print(f'  Depth:    max={result.depth_field.max():.2f} m, mean={result.depth_field.mean():.2f} m')
        print(f'  Pressure: max={result.pressure_field.max():.2f} kPa, mean={result.pressure_field.mean():.2f} kPa')
        print(f'  Polygon:  {len(result.polygon)} vertices')

    # Monotonicity check
    print('\n=== Monotonicity Check ===\n')
    velocities = []
    for prob in [0.2, 0.4, 0.6, 0.8, 1.0]:
        result = _heuristic_runout_fields(graph, prob)
        velocities.append((prob, result.velocity_field.max()))

    print('Probability -> Max velocity:')
    for prob, vel in velocities:
        print(f'  p={prob:.1f}: v_max={vel:.2f} m/s')

    v_increasing = all(velocities[i][1] <= velocities[i + 1][1] + 0.5 for i in range(len(velocities) - 1))
    if v_increasing:
        print('PASS: Velocity generally increases with probability')
    else:
        print('WARN: Velocity not strictly monotonic')

    # Runout polygon check
    result_high = _heuristic_runout_fields(graph, 0.9)
    if len(result_high.polygon) >= 3:
        print(f'PASS: Runout polygon has {len(result_high.polygon)} vertices')
    else:
        print(f'WARN: Runout polygon has {len(result_high.polygon)} vertices')

    # Physics sanity check
    print('\n=== Physics Sanity Check ===\n')
    result_check = _heuristic_runout_fields(graph, 0.8)
    v = result_check.velocity_field.max()
    p = result_check.pressure_field.max()
    expected_p = 200.0 * v ** 2 / 1000.0
    ratio = p / max(expected_p, 0.001)
    print(f'Max velocity: {v:.2f} m/s')
    print(f'Max pressure: {p:.2f} kPa')
    print(f'Expected (rho*v^2/1000): {expected_p:.2f} kPa')
    print(f'Ratio: {ratio:.2f}')
    if 0.5 < ratio < 2.0:
        print('PASS: Pressure in plausible range')
    else:
        print(f'WARN: Pressure ratio {ratio:.2f} outside 0.5-2.0')

    # Full engine compute_runout
    print('\n=== Full Engine compute_runout() ===\n')
    full_result = engine.compute_runout(
        dem, transform, lat=35.0, lng=76.0, probability=0.7,
    )
    if full_result is None:
        print('FAIL: compute_runout returned None')
        return 1
    print(f'Method: {full_result.method}')
    print(f'Velocity max: {full_result.velocity_field.max():.2f} m/s')
    print(f'Depth max: {full_result.depth_field.max():.2f} m')
    print(f'Pressure max: {full_result.pressure_field.max():.2f} kPa')
    print(f'Polygon vertices: {len(full_result.polygon)}')
    print('PASS: Full engine compute_runout succeeded')

    print('\n=== Demo Complete ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
