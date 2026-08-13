import unittest

from backend.common.real_features import TerrainUnavailableError
from backend.common.terrain_diagnostics import (
    MAX_TERRAIN_LOSS_RATE,
    build_terrain_loss_report,
    classify_terrain_failure,
    count_runtime_terrain_failure_reasons,
    validate_terrain_gate,
)


class TerrainDiagnosticsTests(unittest.TestCase):
    def test_failure_reasons_are_stable_and_non_sensitive(self) -> None:
        self.assertEqual(
            classify_terrain_failure(
                TerrainUnavailableError("No valid DEM window found near secret/path.tif")
            ),
            "invalid_or_nodata_window",
        )
        self.assertEqual(
            classify_terrain_failure(FileNotFoundError("missing dem file")),
            "dem_read_error",
        )
        self.assertEqual(
            classify_terrain_failure(ValueError("unexpected terrain value")),
            "terrain_value_error",
        )

    def test_report_separates_terrain_loss_from_later_stage_loss(self) -> None:
        report = build_terrain_loss_report({
            "raw_rows": 10,
            "no_point": 1,
            "no_timestamp": 1,
            "no_region": 0,
            "no_dem": 1,
            "terrain_failed": 1,
            "terrain_success": 6,
            "assembled_ok": 5,
            "terrain_failure_reasons": {
                "missing_dem": 1,
                "invalid_or_nodata_window": 1,
            },
            "terrain_candidates_by_region": {"nepal": 8},
            "terrain_candidates_by_source": {"gee_sar": 8},
            "terrain_candidates_by_season": {"2023-2024": 8},
            "terrain_missing_dem_by_region": {"nepal": 1},
            "terrain_missing_dem_by_source": {"gee_sar": 1},
            "terrain_missing_dem_by_season": {"2023-2024": 1},
            "terrain_failed_by_region": {"nepal": 1},
            "terrain_failed_by_source": {"gee_sar": 1},
            "terrain_failed_by_season": {"2023-2024": 1},
            "terrain_success_by_region": {"nepal": 6},
            "terrain_success_by_source": {"gee_sar": 6},
            "terrain_success_by_season": {"2023-2024": 6},
            "terrain_failure_reasons_by_region": {
                "nepal": {"missing_dem": 1, "invalid_or_nodata_window": 1},
            },
            "terrain_failure_reasons_by_source": {
                "gee_sar": {"missing_dem": 1, "invalid_or_nodata_window": 1},
            },
            "terrain_failure_reasons_by_season": {
                "2023-2024": {"missing_dem": 1, "invalid_or_nodata_window": 1},
            },
        })

        self.assertEqual(report["candidate_rows"], 8)
        self.assertEqual(report["terrain_loss_count"], 2)
        self.assertAlmostEqual(report["terrain_loss_rate"], 0.25)
        self.assertEqual(report["post_terrain_weather_or_governance_loss"], 1)
        self.assertEqual(report["by_region"]["nepal"]["loss_count"], 2)
        self.assertEqual(report["by_source"]["gee_sar"]["loss_count"], 2)
        self.assertEqual(report["by_season"]["2023-2024"]["loss_count"], 2)
        self.assertEqual(report["failure_reasons_by_source"]["gee_sar"]["missing_dem"], 1)
        self.assertEqual(report["failure_reasons_by_season"]["2023-2024"]["missing_dem"], 1)
        self.assertEqual(report["by_stage"]["terrain_assembly"]["loss_count"], 2)
        self.assertEqual(report["by_stage"]["post_terrain_weather_or_governance"]["loss_count"], 1)
        self.assertEqual(report["failure_reasons_by_region"]["nepal"]["missing_dem"], 1)

    def test_strict_gate_rejects_unexplained_or_excessive_loss(self) -> None:
        errors = validate_terrain_gate({
            "terrain_loss_rate": MAX_TERRAIN_LOSS_RATE + 0.01,
            "failure_reasons": {"unknown_terrain_error": 1},
            "by_region": {},
        })
        self.assertEqual(len(errors), 2)
        self.assertIn("exceeds", errors[0])
        self.assertIn("unknown_terrain_error", errors[1])

    def test_runtime_counts_preserve_specific_reason_and_fail_closed_when_missing(self) -> None:
        counts = count_runtime_terrain_failure_reasons([
            {
                "availability_reason": "unavailable_terrain",
                "terrain_failure_reason": "dem_read_error",
            },
            {"availability_reason": "unavailable_terrain"},
            {"availability_reason": "unavailable_weather"},
        ])
        self.assertEqual(
            counts,
            {"dem_read_error": 1, "unknown_terrain_error": 1},
        )

    def test_canonical_grid_cell_preserves_specific_reason(self) -> None:
        from backend.inference.grid import _build_unavailable_cell

        row = _build_unavailable_cell(
            cell={"row": 0, "col": 0, "lat_end": 28.1, "lng_end": 86.1},
            center_lat=28.0,
            center_lng=86.0,
            bundle={
                "selected_features": [],
                "created_at": "2026-08-03T00:00:00Z",
                "calibration_method": "test",
            },
            snowpack_proxy=None,
            reason="unavailable_terrain",
            terrain_failure_reason="dem_read_error",
        )
        self.assertEqual(row["terrain_failure_reason"], "dem_read_error")
        self.assertEqual(row["terrain_inputs"]["failure_reason"], "dem_read_error")


if __name__ == "__main__":
    unittest.main()
