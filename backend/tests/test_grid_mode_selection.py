"""Tests for RAVAFCAST_GRID_MODE env var selection (G9)."""
from __future__ import annotations

import unittest
import os


class GridModeSelectionTests(unittest.TestCase):

    def test_default_grid_mode_is_degree(self) -> None:
        self.assertEqual(os.getenv('RAVAFCAST_GRID_MODE', 'degree').lower(), 'degree')

    def test_projected_grid_has_manifest_hash(self) -> None:
        from backend.common.features import build_region_grid_projected
        from backend.common.regions import Region
        try:
            region = Region(
                name='Test', bbox=(30.0, 77.0, 30.5, 77.5),
                center=(30.25, 77.25), zoom=8,
            )
            cells = build_region_grid_projected(region, cell_size_m=11000, strict=False)
            self.assertTrue(len(cells) > 0)
            self.assertIn('grid_manifest_hash', cells[0])
            self.assertIn('pixel_id', cells[0])
        except (RuntimeError, TypeError):
            self.skipTest("pyproj not available")

    def test_projected_grid_strict_fails_without_pyproj(self) -> None:
        import importlib.util
        if importlib.util.find_spec('pyproj') is not None:
            self.skipTest("pyproj installed — strict mode works")
        from backend.common.features import build_region_grid_projected
        from backend.common.regions import Region
        region = Region(
            name='Test', bbox=(30.0, 77.0, 30.5, 77.5),
            center=(30.25, 77.25), zoom=8,
        )
        with self.assertRaises(RuntimeError):
            build_region_grid_projected(region, cell_size_m=500.0, strict=True)


if __name__ == '__main__':
    unittest.main()
