"""Tests for the synthetic-safe technical artifact generator."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.generate_technical_artifact import generate_artifact


class TechnicalArtifactTests(unittest.TestCase):
    def test_artifact_has_required_fields(self) -> None:
        artifact = generate_artifact()
        self.assertEqual(artifact['artifact_type'], 'synthetic_safe_technical_artifact')
        self.assertEqual(artifact['pipeline_mode'], 'dry_run_synthetic')
        self.assertIn('generated_at', artifact)
        self.assertIn('settings', artifact)

    def test_hazard_impact_separation_verified(self) -> None:
        artifact = generate_artifact()
        sep = artifact['hazard_impact_separation']
        self.assertTrue(sep['separation_verified'])
        self.assertNotIn('exposure', sep['hazard_vector'])
        self.assertIn('exposure', sep['impact_vector'])

    def test_danger_methodology_configurable(self) -> None:
        artifact = generate_artifact()
        dm = artifact['danger_methodology']
        self.assertTrue(dm['configurable'])
        self.assertIn('default_danger_level', dm)
        self.assertIn('custom_danger_level', dm)

    def test_publication_eligibility_flow(self) -> None:
        artifact = generate_artifact()
        pe = artifact['publication_eligibility']
        self.assertIn('cell_eligible_before_uq', pe)
        self.assertIn('cell_eligible_after_uq', pe)
        self.assertIn('brier_score', pe)

    def test_conformal_prediction_coverage(self) -> None:
        artifact = generate_artifact()
        cp = artifact['conformal_prediction']
        self.assertEqual(cp['method'], 'split_conformal')
        self.assertIsNotNone(cp['empirical_coverage'])
        self.assertGreaterEqual(cp['empirical_coverage'], 0.8)

    def test_safety_gates(self) -> None:
        artifact = generate_artifact()
        sg = artifact['safety_gates']
        self.assertTrue(sg['dry_run'])
        self.assertTrue(sg['no_real_data'])
        self.assertTrue(sg['no_supabase_writes'])
        self.assertTrue(sg['synthetic_inputs_only'])

    def test_calibration_manifest_present(self) -> None:
        artifact = generate_artifact()
        cm = artifact['calibration_manifest']
        self.assertIn('version', cm)
        self.assertIn('sample_count', cm)
        self.assertIn('alpha', cm)
        self.assertIn('uq_method', cm)

    def test_release_decision_present(self) -> None:
        artifact = generate_artifact()
        rd = artifact['release_decision']
        self.assertEqual(rd['artifact_mode'], 'technical_artifact')
        self.assertTrue(rd['allowed'])
        self.assertEqual(rd['warning_authority'], 'none')

    def test_artifact_writes_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'artifact.json'
            generate_artifact(path)
            self.assertTrue(path.exists())
            with open(path) as f:
                loaded = json.load(f)
            self.assertEqual(loaded['artifact_type'], 'synthetic_safe_technical_artifact')


if __name__ == '__main__':
    unittest.main()
