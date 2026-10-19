"""Regression tests for binding the training input to its reviewed snapshot."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.scripts.audit_training_dataset import validate_training_snapshot_binding


REPO_ROOT = Path(__file__).resolve().parents[2]


class TrainingSnapshotBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.real_manifest = REPO_ROOT / (
            "backend/data/open_source_labels/hiaval_hma_rebuilt_20260803/"
            "snapshot_manifest.json"
        )
        self.real_other_events = REPO_ROOT / (
            "backend/data/open_source_labels/gee_sar_remote_audit/events.jsonl"
        )
        self.tempdir = TemporaryDirectory(dir=REPO_ROOT)
        root = Path(self.tempdir.name)
        self.manifest = root / "snapshot_manifest.json"
        self.events = root / "events.jsonl"
        self.other_events = root / "other-events.jsonl"
        payload = '{"event_id":"fixture-1","label":1}\n'
        self.events.write_text(payload, encoding="utf-8")
        self.other_events.write_text('{"event_id":"other-1","label":0}\n', encoding="utf-8")
        self.manifest.write_text(json.dumps({
            "snapshot_schema_version": "mvp4_hiaval_snapshot_v1",
            "events_path": self.events.name,
            "event_rows_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "source_key": "hiaval_hma",
            "license_review_id": "mvp4-hiaval-cc-by4-review-20260801",
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_matching_snapshot_and_manifest_are_accepted(self) -> None:
        result = validate_training_snapshot_binding(
            self.manifest,
            open_source_snapshot_path=self.events,
            source_key="hiaval_hma",
            license_review_id="mvp4-hiaval-cc-by4-review-20260801",
        )

        self.assertTrue(result["passed"], result["errors"])

    def test_different_snapshot_is_rejected_even_when_manifest_is_valid(self) -> None:
        result = validate_training_snapshot_binding(
            self.manifest,
            open_source_snapshot_path=self.other_events,
            source_key="hiaval_hma",
            license_review_id="mvp4-hiaval-cc-by4-review-20260801",
        )

        self.assertFalse(result["passed"])
        self.assertIn("does not match", " ".join(result["errors"]))

    def test_missing_runtime_snapshot_is_rejected(self) -> None:
        result = validate_training_snapshot_binding(
            self.manifest,
            open_source_snapshot_path=None,
            source_key="hiaval_hma",
            license_review_id="mvp4-hiaval-cc-by4-review-20260801",
        )

        self.assertFalse(result["passed"])
        self.assertIn("OPEN_SOURCE_LABEL_SNAPSHOT", " ".join(result["errors"]))

    def test_train_entrypoint_rejects_snapshot_path_mismatch(self) -> None:
        if not self.real_manifest.is_file() or not self.real_other_events.is_file():
            self.skipTest("optional reviewed training snapshot fixtures are not present in this checkout")
        import backend.train_model as train_model
        with patch.object(train_model, "TRAINING_PREFLIGHT_STRICT", True), \
            patch.object(train_model, "TRAINING_RESEARCH_OVERRIDE", False), \
            patch.dict(
                "os.environ",
                {
                    "SNAPSHOT_MANIFEST": str(self.real_manifest),
                    "OPEN_SOURCE_LABEL_SNAPSHOT": str(self.real_other_events),
                    "OPEN_SOURCE_LABEL_SOURCE_KEY": "hiaval_hma",
                    "OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID": "mvp4-hiaval-cc-by4-review-20260801",
                },
                clear=False,
            ):
            result = train_model._reviewed_snapshot_preflight()

        self.assertFalse(result["passed"])
        self.assertIn("does not match", " ".join(result["errors"]))
        self.assertFalse(result["snapshot_binding"]["passed"])

    def test_mts_lstm_schedule_is_release_flagged(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/ml_pipeline.yml").read_text(
            encoding="utf-8"
        )
        job = workflow.split("  train_mtslstm:", 1)[1].split(
            "  infer_mtslstm:", 1
        )[0]

        self.assertIn("vars.MVP4_TRAINING_ENABLED == 'true'", job)


if __name__ == "__main__":
    unittest.main()
