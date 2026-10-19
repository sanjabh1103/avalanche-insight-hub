from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backend.common.training_reproducibility import (
    ReproducibilityConfig,
    TrainingReproducibilityError,
    build_training_evidence,
    canonical_json_bytes,
    validate_reproducibility_manifest,
)


def _frame() -> pd.DataFrame:
    rows = []
    for index in range(6):
        event_id = f"event-{index}"
        timestamp = pd.Timestamp("2024-11-01", tz="UTC") + pd.Timedelta(days=index * 120)
        rows.extend([
            {
                "event_id": event_id,
                "source_event_id": event_id,
                "timestamp": timestamp,
                "region_key": "himalayas_nepal",
                "lat": 27.5 + index * 0.01,
                "lng": 86.5 + index * 0.01,
                "label": 1,
                "label_source": "open_epa",
                "value": float(index),
                "governed_at": f"volatile-{index}",
            },
            {
                "event_id": None,
                "source_event_id": event_id,
                "timestamp": timestamp,
                "region_key": "himalayas_nepal",
                "lat": 27.6 + index * 0.01,
                "lng": 86.6 + index * 0.01,
                "label": 0,
                "label_source": "synthetic_negative",
                "value": float(index + 1),
                "governed_at": f"volatile-{index + 10}",
            },
        ])
    return pd.DataFrame(rows)


class TrainingReproducibilityTests(unittest.TestCase):
    def test_hash_is_canonical_and_volatile_fields_do_not_change_it(self) -> None:
        first = _frame()
        second = first.copy()
        second["governed_at"] = "a-different-clock"
        with TemporaryDirectory() as tmpdir:
            _, first_manifest, _ = build_training_evidence(
                first,
                artifact_dir=Path(tmpdir) / "first",
                config=ReproducibilityConfig(minimum_seasons=1, minimum_span_days=0),
            )
            _, second_manifest, _ = build_training_evidence(
                second,
                artifact_dir=Path(tmpdir) / "second",
                config=ReproducibilityConfig(minimum_seasons=1, minimum_span_days=0),
            )
        self.assertEqual(first_manifest["snapshot_hash"], second_manifest["snapshot_hash"])
        self.assertEqual(json.loads(canonical_json_bytes({"b": 1, "a": 2})), {"a": 2, "b": 1})

    def test_paired_negative_stays_in_the_same_event_group(self) -> None:
        enriched, manifest, _ = build_training_evidence(
            _frame(),
            config=ReproducibilityConfig(minimum_seasons=1, minimum_span_days=0),
        )
        for event_id, group in enriched.groupby("source_event_id"):
            self.assertEqual(group["event_group_id"].nunique(), 1, event_id)
        self.assertEqual(manifest["event_group_count"], 6)

    def test_split_boundaries_are_disjoint_and_monotonic(self) -> None:
        _, manifest, report = build_training_evidence(
            _frame(),
            config=ReproducibilityConfig(
                minimum_seasons=1,
                minimum_span_days=0,
                minimum_positive_seasons=1,
                minimum_positive_sources=1,
            ),
        )
        self.assertTrue(report["passed"])
        splits = manifest["split_boundaries"]
        self.assertLessEqual(splits["train"]["end"], splits["calibration"]["start"])
        self.assertLessEqual(splits["calibration"]["end"], splits["test"]["start"])
        self.assertTrue(set(splits["train"]["event_group_ids"]).isdisjoint(splits["test"]["event_group_ids"]))

    def test_strict_preflight_rejects_single_season_evidence(self) -> None:
        short = _frame()
        short["timestamp"] = pd.Timestamp("2025-01-01", tz="UTC")
        short["label_source"] = "gee_sar"
        _, manifest, report = build_training_evidence(short)
        self.assertFalse(report["passed"])
        self.assertIn("minimum seasons", " ".join(report["errors"]))
        with self.assertRaises(TrainingReproducibilityError):
            validate_reproducibility_manifest(manifest, strict=True)

    def test_himalayan_season_boundary_is_region_aware(self) -> None:
        frame = _frame().iloc[[0, 2, 4]].copy()
        frame['timestamp'] = [
            pd.Timestamp('2025-10-31T12:00:00Z'),
            pd.Timestamp('2025-11-01T12:00:00Z'),
            pd.Timestamp('2026-01-15T12:00:00Z'),
        ]
        _, manifest, _ = build_training_evidence(
            frame,
            config=ReproducibilityConfig(
                minimum_seasons=1,
                minimum_span_days=0,
                minimum_positive_seasons=1,
                minimum_positive_sources=1,
            ),
        )
        self.assertEqual(manifest['season_ids'], ['2024-2025', '2025-2026'])
        self.assertEqual(manifest['group_policy']['season_start_months']['himalayas_nepal'], 11)


if __name__ == "__main__":
    unittest.main()
