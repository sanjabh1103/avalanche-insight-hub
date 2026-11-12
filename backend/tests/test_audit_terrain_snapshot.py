from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.common.real_features import TerrainUnavailableError
from backend.scripts.audit_terrain_snapshot import audit_snapshot


def _write_snapshot(root: Path, rows: list[dict[str, object]]) -> Path:
    events_path = root / "events.jsonl"
    payload = b"".join(
        (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        for row in rows
    )
    events_path.write_bytes(payload)
    manifest_path = root / "snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "events_path": events_path.name,
                "event_rows_sha256": hashlib.sha256(payload).hexdigest(),
                "source_key": "fixture_source",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


class AuditTerrainSnapshotTests(unittest.TestCase):
    def test_reports_stable_reasons_and_source_season_breakdowns(self) -> None:
        rows = [
            {
                "external_id": "ok-1",
                "event_group_id": "group-ok-1",
                "source_key": "hiaval_hma",
                "event_time": "2020-11-03T00:00:00Z",
                "region_key": "himalayas_nepal",
                "lat": 28.0,
                "lng": 86.0,
            },
            {
                "external_id": "bad-1",
                "event_group_id": "group-bad-1",
                "source_key": "everest_sentinel1",
                "event_time_start": "2021-11-03T00:00:00Z",
                "event_time_end": "2021-11-15T00:00:00Z",
                "region_key": "himalayas_nepal",
                "lat": 28.1,
                "lng": 86.1,
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = _write_snapshot(root, rows)
            dem_root = root / "dem"
            dem_root.mkdir()
            (dem_root / "himalayas_nepal.tif").touch()

            def terrain_for_row(_path: str, *, lat: float, lng: float) -> dict[str, float]:
                if lat > 28.05:
                    raise TerrainUnavailableError("no valid DEM window")
                return {
                    "elevation_m": 4000.0,
                    "slope_angle_deg": 35.0,
                    "aspect_deg": 180.0,
                    "terrain_roughness": 1.0,
                    "curvature_proxy": 0.1,
                }

            with patch(
                "backend.scripts.audit_terrain_snapshot.extract_cell_terrain",
                side_effect=terrain_for_row,
            ):
                report = audit_snapshot(
                    manifest_path,
                    region_keys=["himalayas_nepal"],
                    dem_root=dem_root,
                )

        self.assertEqual(report["snapshot_row_count"], 2)
        self.assertEqual(report["candidate_rows"], 2)
        self.assertEqual(report["terrain_success"], 1)
        self.assertEqual(report["terrain_loss_count"], 1)
        self.assertEqual(report["failure_reasons"], {"invalid_or_nodata_window": 1})
        self.assertEqual(
            report["failure_reasons_by_source"],
            {"everest_sentinel1": {"invalid_or_nodata_window": 1}},
        )
        self.assertEqual(
            report["failure_reasons_by_season"],
            {"2021-2022": {"invalid_or_nodata_window": 1}},
        )
        self.assertEqual(report["gate_errors"], ["terrain loss rate 0.500000 exceeds 0.020000"])
        self.assertEqual(report["failure_records"][0]["event_group_id"], "group-bad-1")

    def test_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = _write_snapshot(
                root,
                [
                    {
                        "external_id": "one",
                        "region_key": "himalayas_nepal",
                        "lat": 28.0,
                        "lng": 86.0,
                    }
                ],
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["event_rows_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "event snapshot hash mismatch"):
                audit_snapshot(manifest_path, dem_root=root)

    def test_default_dem_root_is_repo_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = _write_snapshot(
                root,
                [
                    {
                        "external_id": "one",
                        "region_key": "himalayas_nepal",
                        "lat": 28.0,
                        "lng": 86.0,
                    }
                ],
            )
            expected_dem = root / "backend" / "data" / "dem" / "himalayas_nepal.tif"
            expected_dem.parent.mkdir(parents=True)
            expected_dem.touch()

            with patch("backend.scripts.audit_terrain_snapshot.repo_root", return_value=root), patch(
                "backend.scripts.audit_terrain_snapshot.extract_cell_terrain",
                return_value={"elevation_m": 4000.0},
            ) as extractor:
                report = audit_snapshot(
                    manifest_path,
                    region_keys=["himalayas_nepal"],
                )

        self.assertEqual(report["terrain_success"], 1)
        self.assertEqual(extractor.call_args.args[0], str(expected_dem))


if __name__ == "__main__":
    unittest.main()
