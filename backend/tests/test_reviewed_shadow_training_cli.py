"""Invocation checks for the reviewed shadow-training candidate CLI."""
from __future__ import annotations

import subprocess
import sys
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'backend/scripts/build_reviewed_shadow_training_candidates.py'


class TestReviewedShadowTrainingCLI(unittest.TestCase):
    def test_direct_path_and_module_invocation_are_supported(self) -> None:
        commands = (
            [sys.executable, str(SCRIPT), '--help'],
            [sys.executable, '-m', 'backend.scripts.build_reviewed_shadow_training_candidates', '--help'],
        )
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Build shadow-only training candidates', result.stdout)

    def test_direct_path_and_module_emit_same_exclusion_for_invalid_fixture(self) -> None:
        payload = {'cases': [{'id': 'invalid-case', 'status': 'draft'}], 'reviews': []}
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / 'input.json'
            input_path.write_text(json.dumps(payload), encoding='utf-8')
            outputs: list[str] = []
            for command_prefix in (
                [sys.executable, str(SCRIPT)],
                [sys.executable, '-m', 'backend.scripts.build_reviewed_shadow_training_candidates'],
            ):
                output_path = Path(temp_dir) / f'output-{len(outputs)}.json'
                result = subprocess.run(
                    command_prefix + ['--input', str(input_path), '--output', str(output_path)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(output_path.read_text(encoding='utf-8'))
                self.assertEqual(json.loads(outputs[-1])['summary']['excluded_count'], 1)
            self.assertEqual(json.loads(outputs[0]), json.loads(outputs[1]))


if __name__ == '__main__':
    unittest.main()
