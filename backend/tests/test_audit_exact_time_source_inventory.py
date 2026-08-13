from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.audit_exact_time_source_inventory import (
    build_bounded_interval_gap_report,
    build_evidence_inventory,
)


def _write_snapshot(root: Path, name: str, manifest: dict, rows: list[dict]) -> Path:
    snapshot_dir = root / name
    snapshot_dir.mkdir()
    payload = b"".join(
        (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        for row in rows
    )
    (snapshot_dir / "events.jsonl").write_bytes(payload)
    (snapshot_dir / "snapshot_manifest.json").write_text(
        json.dumps(
            {
                "events_path": "events.jsonl",
                "event_rows_sha256": hashlib.sha256(payload).hexdigest(),
                **manifest,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return snapshot_dir / "snapshot_manifest.json"


class ExactTimeSourceInventoryTests(unittest.TestCase):
    def test_inventory_ignores_station_free_feature_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_snapshot(
                root,
                "label",
                {
                    "source_key": "label_source",
                    "source_keys": ["label_source"],
                    "license_status": "permissive_core_reviewed",
                    "training_eligible": False,
                },
                [{
                    "event_time": "2023-11-03T12:00:00Z",
                    "timestamp_precision": "timestamp",
                    "region_key": "himalayas_nepal",
                    "source_key": "label_source",
                }],
            )
            feature_dir = root / "feature-only"
            feature_dir.mkdir()
            feature_payload = b'{"feature": 1}\n'
            (feature_dir / "features.jsonl").write_bytes(feature_payload)
            (feature_dir / "snapshot_manifest.json").write_text(
                json.dumps({
                    "snapshot_schema_version": "mvp4_station_free_feature_snapshot_v1",
                    "source_key": "mvp4_station_free_feature_snapshot",
                    "feature_rows_path": "features.jsonl",
                    "feature_rows_sha256": hashlib.sha256(feature_payload).hexdigest(),
                }),
                encoding="utf-8",
            )

            inventory = build_evidence_inventory(root)

        self.assertEqual(inventory["summary"]["snapshot_count"], 1)
        self.assertNotIn(
            "mvp4_station_free_feature_snapshot",
            {item["source_key"] for item in inventory["snapshots"]},
        )

    def test_inventory_separates_exact_day_interval_and_derived_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_snapshot(
                root,
                "exact",
                {
                    "source_key": "exact_source",
                    "source_keys": ["exact_source"],
                    "license_status": "permissive_core_reviewed",
                    "training_eligible": False,
                    "event_time_semantics": "independent_observed_occurrence_time",
                    "source_time_review_status": "approved_occurrence_time",
                    "source_time_review_id": "fixture-time-review-1",
                },
                [
                    {
                        "event_time": "2023-11-03T12:00:00Z",
                        "timestamp_precision": "timestamp",
                        "region_key": "himalayas_nepal",
                        "source_key": "exact_source",
                    }
                ],
            )
            _write_snapshot(
                root,
                "day",
                {
                    "source_key": "day_source",
                    "source_keys": ["day_source"],
                    "license_status": "permissive_core_reviewed",
                    "training_eligible": False,
                },
                [
                    {
                        "event_time": "2023-11-04T00:00:00Z",
                        "timestamp_precision": "day",
                        "region_key": "himalayas_nepal",
                        "source_key": "day_source",
                    }
                ],
            )
            interval_row = {
                "event_time_start": "2023-11-05T00:00:00Z",
                "event_time_end": "2023-11-17T00:00:00Z",
                "timestamp_precision": "bounded_12_day_detection_interval",
                "region_key": "himalayas_nepal",
                "source_key": "interval_source",
            }
            _write_snapshot(
                root,
                "interval",
                {
                    "source_key": "interval_source",
                    "source_keys": ["interval_source"],
                    "license_status": "permissive_shadow_reviewed",
                    "training_eligible": False,
                },
                [interval_row],
            )
            _write_snapshot(
                root,
                "catalog",
                {
                    "source_key": "derived_catalog",
                    "source_keys": ["exact_source", "day_source"],
                    "license_status": "reviewed",
                    "training_eligible": False,
                },
                [dict(interval_row, source_key="day_source")],
            )

            inventory = build_evidence_inventory(root)

        self.assertEqual(inventory["summary"]["snapshot_count"], 4)
        self.assertEqual(inventory["summary"]["exact_timestamp_record_count"], 1)
        self.assertEqual(inventory["summary"]["day_record_count"], 1)
        self.assertEqual(inventory["summary"]["bounded_interval_record_count"], 1)
        self.assertEqual(inventory["summary"]["derived_catalog_count"], 1)
        self.assertEqual(inventory["summary"]["core_exact_time_source_count"], 0)
        exact = next(item for item in inventory["snapshots"] if item["source_key"] == "exact_source")
        self.assertTrue(exact["exact_time_candidate"])
        self.assertTrue(exact["exact_time_reviewed"])
        self.assertTrue(exact["qualified_exact_time_candidate"])
        self.assertIn("manifest_training_eligible_false", exact["blockers"])

    def test_unreviewed_exact_rows_are_not_qualified_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_snapshot(
                root,
                "unreviewed-exact",
                {
                    "source_key": "unreviewed_exact_source",
                    "source_keys": ["unreviewed_exact_source"],
                    "license_status": "permissive_core_reviewed",
                    "training_eligible": True,
                },
                [{
                    "event_time": "2023-11-03T12:00:00Z",
                    "timestamp_precision": "timestamp",
                    "region_key": "himalayas_nepal",
                    "source_key": "unreviewed_exact_source",
                }],
            )

            inventory = build_evidence_inventory(root)

        record = inventory["snapshots"][0]
        self.assertTrue(record["exact_time_candidate"])
        self.assertFalse(record["exact_time_reviewed"])
        self.assertFalse(record["qualified_exact_time_candidate"])
        self.assertIn("exact_occurrence_time_review_not_approved", record["blockers"])
        self.assertEqual(inventory["summary"]["qualified_exact_time_candidate_count"], 0)

    def test_hash_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = _write_snapshot(
                Path(tmpdir),
                "broken",
                {"source_key": "broken_source"},
                [{"event_time": "2023-11-03T00:00:00Z", "timestamp_precision": "timestamp"}],
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["event_rows_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "event snapshot hash mismatch"):
                build_evidence_inventory(Path(tmpdir))

    def test_explicit_day_precision_wins_over_day_envelope_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_snapshot(
                root,
                "day-envelope",
                {"source_key": "day_source"},
                [
                    {
                        "event_time": "2023-11-03T00:00:00Z",
                        "event_time_start": "2023-11-03T00:00:00Z",
                        "event_time_end": "2023-11-04T00:00:00Z",
                        "timestamp_precision": "day",
                    }
                ],
            )

            inventory = build_evidence_inventory(root)

        self.assertEqual(inventory["summary"]["day_record_count"], 1)
        self.assertEqual(inventory["summary"]["bounded_interval_record_count"], 0)

    def test_interval_gap_report_never_substitutes_a_midpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_snapshot(
                root,
                "interval",
                {
                    "source_key": "interval_source",
                    "source_keys": ["interval_source"],
                    "license_status": "permissive_shadow_reviewed",
                    "training_eligible": False,
                },
                [
                    {
                        "event_time_start": "2023-11-03T00:00:00Z",
                        "event_time_end": "2023-11-15T00:00:00Z",
                        "timestamp_precision": "bounded_12_day_detection_interval",
                        "region_key": "himalayas_nepal",
                        "source_key": "interval_source",
                    }
                ],
            )

            report = build_bounded_interval_gap_report(root)

        self.assertEqual(report["summary"]["bounded_interval_record_count"], 1)
        self.assertEqual(report["summary"]["exact_occurrence_timestamp_record_count"], 0)
        self.assertFalse(report["summary"]["midpoint_substitution_used"])
        entry = report["sources"][0]
        self.assertEqual(entry["interval_width_days"], {"min": 12.0, "max": 12.0, "mean": 12.0, "median": 12.0})
        self.assertIn("no_exact_event_timestamp_in_rows", entry["gap_reason_codes"])


if __name__ == "__main__":
    unittest.main()
