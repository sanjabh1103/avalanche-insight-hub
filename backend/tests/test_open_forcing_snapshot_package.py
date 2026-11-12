from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.scripts.package_open_forcing_snapshot import _archive_bytes


class OpenForcingSnapshotPackageTests(unittest.TestCase):
    def test_archive_is_deterministic_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            (root / "z").mkdir(parents=True)
            (root / "a.txt").write_text("a\n")
            (root / "z" / "b.txt").write_text("b\n")
            first = _archive_bytes(root)
            second = _archive_bytes(root)
            self.assertEqual(first, second)
            self.assertGreater(len(first), 0)


if __name__ == "__main__":
    unittest.main()
