from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.open_forcing.contracts import OpenForcingContractError
from backend.open_forcing.coverage import (
    AoiBounds,
    NativeForcingPoint,
    construct_aoi_coverage_plan,
)


class OpenForcingCoverageTests(unittest.TestCase):
    def _plan(
        self,
        *,
        status: str = "pending",
        points: tuple[NativeForcingPoint, ...] | None = None,
        max_assignment_distance_m: float | None = None,
    ):
        start = datetime(2026, 7, 31, tzinfo=timezone.utc)
        return construct_aoi_coverage_plan(
            source_id="open_meteo_nwp",
            provider="open-meteo-single-runs",
            model_id="ecmwf_ifs025",
            run_id="2026-07-31T00:00",
            aoi=AoiBounds(34.0, 75.0, 34.2, 75.2),
            target_rows=4,
            target_cols=4,
            target_resolution_m=500.0,
            native_resolution_m=9000.0,
            required_variables=("temperature_2m", "precipitation"),
            valid_times=(start, start + timedelta(hours=1)),
            native_points=points
            or (
                NativeForcingPoint("p00", 34.025, 75.025),
                NativeForcingPoint("p01", 34.025, 75.175),
                NativeForcingPoint("p10", 34.175, 75.025),
                NativeForcingPoint("p11", 34.175, 75.175),
            ),
            max_assignment_distance_m=max_assignment_distance_m,
            license_review_status=status,
        )

    def test_multi_point_plan_covers_target_cells_without_claiming_target_resolution(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.target_cell_count, 16)
        self.assertEqual(plan.coverage_fraction, 1.0)
        self.assertTrue(plan.complete_spatial_coverage)
        self.assertEqual(plan.effective_information_scale_m, 9000.0)
        self.assertFalse(plan.can_enter_forcing_pipeline)

    def test_pending_license_blocks_forcing_pipeline(self) -> None:
        self.assertFalse(self._plan(status="pending").can_enter_forcing_pipeline)
        self.assertTrue(self._plan(status="approved").can_enter_forcing_pipeline)

    def test_sparse_points_expose_missing_target_cells(self) -> None:
        plan = self._plan(
            points=(NativeForcingPoint("centre", 34.1, 75.1),),
            max_assignment_distance_m=3000.0,
        )
        self.assertLess(plan.coverage_fraction, 1.0)
        self.assertFalse(plan.complete_spatial_coverage)

    def test_unknown_assignment_and_invalid_time_fail_closed(self) -> None:
        plan = self._plan()
        with self.assertRaises(OpenForcingContractError):
            type(plan)(**{**plan.__dict__, "assignments": ("unknown",) * plan.target_cell_count}).validate()

        with self.assertRaises(OpenForcingContractError):
            self._plan(points=(NativeForcingPoint("p", 34.1, 75.1),)).__class__(
                **{**plan.__dict__, "valid_times": (datetime(2026, 7, 31),)}
            ).validate()


if __name__ == "__main__":
    unittest.main()
