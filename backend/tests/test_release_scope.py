import unittest

from scripts.verify_release_scope import (
    classify_path,
    matches_denylist,
    scope_hash,
)


class ReleaseScopePolicyTests(unittest.TestCase):
    def test_knowledge_surface_is_the_only_automatic_rc_category(self) -> None:
        category, selected, _ = classify_path("src/lib/knowledge-graph/explainer.ts")
        self.assertEqual(category, "knowledge_rc_in")
        self.assertTrue(selected)

    def test_reviewed_explainer_dependency_is_intentionally_selected(self) -> None:
        category, selected, _ = classify_path(
            "src/lib/knowledge-graph/sectionGenerators.ts"
        )
        self.assertEqual(category, "knowledge_rc_in")
        self.assertTrue(selected)

    def test_new_path_inside_knowledge_directory_stays_manual_review(self) -> None:
        category, selected, _ = classify_path("src/lib/knowledge-graph/new_file.ts")
        self.assertEqual(category, "manual_review")
        self.assertFalse(selected)

    def test_gee_and_customer_paths_are_explicitly_excluded(self) -> None:
        gee_category, gee_selected, _ = classify_path("backend/gee_extractor.py")
        provenance_category, provenance_selected, _ = classify_path(
            "backend/scripts/provenance_backfill.py"
        )
        customer_category, customer_selected, _ = classify_path(
            "docs/shared_content/export.md"
        )
        self.assertEqual(gee_category, "gee_exclude")
        self.assertFalse(gee_selected)
        self.assertEqual(provenance_category, "gee_exclude")
        self.assertFalse(provenance_selected)
        self.assertEqual(customer_category, "customer_exclude")
        self.assertFalse(customer_selected)

    def test_denylist_is_never_selected(self) -> None:
        category, selected, _ = classify_path("backend/train_model.py")
        self.assertEqual(category, "denylist_manual_review")
        self.assertFalse(selected)
        self.assertTrue(matches_denylist("backend/common/../train_model.py"))

    def test_scope_hash_is_order_independent_and_content_bound(self) -> None:
        first = [
            {"path": "a.py", "git_status": " M", "kind": "file", "sha256": "a", "rc_selected": True},
            {"path": "b.py", "git_status": "??", "kind": "file", "sha256": "b", "rc_selected": False},
        ]
        second = list(reversed(first))
        self.assertEqual(scope_hash(first), scope_hash(second))
        second[1] = {**second[1], "sha256": "changed"}
        self.assertNotEqual(scope_hash(first), scope_hash(second))


if __name__ == "__main__":
    unittest.main()
