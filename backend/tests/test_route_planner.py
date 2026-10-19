"""Tests for F10: Safe-Route Re-Computation Engine."""
from __future__ import annotations

import unittest

from backend.common.route_planner import (
    GridCell,
    RouteStep,
    SafeRoute,
    assess_route_safety,
    build_adjacency,
    cells_from_grid,
    compute_safe_route,
    compute_safe_routes_batch,
)


def _make_grid(grid_size: int = 5, risk_map: dict[tuple[int, int], float] | None = None) -> list[dict]:
    """Build a test grid with optional risk assignments."""
    risk_map = risk_map or {}
    cells = []
    for row in range(grid_size):
        for col in range(grid_size):
            cells.append({
                'row': row,
                'col': col,
                'lat': 32.0 + row * 0.1,
                'lng': 77.0 + col * 0.1,
                'risk_score': risk_map.get((row, col), 0.0),
                'composite_risk_level': int(risk_map.get((row, col), 0.0)),
                'dominant_hazard': 'avalanche',
            })
    return cells


class CellsFromGridTests(unittest.TestCase):
    def test_converts_raw_dicts_to_grid_cells(self) -> None:
        raw = [
            {'row': 0, 'col': 1, 'lat': 32.0, 'lng': 77.1, 'risk_score': 2.5, 'composite_risk_level': 2},
            {'row': 1, 'col': 0, 'lat': 32.1, 'lng': 77.0, 'risk_score': 4.0, 'composite_risk_level': 4},
        ]
        cells = cells_from_grid(raw)
        self.assertEqual(len(cells), 2)
        self.assertIsInstance(cells[0], GridCell)
        self.assertEqual(cells[0].row, 0)
        self.assertEqual(cells[0].col, 1)
        self.assertEqual(cells[0].risk_score, 2.5)
        self.assertEqual(cells[0].cell_id, 'r0c1')

    def test_handles_missing_risk_keys_with_defaults(self) -> None:
        raw = [{'row': 0, 'col': 0, 'lat': 32.0, 'lng': 77.0}]
        cells = cells_from_grid(raw)
        self.assertEqual(cells[0].risk_score, 0.0)
        self.assertEqual(cells[0].risk_level, 0)
        self.assertEqual(cells[0].hazard_type, 'avalanche')

    def test_uses_composite_risk_fallback(self) -> None:
        raw = [{'row': 0, 'col': 0, 'lat': 32.0, 'lng': 77.0, 'composite_risk': 3.2}]
        cells = cells_from_grid(raw)
        self.assertAlmostEqual(cells[0].risk_score, 3.2)


class BuildAdjacencyTests(unittest.TestCase):
    def test_4_directional_adjacency(self) -> None:
        cells = cells_from_grid(_make_grid(3))
        adj = build_adjacency(cells, 3, allow_diagonal=False)
        # Corner cell r0c0 should have 2 neighbors (right and down)
        self.assertEqual(len(adj['r0c0']), 2)
        # Center cell r1c1 should have 4 neighbors
        self.assertEqual(len(adj['r1c1']), 4)

    def test_8_directional_adjacency(self) -> None:
        cells = cells_from_grid(_make_grid(3))
        adj = build_adjacency(cells, 3, allow_diagonal=True)
        # Corner cell r0c0 should have 3 neighbors (right, down, diagonal)
        self.assertEqual(len(adj['r0c0']), 3)
        # Center cell r1c1 should have 8 neighbors
        self.assertEqual(len(adj['r1c1']), 8)

    def test_edge_weight_includes_risk(self) -> None:
        cells = cells_from_grid(_make_grid(2, risk_map={(0, 1): 4.0}))
        adj = build_adjacency(cells, 2, allow_diagonal=False)
        # Edge from r0c0 to r0c1 should have weight = 1.0 * (1 + 4.0) = 5.0
        neighbors = dict(adj['r0c0'])
        self.assertIn('r0c1', neighbors)
        self.assertAlmostEqual(neighbors['r0c1'], 5.0)


class ComputeSafeRouteTests(unittest.TestCase):
    def test_straight_line_path_on_clear_grid(self) -> None:
        cells = _make_grid(5)
        route = compute_safe_route(cells, 5, (0, 0), (0, 4))
        self.assertEqual(route.status, 'ok')
        self.assertEqual(route.step_count, 5)
        self.assertEqual(route.start_cell, 'r0c0')
        self.assertEqual(route.end_cell, 'r0c4')
        self.assertEqual(route.steps[0].row, 0)
        self.assertEqual(route.steps[0].col, 0)
        self.assertEqual(route.steps[-1].row, 0)
        self.assertEqual(route.steps[-1].col, 4)

    def test_routes_around_blocked_cells(self) -> None:
        # Block the middle row (row 2) except first column
        risk_map = {(2, c): 5.0 for c in range(1, 5)}
        cells = _make_grid(5, risk_map=risk_map)
        route = compute_safe_route(cells, 5, (0, 2), (4, 2), risk_threshold=3.5)
        self.assertEqual(route.status, 'ok')
        # Route should avoid row 2 cols 1-4
        for step in route.steps:
            if step.row == 2:
                self.assertEqual(step.col, 0, f'Route should not enter blocked cell r2c{step.col}')

    def test_returns_blocked_when_start_is_blocked(self) -> None:
        cells = _make_grid(3, risk_map={(0, 0): 5.0})
        route = compute_safe_route(cells, 3, (0, 0), (2, 2))
        self.assertEqual(route.status, 'blocked')
        self.assertEqual(route.step_count, 0)

    def test_returns_blocked_when_end_is_blocked(self) -> None:
        cells = _make_grid(3, risk_map={(2, 2): 5.0})
        route = compute_safe_route(cells, 3, (0, 0), (2, 2))
        self.assertEqual(route.status, 'blocked')
        self.assertEqual(route.step_count, 0)

    def test_returns_no_path_when_surrounded_by_blocked(self) -> None:
        # Block all neighbors of center cell
        risk_map = {(0, 0): 5.0, (0, 1): 5.0, (0, 2): 5.0,
                    (1, 0): 5.0, (1, 2): 5.0,
                    (2, 0): 5.0, (2, 1): 5.0, (2, 2): 5.0}
        cells = _make_grid(3, risk_map=risk_map)
        route = compute_safe_route(cells, 3, (1, 1), (0, 0), risk_threshold=3.5)
        # Start is not blocked but all paths out are
        self.assertIn(route.status, ('no_path', 'blocked'))

    def test_diagonal_path_is_shorter_than_orthogonal(self) -> None:
        cells = _make_grid(5)
        route_diag = compute_safe_route(cells, 5, (0, 0), (4, 4), allow_diagonal=True)
        route_ortho = compute_safe_route(cells, 5, (0, 0), (4, 4), allow_diagonal=False)
        self.assertEqual(route_diag.status, 'ok')
        self.assertEqual(route_ortho.status, 'ok')
        # Diagonal path should have fewer steps (5 vs 9)
        self.assertLess(route_diag.step_count, route_ortho.step_count)

    def test_route_avoids_high_risk_cells_when_possible(self) -> None:
        # Create a grid where the direct path goes through high-risk cells
        # but a longer detour goes through low-risk cells
        risk_map = {(0, 1): 4.0, (0, 2): 4.0, (0, 3): 4.0}
        cells = _make_grid(5, risk_map=risk_map)
        route = compute_safe_route(cells, 5, (0, 0), (0, 4), risk_threshold=3.5)
        self.assertEqual(route.status, 'ok')
        # Route should go around the blocked row 0 cells
        for step in route.steps:
            if step.row == 0 and 1 <= step.col <= 3:
                self.fail(f'Route entered high-risk cell r0c{step.col}')

    def test_to_dict_serialization(self) -> None:
        cells = _make_grid(3)
        route = compute_safe_route(cells, 3, (0, 0), (2, 2))
        d = route.to_dict()
        self.assertEqual(d['status'], 'ok')
        self.assertEqual(d['start_cell'], 'r0c0')
        self.assertEqual(d['end_cell'], 'r2c2')
        self.assertEqual(d['grid_size'], 3)
        self.assertEqual(d['algorithm'], 'dijkstra')
        self.assertIn('steps', d)
        self.assertIn('total_cost', d)
        self.assertIn('max_risk', d)
        self.assertIn('avg_risk', d)

    def test_max_and_avg_risk_properties(self) -> None:
        risk_map = {(0, 0): 1.0, (0, 1): 2.0, (0, 2): 1.5}
        cells = _make_grid(3, risk_map=risk_map)
        route = compute_safe_route(cells, 3, (0, 0), (0, 2), allow_diagonal=False)
        self.assertEqual(route.status, 'ok')
        self.assertGreater(route.max_risk_along_route, 0)
        self.assertGreater(route.avg_risk_along_route, 0)


class ComputeSafeRoutesBatchTests(unittest.TestCase):
    def test_batch_computes_multiple_routes(self) -> None:
        cells = _make_grid(5)
        requests = [
            {'start': [0, 0], 'end': [4, 4]},
            {'start': [0, 4], 'end': [4, 0]},
        ]
        routes = compute_safe_routes_batch(cells, 5, requests)
        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0].status, 'ok')
        self.assertEqual(routes[1].status, 'ok')
        self.assertEqual(routes[0].start_cell, 'r0c0')
        self.assertEqual(routes[1].start_cell, 'r0c4')


class AssessRouteSafetyTests(unittest.TestCase):
    def test_safe_route_assessment(self) -> None:
        cells = _make_grid(3, risk_map={(0, 0): 1.0, (0, 1): 1.5, (0, 2): 2.0})
        route = compute_safe_route(cells, 3, (0, 0), (0, 2), allow_diagonal=False)
        assessment = assess_route_safety(route, risk_threshold=3.5)
        self.assertTrue(assessment['is_safe'])
        self.assertEqual(assessment['dangerous_steps'], 0)
        self.assertEqual(assessment['route_status'], 'ok')

    def test_unsafe_route_assessment(self) -> None:
        # Create a 1x3 corridor where the middle cell has risk 3.8 (above 3.5 threshold)
        # but the only path goes through it (surrounded by blocked cells)
        cells = _make_grid(3, risk_map={
            (0, 0): 1.0, (0, 1): 3.8, (0, 2): 2.0,
            (1, 0): 5.0, (1, 1): 5.0, (1, 2): 5.0,
            (2, 0): 5.0, (2, 1): 5.0, (2, 2): 5.0,
        })
        # Use threshold 5.0 so the 3.8 cell is passable
        route = compute_safe_route(cells, 3, (0, 0), (0, 2), allow_diagonal=False, risk_threshold=5.0)
        self.assertEqual(route.status, 'ok')
        assessment = assess_route_safety(route, risk_threshold=3.5)
        self.assertFalse(assessment['is_safe'])
        self.assertGreater(assessment['dangerous_steps'], 0)

    def test_blocked_route_assessment(self) -> None:
        cells = _make_grid(3, risk_map={(0, 0): 5.0})
        route = compute_safe_route(cells, 3, (0, 0), (2, 2))
        assessment = assess_route_safety(route)
        self.assertFalse(assessment['is_safe'])
        self.assertEqual(assessment['route_status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
