import tempfile
import unittest
from pathlib import Path

from scripts.audit_knowledge_release_closure import resolve_local_import


class KnowledgeReleaseClosureTests(unittest.TestCase):
    def test_resolves_extensionless_local_typescript_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/lib").mkdir(parents=True)
            (root / "src/lib/source.ts").write_text(
                "import { value } from './dependency';\n", encoding="utf-8"
            )
            (root / "src/lib/dependency.ts").write_text(
                "export const value = 1;\n", encoding="utf-8"
            )
            self.assertEqual(
                resolve_local_import(root, "src/lib/source.ts", "./dependency"),
                "src/lib/dependency.ts",
            )

    def test_rejects_imports_that_escape_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "outside.ts").write_text("export const value = 1;\n", encoding="utf-8")
            self.assertIsNone(resolve_local_import(root, "src/source.ts", "../../outside.ts"))

    def test_missing_local_import_is_not_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            self.assertIsNone(resolve_local_import(root, "src/source.ts", "./missing"))


if __name__ == "__main__":
    unittest.main()
