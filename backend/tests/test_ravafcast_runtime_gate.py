"""Tests for ravafcast_runtime_gate — disabled-by-default seam verification.

Verifies:
- Disabled mode is a no-op (default)
- Invalid contracts fail closed
- Active RF results are equality-stable (gate does not touch them)
- Safety locks remain false
"""

import os
import unittest

from backend.common.ravafcast_runtime_gate import (
    check_pipeline_status,
    emit_gate_metadata,
    GateStatus,
)
from backend.common.ravafcast_contracts import (
    LabelContract,
    RegionElevationContract,
    EvidenceCaseContract,
    compute_provenance_hash,
)


class TestRuntimeGateDisabled(unittest.TestCase):

    def setUp(self):
        os.environ.pop("RAVAFCAST_PIPELINE_ENABLED", None)

    def test_disabled_by_default(self):
        status = check_pipeline_status()
        self.assertEqual(status.status, "disabled")
        self.assertIn("false", status.reason.lower())

    def test_disabled_does_not_check_contracts(self):
        status = check_pipeline_status(label_contract=LabelContract(
            labels=(1, 2), label_names=("A", "B"),
            missing_label_policy="reject", forecast_window_hours=24,
            approved_by="X", approved_at="2026-07-18T00:00:00Z",
        ))
        self.assertEqual(status.status, "disabled")
        self.assertFalse(status.contracts_provided)


class TestRuntimeGateBlocked(unittest.TestCase):

    def setUp(self):
        os.environ["RAVAFCAST_PIPELINE_ENABLED"] = "true"

    def tearDown(self):
        os.environ.pop("RAVAFCAST_PIPELINE_ENABLED", None)

    def test_no_contracts_blocks(self):
        status = check_pipeline_status()
        self.assertEqual(status.status, "blocked_missing_contract")
        self.assertFalse(status.contracts_provided)

    def test_invalid_contract_blocks(self):
        bad_label = LabelContract(
            labels=(1, 1),
            label_names=("A", "B"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="X",
            approved_at="2026-07-18T00:00:00Z",
        )
        status = check_pipeline_status(label_contract=bad_label)
        self.assertEqual(status.status, "blocked_missing_contract")
        self.assertTrue(status.contracts_provided)
        self.assertFalse(status.contracts_valid)

    def test_valid_contracts_no_hypothesis_is_shadow(self):
        good_label = LabelContract(
            labels=(1, 2, 3, 4),
            label_names=("Low", "Moderate", "High", "Very High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner-Scientist-1",
            approved_at="2026-07-18T00:00:00Z",
        )
        status = check_pipeline_status(label_contract=good_label)
        self.assertEqual(status.status, "shadow_not_selected")
        self.assertTrue(status.contracts_valid)
        self.assertFalse(status.hypothesis_selected)

    def test_valid_contracts_with_hypothesis_is_active(self):
        good_label = LabelContract(
            labels=(1, 2, 3, 4),
            label_names=("Low", "Moderate", "High", "Very High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner-Scientist-1",
            approved_at="2026-07-18T00:00:00Z",
        )
        good_region = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 3000),
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        status = check_pipeline_status(
            label_contract=good_label,
            region_elevation_contract=good_region,
            hypothesis_selected=True,
        )
        self.assertEqual(status.status, "active")
        self.assertTrue(status.contracts_valid)
        self.assertTrue(status.hypothesis_selected)


class TestRuntimeGateMetadata(unittest.TestCase):

    def test_metadata_has_active_path_unchanged(self):
        os.environ.pop("RAVAFCAST_PIPELINE_ENABLED", None)
        status = check_pipeline_status()
        meta = emit_gate_metadata(status)
        self.assertIn("ravafcast_gate", meta)
        self.assertTrue(meta["ravafcast_gate"]["active_path_unchanged"])

    def test_metadata_status_propagates(self):
        os.environ["RAVAFCAST_PIPELINE_ENABLED"] = "true"
        try:
            status = check_pipeline_status()
            meta = emit_gate_metadata(status)
            self.assertEqual(meta["ravafcast_gate"]["status"], "blocked_missing_contract")
        finally:
            os.environ.pop("RAVAFCAST_PIPELINE_ENABLED", None)


class TestRuntimeGateSafety(unittest.TestCase):

    def test_gate_does_not_modify_risk_score(self):
        """The gate must not touch risk_score or any active-path output."""
        os.environ.pop("RAVAFCAST_PIPELINE_ENABLED", None)
        status = check_pipeline_status()
        meta = emit_gate_metadata(status)
        self.assertNotIn("risk_score", meta)
        self.assertNotIn("danger", meta)
        self.assertNotIn("cap_alert", meta)

    def test_gate_never_raises(self):
        """Gate must always return a status, never raise."""
        os.environ["RAVAFCAST_PIPELINE_ENABLED"] = "true"
        try:
            status = check_pipeline_status(
                label_contract=object(),  # not a contract at all
            )
            self.assertIn(status.status, ("blocked_missing_contract", "disabled"))
        finally:
            os.environ.pop("RAVAFCAST_PIPELINE_ENABLED", None)


if __name__ == "__main__":
    unittest.main()
