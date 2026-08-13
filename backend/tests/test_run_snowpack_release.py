"""Producer-to-gate integration tests for the SNOWPACK release orchestrator.

G6 (sixth-pass): Proves the producer-to-consumer contract holds.
The orchestrator generates a bundle, then the release gate verifies it.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.common.snowpack_contracts import (
    ForecastSemanticsContract,
    InitialSnowStateContract,
    ProvenanceMetadata,
)
from backend.common.snowpack_release_semantics import (
    forecast_semantics_envelope,
    initial_state_envelope,
    snow_free_state_hash,
)


def _write_approved_registry(root: Path) -> Path:
    """Create hash-verified registry records for the producer integration test."""
    manifest_dir = root / 'manifests'
    manifest_dir.mkdir()
    records = []
    for manifest_id, kind in (
        ('fm_001', 'forcing'),
        ('gm_001', 'geometry'),
        ('tc_001', 'toolchain'),
    ):
        relative = f'manifests/{manifest_id}.json'
        path = root / relative
        path.write_text(json.dumps({
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
        }), encoding='utf-8')
        payload_relative = None
        payload_sha = None
        if kind in {'forcing', 'geometry'}:
            payload_relative = f'manifests/{manifest_id}-payload.json'
            payload_path = root / payload_relative
            payload = (
                [{'time': '2024-01-01T00:00:00+00:00', 'temperature_2m': -5.0,
                  'relative_humidity_2m': 80.0, 'windspeed_10m': 5.0,
                  'shortwave_radiation': 200.0, 'precipitation': 0.0,
                  'cloud_cover': 50.0}]
                if kind == 'forcing'
                else {'latitude': 28.0, 'longitude': 86.0, 'elevation_m': 4000.0,
                      'slope_angle': 30.0, 'aspect': 180.0,
                      'crs': 'EPSG:4326', 'zone_id': 'nepal-lower-test',
                      'dem_sha256': 'd' * 64}
            )
            payload_path.write_text(json.dumps(payload), encoding='utf-8')
            manifest = json.loads(path.read_text())
            manifest['payload_path'] = payload_relative
            manifest['payload_sha256'] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
            path.write_text(json.dumps(manifest), encoding='utf-8')
            payload_sha = manifest['payload_sha256']
        record = {
            'id': manifest_id,
            'kind': kind,
            'content_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'source': 'test-source',
            'licence': 'test-licence',
            'units': 'SI',
            'region': 'himalayas_nepal',
            'elevation_band': 'lower',
            'valid_from': '2024-01-01T00:00:00Z',
            'valid_to': '2030-01-01T00:00:00Z',
            'approval_state': 'approved',
            'manifest_path': relative,
        }
        if payload_relative is not None:
            record['payload_path'] = payload_relative
            record['payload_sha256'] = payload_sha
        records.append(record)
    registry = root / 'registry.json'
    registry.write_text(json.dumps({
        'schema_version': 'snowpack_manifest_registry_v1',
        'manifests': records,
    }), encoding='utf-8')
    return registry


def _write_contract_registry(root: Path) -> Path:
    """Create a forcing registry with hash-bound mapping/policy contracts."""
    registry = _write_approved_registry(root)
    mapping = root / 'mapping.json'
    policy = root / 'policy.json'
    mapping.write_text('{"contract":"mapping"}\n', encoding='utf-8')
    policy.write_text('{"contract":"policy"}\n', encoding='utf-8')
    manifest_path = root / 'manifests/fm_001.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update({
        'mapping_contract_path': 'mapping.json',
        'mapping_contract_sha256': hashlib.sha256(mapping.read_bytes()).hexdigest(),
        'meteoio_policy_path': 'policy.json',
        'meteoio_policy_sha256': hashlib.sha256(policy.read_bytes()).hexdigest(),
    })
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    data = json.loads(registry.read_text(encoding='utf-8'))
    forcing_record = next(item for item in data['manifests'] if item['id'] == 'fm_001')
    forcing_record['content_sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    registry.write_text(json.dumps(data), encoding='utf-8')
    return registry


def _write_semantics_inputs(root: Path, run_id: str = 'run_001') -> tuple[Path, Path]:
    input_dir = root / 'semantics'
    input_dir.mkdir()
    provenance = ProvenanceMetadata(
        source='test-state', source_class='direct', licence='test-licence',
        timestamp='2026-01-15T00:00:00+00:00', units={'state': 'native'},
        hash='a' * 64, run_id=run_id,
    )
    provisional = InitialSnowStateContract(
        state_id='state_001', state_type='snow_free',
        start_time='2026-01-15T00:00:00Z', source='test-state',
        state_sha256='0' * 64, provenance=provenance,
    )
    state = replace(provisional, state_sha256=snow_free_state_hash(provisional))
    forecast = ForecastSemanticsContract(
        mode='forecast', source='test-forecast',
        forecast_cycle='2026-01-15T00:00:00Z',
        valid_from='2026-01-16T00:00:00Z', valid_to='2026-01-17T00:00:00Z',
        as_of='2026-01-15T00:00:00Z', lead_time_h=24,
        region_key='himalayas_nepal', elevation_band='lower',
        forcing_manifest_id='fm_001',
    )
    state_path = input_dir / 'initial-state.json'
    forecast_path = input_dir / 'forecast-semantics.json'
    state_path.write_text(json.dumps(initial_state_envelope(state)), encoding='utf-8')
    forecast_path.write_text(json.dumps(forecast_semantics_envelope(forecast)), encoding='utf-8')
    return state_path, forecast_path


class TestOrchestratorSafeCleanup(unittest.TestCase):
    """G8: Orchestrator must reject unsafe output paths."""

    def test_symlink_output_bundle_rejected(self) -> None:
        """Orchestrator must refuse to delete a symlinked output path."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            real_dir = d / 'real'
            real_dir.mkdir()
            symlink_path = d / 'symlink_to_real'
            symlink_path.symlink_to(real_dir)

            from backend.scripts.run_snowpack_release import run_release_orchestration
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=symlink_path,
                approved_artifact_root=d,
            )
            self.assertEqual(exit_code, 1)
            # Symlink must still exist (not deleted)
            self.assertTrue(symlink_path.exists())

    def test_file_output_bundle_rejected(self) -> None:
        """Orchestrator must refuse to delete a non-directory output path."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            file_path = d / 'not_a_dir.txt'
            file_path.write_text('I am a file', encoding='utf-8')

            from backend.scripts.run_snowpack_release import run_release_orchestration
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=file_path,
                approved_artifact_root=d,
            )
            self.assertEqual(exit_code, 1)

    def test_nonexistent_traversal_output_path_rejected_before_cleanup(self) -> None:
        """C0.12: Nonexistent paths containing .. must fail before mkdir/rmtree."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            approved = d / 'approved'
            approved.mkdir()
            target = approved / 'missing' / '..' / 'bundle'
            marker = d / 'marker.txt'
            marker.write_text('must remain', encoding='utf-8')

            from backend.scripts.run_snowpack_release import run_release_orchestration
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=target,
                approved_artifact_root=approved,
                dry_run=True,
            )
            self.assertEqual(exit_code, 1)
            self.assertFalse(target.exists())
            self.assertEqual(marker.read_text(encoding='utf-8'), 'must remain')

    def test_output_outside_approved_root_rejected(self) -> None:
        """C0.12: Sibling-prefix/outside targets cannot be selected for cleanup."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            approved = d / 'bundle-root'
            approved.mkdir()
            outside = d / 'bundle-root-evil' / 'bundle'

            from backend.scripts.run_snowpack_release import run_release_orchestration
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=outside,
                approved_artifact_root=approved,
                dry_run=True,
            )
            self.assertEqual(exit_code, 1)
            self.assertFalse(outside.parent.exists())


class TestOrchestratorDryRunRejected(unittest.TestCase):
    """G7: Dry-run mode must not produce a release bundle."""

    def test_dry_run_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from backend.scripts.run_snowpack_release import run_release_orchestration
            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=Path(tmp) / 'bundle',
                approved_artifact_root=Path(tmp),
                dry_run=True,
            )
            self.assertEqual(exit_code, 1)


class TestOrchestratorExternalArtifactRejected(unittest.TestCase):
    """G5: Orchestrator must reject manifests with external artifact paths."""

    def test_external_artifact_path_rejected(self) -> None:
        """Orchestrator must fail when manifest has paths outside native-output/."""
        from backend.scripts.run_snowpack_release import _rebase_manifest_paths_to_relative

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle_root = d / 'bundle'
            native_output = bundle_root / 'native-output'
            native_output.mkdir(parents=True)

            # Manifest with an external path
            manifest_data = {
                'artifacts': [
                    {'file_path': '/tmp/external/run.smet', 'file_type': '.smet',
                     'size_bytes': 10, 'sha256': 'a' * 64, 'is_critical': True},
                ],
            }
            result = _rebase_manifest_paths_to_relative(
                manifest_data, bundle_root, native_output,
            )
            self.assertIsNone(result, 'External path must be rejected')


class TestOrchestratorProducerGateIntegration(unittest.TestCase):
    """G6: Full producer-to-gate integration test with monkeypatched runner."""

    def test_valid_producer_bundle_passes_gate(self) -> None:
        """Producer generates a valid bundle → release gate validates it → exit 0."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle_dir = d / 'release_bundle'
            registry = _write_approved_registry(d)
            state_path, forecast_path = _write_semantics_inputs(d)

            # Define contents for native output files
            contents = {
                '.smet': '0123456789',
                'processed-meteo.smet': 'processed meteo',
                '.pro': '1234567890',
                '.sno': '2345678901',
                '.haz': '3456789012',
                '.log': '4567890123',
            }

            # Create a fake runner that creates files as a side effect
            def fake_runner(**kwargs):
                forcing_record = kwargs['approved_forcing_manifest']
                geometry_record = kwargs['approved_geometry_manifest']
                self.assertTrue(Path(forcing_record['resolved_payload_path']).is_file())
                self.assertTrue(Path(geometry_record['resolved_payload_path']).is_file())
                self.assertEqual(forcing_record['id'], kwargs['forcing_manifest_id'])
                self.assertEqual(geometry_record['id'], kwargs['geometry_manifest_id'])
                output_dir = kwargs['output_dir']
                output_dir.mkdir(parents=True, exist_ok=True)
                for suffix, content in contents.items():
                    (output_dir / f'run{suffix}').write_text(content, encoding='utf-8')
                from backend.common.snowpack_artifact_manifest import (
                    build_manifest_from_directory, manifest_to_json,
                )
                manifest = build_manifest_from_directory(
                    run_id=kwargs['run_id'],
                    region_key=kwargs['region'].key,
                    elevation_band=kwargs['elevation_band'],
                    aspect_class='N',
                    binary_version='snowpack-3.7.0',
                    output_dir=output_dir,
                    created_at='2026-01-15T00:00:00+00:00',
                    native_binary_invoked=True,
                    toolchain_id=kwargs['toolchain_manifest_id'],
                    forcing_manifest_id=kwargs['forcing_manifest_id'],
                    geometry_manifest_id=kwargs['geometry_manifest_id'],
                )
                manifest_data = json.loads(manifest_to_json(manifest))
                cmd_str = 'snowpack -c config.ini'
                toolchain_manifest = {
                    'schema_version': 'snowpack_toolchain_manifest_v1',
                    'toolchain_id': kwargs['toolchain_manifest_id'],
                    'meteoio_commit': 'a' * 40,
                    'snowpack_commit': 'b' * 40,
                    'binary_path': '/opt/snowpack/bin/snowpack',
                    'binary_sha256': 'a' * 64,
                    'binary_version': 'snowpack-3.7.0',
                    'image_id': 'sha256:' + 'c' * 64,
                    'image_archive_sha256': 'd' * 64,
                    'image_repository_digest': '',
                    'image_identity_source': 'local_id_and_archive',
                }
                toolchain_manifest_sha256 = hashlib.sha256(
                    json.dumps(toolchain_manifest, indent=2, sort_keys=True).encode()
                ).hexdigest()
                return {
                    'status': 'completed',
                    'method': 'awsome',
                    'engine': 'snowpack_direct',
                    'run_id': kwargs['run_id'],
                    'toolchain_manifest_id': kwargs['toolchain_manifest_id'],
                    'forcing_manifest_id': kwargs['forcing_manifest_id'],
                    'geometry_manifest_id': kwargs['geometry_manifest_id'],
                    'no_fallback': True,
                    'manifest': manifest_data,
                    'execution_evidence': {
                        'binary_path': '/opt/snowpack/bin/snowpack',
                        'binary_sha256': 'a' * 64,
                        'binary_version': 'snowpack-3.7.0',
                        'command': cmd_str,
                        'command_sha256': hashlib.sha256(cmd_str.encode()).hexdigest(),
                        'exit_code': 0,
                        'version_exit_code': 0,
                        'version_verified': True,
                        'toolchain_manifest_sha256': toolchain_manifest_sha256,
                        'toolchain_manifest_verified': True,
                        'image_id': 'sha256:' + 'c' * 64,
                        'image_archive_sha256': 'd' * 64,
                        'image_repository_digest': '',
                        'image_identity_source': 'local_id_and_archive',
                        'toolchain_manifest': toolchain_manifest,
                        'started_at': '2026-01-15T00:00:00+00:00',
                        'finished_at': '2026-01-15T00:05:00+00:00',
                        'toolchain_id': kwargs['toolchain_manifest_id'],
                        'run_id': kwargs['run_id'],
                        'stdout_sha256': 'b' * 64,
                        'stderr_sha256': 'c' * 64,
                    },
                }

            from backend.common.regions import Region
            fake_region = Region(
                name='Himalayas Nepal',
                bbox=(80.0, 26.0, 88.0, 30.0),
                center=(84.0, 28.0),
                zoom=7,
            )

            with patch(
                'backend.common.awsome_runner.run_awsome_for_region',
                side_effect=fake_runner,
            ), patch(
                'backend.common.regions.load_regions',
                return_value=[fake_region],
            ):
                from backend.scripts.run_snowpack_release import run_release_orchestration
                exit_code = run_release_orchestration(
                    region_key='himalayas_nepal',
                    elevation_band='lower',
                    run_id='run_001',
                    toolchain_id='tc_001',
                    forcing_id='fm_001',
                    geometry_id='gm_001',
                    engine='snowpack_direct',
                    output_bundle=bundle_dir,
                    approved_artifact_root=d,
                    manifest_registry_path=registry,
                    expected_registry_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),
                    initial_state_manifest_path=state_path,
                    forecast_semantics_manifest_path=forecast_path,
                )
                # Producer should succeed AND gate should validate
                self.assertEqual(
                    exit_code, 0,
                    f'Producer-to-gate integration failed: exit={exit_code}',
                )

    def test_poc_producer_bundle_passes_both_gates(self) -> None:
        """P1-12: POC producer creates bundle → self-gate validates →
        consumer gate validates the copied bundle. No gate monkeypatching."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle_dir = d / 'release_bundle'
            registry = _write_approved_registry(d)
            state_path, forecast_path = _write_semantics_inputs(d)

            # POC: Use Pir Panjal decision record
            dr_path = Path('docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json')
            dr_hash = hashlib.sha256(dr_path.read_bytes()).hexdigest()

            # POC: Regenerate initial state with POC run_id
            provenance = ProvenanceMetadata(
                source='test-state', source_class='direct', licence='test-licence',
                timestamp='2026-01-15T00:00:00+00:00', units={'state': 'native'},
                hash='a' * 64, run_id='run_poc_001',
            )
            provisional = InitialSnowStateContract(
                state_id='state_001', state_type='snow_free',
                start_time='2026-01-15T00:00:00Z', source='test-state',
                state_sha256='0' * 64, provenance=provenance,
            )
            state = replace(provisional, state_sha256=snow_free_state_hash(provisional))
            state_path = d / 'semantics' / 'initial-state.json'
            state_path.write_text(json.dumps(initial_state_envelope(state)), encoding='utf-8')

            # POC: Override registry records for Pir Panjal
            # We need to rewrite the registry with pir_panjal region/band
            records = []
            for manifest_id, kind in (
                ('fm_001', 'forcing'),
                ('gm_001', 'geometry'),
                ('tc_001', 'toolchain'),
            ):
                relative = f'manifests/{manifest_id}.json'
                path = d / relative
                manifest = json.loads(path.read_text())
                manifest['region'] = 'pir_panjal_nw_himalaya'
                manifest['elevation_band'] = 'middle'
                path.write_text(json.dumps(manifest), encoding='utf-8')
                payload_relative = manifest.get('payload_path')
                if payload_relative:
                    payload_path = d / payload_relative
                    manifest['payload_sha256'] = hashlib.sha256(
                        payload_path.read_bytes()
                    ).hexdigest()
                    path.write_text(json.dumps(manifest), encoding='utf-8')
                record = {
                    'id': manifest_id,
                    'kind': kind,
                    'content_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'source': 'test-source',
                    'licence': 'test-licence',
                    'units': 'SI',
                    'region': 'pir_panjal_nw_himalaya',
                    'elevation_band': 'middle',
                    'valid_from': '2024-01-01T00:00:00Z',
                    'valid_to': '2030-01-01T00:00:00Z',
                    'approval_state': 'approved',
                    'manifest_path': relative,
                }
                if payload_relative:
                    record['payload_path'] = payload_relative
                    record['payload_sha256'] = manifest['payload_sha256']
                records.append(record)
            registry.write_text(json.dumps({
                'schema_version': 'snowpack_manifest_registry_v1',
                'manifests': records,
            }), encoding='utf-8')
            registry_hash = hashlib.sha256(registry.read_bytes()).hexdigest()

            # POC: Override forecast semantics for Pir Panjal 48h
            # as_of → valid_from must be lead_time_h hours apart
            # forecast_cycle must be <= as_of
            forecast = ForecastSemanticsContract(
                mode='forecast', source='test-forecast',
                forecast_cycle='2026-01-13T00:00:00Z',
                valid_from='2026-01-15T00:00:00Z', valid_to='2026-01-17T00:00:00Z',
                as_of='2026-01-13T00:00:00Z', lead_time_h=48,
                region_key='pir_panjal_nw_himalaya', elevation_band='middle',
                forcing_manifest_id='fm_001',
                ensemble_members=1,
            )
            forecast_path = d / 'semantics' / 'forecast-semantics.json'
            forecast_path.write_text(
                json.dumps(forecast_semantics_envelope(forecast)), encoding='utf-8'
            )

            contents = {
                '.smet': '0123456789',
                'processed-meteo.smet': 'processed meteo',
                '.pro': '1234567890',
                '.sno': '2345678901',
                '.haz': '3456789012',
                '.log': '4567890123',
            }

            def fake_runner(**kwargs):
                output_dir = kwargs['output_dir']
                output_dir.mkdir(parents=True, exist_ok=True)
                for suffix, content in contents.items():
                    (output_dir / f'run{suffix}').write_text(content, encoding='utf-8')
                from backend.common.snowpack_artifact_manifest import (
                    build_manifest_from_directory, manifest_to_json,
                )
                manifest = build_manifest_from_directory(
                    run_id=kwargs['run_id'],
                    region_key=kwargs['region'].key,
                    elevation_band=kwargs['elevation_band'],
                    aspect_class='N',
                    binary_version='snowpack-3.7.0',
                    output_dir=output_dir,
                    created_at='2026-01-15T00:00:00+00:00',
                    native_binary_invoked=True,
                    toolchain_id=kwargs['toolchain_manifest_id'],
                    forcing_manifest_id=kwargs['forcing_manifest_id'],
                    geometry_manifest_id=kwargs['geometry_manifest_id'],
                )
                manifest_data = json.loads(manifest_to_json(manifest))
                cmd_str = 'snowpack -c config.ini'
                toolchain_manifest = {
                    'schema_version': 'snowpack_toolchain_manifest_v1',
                    'toolchain_id': kwargs['toolchain_manifest_id'],
                    'meteoio_commit': 'a' * 40,
                    'snowpack_commit': 'b' * 40,
                    'binary_path': '/opt/snowpack/bin/snowpack',
                    'binary_sha256': 'a' * 64,
                    'binary_version': 'snowpack-3.7.0',
                    'image_id': 'sha256:' + 'c' * 64,
                    'image_archive_sha256': 'd' * 64,
                    'image_repository_digest': '',
                    'image_identity_source': 'local_id_and_archive',
                }
                toolchain_manifest_sha256 = hashlib.sha256(
                    json.dumps(toolchain_manifest, indent=2, sort_keys=True).encode()
                ).hexdigest()
                return {
                    'status': 'completed',
                    'method': 'awsome',
                    'engine': 'snowpack_direct',
                    'run_id': kwargs['run_id'],
                    'toolchain_manifest_id': kwargs['toolchain_manifest_id'],
                    'forcing_manifest_id': kwargs['forcing_manifest_id'],
                    'geometry_manifest_id': kwargs['geometry_manifest_id'],
                    'no_fallback': True,
                    'manifest': manifest_data,
                    'execution_evidence': {
                        'binary_path': '/opt/snowpack/bin/snowpack',
                        'binary_sha256': 'a' * 64,
                        'binary_version': 'snowpack-3.7.0',
                        'command': cmd_str,
                        'command_sha256': hashlib.sha256(cmd_str.encode()).hexdigest(),
                        'exit_code': 0,
                        'version_exit_code': 0,
                        'version_verified': True,
                        'toolchain_manifest_sha256': toolchain_manifest_sha256,
                        'toolchain_manifest_verified': True,
                        'image_id': 'sha256:' + 'c' * 64,
                        'image_archive_sha256': 'd' * 64,
                        'image_repository_digest': '',
                        'image_identity_source': 'local_id_and_archive',
                        'toolchain_manifest': toolchain_manifest,
                        'started_at': '2026-01-15T00:00:00+00:00',
                        'finished_at': '2026-01-15T00:05:00+00:00',
                        'toolchain_id': kwargs['toolchain_manifest_id'],
                        'run_id': kwargs['run_id'],
                        'stdout_sha256': 'b' * 64,
                        'stderr_sha256': 'c' * 64,
                    },
                }

            from backend.common.regions import Region
            fake_region = Region(
                name='Pir Panjal NW Himalaya',
                bbox=(73.0, 33.0, 78.0, 35.0),
                center=(75.5, 34.0),
                zoom=7,
            )

            with patch(
                'backend.common.awsome_runner.run_awsome_for_region',
                side_effect=fake_runner,
            ), patch(
                'backend.common.regions.load_regions',
                return_value=[fake_region],
            ):
                from backend.scripts.run_snowpack_release import run_release_orchestration
                exit_code = run_release_orchestration(
                    region_key='pir_panjal_nw_himalaya',
                    elevation_band='middle',
                    run_id='run_poc_001',
                    toolchain_id='tc_001',
                    forcing_id='fm_001',
                    geometry_id='gm_001',
                    engine='snowpack_direct',
                    output_bundle=bundle_dir,
                    approved_artifact_root=d,
                    manifest_registry_path=registry,
                    expected_registry_sha256=registry_hash,
                    initial_state_manifest_path=state_path,
                    forecast_semantics_manifest_path=forecast_path,
                    decision_record_path=dr_path,
                    expected_decision_record_sha256=dr_hash,
                )
                # Producer self-gate must pass
                self.assertEqual(
                    exit_code, 0,
                    f'POC producer-to-gate integration failed: exit={exit_code}',
                )

                # Now copy the bundle to a separate directory and run the
                # consumer gate independently (simulating download + re-gate)
                import shutil
                consumer_dir = d / 'consumer_bundle'
                shutil.copytree(bundle_dir, consumer_dir)

                from backend.scripts.release_gate import run_release_gate
                consumer_exit = run_release_gate(
                    consumer_dir,
                    expected_run_id='run_poc_001',
                    expected_registry_sha256=registry_hash,
                    expected_decision_record_sha256=dr_hash,
                    poc_mode=True,
                )
                self.assertEqual(
                    consumer_exit, 0,
                    f'Consumer gate rejected POC bundle that producer validated: '
                    f'exit={consumer_exit}',
                )

    def test_contract_files_are_bundled_and_re_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle_dir = d / 'release_bundle'
            registry = _write_contract_registry(d)
            state_path, forecast_path = _write_semantics_inputs(d)

            def fake_runner(**kwargs):
                output_dir = kwargs['output_dir']
                output_dir.mkdir(parents=True, exist_ok=True)
                for name in ('run.smet', 'processed-meteo.smet', 'run.pro', 'run.sno', 'run.haz', 'run.log'):
                    (output_dir / name).write_text('native', encoding='utf-8')
                from backend.common.snowpack_artifact_manifest import build_manifest_from_directory, manifest_to_json
                manifest = build_manifest_from_directory(
                    run_id=kwargs['run_id'], region_key=kwargs['region'].key,
                    elevation_band=kwargs['elevation_band'], aspect_class='N',
                    binary_version='snowpack-3.7.0', output_dir=output_dir,
                    created_at='2026-01-15T00:00:00+00:00', native_binary_invoked=True,
                    toolchain_id=kwargs['toolchain_manifest_id'],
                    forcing_manifest_id=kwargs['forcing_manifest_id'],
                    geometry_manifest_id=kwargs['geometry_manifest_id'],
                )
                toolchain_manifest = {
                    'schema_version': 'snowpack_toolchain_manifest_v1',
                    'toolchain_id': kwargs['toolchain_manifest_id'],
                    'meteoio_commit': 'a' * 40, 'snowpack_commit': 'b' * 40,
                    'binary_path': '/opt/snowpack/bin/snowpack',
                    'binary_sha256': 'a' * 64, 'binary_version': 'snowpack-3.7.0',
                    'image_id': 'sha256:' + 'c' * 64,
                    'image_archive_sha256': 'd' * 64,
                    'image_repository_digest': '', 'image_identity_source': 'local_id_and_archive',
                }
                toolchain_hash = hashlib.sha256(
                    json.dumps(toolchain_manifest, indent=2, sort_keys=True).encode()
                ).hexdigest()
                return {
                    'status': 'completed', 'method': 'awsome', 'engine': 'snowpack_direct',
                    'run_id': kwargs['run_id'], 'toolchain_manifest_id': kwargs['toolchain_manifest_id'],
                    'forcing_manifest_id': kwargs['forcing_manifest_id'],
                    'geometry_manifest_id': kwargs['geometry_manifest_id'], 'no_fallback': True,
                    'manifest': json.loads(manifest_to_json(manifest)),
                    'execution_evidence': {
                        'binary_path': '/opt/snowpack/bin/snowpack', 'binary_sha256': 'a' * 64,
                        'binary_version': 'snowpack-3.7.0', 'command': 'snowpack -c config.ini',
                        'command_sha256': hashlib.sha256('snowpack -c config.ini'.encode()).hexdigest(), 'exit_code': 0, 'version_exit_code': 0,
                        'version_verified': True, 'toolchain_manifest_sha256': toolchain_hash,
                        'toolchain_manifest_verified': True, 'image_id': 'sha256:' + 'c' * 64,
                        'image_archive_sha256': 'd' * 64, 'image_repository_digest': '',
                        'image_identity_source': 'local_id_and_archive',
                        'toolchain_manifest': toolchain_manifest,
                        'started_at': '2026-01-15T00:00:00+00:00',
                        'finished_at': '2026-01-15T00:05:00+00:00',
                        'toolchain_id': kwargs['toolchain_manifest_id'], 'run_id': kwargs['run_id'],
                        'stdout_sha256': 'b' * 64, 'stderr_sha256': 'c' * 64,
                    },
                }

            from backend.common.regions import Region
            fake_region = Region(
                name='Himalayas Nepal', bbox=(80.0, 26.0, 88.0, 30.0),
                center=(84.0, 28.0), zoom=7,
            )
            with patch('backend.common.awsome_runner.run_awsome_for_region', side_effect=fake_runner), patch(
                'backend.common.regions.load_regions', return_value=[fake_region]
            ):
                from backend.scripts.run_snowpack_release import run_release_orchestration
                exit_code = run_release_orchestration(
                    region_key='himalayas_nepal', elevation_band='lower', run_id='run_001',
                    toolchain_id='tc_001', forcing_id='fm_001', geometry_id='gm_001',
                    engine='snowpack_direct', output_bundle=bundle_dir, approved_artifact_root=d,
                    manifest_registry_path=registry,
                    expected_registry_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),
                    initial_state_manifest_path=state_path, forecast_semantics_manifest_path=forecast_path,
                )
            self.assertEqual(exit_code, 0)
            self.assertTrue((bundle_dir / 'input-manifests/forcing-contracts/mapping_contract.json').exists())
            self.assertTrue((bundle_dir / 'input-manifests/forcing-contracts/meteoio_policy.json').exists())

    def test_missing_external_registry_anchor_fails_before_native_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from backend.scripts.run_snowpack_release import run_release_orchestration

            exit_code = run_release_orchestration(
                region_key='himalayas_nepal',
                elevation_band='lower',
                run_id='run_001',
                toolchain_id='tc_001',
                forcing_id='fm_001',
                geometry_id='gm_001',
                engine='snowpack_direct',
                output_bundle=root / 'bundle',
                approved_artifact_root=root,
            )
            self.assertEqual(exit_code, 1)

    def test_failed_native_execution_cleans_up(self) -> None:
        """Producer must clean up bundle on failed native execution."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle_dir = d / 'release_bundle'

            fake_result = {
                'status': 'failed',
                'method': 'awsome',
                'run_id': 'run_001',
                'no_fallback': True,
                'error': 'Native execution failed',
            }

            from backend.common.regions import Region
            fake_region = Region(
                name='Himalayas Nepal',
                bbox=(80.0, 26.0, 88.0, 30.0),
                center=(84.0, 28.0),
                zoom=7,
            )

            with patch(
                'backend.common.awsome_runner.run_awsome_for_region',
                return_value=fake_result,
            ), patch(
                'backend.common.regions.load_regions',
                return_value=[fake_region],
            ):
                from backend.scripts.run_snowpack_release import run_release_orchestration
                exit_code = run_release_orchestration(
                    region_key='himalayas_nepal',
                    elevation_band='lower',
                    run_id='run_001',
                    toolchain_id='tc_001',
                    forcing_id='fm_001',
                    geometry_id='gm_001',
                    engine='snowpack_direct',
                    output_bundle=bundle_dir,
                    approved_artifact_root=d,
                )
                self.assertEqual(exit_code, 1)
                # Bundle directory should be cleaned up
                self.assertFalse(bundle_dir.exists(),
                                 'Failed bundle must be cleaned up')


if __name__ == '__main__':
    unittest.main()
