"""Tests for F8: GNN Runout Dynamics scaffold."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from rasterio.transform import from_bounds

from backend.models.gnn_runout import (
    DEMGraphConverter,
    GNNRunoutConfig,
    GNNRunoutEngine,
    GNNRunoutResult,
    GraphData,
    _heuristic_runout_fields,
    _extract_runout_polygon,
)


class DEMGraphConverterTests(unittest.TestCase):
    """Tests for DEM → graph tensor conversion."""

    @staticmethod
    def _make_dem(rows: int = 10, cols: int = 10) -> tuple[np.ndarray, object]:
        dem = np.linspace(3000, 2800, num=rows * cols, dtype=np.float32).reshape((rows, cols))
        transform = from_bounds(-107.0, 39.0, -106.0, 40.0, cols, rows)
        return dem, transform

    def test_dem_graph_converter_basic(self) -> None:
        dem, transform = self._make_dem()
        config = GNNRunoutConfig(max_nodes=500, connectivity_radius_m=50000.0)
        converter = DEMGraphConverter(config)
        graph = converter.convert(dem, transform, lat=39.5, lng=-106.5)

        self.assertGreater(graph.num_nodes, 0)
        self.assertGreater(graph.num_edges, 0)
        self.assertEqual(graph.node_positions.shape, (graph.num_nodes, 2))
        self.assertEqual(graph.node_features.shape[0], graph.num_nodes)
        self.assertEqual(graph.node_features.shape[1], 4)  # [elev, slope, aspect, snow_depth]

    def test_dem_graph_converter_node_features(self) -> None:
        dem, transform = self._make_dem()
        config = GNNRunoutConfig(max_nodes=500, connectivity_radius_m=50.0)
        converter = DEMGraphConverter(config)
        graph = converter.convert(dem, transform, lat=39.5, lng=-106.5)

        # Elevation should be in meters (2800-3000 range)
        elevations = graph.node_features[:, 0]
        self.assertTrue(np.all(elevations >= 2700))
        self.assertTrue(np.all(elevations <= 3100))

        # Slope should be in degrees [0, 90]
        slopes = graph.node_features[:, 1]
        self.assertTrue(np.all(slopes >= 0))
        self.assertTrue(np.all(slopes <= 90))

        # Aspect should be in degrees [0, 360)
        aspects = graph.node_features[:, 2]
        self.assertTrue(np.all(aspects >= 0))
        self.assertTrue(np.all(aspects < 360))

    def test_dem_graph_converter_edge_features(self) -> None:
        dem, transform = self._make_dem()
        config = GNNRunoutConfig(max_nodes=500, connectivity_radius_m=50000.0)
        converter = DEMGraphConverter(config)
        graph = converter.convert(dem, transform, lat=39.5, lng=-106.5)

        self.assertGreater(graph.num_edges, 0)
        self.assertEqual(graph.edge_features.shape[1], 3)  # [distance, direction, elev_diff]
        # Distances should be positive
        distances = graph.edge_features[:, 0]
        self.assertTrue(np.all(distances >= 0))
        # Directions should be [0, 360)
        directions = graph.edge_features[:, 1]
        self.assertTrue(np.all(directions >= 0))
        self.assertTrue(np.all(directions < 360))

    def test_dem_graph_converter_max_nodes_cap(self) -> None:
        # Large DEM that exceeds max_nodes
        dem, transform = self._make_dem(rows=100, cols=100)
        config = GNNRunoutConfig(max_nodes=50, connectivity_radius_m=50000.0)
        converter = DEMGraphConverter(config)
        graph = converter.convert(dem, transform, lat=39.5, lng=-106.5)

        self.assertLessEqual(graph.num_nodes, 50)

    def test_dem_graph_converter_empty_dem(self) -> None:
        dem = np.zeros((0, 0), dtype=np.float32)
        transform = from_bounds(-107.0, 39.0, -106.0, 40.0, 1, 1)
        config = GNNRunoutConfig()
        converter = DEMGraphConverter(config)
        graph = converter.convert(dem, transform, lat=39.5, lng=-106.5)

        self.assertEqual(graph.num_nodes, 0)
        self.assertEqual(graph.num_edges, 0)


class GNNRunoutEngineTests(unittest.TestCase):
    """Tests for GNN engine weight loading and fallback."""

    def test_gnn_engine_no_weights_returns_none(self) -> None:
        config = GNNRunoutConfig(enabled=True, weights_path=None)
        engine = GNNRunoutEngine(config)
        self.assertFalse(engine.is_available())

    def test_gnn_engine_with_mock_weights(self) -> None:
        # Create a mock weights file
        import tempfile
        import json

        with tempfile.NamedTemporaryFile(suffix='.pt', delete=False, mode='wb') as f:
            # Write minimal mock data
            if hasattr(np, 'save'):
                np.save(f.name, np.array({'mock': True}, dtype=object))
            weights_path = Path(f.name)

        try:
            # Patch torch to simulate weight loading
            with patch('backend.models.gnn_runout._HAS_TORCH', True), \
                 patch('backend.models.gnn_runout.torch', MagicMock()):
                import backend.models.gnn_runout as gnn_mod
                # Make torch.load return a mock model
                gnn_mod.torch.load = MagicMock(return_value=MagicMock())
                config = GNNRunoutConfig(enabled=True, weights_path=weights_path)
                engine = GNNRunoutEngine(config)
                self.assertTrue(engine.is_available())
        finally:
            weights_path.unlink(missing_ok=True)

    def test_gnn_engine_disabled_by_default(self) -> None:
        config = GNNRunoutConfig()
        self.assertFalse(config.enabled)

    def test_gnn_engine_compute_runout_no_weights_returns_heuristic(self) -> None:
        # Without weights, compute_runout should return heuristic result
        dem, transform = DEMGraphConverterTests._make_dem()
        config = GNNRunoutConfig(enabled=True, weights_path=None, max_nodes=100)
        engine = GNNRunoutEngine(config)
        result = engine.compute_runout(dem, transform, lat=39.5, lng=-106.5, probability=0.8)

        # Should return heuristic result (not None, since heuristic is always available)
        self.assertIsNotNone(result)
        self.assertEqual(result.method, 'gnn_heuristic')


class HeuristicRunoutFieldsTests(unittest.TestCase):
    """Tests for heuristic kinematic runout model."""

    @staticmethod
    def _make_graph(n: int = 10) -> GraphData:
        positions = np.array([[39.5 + i * 0.001, -106.5 + i * 0.001] for i in range(n)])
        features = np.array([
            [3000 - i * 20, 35.0, 135.0, 0.5] for i in range(n)
        ], dtype=np.float64)
        edge_index = np.array([[0, 1], [1, 0]], dtype=np.int64)
        edge_features = np.array([[50.0, 45.0, -20.0], [50.0, 225.0, 20.0]], dtype=np.float64)
        return GraphData(
            node_positions=positions,
            node_features=features,
            edge_index=edge_index,
            edge_features=edge_features,
        )

    def test_heuristic_runout_fields_basic(self) -> None:
        graph = self._make_graph(10)
        result = _heuristic_runout_fields(graph, probability=0.8)

        self.assertEqual(result.method, 'gnn_heuristic')
        self.assertEqual(result.velocity_field.shape, (10, 2))
        self.assertEqual(result.depth_field.shape, (10,))
        self.assertEqual(result.pressure_field.shape, (10,))

    def test_heuristic_runout_fields_velocity_positive(self) -> None:
        graph = self._make_graph(10)
        result = _heuristic_runout_fields(graph, probability=0.8)

        speeds = np.sqrt(result.velocity_field[:, 0] ** 2 + result.velocity_field[:, 1] ** 2)
        # At least some nodes should have positive velocity on 35° slope
        self.assertTrue(np.any(speeds > 0))

    def test_heuristic_runout_fields_depth_bounded(self) -> None:
        graph = self._make_graph(10)
        result = _heuristic_runout_fields(graph, probability=0.8)

        self.assertTrue(np.all(result.depth_field >= 0))
        self.assertTrue(np.all(result.depth_field <= 5.0))

    def test_heuristic_runout_fields_pressure_bounded(self) -> None:
        graph = self._make_graph(10)
        result = _heuristic_runout_fields(graph, probability=0.8)

        self.assertTrue(np.all(result.pressure_field >= 0))
        self.assertTrue(np.all(result.pressure_field <= 500.0))

    def test_heuristic_runout_fields_empty_graph(self) -> None:
        graph = GraphData(
            node_positions=np.zeros((0, 2)),
            node_features=np.zeros((0, 4)),
            edge_index=np.zeros((2, 0), dtype=np.int64),
            edge_features=np.zeros((0, 3)),
        )
        result = _heuristic_runout_fields(graph, probability=0.5)

        self.assertEqual(result.method, 'gnn_heuristic')
        self.assertEqual(result.velocity_field.shape, (0, 2))
        self.assertEqual(len(result.polygon), 0)


class ExtractRunoutPolygonTests(unittest.TestCase):
    """Tests for polygon extraction from node positions."""

    def test_gnn_runout_polygon_shape(self) -> None:
        positions = np.array([[39.5, -106.5], [39.51, -106.5], [39.5, -106.51], [39.51, -106.51]])
        depths = np.array([1.0, 2.0, 1.5, 0.5])
        polygon = _extract_runout_polygon(positions, depths)

        self.assertGreaterEqual(len(polygon), 4)
        for point in polygon:
            self.assertEqual(len(point), 2)  # [lng, lat]

    def test_gnn_runout_polygon_all_zero_depth(self) -> None:
        positions = np.array([[39.5, -106.5], [39.51, -106.5], [39.5, -106.51]])
        depths = np.array([0.0, 0.0, 0.0])
        polygon = _extract_runout_polygon(positions, depths)

        # Should return bounding box
        self.assertGreaterEqual(len(polygon), 4)

    def test_gnn_runout_polygon_empty(self) -> None:
        polygon = _extract_runout_polygon(np.zeros((0, 2)), np.zeros(0))
        self.assertEqual(len(polygon), 0)


class RunoutIntegrationTests(unittest.TestCase):
    """Integration tests with runout.py."""

    @patch('backend.common.runout.GNN_RUNOUT_ENABLED', False)
    def test_runout_polygon_for_cell_gnn_fallback(self) -> None:
        from backend.common.runout import runout_polygon_for_cell

        cell = {
            'row': 3,
            'col': 4,
            'lat': 39.50,
            'lng': -106.50,
            'probability': 0.8,
            'risk_score': 4,
            'terrain_inputs': {'slope_angle_deg': 35.0, 'aspect_deg': 135.0},
        }
        polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell=cell)

        # Should fall back to alpha_beta_elliptical
        self.assertEqual(polygon.method, 'alpha_beta_elliptical')
        self.assertEqual(polygon.row, 3)
        self.assertEqual(polygon.col, 4)

    @patch('backend.common.runout.GNN_RUNOUT_ENABLED', True)
    @patch('backend.common.runout._get_gnn_engine')
    def test_runout_polygon_for_cell_gnn_enabled_no_weights(self, mock_engine_fn: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = False
        mock_engine_fn.return_value = mock_engine

        from backend.common.runout import runout_polygon_for_cell

        cell = {
            'row': 3,
            'col': 4,
            'lat': 39.50,
            'lng': -106.50,
            'probability': 0.8,
            'risk_score': 4,
            'terrain_inputs': {'slope_angle_deg': 35.0, 'aspect_deg': 135.0},
        }
        polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell=cell)

        # Should fall back to alpha_beta_elliptical since GNN not available
        self.assertEqual(polygon.method, 'alpha_beta_elliptical')

    @patch('backend.common.runout.GNN_RUNOUT_ENABLED', True)
    @patch('backend.common.runout._get_gnn_engine')
    @patch('backend.common.runout._HAS_RASTERIO', False)
    def test_runout_polygon_for_cell_gnn_success_no_rasterio(self, mock_engine_fn: MagicMock) -> None:
        # GNN enabled but no rasterio → can't read DEM → falls back
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_engine_fn.return_value = mock_engine

        from backend.common.runout import runout_polygon_for_cell

        cell = {
            'row': 3,
            'col': 4,
            'lat': 39.50,
            'lng': -106.50,
            'probability': 0.8,
            'risk_score': 4,
            'terrain_inputs': {'slope_angle_deg': 35.0, 'aspect_deg': 135.0},
        }
        polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell=cell)

        # Falls back to alpha_beta_elliptical
        self.assertEqual(polygon.method, 'alpha_beta_elliptical')

    @patch('backend.common.runout.GNN_RUNOUT_ENABLED', True)
    @patch('backend.common.runout.GNN_RUNOUT_EXTERNAL_CALIBRATED', True)
    @patch('backend.common.runout.GNN_RUNOUT_HELD_OUT_VALIDATED', True)
    @patch('backend.common.runout.GNN_RUNOUT_PROMOTION_GATE_PASSED', True)
    @patch('backend.common.runout._get_gnn_engine')
    def test_runout_polygon_for_cell_gnn_success(self, mock_engine_fn: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True
        mock_result = GNNRunoutResult(
            velocity_field=np.zeros((5, 2)),
            depth_field=np.ones(5),
            pressure_field=np.ones(5),
            polygon=[[-106.5, 39.5], [-106.49, 39.5], [-106.49, 39.51], [-106.5, 39.51], [-106.5, 39.5]],
            method='gnn_runout',
            node_positions=np.zeros((5, 2)),
            metadata={'weights_loaded': True},
        )
        mock_engine.compute_runout.return_value = mock_result
        mock_engine_fn.return_value = mock_engine

        # Also need to mock rasterio and DEM file
        with patch('backend.common.runout._HAS_RASTERIO', True), \
             patch('backend.common.runout.DEM_ROOT') as mock_dem_root, \
             patch('backend.common.runout.rasterio') as mock_rasterio:
            mock_dem_root.__truediv__.return_value.exists.return_value = True
            mock_src = MagicMock()
            mock_src.res = (0.001, 0.001)
            mock_src.crs.is_geographic = True
            mock_src.height = 100
            mock_src.width = 100
            mock_src.index.return_value = (50, 50)
            mock_src.read.return_value = np.linspace(3000, 2800, 100).reshape(10, 10).astype(np.float32)
            mock_src.window_transform.return_value = from_bounds(-107, 39, -106, 40, 10, 10)
            mock_rasterio.open.return_value.__enter__.return_value = mock_src

            from backend.common.runout import runout_polygon_for_cell

            cell = {
                'row': 3,
                'col': 4,
                'lat': 39.50,
                'lng': -106.50,
                'probability': 0.8,
                'risk_score': 4,
                'terrain_inputs': {'slope_angle_deg': 35.0, 'aspect_deg': 135.0},
            }
            polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell=cell)

            self.assertEqual(polygon.method, 'gnn_runout')
            self.assertEqual(polygon.row, 3)
            self.assertEqual(polygon.col, 4)


class TelingNalaCaseStudyTests(unittest.TestCase):
    """Validate heuristic against known Teling Nala parameters.

    Teling Nala (Uttarakhand): slope ~35°, typical runout ~800m,
    release probability ~0.7 for a moderate event.
    """

    def test_teling_nala_case_study(self) -> None:
        # Simulate a 35° slope with Teling Nala-like parameters
        n = 20
        positions = np.array([[30.0 + i * 0.001, 79.0 + i * 0.001] for i in range(n)])
        features = np.array([
            [3500 - i * 40, 35.0, 180.0, 0.5] for i in range(n)
        ], dtype=np.float64)
        edge_index = np.array([[i, i + 1] for i in range(n - 1)] + [[i + 1, i] for i in range(n - 1)]).T
        edge_features = np.array([[100.0, 0.0, -40.0]] * (n - 1) + [[100.0, 180.0, 40.0]] * (n - 1))
        graph = GraphData(
            node_positions=positions,
            node_features=features,
            edge_index=edge_index,
            edge_features=edge_features,
        )

        result = _heuristic_runout_fields(graph, probability=0.7)

        # Velocity should be in a reasonable range for 35° slope
        speeds = np.sqrt(result.velocity_field[:, 0] ** 2 + result.velocity_field[:, 1] ** 2)
        max_speed = float(np.max(speeds))
        self.assertGreater(max_speed, 5.0)  # At least 5 m/s
        self.assertLessEqual(max_speed, 60.0)  # Capped at 60 m/s

        # Depth should be reasonable (0.5-4m for moderate event)
        self.assertTrue(np.all(result.depth_field >= 0))
        self.assertLess(float(np.max(result.depth_field)), 5.0)

        # Pressure should be positive and bounded
        self.assertTrue(np.all(result.pressure_field >= 0))
        self.assertLessEqual(float(np.max(result.pressure_field)), 500.0)

        # Polygon should have at least 4 points
        self.assertGreaterEqual(len(result.polygon), 4)

        # Metadata should contain heuristic flag
        self.assertTrue(result.metadata.get('heuristic'))


if __name__ == '__main__':
    unittest.main()
