from __future__ import annotations

import unittest

from scripts.build_structural_knowledge_snapshot import deduplicate_structure_results


class StructuralKnowledgeSnapshotTests(unittest.TestCase):
    def test_identical_batch_rows_collapse_deterministically(self) -> None:
        rows = [
            {"path": "src/z.py", "language": "python", "functions": []},
            {"path": "src/a.py", "language": "python", "functions": []},
            {"path": "src/a.py", "language": "python", "functions": []},
        ]

        result = deduplicate_structure_results(rows)

        self.assertEqual([row["path"] for row in result.results], ["src/a.py", "src/z.py"])
        self.assertEqual(result.duplicate_paths, ["src/a.py"])
        self.assertEqual(result.duplicate_row_count, 1)
        self.assertEqual(result.conflicting_paths, [])

    def test_conflicting_rows_for_one_path_fail_closed(self) -> None:
        rows = [
            {"path": "src/a.py", "language": "python", "functions": []},
            {"path": "src/a.py", "language": "python", "functions": [{"name": "changed"}]},
        ]

        with self.assertRaisesRegex(ValueError, "Conflicting structural rows.*src/a.py"):
            deduplicate_structure_results(rows)


if __name__ == "__main__":
    unittest.main()
