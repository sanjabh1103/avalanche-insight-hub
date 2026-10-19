from __future__ import annotations

import unittest
import hashlib
import json
from datetime import datetime, timezone

from backend.open_forcing.contracts import ASSIMILATION_DISCLOSURE, SourceSnapshot
from backend.scripts.replay_open_forcing_snapshot import (
    _canonical_hash,
    _validate_grid_descriptor,
    _validate_source_point_coverage,
)


def _grid() -> dict[str, object]:
    descriptor: dict[str, object] = {
        "construction": "projected_configured_grid_descriptor",
        "target_crs": "EPSG:32643",
        "target_resolution_m": 500.0,
        "rows": 2,
        "cols": 2,
        "cell_count": 4,
        "aoi_center_latitude": 34.0,
        "aoi_center_longitude": 75.0,
        "width_m": 1000.0,
        "height_m": 1000.0,
        "information_boundary": "grid spacing is not observational resolution",
    }
    descriptor["grid_manifest_hash"] = _canonical_hash(descriptor)
    return descriptor


class OpenForcingSnapshotReplayTests(unittest.TestCase):
    def test_grid_descriptor_hash_and_cell_count_are_verified(self) -> None:
        self.assertEqual(_validate_grid_descriptor(_grid()), 4)

    def test_grid_descriptor_tampering_fails_closed(self) -> None:
        tampered = _grid()
        tampered["rows"] = 3
        with self.assertRaisesRegex(RuntimeError, "dimensions are inconsistent|hash mismatch"):
            _validate_grid_descriptor(tampered)

    @staticmethod
    def _source_point_fixture() -> tuple[dict[str, object], SourceSnapshot, bytes]:
        raw = json.dumps(
            [{
                "latitude": 34.0,
                "longitude": 75.0,
                "hourly": {
                    "time": ["2026-07-31T00:00", "2026-07-31T01:00"],
                    "temperature_2m": [-5.0, -4.0],
                },
            }],
            separators=(",", ":"),
        ).encode()
        snapshot_time = datetime(2026, 7, 31, tzinfo=timezone.utc)
        snapshot = SourceSnapshot(
            source_id="open_meteo_nwp",
            product="selected NWP",
            issue_time=snapshot_time,
            valid_time=snapshot_time,
            retrieved_at=snapshot_time,
            source_as_of=snapshot_time,
            native_resolution_m=25_000.0,
            content_sha256=hashlib.sha256(raw).hexdigest(),
            license_id="pending-review",
            provider="open-meteo-single-runs",
            model_id="ecmwf_ifs025",
            run_id="2026-07-31T00:00",
            assimilation_disclosure=ASSIMILATION_DISCLOSURE,
        )
        record = {
            "source_id": "open_meteo_nwp",
            "provider": "open-meteo-single-runs",
            "model_id": "ecmwf_ifs025",
            "run_id": "2026-07-31T00:00",
            "aoi": {"min_latitude": 33.9, "min_longitude": 74.9, "max_latitude": 34.1, "max_longitude": 75.1},
            "target_rows": 1,
            "target_cols": 1,
            "target_resolution_m": 50_000.0,
            "native_resolution_m": 25_000.0,
            "required_variables": ["temperature_2m"],
            "valid_times": ["2026-07-31T00:00+00:00", "2026-07-31T01:00+00:00"],
            "native_points": [{"point_id": "p000", "latitude": 34.0, "longitude": 75.0}],
            "assignments": ["p000"],
            "max_assignment_distance_m": 10_000.0,
            "coverage_fraction": 1.0,
            "complete_spatial_coverage": True,
            "license_review_status": "pending",
            "can_enter_forcing_pipeline": False,
            "research_only": True,
            "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
        }
        return record, snapshot, raw

    def test_source_point_coverage_rebuilds_from_raw_payload(self) -> None:
        record, snapshot, raw = self._source_point_fixture()
        _validate_source_point_coverage(record, forecast_snapshot=snapshot, forecast_bytes=raw, cell_count=1)

    def test_source_point_assignment_tampering_fails_closed(self) -> None:
        record, snapshot, raw = self._source_point_fixture()
        record["assignments"] = [None]
        with self.assertRaisesRegex(RuntimeError, "assignments"):
            _validate_source_point_coverage(record, forecast_snapshot=snapshot, forecast_bytes=raw, cell_count=1)


if __name__ == "__main__":
    unittest.main()
