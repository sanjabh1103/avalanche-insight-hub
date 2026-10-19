from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.interval_training_preparation import (
    INTERVAL_TRAINING_PREPARATION_VERSION,
    IntervalTrainingPreparationError,
    build_interval_training_preparation_manifest,
    load_interval_training_preparation_manifest,
    write_interval_training_preparation_manifest,
)


def _frame() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, (year, source_key, family) in enumerate(
        (
            (2020, "hiaval_hma", "hiaval_literature_database"),
            (2020, "everest_sentinel1", "everest_sentinel1_satellite_detection"),
            (2021, "hiaval_hma", "hiaval_literature_database"),
            (2021, "everest_sentinel1", "everest_sentinel1_satellite_detection"),
            (2022, "hiaval_hma", "hiaval_literature_database"),
            (2022, "everest_sentinel1", "everest_sentinel1_satellite_detection"),
        )
    ):
        start = f"{year}-12-{index + 1:02d}T00:00:00Z"
        end = f"{year}-12-{index + 2:02d}T00:00:00Z"
        rows.append(
            {
                "row_id": f"row-{index}",
                "source_event_id": f"event-{index}",
                "event_group_id": f"group-{index}",
                "spatial_group_id": f"himalayas_nepal:{index}:0",
                "label": 1,
                "label_source": source_key,
                "origin_source_family": family,
                "feature_source_key": "era5",
                "feature_source_family": "open_weather_reanalysis",
                "region_key": "himalayas_nepal",
                "interval_start": start,
                "interval_end": end,
                "timestamp_precision": "day" if source_key == "hiaval_hma" else "interval",
                "feature_cutoff_at": start,
                "source_overlap_review_status": "reviewed",
                "license_review_id": f"license-{source_key}",
                "source_row_sha256": f"{index:064x}",
                "lat": 28.0 + index * 0.01,
                "lng": 86.0 + index * 0.01,
                "features": {"snowfall": float(index + 1)},
                "shadow_only": True,
                "core_training_eligible": False,
                "production_scoring_eligible": False,
            }
        )
    return rows


def _fixture(root: Path) -> tuple[
    Path,
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    frame_path = root / "interval_training_frame.jsonl"
    frame_rows = _frame()
    frame_payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in frame_rows).encode()
    frame_path.write_bytes(frame_payload)
    frame_hash = hashlib.sha256(frame_payload).hexdigest()
    label_hash = "a" * 64
    feature_hash = "b" * 64
    label_manifest = {
        "events_path": "events.jsonl",
        "event_rows_sha256": label_hash,
        "training_eligible": False,
        "production_scoring_eligible": False,
    }
    feature_manifest = {
        "manifest_hash": feature_hash,
        "source_manifests": {
            "era5": {
                "license_status": "pending",
                "cutoff_policy_review_status": "pending_scientist_approval",
            }
        },
        "feature_rows_sha256": "c" * 64,
        "training_eligible": False,
        "production_scoring_eligible": False,
    }
    join_report = {
        "status": "shadow_frame_written",
        "label_event_rows_sha256": label_hash,
        "feature_manifest_hash": feature_hash,
        "training_eligible": False,
        "production_scoring_eligible": False,
        "shadow_only": True,
        "evidence": {
            "snapshot_path": str(frame_path),
            "snapshot_hash": frame_hash,
            "snapshot_file_sha256": frame_hash,
            "row_count": len(frame_rows),
            "event_group_count": len(frame_rows),
            "spatial_group_count": len(frame_rows),
            "positive_season_ids": ["2020-2021", "2021-2022", "2022-2023"],
            "positive_source_ids": ["everest_sentinel1", "hiaval_hma"],
            "independent_positive_source_family_ids": [
                "everest_sentinel1_satellite_detection",
                "hiaval_literature_database",
            ],
            "source_family_counts": {
                "everest_sentinel1_satellite_detection": 3,
                "hiaval_literature_database": 3,
            },
            "split_boundaries": {
                "train": {"event_group_ids": ["group-0", "group-1", "group-2"]},
                "calibration": {"event_group_ids": ["group-3"]},
                "test": {"event_group_ids": ["group-4", "group-5"]},
            },
            "validation": {"passed": True},
            "shadow_only": True,
            "core_training_eligible": False,
            "production_scoring_eligible": False,
            "snapshot_provenance": {"feature_manifest_hash": feature_hash},
        },
    }
    return frame_path, label_manifest, feature_manifest, {
        "status": "shadow_frame_written",
        "label_event_rows_sha256": label_hash,
        "feature_manifest_hash": feature_hash,
        "training_eligible": False,
        "production_scoring_eligible": False,
        "shadow_only": True,
        "evidence": {
            "snapshot_path": str(frame_path),
            "snapshot_hash": frame_hash,
            "snapshot_file_sha256": frame_hash,
            "row_count": len(frame_rows),
            "event_group_count": len(frame_rows),
            "spatial_group_count": len(frame_rows),
            "positive_season_ids": ["2020-2021", "2021-2022", "2022-2023"],
            "positive_source_ids": ["everest_sentinel1", "hiaval_hma"],
            "independent_positive_source_family_ids": [
                "everest_sentinel1_satellite_detection",
                "hiaval_literature_database",
            ],
            "source_family_counts": {
                "everest_sentinel1_satellite_detection": 3,
                "hiaval_literature_database": 3,
            },
            "split_boundaries": {
                "train": {"event_group_ids": ["group-0", "group-1", "group-2"]},
                "calibration": {"event_group_ids": ["group-3"]},
                "test": {"event_group_ids": ["group-4", "group-5"]},
            },
            "validation": {"passed": True},
            "shadow_only": True,
            "core_training_eligible": False,
            "production_scoring_eligible": False,
            "snapshot_provenance": {"feature_manifest_hash": feature_hash},
        },
    }


class IntervalTrainingPreparationTests(unittest.TestCase):
    def test_builds_content_addressed_shadow_only_preparation_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, label_manifest, feature_manifest, join_report = _fixture(root)
            manifest = build_interval_training_preparation_manifest(
                label_manifest=label_manifest,
                feature_manifest=feature_manifest,
                join_report=join_report,
            )
            self.assertEqual(manifest["schema_version"], INTERVAL_TRAINING_PREPARATION_VERSION)
            self.assertEqual(manifest["training_path_status"], "implemented_shadow_only")
            self.assertTrue(manifest["shadow_evidence_ready"])
            self.assertFalse(manifest["training_eligible"])
            self.assertFalse(manifest["core_training_eligible"])
            self.assertFalse(manifest["production_scoring_eligible"])
            self.assertTrue(manifest["contract"]["point_time_synthesis_forbidden"])
            self.assertEqual(manifest["contract"]["negative_sampling_status"], "defined_shadow_only")
            self.assertEqual(
                manifest["contract"]["interval_loss_implementation_status"],
                "defined_shadow_only",
            )

            output = root / "interval_training_preparation_manifest.json"
            written = write_interval_training_preparation_manifest(output, manifest)
            loaded = load_interval_training_preparation_manifest(output)
            self.assertEqual(written["manifest_hash"], loaded["manifest_hash"])
            self.assertEqual(loaded["manifest_hash"], manifest["manifest_hash"])

    def test_rejects_promoted_join_evidence(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            frame_path, label_manifest, feature_manifest, join_report = _fixture(root)
            frame_hash = hashlib.sha256(frame_path.read_bytes()).hexdigest()
            self.assertEqual(frame_hash, join_report["evidence"]["snapshot_hash"])
            join_report["training_eligible"] = True
            with self.assertRaisesRegex(IntervalTrainingPreparationError, "training_eligible"):
                build_interval_training_preparation_manifest(
                    label_manifest=label_manifest,
                    feature_manifest=feature_manifest,
                    join_report=join_report,
                )


if __name__ == "__main__":
    unittest.main()
