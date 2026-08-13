from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_mvp4_source_registry import validate_source_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "docs/MVP4/03_ml_evidence/source_manifest_registry.json"


class Mvp4SourceRegistryTests(unittest.TestCase):
    def _registry(self) -> dict:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_current_registry_passes_and_remains_non_promoting(self) -> None:
        report = validate_source_registry(self._registry())

        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["source_count"], 9)
        self.assertTrue(report["non_promoting_registry"])
        self.assertTrue(all(source["training_eligible"] is False for source in report["sources"]))
        self.assertTrue(all(source["production_scoring_eligible"] is False for source in report["sources"]))

    def test_training_flag_cannot_be_enabled_in_evidence_registry(self) -> None:
        registry = self._registry()
        registry["sources"][0]["training_eligible"] = True

        report = validate_source_registry(registry)

        self.assertFalse(report["passed"])
        self.assertTrue(any("training_eligible must be false" in error for error in report["errors"]))

    def test_approved_source_cannot_keep_pending_rights(self) -> None:
        registry = self._registry()
        source = registry["sources"][0]
        source["review_status"] = "approved"

        report = validate_source_registry(registry)

        self.assertFalse(report["passed"])
        self.assertTrue(any("cannot be approved while licence status" in error for error in report["errors"]))

    def test_occurrence_time_claim_requires_explicit_core_review(self) -> None:
        registry = self._registry()
        source = registry["sources"][1]
        source["time_semantics"]["source_time_is_avalanche_occurrence_time"] = True

        report = validate_source_registry(registry)

        self.assertFalse(report["passed"])
        self.assertTrue(any("occurrence-time claim requires" in error for error in report["errors"]))

    def test_duplicate_source_ids_are_rejected(self) -> None:
        registry = self._registry()
        registry["sources"].append(copy.deepcopy(registry["sources"][0]))

        report = validate_source_registry(registry)

        self.assertFalse(report["passed"])
        self.assertTrue(any("source_id is duplicated" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
