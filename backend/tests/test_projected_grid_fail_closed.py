"""Tests for projected grid strict fail-closed mode."""
from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import patch

from backend.common.features import build_region_grid, build_region_grid_projected
from backend.common.regions import Region


def _make_region() -> Region:
    return Region(
        name="Test Region",
        bbox=(32.0, 77.0, 32.5, 77.5),
        center=(32.25, 77.25),
        zoom=10,
    )


class ProjectedGridStrictModeTests(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_strict_true_with_pyproj_produces_grid(self) -> None:
        """Strict mode with pyproj available should produce a projected grid."""
        region = _make_region()
        cells = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        self.assertGreater(len(cells), 0)
        first = cells[0]
        self.assertIn('x_m', first)
        self.assertIn('pixel_id', first)
        self.assertIn('grid_manifest_hash', first)

    def test_strict_true_without_pyproj_raises(self) -> None:
        """Strict mode without pyproj must raise RuntimeError, not silently fall back."""
        region = _make_region()
        with patch.dict('sys.modules', {'pyproj': None}):
            with self.assertRaises(RuntimeError, msg="pyproj is not available"):
                build_region_grid_projected(region, cell_size_m=500.0, strict=True)

    def test_strict_false_without_pyproj_falls_back(self) -> None:
        """Non-strict mode without pyproj should fall back to degree grid (existing behavior)."""
        region = _make_region()
        with patch.dict('sys.modules', {'pyproj': None}):
            cells = build_region_grid_projected(region, cell_size_m=500.0, strict=False)
        self.assertGreater(len(cells), 0)
        first = cells[0]
        # Degree grid cells don't have x_m
        self.assertNotIn('x_m', first)

    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_pixel_ids_are_stable_and_unique(self) -> None:
        """Pixel IDs must be stable and unique across calls."""
        region = _make_region()
        cells1 = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        cells2 = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        ids1 = [c['pixel_id'] for c in cells1]
        ids2 = [c['pixel_id'] for c in cells2]
        self.assertEqual(ids1, ids2, "Pixel IDs must be stable across calls")
        self.assertEqual(len(set(ids1)), len(ids1), "Pixel IDs must be unique")

    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_grid_manifest_hash_is_deterministic(self) -> None:
        """Grid manifest hash must be identical for same inputs."""
        region = _make_region()
        cells1 = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        cells2 = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        self.assertEqual(cells1[0]['grid_manifest_hash'], cells2[0]['grid_manifest_hash'])

    @unittest.skipIf(importlib.util.find_spec('pyproj') is None, 'pyproj not installed')
    def test_grid_manifest_hash_changes_with_different_cell_size(self) -> None:
        """Different cell sizes should produce different manifest hashes."""
        region = _make_region()
        cells_500 = build_region_grid_projected(region, cell_size_m=500.0, strict=True)
        cells_1000 = build_region_grid_projected(region, cell_size_m=1000.0, strict=True)
        self.assertNotEqual(
            cells_500[0]['grid_manifest_hash'],
            cells_1000[0]['grid_manifest_hash'],
        )

    def test_existing_projected_grid_tests_still_pass(self) -> None:
        """Ensure the existing non-strict path still works (backward compat)."""
        region = _make_region()
        # This should not raise regardless of pyproj availability
        cells = build_region_grid_projected(region, cell_size_m=500.0)
        self.assertGreater(len(cells), 0)


if __name__ == '__main__':
    unittest.main()
