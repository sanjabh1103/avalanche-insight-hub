from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MetadataPreflightDependencyBoundaryTests(unittest.TestCase):
    def test_metadata_preflight_imports_without_site_packages(self) -> None:
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(ROOT)
        result = subprocess.run(
            [
                sys.executable,
                '-S',
                '-c',
                'import backend.scripts.audit_training_dataset',
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f'metadata preflight imported a non-stdlib dependency before install: {result.stderr}',
        )

    def test_source_owner_intake_imports_without_site_packages(self) -> None:
        environment = os.environ.copy()
        environment['PYTHONPATH'] = str(ROOT)
        result = subprocess.run(
            [
                sys.executable,
                '-S',
                '-c',
                'import backend.scripts.validate_mvp4_source_manifest',
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f'source-owner intake imported a non-stdlib dependency before install: {result.stderr}',
        )


if __name__ == '__main__':
    unittest.main()
