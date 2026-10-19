from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from backend.scripts.generate_technical_artifact import (
    build_technical_artifact_asset,
    build_canonical_manifest,
    select_regional_asset,
    generate_run_derived_artifact,
)


class TestTechnicalArtifactAsset(unittest.TestCase):
    def test_generated_artifact_contains_artifact_id_and_sha256(self) -> None:
        forecast_run_id = 'test-run-001'
        model_metadata = {
            'model_type': 'surrogate_rf_v1',
            'model_version': 'rf_v2',
            'release_decision': {'allowed': True, 'artifact_mode': 'technical_artifact'},
            'artifact_mode': 'technical_artifact',
        }
        payload = {
            'cells': [
                {'status': 'ready', 'danger_output': {'danger_level': 3, 'profile': 'dry'}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'artifact.json'
            artifact = generate_run_derived_artifact(
                forecast_run_id=forecast_run_id,
                model_metadata=model_metadata,
                payload=payload,
                output_path=output_path,
            )

        self.assertIn('artifact_id', artifact)
        self.assertRegex(
            artifact['artifact_id'],
            re.compile(r'^rda_.+_[0-9a-f]{12}$'),
        )
        self.assertIn('sha256', artifact)
        self.assertEqual(len(artifact['sha256']), 64)

    def test_build_technical_artifact_asset_has_all_fields(self) -> None:
        asset = build_technical_artifact_asset(
            artifact_id='rda_test_abc123',
            sha256='a' * 64,
            storage_ref='s3://bucket/runs/test/artifact.json',
            path='/tmp/artifact.json',
            generated_at='2026-07-12T00:00:00Z',
        )
        expected_keys = {'artifact_id', 'sha256', 'media_type', 'storage_ref', 'path', 'roles', 'generated_at'}
        self.assertEqual(set(asset.keys()), expected_keys)
        self.assertEqual(asset['media_type'], 'application/json')
        self.assertEqual(asset['roles'], ['metadata'])

    def test_sha256_recomputed_from_file_bytes_matches(self) -> None:
        forecast_run_id = 'test-run-002'
        model_metadata = {
            'model_type': 'surrogate_rf_v1',
            'model_version': 'rf_v2',
            'release_decision': {'allowed': True, 'artifact_mode': 'technical_artifact'},
            'artifact_mode': 'technical_artifact',
        }
        payload = {
            'cells': [
                {'status': 'ready', 'danger_output': {'danger_level': 2, 'profile': 'wet'}},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'artifact.json'
            artifact = generate_run_derived_artifact(
                forecast_run_id=forecast_run_id,
                model_metadata=model_metadata,
                payload=payload,
                output_path=output_path,
            )
            ready_cells = [
                c for c in payload.get('cells', [])
                if isinstance(c, dict) and c.get('status') == 'ready'
            ]
            # G-11: SHA-256 is now computed from full artifact bytes, not metadata summary
            artifact_copy = dict(artifact)
            artifact_copy['sha256'] = ''
            artifact_copy['artifact_id'] = ''
            recomputed_bytes = json.dumps(artifact_copy, sort_keys=True, default=str).encode('utf-8')
            recomputed = hashlib.sha256(recomputed_bytes).hexdigest()

        self.assertEqual(artifact['sha256'], recomputed)


class TestCanonicalManifest(unittest.TestCase):
    """G-12: Test canonical manifest and multi-region asset selection."""

    def _make_artifact(self) -> dict:
        return {
            'artifact_id': 'rda_test_abc123',
            'sha256': 'abc123def456',
            'artifact_type': 'run_derived_technical_artifact',
            'model_identity': {'model_type': 'surrogate_rf_v1', 'model_version': '0.3.0'},
        }

    def test_manifest_references_artifact_sha256(self):
        """Manifest is built after artifact and references its SHA-256."""
        artifact = self._make_artifact()
        manifest = build_canonical_manifest(artifact)
        self.assertEqual(manifest['artifact_sha256'], 'abc123def456')
        self.assertEqual(manifest['artifact_id'], 'rda_test_abc123')

    def test_manifest_includes_region_assets(self):
        """Manifest lists all regional assets."""
        artifact = self._make_artifact()
        region_assets = [
            {'region': 'great_himalaya', 'storage_ref': 's3://bucket/gh.json', 'sha256': 'aaa'},
            {'region': 'pir_panjal', 'storage_ref': 's3://bucket/pp.json', 'sha256': 'bbb'},
        ]
        manifest = build_canonical_manifest(artifact, region_assets=region_assets)
        self.assertEqual(manifest['asset_count'], 2)
        self.assertEqual(len(manifest['region_assets']), 2)

    def test_manifest_empty_assets_when_none_provided(self):
        """Manifest has empty assets list when none provided."""
        artifact = self._make_artifact()
        manifest = build_canonical_manifest(artifact)
        self.assertEqual(manifest['asset_count'], 0)
        self.assertEqual(manifest['region_assets'], [])

    def test_select_regional_asset_prefers_matching_region(self):
        """select_regional_asset returns the asset matching preferred_region, not just the first."""
        manifest = {
            'region_assets': [
                {'region': 'great_himalaya', 'storage_ref': 's3://bucket/gh.json'},
                {'region': 'pir_panjal', 'storage_ref': 's3://bucket/pp.json'},
            ],
        }
        selected = select_regional_asset(manifest, preferred_region='pir_panjal')
        self.assertIsNotNone(selected)
        self.assertEqual(selected['region'], 'pir_panjal')

    def test_select_regional_asset_falls_back_to_first(self):
        """select_regional_asset falls back to first when no match."""
        manifest = {
            'region_assets': [
                {'region': 'great_himalaya', 'storage_ref': 's3://bucket/gh.json'},
                {'region': 'pir_panjal', 'storage_ref': 's3://bucket/pp.json'},
            ],
        }
        selected = select_regional_asset(manifest, preferred_region='nonexistent')
        self.assertIsNotNone(selected)
        self.assertEqual(selected['region'], 'great_himalaya')

    def test_select_regional_asset_returns_none_for_empty(self):
        """select_regional_asset returns None when no assets."""
        manifest = {'region_assets': []}
        selected = select_regional_asset(manifest)
        self.assertIsNone(selected)

    def test_select_regional_asset_no_preference_returns_first(self):
        """select_regional_asset without preference returns first asset."""
        manifest = {
            'region_assets': [
                {'region': 'great_himalaya', 'storage_ref': 's3://bucket/gh.json'},
                {'region': 'pir_panjal', 'storage_ref': 's3://bucket/pp.json'},
            ],
        }
        selected = select_regional_asset(manifest)
        self.assertEqual(selected['region'], 'great_himalaya')

    def test_runtime_wiring_build_manifest_then_select(self):
        """G-12: Runtime path builds canonical manifest from artifact and selects regional asset."""
        artifact = self._make_artifact()
        region_assets = [
            {'region': 'great_himalaya', 'storage_ref': 's3://bucket/gh.json', 'sha256': 'aaa'},
            {'region': 'pir_panjal', 'storage_ref': 's3://bucket/pp.json', 'sha256': 'bbb'},
        ]
        manifest = build_canonical_manifest(artifact, region_assets=region_assets)
        # Manifest references artifact hash
        self.assertEqual(manifest['artifact_sha256'], 'abc123def456')
        # Select preferred region
        selected = select_regional_asset(manifest, preferred_region='pir_panjal')
        self.assertIsNotNone(selected)
        self.assertEqual(selected['region'], 'pir_panjal')
        # Select default (first) when no preference
        selected_default = select_regional_asset(manifest)
        self.assertIsNotNone(selected_default)
        self.assertEqual(selected_default['region'], 'great_himalaya')

    def test_runtime_wiring_empty_manifest_returns_none(self):
        """G-12: select_regional_asset returns None for empty manifest."""
        manifest = build_canonical_manifest(self._make_artifact())
        self.assertEqual(manifest['asset_count'], 0)
        self.assertIsNone(select_regional_asset(manifest))

    def test_multi_region_manifest_with_three_regions(self):
        """G-12: Manifest with three regions — select preferred and verify fallback."""
        artifact = self._make_artifact()
        region_assets = [
            {'region': 'great_himalaya', 'storage_ref': 's3://bucket/gh.json', 'sha256': 'aaa'},
            {'region': 'pir_panjal', 'storage_ref': 's3://bucket/pp.json', 'sha256': 'bbb'},
            {'region': 'trans_himalaya', 'storage_ref': 's3://bucket/th.json', 'sha256': 'ccc'},
        ]
        manifest = build_canonical_manifest(artifact, region_assets=region_assets)
        self.assertEqual(manifest['asset_count'], 3)
        # Select each region
        for region in ['great_himalaya', 'pir_panjal', 'trans_himalaya']:
            selected = select_regional_asset(manifest, preferred_region=region)
            self.assertIsNotNone(selected)
            self.assertEqual(selected['region'], region)
        # Fallback to first when preferred not found
        selected = select_regional_asset(manifest, preferred_region='nonexistent')
        self.assertIsNotNone(selected)
        self.assertEqual(selected['region'], 'great_himalaya')


if __name__ == '__main__':
    unittest.main()
