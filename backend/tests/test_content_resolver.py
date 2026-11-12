"""Tests for content resolver (P4).

Tests verify that:
- Valid content with matching hash passes
- Hash mismatch is rejected
- Missing files are rejected
- Symlinks are rejected (path substitution attack)
- Non-hex declared hashes are rejected
- In-memory bytes verification works
- JSON payload verification works
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.common.track_contracts.content_resolver import (
    ContentResolver,
    ContentResolutionError,
    ContentVerificationResult,
)


class TestContentResolver(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.base_path = Path(self.tmpdir)
        self.resolver = ContentResolver(base_path=self.base_path)

        # Create a test file
        self.test_content = b'{"test": "content", "level": 3}'
        self.test_file = self.base_path / "test.json"
        self.test_file.write_bytes(self.test_content)
        self.test_hash = hashlib.sha256(self.test_content).hexdigest()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_content_passes(self):
        result = self.resolver.resolve_and_verify(
            self.test_hash, "test.json"
        )
        self.assertTrue(result.verified)
        self.assertEqual(result.actual_hash, self.test_hash)

    def test_hash_mismatch_rejected(self):
        wrong_hash = "b" * 64
        with self.assertRaises(ContentResolutionError):
            self.resolver.resolve_and_verify(wrong_hash, "test.json")

    def test_missing_file_rejected(self):
        with self.assertRaises(ContentResolutionError):
            self.resolver.resolve_and_verify(
                self.test_hash, "nonexistent.json"
            )

    def test_symlink_rejected(self):
        """Symlinks must be rejected to prevent path substitution attacks."""
        symlink_path = self.base_path / "symlink.json"
        try:
            os.symlink(self.test_file, symlink_path)
        except OSError:
            self.skipTest("cannot create symlink on this platform")
        with self.assertRaises(ContentResolutionError) as ctx:
            self.resolver.resolve_and_verify(
                self.test_hash, "symlink.json"
            )
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_non_hex_hash_rejected(self):
        with self.assertRaises(ContentResolutionError):
            self.resolver.resolve_and_verify("z" * 64, "test.json")

    def test_short_hash_rejected(self):
        with self.assertRaises(ContentResolutionError):
            self.resolver.resolve_and_verify("abc123", "test.json")

    def test_verify_bytes_matching(self):
        result = self.resolver.verify_bytes(self.test_hash, self.test_content)
        self.assertTrue(result.verified)

    def test_verify_bytes_mismatch(self):
        wrong_content = b'{"different": "content"}'
        with self.assertRaises(ContentResolutionError):
            self.resolver.verify_bytes(self.test_hash, wrong_content)

    def test_verify_json_payload(self):
        payload = {"test": "content", "level": 3}
        # Compute the canonical hash the same way
        canonical = json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
        expected_hash = hashlib.sha256(canonical).hexdigest()
        result = self.resolver.verify_json_payload(expected_hash, payload)
        self.assertTrue(result.verified)

    def test_verify_json_payload_mismatch(self):
        payload = {"test": "content", "level": 3}
        wrong_hash = "c" * 64
        with self.assertRaises(ContentResolutionError):
            self.resolver.verify_json_payload(wrong_hash, payload)

    def test_byte_mutation_detected(self):
        """Mutating a single byte of the content must cause hash mismatch."""
        mutated_content = self.test_content.replace(b'3', b'4')
        with self.assertRaises(ContentResolutionError):
            self.resolver.verify_bytes(self.test_hash, mutated_content)

    def test_arbitrary_hex_hash_without_file_fails(self):
        """An arbitrary valid hex hash with no matching file must fail."""
        arbitrary_hash = "d" * 64
        with self.assertRaises(ContentResolutionError):
            self.resolver.resolve_and_verify(arbitrary_hash, "nonexistent.json")

    def test_parent_traversal_rejected(self):
        outside = Path(self.tmpdir).parent / "Partner-outside-content.txt"
        outside.write_bytes(self.test_content)
        try:
            with self.assertRaises(ContentResolutionError) as caught:
                self.resolver.resolve_and_verify(self.test_hash, "../Partner-outside-content.txt")
            self.assertIn("traversal", str(caught.exception).lower())
        finally:
            outside.unlink(missing_ok=True)

    def test_absolute_path_rejected(self):
        with self.assertRaises(ContentResolutionError):
            self.resolver.resolve_and_verify(self.test_hash, str(self.test_file))

    def test_symlinked_parent_rejected(self):
        parent = self.base_path / "parent-link"
        target = self.base_path / "real-parent"
        target.mkdir()
        (target / "nested.json").write_bytes(self.test_content)
        try:
            os.symlink(target, parent)
        except OSError:
            self.skipTest("cannot create symlink on this platform")
        with self.assertRaises(ContentResolutionError) as caught:
            self.resolver.resolve_and_verify(self.test_hash, "parent-link/nested.json")
        self.assertIn("symlink", str(caught.exception).lower())


if __name__ == "__main__":
    unittest.main()
