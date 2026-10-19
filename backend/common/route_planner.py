"""F10: Safe-Route Re-Computation Engine.

Graph-based pathfinding over the forecast grid that avoids cells flagged
as high risk by the multi-hazard assessment. Uses Dijkstra's algorithm
with risk-weighted edge costs to compute the safest transit path between
two grid cells.

Scientific basis:
    DRDE/Partner operational requirement for safe route planning in
    avalanche-prone terrain. The route planner treats each grid cell as
    a node in a graph, with edge weights proportional to the composite
    risk level of the destination cell. Cells exceeding a configurable
    risk threshold are treated as impassable obstacles.

Integration points:
    - Consumes grid cells from ``build_region_grid`` (backend/common/features.py)
    - Consumes ``risk_score`` / ``composite_risk_level`` from multi-hazard
      assessment (backend/common/multi_hazard.py)
    - Called by daily_inference.py to attach safe-route metadata to payloads
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridCell:
    """A single cell in the forecast grid."""
    row: int
    col: int
    lat: float
    lng: float
    risk_score: float = 0.0
    risk_level: int = 0
    hazard_type: str = 'avalanche'

    @property
    def cell_id(self) -> str:
        return f'r{self.row}c{self.col}'


@dataclass
class RouteStep:
    """A single step in a computed safe route."""
    row: int
    col: int
    lat: float
    lng: float
    risk_score: float
    risk_level: int
    cumulative_cost: float
    step_index: int


@dataclass
class SafeRoute:
    """Result of a safe-route computation."""
    steps: list[RouteStep] = field(default_factory=list)
    total_cost: float = 0.0
    status: str = 'ok'  # ok | blocked | no_path
    blocked_cells: list[str] = field(default_factory=list)
    start_cell: str = ''
    end_cell: str = ''
    grid_size: int = 0
    algorithm: str = 'dijkstra'

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def max_risk_along_route(self) -> float:
        return max((s.risk_score for s in self.steps), default=0.0)

    @property
    def avg_risk_along_route(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.risk_score for s in self.steps) / len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            'status': self.status,
            'start_cell': self.start_cell,
            'end_cell': self.end_cell,
            'grid_size': self.grid_size,
            'algorithm': self.algorithm,
            'step_count': self.step_count,
            'total_cost': round(self.total_cost, 4),
            'max_risk': round(self.max_risk_along_route, 3),
            'avg_risk': round(self.avg_risk_along_route, 3),
            'blocked_cells': self.blocked_cells,
            'steps': [
                {
                    'step_index': s.step_index,
                    'row': s.row,
                    'col': s.col,
                    'lat': round(s.lat, 5),
                    'lng': round(s.lng, 5),
                    'risk_score': round(s.risk_score, 3),
                    'risk_level': s.risk_level,
                    'cumulative_cost': round(s.cumulative_cost, 4),
                }
                for s in self.steps
            ],
        }


# ---------------------------------------------------------------------------
# Grid utilities
# ---------------------------------------------------------------------------

def cells_from_grid(
    grid_cells: list[dict[str, Any]],
    *,
    risk_key: str = 'risk_score',
    risk_level_key: str = 'composite_risk_level',
    hazard_key: str = 'dominant_hazard',
) -> list[GridCell]:
    """Convert raw grid cell dicts into ``GridCell`` objects.

    Args:
        grid_cells: List of cell dicts from ``build_region_grid`` or
            multi-hazard assessment output.
        risk_key: Dict key for the risk score (0-5 scale).
        risk_level_key: Dict key for the integer risk level.
        hazard_key: Dict key for the dominant hazard type.

    Returns:
        List of ``GridCell`` objects.
    """
    result: list[GridCell] = []
    for cell in grid_cells:
        result.append(GridCell(
            row=int(cell.get('row', 0)),
            col=int(cell.get('col', 0)),
            lat=float(cell.get('lat', 0.0)),
            lng=float(cell.get('lng', 0.0)),
            risk_score=float(cell.get(risk_key, cell.get('composite_risk', 0.0)) or 0.0),
            risk_level=int(cell.get(risk_level_key, 0) or 0),
            hazard_type=str(cell.get(hazard_key, 'avalanche')),
        ))
    return result


def build_adjacency(
    cells: list[GridCell],
    grid_size: int,
    *,
    allow_diagonal: bool = True,
) -> dict[str, list[tuple[str, float]]]:
    """Build adjacency list for the grid graph.

    Edge weight = 1.0 + risk_score of the destination cell.
    This means entering a high-risk cell is expensive but not impossible
    (unless it exceeds the threshold and is blocked).

    Args:
        cells: List of ``GridCell`` objects.
        grid_size: Grid dimension (grid_size x grid_size).
        allow_diagonal: Allow 8-directional movement (vs 4-directional).

    Returns:
        Adjacency dict mapping cell_id -> list of (neighbor_id, edge_weight).
    """
    cell_map: dict[str, GridCell] = {c.cell_id: c for c in cells}
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if allow_diagonal:
        directions += [(-1, -1), (-1, 1), (1, -1), (1, 1)]

    adj: dict[str, list[tuple[str, float]]] = {}
    for cell in cells:
        neighbors: list[tuple[str, float]] = []
        for dr, dc in directions:
            nr, nc = cell.row + dr, cell.col + dc
            if 0 <= nr < grid_size and 0 <= nc < grid_size:
                nid = f'r{nr}c{nc}'
                if nid in cell_map:
                    dest = cell_map[nid]
                    distance = math.sqrt(dr * dr + dc * dc)
                    weight = distance * (1.0 + dest.risk_score)
                    neighbors.append((nid, weight))
        adj[cell.cell_id] = neighbors
    return adj


# ---------------------------------------------------------------------------
# Pathfinding
# ---------------------------------------------------------------------------

def compute_safe_route(
    cells: list[dict[str, Any]],
    grid_size: int,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    risk_threshold: float = 3.5,
    allow_diagonal: bool = True,
    max_iterations: int = 10000,
) -> SafeRoute:
    """Compute the safest route between two grid cells using Dijkstra's algorithm.

    Cells with ``risk_score >= risk_threshold`` are treated as impassable
    obstacles. The algorithm minimizes cumulative edge weight, which is
    proportional to the risk score of each cell entered.

    Args:
        cells: Raw grid cell dicts with risk data.
        grid_size: Grid dimension (N x N).
        start: (row, col) tuple for the start cell.
        end: (row, col) tuple for the end cell.
        risk_threshold: Cells with risk_score >= this value are blocked.
        allow_diagonal: Allow 8-directional movement.
        max_iterations: Safety limit to prevent infinite loops.

    Returns:
        ``SafeRoute`` with the computed path or a blocked/no_path status.
    """
    grid_cells = cells_from_grid(cells)
    cell_map: dict[str, GridCell] = {c.cell_id: c for c in grid_cells}

    start_id = f'r{start[0]}c{start[1]}'
    end_id = f'r{end[0]}c{end[1]}'

    if start_id not in cell_map:
        return SafeRoute(
            status='no_path',
            start_cell=start_id,
            end_cell=end_id,
            grid_size=grid_size,
            blocked_cells=[],
        )
    if end_id not in cell_map:
        return SafeRoute(
            status='no_path',
            start_cell=start_id,
            end_cell=end_id,
            grid_size=grid_size,
            blocked_cells=[],
        )

    # Identify blocked cells
    blocked: list[str] = []
    blocked_set: set[str] = set()
    for cell in grid_cells:
        if cell.risk_score >= risk_threshold:
            blocked.append(cell.cell_id)
            blocked_set.add(cell.cell_id)

    # If start or end is blocked, no safe route exists
    if start_id in blocked_set or end_id in blocked_set:
        return SafeRoute(
            status='blocked',
            start_cell=start_id,
            end_cell=end_id,
            grid_size=grid_size,
            blocked_cells=blocked,
        )

    # Build adjacency, excluding blocked cells
    adj = build_adjacency(grid_cells, grid_size, allow_diagonal=allow_diagonal)
    # Remove edges to blocked cells
    for cid in list(adj.keys()):
        if cid in blocked_set:
            adj[cid] = []
        else:
            adj[cid] = [(n, w) for n, w in adj[cid] if n not in blocked_set]

    # Dijkstra's algorithm
    dist: dict[str, float] = {start_id: 0.0}
    prev: dict[str, str | None] = {start_id: None}
    pq: list[tuple[float, str]] = [(0.0, start_id)]
    iterations = 0

    while pq and iterations < max_iterations:
        iterations += 1
        cur_dist, cur_id = heapq.heappop(pq)

        if cur_id == end_id:
            break

        if cur_dist > dist.get(cur_id, float('inf')):
            continue

        for neighbor_id, weight in adj.get(cur_id, []):
            new_dist = cur_dist + weight
            if new_dist < dist.get(neighbor_id, float('inf')):
                dist[neighbor_id] = new_dist
                prev[neighbor_id] = cur_id
                heapq.heappush(pq, (new_dist, neighbor_id))

    # Reconstruct path
    if end_id not in dist:
        return SafeRoute(
            status='no_path',
            start_cell=start_id,
            end_cell=end_id,
            grid_size=grid_size,
            blocked_cells=blocked,
        )

    path: list[str] = []
    cur: str | None = end_id
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()

    steps: list[RouteStep] = []
    cumulative = 0.0
    for idx, cid in enumerate(path):
        cell = cell_map[cid]
        steps.append(RouteStep(
            row=cell.row,
            col=cell.col,
            lat=cell.lat,
            lng=cell.lng,
            risk_score=cell.risk_score,
            risk_level=cell.risk_level,
            cumulative_cost=round(cumulative, 4),
            step_index=idx,
        ))
        if idx < len(path) - 1:
            for nid, w in adj.get(cid, []):
                if nid == path[idx + 1]:
                    cumulative += w
                    break

    return SafeRoute(
        steps=steps,
        total_cost=round(dist[end_id], 4),
        status='ok',
        blocked_cells=blocked,
        start_cell=start_id,
        end_cell=end_id,
        grid_size=grid_size,
        algorithm='dijkstra',
    )


def compute_safe_routes_batch(
    cells: list[dict[str, Any]],
    grid_size: int,
    requests: list[dict[str, Any]],
    *,
    risk_threshold: float = 3.5,
    allow_diagonal: bool = True,
) -> list[SafeRoute]:
    """Compute safe routes for multiple start/end pairs.

    Args:
        cells: Raw grid cell dicts with risk data.
        grid_size: Grid dimension.
        requests: List of dicts with 'start' and 'end' keys (each a [row, col] pair).
        risk_threshold: Cells with risk_score >= this value are blocked.
        allow_diagonal: Allow 8-directional movement.

    Returns:
        List of ``SafeRoute`` objects, one per request.
    """
    routes: list[SafeRoute] = []
    for req in requests:
        start = (int(req['start'][0]), int(req['start'][1]))
        end = (int(req['end'][0]), int(req['end'][1]))
        route = compute_safe_route(
            cells,
            grid_size,
            start,
            end,
            risk_threshold=risk_threshold,
            allow_diagonal=allow_diagonal,
        )
        routes.append(route)
    return routes


def assess_route_safety(route: SafeRoute, *, risk_threshold: float = 3.5) -> dict[str, Any]:
    """Assess the safety of a computed route.

    Args:
        route: A computed ``SafeRoute``.
        risk_threshold: The risk level above which a cell is considered dangerous.

    Returns:
        Dict with safety assessment metrics.
    """
    if route.status != 'ok':
        return {
            'route_status': route.status,
            'is_safe': False,
            'max_risk': route.max_risk_along_route,
            'avg_risk': route.avg_risk_along_route,
            'dangerous_steps': 0,
            'blocked_cells_count': len(route.blocked_cells),
        }

    dangerous_steps = [s for s in route.steps if s.risk_score >= risk_threshold]
    return {
        'route_status': route.status,
        'is_safe': len(dangerous_steps) == 0,
        'max_risk': round(route.max_risk_along_route, 3),
        'avg_risk': round(route.avg_risk_along_route, 3),
        'dangerous_steps': len(dangerous_steps),
        'blocked_cells_count': len(route.blocked_cells),
        'total_cost': round(route.total_cost, 4),
        'step_count': route.step_count,
    }
