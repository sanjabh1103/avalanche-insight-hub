"""Dependency-boundary tests for the minimal native SNOWPACK image."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest


class SnowpackStorageDependencyContractTests(unittest.TestCase):
    def test_supabase_io_does_not_require_joblib_or_application_artifacts(self) -> None:
        env = os.environ.copy()
        env['SUPABASE_URL'] = 'https://eyyellmffzzujyssaayb.supabase.co'
        env['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
        script = """
import sys
sys.modules['joblib'] = None
from backend.common.supabase_io import _base_url, _headers
assert _base_url() == 'https://eyyellmffzzujyssaayb.supabase.co'
assert _headers()['Authorization'] == 'Bearer test-service-role-key'
"""
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
