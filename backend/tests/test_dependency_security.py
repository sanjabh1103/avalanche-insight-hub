"""G-02/G-03: Verify dependency security — lock files pin patched versions.

The active .venv may have older packages (e.g. Pillow 12.2.0) but the lock
files (core-py312.txt, ci-py312.txt) must pin patched versions (e.g. 12.3.0).
CI must install from locks, not from the active .venv.
"""
from __future__ import annotations

import unittest
from pathlib import Path


class TestDependencySecurity(unittest.TestCase):
    """G-02/G-03: Lock files must pin patched versions of known-vulnerable packages."""

    REPO_ROOT = Path(__file__).resolve().parents[2]
    LOCK_DIR = Path(__file__).resolve().parent.parent / 'locks'

    def _read_lock(self, filename: str) -> str:
        path = self.LOCK_DIR / filename
        if not path.exists():
            self.skipTest(f'{filename} not found')
        return path.read_text()

    def test_core_lock_pins_pillow_12_3_0(self):
        """core-py312.txt must pin Pillow >= 12.3.0 (fixes 5 CVEs in 12.2.0)."""
        content = self._read_lock('core-py312.txt')
        self.assertIn('pillow==12.3.0', content)

    def test_snowpack_lock_pins_pillow_12_3_0(self):
        """snowpack-py312.txt must pin Pillow >= 12.3.0."""
        content = self._read_lock('snowpack-py312.txt')
        self.assertIn('pillow==12.3.0', content)

    def test_pdfminer_six_pinned(self):
        """G-02: pdfminer.six must be pinned in lock files."""
        content = self._read_lock('core-py312.txt')
        self.assertIn('pdfminer-six==20251230', content)

    def test_core_lock_pins_patched_h2(self):
        """CVE-2026-71554: core runtime must use h2 4.4.1 or newer."""
        content = self._read_lock('core-py312.txt')
        self.assertIn('h2==4.4.1', content)

    def test_lock_files_have_hashes(self):
        """G-03: Lock files must use --hash for reproducible installs."""
        for filename in ('core-py312.txt', 'ci-py312.txt'):
            content = self._read_lock(filename)
            self.assertIn('--hash=sha256:', content,
                          f'{filename} must contain hash-pinned dependencies')

    def test_core_and_ci_locks_share_modal_compatible_protobuf(self):
        """Earth Engine and Modal must resolve to one protobuf version."""
        core = self._read_lock('core-py312.txt')
        ci = self._read_lock('ci-py312.txt')
        self.assertIn('protobuf==5.29.6', core)
        self.assertIn('protobuf==5.29.6', ci)
        ci_input = (self.REPO_ROOT / 'backend' / 'requirements-ci.in').read_text()
        self.assertIn('modal==0.73.83', ci_input)
        self.assertNotIn('modal>=', ci_input)
        core_input = (self.REPO_ROOT / 'backend' / 'requirements-core.in').read_text()
        self.assertIn('protobuf==5.29.6', core_input)


if __name__ == '__main__':
    unittest.main()
