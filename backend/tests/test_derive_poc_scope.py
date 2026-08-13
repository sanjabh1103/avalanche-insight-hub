"""Tests for the derive_poc_scope CLI helper.

P1-7/P1-8: Verifies that the helper:
  1. Reads raw bytes and verifies the external SHA-256 BEFORE parsing
  2. Rejects hash mismatches
  3. Emits the correct region, band, and horizon
  4. Works as a CLI (exit codes, stdout/stderr)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class DerivePocScopeTests(unittest.TestCase):
    _DECISION_RECORD_PATH = REPO_ROOT / 'docs' / 'MVP4' / '00_governance' / 'PIR_PANJAL_POC_DECISION_RECORD.json'

    def setUp(self) -> None:
        self._dr_bytes = self._DECISION_RECORD_PATH.read_bytes()
        self._dr_hash = hashlib.sha256(self._dr_bytes).hexdigest()

    def test_derive_scope_returns_correct_values(self) -> None:
        from backend.scripts.derive_poc_scope import derive_scope
        scope = derive_scope(self._DECISION_RECORD_PATH, self._dr_hash)
        self.assertEqual(scope['region_key'], 'pir_panjal_nw_himalaya')
        self.assertEqual(scope['elevation_band'], 'middle')
        self.assertEqual(scope['headline_horizon_hours'], 48)
        self.assertEqual(scope['ensemble_members'], 1)

    def test_derive_scope_rejects_hash_mismatch(self) -> None:
        from backend.scripts.derive_poc_scope import derive_scope
        wrong_hash = 'a' * 64
        with self.assertRaises(SystemExit) as ctx:
            derive_scope(self._DECISION_RECORD_PATH, wrong_hash)
        self.assertEqual(ctx.exception.code, 1)

    def test_derive_scope_rejects_invalid_hash_format(self) -> None:
        from backend.scripts.derive_poc_scope import derive_scope
        with self.assertRaises(SystemExit) as ctx:
            derive_scope(self._DECISION_RECORD_PATH, 'not-a-hash')
        self.assertEqual(ctx.exception.code, 1)

    def test_cli_json_emit(self) -> None:
        """CLI --emit json prints valid JSON to stdout."""
        env = os.environ.copy()
        env['PYTHONPATH'] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, '-m', 'backend.scripts.derive_poc_scope',
             '--decision-record-path', str(self._DECISION_RECORD_PATH),
             '--expected-sha256', self._dr_hash,
             '--emit', 'json'],
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['region_key'], 'pir_panjal_nw_himalaya')
        self.assertEqual(data['elevation_band'], 'middle')
        self.assertEqual(data['headline_horizon_hours'], 48)

    def test_cli_hash_mismatch_exits_1(self) -> None:
        """CLI exits 1 on hash mismatch."""
        env = os.environ.copy()
        env['PYTHONPATH'] = str(REPO_ROOT)
        result = subprocess.run(
            [sys.executable, '-m', 'backend.scripts.derive_poc_scope',
             '--decision-record-path', str(self._DECISION_RECORD_PATH),
             '--expected-sha256', 'a' * 64,
             '--emit', 'json'],
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('hash mismatch', result.stderr)

    def test_cli_github_env_emit(self) -> None:
        """CLI --emit github-env writes to GITHUB_ENV file."""
        with tempfile.TemporaryDirectory() as tmp:
            github_env_path = Path(tmp) / 'github_env'
            github_env_path.write_text('')
            env = os.environ.copy()
            env['PYTHONPATH'] = str(REPO_ROOT)
            env['GITHUB_ENV'] = str(github_env_path)
            result = subprocess.run(
                [sys.executable, '-m', 'backend.scripts.derive_poc_scope',
                 '--decision-record-path', str(self._DECISION_RECORD_PATH),
                 '--expected-sha256', self._dr_hash,
                 '--emit', 'github-env'],
                capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            content = github_env_path.read_text()
            self.assertIn('POC_REGION=pir_panjal_nw_himalaya', content)
            self.assertIn('POC_ELEVATION_BAND=middle', content)
            self.assertIn('POC_HEADLINE_HORIZON_HOURS=48', content)


if __name__ == '__main__':
    unittest.main()
