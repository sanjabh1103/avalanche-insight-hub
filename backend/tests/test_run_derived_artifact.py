"""Tests for Phase 4: Run-derived technical artifact generation.

Verifies that:
- generate_run_derived_artifact produces artifact with SHA-256
- Artifact includes immutable artifact_id
- Artifact includes model identity from model_metadata
- Artifact includes release_decision from model_metadata
- Artifact includes calibration_manifest
- Artifact includes danger_profile from cells
- Artifact file is written to output_path
- safety_gates reflect live inference (not dry_run)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.scripts.generate_technical_artifact import generate_run_derived_artifact


class TestRunDerivedArtifact(unittest.TestCase):
    """Test generate_run_derived_artifact function."""

    def _make_model_metadata(self) -> dict:
        return {
            'model_type': 'surrogate_rf_v1',
            'model_version': '0.3.0',
            'artifact_mode': 'technical_artifact',
            'release_decision': {
                'allowed': True,
                'artifact_mode': 'technical_artifact',
                'warning_authority': 'none',
                'movement_advice': 'none',
            },
        }

    def _make_payload(self) -> dict:
        return {
            'cells': [
                {
                    'status': 'ready',
                    'danger_output': {
                        'danger_level': 3,
                        'profile': 'heuristic-risk-bands-v1',
                        'factors_used': ['slope_angle', 'snow_load'],
                        'is_shadow_only': False,
                    },
                },
                {
                    'status': 'ready',
                    'danger_output': {
                        'danger_level': 4,
                        'profile': 'heuristic-risk-bands-v1',
                        'factors_used': ['slope_angle', 'snow_load'],
                        'is_shadow_only': False,
                    },
                },
                {
                    'status': 'blocked',
                },
            ],
            'calibration_lineage': {
                'manifest': {'uq_method': 'split_conformal', 'sha256': 'abc123'},
                'calibrator_loaded': True,
                'fallback_active': False,
            },
        }

    def test_artifact_has_sha256(self):
        """Artifact includes a non-empty SHA-256 hash."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_001',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertIn('sha256', artifact)
        self.assertTrue(artifact['sha256'])
        self.assertEqual(len(artifact['sha256']), 64)

    def test_artifact_has_immutable_id(self):
        """Artifact includes artifact_id with run_id and hash prefix."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_002',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertIn('artifact_id', artifact)
        self.assertTrue(artifact['artifact_id'].startswith('rda_test_run_002_'))

    def test_artifact_includes_model_identity(self):
        """Artifact includes model_type and model_version from model_metadata."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_003',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertEqual(artifact['model_identity']['model_type'], 'surrogate_rf_v1')
        self.assertEqual(artifact['model_identity']['model_version'], '0.3.0')

    def test_artifact_includes_release_decision(self):
        """Artifact includes release_decision from model_metadata."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_004',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertIn('release_decision', artifact)
        self.assertTrue(artifact['release_decision']['allowed'])

    def test_artifact_includes_calibration_manifest(self):
        """Artifact includes calibration_manifest from calibration_lineage."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_005',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
            calibration_lineage=self._make_payload()['calibration_lineage'],
        )
        self.assertIn('calibration_manifest', artifact)
        self.assertEqual(artifact['calibration_manifest']['manifest']['uq_method'], 'split_conformal')

    def test_artifact_includes_danger_profile(self):
        """Artifact includes danger_profile with max_danger_level from cells."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_006',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertIn('danger_profile', artifact)
        self.assertEqual(artifact['danger_profile']['max_danger_level'], 4)
        self.assertEqual(artifact['danger_profile']['cell_count'], 2)
        self.assertEqual(artifact['danger_profile']['cells_with_danger_output'], 2)

    def test_artifact_safety_gates_not_dry_run(self):
        """Artifact safety_gates reflect live inference, not dry_run."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_007',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertFalse(artifact['safety_gates']['dry_run'])
        self.assertFalse(artifact['safety_gates']['synthetic_inputs_only'])

    def test_artifact_written_to_file(self):
        """Artifact is written to output_path when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'artifact.json'
            artifact = generate_run_derived_artifact(
                forecast_run_id='test_run_008',
                model_metadata=self._make_model_metadata(),
                payload=self._make_payload(),
                output_path=output_path,
            )
            self.assertTrue(output_path.exists())
            with open(output_path) as f:
                loaded = json.load(f)
            self.assertEqual(loaded['artifact_id'], artifact['artifact_id'])
            self.assertEqual(loaded['sha256'], artifact['sha256'])

    def test_artifact_type_is_run_derived(self):
        """Artifact type is 'run_derived_technical_artifact'."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_009',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertEqual(artifact['artifact_type'], 'run_derived_technical_artifact')

    def test_artifact_version_is_2(self):
        """Artifact version is 2.0.0."""
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_010',
            model_metadata=self._make_model_metadata(),
            payload=self._make_payload(),
        )
        self.assertEqual(artifact['artifact_version'], '2.0.0')

    def test_artifact_with_empty_cells(self):
        """Artifact handles empty cells gracefully."""
        payload = {'cells': []}
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_run_011',
            model_metadata=self._make_model_metadata(),
            payload=payload,
        )
        self.assertEqual(artifact['danger_profile']['max_danger_level'], 0)
        self.assertEqual(artifact['danger_profile']['cell_count'], 0)


class TestArtifactHashAndModelIdentity(unittest.TestCase):
    """G-11: Verify artifact hash is byte-based and model identity uses active_model_type."""

    def _make_payload(self) -> dict:
        return {
            'cells': [
                {
                    'status': 'ready',
                    'danger_output': {'danger_level': 3, 'profile': 'heuristic-risk-bands-v1'},
                },
            ],
        }

    def test_model_identity_uses_active_model_type(self):
        """Model identity reads active_model_type, not model_type."""
        model_metadata = {
            'active_model_type': 'mts_lstm_v1',
            'active_model_version': '0.5.0',
            'model_type': 'surrogate_rf_v1',  # Old key — should NOT be used
            'model_version': '0.3.0',
        }
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_g11_001',
            model_metadata=model_metadata,
            payload=self._make_payload(),
        )
        self.assertEqual(artifact['model_identity']['model_type'], 'mts_lstm_v1')
        self.assertEqual(artifact['model_identity']['model_version'], '0.5.0')

    def test_model_identity_falls_back_to_model_type(self):
        """When active_model_type is absent, falls back to model_type."""
        model_metadata = {
            'model_type': 'surrogate_rf_v1',
            'model_version': '0.3.0',
        }
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_g11_002',
            model_metadata=model_metadata,
            payload=self._make_payload(),
        )
        self.assertEqual(artifact['model_identity']['model_type'], 'surrogate_rf_v1')

    def test_sha256_is_byte_based_not_metadata(self):
        """SHA-256 is computed from full artifact bytes, not a metadata summary."""
        import hashlib
        model_metadata = {
            'active_model_type': 'surrogate_rf_v1',
            'active_model_version': '0.3.0',
        }
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_g11_003',
            model_metadata=model_metadata,
            payload=self._make_payload(),
        )
        # Recompute hash from the artifact dict with placeholder sha256/artifact_id
        artifact_copy = dict(artifact)
        artifact_copy['sha256'] = ''
        artifact_copy['artifact_id'] = ''
        expected_bytes = json.dumps(artifact_copy, sort_keys=True, default=str).encode('utf-8')
        expected_hash = hashlib.sha256(expected_bytes).hexdigest()
        self.assertEqual(artifact['sha256'], expected_hash)

    def test_artifact_id_contains_sha256_prefix(self):
        """Artifact ID contains the first 12 chars of the SHA-256 hash."""
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_g11_004',
            model_metadata=model_metadata,
            payload=self._make_payload(),
        )
        self.assertTrue(artifact['artifact_id'].startswith('rda_test_g11_004_'))
        self.assertEqual(artifact['artifact_id'][-12:], artifact['sha256'][:12])

    def test_different_payloads_produce_different_hashes(self):
        """Different payloads produce different SHA-256 hashes."""
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        payload1 = {'cells': [{'status': 'ready', 'danger_output': {'danger_level': 2, 'profile': 'a'}}]}
        payload2 = {'cells': [{'status': 'ready', 'danger_output': {'danger_level': 4, 'profile': 'b'}}]}
        artifact1 = generate_run_derived_artifact(forecast_run_id='r1', model_metadata=model_metadata, payload=payload1)
        artifact2 = generate_run_derived_artifact(forecast_run_id='r1', model_metadata=model_metadata, payload=payload2)
        self.assertNotEqual(artifact1['sha256'], artifact2['sha256'])

    def test_verify_artifact_hash_valid(self):
        """G-11: verify_artifact_hash returns True for a freshly generated artifact."""
        from backend.scripts.generate_technical_artifact import verify_artifact_hash
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_verify_001',
            model_metadata=model_metadata,
            payload={'cells': [{'status': 'ready', 'danger_output': {'danger_level': 3, 'profile': 'a'}}]},
        )
        self.assertTrue(verify_artifact_hash(artifact))

    def test_verify_artifact_hash_tampered_content(self):
        """G-11: verify_artifact_hash returns False when content is tampered after hashing."""
        from backend.scripts.generate_technical_artifact import verify_artifact_hash
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_verify_002',
            model_metadata=model_metadata,
            payload={'cells': [{'status': 'ready', 'danger_output': {'danger_level': 3, 'profile': 'a'}}]},
        )
        # Tamper with content but keep the original hash
        artifact['cells'] = [{'status': 'ready', 'danger_output': {'danger_level': 5, 'profile': 'tampered'}}]
        self.assertFalse(verify_artifact_hash(artifact))

    def test_verify_artifact_hash_missing_sha256(self):
        """G-11: verify_artifact_hash returns False when sha256 field is empty."""
        from backend.scripts.generate_technical_artifact import verify_artifact_hash
        artifact = {'artifact_type': 'test', 'sha256': '', 'artifact_id': ''}
        self.assertFalse(verify_artifact_hash(artifact))

    def test_verify_artifact_hash_round_trip(self):
        """G-11: Generate artifact, serialize to JSON, deserialize, and verify — hash still matches."""
        import json as _json
        from backend.scripts.generate_technical_artifact import verify_artifact_hash
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_verify_003',
            model_metadata=model_metadata,
            payload={'cells': [{'status': 'ready', 'danger_output': {'danger_level': 2, 'profile': 'b'}}]},
        )
        serialized = _json.dumps(artifact, sort_keys=True, default=str)
        deserialized = _json.loads(serialized)
        self.assertTrue(verify_artifact_hash(deserialized))

    def test_persisted_file_bytes_match_declared_hash(self):
        """G-11: The raw bytes of the persisted file must match the declared sha256."""
        import hashlib as _hashlib
        import json as _json
        import tempfile
        from pathlib import Path
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'artifact.json'
            artifact = generate_run_derived_artifact(
                forecast_run_id='test_persisted_001',
                model_metadata=model_metadata,
                payload={'cells': [{'status': 'ready', 'danger_output': {'danger_level': 3, 'profile': 'a'}}]},
                output_path=output_path,
            )
            # Read the raw persisted file bytes
            raw_bytes = output_path.read_bytes()
            # The persisted file should use canonical serialization (sort_keys=True, no indent)
            # The hash was computed BEFORE sha256/artifact_id/hash_basis were set
            # So we need to blank those fields and recompute
            persisted = _json.loads(raw_bytes)
            persisted['sha256'] = ''
            persisted['artifact_id'] = ''
            recomputed = _hashlib.sha256(
                _json.dumps(persisted, sort_keys=True, default=str).encode('utf-8')
            ).hexdigest()
            self.assertEqual(artifact['sha256'], recomputed,
                             'Declared hash must match recomputed hash from persisted file content')

    def test_artifact_has_hash_basis_field(self):
        """G-11: Artifact must declare its hash basis contract."""
        model_metadata = {'active_model_type': 'test_model', 'active_model_version': '1.0'}
        artifact = generate_run_derived_artifact(
            forecast_run_id='test_basis_001',
            model_metadata=model_metadata,
            payload={'cells': [{'status': 'ready', 'danger_output': {'danger_level': 1, 'profile': 'a'}}]},
        )
        self.assertIn('hash_basis', artifact)
        self.assertEqual(artifact['hash_basis'], 'canonical_content')


if __name__ == '__main__':
    unittest.main()
