"""R1.1 adversarial probes: independent registry-root trust anchor.

These tests prove that the release gate rejects a bundle where:
  - the registry bytes are missing from the bundle;
  - the registry bytes are tampered while all internal references are updated;
  - only the registry bytes are tampered;
  - selected records in the snapshot disagree with the actual registry;
  - the registry is malformed JSON or malformed UTF-8;
  - the registry contains duplicate manifest IDs;
  - the registry record for a selected ID has the wrong region/elevation;
  - the registry record for a selected ID is not approved;
  - the registry record content_sha256 disagrees with the bundled manifest;
  - a valid bundle with a matching registry still passes.

The trust anchor is the externally supplied --expected-registry-sha256.
The gate must hash the actual bundled registry bytes and compare them
against that external digest. It must not trust the registry_sha256 claim
inside the snapshot or result.json.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.common.snowpack_artifact_manifest import (
    ArtifactEntry,
    ArtifactManifest,
    build_manifest_from_directory,
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
from backend.scripts.release_gate import run_release_gate


# ── Fixture registry builder ──────────────────────────────────────────────

def _build_fixture_registry(
    approved: dict[str, dict[str, str]],
    *,
    toolchain_manifest_sha256: str = 'f' * 64,
) -> bytes:
    """Build a deterministic fixture registry with records matching the bundle."""
    records = []
    for kind, entry in approved.items():
        record = {
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
        }
        records.append(record)
    records.append({
        'id': 'tc_001',
        'kind': 'toolchain',
        'content_sha256': toolchain_manifest_sha256,
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
    registry = {
        'schema_version': 'snowpack_manifest_registry_v1',
        'manifests': records,
    }
    return json.dumps(registry, sort_keys=True, indent=2).encode('utf-8')


def _write_approved_inputs(dir_path: Path) -> dict[str, dict[str, str]]:
    """Write synthetic-but-explicit input bytes for gate fixtures."""
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
    return approved


def _write_release_semantics_inputs(dir_path: Path, run_id: str = 'run_001') -> dict[str, dict[str, str]]:
    input_dir = dir_path / 'input-manifests'
    input_dir.mkdir(exist_ok=True)
    provenance = ProvenanceMetadata(
        source='test-approved-state', source_class='direct', licence='test-licence',
        timestamp='2026-01-15T00:00:00+00:00', units={'state': 'native'},
        hash='a' * 64, run_id=run_id,
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


def _build_valid_bundle(dir_path: Path, run_id: str = 'run_001') -> str:
    """Build a complete valid release bundle and return the registry SHA-256."""
    input_dir = dir_path / 'input-manifests'
    input_dir.mkdir(exist_ok=True)
    native_dir = dir_path / 'native-output'
    native_dir.mkdir(exist_ok=True)

    approved = _write_approved_inputs(dir_path)
    release_semantics = _write_release_semantics_inputs(dir_path, run_id)

    # Write toolchain manifest
    toolchain_manifest = {
        'schema_version': 'snowpack_toolchain_manifest_v1',
        'toolchain_id': 'tc_001',
        'meteoio_commit': 'a' * 40,
        'snowpack_commit': 'b' * 40,
        'binary_path': '/usr/local/bin/snowpack',
        'binary_sha256': 'a' * 64,
        'binary_version': 'snowpack-3.7.0',
        'compiler_version': 'gcc-13',
        'cmake_version': 'cmake-3.28',
        'image_id': 'sha256:' + 'c' * 64,
        'image_archive_sha256': 'd' * 64,
        'image_identity_source': 'local_id_and_archive',
    }
    toolchain_bytes = json.dumps(toolchain_manifest, indent=2, sort_keys=True).encode('utf-8')
    toolchain_hash = hashlib.sha256(toolchain_bytes).hexdigest()
    (dir_path / 'toolchain-manifest.json').write_bytes(toolchain_bytes)

    # Write native outputs
    for name, content in (
        ('run.smet', b'smet header\n'),
        ('processed-meteo.smet', b'processed meteo data\n'),
        ('run.pro', b'pro data\n'),
        ('run.sno', b'sno data\n'),
        ('run.haz', b'haz data\n'),
        ('run.log', b'log data\n'),
    ):
        (native_dir / name).write_bytes(content)

    # Build artifact manifest with correct API
    manifest = build_manifest_from_directory(
        run_id=run_id,
        region_key='himalayas_nepal',
        elevation_band='lower',
        aspect_class='N',
        binary_version='snowpack-3.7.0',
        output_dir=native_dir,
        created_at='2026-01-15T00:05:00+00:00',
        native_binary_invoked=True,
        toolchain_id='tc_001',
        forcing_manifest_id='fm_001',
        geometry_manifest_id='gm_001',
    )
    manifest_data = {
        'run_id': manifest.run_id,
        'region_key': manifest.region_key,
        'elevation_band': manifest.elevation_band,
        'aspect_class': manifest.aspect_class,
        'binary_version': manifest.binary_version,
        'artifacts': [
            {
                'file_path': f'native-output/{Path(a.file_path).name}',
                'file_type': a.file_type,
                'size_bytes': a.size_bytes,
                'sha256': a.sha256,
                'is_critical': a.is_critical,
                'role': a.role,
            }
            for a in manifest.artifacts
        ],
        'is_native_execution': True,
        'native_binary_invoked': True,
        'created_at': manifest.created_at,
        'toolchain_id': 'tc_001',
        'forcing_manifest_id': 'fm_001',
        'geometry_manifest_id': 'gm_001',
    }
    (dir_path / 'manifest.json').write_text(json.dumps(manifest_data, indent=2), encoding='utf-8')

    # Build and write the actual registry
    registry_bytes = _build_fixture_registry(approved, toolchain_manifest_sha256=toolchain_hash)
    registry_path = input_dir / 'approval-registry.json'
    registry_path.write_bytes(registry_bytes)
    registry_sha256 = hashlib.sha256(registry_bytes).hexdigest()

    # Build snapshot
    snapshot_records = {}
    for kind, record_id, manifest_sha256 in (
        ('forcing', 'fm_001', approved['forcing']['manifest_sha256']),
        ('geometry', 'gm_001', approved['geometry']['manifest_sha256']),
        ('toolchain', 'tc_001', toolchain_hash),
    ):
        snapshot_records[kind] = {
            'id': record_id,
            'kind': kind,
            'source': 'test-source',
            'licence': 'test-licence',
            'units': 'SI',
            'region': 'himalayas_nepal',
            'elevation_band': 'lower',
            'valid_from': '2024-01-01T00:00:00Z',
            'valid_to': '2030-01-01T00:00:00Z',
            'approval_state': 'approved',
            'source_registry_version': 'snowpack_manifest_registry_v1',
            'manifest_sha256': manifest_sha256,
        }
        if kind in ('forcing', 'geometry'):
            snapshot_records[kind]['payload_sha256'] = approved[kind]['payload_sha256']
            snapshot_records[kind]['bundle_manifest_path'] = f'input-manifests/{kind}-manifest.json'
            snapshot_records[kind]['bundle_payload_path'] = f'input-manifests/{kind}-payload.json'
        if kind == 'toolchain':
            snapshot_records[kind]['toolchain_manifest_sha256'] = toolchain_hash
    snapshot = {
        'schema_version': 'snowpack_approval_snapshot_v1',
        'source_registry_version': 'snowpack_manifest_registry_v1',
        'registry_sha256': registry_sha256,
        'registry_bundle_path': 'input-manifests/approval-registry.json',
        'records': snapshot_records,
    }
    snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode('utf-8')
    (input_dir / 'approval-registry-snapshot.json').write_bytes(snapshot_bytes)

    # Write result.json
    result = {
        'run_id': run_id,
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
            'sha256': hashlib.sha256(snapshot_bytes).hexdigest(),
            'registry_sha256': registry_sha256,
            'registry_bundle_path': 'input-manifests/approval-registry.json',
        },
        'no_fallback': True,
        **release_semantics,
    }
    (dir_path / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    # Write invocation.json
    cmd = 'snowpack -c config.ini'
    invocation = {
        'binary_path': '/usr/local/bin/snowpack',
        'binary_sha256': 'a' * 64,
        'binary_version': 'snowpack-3.7.0',
        'command': cmd,
        'command_sha256': hashlib.sha256(cmd.encode()).hexdigest(),
        'exit_code': 0,
        'version_exit_code': 0,
        'version_verified': True,
        'started_at': '2026-01-15T00:00:00+00:00',
        'finished_at': '2026-01-15T00:05:00+00:00',
        'toolchain_id': 'tc_001',
        'run_id': run_id,
        'toolchain_manifest_sha256': toolchain_hash,
        'toolchain_manifest_verified': True,
        'image_id': 'sha256:' + 'c' * 64,
        'image_archive_sha256': 'd' * 64,
        'image_repository_digest': '',
        'image_identity_source': 'local_id_and_archive',
    }
    (dir_path / 'invocation.json').write_text(json.dumps(invocation, indent=2), encoding='utf-8')

    return registry_sha256


def _gate(root: Path, registry_sha256: str, run_id: str = 'run_001') -> int:
    return run_release_gate(
        root,
        expected_run_id=run_id,
        expected_registry_sha256=registry_sha256,
    )


# ── Adversarial tests ─────────────────────────────────────────────────────

class TestR11RegistryRootTrustAnchor(unittest.TestCase):
    """R1.1: the gate must hash actual bundled registry bytes, not trust claims."""

    def test_valid_bundle_with_matching_registry_passes(self) -> None:
        """A valid bundle with a correctly hashed registry must pass."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            self.assertEqual(_gate(root, registry_sha256), 0)

    def test_missing_registry_bytes_fails(self) -> None:
        """If the registry file is absent from the bundle, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            (root / 'input-manifests' / 'approval-registry.json').unlink()
            self.assertEqual(_gate(root, registry_sha256), 1)

    def test_tampered_registry_bytes_fails(self) -> None:
        """If the registry bytes are modified but the snapshot claim is unchanged,
        the gate must detect the hash mismatch against the external anchor."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            tampered = json.loads(reg_path.read_bytes())
            tampered['manifests'][0]['source'] = 'attacker-source'
            reg_path.write_bytes(json.dumps(tampered, sort_keys=True, indent=2).encode())
            self.assertEqual(_gate(root, registry_sha256), 1)

    def test_tampered_registry_with_all_refs_updated_fails(self) -> None:
        """The critical R1.1 attack: attacker modifies the registry AND updates
        all internal references (snapshot, result.json) to be self-consistent.
        The gate must still fail because the registry hash no longer matches
        the externally supplied expected_registry_sha256."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_sha256 = _build_valid_bundle(root)
            # Attacker modifies the registry
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            tampered = json.loads(reg_path.read_bytes())
            tampered['manifests'][0]['source'] = 'attacker-source'
            tampered_bytes = json.dumps(tampered, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            # Attacker updates snapshot to claim the tampered hash
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            # Attacker updates result.json to match
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # Gate must reject: tampered hash != externally supplied original hash
            self.assertEqual(_gate(root, original_sha256), 1)

    def test_tampered_registry_with_all_refs_and_fake_expected_fails(self) -> None:
        """Even if the attacker sets the expected hash to the tampered hash,
        the gate must still verify that the registry records match the bundled
        manifests. This test changes the registry content_sha256 to not match
        the bundled manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            # Attacker modifies the registry content_sha256 for the forcing record
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            for record in reg['manifests']:
                if record['id'] == 'fm_001':
                    record['content_sha256'] = '0' * 64
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            # Update all internal refs to be self-consistent with tampered hash
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap['records']['forcing']['manifest_sha256'] = '0' * 64
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result['approved_inputs']['forcing']['manifest_sha256'] = '0' * 64
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # Even with the tampered hash as expected, the gate must detect that
            # the registry record's content_sha256 does not match the actual
            # bundled manifest file hash.
            self.assertEqual(_gate(root, tampered_hash), 1)

    def test_malformed_json_registry_fails(self) -> None:
        """Malformed JSON in the registry file must fail closed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg_path.write_bytes(b'{not valid json')
            # Use the hash of the malformed bytes as expected — gate must still
            # reject because the registry is not valid JSON.
            malformed_hash = hashlib.sha256(b'{not valid json').hexdigest()
            self.assertEqual(_gate(root, malformed_hash), 1)

    def test_malformed_utf8_registry_fails(self) -> None:
        """Malformed UTF-8 in the registry file must fail closed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            bad_bytes = b'\xff\xfe\x00{bad utf-8'
            reg_path.write_bytes(bad_bytes)
            bad_hash = hashlib.sha256(bad_bytes).hexdigest()
            self.assertEqual(_gate(root, bad_hash), 1)

    def test_duplicate_manifest_ids_in_registry_fails(self) -> None:
        """Duplicate manifest IDs in the registry must fail closed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            # Duplicate the first record
            reg['manifests'].append(reg['manifests'][0])
            dup_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(dup_bytes)
            dup_hash = hashlib.sha256(dup_bytes).hexdigest()
            self.assertEqual(_gate(root, dup_hash), 1)

    def test_wrong_region_in_registry_record_fails(self) -> None:
        """If a registry record has the wrong region, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            for record in reg['manifests']:
                if record['id'] == 'fm_001':
                    record['region'] = 'wrong_region'
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            # Update snapshot to be self-consistent
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap['records']['forcing']['region'] = 'wrong_region'
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # The gate must reject because the registry record region disagrees
            # with the manifest region (himalayas_nepal).
            self.assertEqual(_gate(root, tampered_hash), 1)

    def test_unapproved_record_in_registry_fails(self) -> None:
        """If a registry record is not approved, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            for record in reg['manifests']:
                if record['id'] == 'fm_001':
                    record['approval_state'] = 'rejected'
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            # Update snapshot to be self-consistent
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap['records']['forcing']['approval_state'] = 'rejected'
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            self.assertEqual(_gate(root, tampered_hash), 1)

    def test_registry_symlink_fails(self) -> None:
        """A symlinked registry file must fail closed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            # Replace with a symlink to an external file
            external = Path(tmp) / 'external-registry.json'
            external.write_bytes(reg_path.read_bytes())
            reg_path.unlink()
            reg_path.symlink_to(external)
            self.assertEqual(_gate(root, registry_sha256), 1)

    def test_registry_path_traversal_in_result_ignored(self) -> None:
        """G-R1.1.7: The gate uses a fixed registry path and ignores the
        registry_bundle_path in result.json. A traversal attempt in result.json
        should be ignored — the gate reads from the fixed path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['registry_bundle_path'] = '../outside.json'
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # Gate should still pass — it uses the fixed path, not result.json's path
            self.assertEqual(_gate(root, registry_sha256), 0)

    def test_snapshot_registry_hash_claim_mismatch_fails(self) -> None:
        """If the snapshot claims a different registry hash than what the
        actual registry bytes hash to, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            # Change the snapshot's registry_sha256 claim to a wrong value
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = 'f' * 64
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = 'f' * 64
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # The gate must fail because 'f'*64 != actual registry hash
            self.assertEqual(_gate(root, registry_sha256), 1)


# ── R1.1 cross-verification gap probes ────────────────────────────────────

class TestR11TrustAnchorProvenance(unittest.TestCase):
    """G-R1.1.1: The expected_registry_sha256 must not be sourceable from
    inside the bundle. If the expected hash matches any hash found in the
    bundle's result.json or snapshot, the anchor is circular."""

    def test_expected_hash_matching_result_json_field_warns_but_passes(self) -> None:
        """G-R1.1.1: If the expected hash equals the registry_sha256 found in
        result.json, the gate should emit a WARNING (not fail) because the
        hash could be circular. The gate cannot verify provenance — it can
        only verify the hash matches the actual bytes. Provenance is a CI
        policy concern, not a gate concern."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            result = json.loads((root / 'result.json').read_text())
            internal_registry_sha = result['registry_snapshot']['registry_sha256']
            # The gate should pass (hash matches actual bytes) but warn
            self.assertEqual(_gate(root, internal_registry_sha), 0)

    def test_expected_hash_matching_bundled_file_hash_fails(self) -> None:
        """If the expected hash equals the hash of any bundled JSON file
        other than the registry itself, refuse (circular anchor)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            # Hash the snapshot file and try to use it as the expected registry hash
            snap_bytes = (root / 'input-manifests' / 'approval-registry-snapshot.json').read_bytes()
            snap_hash = hashlib.sha256(snap_bytes).hexdigest()
            self.assertEqual(_gate(root, snap_hash), 1)


class TestR11PostApprovalMutation(unittest.TestCase):
    """G-R1.1.2: The producer must not mutate the registry after execution.
    The gate should detect if the registry bytes differ from the pre-execution
    freeze."""

    def test_registry_mutated_after_freeze_fails(self) -> None:
        """If the registry was mutated after the pre-execution freeze (e.g.,
        toolchain content_sha256 was rewritten), the gate should detect that
        the registry bytes don't match the frozen approved bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            # Simulate post-approval mutation: change a non-selected field
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            reg['manifests'][0]['source'] = 'mutated-post-approval'
            mutated_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(mutated_bytes)
            mutated_hash = hashlib.sha256(mutated_bytes).hexdigest()
            # Update all internal refs to be self-consistent
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = mutated_hash
            snap['records']['forcing']['source'] = 'mutated-post-approval'
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = mutated_hash
            result['approved_inputs']['forcing']['source'] = 'mutated-post-approval'
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # Gate must fail: mutated hash != original approved hash
            self.assertEqual(_gate(root, registry_sha256), 1)


class TestR11TOCTOUAndFixedPath(unittest.TestCase):
    """G-R1.1.3 + G-R1.1.7: The gate must use a fixed registry path and
    open the file atomically (O_NOFOLLOW) to prevent TOCTOU races."""

    def test_registry_at_non_standard_path_fails(self) -> None:
        """If the registry is at a different path than the fixed
        input-manifests/approval-registry.json, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            # Move the registry to a different name
            old_path = root / 'input-manifests' / 'approval-registry.json'
            new_path = root / 'input-manifests' / 'renamed-registry.json'
            old_path.rename(new_path)
            # Update result.json to point to the new path
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['registry_bundle_path'] = 'input-manifests/renamed-registry.json'
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # Gate must fail: registry must be at the fixed path
            self.assertEqual(_gate(root, registry_sha256), 1)

    def test_registry_replaced_with_directory_fails(self) -> None:
        """If the registry path is a directory, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg_path.unlink()
            reg_path.mkdir()
            self.assertEqual(_gate(root, registry_sha256), 1)


class TestR11RegistryAllowlist(unittest.TestCase):
    """G-R1.1.4 + G-R1.1.9: The gate must verify no unapproved records exist
    for the same region/elevation as the run."""

    def test_unapproved_record_for_same_region_fails(self) -> None:
        """If the registry contains an unapproved record for the same
        region/elevation as the run, the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            # Add an unapproved record for the same region/elevation
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            reg['manifests'].append({
                'id': 'fm_rogue',
                'kind': 'forcing',
                'content_sha256': 'a' * 64,
                'source': 'rogue-source',
                'licence': 'test',
                'units': 'SI',
                'region': 'himalayas_nepal',
                'elevation_band': 'lower',
                'valid_from': '2024-01-01T00:00:00Z',
                'valid_to': '2030-01-01T00:00:00Z',
                'approval_state': 'rejected',
                'manifest_path': 'fixtures/rogue.json',
                'payload_path': 'fixtures/rogue-payload.json',
                'payload_sha256': 'b' * 64,
            })
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            # Update internal refs
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # Even with the tampered hash as expected, the gate must detect
            # the unapproved record for the same region/elevation.
            self.assertEqual(_gate(root, tampered_hash), 1)


class TestR11ValidityInterval(unittest.TestCase):
    """G-R1.1.6: The gate must verify valid_from/valid_to against the run
    timestamp."""

    def test_expired_record_fails(self) -> None:
        """If a selected record's valid_to is before the run timestamp,
        the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            # Make the forcing record expired
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            for record in reg['manifests']:
                if record['id'] == 'fm_001':
                    record['valid_to'] = '2020-01-01T00:00:00Z'
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            # Update internal refs
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap['records']['forcing']['valid_to'] = '2020-01-01T00:00:00Z'
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result['approved_inputs']['forcing']['valid_to'] = '2020-01-01T00:00:00Z'
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            # The run timestamp is 2026-01-15, but valid_to is 2020 — expired
            self.assertEqual(_gate(root, tampered_hash), 1)

    def test_not_yet_valid_record_fails(self) -> None:
        """If a selected record's valid_from is after the run timestamp,
        the gate must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_sha256 = _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            for record in reg['manifests']:
                if record['id'] == 'fm_001':
                    record['valid_from'] = '2030-01-01T00:00:00Z'
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap['records']['forcing']['valid_from'] = '2030-01-01T00:00:00Z'
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result['approved_inputs']['forcing']['valid_from'] = '2030-01-01T00:00:00Z'
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            self.assertEqual(_gate(root, tampered_hash), 1)

    def test_retrospective_window_uses_separate_approval_window(self) -> None:
        """Historical data validity must not expire a later approved replay."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            approval_from = '2026-01-01T00:00:00Z'
            approval_to = '2026-12-31T23:59:59Z'
            for record in reg['manifests']:
                record['approval_valid_from'] = approval_from
                record['approval_valid_to'] = approval_to
            registry_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(registry_bytes)
            registry_sha256 = hashlib.sha256(registry_bytes).hexdigest()

            snapshot_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_bytes())
            snapshot['registry_sha256'] = registry_sha256
            for record in snapshot['records'].values():
                record['approval_valid_from'] = approval_from
                record['approval_valid_to'] = approval_to
            snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode()
            snapshot_path.write_bytes(snapshot_bytes)

            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snapshot_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = registry_sha256
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')

            self.assertEqual(_gate(root, registry_sha256), 0)


class TestR11SchemaAndSize(unittest.TestCase):
    """G-R1.1.5 + G-R1.1.8: Schema versioning and registry size limits."""

    def test_unsupported_schema_version_fails(self) -> None:
        """A registry with an unsupported schema version must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            reg['schema_version'] = 'snowpack_manifest_registry_v999'
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            snap['source_registry_version'] = 'snowpack_manifest_registry_v999'
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            self.assertEqual(_gate(root, tampered_hash), 1)

    def test_oversized_registry_fails(self) -> None:
        """A registry exceeding the size limit must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            # Add a huge payload_sha256 to inflate the file
            for record in reg['manifests']:
                record['padding'] = 'x' * (2 * 1024 * 1024)  # 2MB per record
            huge_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(huge_bytes)
            huge_hash = hashlib.sha256(huge_bytes).hexdigest()
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = huge_hash
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = huge_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            self.assertEqual(_gate(root, huge_hash), 1)


class TestR11FieldCompleteness(unittest.TestCase):
    """G-R1.1.5 (Phase 5): Every registry record must have all required fields."""

    def test_record_missing_required_field_fails(self) -> None:
        """A registry record missing a required field must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            reg_path = root / 'input-manifests' / 'approval-registry.json'
            reg = json.loads(reg_path.read_bytes())
            # Remove 'approval_state' from a selected record
            for record in reg['manifests']:
                if record['id'] == 'fm_001':
                    del record['approval_state']
            tampered_bytes = json.dumps(reg, sort_keys=True, indent=2).encode()
            reg_path.write_bytes(tampered_bytes)
            tampered_hash = hashlib.sha256(tampered_bytes).hexdigest()
            snap_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snap = json.loads(snap_path.read_bytes())
            snap['registry_sha256'] = tampered_hash
            del snap['records']['forcing']['approval_state']
            snap_bytes = json.dumps(snap, sort_keys=True, indent=2).encode()
            snap_path.write_bytes(snap_bytes)
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snap_bytes).hexdigest()
            result['registry_snapshot']['registry_sha256'] = tampered_hash
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
            self.assertEqual(_gate(root, tampered_hash), 1)


if __name__ == '__main__':
    unittest.main()
