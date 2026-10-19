from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.interval_training_reproducibility import (
    IntervalTrainingReproducibilityError,
    IntervalTrainingReproducibilityConfig,
    build_interval_training_evidence,
    build_interval_training_frame,
    build_interval_training_frame_from_staging,
    evaluate_interval_training_staging_join,
    validate_interval_training_frame,
)


def _label(index: int, *, source_key: str, year: int, **overrides):
    start = f"{year}-12-{index + 1:02d}T00:00:00Z"
    end = f"{year}-12-{index + 2:02d}T00:00:00Z"
    row = {
        "source_event_id": f"{source_key}-event-{index}",
        "event_group_id": f"{source_key}:group:{index}",
        "source_key": source_key,
        "origin_source_family": f"{source_key}:independent_family",
        "region_key": "himalayas_nepal",
        "feature_join_key": f"nepal-cell-{index}",
        "event_time_start": start,
        "event_time_end": end,
        "timestamp_precision": "day" if source_key == "hiaval_hma" else "interval",
        "feature_cutoff_at": f"{year}-12-{index + 1:02d}T00:00:00Z",
        "source_overlap_review_status": "reviewed",
        "license_review_id": f"license-review-{source_key}",
        "source_row_sha256": f"{index:064x}",
        "lat": 28.0 + index * 0.01,
        "lng": 86.0 + index * 0.01,
        "label": 1,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
    }
    row.update(overrides)
    return row


def _feature(index: int, *, year: int, **overrides):
    start = f"{year}-12-{index + 1:02d}T00:00:00Z"
    end = f"{year}-12-{index + 2:02d}T00:00:00Z"
    row = {
        "feature_id": f"weather-feature-{index}",
        "source_key": "open_meteo",
        "source_family": "open_weather_nwp",
        "region_key": "himalayas_nepal",
        "feature_join_key": f"nepal-cell-{index}",
        "feature_valid_from": start,
        "feature_valid_until": f"{year}-12-{index + 3:02d}T00:00:00Z",
        "feature_cutoff_at": start,
        "features": {"snowfall_24h": float(index + 1), "wind_speed": 8.0},
        "production_eligible": False,
    }
    row.update(overrides)
    return row


def _fixture():
    labels = []
    features = []
    for index, (source_key, year) in enumerate(
        (
            ("hiaval_hma", 2020),
            ("everest_sentinel1", 2020),
            ("hiaval_hma", 2021),
            ("everest_sentinel1", 2021),
            ("hiaval_hma", 2022),
            ("everest_sentinel1", 2022),
        )
    ):
        labels.append(_label(index, source_key=source_key, year=year))
        features.append(_feature(index, year=year))
    return labels, features


class IntervalTrainingReproducibilityTests(unittest.TestCase):
    def test_frame_preserves_intervals_groups_and_shadow_flags(self) -> None:
        labels, features = _fixture()

        frame = build_interval_training_frame(labels, features)

        self.assertEqual(len(frame), 6)
        first_label = next(row for row in frame if row["source_event_id"] == "hiaval_hma-event-0")
        self.assertNotIn("timestamp", first_label)
        self.assertNotIn("event_time", first_label)
        self.assertEqual(first_label["interval_start"], "2020-12-01T00:00:00Z")
        self.assertEqual(first_label["interval_end"], "2020-12-02T00:00:00Z")
        self.assertTrue(all(row["shadow_only"] for row in frame))
        self.assertTrue(all(not row["core_training_eligible"] for row in frame))
        self.assertTrue(all(not row["production_scoring_eligible"] for row in frame))
        self.assertTrue(all(row["event_group_id"] for row in frame))

        validation = validate_interval_training_frame(frame)
        self.assertTrue(validation["passed"])
        self.assertEqual(validation["precision_counts"], {"day": 3, "interval": 3})

    def test_evidence_hash_and_splits_are_order_independent(self) -> None:
        labels, features = _fixture()
        frame = build_interval_training_frame(labels, features)

        forward = build_interval_training_evidence(frame)
        reverse = build_interval_training_evidence(list(reversed(copy.deepcopy(frame))))

        self.assertEqual(forward["snapshot_hash"], reverse["snapshot_hash"])
        self.assertEqual(forward["split_boundaries"], reverse["split_boundaries"])
        self.assertEqual(forward["positive_season_ids"], ["2020-2021", "2021-2022", "2022-2023"])
        self.assertEqual(
            forward["positive_source_ids"],
            ["everest_sentinel1", "hiaval_hma"],
        )
        self.assertEqual(
            forward["independent_positive_source_family_ids"],
            ["everest_sentinel1:independent_family", "hiaval_hma:independent_family"],
        )
        self.assertFalse(forward["core_training_eligible"])
        self.assertFalse(forward["production_scoring_eligible"])

    def test_evidence_enforces_season_and_independent_family_minima(self) -> None:
        labels, features = _fixture()
        frame = build_interval_training_frame(labels, features)

        with self.assertRaisesRegex(IntervalTrainingReproducibilityError, "positive seasons"):
            build_interval_training_evidence(
                frame,
                config=IntervalTrainingReproducibilityConfig(minimum_positive_seasons=4),
            )

        one_family = [dict(row, origin_source_family="shared-family") for row in frame]
        with self.assertRaisesRegex(IntervalTrainingReproducibilityError, "source families"):
            build_interval_training_evidence(one_family)

    def test_evidence_writes_and_rechecks_exact_snapshot_hash(self) -> None:
        labels, features = _fixture()
        frame = build_interval_training_frame(labels, features)

        with TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "interval-shadow.jsonl"
            manifest = build_interval_training_evidence(frame, snapshot_path=snapshot_path)

            self.assertTrue(snapshot_path.is_file())
            self.assertEqual(manifest["snapshot_hash"], manifest["snapshot_file_sha256"])
            self.assertEqual(manifest["snapshot_path"], str(snapshot_path))

    def test_missing_cutoff_is_rejected_before_join(self) -> None:
        labels, features = _fixture()
        labels[0].pop("feature_cutoff_at")

        with self.assertRaisesRegex(IntervalTrainingReproducibilityError, "feature_cutoff_at"):
            build_interval_training_frame(labels, features)

    def test_staging_path_gets_cutoff_from_joined_feature_without_point_time(self) -> None:
        labels, features = _fixture()
        for label in labels:
            label.pop("feature_cutoff_at")

        frame = build_interval_training_frame_from_staging(labels, features)

        self.assertEqual(len(frame), 6)
        self.assertTrue(all(row["feature_cutoff_at"] for row in frame))
        self.assertTrue(all("event_time" not in row and "timestamp" not in row for row in frame))
        self.assertTrue(all(row["shadow_only"] for row in frame))
        self.assertTrue(all(not row["core_training_eligible"] for row in frame))

    def test_staging_join_report_preserves_no_match_reasons(self) -> None:
        labels, features = _fixture()
        for feature in features:
            feature["feature_join_key"] = "different-region:0:0"

        report = evaluate_interval_training_staging_join(labels, features)

        self.assertEqual(report["summary"]["joined_count"], 0)
        self.assertTrue(report["issues"])
        self.assertTrue(all(issue["reason"] in {
            "no_eligible_feature",
            "join_key_mismatch",
        } for issue in report["issues"]))

    def test_incomplete_feature_vector_is_not_trainable_evidence(self) -> None:
        labels, features = _fixture()
        frame = build_interval_training_frame_from_staging(labels, features)
        frame[0]["features"]["snowfall_24h"] = None

        report = validate_interval_training_frame(frame)

        self.assertFalse(report["passed"])
        self.assertEqual(report["error_counts"]["missing_feature_value"], 1)

    def test_point_time_and_promotion_flags_are_rejected(self) -> None:
        labels, features = _fixture()
        labels[0]["event_time"] = "2020-12-01T12:00:00Z"

        with self.assertRaisesRegex(IntervalTrainingReproducibilityError, "point-time"):
            build_interval_training_frame(labels, features)

        labels, features = _fixture()
        labels[0]["core_training_eligible"] = True

        with self.assertRaisesRegex(IntervalTrainingReproducibilityError, "core_training_eligible"):
            build_interval_training_frame(labels, features)

    def test_validation_rejects_mixed_or_promoted_frame(self) -> None:
        labels, features = _fixture()
        frame = build_interval_training_frame(labels, features)
        frame[0]["timestamp"] = frame[0]["interval_start"]

        report = validate_interval_training_frame(frame)

        self.assertFalse(report["passed"])
        self.assertIn("point_time_field_present", report["error_counts"])


if __name__ == "__main__":
    unittest.main()
