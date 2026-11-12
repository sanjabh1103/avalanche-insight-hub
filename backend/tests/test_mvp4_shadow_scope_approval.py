from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.verify_mvp4_shadow_scope_approval import ROOT, validate_shadow_scope_approval


TEMPLATE = ROOT / "schemas/mvp4_shadow_scope_approval.template.json"


class Mvp4ShadowScopeApprovalTests(unittest.TestCase):
    def _write(self, root: Path, value: dict) -> Path:
        path = root / "approval.json"
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        return path

    def _approved_fixture(self, root: Path) -> dict:
        value = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        for index, binding in enumerate(value["snapshot_bindings"]):
            source = root / f"snapshot-fixture-{index}.json"
            source.write_text(json.dumps({"fixture": index}), encoding="utf-8")
            binding["path"] = source.relative_to(ROOT).as_posix()
            binding["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        value["decision"] = "APPROVED_SHADOW_ONLY"
        value["approval_decisions"] = {key: "APPROVED" for key in value["approval_decisions"]}
        value["approved_by"] = [
            {"role": "scientist", "approval_ref": "meeting-ref-scientist"},
            {"role": "customer", "approval_ref": "meeting-ref-customer"},
        ]
        value["approved_at"] = "2026-08-04T00:00:00Z"
        value["scope_change_reference"] = "MOM-29-07-shadow-scope"
        return value

    def test_template_is_structurally_valid_but_not_approved(self) -> None:
        report = validate_shadow_scope_approval(TEMPLATE)

        self.assertFalse(report["passed"])
        self.assertTrue(report["structurally_valid"])
        self.assertEqual(report["decision"], "PENDING")
        self.assertTrue(report["approval_required"])

    def test_approved_shadow_scope_requires_hashes_and_attributable_reviewers(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            path = self._write(root, self._approved_fixture(root))
            report = validate_shadow_scope_approval(path)

        self.assertTrue(report["passed"], report)
        self.assertTrue(report["shadow_only"])
        self.assertTrue(report["core_exact_time_gate_unchanged"])

    def test_approved_shadow_scope_requires_source_rights_and_api_scope_decision(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            value = self._approved_fixture(root)
            value["approval_decisions"]["source_rights_and_api_scope"] = "APPROVED"
            report = validate_shadow_scope_approval(self._write(root, value))

        self.assertTrue(report["passed"], report)

    def test_promotion_flags_are_rejected(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            value = self._approved_fixture(root)
            value["policy"]["model_fit_allowed"] = True
            report = validate_shadow_scope_approval(self._write(root, value))

        self.assertFalse(report["passed"])
        self.assertTrue(any("model_fit_allowed" in error for error in report["errors"]))

    def test_rejected_decision_cannot_be_treated_as_approval(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            value = self._approved_fixture(root)
            value["decision"] = "REJECTED"
            report = validate_shadow_scope_approval(self._write(root, value))

        self.assertFalse(report["passed"])
        self.assertTrue(any("PENDING or APPROVED_SHADOW_ONLY" in error for error in report["errors"]))

    def test_external_manifest_path_is_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            report = validate_shadow_scope_approval(Path(tmpdir) / "approval.json")

        self.assertFalse(report["passed"])
        self.assertTrue(any("under the repository root" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
