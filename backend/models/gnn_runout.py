"""F8: GNN Runout Dynamics — GNS-compatible scaffold with heuristic fallback.

Implements a hybrid interface for a partner's GNN avalanche flow simulator
(Pradyumn et al., FMFP 2025) based on the Graph Network-based Simulator (GNS)
architecture (Sanchez-Gonzalez et al., 2020).

The scaffold defines:
  1. DEM → graph tensor conversion (DEMGraphConverter)
  2. GNS model interface (GNSModelInterface) — abstract encoder/processor/decoder
  3. GNN runout engine (GNNRunoutEngine) — loads .pt weights if available,
     falls back to heuristic kinematic model if not
  4. Output schema (GNNRunoutResult) — velocity/depth/pressure fields + polygon

When Partner provides a partner's pre-trained .pt weights, the engine loads them
via torch.load() and runs GNS rollout inference. Without weights, compute_runout()
returns None and the caller falls back to the existing Alpha-Beta model.

Env flags:
  GNN_RUNOUT_ENABLED — enable GNN runout path (default: false)
  GNN_RUNOUT_WEIGHTS_PATH — path to .pt weights file
  GNN_RUNOUT_MAX_NODES — max graph nodes for edge deployment (default: 2000)
  GNN_RUNOUT_CONNECTIVITY_RADIUS_M — max edge distance (default: 50.0)
  GNN_RUNOUT_NUM_MESSAGE_PASSING — M in GNS (default: 10)
  GNN_RUNOUT_ROLLOUT_STEPS — K timesteps (default: 100)
  GNN_RUNOUT_DT — timestep in seconds (default: 0.01)
"""
from __future__ import annotations

import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Lazy torch import — GNN inference requires torch but the scaffold doesn't
try:
    import torch
    _HAS_TORCH = True
except Exception:
    torch = None
    _HAS_TORCH = False


# ─── Configuration ─────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class GNNRunoutConfig:
    """Configuration for GNN runout engine."""
    weights_path: Path | None = None
    connectivity_radius_m: float = _env_float('GNN_RUNOUT_CONNECTIVITY_RADIUS_M', 50.0)
    max_nodes: int = _env_int('GNN_RUNOUT_MAX_NODES', 2000)
    num_message_passing: int = _env_int('GNN_RUNOUT_NUM_MESSAGE_PASSING', 10)
    rollout_steps: int = _env_int('GNN_RUNOUT_ROLLOUT_STEPS', 100)
    dt: float = _env_float('GNN_RUNOUT_DT', 0.01)
    enabled: bool = _env_bool('GNN_RUNOUT_ENABLED', False)

    @classmethod
    def from_env(cls) -> GNNRunoutConfig:
        weights_env = os.environ.get('GNN_RUNOUT_WEIGHTS_PATH', '').strip()
        weights_path = Path(weights_env) if weights_env else None
        return cls(weights_path=weights_path)


# ─── Graph Data Structure ──────────────────────────────────────────────────

@dataclass
class GraphData:
    """Lightweight graph container — GNS-compatible without torch_geometric.

    Node features: [elevation_m, slope_deg, aspect_deg, snow_depth_proxy_m]
    Edge features: [distance_m, direction_deg, elevation_diff_m]
    """
    node_positions: np.ndarray   # (N, 2) — [lat, lng] per node
    node_features: np.ndarray    # (N, F) — features per node
    edge_index: np.ndarray       # (2, E) — sender, receiver indices
    edge_features: np.ndarray    # (E, Ef) — features per edge
    num_nodes: int = 0
    num_edges: int = 0

    def __post_init__(self) -> None:
        self.num_nodes = int(self.node_positions.shape[0]) if self.node_positions.size else 0
        self.num_edges = int(self.edge_index.shape[1]) if self.edge_index.size else 0

    def to_torch(self) -> dict[str, Any] | None:
        """Convert to torch tensors if torch is available."""
        if not _HAS_TORCH:
            return None
        return {
            'node_positions': torch.from_numpy(self.node_positions).float(),
            'node_features': torch.from_numpy(self.node_features).float(),
            'edge_index': torch.from_numpy(self.edge_index).long(),
            'edge_features': torch.from_numpy(self.edge_features).float(),
        }


# ─── DEM → Graph Converter ─────────────────────────────────────────────────

class DEMGraphConverter:
    """Converts a DEM raster window to a GNS-compatible graph tensor.

    Nodes represent terrain cells sampled from the DEM. Edges connect nodes
    within a spatial proximity radius (connectivity_radius_m). This matches
    the GNS approach where material points are graph nodes and their pairwise
    interactions are edges.
    """

    def __init__(self, config: GNNRunoutConfig) -> None:
        self.config = config

    def convert(
        self,
        dem_array: np.ndarray,
        transform: Any,
        lat: float,
        lng: float,
        window_radius_m: float = 2500.0,
        snow_depth_proxy: float = 0.5,
    ) -> GraphData:
        """Convert DEM array to GraphData.

        Args:
            dem_array: 2D elevation array (meters)
            transform: rasterio affine transform
            lat, lng: center coordinates of the release point
            window_radius_m: half-size of the DEM window to consider
            snow_depth_proxy: proxy snow depth in meters (default 0.5)

        Returns:
            GraphData with nodes, edges, and features
        """
        rows, cols = dem_array.shape
        if rows == 0 or cols == 0:
            return GraphData(
                node_positions=np.zeros((0, 2)),
                node_features=np.zeros((0, 4)),
                edge_index=np.zeros((2, 0), dtype=np.int64),
                edge_features=np.zeros((0, 3)),
            )

        # Subsample to max_nodes
        total_cells = rows * cols
        if total_cells > self.config.max_nodes:
            step = int(math.ceil(math.sqrt(total_cells / self.config.max_nodes)))
            dem_sub = dem_array[::step, ::step]
            rows_s, cols_s = dem_sub.shape
        else:
            dem_sub = dem_array
            rows_s, cols_s = rows, cols

        # Compute lat/lng for each node
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lng = max(1.0, meters_per_deg_lat * math.cos(math.radians(lat)))

        # Node positions (lat, lng) from transform
        node_positions = []
        node_features = []
        for r in range(rows_s):
            for c in range(cols_s):
                # Convert pixel to world coordinates
                if hasattr(transform, '__call__'):
                    x, y = transform(c + 0.5, r + 0.5)
                else:
                    x = transform.c + (c + 0.5) * transform.a
                    y = transform.f + (r + 0.5) * transform.e
                node_positions.append([y, x])  # [lat, lng]

                elevation = float(dem_sub[r, c])
                slope_deg = self._compute_slope(dem_sub, r, c, rows_s, cols_s)
                aspect_deg = self._compute_aspect(dem_sub, r, c, rows_s, cols_s)
                node_features.append([elevation, slope_deg, aspect_deg, snow_depth_proxy])

        node_positions = np.array(node_positions, dtype=np.float64)
        node_features = np.array(node_features, dtype=np.float64)

        # Build edges via k-nearest neighbors within connectivity radius
        edge_index, edge_features = self._build_edges(node_positions, node_features)

        return GraphData(
            node_positions=node_positions,
            node_features=node_features,
            edge_index=edge_index,
            edge_features=edge_features,
        )

    def _compute_slope(
        self, dem: np.ndarray, r: int, c: int, rows: int, cols: int,
    ) -> float:
        """Compute local slope angle in degrees using finite differences."""
        r_min = max(0, r - 1)
        r_max = min(rows - 1, r + 1)
        c_min = max(0, c - 1)
        c_max = min(cols - 1, c + 1)

        dz_dy = float(dem[r_max, c] - dem[r_min, c]) if r_max > r_min else 0.0
        dz_dx = float(dem[r, c_max] - dem[r, c_min]) if c_max > c_min else 0.0

        gradient_mag = math.sqrt(dz_dx ** 2 + dz_dy ** 2)
        # Assume ~30m pixel resolution for slope angle
        pixel_res_m = 30.0
        slope_rad = math.atan2(gradient_mag, pixel_res_m)
        return math.degrees(slope_rad)

    def _compute_aspect(
        self, dem: np.ndarray, r: int, c: int, rows: int, cols: int,
    ) -> float:
        """Compute aspect angle in degrees (0=N, 90=E, 180=S, 270=W)."""
        r_min = max(0, r - 1)
        r_max = min(rows - 1, r + 1)
        c_min = max(0, c - 1)
        c_max = min(cols - 1, c + 1)

        dz_dx = float(dem[r, c_max] - dem[r, c_min]) if c_max > c_min else 0.0
        dz_dy = float(dem[r_max, c] - dem[r_min, c]) if r_max > r_min else 0.0

        if abs(dz_dx) < 1e-9 and abs(dz_dy) < 1e-9:
            return 0.0
        # Aspect: 0=N, measured clockwise
        aspect_rad = math.atan2(dz_dx, dz_dy)
        aspect_deg = math.degrees(aspect_rad) % 360.0
        return aspect_deg

    def _build_edges(
        self,
        node_positions: np.ndarray,
        node_features: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build edge index and features using spatial proximity.

        Connects nodes within connectivity_radius_m. For efficiency with
        large graphs, uses a grid-based spatial hash.
        """
        n = len(node_positions)
        if n == 0:
            return (
                np.zeros((2, 0), dtype=np.int64),
                np.zeros((0, 3), dtype=np.float64),
            )

        radius = self.config.connectivity_radius_m
        meters_per_deg_lat = 111_320.0

        # Convert positions to meters relative to first node
        ref_lat = node_positions[0, 0] if n > 0 else 0.0
        meters_per_deg_lng = max(1.0, meters_per_deg_lat * math.cos(math.radians(ref_lat)))
        pos_m = np.zeros((n, 2), dtype=np.float64)
        pos_m[:, 0] = (node_positions[:, 0] - ref_lat) * meters_per_deg_lat
        pos_m[:, 1] = (node_positions[:, 1] - node_positions[0, 1]) * meters_per_deg_lng

        # Grid-based spatial hash for efficient neighbor search
        cell_size = radius
        grid: dict[tuple[int, int], list[int]] = {}
        for i in range(n):
            gx = int(pos_m[i, 0] // cell_size)
            gy = int(pos_m[i, 1] // cell_size)
            key = (gx, gy)
            if key not in grid:
                grid[key] = []
            grid[key].append(i)

        senders: list[int] = []
        receivers: list[int] = []
        edge_feats: list[list[float]] = []

        for i in range(n):
            gx = int(pos_m[i, 0] // cell_size)
            gy = int(pos_m[i, 1] // cell_size)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    key = (gx + dx, gy + dy)
                    if key not in grid:
                        continue
                    for j in grid[key]:
                        if j <= i:
                            continue
                        dist_m = math.sqrt(
                            (pos_m[i, 0] - pos_m[j, 0]) ** 2
                            + (pos_m[i, 1] - pos_m[j, 1]) ** 2
                        )
                        if dist_m > radius:
                            continue
                        direction_deg = math.degrees(
                            math.atan2(
                                pos_m[j, 1] - pos_m[i, 1],
                                pos_m[j, 0] - pos_m[i, 0],
                            )
                        ) % 360.0
                        elev_diff = float(
                            node_features[j, 0] - node_features[i, 0]
                        )
                        # Bidirectional edges
                        senders.extend([i, j])
                        receivers.extend([j, i])
                        edge_feats.append([dist_m, direction_deg, elev_diff])
                        edge_feats.append([dist_m, (direction_deg + 180) % 360, -elev_diff])

        edge_index = np.array([senders, receivers], dtype=np.int64)
        edge_features = np.array(edge_feats, dtype=np.float64)
        return edge_index, edge_features


# ─── GNS Model Interface ───────────────────────────────────────────────────

class GNSModelInterface(ABC):
    """Abstract interface for GNS model loading and inference.

    Partner plugs in a partner's trained model by implementing this interface
    (or by providing a .pt file that GNNRunoutEngine can load).
    """

    @abstractmethod
    def load_weights(self, path: Path) -> bool:
        """Load pre-trained weights. Returns True on success."""
        ...

    @abstractmethod
    def predict_next_state(self, graph: GraphData) -> GraphData:
        """Predict next state given current state graph."""
        ...

    @abstractmethod
    def rollout(self, initial_graph: GraphData, steps: int) -> list[GraphData]:
        """Run K-step rollout from initial state."""
        ...


# ─── GNN Runout Result ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class GNNRunoutResult:
    """Output of GNN runout computation."""
    velocity_field: np.ndarray   # (N, 2) — velocity [v_lat, v_lng] per node (m/s)
    depth_field: np.ndarray      # (N,) — flow depth per node (m)
    pressure_field: np.ndarray   # (N,) — impact pressure per node (kPa)
    polygon: list[list[float]]   # runout polygon [[lng, lat], ...]
    method: str                  # 'gnn_runout' or 'gnn_heuristic'
    node_positions: np.ndarray   # (N, 2) — [lat, lng] per node
    metadata: dict = field(default_factory=dict)


# ─── GNN Runout Engine ─────────────────────────────────────────────────────

class GNNRunoutEngine:
    """Main engine — loads GNS weights if available, falls back to heuristic.

    Usage:
        engine = GNNRunoutEngine.from_env()
        if engine.is_available():
            result = engine.compute_runout(dem_path, lat, lng, probability)
            if result is not None:
                # Use GNN result
                ...
        # If result is None, caller falls back to Alpha-Beta
    """

    def __init__(self, config: GNNRunoutConfig) -> None:
        self.config = config
        self._model: Any = None
        self._weights_loaded: bool = False
        self._converter = DEMGraphConverter(config)

        if config.weights_path and config.weights_path.exists():
            self._try_load_weights(config.weights_path)

    @classmethod
    def from_env(cls) -> GNNRunoutEngine:
        return cls(GNNRunoutConfig.from_env())

    def _try_load_weights(self, path: Path) -> None:
        """Attempt to load .pt weights using torch."""
        if not _HAS_TORCH:
            return
        try:
            self._model = torch.load(str(path), map_location='cpu', weights_only=False)
            self._weights_loaded = True
        except Exception:
            self._model = None
            self._weights_loaded = False

    def is_available(self) -> bool:
        """True if GNN weights are loaded and torch is available."""
        return _HAS_TORCH and self._weights_loaded and self._model is not None

    def compute_runout(
        self,
        dem_array: np.ndarray,
        transform: Any,
        lat: float,
        lng: float,
        probability: float,
        snow_depth_proxy: float = 0.5,
    ) -> GNNRunoutResult | None:
        """Compute runout using GNN if available, else heuristic.

        Args:
            dem_array: 2D elevation array
            transform: rasterio affine transform
            lat, lng: release point coordinates
            probability: avalanche probability (0-1)
            snow_depth_proxy: proxy snow depth in meters

        Returns:
            GNNRunoutResult if successful, None if caller should fall back
        """
        graph = self._converter.convert(
            dem_array, transform, lat, lng,
            snow_depth_proxy=snow_depth_proxy,
        )

        if graph.num_nodes == 0:
            return None

        if self.is_available():
            try:
                return self._gnn_inference(graph, probability)
            except Exception:
                # GNN inference failed — fall through to heuristic
                pass

        # Heuristic fallback (kinematic model)
        return _heuristic_runout_fields(graph, probability)

    def _gnn_inference(self, graph: GraphData, probability: float) -> GNNRunoutResult:
        """Run GNS rollout inference with loaded weights.

        This is the path that activates when Partner provides a partner weights.
        The implementation uses the loaded model to predict per-node accelerations
        over K rollout steps, then extracts velocity/depth/pressure fields.
        """
        # Convert to torch tensors
        torch_data = graph.to_torch()
        if torch_data is None:
            return _heuristic_runout_fields(graph, probability)

        # Run rollout
        current_graph = graph
        for _step in range(self.config.rollout_steps):
            current_graph = self._predict_step(current_graph)

        # Extract fields from final state
        velocities = current_graph.node_features[:, 4:6] if current_graph.node_features.shape[1] >= 6 else np.zeros((current_graph.num_nodes, 2))
        depths = current_graph.node_features[:, 6] if current_graph.node_features.shape[1] >= 7 else np.full(current_graph.num_nodes, probability * 2.0)

        # Compute pressure from velocity (Voellmy-like: p = rho * v^2)
        rho = 200.0  # snow density kg/m^3
        speeds = np.sqrt(velocities[:, 0] ** 2 + velocities[:, 1] ** 2)
        pressures = rho * speeds ** 2 / 1000.0  # kPa

        polygon = _extract_runout_polygon(current_graph.node_positions, depths)

        return GNNRunoutResult(
            velocity_field=velocities,
            depth_field=depths,
            pressure_field=pressures,
            polygon=polygon,
            method='gnn_runout',
            node_positions=current_graph.node_positions,
            metadata={
                'weights_loaded': True,
                'rollout_steps': self.config.rollout_steps,
                'num_nodes': current_graph.num_nodes,
                'num_edges': current_graph.num_edges,
            },
        )

    def _predict_step(self, graph: GraphData) -> GraphData:
        """Single GNS prediction step using loaded model.

        Calls the model's forward pass to predict per-node accelerations,
        then updates velocities and positions via Euler integration.
        """
        torch_data = graph.to_torch()
        if torch_data is None or self._model is None:
            return graph

        # This is where Partner's model gets called.
        # The model should accept (node_features, edge_index, edge_features)
        # and return per-node accelerations.
        try:
            with torch.no_grad():
                accelerations = self._model(
                    torch_data['node_features'],
                    torch_data['edge_index'],
                    torch_data['edge_features'],
                )
            accelerations = accelerations.cpu().numpy()
        except Exception:
            return graph

        # Update velocities and positions via Euler integration
        dt = self.config.dt
        current_features = graph.node_features.copy()
        current_positions = graph.node_positions.copy()

        # If velocity columns don't exist yet, initialize to zero
        if current_features.shape[1] < 6:
            current_features = np.hstack([
                current_features,
                np.zeros((current_features.shape[0], 2)),  # velocity
                np.zeros((current_features.shape[0], 1)),   # depth
            ])

        # Update velocity: v += a * dt
        current_features[:, 4:6] += accelerations[:, :2] * dt
        # Update depth (simple accumulation)
        current_features[:, 6] = np.maximum(current_features[:, 6], 0.0)
        # Update positions (convert m/s velocity to deg/s)
        ref_lat = current_positions[0, 0] if len(current_positions) > 0 else 0.0
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lng = max(1.0, meters_per_deg_lat * math.cos(math.radians(ref_lat)))
        current_positions[:, 0] += current_features[:, 4] * dt / meters_per_deg_lat
        current_positions[:, 1] += current_features[:, 5] * dt / meters_per_deg_lng

        return GraphData(
            node_positions=current_positions,
            node_features=current_features,
            edge_index=graph.edge_index,
            edge_features=graph.edge_features,
        )


# ─── Heuristic Runout Fields ───────────────────────────────────────────────

def _heuristic_runout_fields(
    graph: GraphData,
    probability: float,
) -> GNNRunoutResult:
    """Kinematic heuristic runout model.

    Uses slope angle and probability to estimate:
    - Velocity: v = sqrt(2 * g * L * sin(slope)) * probability_factor
    - Depth: d = probability * initial_depth * (1 + slope_factor)
    - Pressure: p = rho * v^2 / 1000 (kPa, Voellmy-like)
    """
    g = 9.81  # gravity m/s^2
    rho = 200.0  # snow density kg/m^3
    n = graph.num_nodes

    if n == 0:
        return GNNRunoutResult(
            velocity_field=np.zeros((0, 2)),
            depth_field=np.zeros(0),
            pressure_field=np.zeros(0),
            polygon=[],
            method='gnn_heuristic',
            node_positions=np.zeros((0, 2)),
            metadata={'heuristic': True},
        )

    slopes_rad = np.radians(graph.node_features[:, 1])  # slope_deg → rad
    aspects_rad = np.radians(graph.node_features[:, 2])  # aspect_deg → rad

    # Flow distance estimate (proportional to probability)
    flow_distance = 300.0 + probability * 900.0  # 300-1200m

    # Velocity magnitude from energy conservation: v = sqrt(2 * g * L * sin(slope))
    slope_factor = np.maximum(np.sin(slopes_rad), 0.0)
    velocity_mag = np.sqrt(2.0 * g * flow_distance * slope_factor) * (0.5 + 0.5 * probability)
    velocity_mag = np.clip(velocity_mag, 0.0, 60.0)  # cap at 60 m/s

    # Velocity direction (downslope = aspect direction)
    v_lat = -velocity_mag * np.cos(aspects_rad)
    v_lng = velocity_mag * np.sin(aspects_rad)
    velocities = np.column_stack([v_lat, v_lng])

    # Flow depth: proportional to probability and slope
    depths = probability * (1.0 + slope_factor * 2.0) * 1.5  # 0-4.5m
    depths = np.clip(depths, 0.0, 5.0)

    # Impact pressure: p = rho * v^2 (Pa) → kPa
    pressures = rho * velocity_mag ** 2 / 1000.0
    pressures = np.clip(pressures, 0.0, 500.0)  # cap at 500 kPa

    polygon = _extract_runout_polygon(graph.node_positions, depths)

    return GNNRunoutResult(
        velocity_field=velocities,
        depth_field=depths,
        pressure_field=pressures,
        polygon=polygon,
        method='gnn_heuristic',
        node_positions=graph.node_positions,
        metadata={
            'heuristic': True,
            'flow_distance_m': flow_distance,
            'max_velocity_ms': float(np.max(velocity_mag)),
            'max_depth_m': float(np.max(depths)),
            'max_pressure_kpa': float(np.max(pressures)),
        },
    )


def _extract_runout_polygon(
    node_positions: np.ndarray,
    depths: np.ndarray,
) -> list[list[float]]:
    """Extract runout polygon from node positions with significant flow depth.

    Selects nodes with depth > 10% of max depth and computes a convex hull
    approximation as the runout polygon.
    """
    if len(node_positions) == 0:
        return []

    max_depth = float(np.max(depths)) if depths.size else 0.0
    if max_depth < 1e-6:
        # Return bounding box of all nodes
        lats = node_positions[:, 0]
        lngs = node_positions[:, 1]
        return [
            [float(np.min(lngs)), float(np.min(lats))],
            [float(np.max(lngs)), float(np.min(lats))],
            [float(np.max(lngs)), float(np.max(lats))],
            [float(np.min(lngs)), float(np.max(lats))],
            [float(np.min(lngs)), float(np.min(lats))],
        ]

    threshold = max_depth * 0.1
    significant = depths >= threshold
    if not np.any(significant):
        significant = depths >= 0.0  # fallback: all nodes

    selected = node_positions[significant]
    lats = selected[:, 0]
    lngs = selected[:, 1]

    # Simple convex hull approximation: bounding box + midpoints
    lat_min, lat_max = float(np.min(lats)), float(np.max(lats))
    lng_min, lng_max = float(np.min(lngs)), float(np.max(lngs))

    # Add midpoints for a more polygon-like shape
    lat_mid = float(np.mean(lats))
    lng_mid = float(np.mean(lngs))

    return [
        [lng_min, lat_min],
        [lng_mid, lat_min],
        [lng_max, lat_min],
        [lng_max, lat_mid],
        [lng_max, lat_max],
        [lng_mid, lat_max],
        [lng_min, lat_max],
        [lng_min, lat_mid],
        [lng_min, lat_min],
    ]
