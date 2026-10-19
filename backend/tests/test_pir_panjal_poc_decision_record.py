"""Contract tests for the canonical Pir Panjal POC decision record."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = REPO_ROOT / "docs" / "MVP4" / "00_governance" / "PIR_PANJAL_POC_DECISION_RECORD.json"


class PirPanjalPocDecisionRecordTests(unittest.TestCase):
    def test_canonical_record_exists_and_has_frozen_scope(self) -> None:
        self.assertTrue(RECORD_PATH.is_file())
        record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))

        self.assertEqual(record["schema_version"], "pir_panjal_poc_decision_v1")
        self.assertEqual(record["selected_sector"], "pir_panjal_nw_himalaya")
        self.assertTrue(record["customer_selected_poc"])
        self.assertFalse(record["Partner_approved"])
        self.assertFalse(record["official_warning_eligible"])
        self.assertIn(record["poc_scope_status"], ("customer_selected", "customer_selected_local_candidate", "hosted_v2_verified"))
        self.assertEqual(record["evidence_class"], "pipeline-proof-only")
        self.assertEqual(record["representative_regime"]["elevation_band"], "middle")
        self.assertIn(record["representative_regime"]["status"], ("candidate_fixture", "derived_candidate"))
        self.assertEqual(record["forecast"]["target_hours"], 48)
        self.assertEqual(record["forecast"]["optional_extension_hours"], 72)
        self.assertEqual(record["problem_scope"], ["storm_new_snow", "wind_slab"])
        self.assertEqual(record["engine_roles"]["physical_backbone"], "SNOWPACK")
        self.assertEqual(record["engine_roles"]["baseline_model"], "RF")
        self.assertEqual(record["engine_roles"]["hybrid_ml"], "shadow_only")
        self.assertEqual(record["engine_roles"]["modal"], "technical_shadow_only")

    def test_record_contains_non_claims_and_external_gates(self) -> None:
        record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
        non_claims = set(record["non_claims"])
        self.assertIn("no_official_warning", non_claims)
        self.assertIn("no_validated_pir_panjal_accuracy", non_claims)
        self.assertIn("no_modal_accuracy_claim", non_claims)
        self.assertIn("no_proxy_as_observation_claim", non_claims)
        # native_snowpack_round_trip may be "blocked" (pre-run) or
        # "hosted_v2_verified" (post-run); either is valid. Partner and
        # warning promotion must always remain blocked.
        round_trip = record["external_gates"]["native_snowpack_round_trip"]
        self.assertTrue(
            "blocked" in round_trip or "hosted_v2_verified" in round_trip,
            f"unexpected native_snowpack_round_trip value: {round_trip}",
        )
        self.assertEqual(record["external_gates"]["Partner_scientific_validation"], "blocked")
        self.assertEqual(record["external_gates"]["official_warning_promotion"], "blocked")

    def test_governance_documents_reference_the_canonical_record(self) -> None:
        references = (
            REPO_ROOT / "docs" / "MVP4" / "snowpack" / "Imp_plan.md",
            REPO_ROOT / "docs" / "MVP4" / "snowpack" / "claim_ledger.md",
            REPO_ROOT / "docs" / "MVP4" / "snowpack" / "deep-research-reconciliation.md",
            REPO_ROOT / "docs" / "MVP4" / "00_governance" / "MVP4_RELEASE_MANIFEST.json",
            REPO_ROOT / "docs" / "MVP4" / "00_governance" / "RELEASE_CANDIDATE_SCOPE_INVENTORY.md",
        )
        record_name = RECORD_PATH.name
        for path in references:
            self.assertIn(record_name, path.read_text(encoding="utf-8"), str(path))

    def test_no_governance_document_claims_Partner_approval_for_this_poc(self) -> None:
        paths = (
            REPO_ROOT / "docs" / "MVP4" / "snowpack" / "Imp_plan.md",
            REPO_ROOT / "docs" / "MVP4" / "snowpack" / "claim_ledger.md",
            REPO_ROOT / "docs" / "MVP4" / "snowpack" / "deep-research-reconciliation.md",
        )
        forbidden = "Partner-selected Indian sector (Pir Panjal"
        for path in paths:
            self.assertNotIn(forbidden, path.read_text(encoding="utf-8"), str(path))


if __name__ == "__main__":
    unittest.main()
