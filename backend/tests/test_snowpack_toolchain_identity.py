"""Tests for non-placeholder SNOWPACK runtime identities."""

from __future__ import annotations

import unittest

from backend.common.snowpack_toolchain_identity import is_real_image_id, is_real_sha256
from backend.scripts.release_gate import _validate_invocation


class SnowpackToolchainIdentityTests(unittest.TestCase):
    def test_real_image_id_and_archive_digest_are_accepted(self) -> None:
        self.assertTrue(is_real_image_id("sha256:" + "a" * 64))
        self.assertTrue(is_real_sha256("b" * 64))

    def test_zero_and_one_sentinels_are_rejected(self) -> None:
        self.assertFalse(is_real_image_id("sha256:" + "0" * 64))
        self.assertFalse(is_real_image_id("sha256:" + "1" * 64))
        self.assertFalse(is_real_sha256("0" * 64))
        self.assertFalse(is_real_sha256("1" * 64))

    def test_malformed_values_are_rejected(self) -> None:
        self.assertFalse(is_real_image_id("sha256:short"))
        self.assertFalse(is_real_sha256("not-a-digest"))

    def test_release_gate_rejects_placeholder_runtime_identity(self) -> None:
        invocation = {
            "binary_path": "/opt/snowpack/bin/snowpack",
            "binary_version": "SNOWPACK 3.7.0",
            "command": "snowpack",
            "started_at": "2026-08-11T00:00:00Z",
            "finished_at": "2026-08-11T00:01:00Z",
            "toolchain_id": "tc_candidate",
            "run_id": "run_candidate",
            "binary_sha256": "a" * 64,
            "command_sha256": "b" * 64,
            "exit_code": 0,
            "version_exit_code": 0,
            "version_verified": True,
            "image_id": "sha256:" + "0" * 64,
            "image_archive_sha256": "c" * 64,
            "image_repository_digest": "",
            "image_identity_source": "local_id_and_archive",
            "toolchain_manifest_verified": True,
        }
        invocation["toolchain_manifest_sha256"] = "d" * 64
        errors = _validate_invocation(invocation)
        self.assertTrue(any("image_id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
