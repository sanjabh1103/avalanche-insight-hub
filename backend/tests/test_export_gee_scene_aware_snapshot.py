from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from backend import gee_extractor
from backend.scripts.export_gee_scene_aware_snapshot import (
    GEE_SCENE_AWARE_SNAPSHOT_VERSION,
    _gee_request_deadline,
    build_snapshot,
    collect_from_gee,
    iter_chunk_windows,
    write_snapshot,
)


def _raw_event(*, scene_ids: list[str], region_key: str = "himalayas_nepal") -> dict[str, object]:
    return {
        "source": "gee_sar",
        "location": "SRID=4326;POINT(86.10 28.10)",
        "source_scene_ids": scene_ids,
        "features": {
            "region_key": region_key,
            "sar_window_start": "2021-11-01T00:00:00Z",
            "sar_window_end": "2022-04-30T00:00:00Z",
            "sar_scene_ids": scene_ids,
            "scene_count": len(scene_ids),
            "scene_lineage_refs": [
                {
                    "scene_id": scene_id,
                    "acquisition_time": f"2022-01-{15 + index:02d}T00:00:00+00:00",
                }
                for index, scene_id in enumerate(scene_ids)
            ],
            "scene_lineage_sha256": "a" * 64,
            "sar_centroid": {"lat": 28.10, "lng": 86.10},
        },
    }


class GeeSceneAwareSnapshotTests(unittest.TestCase):
    def test_request_deadline_is_applied_and_restored(self) -> None:
        state = SimpleNamespace(deadline_ms=2500.0)
        calls: list[float] = []

        def set_deadline(value: float) -> None:
            calls.append(value)
            state.deadline_ms = value

        gee_module = SimpleNamespace(
            data=SimpleNamespace(setDeadline=set_deadline, _get_state=lambda: state)
        )
        with _gee_request_deadline(gee_module, 12.5):
            self.assertEqual(state.deadline_ms, 12500.0)
        self.assertEqual(state.deadline_ms, 2500.0)
        self.assertEqual(calls, [12500.0, 2500.0])

    def test_builds_bounded_rows_without_point_time_synthesis(self) -> None:
        rows, manifest, scenes = build_snapshot(
            {"himalayas_nepal": [_raw_event(scene_ids=["S1", "S2"])]}
        )
        self.assertEqual(manifest["snapshot_schema_version"], GEE_SCENE_AWARE_SNAPSHOT_VERSION)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("event_time", rows[0])
        self.assertNotIn("timestamp", rows[0])
        self.assertEqual(rows[0]["timestamp_precision"], "interval")
        self.assertFalse(rows[0]["training_eligible"])
        self.assertEqual(rows[0]["license_status"], "pending_rights_review")
        self.assertEqual(manifest["label_time_contract"], "interval_censored_core_v1")
        self.assertEqual(manifest["license_status"], "pending_rights_review")
        self.assertEqual(
            manifest["license_terms_url"],
            "https://developers.google.com/earth-engine/reference/Additional.API.Terms",
        )
        self.assertIn("account/use/output scope", manifest["license_reuse_scope"])
        self.assertEqual(manifest["positive_source_ids"], ["gee_sar_scene_aware"])
        self.assertEqual(
            manifest["target_regions"],
            {"himalayas_nepal": {"season_start_month": 11}},
        )
        self.assertFalse(manifest["interval_training_ready"])
        self.assertEqual(
            manifest["feature_cutoff_status"],
            "pending_explicit_feature_snapshot",
        )
        self.assertEqual(manifest["exact_timestamp_record_count"], 0)
        self.assertEqual(manifest["positive_season_ids"], ["2021-2022"])
        self.assertEqual(len(scenes), 2)

    def test_missing_scene_ids_are_excluded(self) -> None:
        rows, manifest, scenes = build_snapshot(
            {"himalayas_nepal": [_raw_event(scene_ids=[])]}
        )
        self.assertEqual(rows, [])
        self.assertEqual(scenes, [])
        self.assertEqual(manifest["excluded_record_counts"], {"missing_scene_ids": 1})
        self.assertFalse(manifest["training_eligible"])

    def test_snow_season_windows_skip_out_of_season_requests(self) -> None:
        windows = list(
            iter_chunk_windows(
                region_key="himalayas_nepal",
                start=datetime(2021, 11, 1, tzinfo=timezone.utc),
                end=datetime(2024, 5, 1, tzinfo=timezone.utc),
                chunk_days=30,
                snow_season_only=True,
            )
        )
        self.assertTrue(windows)
        self.assertTrue(all(window[0].month in {1, 2, 3, 4, 11, 12} for window in windows))
        self.assertFalse(any(window[0].month in {5, 6, 7, 8, 9, 10} for window in windows))
        self.assertEqual(windows[0][0].isoformat(), "2021-11-01T00:00:00+00:00")
        self.assertEqual(windows[-1][1].isoformat(), "2024-05-01T00:00:00+00:00")

    def test_collection_reuses_valid_chunk_cache_without_remote_calls(self) -> None:
        raw = _raw_event(scene_ids=["S1"])
        raw["features"].pop("sar_window_start")
        raw["features"].pop("sar_window_end")
        region = SimpleNamespace(key="himalayas_nepal")
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "chunks"
            with (
                patch.object(gee_extractor, "_initialize_ee", return_value=object()) as init,
                patch.object(gee_extractor, "_process_region", return_value=[raw]) as process,
                patch("backend.common.regions.load_regions", return_value=[region]),
            ):
                first_rows, _, _ = collect_from_gee(
                    region_keys=[region.key],
                    start=datetime(2023, 11, 1, tzinfo=timezone.utc),
                    end=datetime(2024, 2, 1, tzinfo=timezone.utc),
                    chunk_days=30,
                    cache_dir=cache_dir,
                    progress=False,
                )
                init.reset_mock()
                process.reset_mock()
                second_rows, _, _ = collect_from_gee(
                    region_keys=[region.key],
                    start=datetime(2023, 11, 1, tzinfo=timezone.utc),
                    end=datetime(2024, 2, 1, tzinfo=timezone.utc),
                    chunk_days=30,
                    cache_dir=cache_dir,
                    progress=False,
                )
            self.assertEqual(second_rows, first_rows)
            self.assertEqual(first_rows[0]["event_time_start"], "2023-11-01T00:00:00Z")
            self.assertEqual(first_rows[0]["event_time_end"], "2023-12-01T00:00:00Z")
            self.assertEqual(
                first_rows[0]["metadata"]["query_window_source"],
                "gee_filter_date_bounds",
            )
            init.assert_not_called()
            process.assert_not_called()
            self.assertEqual(len(list(cache_dir.rglob("*.json"))), 4)

    def test_incomplete_scene_lineage_cache_is_refreshed_when_required(self) -> None:
        incomplete = _raw_event(scene_ids=["S1"])
        incomplete["features"].pop("scene_lineage_refs")
        complete = _raw_event(scene_ids=["S1"])
        region = SimpleNamespace(key="himalayas_nepal")
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "chunks"
            with (
                patch.object(gee_extractor, "_initialize_ee", return_value=object()) as init,
                patch.object(gee_extractor, "_process_region", return_value=[incomplete]) as process,
                patch("backend.common.regions.load_regions", return_value=[region]),
            ):
                collect_from_gee(
                    region_keys=[region.key],
                    start=datetime(2023, 11, 1, tzinfo=timezone.utc),
                    end=datetime(2023, 12, 1, tzinfo=timezone.utc),
                    chunk_days=30,
                    cache_dir=cache_dir,
                    progress=False,
                )
                process.reset_mock()
                init.reset_mock()
                process.return_value = [complete]
                rows, _, _ = collect_from_gee(
                    region_keys=[region.key],
                    start=datetime(2023, 11, 1, tzinfo=timezone.utc),
                    end=datetime(2023, 12, 1, tzinfo=timezone.utc),
                    chunk_days=30,
                    cache_dir=cache_dir,
                    progress=False,
                    require_scene_acquisition_times=True,
                )
            self.assertEqual(len(rows), 1)
            init.assert_called_once()
            process.assert_called_once()

    def test_write_snapshot_validates_event_scene_and_manifest_hashes(self) -> None:
        rows, manifest, scenes = build_snapshot(
            {"himalayas_nepal": [_raw_event(scene_ids=["S1", "S2"])]}
        )
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "snapshot"
            write_snapshot(output, rows, manifest, scenes)
            events = output / "events.jsonl"
            scene_file = output / "source_scenes.jsonl"
            written = json.loads((output / "snapshot_manifest.json").read_text())
            self.assertEqual(written["event_rows_sha256"], hashlib.sha256(events.read_bytes()).hexdigest())
            self.assertEqual(written["scene_manifest_sha256"], hashlib.sha256(scene_file.read_bytes()).hexdigest())
            self.assertEqual(written["manifest_hash"], manifest["manifest_hash"])


if __name__ == "__main__":
    unittest.main()
