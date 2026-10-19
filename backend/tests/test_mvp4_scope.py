import unittest

from scripts.verify_mvp4_scope import (
    RELEASE_MANIFEST_RELATIVE,
    classify_mvp4_path,
    compare_frozen_entries,
    parse_allowlist_text,
    snapshot_excluded_paths,
)


class Mvp4ScopePolicyTests(unittest.TestCase):
    def test_mvp4_paths_are_candidate_routable_but_need_allowlist(self) -> None:
        category, selectable, _ = classify_mvp4_path(
            "backend/common/interval_training_contract.py"
        )
        self.assertEqual(category, "mvp4_candidate")
        self.assertTrue(selectable)

    def test_gee_paths_remain_outside_automatic_mvp4_selection(self) -> None:
        category, selectable, _ = classify_mvp4_path(
            "backend/scripts/export_gee_scene_aware_snapshot.py"
        )
        self.assertEqual(category, "gee_exclude")
        self.assertFalse(selectable)

    def test_mvp4_customer_review_material_is_not_source_candidate(self) -> None:
        category, selectable, _ = classify_mvp4_path(
            "docs/MVP4/01_customer_review/MVP4_DATA_GATE_APPROVAL_PACKET.md"
        )
        self.assertEqual(category, "customer_exclude")
        self.assertFalse(selectable)

    def test_mvp4_generated_delivery_assets_are_not_source_candidates(self) -> None:
        category, selectable, _ = classify_mvp4_path(
            "docs/MVP4/05_generated_assets/SCIENTIST_REVIEW_FAQ.pdf"
        )
        self.assertEqual(category, "generated_exclude")
        self.assertFalse(selectable)

    def test_pre_remote_gate_contract_is_mvp4_candidate_routable(self) -> None:
        for path in (
            "scripts/prepare_mvp4_pre_remote_approval.py",
            "scripts/verify_mvp4_pre_remote_gate.py",
            "schemas/mvp4_pre_remote_approval.template.json",
            "backend/tests/test_mvp4_pre_remote_gate.py",
        ):
            category, selectable, _ = classify_mvp4_path(path)
            self.assertEqual(category, "mvp4_candidate", path)
            self.assertTrue(selectable, path)

    def test_evidence_and_denylist_paths_are_never_selected(self) -> None:
        evidence = classify_mvp4_path(".phase-loop/p79-exact-time-source-research.json")
        denylist = classify_mvp4_path("backend/common/risk_math.py")
        self.assertEqual(evidence[:2], ("evidence_out", False))
        self.assertEqual(denylist[:2], ("denylist_manual_review", False))

    def test_allowlist_rejects_traversal_and_duplicates(self) -> None:
        paths, errors = parse_allowlist_text(
            "backend/common/interval_training_contract.py\n"
            "../secret.txt\n"
            "backend/common/interval_training_contract.py\n"
        )
        self.assertEqual(paths, ["backend/common/interval_training_contract.py"])
        self.assertEqual(len(errors), 2)

    def test_frozen_entries_detect_added_removed_and_changed_paths(self) -> None:
        frozen = [
            {
                "path": "backend/common/interval_training_contract.py",
                "git_status": "??",
                "kind": "file",
                "sha256": "old-hash",
                "category": "mvp4_candidate",
                "allowlist_selectable": True,
                "reason": "MVP4 lane; exact allowlist still required",
            },
            {
                "path": "docs/shared_content/notes.md",
                "git_status": "??",
                "kind": "file",
                "sha256": "customer-hash",
                "category": "customer_exclude",
                "allowlist_selectable": False,
                "reason": "customer/delivery material is outside the ML RC",
            },
        ]
        current = [
            {**frozen[0], "sha256": "new-hash"},
            {
                "path": "backend/common/new_dirty_file.py",
                "git_status": "??",
                "kind": "file",
                "sha256": "new-file-hash",
                "category": "mvp4_candidate",
                "allowlist_selectable": True,
                "reason": "MVP4 lane; exact allowlist still required",
            },
        ]

        errors = compare_frozen_entries(frozen, current)

        self.assertTrue(any("changed" in error for error in errors))
        self.assertTrue(any("added" in error for error in errors))
        self.assertTrue(any("removed" in error for error in errors))

    def test_release_manifest_is_excluded_from_frozen_entry_snapshot(self) -> None:
        excluded = snapshot_excluded_paths(
            ".phase-loop/p81-mvp4-scope-freeze-20260803.json",
            "scripts/mvp4_release_allowlist.pending.txt",
        )
        self.assertIn(RELEASE_MANIFEST_RELATIVE, excluded)
        self.assertEqual(len(excluded), 3)


if __name__ == "__main__":
    unittest.main()
