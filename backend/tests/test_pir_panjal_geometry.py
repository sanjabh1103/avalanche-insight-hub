from __future__ import annotations

import unittest
from pathlib import Path

from backend.common.pir_panjal_geometry import derive_hgt_terrain


REPO_ROOT = Path(__file__).resolve().parents[2]
DEM_PATH = (
    REPO_ROOT
    / "backend/artifacts/open_forcing/20260801_pir_panjal_nw_himalaya"
    / "snapshots/srtm_dem/N34E074.hgt.gz"
)


class PirPanjalGeometryTests(unittest.TestCase):
    def test_customer_coordinate_produces_derived_candidate_geometry(self) -> None:
        if not DEM_PATH.is_file():
            self.skipTest("local SRTM fixture is not available in this checkout")
        result = derive_hgt_terrain(
            dem_path=DEM_PATH,
            latitude=34.021875,
            longitude=74.347536111,
        )
        self.assertEqual(result["method"], "srtm_hgt_horn_3x3_v1")
        self.assertEqual(result["elevation_m"], 3730.0)
        self.assertAlmostEqual(result["slope_deg"], 26.262132, places=5)
        self.assertAlmostEqual(result["aspect_deg"], 36.885404, places=5)
        self.assertEqual(result["aspect_label"], "NE")
        self.assertEqual(len(result["geometry_sha256"]), 64)

    def test_coordinate_outside_tile_fails_closed(self) -> None:
        if not DEM_PATH.is_file():
            self.skipTest("local SRTM fixture is not available in this checkout")
        with self.assertRaisesRegex(ValueError, "outside the DEM tile"):
            derive_hgt_terrain(dem_path=DEM_PATH, latitude=35.1, longitude=74.3)


if __name__ == "__main__":
    unittest.main()
