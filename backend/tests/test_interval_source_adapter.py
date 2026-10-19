from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.interval_source_adapter import (
    IntervalSourceAdapterError,
    build_interval_label_staging,
    write_interval_label_staging,
)


def _write_source(root: Path, name: str, source_key: str, year: int) -> Path:
    directory = root / name
    directory.mkdir()
    rows = []
    for index in range(3):
        start = f"{year + index}-12-01T00:00:00Z"
        end = f"{year + index}-12-02T00:00:00Z"
        rows.append({
            "source_event_id": f"{source_key}-{index}",
            "event_group_id": f"{source_key}:group:{index}",
            "source_key": source_key,
            "origin_source_family": f"{source_key}:family",
            "region_key": "himalayas_nepal",
            "lat": 28.0 + index * 0.01,
            "lng": 86.0 + index * 0.01,
            "label": 1,
            "event_time_start": start,
            "event_time_end": end,
            "timestamp_precision": "day" if source_key == "hiaval_hma" else "bounded_12_day_detection_interval",
            "source_row_sha256": hashlib.sha256(f"{source_key}-{index}".encode()).hexdigest(),
        })
    payload = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )
    manifest = {
        "source_key": source_key,
        "events_path": "events.jsonl",
        "event_rows_sha256": hashlib.sha256(payload).hexdigest(),
        "license": "CC BY 4.0",
        "license_status": "permissive_core_reviewed" if source_key == "hiaval_hma" else "permissive_shadow_reviewed",
        "license_review_id": f"review-{source_key}",
        "source_role": "test_source",
    }
    (directory / "events.jsonl").write_bytes(payload)
    (directory / "snapshot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


class IntervalSourceAdapterTests(unittest.TestCase):
    def _overlap(self, root: Path) -> Path:
        path = root / "overlap.json"
        path.write_text(json.dumps({
            "status": "reviewed",
            "source_a": "hiaval_hma",
            "source_b": "everest_sentinel1",
            "independent_positive_source_count": 2,
            "same_event_must_not_count_as_independent": True,
        }), encoding="utf-8")
        return path

    def test_builds_nepal_staging_rows_without_point_time_or_activation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hiaval = _write_source(root, "hiaval", "hiaval_hma", 2020)
            everest = _write_source(root, "everest", "everest_sentinel1", 2020)
            rows, manifest, _ = build_interval_label_staging(
                [hiaval, everest],
                overlap_report_path=self._overlap(root),
                region_keys=["himalayas_nepal"],
            )

            self.assertEqual(len(rows), 6)
            self.assertEqual(manifest["positive_season_count"], 3)
            self.assertEqual(manifest["required_independent_positive_sources"], ["everest_sentinel1", "hiaval_hma"])
            self.assertEqual(manifest["label_time_contract"], "interval_censored_core_v1")
            self.assertFalse(manifest["training_eligible"])
            self.assertFalse(manifest["interval_training_ready"])
            for row in rows:
                self.assertNotIn("event_time", row)
                self.assertNotIn("timestamp", row)
                self.assertTrue(row["feature_join_key"].startswith("himalayas_nepal:"))
                self.assertIsNone(row["feature_cutoff_at"])
                self.assertEqual(row["feature_cutoff_status"], "pending_explicit_feature_snapshot")
                self.assertFalse(row["core_training_eligible"])
                self.assertTrue(row["license_review_id"])

    def test_output_is_hash_stable_and_rejects_unreviewed_overlap(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hiaval = _write_source(root, "hiaval", "hiaval_hma", 2020)
            everest = _write_source(root, "everest", "everest_sentinel1", 2020)
            overlap = self._overlap(root)
            rows, manifest, payload = build_interval_label_staging(
                [hiaval, everest], overlap_report_path=overlap, region_keys=["himalayas_nepal"]
            )
            output = root / "output"
            write_interval_label_staging(output, rows, manifest, payload)
            event_payload = (output / "events.jsonl").read_bytes()
            stored = json.loads((output / "snapshot_manifest.json").read_text())
            self.assertEqual(stored["event_rows_sha256"], hashlib.sha256(event_payload).hexdigest())
            self.assertEqual(stored["event_rows_sha256"], manifest["event_rows_sha256"])

            bad = json.loads(overlap.read_text())
            bad["status"] = "computed_pending_review"
            overlap.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaisesRegex(IntervalSourceAdapterError, "must be reviewed"):
                build_interval_label_staging(
                    [hiaval, everest], overlap_report_path=overlap, region_keys=["himalayas_nepal"]
                )

    def test_missing_source_license_review_is_fail_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hiaval = _write_source(root, "hiaval", "hiaval_hma", 2020)
            everest = _write_source(root, "everest", "everest_sentinel1", 2020)
            manifest_path = everest / "snapshot_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest.pop("license_review_id")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(IntervalSourceAdapterError, "license_review_id"):
                build_interval_label_staging(
                    [hiaval, everest], overlap_report_path=self._overlap(root), region_keys=["himalayas_nepal"]
                )


if __name__ == "__main__":
    unittest.main()
