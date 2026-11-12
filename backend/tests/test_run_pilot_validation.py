"""Tests for run_pilot_validation.py."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure scripts dir is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestColoradoReplay(unittest.TestCase):
    def setUp(self):
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'true'

    def test_replay_runs_without_error(self):
        from scripts.run_pilot_validation import run_colorado_replay
        result = run_colorado_replay()
        self.assertEqual(result['track'], 'colorado_replay')
        self.assertIn('precision', result)
        self.assertIn('known_events', result)
        self.assertIn('anomalies_detected', result)
        self.assertGreater(result['known_events'], 0)

    def test_replay_has_avamap_instructions(self):
        from scripts.run_pilot_validation import run_colorado_replay
        result = run_colorado_replay()
        self.assertIn('avamap_benchmark_instructions', result)
        instructions = result['avamap_benchmark_instructions']
        self.assertEqual(instructions['status'], 'manual_benchmark_required')
        self.assertIn('steps', instructions)
        self.assertGreater(len(instructions['steps']), 0)

    def test_replay_no_public_risk_change(self):
        from scripts.run_pilot_validation import run_colorado_replay
        result = run_colorado_replay()
        # Replay mode should never change public risk
        self.assertNotIn('public_risk_changed', result)


class TestHimalayaShadow(unittest.TestCase):
    def setUp(self):
        os.environ['Partner_BULLETIN_VALIDATION_ENABLED'] = 'true'

    def test_shadow_dry_run(self):
        from scripts.run_pilot_validation import run_himalaya_shadow
        result = run_himalaya_shadow(dry_run=True)
        self.assertEqual(result['track'], 'himalaya_shadow')
        self.assertTrue(result['dry_run'])
        self.assertFalse(result['public_risk_changed'])
        self.assertIsNone(result['shadow_table'])

    def test_shadow_has_bulletin_results(self):
        from scripts.run_pilot_validation import run_himalaya_shadow
        result = run_himalaya_shadow(dry_run=True)
        self.assertIn('bulletins_tested', result)
        self.assertGreater(result['bulletins_tested'], 0)
        self.assertIn('danger_level_accuracy', result)
        self.assertIn('zone_accuracy', result)

    def test_shadow_has_avamap_instructions(self):
        from scripts.run_pilot_validation import run_himalaya_shadow
        result = run_himalaya_shadow(dry_run=True)
        self.assertIn('avamap_benchmark_instructions', result)

    def test_shadow_no_writes_in_dry_run(self):
        from scripts.run_pilot_validation import run_himalaya_shadow
        result = run_himalaya_shadow(dry_run=True)
        self.assertIsNone(result['shadow_table'])


class TestCLIArgumentParsing(unittest.TestCase):
    def test_colorado_requires_replay(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, 'scripts/run_pilot_validation.py', '--region', 'colorado_rockies'],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        self.assertNotEqual(result.returncode, 0)

    def test_himalaya_requires_shadow(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, 'scripts/run_pilot_validation.py', '--region', 'great_himalaya'],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
