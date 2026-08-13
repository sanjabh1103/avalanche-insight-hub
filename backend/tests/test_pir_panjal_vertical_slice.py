"""Contract tests for the candidate Pir Panjal vertical-slice runner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.common.meteoio_openmeteo import NativeExecutionEvidence
from backend.scripts.run_pir_panjal_poc_vertical_slice import (
    PirPanjalVerticalSliceError,
    _inventory,
    _native_runtime_warning_summary,
    _require_empty_output_dir,
)


class PirPanjalVerticalSliceContractTests(unittest.TestCase):
    def test_inventory_excludes_self_hashing_result_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "candidate-result.json").write_text("{}", encoding="utf-8")
            (root / "native.pro").write_text("native", encoding="utf-8")
            inventory = _inventory(root)
            self.assertEqual([item["path"] for item in inventory], ["native.pro"])

    def test_runner_rejects_stale_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            (root / "stale.pro").write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(PirPanjalVerticalSliceError, "must be empty"):
                _require_empty_output_dir(root)

    def test_native_runtime_warnings_are_recorded_from_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "candidate.log"
            log.write_text(
                "[stdout]\ncompleted\n[stderr]\n[W] precipitation should be re-accumulated\n",
                encoding="utf-8",
            )
            evidence = NativeExecutionEvidence(log_path="/container/candidate.log")
            summary = _native_runtime_warning_summary(root, evidence.log_path)
            self.assertEqual(summary["status"], "recorded")
            self.assertEqual(summary["log_path"], "candidate.log")
            self.assertEqual(len(summary["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()
