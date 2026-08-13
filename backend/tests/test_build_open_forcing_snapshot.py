from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.open_forcing.contracts import ASSIMILATION_DISCLOSURE, SourceSnapshot
from backend.open_forcing.coverage import construct_aoi_coverage_plan
from backend.open_forcing.open_meteo_source import OpenMeteoRunRequest, parse_open_meteo_single_run
from backend.scripts.build_open_forcing_snapshot import (
    _aoi_bounds,
    _coverage_mask_from_plan,
    _grid_descriptor,
    _model_grid_points,
    _resolve_region,
)


def _snapshot() -> SourceSnapshot:
    timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
    snapshot = SourceSnapshot(
        source_id="open_meteo_nwp",
        product="selected NWP",
        issue_time=timestamp,
        valid_time=timestamp,
        retrieved_at=timestamp,
        source_as_of=timestamp,
        native_resolution_m=25_000.0,
        content_sha256="a" * 64,
        license_id="pending-review",
        provider="open-meteo-single-runs",
        model_id="ecmwf_ifs025",
        run_id="2026-07-31T00:00",
        assimilation_disclosure=ASSIMILATION_DISCLOSURE,
    )
    snapshot.validate()
    return snapshot


class BuildOpenForcingSnapshotTests(unittest.TestCase):
    def test_region_key_resolves_configured_nepal_center(self) -> None:
        import argparse

        args = argparse.Namespace(region_key="himalayas_nepal", latitude=34.0, longitude=75.0)
        record = _resolve_region(args)

        self.assertEqual(record["key"], "himalayas_nepal")
        self.assertEqual(record["center"], [28.0, 86.25])
        self.assertEqual((args.latitude, args.longitude), (28.0, 86.25))

    def test_model_grid_is_deterministic_three_by_three(self) -> None:
        points = _model_grid_points(34.0, 75.0, spacing_deg=0.25, radius=1)
        self.assertEqual(len(points), 9)
        self.assertEqual(
            [(point.latitude, point.longitude) for point in points],
            [
                (33.75, 74.75),
                (33.75, 75.0),
                (33.75, 75.25),
                (34.0, 74.75),
                (34.0, 75.0),
                (34.0, 75.25),
                (34.25, 74.75),
                (34.25, 75.0),
                (34.25, 75.25),
            ],
        )

    def test_native_coverage_is_complete_without_claiming_target_values(self) -> None:
        points = _model_grid_points(34.0, 75.0, spacing_deg=0.25, radius=1)
        request = OpenMeteoRunRequest(
            latitudes=tuple(point.latitude for point in points),
            longitudes=tuple(point.longitude for point in points),
            model_id="ecmwf_ifs025",
            run_id="2026-07-31T00:00",
            forecast_hours=3,
            hourly_variables=("temperature_2m",),
        )
        response = [
            {
                "latitude": point.latitude,
                "longitude": point.longitude,
                "hourly": {
                    "time": [
                        "2026-07-31T00:00",
                        "2026-07-31T01:00",
                        "2026-07-31T02:00",
                    ],
                    "temperature_2m": [-5.0, -4.5, -4.0],
                },
            }
            for point in points
        ]
        payload = parse_open_meteo_single_run(response, request)
        plan = construct_aoi_coverage_plan(
            source_id="open_meteo_nwp",
            provider="open-meteo-single-runs",
            model_id="ecmwf_ifs025",
            run_id="2026-07-31T00:00",
            aoi=_aoi_bounds(34.0, 75.0),
            target_rows=100,
            target_cols=100,
            target_resolution_m=500.0,
            native_resolution_m=25_000.0,
            required_variables=request.hourly_variables,
            valid_times=payload.points[0].times,
            native_points=tuple(point.point for point in payload.points),
            license_review_status="pending",
        )
        plan.validate()
        self.assertTrue(plan.complete_spatial_coverage)
        self.assertFalse(plan.can_enter_forcing_pipeline)
        self.assertEqual(plan.effective_information_scale_m, 25_000.0)
        mask, record = _coverage_mask_from_plan(_snapshot(), _grid_descriptor(34.0, 75.0, 500.0), plan.assignments)
        self.assertEqual(mask.coverage_fraction, 1.0)
        self.assertEqual(record["coverage_method"], "nearest_native_source_point_assignment_only")


if __name__ == "__main__":
    unittest.main()
