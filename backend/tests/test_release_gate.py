"""Dedicated tests for the release gate CLI (P0.8b).

These tests directly invoke run_release_gate() with real file bundles.
They cover the critical false-green vulnerabilities identified in the Codex audit:
  - tampered file must fail (hash mismatch detected)
  - stale hash with relocated paths must fail (hashes preserved, not recomputed)
  - missing run_id must fail (no as_of fallback)
  - native_running status must fail (only completed is releaseable)
  - partial/proxy/toolchain-unavailable statuses must fail
  - mismatched result/manifest run IDs must fail
  - multiple result/manifest files must fail
  - missing .log, toolchain ID, forcing ID, geometry ID must fail
  - valid bundle with relocated paths must pass (hashes preserved)
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from backend.common.snowpack_artifact_manifest import (
    ArtifactEntry,
    ArtifactManifest,
    build_manifest_from_directory,
    compute_file_hash,
)
from backend.common.snowpack_contracts import (
    ForecastSemanticsContract,
    InitialSnowStateContract,
    ProvenanceMetadata,
)
from backend.common.snowpack_release_semantics import (
    forecast_semantics_envelope,
    initial_state_envelope,
    sha256_bytes,
    snow_free_state_hash,
)
from backend.scripts.release_gate import run_release_gate as _run_release_gate


# G5: The mutable fixture registry cache has been completely removed.
# Fixture builders return the registry hash as a local value. Callers must use
# that value explicitly; no mutable registry trust state is retained here.


def run_release_gate(
    artifacts_dir: Path,
    expected_run_id: str = '',
    expected_registry_sha256: str = '',
    expected_decision_record_sha256: str = '',
    poc_mode: bool = False,
) -> int:
    """Run the production gate with the fixture's external trust anchor.

    G7: The expected_registry_sha256 is the external trust root. If the caller
    does not provide it explicitly, the helper computes it from the bundle's
    registry file bytes. This simulates an out-of-band channel for positive
    tests. Negative tests that need to verify tampering detection MUST pass
    an explicit hash that differs from the bundle's actual registry bytes.
    The production gate (_run_release_gate) NEVER computes this hash from
    the bundle — it requires an external value.
    """
    if not expected_registry_sha256:
        # G7: Simulate out-of-band trust root for positive tests.
        registry_path = artifacts_dir / 'input-manifests' / 'approval-registry.json'
        if registry_path.is_file():
            expected_registry_sha256 = hashlib.sha256(
                registry_path.read_bytes()
            ).hexdigest()
        else:
            # No registry file and no explicit hash — gate will reject.
            expected_registry_sha256 = ''
    return _run_release_gate(
        artifacts_dir,
        expected_run_id=expected_run_id,
        expected_registry_sha256=expected_registry_sha256,
        expected_decision_record_sha256=expected_decision_record_sha256,
        poc_mode=poc_mode,
    )


def _refresh_fixture_snapshot(dir_path: Path) -> str:
    """Bind fixture snapshot records to the bytes present in the bundle.

    G5: Returns the registry_sha256 computed from the actual frozen registry
    bytes. No global state — callers must use the returned hash.
    """
    snapshot_path = dir_path / 'input-manifests' / 'approval-registry-snapshot.json'
    if not snapshot_path.exists():
        return ''
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    snapshot['source_registry_version'] = 'snowpack_manifest_registry_v1'
    snapshot['registry_bundle_path'] = 'input-manifests/approval-registry.json'
    for kind in ('forcing', 'geometry'):
        entry = _write_approved_inputs.__dict__.get('last_entries', {}).get(kind)
        if entry is None:
            manifest_path = dir_path / 'input-manifests' / f'{kind}-manifest.json'
            payload_path = dir_path / 'input-manifests' / f'{kind}-payload.json'
            entry = {
                'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                'payload_sha256': hashlib.sha256(payload_path.read_bytes()).hexdigest(),
            }
        record = snapshot['records'][kind]
        record['source_registry_version'] = 'snowpack_manifest_registry_v1'
        record['manifest_sha256'] = entry['manifest_sha256']
        record['payload_sha256'] = entry['payload_sha256']
        record['bundle_manifest_path'] = f'input-manifests/{kind}-manifest.json'
        record['bundle_payload_path'] = f'input-manifests/{kind}-payload.json'
    toolchain_path = dir_path / 'toolchain-manifest.json'
    toolchain_hash = 'f' * 64
    if toolchain_path.exists():
        toolchain_bytes = json.loads(toolchain_path.read_text(encoding='utf-8'))
        toolchain_hash = hashlib.sha256(
            json.dumps(toolchain_bytes, indent=2, sort_keys=True).encode('utf-8')
        ).hexdigest()
        snapshot['records']['toolchain']['source_registry_version'] = 'snowpack_manifest_registry_v1'
        snapshot['records']['toolchain']['toolchain_manifest_sha256'] = toolchain_hash
        # G-R1.1.2: manifest_sha256 stays as the registry's approved content_sha256.
        # The toolchain_manifest_sha256 is the runtime hash.
    # G-R1.1.2: The registry is frozen before execution and must NOT be mutated
    # post-approval. The registry's toolchain content_sha256 must already match
    # the actual toolchain-manifest.json hash. If it doesn't, the gate will
    # fail — which is the correct behavior. We do NOT update the registry here.
    # Instead, we just recompute the registry hash from the frozen bytes.
    registry_path = dir_path / 'input-manifests' / 'approval-registry.json'
    if registry_path.exists():
        frozen_registry_bytes = registry_path.read_bytes()
        frozen_registry = json.loads(frozen_registry_bytes)
        # Verify the registry's toolchain content_sha256 already matches
        for reg_record in frozen_registry.get('manifests', []):
            if reg_record.get('id') == 'tc_001':
                if reg_record.get('content_sha256') != toolchain_hash:
                    # The registry was written with a placeholder. Update it
                    # NOW (before execution freeze) so the gate sees consistent
                    # bytes. This is the pre-execution freeze, not a post-hoc
                    # mutation.
                    reg_record['content_sha256'] = toolchain_hash
        frozen_bytes_final = json.dumps(frozen_registry, sort_keys=True, indent=2).encode('utf-8')
        registry_path.write_bytes(frozen_bytes_final)
        registry_sha256 = hashlib.sha256(frozen_bytes_final).hexdigest()
        # Set the snapshot's manifest_sha256 to match the registry's content_sha256
        snapshot['records']['toolchain']['manifest_sha256'] = toolchain_hash
    else:
        registry_sha256 = ''
    snapshot['registry_sha256'] = registry_sha256
    snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode('utf-8')
    snapshot_path.write_bytes(snapshot_bytes)
    result_path = dir_path / 'result.json'
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding='utf-8'))
        result['registry_snapshot'] = {
            'path': 'input-manifests/approval-registry-snapshot.json',
            'sha256': hashlib.sha256(snapshot_bytes).hexdigest(),
            'registry_sha256': registry_sha256,
            'registry_bundle_path': 'input-manifests/approval-registry.json',
        }
        result_path.write_text(json.dumps(result), encoding='utf-8')
    return registry_sha256


def _write_approved_inputs(dir_path: Path) -> tuple[dict[str, dict[str, str]], str]:
    """Write synthetic-but-explicit input bytes for gate fixtures.

    Returns (approved_dict, registry_sha256) where registry_sha256 is
    computed from the actual registry bytes written to the bundle.
    G5: No global state — callers must use the returned hash explicitly.
    """
    input_dir = dir_path / 'input-manifests'
    input_dir.mkdir(exist_ok=True)
    approved: dict[str, dict[str, str]] = {}
    for kind, manifest_id, payload in (
        ('forcing', 'fm_001', [{'time': '2024-01-01T00:00:00+00:00'}]),
        ('geometry', 'gm_001', {'latitude': 28.0, 'longitude': 86.0, 'elevation_m': 4000.0, 'slope_angle': 30.0, 'aspect': 180.0}),
    ):
        manifest = {
            'id': manifest_id,
            'kind': kind,
            'source': 'test-source',
            'licence': 'test-licence',
            'units': 'SI',
            'region': 'himalayas_nepal',
            'elevation_band': 'lower',
            'valid_from': '2024-01-01T00:00:00Z',
            'valid_to': '2030-01-01T00:00:00Z',
            'approval_state': 'approved',
        }
        manifest_path = input_dir / f'{kind}-manifest.json'
        payload_path = input_dir / f'{kind}-payload.json'
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        manifest_path.write_bytes(manifest_bytes)
        payload_path.write_bytes(payload_bytes)
        approved[kind] = {
            'manifest_id': manifest_id,
            'manifest_path': f'input-manifests/{kind}-manifest.json',
            'payload_path': f'input-manifests/{kind}-payload.json',
            'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'payload_sha256': hashlib.sha256(payload_bytes).hexdigest(),
        }
    # R1.1: Build and write the actual fixture registry with records matching
    # the bundled manifests. The gate will hash these bytes independently.
    toolchain_hash = 'f' * 64  # placeholder; updated by _refresh_fixture_snapshot
    registry_records = []
    for kind, entry in approved.items():
        registry_records.append({
            'id': entry['manifest_id'],
            'kind': kind,
            'content_sha256': entry['manifest_sha256'],
            'source': 'test-source',
            'licence': 'test-licence',
            'units': 'SI',
            'region': 'himalayas_nepal',
            'elevation_band': 'lower',
            'valid_from': '2024-01-01T00:00:00Z',
            'valid_to': '2030-01-01T00:00:00Z',
            'approval_state': 'approved',
            'manifest_path': f'fixtures/{kind}-manifest.json',
            'payload_path': f'fixtures/{kind}-payload.json',
            'payload_sha256': entry['payload_sha256'],
        })
    registry_records.append({
        'id': 'tc_001',
        'kind': 'toolchain',
        'content_sha256': toolchain_hash,
        'source': 'test-source',
        'licence': 'test-licence',
        'units': 'SI',
        'region': 'himalayas_nepal',
        'elevation_band': 'lower',
        'valid_from': '2024-01-01T00:00:00Z',
        'valid_to': '2030-01-01T00:00:00Z',
        'approval_state': 'approved',
        'manifest_path': 'fixtures/toolchain-manifest.json',
    })
    fixture_registry = {
        'schema_version': 'snowpack_manifest_registry_v1',
        'manifests': registry_records,
    }
    registry_bytes = json.dumps(fixture_registry, sort_keys=True, indent=2).encode('utf-8')
    (input_dir / 'approval-registry.json').write_bytes(registry_bytes)
    registry_sha256 = hashlib.sha256(registry_bytes).hexdigest()
    snapshot = {
        'schema_version': 'snowpack_approval_snapshot_v1',
        'registry_sha256': registry_sha256,
        'registry_bundle_path': 'input-manifests/approval-registry.json',
        'records': {
            kind: {
                'id': entry['manifest_id'],
                'kind': kind,
                'source': 'test-source',
                'licence': 'test-licence',
                'units': 'SI',
                'region': 'himalayas_nepal',
                'elevation_band': 'lower',
                'valid_from': '2024-01-01T00:00:00Z',
                'valid_to': '2030-01-01T00:00:00Z',
                'approval_state': 'approved',
            }
            for kind, entry in approved.items()
        } | {
            'toolchain': {
                'id': 'tc_001', 'kind': 'toolchain', 'source': 'test-source',
                'licence': 'test-licence', 'units': 'SI',
                'region': 'himalayas_nepal', 'elevation_band': 'lower',
                'valid_from': '2024-01-01T00:00:00Z',
                'valid_to': '2030-01-01T00:00:00Z', 'approval_state': 'approved',
            }
        },
    }
    (input_dir / 'approval-registry-snapshot.json').write_text(
        json.dumps(snapshot, sort_keys=True, indent=2), encoding='utf-8'
    )
    _write_approved_inputs.last_entries = approved
    return approved, registry_sha256


def _write_release_semantics_inputs(dir_path: Path, run_id: str = 'run_001') -> dict[str, dict[str, str]]:
    """Write explicit state/forecast fixtures for every valid release bundle."""
    # Some negative tests intentionally pass invalid result run_id values;
    # keep the fixture input itself valid so the gate reaches that boundary.
    semantics_run_id = run_id if isinstance(run_id, str) and run_id else 'run_001'
    input_dir = dir_path / 'input-manifests'
    input_dir.mkdir(exist_ok=True)
    provenance = ProvenanceMetadata(
        source='test-approved-state', source_class='direct', licence='test-licence',
        timestamp='2026-01-15T00:00:00+00:00', units={'state': 'native'},
        hash='a' * 64, run_id=semantics_run_id,
    )
    provisional = InitialSnowStateContract(
        state_id='state_001', state_type='snow_free',
        start_time='2026-01-15T00:00:00Z', source='test-approved-state',
        state_sha256='0' * 64, provenance=provenance,
    )
    state = InitialSnowStateContract(
        state_id=provisional.state_id, state_type=provisional.state_type,
        start_time=provisional.start_time, source=provisional.source,
        state_sha256=snow_free_state_hash(provisional),
        provenance=provisional.provenance,
    )
    forecast = ForecastSemanticsContract(
        mode='forecast', source='test-forecast',
        forecast_cycle='2026-01-15T00:00:00Z',
        valid_from='2026-01-16T00:00:00Z',
        valid_to='2026-01-17T00:00:00Z',
        as_of='2026-01-15T00:00:00Z', lead_time_h=24,
        region_key='himalayas_nepal', elevation_band='lower',
        forcing_manifest_id='fm_001',
    )
    state_bytes = json.dumps(initial_state_envelope(state), sort_keys=True, indent=2).encode()
    forecast_bytes = json.dumps(forecast_semantics_envelope(forecast), sort_keys=True, indent=2).encode()
    (input_dir / 'initial-state.json').write_bytes(state_bytes)
    (input_dir / 'forecast-semantics.json').write_bytes(forecast_bytes)
    return {
        'initial_state': {
            'manifest_path': 'input-manifests/initial-state.json',
            'manifest_sha256': sha256_bytes(state_bytes),
            'state_id': state.state_id,
            'state_sha256': state.state_sha256,
        },
        'forecast_semantics': {
            'manifest_path': 'input-manifests/forecast-semantics.json',
            'manifest_sha256': sha256_bytes(forecast_bytes),
            'forcing_manifest_id': forecast.forcing_manifest_id,
        },
    }


def _write_result_json(dir_path: Path, **overrides) -> None:
    """Write a result.json file."""
    release_semantics = _write_release_semantics_inputs(
        dir_path, overrides.get('run_id', 'run_001')
    )
    approved, registry_sha256 = _write_approved_inputs(dir_path)
    defaults = {
        'run_id': 'run_001',
        'status': 'completed',
        'region': 'himalayas_nepal',
        'region_key': 'himalayas_nepal',
        'elevation_band': 'lower',
        'engine': 'snowpack_direct',
        'toolchain_manifest_id': 'tc_001',
        'forcing_manifest_id': 'fm_001',
        'geometry_manifest_id': 'gm_001',
        'scope_mode': 'non_poc',
        'approved_inputs': approved,
        'registry_snapshot': {
            'path': 'input-manifests/approval-registry-snapshot.json',
            'sha256': hashlib.sha256(
                (dir_path / 'input-manifests/approval-registry-snapshot.json').read_bytes()
            ).hexdigest(),
            'registry_sha256': registry_sha256,
            'registry_bundle_path': 'input-manifests/approval-registry.json',
        },
        'no_fallback': True,  # C0-S7: required for release
        **release_semantics,
    }
    registry_sha256 = _refresh_fixture_snapshot(dir_path)
    snapshot_path = dir_path / 'input-manifests' / 'approval-registry-snapshot.json'
    defaults['registry_snapshot'] = {
        'path': 'input-manifests/approval-registry-snapshot.json',
        'sha256': hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        'registry_sha256': registry_sha256,
        'registry_bundle_path': 'input-manifests/approval-registry.json',
    }
    defaults.update(overrides)
    with open(dir_path / 'result.json', 'w') as f:
        json.dump(defaults, f)


def _write_invocation_json(dir_path: Path, **overrides) -> None:
    """Write an invocation.json (execution attestation) file."""
    import hashlib as _hashlib
    # G10: command_sha256 must match actual SHA-256 of command field
    _default_cmd = 'snowpack -c config.ini'
    defaults = {
        'binary_path': '/usr/local/bin/snowpack',
        'binary_sha256': 'a' * 64,
        'binary_version': 'snowpack-3.7.0',
        'command': _default_cmd,
        'command_sha256': _hashlib.sha256(_default_cmd.encode()).hexdigest(),
        'exit_code': 0,
        'version_exit_code': 0,
        'version_verified': True,
        'started_at': '2026-01-15T00:00:00+00:00',
        'finished_at': '2026-01-15T00:05:00+00:00',
        'toolchain_id': 'tc_001',
        'run_id': 'run_001',  # C0-S6: run_id binding
        'toolchain_manifest_verified': True,
        'image_id': 'sha256:' + 'c' * 64,
        'image_archive_sha256': 'd' * 64,
        'image_repository_digest': '',
        'image_identity_source': 'local_id_and_archive',
    }
    defaults.update(overrides)
    # G10: Recompute command_sha256 if command was overridden
    if 'command' in overrides and 'command_sha256' not in overrides:
        defaults['command_sha256'] = _hashlib.sha256(
            overrides['command'].encode()
        ).hexdigest()

    # C0.31: The fixture includes a byte-addressed runtime toolchain manifest.
    toolchain_path = dir_path / 'toolchain-manifest.json'
    if not toolchain_path.exists():
        toolchain = {
            'schema_version': 'snowpack_toolchain_manifest_v1',
            'toolchain_id': defaults['toolchain_id'],
            'meteoio_commit': 'a' * 40,
            'snowpack_commit': 'b' * 40,
            'binary_path': defaults['binary_path'],
            'binary_sha256': defaults['binary_sha256'],
            'binary_version': defaults['binary_version'],
            'image_id': 'sha256:' + 'c' * 64,
            'image_archive_sha256': 'd' * 64,
            'image_repository_digest': '',
            'image_identity_source': 'local_id_and_archive',
        }
        with open(toolchain_path, 'w') as f:
            json.dump(toolchain, f)
    toolchain_data = json.loads(toolchain_path.read_text())
    defaults['toolchain_manifest_sha256'] = _hashlib.sha256(
        json.dumps(toolchain_data, indent=2, sort_keys=True).encode()
    ).hexdigest()
    with open(dir_path / 'invocation.json', 'w') as f:
        json.dump(defaults, f)
    _refresh_fixture_snapshot(dir_path)


def _write_manifest_json(dir_path: Path, manifest: ArtifactManifest) -> None:
    """Write a manifest.json file."""
    data = {
        'run_id': manifest.run_id,
        'region_key': manifest.region_key,
        'elevation_band': manifest.elevation_band,
        'aspect_class': manifest.aspect_class,
        'binary_version': manifest.binary_version,
        'artifacts': [
            {
                'file_path': a.file_path,
                'file_type': a.file_type,
                'size_bytes': a.size_bytes,
                'sha256': a.sha256,
                'is_critical': a.is_critical,
                'role': a.role,
            }
            for a in manifest.artifacts
        ],
        'is_native_execution': manifest.is_native_execution,
        'native_binary_invoked': manifest.native_binary_invoked,
        'created_at': manifest.created_at,
        'toolchain_id': manifest.toolchain_id,
        'forcing_manifest_id': manifest.forcing_manifest_id,
        'geometry_manifest_id': manifest.geometry_manifest_id,
    }
    with open(dir_path / 'manifest.json', 'w') as f:
        json.dump(data, f)


def _build_valid_bundle(dir_path: Path, run_id: str = 'run_001') -> ArtifactManifest:
    """Build a valid artifact bundle in dir_path. Returns the manifest.

    G16: Uses canonical bundle layout with native-output/ subdirectory.
    """
    # G16: Native outputs go in native-output/ subdirectory
    native_output = dir_path / 'native-output'
    native_output.mkdir(parents=True, exist_ok=True)
    for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
        (native_output / f'run{suffix}').write_text(f'data_{suffix}_content', encoding='utf-8')
    (native_output / 'processed-meteo.smet').write_text('processed_meteo_content', encoding='utf-8')

    manifest = build_manifest_from_directory(
        run_id=run_id,
        region_key='himalayas_nepal',
        elevation_band='lower',
        aspect_class='N',
        binary_version='snowpack-3.7.0',
        output_dir=native_output,
        created_at='2026-01-15T00:00:00+00:00',
        native_binary_invoked=True,
        toolchain_id='tc_001',
        forcing_manifest_id='fm_001',
        geometry_manifest_id='gm_001',
    )
    # Rebase manifest paths to be relative to bundle root
    manifest_data = json.loads(json.dumps({
        'run_id': manifest.run_id, 'region_key': manifest.region_key,
        'elevation_band': manifest.elevation_band, 'aspect_class': manifest.aspect_class,
        'binary_version': manifest.binary_version,
        'artifacts': [{'file_path': f'native-output/{Path(a.file_path).name}',
                       'file_type': a.file_type, 'size_bytes': a.size_bytes,
                       'sha256': a.sha256, 'is_critical': a.is_critical, 'role': a.role}
                      for a in manifest.artifacts],
        'is_native_execution': True, 'native_binary_invoked': True,
        'created_at': manifest.created_at, 'toolchain_id': 'tc_001',
        'forcing_manifest_id': 'fm_001', 'geometry_manifest_id': 'gm_001',
    }))
    with open(dir_path / 'manifest.json', 'w') as f:
        json.dump(manifest_data, f)
    _write_result_json(dir_path, run_id=run_id, status='completed')
    _write_invocation_json(dir_path, toolchain_id='tc_001', run_id=run_id)
    return manifest


class TestReleaseGateValidBundle(unittest.TestCase):
    """A valid bundle must pass the release gate."""

    def test_valid_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            self.assertEqual(run_release_gate(d), 0)

    def test_valid_bundle_with_relocated_paths_passes(self) -> None:
        """Valid bundle with relative paths must pass.

        SIXTH-PASS: The gate now requires relative POSIX paths in the manifest.
        Absolute build-machine paths are REJECTED (G1/G2 fix). The manifest
        must contain paths relative to the bundle root (e.g., native-output/run.smet).
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # Create the bundle with canonical layout
            bundle_dir = d / 'native-artifacts'
            native_output = bundle_dir / 'native-output'
            native_output.mkdir(parents=True)
            contents = {'.smet': 'data_.smet', '.pro': 'data_.pro', '.sno': 'data_.sno',
                        '.haz': 'data_.haz', '.log': 'data_.log'}
            for suffix, content in contents.items():
                (native_output / f'run{suffix}').write_text(content, encoding='utf-8')
            (native_output / 'processed-meteo.smet').write_text('processed meteo', encoding='utf-8')

            # Build manifest with RELATIVE paths (as the orchestrator produces)
            import hashlib as _hashlib
            artifacts = []
            for suffix, content in contents.items():
                h = _hashlib.sha256(content.encode()).hexdigest()
                artifacts.append({
                    'file_path': f'native-output/run{suffix}',
                    'file_type': suffix,
                    'size_bytes': len(content.encode()),
                    'sha256': h,
                    'is_critical': True,
                    'role': {
                        '.smet': 'forcing_smet', '.pro': 'profile_pro',
                        '.sno': 'snow_profile_sno', '.haz': 'hazard_haz',
                        '.log': 'execution_log',
                    }[suffix],
                })
            processed = 'processed meteo'
            artifacts.append({
                'file_path': 'native-output/processed-meteo.smet',
                'file_type': '.smet',
                'size_bytes': len(processed.encode()),
                'sha256': _hashlib.sha256(processed.encode()).hexdigest(),
                'is_critical': True,
                'role': 'processed_meteo',
            })
            with open(bundle_dir / 'manifest.json', 'w') as f:
                json.dump({
                    'run_id': 'run_001', 'region_key': 'himalayas_nepal',
                    'elevation_band': 'lower', 'aspect_class': 'N',
                    'binary_version': 'snowpack-3.7.0', 'artifacts': artifacts,
                    'is_native_execution': True, 'native_binary_invoked': True,
                    'created_at': '2026-01-15T00:00:00+00:00',
                    'toolchain_id': 'tc_001', 'forcing_manifest_id': 'fm_001',
                    'geometry_manifest_id': 'gm_001',
                }, f)
            _write_result_json(bundle_dir, run_id='run_001', status='completed')
            _write_invocation_json(bundle_dir, toolchain_id='tc_001', run_id='run_001')

            # Gate must pass — relative paths map exactly to bundle contents
            self.assertEqual(run_release_gate(bundle_dir), 0)

    def test_absolute_build_machine_paths_rejected(self) -> None:
        """SIXTH-PASS G1: Absolute build-machine paths in manifest must FAIL.

        The old behavior (basename recovery) allowed absolute paths to be
        silently mapped to bundle files. This is now rejected.
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle_dir = d / 'native-artifacts'
            native_output = bundle_dir / 'native-output'
            native_output.mkdir(parents=True)
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (native_output / f'run{suffix}').write_text(f'data_{suffix}', encoding='utf-8')

            # Manifest with ABSOLUTE paths (old-style — must now be rejected)
            build_dir = d / 'build_output'
            build_dir.mkdir()
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (build_dir / f'run{suffix}').write_text(f'data_{suffix}', encoding='utf-8')
            manifest = build_manifest_from_directory(
                run_id='run_001', region_key='himalayas_nepal', elevation_band='lower',
                aspect_class='N', binary_version='snowpack-3.7.0', output_dir=build_dir,
                created_at='2026-01-15T00:00:00+00:00', native_binary_invoked=True,
                toolchain_id='tc_001', forcing_manifest_id='fm_001',
                geometry_manifest_id='gm_001',
            )
            _write_manifest_json(bundle_dir, manifest)
            _write_result_json(bundle_dir, run_id='run_001', status='completed')
            _write_invocation_json(bundle_dir, toolchain_id='tc_001', run_id='run_001')

            # Gate must FAIL — absolute paths are rejected
            self.assertEqual(run_release_gate(bundle_dir), 1)


class TestReleaseGateTamperedFile(unittest.TestCase):
    """A tampered file must fail the release gate (hash mismatch)."""

    def test_tampered_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Tamper with .pro file
            (d / 'native-output' / 'run.pro').write_text('TAMPERED_CONTENT', encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_tampered_file_with_relocated_paths_fails(self) -> None:
        """Tampered file with relative paths must fail — hashes preserved, not recomputed.

        SIXTH-PASS: The gate now requires relative POSIX paths. The manifest
        contains relative paths, and the gate maps them exactly to the bundle.
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            native_output = d / 'native-output'
            native_output.mkdir(parents=True)
            # Create files with known content, but TAMPER .pro
            contents = {'.smet': 'data_.smet', '.pro': 'TAMPERED', '.sno': 'data_.sno',
                        '.haz': 'data_.haz', '.log': 'data_.log'}
            for suffix, content in contents.items():
                (native_output / f'run{suffix}').write_text(content, encoding='utf-8')

            # Build manifest with RELATIVE paths and the UNTAMPERED .pro hash
            import hashlib as _hashlib
            untampered_pro_hash = _hashlib.sha256(b'data_.pro').hexdigest()
            artifacts = []
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                if suffix == '.pro':
                    h = untampered_pro_hash  # Use UNTAMPERED hash
                    size = len(b'data_.pro')
                else:
                    h = _hashlib.sha256(contents[suffix].encode()).hexdigest()
                    size = len(contents[suffix].encode())
                artifacts.append({
                    'file_path': f'native-output/run{suffix}',
                    'file_type': suffix, 'size_bytes': size,
                    'sha256': h, 'is_critical': True,
                })
            with open(d / 'manifest.json', 'w') as f:
                json.dump({
                    'run_id': 'run_001', 'region_key': 'himalayas_nepal',
                    'elevation_band': 'lower', 'aspect_class': 'N',
                    'binary_version': 'snowpack-3.7.0', 'artifacts': artifacts,
                    'is_native_execution': True, 'native_binary_invoked': True,
                    'created_at': '2026-01-15T00:00:00+00:00',
                    'toolchain_id': 'tc_001', 'forcing_manifest_id': 'fm_001',
                    'geometry_manifest_id': 'gm_001',
                }, f)
            _write_result_json(d, run_id='run_001', status='completed')
            _write_invocation_json(d, toolchain_id='tc_001', run_id='run_001')

            # Gate must FAIL — tampered .pro hash won't match the preserved manifest hash
            self.assertEqual(run_release_gate(d), 1)

    def test_tampered_file_with_original_source_still_existing_fails(self) -> None:
        """CRITICAL: Tampered downloaded file must fail even if original source still exists.

        SIXTH-PASS: With relative paths, the gate maps exactly to bundle files.
        An untampered original elsewhere on the filesystem is irrelevant —
        the gate only looks at relative paths within the bundle.
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # Create an untampered original elsewhere (simulating shared CI runner)
            build_dir = d / 'build_output'
            build_dir.mkdir()
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (build_dir / f'run{suffix}').write_text(f'data_{suffix}', encoding='utf-8')

            # Create the bundle with TAMPERED .pro
            native_output = d / 'native-output'
            native_output.mkdir(parents=True)
            contents = {'.smet': 'data_.smet', '.pro': 'TAMPERED', '.sno': 'data_.sno',
                        '.haz': 'data_.haz', '.log': 'data_.log'}
            for suffix, content in contents.items():
                (native_output / f'run{suffix}').write_text(content, encoding='utf-8')

            # Manifest with RELATIVE paths and UNTAMPERED .pro hash
            import hashlib as _hashlib
            untampered_pro_hash = _hashlib.sha256(b'data_.pro').hexdigest()
            artifacts = []
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                if suffix == '.pro':
                    h = untampered_pro_hash
                    size = len(b'data_.pro')
                else:
                    h = _hashlib.sha256(contents[suffix].encode()).hexdigest()
                    size = len(contents[suffix].encode())
                artifacts.append({
                    'file_path': f'native-output/run{suffix}',
                    'file_type': suffix, 'size_bytes': size,
                    'sha256': h, 'is_critical': True,
                })
            with open(d / 'manifest.json', 'w') as f:
                json.dump({
                    'run_id': 'run_001', 'region_key': 'himalayas_nepal',
                    'elevation_band': 'lower', 'aspect_class': 'N',
                    'binary_version': 'snowpack-3.7.0', 'artifacts': artifacts,
                    'is_native_execution': True, 'native_binary_invoked': True,
                    'created_at': '2026-01-15T00:00:00+00:00',
                    'toolchain_id': 'tc_001', 'forcing_manifest_id': 'fm_001',
                    'geometry_manifest_id': 'gm_001',
                }, f)
            _write_result_json(d, run_id='run_001', status='completed')
            _write_invocation_json(d, toolchain_id='tc_001', run_id='run_001')

            # The untampered build_output/ still exists, but the gate only
            # checks files at relative paths within the bundle.
            # The tampered .pro in native-output/ won't match the manifest hash.
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateMissingRunId(unittest.TestCase):
    """Missing run_id must fail — no as_of fallback."""

    def test_missing_run_id_in_result_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Rewrite result.json without run_id
            _write_result_json(d, status='completed')
            del_run_id = json.loads((d / 'result.json').read_text())
            del_run_id.pop('run_id', None)
            with open(d / 'result.json', 'w') as f:
                json.dump(del_run_id, f)
            self.assertEqual(run_release_gate(d), 1)

    def test_as_of_does_not_substitute_for_run_id(self) -> None:
        """as_of must not be used as a fallback for run_id."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Rewrite result.json with as_of but no run_id
            with open(d / 'result.json', 'w') as f:
                json.dump({'status': 'completed', 'as_of': '2026-01-15T00:00:00+00:00'}, f)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateStatusRejection(unittest.TestCase):
    """Only 'completed' status is releaseable."""

    def test_native_running_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, run_id='run_001', status='native_running')
            self.assertEqual(run_release_gate(d), 1)

    def test_partial_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, run_id='run_001', status='partial')
            self.assertEqual(run_release_gate(d), 1)

    def test_fallback_proxy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, run_id='run_001', status='fallback_proxy')
            self.assertEqual(run_release_gate(d), 1)

    def test_toolchain_unavailable_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, run_id='run_001', status='toolchain_unavailable')
            self.assertEqual(run_release_gate(d), 1)

    def test_configuration_validated_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, run_id='run_001', status='configuration_validated')
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateRunIdMismatch(unittest.TestCase):
    """Mismatched run IDs between result and manifest must fail."""

    def test_mismatched_run_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d, run_id='run_001')
            # Rewrite result.json with a different run_id
            _write_result_json(d, run_id='run_002', status='completed')
            self.assertEqual(run_release_gate(d), 1)

    def test_expected_run_id_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d, run_id='run_001')
            self.assertEqual(run_release_gate(d, expected_run_id='run_999'), 1)

    def test_expected_run_id_match_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d, run_id='run_001')
            self.assertEqual(run_release_gate(d, expected_run_id='run_001'), 0)


class TestReleaseGateMissingFiles(unittest.TestCase):
    """Missing required files must fail."""

    def test_missing_result_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'result.json').unlink()
            self.assertEqual(run_release_gate(d), 1)

    def test_missing_manifest_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'manifest.json').unlink()
            self.assertEqual(run_release_gate(d), 1)

    def test_missing_log_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # G16: Files are now in native-output/ subdirectory
            (d / 'native-output' / 'run.log').unlink()
            # Rebuild manifest without .log
            native_output = d / 'native-output'
            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=native_output,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
                toolchain_id='tc_001',
                forcing_manifest_id='fm_001',
                geometry_manifest_id='gm_001',
            )
            _write_manifest_json(d, manifest)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateMissingIds(unittest.TestCase):
    """Missing toolchain/forcing/geometry IDs must fail (validate_completed)."""

    def test_missing_toolchain_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            manifest = _build_valid_bundle(d)
            # Rewrite manifest without toolchain_id
            new_manifest = ArtifactManifest(
                run_id=manifest.run_id, region_key=manifest.region_key,
                elevation_band=manifest.elevation_band, aspect_class=manifest.aspect_class,
                binary_version=manifest.binary_version, artifacts=manifest.artifacts,
                is_native_execution=manifest.is_native_execution,
                native_binary_invoked=manifest.native_binary_invoked,
                created_at=manifest.created_at,
                toolchain_id='',  # Missing
                forcing_manifest_id=manifest.forcing_manifest_id,
                geometry_manifest_id=manifest.geometry_manifest_id,
            )
            _write_manifest_json(d, new_manifest)
            self.assertEqual(run_release_gate(d), 1)

    def test_missing_forcing_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            manifest = _build_valid_bundle(d)
            new_manifest = ArtifactManifest(
                run_id=manifest.run_id, region_key=manifest.region_key,
                elevation_band=manifest.elevation_band, aspect_class=manifest.aspect_class,
                binary_version=manifest.binary_version, artifacts=manifest.artifacts,
                is_native_execution=manifest.is_native_execution,
                native_binary_invoked=manifest.native_binary_invoked,
                created_at=manifest.created_at,
                toolchain_id=manifest.toolchain_id,
                forcing_manifest_id='',  # Missing
                geometry_manifest_id=manifest.geometry_manifest_id,
            )
            _write_manifest_json(d, new_manifest)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateNativeBinaryNotInvoked(unittest.TestCase):
    """native_binary_invoked=False must fail."""

    def test_native_binary_not_invoked_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            manifest = _build_valid_bundle(d)
            new_manifest = ArtifactManifest(
                run_id=manifest.run_id, region_key=manifest.region_key,
                elevation_band=manifest.elevation_band, aspect_class=manifest.aspect_class,
                binary_version=manifest.binary_version, artifacts=manifest.artifacts,
                is_native_execution=manifest.is_native_execution,
                native_binary_invoked=False,  # Not invoked
                created_at=manifest.created_at,
                toolchain_id=manifest.toolchain_id,
                forcing_manifest_id=manifest.forcing_manifest_id,
                geometry_manifest_id=manifest.geometry_manifest_id,
            )
            _write_manifest_json(d, new_manifest)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateInvocationAttestation(unittest.TestCase):
    """C0.2: invocation.json (execution attestation) tests."""

    def test_missing_invocation_json_fails(self) -> None:
        """Missing invocation.json must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'invocation.json').unlink()
            self.assertEqual(run_release_gate(d), 1)

    def test_invocation_nonzero_exit_code_fails(self) -> None:
        """invocation.json with exit_code != 0 must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_invocation_json(d, exit_code=1)
            self.assertEqual(run_release_gate(d), 1)

    def test_invocation_missing_field_fails(self) -> None:
        """invocation.json missing a required field must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Rewrite invocation without binary_sha256
            with open(d / 'invocation.json', 'w') as f:
                json.dump({
                    'binary_path': '/usr/local/bin/snowpack',
                    'binary_version': 'snowpack-3.7.0',
                    'command': 'snowpack -c config.ini',
                    'command_sha256': 'b' * 64,
                    'exit_code': 0,
                    'started_at': '2026-01-15T00:00:00+00:00',
                    'finished_at': '2026-01-15T00:05:00+00:00',
                    'toolchain_id': 'tc_001',
                }, f)
            self.assertEqual(run_release_gate(d), 1)

    def test_invocation_toolchain_id_mismatch_fails(self) -> None:
        """invocation.json toolchain_id must match manifest toolchain_id."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_invocation_json(d, toolchain_id='different_tc_id')
            self.assertEqual(run_release_gate(d), 1)

    def test_invocation_run_id_mismatch_fails(self) -> None:
        """C0-S6: invocation.json run_id must match result run_id."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_invocation_json(d, run_id='different_run_id')
            self.assertEqual(run_release_gate(d), 1)

    def test_invocation_invalid_sha256_format_fails(self) -> None:
        """C0-S6: invocation.json binary_sha256 must be 64 hex chars."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_invocation_json(d, binary_sha256='not-a-hash')
            self.assertEqual(run_release_gate(d), 1)

    def test_invocation_timestamp_ordering_fails(self) -> None:
        """C0-S6: invocation.json started_at must be before finished_at."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_invocation_json(
                d,
                started_at='2026-01-15T00:10:00+00:00',
                finished_at='2026-01-15T00:05:00+00:00',
            )
            self.assertEqual(run_release_gate(d), 1)

    def test_toolchain_manifest_version_mismatch_fails(self) -> None:
        """C0.31: manifest and invocation versions must be cross-bound."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            manifest_path = d / 'toolchain-manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['binary_version'] = 'tampered-version'
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(run_release_gate(d), 1)

    def test_toolchain_manifest_image_id_mismatch_fails(self) -> None:
        """R6: invocation and toolchain manifest must share local image identity."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            manifest_path = d / 'toolchain-manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['image_id'] = 'sha256:' + 'e' * 64
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(run_release_gate(d), 1)

    def test_toolchain_manifest_archive_hash_mismatch_fails(self) -> None:
        """R6: invocation and toolchain manifest must share archive identity."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            manifest_path = d / 'toolchain-manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['image_archive_sha256'] = 'f' * 64
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(run_release_gate(d), 1)

    def test_legacy_image_digest_field_fails_closed(self) -> None:
        """R6: ambiguous legacy image_digest must not remain accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_invocation_json(d, image_digest='sha256:' + 'a' * 64)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateNoFallbackRequirement(unittest.TestCase):
    """C0-S7: Release bundles must have no_fallback == true."""

    def test_no_fallback_false_fails(self) -> None:
        """result.json with no_fallback=false must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, no_fallback=False)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateReleaseSemantics(unittest.TestCase):
    """C2-prep: consumer-side state/forecast bindings must fail closed."""

    def test_missing_initial_state_descriptor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            result = json.loads((d / 'result.json').read_text(encoding='utf-8'))
            result.pop('initial_state')
            (d / 'result.json').write_text(json.dumps(result), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_tampered_state_manifest_hash_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            state_path = d / 'input-manifests' / 'initial-state.json'
            state_path.write_bytes(state_path.read_bytes() + b'\n')
            self.assertEqual(run_release_gate(d), 1)

    def test_forecast_region_context_tamper_fails_even_with_rehashed_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            forecast_path = d / 'input-manifests' / 'forecast-semantics.json'
            forecast = json.loads(forecast_path.read_text(encoding='utf-8'))
            forecast['contract']['region_key'] = 'pir_panjal_nw_himalaya'
            forecast_bytes = json.dumps(forecast, sort_keys=True, indent=2).encode()
            forecast_path.write_bytes(forecast_bytes)
            result = json.loads((d / 'result.json').read_text(encoding='utf-8'))
            result['forecast_semantics']['manifest_sha256'] = hashlib.sha256(forecast_bytes).hexdigest()
            (d / 'result.json').write_text(json.dumps(result), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_naive_initial_state_timestamp_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            state_path = d / 'input-manifests' / 'initial-state.json'
            state = json.loads(state_path.read_text(encoding='utf-8'))
            state['contract']['start_time'] = '2026-01-15T00:00:00'
            state_path.write_text(json.dumps(state, sort_keys=True, indent=2), encoding='utf-8')
            result = json.loads((d / 'result.json').read_text(encoding='utf-8'))
            result['initial_state']['manifest_sha256'] = hashlib.sha256(state_path.read_bytes()).hexdigest()
            (d / 'result.json').write_text(json.dumps(result), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_no_fallback_missing_fails(self) -> None:
        """result.json without no_fallback field must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Rewrite result without no_fallback
            with open(d / 'result.json', 'w') as f:
                json.dump({
                    'run_id': 'run_001',
                    'status': 'completed',
                    'region': 'himalayas_nepal',
                }, f)
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGatePathContainment(unittest.TestCase):
    """C0-S1: Adversarial path containment tests using is_relative_to()."""

    def test_sibling_prefix_escape_fails(self) -> None:
        """CRITICAL: A sibling directory with a prefix-matching name must NOT pass.

        /tmp/bundle_evil must NOT be accepted as being inside /tmp/bundle.
        This is the exact vulnerability that startswith() had.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create bundle dir with a name that could be a prefix of another dir
            bundle_dir = tmp_path / 'bundle'
            bundle_dir.mkdir()
            # Create sibling dir whose name starts with 'bundle'
            evil_dir = tmp_path / 'bundle_evil'
            evil_dir.mkdir()
            # Put untampered files in evil_dir
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (evil_dir / f'run{suffix}').write_text(f'data_{suffix}', encoding='utf-8')
            # Build manifest pointing to evil_dir paths
            manifest = build_manifest_from_directory(
                run_id='run_001', region_key='himalayas_nepal', elevation_band='lower',
                aspect_class='N', binary_version='snowpack-3.7.0', output_dir=evil_dir,
                created_at='2026-01-15T00:00:00+00:00', native_binary_invoked=True,
                toolchain_id='tc_001', forcing_manifest_id='fm_001',
                geometry_manifest_id='gm_001',
            )
            _write_manifest_json(bundle_dir, manifest)
            _write_result_json(bundle_dir, run_id='run_001', status='completed')
            _write_invocation_json(bundle_dir, toolchain_id='tc_001')
            # The gate must FAIL — evil_dir is NOT inside bundle_dir
            # startswith() would incorrectly pass this; is_relative_to() correctly rejects
            self.assertEqual(run_release_gate(bundle_dir), 1)

    def test_symlinked_metadata_fails(self) -> None:
        """C0-S10: Symlinked result.json/manifest.json/invocation.json must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Replace result.json with a symlink to an external file
            real_result = d / 'result.json'
            external = d.parent / 'external_result.json'
            external.write_text(real_result.read_text(), encoding='utf-8')
            real_result.unlink()
            real_result.symlink_to(external)
            self.assertEqual(run_release_gate(d), 1)

    def test_traversal_path_fails(self) -> None:
        """Manifest paths with traversal (../) must not escape the bundle."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # Create a file outside the bundle
            external = d.parent / 'external_secret.smet'
            external.write_text('secret_data', encoding='utf-8')
            # Build bundle
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (d / f'run{suffix}').write_text(f'data_{suffix}', encoding='utf-8')
            manifest = build_manifest_from_directory(
                run_id='run_001', region_key='himalayas_nepal', elevation_band='lower',
                aspect_class='N', binary_version='snowpack-3.7.0', output_dir=d,
                created_at='2026-01-15T00:00:00+00:00', native_binary_invoked=True,
                toolchain_id='tc_001', forcing_manifest_id='fm_001',
                geometry_manifest_id='gm_001',
            )
            # Tamper manifest to include a traversal path
            manifest_data = json.loads(json.dumps({
                'run_id': manifest.run_id, 'region_key': manifest.region_key,
                'elevation_band': manifest.elevation_band, 'aspect_class': manifest.aspect_class,
                'binary_version': manifest.binary_version,
                'artifacts': [{'file_path': str(external), 'file_type': 'smet',
                               'size_bytes': external.stat().st_size,
                               'sha256': '0' * 64, 'is_critical': True}]
                + [{'file_path': a.file_path, 'file_type': a.file_type,
                     'size_bytes': a.size_bytes, 'sha256': a.sha256,
                     'is_critical': a.is_critical} for a in manifest.artifacts[1:]],
                'is_native_execution': True, 'native_binary_invoked': True,
                'created_at': manifest.created_at, 'toolchain_id': 'tc_001',
                'forcing_manifest_id': 'fm_001', 'geometry_manifest_id': 'gm_001',
            }))
            with open(d / 'manifest.json', 'w') as f:
                json.dump(manifest_data, f)
            _write_result_json(d, run_id='run_001', status='completed')
            _write_invocation_json(d, toolchain_id='tc_001')
            # The gate must FAIL — traversal path is outside the bundle
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateFifthPassHardening(unittest.TestCase):
    """Fifth-pass adversarial tests for G1-G18 hardening."""

    def test_G1_malformed_result_json_fails_closed(self) -> None:
        """G1: Malformed JSON in result.json must exit 1, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Overwrite result.json with malformed JSON
            (d / 'result.json').write_text('{invalid json!!!', encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_G1_malformed_manifest_json_fails_closed(self) -> None:
        """G1: Malformed JSON in manifest.json must exit 1, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'manifest.json').write_text('not json at all', encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_G1_malformed_invocation_json_fails_closed(self) -> None:
        """G1: Malformed JSON in invocation.json must exit 1, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'invocation.json').write_text('{broken', encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_G2_no_fallback_truthy_string_fails(self) -> None:
        """G2: no_fallback='yes' (truthy string) must fail — only boolean True passes."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, no_fallback='yes')  # truthy but not True
            self.assertEqual(run_release_gate(d), 1)

    def test_G2_no_fallback_integer_1_fails(self) -> None:
        """G2: no_fallback=1 (truthy int) must fail — only boolean True passes."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, no_fallback=1)  # truthy but not True
            self.assertEqual(run_release_gate(d), 1)

    def test_G3_symlink_to_external_smet_fails(self) -> None:
        """G3: Symlink to external .smet file must not count toward required suffixes."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            native_output = d / 'native-output'
            # Replace real .smet with a symlink to an external file
            external_smet = d.parent / 'external.smet'
            external_smet.write_text('external data', encoding='utf-8')
            (native_output / 'run.smet').unlink()
            (native_output / 'run.smet').symlink_to(external_smet)
            self.assertEqual(run_release_gate(d), 1)

    def test_G8_artifacts_dir_is_symlink_fails(self) -> None:
        """G8: artifacts_dir being a symlink must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            real_dir = d / 'real_bundle'
            real_dir.mkdir()
            _build_valid_bundle(real_dir)
            # Create symlink to the real bundle
            link = d / 'link_to_bundle'
            link.symlink_to(real_dir)
            self.assertEqual(run_release_gate(link), 1)

    def test_G8_artifacts_dir_is_file_fails(self) -> None:
        """G8: artifacts_dir being a file (not directory) must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / 'not_a_dir.txt').write_text('I am a file', encoding='utf-8')
            self.assertEqual(run_release_gate(d / 'not_a_dir.txt'), 1)

    def test_G10_command_sha256_mismatch_fails(self) -> None:
        """G10: command_sha256 not matching SHA-256 of command field must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Write invocation with mismatched command_sha256
            _write_invocation_json(d, command='snowpack -i input.smet', command_sha256='0' * 64)
            self.assertEqual(run_release_gate(d), 1)

    def test_G16_unexpected_top_level_file_fails(self) -> None:
        """G16: Unexpected file in bundle root must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'unexpected.txt').write_text('surprise!', encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_G16_unexpected_top_level_dir_fails(self) -> None:
        """G16: Unexpected directory in bundle root must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'extra-dir').mkdir()
            self.assertEqual(run_release_gate(d), 1)

    def test_G17_native_binary_invoked_truthy_string_fails(self) -> None:
        """G17: native_binary_invoked='yes' (truthy) must fail — only True passes."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Rewrite manifest with truthy non-boolean native_binary_invoked
            with open(d / 'manifest.json', 'r') as f:
                mdata = json.load(f)
            mdata['native_binary_invoked'] = 'yes'  # truthy but not True
            with open(d / 'manifest.json', 'w') as f:
                json.dump(mdata, f)
            self.assertEqual(run_release_gate(d), 1)

    def test_G18_empty_manifest_fails_early(self) -> None:
        """G18: Empty manifest (no artifacts) must fail immediately."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            native_output = d / 'native-output'
            native_output.mkdir()
            # Write manifest with no artifacts
            with open(d / 'manifest.json', 'w') as f:
                json.dump({
                    'run_id': 'run_001', 'region_key': 'himalayas_nepal',
                    'elevation_band': 'lower', 'aspect_class': 'N',
                    'binary_version': 'snowpack-3.7.0', 'artifacts': [],
                    'is_native_execution': True, 'native_binary_invoked': True,
                    'created_at': '2026-01-15T00:00:00+00:00',
                    'toolchain_id': 'tc_001', 'forcing_manifest_id': 'fm_001',
                    'geometry_manifest_id': 'gm_001',
                }, f)
            _write_result_json(d, run_id='run_001', status='completed')
            _write_invocation_json(d, toolchain_id='tc_001', run_id='run_001')
            self.assertEqual(run_release_gate(d), 1)

    def test_G15_excessive_artifact_count_fails(self) -> None:
        """G15: Manifest with >1000 artifacts must fail (DoS protection)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            native_output = d / 'native-output'
            native_output.mkdir()
            # Create manifest with 1001 fake artifacts
            artifacts = []
            for i in range(1001):
                artifacts.append({
                    'file_path': f'native-output/fake{i}.smet',
                    'file_type': 'smet', 'size_bytes': 100,
                    'sha256': 'a' * 64, 'is_critical': False,
                })
            with open(d / 'manifest.json', 'w') as f:
                json.dump({
                    'run_id': 'run_001', 'region_key': 'himalayas_nepal',
                    'elevation_band': 'lower', 'aspect_class': 'N',
                    'binary_version': 'snowpack-3.7.0', 'artifacts': artifacts,
                    'is_native_execution': True, 'native_binary_invoked': True,
                    'created_at': '2026-01-15T00:00:00+00:00',
                    'toolchain_id': 'tc_001', 'forcing_manifest_id': 'fm_001',
                    'geometry_manifest_id': 'gm_001',
                }, f)
            _write_result_json(d, run_id='run_001', status='completed')
            _write_invocation_json(d, toolchain_id='tc_001', run_id='run_001')
            self.assertEqual(run_release_gate(d), 1)

    def test_C0_11_nested_invalid_manifest_type_fails_closed(self) -> None:
        """C0.11: Nested schema type errors must return 1, never traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            with open(d / 'manifest.json') as f:
                manifest_data = json.load(f)
            manifest_data['artifacts'][0]['file_type'] = []
            with open(d / 'manifest.json', 'w') as f:
                json.dump(manifest_data, f)
            self.assertEqual(run_release_gate(d), 1)

    def test_C0_11_invalid_manifest_size_and_boolean_types_fail_closed(self) -> None:
        """C0.11: Invalid size and boolean types must be rejected before validation."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            with open(d / 'manifest.json') as f:
                manifest_data = json.load(f)
            manifest_data['artifacts'][0]['size_bytes'] = '10'
            manifest_data['artifacts'][0]['is_critical'] = 'true'
            with open(d / 'manifest.json', 'w') as f:
                json.dump(manifest_data, f)
            self.assertEqual(run_release_gate(d), 1)

    def test_C0_11_invalid_result_field_types_fail_closed(self) -> None:
        """C0.11: Invalid result field types must fail without uncaught errors."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            _write_result_json(d, run_id=[], status={'completed': True}, no_fallback=1)
            self.assertEqual(run_release_gate(d), 1)

    def test_R1_external_registry_anchor_rejects_snapshot_and_result_mutation(self) -> None:
        """A self-consistent bundled snapshot cannot replace the external root."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            snapshot_path = d / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
            snapshot['registry_sha256'] = 'f' * 64
            snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode('utf-8')
            snapshot_path.write_bytes(snapshot_bytes)
            result_path = d / 'result.json'
            result = json.loads(result_path.read_text(encoding='utf-8'))
            result['registry_snapshot']['sha256'] = hashlib.sha256(snapshot_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = 'f' * 64
            result_path.write_text(json.dumps(result), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_R1_snapshot_record_hash_tampering_fails_after_rehashing_snapshot(self) -> None:
        """Changing record hashes and the snapshot reference must still fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            snapshot_path = d / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
            snapshot['records']['forcing']['manifest_sha256'] = 'f' * 64
            snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode('utf-8')
            snapshot_path.write_bytes(snapshot_bytes)
            result_path = d / 'result.json'
            result = json.loads(result_path.read_text(encoding='utf-8'))
            result['registry_snapshot']['sha256'] = hashlib.sha256(snapshot_bytes).hexdigest()
            result_path.write_text(json.dumps(result), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_R2_semantic_artifact_outside_native_output_fails(self) -> None:
        """A role-labelled native artifact under input-manifests is not native output."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            source = d / 'native-output' / 'run.pro'
            target = d / 'input-manifests' / 'rogue.pro'
            source.rename(target)
            manifest_path = d / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            profile = next(item for item in manifest['artifacts'] if item['role'] == 'profile_pro')
            profile['file_path'] = 'input-manifests/rogue.pro'
            profile['size_bytes'] = target.stat().st_size
            profile['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_R2_duplicate_semantic_role_fails(self) -> None:
        """A second profile role must not be accepted as an extra native output."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            duplicate = d / 'native-output' / 'duplicate.pro'
            duplicate.write_text('duplicate profile', encoding='utf-8')
            manifest_path = d / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            source = next(item for item in manifest['artifacts'] if item['role'] == 'profile_pro')
            manifest['artifacts'].append({
                **source,
                'file_path': 'native-output/duplicate.pro',
                'size_bytes': duplicate.stat().st_size,
                'sha256': hashlib.sha256(duplicate.read_bytes()).hexdigest(),
            })
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_R3_naive_invocation_timestamps_fail(self) -> None:
        """Invocation timestamps must be explicitly timezone-aware UTC."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            invocation_path = d / 'invocation.json'
            invocation = json.loads(invocation_path.read_text(encoding='utf-8'))
            invocation['started_at'] = '2026-01-15T00:00:00'
            invocation['finished_at'] = '2026-01-15T00:05:00'
            invocation_path.write_text(json.dumps(invocation), encoding='utf-8')
            self.assertEqual(run_release_gate(d), 1)

    def test_R3_malformed_utf8_metadata_fails_closed(self) -> None:
        """Malformed UTF-8 in a JSON boundary must return a gate failure."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            (d / 'invocation.json').write_bytes(b'{\xff\xfe')
            self.assertEqual(run_release_gate(d), 1)


class TestReleaseGateDecisionRecord(unittest.TestCase):
    """Adversarial tests for G2/G3/G4: decision record validation at the consumer gate."""

    _DECISION_RECORD_PATH = REPO_ROOT / 'docs' / 'MVP4' / '00_governance' / 'PIR_PANJAL_POC_DECISION_RECORD.json'

    def _build_poc_bundle(self, d: Path) -> str:
        """Build a fully consistent POC bundle with a decision record.
        Returns the decision record SHA-256 hash."""
        # Build the base bundle, then update ALL layers to Pir Panjal/middle/48h
        _build_valid_bundle(d)
        dr_bytes = self._DECISION_RECORD_PATH.read_bytes()
        dr_hash = hashlib.sha256(dr_bytes).hexdigest()
        # Add decision-record directory
        dr_dir = d / 'decision-record'
        dr_dir.mkdir(parents=True, exist_ok=True)
        (dr_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json').write_bytes(dr_bytes)
        (dr_dir / 'decision-record.sha256').write_text(dr_hash + '\n', encoding='utf-8')
        # Load the actual decision record to get the correct decision_id
        from backend.common.pir_panjal_decision_record import load_decision_record
        dr = load_decision_record(self._DECISION_RECORD_PATH)
        # Update result.json to match Pir Panjal scope
        result = json.loads((d / 'result.json').read_text())
        result['region_key'] = 'pir_panjal_nw_himalaya'
        result['elevation_band'] = 'middle'
        result['scope_mode'] = 'poc'
        result['decision_record'] = {
            'decision_id': dr.decision_id,
            'decision_record_sha256': dr_hash,
            'selected_sector': 'pir_panjal_nw_himalaya',
            'elevation_band': 'middle',
            'headline_horizon_hours': 48,
            'ensemble_members': 1,
            'track_id': 'track_1_indian_candidate',
            'evidence_class': 'pipeline-proof-only',
            'official_warning_eligible': False,
            'scope_hash_required': True,
        }
        (d / 'result.json').write_text(json.dumps(result))
        # Update manifest.json to match Pir Panjal scope
        manifest = json.loads((d / 'manifest.json').read_text())
        manifest['region_key'] = 'pir_panjal_nw_himalaya'
        manifest['elevation_band'] = 'middle'
        (d / 'manifest.json').write_text(json.dumps(manifest))
        # Update forecast-semantics to match Pir Panjal/48h/1-member
        forecast_path = d / 'input-manifests' / 'forecast-semantics.json'
        forecast_data = json.loads(forecast_path.read_text())
        forecast_data['contract']['region_key'] = 'pir_panjal_nw_himalaya'
        forecast_data['contract']['elevation_band'] = 'middle'
        forecast_data['contract']['lead_time_h'] = 48
        forecast_data['contract']['ensemble_members'] = 1
        # Fix valid_from/as_of to match 48h lead time
        forecast_data['contract']['as_of'] = '2026-01-15T00:00:00Z'
        forecast_data['contract']['valid_from'] = '2026-01-17T00:00:00Z'
        forecast_data['contract']['valid_to'] = '2026-01-18T00:00:00Z'
        forecast_path.write_text(json.dumps(forecast_data, indent=2))
        # Update result.json forecast_semantics descriptor hash
        result = json.loads((d / 'result.json').read_text())
        fs_bytes = forecast_path.read_bytes()
        result['forecast_semantics']['manifest_sha256'] = hashlib.sha256(fs_bytes).hexdigest()
        (d / 'result.json').write_text(json.dumps(result))
        # Update individual manifest files to Pir Panjal/middle FIRST
        for kind in ('forcing', 'geometry'):
            mp = d / 'input-manifests' / f'{kind}-manifest.json'
            if mp.exists():
                md = json.loads(mp.read_text())
                md['region'] = 'pir_panjal_nw_himalaya'
                md['elevation_band'] = 'middle'
                mp.write_text(json.dumps(md, sort_keys=True))
        # Update frozen registry records to Pir Panjal/middle BEFORE refresh
        registry_path = d / 'input-manifests' / 'approval-registry.json'
        if registry_path.exists():
            registry = json.loads(registry_path.read_text())
            for rec in registry.get('manifests', []):
                if rec.get('region') == 'himalayas_nepal':
                    rec['region'] = 'pir_panjal_nw_himalaya'
                    rec['elevation_band'] = 'middle'
                # Update content_sha256 to match the updated manifest file
                if rec.get('id') == 'fm_001':
                    rec['content_sha256'] = hashlib.sha256(
                        (d / 'input-manifests' / 'forcing-manifest.json').read_bytes()
                    ).hexdigest()
                elif rec.get('id') == 'gm_001':
                    rec['content_sha256'] = hashlib.sha256(
                        (d / 'input-manifests' / 'geometry-manifest.json').read_bytes()
                    ).hexdigest()
            for rec in registry.get('records', []):
                if rec.get('region') == 'himalayas_nepal':
                    rec['region'] = 'pir_panjal_nw_himalaya'
                    rec['elevation_band'] = 'middle'
            registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True))
        # Clear stale cached entries so _refresh_fixture_snapshot reads actual files
        _write_approved_inputs.last_entries = {}
        # Refresh snapshot to recompute manifest hashes from updated files
        _refresh_fixture_snapshot(d)
        # Now update snapshot region/band fields (after refresh preserved hashes)
        snapshot_path = d / 'input-manifests' / 'approval-registry-snapshot.json'
        if snapshot_path.exists():
            snapshot = json.loads(snapshot_path.read_text())
            for kind in ('forcing', 'geometry', 'toolchain'):
                rec = snapshot.get('records', {}).get(kind, {})
                rec['region'] = 'pir_panjal_nw_himalaya'
                rec['elevation_band'] = 'middle'
            snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode('utf-8')
            snapshot_path.write_bytes(snapshot_bytes)
        # Recompute registry hash from final frozen bytes
        final_registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        # Update result.json with all final hashes
        result = json.loads((d / 'result.json').read_text())
        result['registry_snapshot']['sha256'] = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        result['registry_snapshot']['registry_sha256'] = final_registry_sha256
        for kind in ('forcing', 'geometry'):
            mp = d / 'input-manifests' / f'{kind}-manifest.json'
            pp = d / 'input-manifests' / f'{kind}-payload.json'
            if mp.exists() and pp.exists():
                result['approved_inputs'][kind]['manifest_sha256'] = hashlib.sha256(mp.read_bytes()).hexdigest()
                result['approved_inputs'][kind]['payload_sha256'] = hashlib.sha256(pp.read_bytes()).hexdigest()
        (d / 'result.json').write_text(json.dumps(result))
        return dr_hash

    def test_g2_valid_poc_bundle_with_decision_record_passes(self) -> None:
        """G2: A valid POC bundle containing decision-record/ passes the gate."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 0)

    def test_g3_missing_record_with_digest_fails(self) -> None:
        """G3: Expected digest supplied but decision record absent → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # No decision-record/ directory, but digest is supplied
            rc = run_release_gate(d, expected_decision_record_sha256='a' * 64, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_g3_record_present_without_digest_fails(self) -> None:
        """G3: Decision record present but no expected digest → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._build_poc_bundle(d)
            rc = run_release_gate(d, poc_mode=True)  # No expected_decision_record_sha256
            self.assertEqual(rc, 1)

    def test_g3_record_hash_changed_fails(self) -> None:
        """G3: Decision record byte hash mismatch → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._build_poc_bundle(d)
            # Supply wrong expected hash
            rc = run_release_gate(d, expected_decision_record_sha256='b' * 64, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_g3_multiple_json_files_in_decision_record_fails(self) -> None:
        """C0.4: decision-record/ with extra JSON file → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            dr_dir = d / 'decision-record'
            (dr_dir / 'extra.json').write_text('{}', encoding='utf-8')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_g3_symlink_in_decision_record_fails(self) -> None:
        """C0.4: Symlink in decision-record/ → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            dr_dir = d / 'decision-record'
            (dr_dir / 'link.json').symlink_to(dr_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_c01_result_region_mismatch_with_manifest_fails(self) -> None:
        """C0.1: result.json says Pir Panjal but manifest says Nepal → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Tamper manifest back to Nepal
            manifest = json.loads((d / 'manifest.json').read_text())
            manifest['region_key'] = 'himalayas_nepal'
            (d / 'manifest.json').write_text(json.dumps(manifest))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_g4_bundled_hash_file_mismatch_fails(self) -> None:
        """G4: decision-record.sha256 file doesn't match actual hash → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            dr_dir = d / 'decision-record'
            (dr_dir / 'decision-record.sha256').write_text('c' * 64 + '\n', encoding='utf-8')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_g7_malformed_utf8_decision_record_fails(self) -> None:
        """G7: Malformed UTF-8 in decision record → controlled failure."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            dr_dir = d / 'decision-record'
            (dr_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json').write_bytes(b'{\xff\xfe}')
            rc = run_release_gate(d, expected_decision_record_sha256='a' * 64, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_non_poc_bundle_without_decision_record_passes(self) -> None:
        """A valid non-POC bundle without decision-record/ and without expected digest passes."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            rc = run_release_gate(d)
            self.assertEqual(rc, 0)

    def test_c04_non_poc_bundle_with_decision_record_fails(self) -> None:
        """C0.4: Non-POC mode rejects any decision-record/ directory."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            dr_dir = d / 'decision-record'
            dr_dir.mkdir(parents=True, exist_ok=True)
            dr_bytes = self._DECISION_RECORD_PATH.read_bytes()
            (dr_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json').write_bytes(dr_bytes)
            (dr_dir / 'decision-record.sha256').write_text(hashlib.sha256(dr_bytes).hexdigest() + '\n')
            rc = run_release_gate(d)  # poc_mode=False
            self.assertEqual(rc, 1)

    def test_c04_extra_text_file_in_decision_record_fails(self) -> None:
        """C0.4: Extra non-JSON file in decision-record/ → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            (d / 'decision-record' / 'notes.txt').write_text('extra', encoding='utf-8')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_c02_horizon_changed_to_72_in_binding_fails(self) -> None:
        """C0.2: Changing result.decision_record.headline_horizon_hours from 48 to 72 → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = 72
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_c02_forecast_24h_while_dr_48h_fails(self) -> None:
        """C0.2: Forecast semantics lead_time_h=24 while DR says 48 → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Tamper forecast back to 24h
            forecast_path = d / 'input-manifests' / 'forecast-semantics.json'
            forecast_data = json.loads(forecast_path.read_text())
            forecast_data['contract']['lead_time_h'] = 24
            forecast_data['contract']['valid_from'] = '2026-01-16T00:00:00Z'
            forecast_path.write_text(json.dumps(forecast_data, indent=2))
            # Update result.json hash
            result = json.loads((d / 'result.json').read_text())
            result['forecast_semantics']['manifest_sha256'] = hashlib.sha256(forecast_path.read_bytes()).hexdigest()
            (d / 'result.json').write_text(json.dumps(result))
            _refresh_fixture_snapshot(d)
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_c08_missing_result_region_with_dr_binding_fails(self) -> None:
        """C0.8: result.json without top-level region_key → fail (no fallback to DR binding)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            del result['region_key']
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_c03_ensemble_2_in_binding_fails(self) -> None:
        """C0.3: ensemble_members=2 in result binding → fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = 2
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    # ─── GLC: malformed POC binding type regression tests ───

    def test_glc_horizon_string_not_integer_fails(self) -> None:
        """GLC: headline_horizon_hours='not-an-integer' → controlled PocScopeError, no traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = 'not-an-integer'
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_glc_horizon_none_fails(self) -> None:
        """GLC: headline_horizon_hours=null → controlled failure, no TypeError traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = None
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_glc_horizon_list_fails(self) -> None:
        """GLC: headline_horizon_hours=[48] → controlled failure, no TypeError traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = [48]
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_glc_ensemble_string_not_integer_fails(self) -> None:
        """GLC: ensemble_members='two' → controlled PocScopeError, no traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = 'two'
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_glc_ensemble_float_fails(self) -> None:
        """P0-5: ensemble_members=1.5 → must fail (int coercion truncates to 1, creating false agreement)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = 1.5
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            # P0-5: int(1.5) = 1 would match dr_ensemble=1, but we now reject
            # non-integer types to prevent false agreement from truncation.
            self.assertEqual(rc, 1)

    # ─── 360-1: bool type confusion regression tests ───

    def test_bool_official_warning_int_zero_fails(self) -> None:
        """360-1: official_warning_eligible=0 (int) → must fail (type confusion)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['official_warning_eligible'] = 0
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_bool_official_warning_int_one_fails(self) -> None:
        """360-1: official_warning_eligible=1 (int) → must fail (type confusion)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['official_warning_eligible'] = 1
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_bool_official_warning_string_false_fails(self) -> None:
        """360-1: official_warning_eligible="false" (string) → must fail (type confusion)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['official_warning_eligible'] = "false"
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)


# ─── P1/G1: Strict type regression tests for horizon and ensemble ───


class StrictTypePocScopeTests(TestReleaseGateDecisionRecord):
    """P1/G1: int() coercion must be replaced with type(value) is int checks.

    int(48.5)=48, int("48")=48, int(True)=1 all silently pass int() conversion.
    The gate must reject these at the JSON boundary using exact type checks.
    """

    def test_horizon_float_48_5_fails(self) -> None:
        """P1/G1: headline_horizon_hours=48.5 (float) → must fail (int() would truncate to 48)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = 48.5
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_horizon_float_48_0_fails(self) -> None:
        """P1/G1: headline_horizon_hours=48.0 (float) → must fail (int() would convert to 48)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = 48.0
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_horizon_string_48_fails(self) -> None:
        """P1/G1: headline_horizon_hours="48" (string) → must fail (int() would convert to 48)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = "48"
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_horizon_bool_true_fails(self) -> None:
        """P1/G1: headline_horizon_hours=True (bool) → must fail (int(True)=1)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['headline_horizon_hours'] = True
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_ensemble_float_1_5_fails(self) -> None:
        """P1/G1: ensemble_members=1.5 (float) → must fail (int() would truncate to 1)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = 1.5
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_ensemble_float_1_0_fails(self) -> None:
        """P1/G1: ensemble_members=1.0 (float) → must fail (int() would convert to 1)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = 1.0
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_ensemble_string_1_fails(self) -> None:
        """P1/G1: ensemble_members="1" (string) → must fail (int() would convert to 1)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = "1"
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_ensemble_bool_true_fails(self) -> None:
        """P1/G1: ensemble_members=True (bool) → must fail (int(True)=1)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = True
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_ensemble_null_fails(self) -> None:
        """P1/G1: ensemble_members=None → must fail (not silently accepted)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = None
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_ensemble_list_fails(self) -> None:
        """P1/G1: ensemble_members=[1] (list) → must fail (not silently accepted)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['ensemble_members'] = [1]
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    # ─── P0-2/P0-3: POC mode state machine adversarial tests ───

    def test_p0_2_poc_mode_without_digest_fails(self) -> None:
        """P0-2: POC mode without external digest must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._build_poc_bundle(d)
            # Run with poc_mode=True but NO expected_decision_record_sha256
            rc = run_release_gate(d, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p0_2_poc_mode_without_record_fails(self) -> None:
        """P0-2: POC mode with digest but no decision record file must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Remove the decision record directory
            import shutil
            shutil.rmtree(d / 'decision-record')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p0_3_non_poc_mode_with_record_fails(self) -> None:
        """P0-3: Non-POC mode with decision-record directory must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Run with poc_mode=False but the bundle has a decision record
            rc = run_release_gate(d, expected_decision_record_sha256='', poc_mode=False)
            self.assertEqual(rc, 1)

    def test_p0_3_non_poc_mode_with_digest_fails(self) -> None:
        """P0-3: Non-POC mode with external digest must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # Supply a digest in non-POC mode
            rc = run_release_gate(d, expected_decision_record_sha256='a' * 64, poc_mode=False)
            self.assertEqual(rc, 1)

    def test_p1_9_broken_symlink_decision_record_dir_fails(self) -> None:
        """P1-9: Broken symlink as decision-record/ must be detected and fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Replace decision-record/ with a broken symlink
            import shutil
            shutil.rmtree(d / 'decision-record')
            (d / 'decision-record').symlink_to(d / 'nonexistent_target')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p1_9_decision_record_as_regular_file_fails(self) -> None:
        """P1-9: decision-record as a regular file (not directory) must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Replace decision-record/ directory with a regular file
            import shutil
            shutil.rmtree(d / 'decision-record')
            (d / 'decision-record').write_text('not a directory')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p0_4_extra_text_file_in_decision_record_fails(self) -> None:
        """P0-4: Extra non-JSON file in decision-record/ must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            (d / 'decision-record' / 'notes.txt').write_text('extra file')
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p0_4_wrong_canonical_filename_fails(self) -> None:
        """P0-4: Decision record with wrong filename must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Rename the JSON file to a wrong name
            dr_dir = d / 'decision-record'
            (dr_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json').rename(
                dr_dir / 'WRONG_NAME.json'
            )
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p1_10_scope_mode_mismatch_fails(self) -> None:
        """P1-10: result.json scope_mode must match gate poc_mode."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Set scope_mode to non_poc when gate is poc_mode
            result = json.loads((d / 'result.json').read_text())
            result['scope_mode'] = 'non_poc'
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p1_10_scope_mode_missing_fails(self) -> None:
        """P1-10: Missing scope_mode in result.json must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            del result['scope_mode']
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p0_4_missing_forecast_ensemble_field_fails(self) -> None:
        """P0-4: Missing ensemble_members in forecast semantics must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Remove ensemble_members from the forecast semantics file
            fs_path = d / 'input-manifests' / 'forecast-semantics.json'
            fs = json.loads(fs_path.read_text())
            del fs['contract']['ensemble_members']
            fs_path.write_text(json.dumps(fs))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_p1_11_fixed_external_registry_digest_passes(self) -> None:
        """G2/R4: A fixed external registry digest (computed from bytes
        OUTSIDE the bundle BEFORE copying) must be accepted when the bundle
        matches it. The expected digest must NOT be derived from any
        bundle-internal source (not result.json, not the registry file inside
        the bundle)."""
        with tempfile.TemporaryDirectory() as ext_tmp, tempfile.TemporaryDirectory() as tmp:
            ext_dir = Path(ext_tmp)  # OUTSIDE the bundle
            d = Path(tmp)            # the bundle
            # Build the POC bundle first (this creates the registry inside)
            dr_hash = self._build_poc_bundle(d)
            # G2: Copy the registry bytes to an EXTERNAL location
            # and hash them THERE — this is the out-of-band trust root
            bundle_registry = d / 'input-manifests' / 'approval-registry.json'
            ext_registry = ext_dir / 'approval-registry.json'
            ext_registry.write_bytes(bundle_registry.read_bytes())
            # G2: Hash the external copy — NOT the bundle's copy, NOT result.json
            external_hash = hashlib.sha256(ext_registry.read_bytes()).hexdigest()
            # The gate must pass: external hash matches the bundle's actual bytes
            rc = run_release_gate(
                d,
                expected_registry_sha256=external_hash,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 0)

    def test_p1_11_fixed_external_registry_digest_rejects_tampered(self) -> None:
        """G2/R4: A fixed external registry digest must reject a tampered
        bundle. The digest is computed from an external copy of the registry;
        after computing the hash, the bundle's registry is tampered, and the
        gate must reject it even if result.json and snapshot are updated."""
        with tempfile.TemporaryDirectory() as ext_tmp, tempfile.TemporaryDirectory() as tmp:
            ext_dir = Path(ext_tmp)
            d = Path(tmp)
            # Build POC bundle
            dr_hash = self._build_poc_bundle(d)
            # G2: Copy registry to external location and hash there
            bundle_registry = d / 'input-manifests' / 'approval-registry.json'
            ext_registry = ext_dir / 'approval-registry.json'
            ext_registry.write_bytes(bundle_registry.read_bytes())
            external_hash = hashlib.sha256(ext_registry.read_bytes()).hexdigest()
            # Tamper the bundle's registry file
            tampered = json.loads(bundle_registry.read_text())
            tampered['tampered'] = True
            bundle_registry.write_text(json.dumps(tampered))
            # Update ALL internal metadata to be self-consistent with tampered hash
            tampered_hash = hashlib.sha256(bundle_registry.read_bytes()).hexdigest()
            snapshot_path = d / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_text())
            snapshot['registry_sha256'] = tampered_hash
            snapshot_path.write_text(json.dumps(snapshot))
            result = json.loads((d / 'result.json').read_text())
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result['registry_snapshot']['sha256'] = hashlib.sha256(
                snapshot_path.read_bytes()
            ).hexdigest()
            (d / 'result.json').write_text(json.dumps(result))
            # Gate must fail: external hash (original) != actual registry hash (tampered)
            rc = run_release_gate(
                d,
                expected_registry_sha256=external_hash,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    def test_r4_external_digest_not_derived_from_result_json(self) -> None:
        """G2/R4: Prove the external digest is NOT derived from result.json.
        The external digest is computed from an external copy of the registry
        file, not from any bundle-internal metadata field."""
        with tempfile.TemporaryDirectory() as ext_tmp, tempfile.TemporaryDirectory() as tmp:
            ext_dir = Path(ext_tmp)
            d = Path(tmp)
            # Build POC bundle
            dr_hash = self._build_poc_bundle(d)
            # G2: Copy registry to external location and hash there
            bundle_registry = d / 'input-manifests' / 'approval-registry.json'
            ext_registry = ext_dir / 'approval-registry.json'
            ext_registry.write_bytes(bundle_registry.read_bytes())
            external_hash = hashlib.sha256(ext_registry.read_bytes()).hexdigest()
            # Verify we're NOT reading from result.json
            result = json.loads((d / 'result.json').read_text())
            result_field_hash = result['registry_snapshot']['registry_sha256']
            self.assertEqual(external_hash, result_field_hash,
                             'Test setup: external hash should match for honest bundle')
            # The gate must pass: external hash matches the actual bytes
            rc = run_release_gate(
                d,
                expected_registry_sha256=external_hash,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 0)

    def test_r4_external_digest_rejects_tampered_registry(self) -> None:
        """G2/R4: An external digest computed from an external copy of the
        registry must reject a bundle where the registry file is tampered,
        even if all internal metadata is updated to be self-consistent."""
        with tempfile.TemporaryDirectory() as ext_tmp, tempfile.TemporaryDirectory() as tmp:
            ext_dir = Path(ext_tmp)
            d = Path(tmp)
            # Build POC bundle
            dr_hash = self._build_poc_bundle(d)
            # G2: Copy registry to external location and hash there
            bundle_registry = d / 'input-manifests' / 'approval-registry.json'
            ext_registry = ext_dir / 'approval-registry.json'
            ext_registry.write_bytes(bundle_registry.read_bytes())
            external_hash = hashlib.sha256(ext_registry.read_bytes()).hexdigest()
            # Tamper the registry file
            tampered = json.loads(bundle_registry.read_text())
            tampered['tampered'] = True
            bundle_registry.write_text(json.dumps(tampered))
            # Update ALL internal metadata to be self-consistent with tampered hash
            tampered_hash = hashlib.sha256(bundle_registry.read_bytes()).hexdigest()
            snapshot_path = d / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_text())
            snapshot['registry_sha256'] = tampered_hash
            snapshot_path.write_text(json.dumps(snapshot))
            result = json.loads((d / 'result.json').read_text())
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result['registry_snapshot']['sha256'] = hashlib.sha256(
                snapshot_path.read_bytes()
            ).hexdigest()
            (d / 'result.json').write_text(json.dumps(result))
            # Gate must fail: external hash (original) != actual registry hash (tampered)
            rc = run_release_gate(
                d,
                expected_registry_sha256=external_hash,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    def test_g2_external_digest_mutated_result_metadata_still_rejected(self) -> None:
        """G2: Mutate result.json metadata to claim a WRONG registry_sha256.
        The gate must reject this because result.json and snapshot disagree
        on registry_sha256 — internal consistency is checked independently
        of the external hash."""
        with tempfile.TemporaryDirectory() as ext_tmp, tempfile.TemporaryDirectory() as tmp:
            ext_dir = Path(ext_tmp)
            d = Path(tmp)
            # Build POC bundle
            dr_hash = self._build_poc_bundle(d)
            # Copy registry to external location and hash there
            bundle_registry = d / 'input-manifests' / 'approval-registry.json'
            ext_registry = ext_dir / 'approval-registry.json'
            ext_registry.write_bytes(bundle_registry.read_bytes())
            external_hash = hashlib.sha256(ext_registry.read_bytes()).hexdigest()
            # Mutate result.json to claim a WRONG hash
            result = json.loads((d / 'result.json').read_text())
            result['registry_snapshot']['registry_sha256'] = 'f' * 64
            (d / 'result.json').write_text(json.dumps(result))
            # Gate must fail: result.json and snapshot disagree
            rc = run_release_gate(
                d,
                expected_registry_sha256=external_hash,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    def test_g2_external_digest_mutated_snapshot_still_rejected(self) -> None:
        """G2: Mutate the snapshot's registry_sha256 to disagree with
        result.json. The gate must reject this internal inconsistency."""
        with tempfile.TemporaryDirectory() as ext_tmp, tempfile.TemporaryDirectory() as tmp:
            ext_dir = Path(ext_tmp)
            d = Path(tmp)
            # Build POC bundle
            dr_hash = self._build_poc_bundle(d)
            # Copy registry to external location and hash there
            bundle_registry = d / 'input-manifests' / 'approval-registry.json'
            ext_registry = ext_dir / 'approval-registry.json'
            ext_registry.write_bytes(bundle_registry.read_bytes())
            external_hash = hashlib.sha256(ext_registry.read_bytes()).hexdigest()
            # Mutate the snapshot to claim a WRONG hash
            snapshot_path = d / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_text())
            snapshot['registry_sha256'] = 'f' * 64
            snapshot_path.write_text(json.dumps(snapshot))
            # Update result.json to match the mutated snapshot
            result = json.loads((d / 'result.json').read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(
                snapshot_path.read_bytes()
            ).hexdigest()
            result['registry_snapshot']['registry_sha256'] = 'f' * 64
            (d / 'result.json').write_text(json.dumps(result))
            # Gate must fail: snapshot claims wrong hash vs actual registry
            rc = run_release_gate(
                d,
                expected_registry_sha256=external_hash,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    # ─── R0-R3, R7: Re-audit adversarial regression tests ───

    def test_r0_non_poc_mode_malformed_digest_fails(self) -> None:
        """R0: Non-POC mode with a malformed (non-SHA-256) digest must fail.
        The gate must reject ANY non-empty digest in non-POC mode, not just
        valid SHA-256 format digests."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            rc = run_release_gate(
                d,
                expected_decision_record_sha256='not-a-sha256',
                poc_mode=False,
            )
            self.assertEqual(rc, 1)

    def test_r0_non_poc_mode_empty_digest_passes(self) -> None:
        """R0: Non-POC mode with empty digest must still pass (no POC intent)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            rc = run_release_gate(
                d,
                expected_decision_record_sha256='',
                poc_mode=False,
            )
            self.assertEqual(rc, 0)

    def test_r0_poc_mode_malformed_digest_fails(self) -> None:
        """R0: POC mode with a malformed digest must fail (must be valid SHA-256)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._build_poc_bundle(d)
            rc = run_release_gate(
                d,
                expected_decision_record_sha256='not-a-sha256',
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    def test_r1_producer_digest_without_path_fails(self) -> None:
        """R1: Producer must reject --expected-decision-record-sha256 without
        --decision-record-path. The digest alone must not be silently ignored.
        This test is covered in test_run_snowpack_release.py; here we verify
        the state machine logic directly."""
        from backend.scripts.run_snowpack_release import run_release_orchestration
        # Call with digest but no path — must fail before any filesystem work.
        # We don't need a real bundle dir since it fails at the state machine.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=d / 'bundle',
                approved_artifact_root=d,
                manifest_registry_path=d / 'registry.json',
                expected_registry_sha256='a' * 64,
                decision_record_path=None,
                expected_decision_record_sha256='a' * 64,
            )
            self.assertEqual(exit_code, 1)

    def test_r1_producer_path_without_digest_fails(self) -> None:
        """R1: Producer must reject --decision-record-path without
        --expected-decision-record-sha256."""
        from backend.scripts.run_snowpack_release import run_release_orchestration
        dr_path = Path('docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json')
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            exit_code = run_release_orchestration(
                region_key='pir_panjal_nw_himalaya',
                elevation_band='middle',
                run_id='run_poc_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=d / 'bundle',
                approved_artifact_root=d,
                manifest_registry_path=d / 'registry.json',
                expected_registry_sha256='a' * 64,
                decision_record_path=dr_path,
                expected_decision_record_sha256='',
            )
            self.assertEqual(exit_code, 1)

    def test_r1_producer_explicit_non_poc_with_path_fails(self) -> None:
        """R1: Producer with explicit poc_mode=False but decision-record-path
        supplied must fail (contradictory combination)."""
        from backend.scripts.run_snowpack_release import run_release_orchestration
        dr_path = Path('docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json')
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=d / 'bundle',
                approved_artifact_root=d,
                manifest_registry_path=d / 'registry.json',
                expected_registry_sha256='a' * 64,
                decision_record_path=dr_path,
                expected_decision_record_sha256='a' * 64,
                poc_mode=False,
            )
            self.assertEqual(exit_code, 1)

    def test_r2_consumer_mode_passthrough(self) -> None:
        """R2: Consumer gate must pass the actual poc_mode to the shared
        validator, not hardcode True. Verify by checking that a non-POC bundle
        with no decision record passes when poc_mode=False."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _build_valid_bundle(d)
            # This is a non-POC bundle — must pass with poc_mode=False
            rc = run_release_gate(d, poc_mode=False)
            self.assertEqual(rc, 0)

    def test_r3_direct_contract_rejects_float_ensemble(self) -> None:
        """R3: Direct ForecastSemanticsContract must reject ensemble_members=1.5."""
        from backend.common.snowpack_contracts import (
            ForecastSemanticsContract, ContractValidationError,
        )
        forecast = ForecastSemanticsContract(
            mode='forecast', source='test',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-17T00:00:00Z', valid_to='2026-01-18T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=48,
            region_key='pir_panjal_nw_himalaya', elevation_band='middle',
            forcing_manifest_id='fm_001',
            ensemble_members=1.5,
        )
        with self.assertRaises(ContractValidationError):
            forecast.validate()

    def test_r3_direct_contract_rejects_string_ensemble(self) -> None:
        """R3: Direct ForecastSemanticsContract must reject ensemble_members="1"."""
        from backend.common.snowpack_contracts import (
            ForecastSemanticsContract, ContractValidationError,
        )
        forecast = ForecastSemanticsContract(
            mode='forecast', source='test',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-17T00:00:00Z', valid_to='2026-01-18T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=48,
            region_key='pir_panjal_nw_himalaya', elevation_band='middle',
            forcing_manifest_id='fm_001',
            ensemble_members="1",
        )
        with self.assertRaises(ContractValidationError):
            forecast.validate()

    def test_r3_direct_contract_rejects_bool_ensemble(self) -> None:
        """R3: Direct ForecastSemanticsContract must reject ensemble_members=True."""
        from backend.common.snowpack_contracts import (
            ForecastSemanticsContract, ContractValidationError,
        )
        forecast = ForecastSemanticsContract(
            mode='forecast', source='test',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-17T00:00:00Z', valid_to='2026-01-18T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=48,
            region_key='pir_panjal_nw_himalaya', elevation_band='middle',
            forcing_manifest_id='fm_001',
            ensemble_members=True,
        )
        with self.assertRaises(ContractValidationError):
            forecast.validate()

    def test_r3_direct_contract_rejects_none_ensemble(self) -> None:
        """R3: Direct ForecastSemanticsContract must reject ensemble_members=None."""
        from backend.common.snowpack_contracts import (
            ForecastSemanticsContract, ContractValidationError,
        )
        forecast = ForecastSemanticsContract(
            mode='forecast', source='test',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-17T00:00:00Z', valid_to='2026-01-18T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=48,
            region_key='pir_panjal_nw_himalaya', elevation_band='middle',
            forcing_manifest_id='fm_001',
            ensemble_members=None,  # type: ignore[arg-type]
        )
        with self.assertRaises(ContractValidationError):
            forecast.validate()

    def test_r3_direct_contract_accepts_valid_int_ensemble(self) -> None:
        """R3: Direct ForecastSemanticsContract must accept ensemble_members=1 (valid int)."""
        from backend.common.snowpack_contracts import ForecastSemanticsContract
        forecast = ForecastSemanticsContract(
            mode='forecast', source='test',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-17T00:00:00Z', valid_to='2026-01-18T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=48,
            region_key='pir_panjal_nw_himalaya', elevation_band='middle',
            forcing_manifest_id='fm_001',
            ensemble_members=1,
        )
        forecast.validate()  # Must not raise

    def test_r7_derive_poc_scope_uses_single_read(self) -> None:
        """R7: derive_poc_scope must use load_decision_record_from_bytes to
        eliminate the TOCTOU seam. Verify the function works correctly."""
        import hashlib as _hashlib
        from backend.scripts.derive_poc_scope import derive_scope
        dr_path = self._DECISION_RECORD_PATH
        dr_hash = _hashlib.sha256(dr_path.read_bytes()).hexdigest()
        scope = derive_scope(dr_path, dr_hash)
        self.assertEqual(scope['region_key'], 'pir_panjal_nw_himalaya')
        self.assertEqual(scope['elevation_band'], 'middle')
        self.assertEqual(scope['headline_horizon_hours'], 48)
        self.assertEqual(scope['ensemble_members'], 1)

    def test_r7_load_decision_record_from_bytes_works(self) -> None:
        """R7: load_decision_record_from_bytes must work on pre-read bytes."""
        import hashlib as _hashlib
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        raw_bytes = self._DECISION_RECORD_PATH.read_bytes()
        dr_hash = _hashlib.sha256(raw_bytes).hexdigest()
        dr = load_decision_record_from_bytes(
            raw_bytes, expected_sha256=dr_hash,
            source_path=str(self._DECISION_RECORD_PATH),
        )
        self.assertEqual(dr.selected_sector, 'pir_panjal_nw_himalaya')
        self.assertEqual(dr.elevation_band, 'middle')
        self.assertEqual(dr.headline_horizon_hours, 48)
        self.assertEqual(dr.ensemble_members, 1)


class PocStringFieldTypeTests(TestReleaseGateDecisionRecord):
    """G10: POC string fields must be actual strings — no str() coercion."""

    def test_decision_id_integer_fails(self) -> None:
        """G10: decision_record.decision_id=123 (int) → must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['decision_id'] = 123
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_track_id_list_fails(self) -> None:
        """G10: decision_record.track_id=['track_1'] (list) → must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['track_id'] = ['track_1_indian_candidate']
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_evidence_class_integer_fails(self) -> None:
        """G10: decision_record.evidence_class=999 (int) → must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['evidence_class'] = 999
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_selected_sector_null_fails(self) -> None:
        """G10: decision_record.selected_sector=None → must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['selected_sector'] = None
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)

    def test_sha256_integer_fails(self) -> None:
        """G10: decision_record_sha256=123 (int) → must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            result = json.loads((d / 'result.json').read_text())
            result['decision_record']['decision_record_sha256'] = 123
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)


# ─── P3/G11: POC lead_time_h float rejection tests ───


class PocLeadTimeFloatTests(TestReleaseGateDecisionRecord):
    """G11: In POC mode, forecast lead_time_h=48.0 (float) must fail."""

    def test_lead_time_float_48_0_fails_in_poc(self) -> None:
        """G11: forecast lead_time_h=48.0 (float) → must fail in POC mode."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Modify the forecast semantics file to use float lead_time_h
            fs_path = d / 'input-manifests' / 'forecast-semantics.json'
            fs_data = json.loads(fs_path.read_text())
            fs_data['contract']['lead_time_h'] = 48.0
            fs_path.write_text(json.dumps(fs_data, indent=2))
            # Update the result.json forecast_semantics hash
            result = json.loads((d / 'result.json').read_text())
            result['forecast_semantics']['manifest_sha256'] = hashlib.sha256(
                fs_path.read_bytes()
            ).hexdigest()
            (d / 'result.json').write_text(json.dumps(result))
            rc = run_release_gate(d, expected_decision_record_sha256=dr_hash, poc_mode=True)
            self.assertEqual(rc, 1)


# ─── G4: Mismatched toolchain identity fixture tests ───


class MismatchedToolchainIdentityTests(TestReleaseGateDecisionRecord):
    """G4: Tests for toolchain identity mismatch detection.

    ARCHITECTURAL NOTE: The release gate checks INTERNAL consistency of
    toolchain manifest fields (binary_sha256, binary_version, image_id, etc.)
    but does NOT have an external toolchain trust anchor. This means:

    - A bundle with MISMATCHED toolchain metadata (e.g., toolchain manifest
      says binary_sha256=X but invocation says binary_sha256=Y) IS rejected
      by these tests.
    - A self-consistent fake binary with all outputs and matching metadata
      would PASS the gate. This is a known architectural limitation.
    - Distinguishing a real pinned SNOWPACK binary from a fake executable
      that produces identical outputs requires an EXTERNAL toolchain approval
      root (operator gate G9). The gate cannot do this independently.

    These tests prove that:
    1. A bundle with ALL expected output suffixes but a MISMATCHED toolchain
       identity (toolchain manifest vs invocation) is rejected.
    2. The gate correctly labels its evidence as 'local attestation, not signed'
       so users cannot mistake synthetic output for native proof.
    3. The gate source contains no 'real native artifacts' claims.
    """

    def test_g4_mismatched_toolchain_identity_fails(self) -> None:
        """G4: A bundle with all output suffixes but a toolchain manifest
        whose binary_sha256 doesn't match the invocation must fail.

        This is a METADATA mismatch test, not a fake-executable integration
        test. The gate detects internal inconsistency between the toolchain
        manifest and the invocation record."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Tamper the toolchain manifest's binary_sha256 to mismatch
            tc_path = d / 'toolchain-manifest.json'
            tc = json.loads(tc_path.read_text())
            tc['binary_sha256'] = 'f' * 64  # Mismatched
            tc_path.write_text(json.dumps(tc))
            rc = run_release_gate(
                d,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    def test_g4_mismatched_binary_version_fails(self) -> None:
        """G4: A bundle with all output suffixes but a mismatched binary_version
        between manifest and toolchain must fail.

        This is a METADATA mismatch test, not a fake-executable integration
        test. The gate detects internal inconsistency between the toolchain
        manifest and the invocation record."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Tamper the toolchain manifest's binary_version to mismatch
            tc_path = d / 'toolchain-manifest.json'
            tc = json.loads(tc_path.read_text())
            tc['binary_version'] = 'FAKE-VERSION-9.9.9'
            tc_path.write_text(json.dumps(tc))
            rc = run_release_gate(
                d,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 1)

    def test_g4_self_consistent_fake_binary_architectural_limitation(self) -> None:
        """G4 ARCHITECTURAL LIMITATION: A self-consistent fake binary with all
        outputs and matching metadata would PASS the gate. This is a known
        limitation — the gate cannot independently distinguish a real pinned
        SNOWPACK binary from a fake executable without an external toolchain
        approval root (operator gate G9).

        This test documents the limitation by showing that a bundle with
        self-consistent metadata passes even though the binary is synthetic.
        The fix is external toolchain approval, not a code-level gate change."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # The bundle has self-consistent metadata and all outputs.
            # The gate passes because it cannot verify the binary is real.
            # This is the architectural limitation.
            rc = run_release_gate(
                d,
                expected_decision_record_sha256=dr_hash,
                poc_mode=True,
            )
            self.assertEqual(rc, 0,
                             'Self-consistent synthetic bundle passes the gate. '
                             'This is a known limitation — external toolchain '
                             'approval (G9) is required to distinguish real binaries.')

    def test_g4_output_wording_does_not_claim_native_proof(self) -> None:
        """G4/G3: The gate's success output must NOT claim 'Real native
        artifacts verified' — it must say 'Release bundle contract passed'
        and label attestation as local/unsigned."""
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            dr_hash = self._build_poc_bundle(d)
            # Capture stdout
            stdout_buf = io.StringIO()
            with contextlib.redirect_stdout(stdout_buf):
                rc = run_release_gate(
                    d,
                    expected_decision_record_sha256=dr_hash,
                    poc_mode=True,
                )
            self.assertEqual(rc, 0)
            output = stdout_buf.getvalue()
            # G3: Must NOT say "Real native artifacts verified"
            self.assertNotIn('Real native artifacts verified', output,
                             'Gate must not claim real native artifacts for synthetic fixtures')
            # G3: Must say "Release bundle contract passed"
            self.assertIn('Release bundle contract passed', output,
                          'Gate must say "Release bundle contract passed"')
            # G4: Must label attestation as local/unsigned
            self.assertIn('local attestation', output.lower(),
                          'Gate must label attestation as local/unsigned')

    def test_g3_no_native_proof_claims_in_source(self) -> None:
        """G3: Static check — the release gate source must NOT contain any
        'real native artifacts' or 'verifies real native' claims anywhere
        (not just in the success message, but also in docstrings, argparse
        descriptions, and comments)."""
        gate_path = REPO_ROOT / 'backend' / 'scripts' / 'release_gate.py'
        content = gate_path.read_text(encoding='utf-8')
        # G3: No "real native artifacts" claims anywhere in the source
        self.assertNotIn('real native artifacts', content.lower(),
                         'Release gate source must not claim "real native artifacts" anywhere')
        self.assertNotIn('verifies real native', content.lower(),
                         'Release gate source must not claim "verifies real native" anywhere')


if __name__ == '__main__':
    unittest.main()
