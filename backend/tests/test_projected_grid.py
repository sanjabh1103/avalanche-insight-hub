"""Tests for UTM-projected grid builder."""
from __future__ import annotations

import unittest
import importlib.util
from unittest.mock import patch

from backend.common.features import build_region_grid, build_region_grid_projected
from backend.common.regions import Region


def _make_region(
    key: str = 'test_region',
    name: str = 'Test Region',
    bbox: tuple[float, float, float, float] = (28.0, 86.0, 29.0, 87.0),
) -> Region:
    return Region(
        name=name,
        bbox=bbox,
        center=((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2),
        zoom=8,
        zone_type='great_himalaya',
    )


class BuildRegionGridProjectedTests(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_projected_grid_has_500m_cells(self) -> None:
        region = _make_region()
        cells = build_region_grid_projected(region, cell_size_m=500.0)
        self.assertGreater(len(cells), 0)
        first = cells[0]
        self.assertIn('x_m', first)
        self.assertIn('y_m', first)
        self.assertIn('cell_size_m', first)
        self.assertEqual(first['cell_size_m'], 500.0)
        self.assertIn('grid_rows', first)
        self.assertIn('grid_cols', first)

    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_projected_grid_cells_are_within_bbox(self) -> None:
        region = _make_region()
        cells = build_region_grid_projected(region, cell_size_m=500.0)
        lat_min, lng_min, lat_max, lng_max = region.bbox
        for cell in cells:
            self.assertGreaterEqual(cell['lat'], lat_min - 0.01)
            self.assertLessEqual(cell['lat'], lat_max + 0.01)
            self.assertGreaterEqual(cell['lng'], lng_min - 0.01)
            self.assertLessEqual(cell['lng'], lng_max + 0.01)

    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_projected_grid_uniform_cell_size(self) -> None:
        region = _make_region()
        cells = build_region_grid_projected(region, cell_size_m=500.0)
        for cell in cells:
            self.assertEqual(cell['cell_size_m'], 500.0)

    def test_falls_back_to_degree_grid_without_pyproj(self) -> None:
        region = _make_region()
        with patch.dict('sys.modules', {'pyproj': None}):
            cells = build_region_grid_projected(region, cell_size_m=500.0)
        self.assertGreater(len(cells), 0)
        first = cells[0]
        self.assertNotIn('x_m', first)
        self.assertNotIn('cell_size_m', first)


class BuildRegionGridTests(unittest.TestCase):
    def test_degree_grid_returns_grid_size_squared_cells(self) -> None:
        region = _make_region()
        cells = build_region_grid(region, grid_size=20)
        self.assertEqual(len(cells), 400)

    def test_degree_grid_cells_have_lat_lng(self) -> None:
        region = _make_region()
        cells = build_region_grid(region, grid_size=10)
        first = cells[0]
        self.assertIn('lat', first)
        self.assertIn('lng', first)
        self.assertIn('row', first)
        self.assertIn('col', first)


if __name__ == '__main__':
    unittest.main()
