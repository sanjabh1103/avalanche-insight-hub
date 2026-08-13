"""C0-S2/C0-S3: Release orchestrator for SNOWPACK native execution.

This script is the CANONICAL producer of release bundles. It:
  1. Generates one explicit run_id at the orchestration boundary
  2. Cleans the bundle directory
  3. Calls the runner with output_dir INSIDE the bundle
  4. Writes relative manifest paths (relative to bundle root)
  5. Produces result.json, manifest.json, invocation.json, and the runtime
     toolchain-manifest.json
  6. Uploads exactly the bundle directory

Canonical bundle layout:
  bundle/
    result.json          # Run result with run_id, status, no_fallback
    manifest.json        # Artifact manifest with RELATIVE paths
    invocation.json      # Execution attestation with real subprocess evidence
    toolchain-manifest.json # Runtime commits, binary/version/SHA, image digest
    native-output/       # All SNOWPACK output files (.smet, .pro, .sno, .haz, .log)

The release gate (release_gate.py) is the consumer. It downloads this bundle
and verifies it. The gate rejects:
  - Absolute manifest paths (must be relative to bundle root)
  - Files outside the bundle (sibling-prefix, traversal, symlink escapes)
  - Missing invocation.json or invalid attestation
  - Non-completed status or missing no_fallback
  - run_id mismatch between result, manifest, and invocation

Usage:
  python -m backend.scripts.run_snowpack_release \
    --region himalayas_nepal \
    --elevation-band lower \
    --run-id snowpack-123-1-himalayas_nepal-lower \
    --engine snowpack_direct \
    --toolchain-id <approved-toolchain-id> \
    --forcing-id <approved-forcing-id> \
    --geometry-id <approved-geometry-id> \
    --initial-state-manifest <state-contract.json> \
    --forecast-semantics-manifest <forecast-contract.json> \
    --manifest-registry config/snowpack_manifest_registry.json \
    --output-bundle backend/artifacts/snowpack/bundle

Exit codes:
  0 = release bundle produced successfully (status=completed)
  1 = execution failed or bundle incomplete
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.snowpack_paths import (
    UnsafePathError,
    create_staging_directory,
    publish_staging_directory,
    safe_remove_directory,
    validate_output_bundle_path,
)

DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / 'backend' / 'artifacts' / 'snowpack'


def _rebase_manifest_paths_to_relative(
    manifest_data: dict,
    bundle_root: Path,
    native_output_dir: Path,
) -> dict | None:
    """C0-S3: Rebase manifest artifact paths to be relative to the bundle root.

    The manifest is built with absolute paths (from output_dir). We rewrite
    them to be relative to the bundle root so the release gate can verify
    files within the bundle regardless of where the bundle is downloaded.

    G5 (SIXTH-PASS): If any artifact path is NOT under native_output_dir,
    return None (fail closed). No basename fallback — every artifact must
    already be inside native-output/.
    """
    rebased = manifest_data.copy()
    new_artifacts = []
    native_output_resolved = native_output_dir.resolve()
    for art in manifest_data.get('artifacts', []):
        original = Path(art['file_path'])
        # G5: Every artifact MUST be under native_output_dir — no fallback
        try:
            rel_to_native = original.resolve().relative_to(native_output_resolved)
            new_path = f'native-output/{rel_to_native}'
        except (ValueError, OSError, RuntimeError):
            print(
                f'ERROR: Artifact path "{art["file_path"]}" is not under '
                f'native-output directory. External paths are not allowed. '
                f'No basename fallback — producer integrity enforced.',
                file=sys.stderr,
            )
            return None
        new_art = art.copy()
        new_art['file_path'] = new_path
        new_artifacts.append(new_art)
    rebased['artifacts'] = new_artifacts
    return rebased


def run_release_orchestration(
    *,
    region_key: str,
    elevation_band: str,
    run_id: str,
    toolchain_id: str,
    forcing_id: str,
    geometry_id: str,
    output_bundle: Path,
    engine: str,
    dry_run: bool = False,
    approved_artifact_root: Path | None = None,
    manifest_registry_path: Path | None = None,
    initial_state_manifest_path: Path | None = None,
    forecast_semantics_manifest_path: Path | None = None,
    expected_registry_sha256: str = '',
    decision_record_path: Path | None = None,
    expected_decision_record_sha256: str = '',
    poc_mode: bool | None = None,
) -> int:
    """Run the release orchestration. Returns 0 on success, 1 on failure.

    R1: POC mode is determined by the explicit --poc-mode flag if supplied,
    or inferred from decision_record_path presence if not. When poc_mode
    is explicit, it must agree with the path/digest combination:
      POC = path + valid digest (both required)
      non-POC = neither (both must be absent)
    Contradictory combinations fail before filesystem mutation.
    """
    # R1: Enforce the exact POC mode state machine before any work.
    has_dr_path = decision_record_path is not None
    has_dr_digest = bool((expected_decision_record_sha256 or '').strip())
    # Determine effective mode: explicit flag takes precedence, else infer
    # from path/digest presence.
    if poc_mode is not None:
        effective_poc_mode = poc_mode
    else:
        effective_poc_mode = has_dr_path or has_dr_digest

    if effective_poc_mode:
        # POC mode: both path and valid digest required
        if not has_dr_path:
            print(
                'ERROR: POC mode requires --decision-record-path.',
                file=sys.stderr,
            )
            return 1
        if not has_dr_digest:
            print(
                'ERROR: POC mode requires --expected-decision-record-sha256.',
                file=sys.stderr,
            )
            return 1
    else:
        # Non-POC mode: neither path nor digest allowed
        if has_dr_path:
            print(
                'ERROR: --decision-record-path supplied in non-POC mode. '
                'Non-POC runs must not include a decision record.',
                file=sys.stderr,
            )
            return 1
        if has_dr_digest:
            print(
                'ERROR: --expected-decision-record-sha256 supplied in non-POC mode. '
                'Non-POC runs must not include a decision record digest.',
                file=sys.stderr,
            )
            return 1

    from backend.common.awsome_runner import (
        _validate_manifest_ids_for_release,
        run_awsome_for_region,
    )
    from backend.common.pir_panjal_decision_record import (
        DecisionRecordError,
        decision_record_manifest_binding,
        load_decision_record,
        validate_poc_scope,
    )
    from backend.common.regions import load_regions
    from backend.common.snowpack_contracts import validate_release_run_id
    from backend.common.snowpack_release_semantics import (
        ReleaseSemanticsError,
        bind_initial_state_to_run_id,
        forecast_semantics_envelope,
        initial_state_envelope,
        load_forecast_semantics_manifest,
        load_initial_state_manifest,
        validate_initial_state_binding,
        validate_release_semantics_context,
    )
    from backend.common.snowpack_paths import ensure_safe_file
    from backend.common.snowpack_manifest_registry import DEFAULT_REGISTRY_PATH, resolve_approved_manifest

    try:
        run_id = validate_release_run_id(run_id)
    except ValueError as exc:
        print(f'ERROR: invalid release run_id: {exc}', file=sys.stderr)
        return 1

    print('=== SNOWPACK RELEASE ORCHESTRATOR ===')
    print(f'Run ID: {run_id}')
    print(f'Region: {region_key}')
    print(f'Elevation band: {elevation_band}')
    print(f'Output bundle: {output_bundle}')
    print(f'Engine: {engine}')

    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(expected_registry_sha256 or '')):
        print(
            'ERROR: release orchestration requires an externally supplied '
            'expected_registry_sha256; the bundled snapshot is not a trust anchor.',
            file=sys.stderr,
        )
        return 1

    # G3/G4: When a decision record path is supplied, load and strictly
    # validate it against the Pir Panjal POC scope. The raw-byte SHA-256
    # must match the externally supplied expected digest. The region, band,
    # and horizon must match the decision record.
    decision_record_binding: dict[str, Any] | None = None
    if decision_record_path is not None:
        if not expected_decision_record_sha256:
            print(
                'ERROR: --decision-record-path requires '
                '--expected-decision-record-sha256; the trust root is external.',
                file=sys.stderr,
            )
            return 1
        try:
            decision_record = load_decision_record(
                decision_record_path,
                expected_sha256=expected_decision_record_sha256,
            )
            validate_poc_scope(
                decision_record,
                region_key=region_key,
                elevation_band=elevation_band,
            )
            decision_record_binding = decision_record_manifest_binding(decision_record)
        except DecisionRecordError as exc:
            print(f'ERROR: decision record validation failed: {exc}', file=sys.stderr)
            return 1

    # C0.28/C0.32: Release mode requires one explicit engine and approved,
    # hash-verified forcing/geometry/toolchain manifests before any filesystem
    # mutation or native execution.
    if engine not in {'snowpack_direct', 'awsome'}:
        print(
            f'ERROR: release engine must be snowpack_direct or awsome, got {engine!r}',
            file=sys.stderr,
        )
        return 1
    if engine == 'awsome':
        print(
            'ERROR: AWSOME is shadow-only until complete runtime/image/output '
            'evidence is available; direct SNOWPACK is the only release engine.',
            file=sys.stderr,
        )
        return 1
    manifest_errors = _validate_manifest_ids_for_release(
        forcing_id=forcing_id,
        geometry_id=geometry_id,
        toolchain_id=toolchain_id,
        registry_path=manifest_registry_path,
        region_key=region_key,
        elevation_band=elevation_band,
    )
    if manifest_errors:
        print('ERROR: release manifest resolver rejected inputs:', file=sys.stderr)
        for error in manifest_errors:
            print(f'  - {error}', file=sys.stderr)
        return 1
    try:
        forcing_record = resolve_approved_manifest(
            forcing_id,
            kind='forcing',
            registry_path=manifest_registry_path,
            expected_region=region_key,
            expected_elevation_band=elevation_band,
        )
        geometry_record = resolve_approved_manifest(
            geometry_id,
            kind='geometry',
            registry_path=manifest_registry_path,
            expected_region=region_key,
            expected_elevation_band=elevation_band,
        )
        toolchain_record = resolve_approved_manifest(
            toolchain_id,
            kind='toolchain',
            registry_path=manifest_registry_path,
            expected_region=region_key,
            expected_elevation_band=elevation_band,
        )
    except ValueError as exc:
        print(f'ERROR: approved input resolution failed: {exc}', file=sys.stderr)
        return 1

    approved_root = approved_artifact_root or DEFAULT_ARTIFACT_ROOT
    # C2-prep: release mode must carry explicit initial-state and forecast
    # semantics manifests. These are input contracts, not scientific approval.
    if initial_state_manifest_path is None or forecast_semantics_manifest_path is None:
        print(
            'ERROR: release requires --initial-state-manifest and '
            '--forecast-semantics-manifest.',
            file=sys.stderr,
        )
        return 1
    try:
        initial_state_source = ensure_safe_file(Path(initial_state_manifest_path))
        forecast_semantics_source = ensure_safe_file(Path(forecast_semantics_manifest_path))
        initial_state, _ = load_initial_state_manifest(initial_state_source)
        forecast_semantics, _ = load_forecast_semantics_manifest(forecast_semantics_source)
        initial_state = bind_initial_state_to_run_id(initial_state, run_id)
        validate_release_semantics_context(
            state=initial_state,
            forecast=forecast_semantics,
            run_id=run_id,
            region_key=region_key,
            elevation_band=elevation_band,
            forcing_manifest_id=forcing_id,
        )
        # C0.1/C0.2/C0.3: Use the shared POC scope contract validator to
        # cross-validate decision record, forecast semantics, and (later)
        # result/manifest. This replaces the producer-only G5 checks with
        # the same validator used by the consumer gate.
        if decision_record_binding is not None:
            from backend.common.poc_scope_contract import PocScopeError, validate_poc_scope_consistency
            # Build a provisional result_data for the producer-side check
            provisional_result = {
                'region_key': region_key,
                'elevation_band': elevation_band,
                'decision_record': decision_record_binding,
            }
            # Build a provisional manifest for cross-validation
            from backend.common.snowpack_artifact_manifest import ArtifactManifest as _AM
            provisional_manifest = _AM(
                run_id=run_id,
                region_key=region_key,
                elevation_band=elevation_band,
                aspect_class='',
                binary_version='',
                artifacts=[],
                is_native_execution=True,
                native_binary_invoked=True,
                created_at='',
                toolchain_id='',
                forcing_manifest_id=forcing_id,
                geometry_manifest_id='',
            )
            try:
                poc_binding = validate_poc_scope_consistency(
                    decision_record=decision_record,
                    result_data=provisional_result,
                    manifest=provisional_manifest,
                    forecast=forecast_semantics,
                    expected_decision_record_sha256=expected_decision_record_sha256,
                    poc_mode=effective_poc_mode,
                )
            except PocScopeError as exc:
                print(f'ERROR: POC scope consistency validation failed: {exc}', file=sys.stderr)
                return 1
            print(f'  OK: POC scope consistent (horizon={poc_binding.headline_horizon_hours}h, '
                  f'ensemble={poc_binding.ensemble_members}, region={poc_binding.region_key})')
    except (OSError, RuntimeError, UnsafePathError, ReleaseSemanticsError) as exc:
        print(f'ERROR: release semantics manifest rejected: {exc}', file=sys.stderr)
        return 1
    try:
        validate_output_bundle_path(
            output_bundle,
            approved_root,
            create_approved_root=not dry_run,
        )
    except (OSError, RuntimeError, UnsafePathError) as exc:
        print(f'ERROR: unsafe output bundle path: {exc}', file=sys.stderr)
        return 1

    # G7: Dry-run mode must NOT produce a release bundle.
    if dry_run:
        print('ERROR: Dry-run mode cannot produce a release bundle. '
              'Use --dry-run only for validation, not release.', file=sys.stderr)
        return 1

    staging_bundle: Path | None = None
    published = False  # C0.29: Track publication state explicitly
    try:
        _, staging_bundle = create_staging_directory(output_bundle, approved_root)
    except (OSError, RuntimeError, UnsafePathError) as exc:
        print(f'ERROR: cannot create safe staging directory: {exc}', file=sys.stderr)
        return 1

    # C0-S3: Native output goes INSIDE the staging bundle.
    native_output_dir = staging_bundle / 'native-output'

    def _cleanup_staging() -> None:
        """C0.29: Clean up staging directory with explicit error reporting."""
        if staging_bundle is not None and not published:
            try:
                safe_remove_directory(staging_bundle, approved_root)
            except (OSError, RuntimeError, UnsafePathError) as cleanup_exc:
                # C0.29: Report cleanup errors instead of silently swallowing them
                print(
                    f'WARNING: staging cleanup failed for {staging_bundle}: {cleanup_exc}',
                    file=sys.stderr,
                )

    # C0.29: Wrap ALL post-staging orchestration in try/except/finally.
    # This ensures that any exception (runner, JSON write, gate, publication)
    # cleans up the staging directory and returns nonzero.
    try:
        native_output_dir.mkdir(parents=True, exist_ok=True)
        input_bundle_dir = staging_bundle / 'input-manifests'
        input_bundle_dir.mkdir(parents=True, exist_ok=True)
        approved_inputs: dict[str, dict[str, Any]] = {}
        for kind, record in (('forcing', forcing_record), ('geometry', geometry_record)):
            manifest_bytes = Path(record['resolved_manifest_path']).read_bytes()
            payload_bytes = Path(record['resolved_payload_path']).read_bytes()
            manifest_name = f'{kind}-manifest.json'
            payload_name = f'{kind}-payload.json'
            (input_bundle_dir / manifest_name).write_bytes(manifest_bytes)
            (input_bundle_dir / payload_name).write_bytes(payload_bytes)
            approved_inputs[kind] = {
                'manifest_id': record['id'],
                'manifest_path': f'input-manifests/{manifest_name}',
                'payload_path': f'input-manifests/{payload_name}',
                'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                'payload_sha256': hashlib.sha256(payload_bytes).hexdigest(),
            }
            if kind == 'forcing':
                contract_files: dict[str, dict[str, str]] = {}
                for contract_name in ('mapping_contract', 'meteoio_policy'):
                    source_path_value = record.get(f'resolved_{contract_name}_path')
                    source_hash = record.get(f'{contract_name}_sha256')
                    if not source_path_value and not source_hash:
                        continue
                    if not source_path_value or not source_hash:
                        print(
                            f'ERROR: forcing {contract_name} path/hash is incomplete',
                            file=sys.stderr,
                        )
                        return 1
                    source_path = Path(source_path_value)
                    if source_path.is_symlink() or not source_path.is_file():
                        print(
                            f'ERROR: forcing {contract_name} is not a regular file',
                            file=sys.stderr,
                        )
                        return 1
                    contract_bytes = source_path.read_bytes()
                    actual_contract_hash = hashlib.sha256(contract_bytes).hexdigest()
                    if actual_contract_hash != source_hash:
                        print(
                            f'ERROR: forcing {contract_name} hash changed before bundling',
                            file=sys.stderr,
                        )
                        return 1
                    contract_relative = (
                        f'input-manifests/forcing-contracts/{contract_name}.json'
                    )
                    contract_target = staging_bundle / contract_relative
                    contract_target.parent.mkdir(parents=True, exist_ok=True)
                    contract_target.write_bytes(contract_bytes)
                    contract_files[contract_name] = {
                        'path': contract_relative,
                        'sha256': actual_contract_hash,
                    }
                if contract_files:
                    approved_inputs[kind]['contract_files'] = contract_files

        # Copy state/forecast contracts into the bundle and bind their exact
        # bytes from result.json. Profile payloads are copied beneath the
        # input-manifests tree; no source-machine absolute path is released.
        bundle_state = initial_state
        state_payload_descriptor: dict[str, str] = {}
        if initial_state.state_type == 'profile':
            state_source_path = Path(initial_state.state_file_path)
            if not state_source_path.is_absolute():
                state_source_path = initial_state_source.parent / state_source_path
            state_payload_source = ensure_safe_file(state_source_path)
            state_suffix = state_source_path.suffix.lower()
            if state_suffix not in {'.caaml', '.smet', '.sno', '.snoold'}:
                print(
                    f'ERROR: unsupported profile initial-state suffix {state_suffix!r}; '
                    'expected .caaml, .smet, .sno, or .snoold.',
                    file=sys.stderr,
                )
                return 1
            state_payload_relative = (
                'input-manifests/initial-state-payload/'
                f'initial-state-profile{state_suffix}'
            )
            state_payload_path = staging_bundle / state_payload_relative
            state_payload_path.parent.mkdir(parents=True, exist_ok=True)
            state_payload_path.write_bytes(state_payload_source.read_bytes())
            bundle_state = replace(initial_state, state_file_path=state_payload_relative)
            state_payload_descriptor = {
                'payload_path': state_payload_relative,
                'payload_sha256': hashlib.sha256(state_payload_path.read_bytes()).hexdigest(),
            }
        validate_initial_state_binding(
            bundle_state,
            bundle_root=staging_bundle if bundle_state.state_type == 'profile' else None,
            payload_path=(staging_bundle / state_payload_descriptor['payload_path'])
            if state_payload_descriptor else None,
        )
        state_manifest_bytes = json.dumps(
            initial_state_envelope(bundle_state), sort_keys=True, indent=2,
        ).encode('utf-8')
        forecast_manifest_bytes = json.dumps(
            forecast_semantics_envelope(forecast_semantics), sort_keys=True, indent=2,
        ).encode('utf-8')
        state_manifest_relative = 'input-manifests/initial-state.json'
        forecast_manifest_relative = 'input-manifests/forecast-semantics.json'
        (input_bundle_dir / 'initial-state.json').write_bytes(state_manifest_bytes)
        (input_bundle_dir / 'forecast-semantics.json').write_bytes(forecast_manifest_bytes)
        release_semantics = {
            'initial_state': {
                'manifest_path': state_manifest_relative,
                'manifest_sha256': hashlib.sha256(state_manifest_bytes).hexdigest(),
                'state_id': bundle_state.state_id,
                'state_sha256': bundle_state.state_sha256,
                **state_payload_descriptor,
            },
            'forecast_semantics': {
                'manifest_path': forecast_manifest_relative,
                'manifest_sha256': hashlib.sha256(forecast_manifest_bytes).hexdigest(),
                'forcing_manifest_id': forecast_semantics.forcing_manifest_id,
            },
        }
        registry_source = Path(manifest_registry_path or DEFAULT_REGISTRY_PATH)
        registry_source_bytes = registry_source.read_bytes()
        # G3/G4: Copy the decision record bytes into the bundle so the
        # downloaded gate can hash them independently against an externally
        # supplied expected_decision_record_sha256.
        if decision_record_path is not None:
            decision_record_dir = staging_bundle / 'decision-record'
            decision_record_dir.mkdir(parents=True, exist_ok=True)
            decision_record_bytes = Path(decision_record_path).read_bytes()
            (decision_record_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json').write_bytes(
                decision_record_bytes
            )
            decision_hash_path = decision_record_dir / 'decision-record.sha256'
            decision_hash_path.write_text(
                hashlib.sha256(decision_record_bytes).hexdigest() + '\n',
                encoding='utf-8',
            )
        # R1.1: Copy the exact approved registry bytes into the bundle so the
        # downloaded gate can hash them independently against an externally
        # supplied expected_registry_sha256. The snapshot's registry_sha256
        # claim is not a trust anchor; the actual bytes are.
        registry_bundle_path = input_bundle_dir / 'approval-registry.json'
        registry_bundle_path.write_bytes(registry_source_bytes)
        snapshot_records = {}
        for kind, record in (
            ('forcing', forcing_record),
            ('geometry', geometry_record),
            ('toolchain', toolchain_record),
        ):
            snapshot_record = {
                key: value for key, value in record.items()
                if not key.startswith('resolved_')
            }
            # R1: snapshot records bind the approved registry record to the
            # exact bytes copied into the release bundle. These are not merely
            # identity echoes.
            snapshot_record['source_registry_version'] = 'snowpack_manifest_registry_v1'
            snapshot_record['manifest_sha256'] = record.get('content_sha256', '')
            if kind in {'forcing', 'geometry'}:
                snapshot_record['payload_sha256'] = record.get('payload_sha256', '')
                snapshot_record['bundle_manifest_path'] = approved_inputs[kind]['manifest_path']
                snapshot_record['bundle_payload_path'] = approved_inputs[kind]['payload_path']
            snapshot_records[kind] = snapshot_record
        snapshot = {
            'schema_version': 'snowpack_approval_snapshot_v1',
            'source_registry_version': 'snowpack_manifest_registry_v1',
            'registry_sha256': hashlib.sha256(registry_source_bytes).hexdigest(),
            'registry_bundle_path': 'input-manifests/approval-registry.json',
            'records': snapshot_records,
        }
        snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode()
        snapshot_path = input_bundle_dir / 'approval-registry-snapshot.json'
        snapshot_path.write_bytes(snapshot_bytes)
        registry_snapshot = {
            'path': 'input-manifests/approval-registry-snapshot.json',
            'sha256': hashlib.sha256(snapshot_bytes).hexdigest(),
            'registry_sha256': snapshot['registry_sha256'],
            'registry_bundle_path': 'input-manifests/approval-registry.json',
        }

        # Load region
        regions = load_regions()
        region = next((r for r in regions if r.key == region_key), None)
        if region is None:
            print(f'ERROR: Region "{region_key}" not found', file=sys.stderr)
            return 1

        # C0-S4: One run_id across all layers
        result = run_awsome_for_region(
            region=region,
            as_of=datetime.fromisoformat(
                forecast_semantics.valid_to.replace('Z', '+00:00')
            ).astimezone(timezone.utc),
            dry_run=False,  # G7: Never dry-run in release mode
            output_dir=native_output_dir,
            elevation_band=elevation_band,
            no_fallback=True,  # C0-S7: acceptance mode
            toolchain_manifest_id=toolchain_id,
            forcing_manifest_id=forcing_id,
            geometry_manifest_id=geometry_id,
            approved_forcing_manifest=forcing_record,
            approved_geometry_manifest=geometry_record,
            run_id=run_id,
            engine=engine,
            initial_state_contract=bundle_state,
            forecast_semantics_contract=forecast_semantics,
            initial_state_path=(
                staging_bundle / state_payload_descriptor['payload_path']
                if state_payload_descriptor else None
            ),
        )

        # G5: Check status BEFORE writing bundle — don't write incomplete bundles
        if result['status'] != 'completed':
            # Preserve enough structured evidence in the CI log to diagnose a
            # native-output contract failure after staging cleanup.  The
            # incomplete bundle is still never published, and subprocess
            # streams remain represented only by their hashes here.
            execution_evidence = result.get('execution_evidence') or {}
            manifest = result.get('manifest') or {}
            print(
                'NATIVE_RESULT_DIAGNOSTICS='
                + json.dumps(
                    {
                        'status': result.get('status'),
                        'method': result.get('method'),
                        'error': result.get('error'),
                        'missing_outputs': result.get('missing_outputs', []),
                        'manifest_errors': result.get('manifest_errors', []),
                        'artifacts': result.get('artifacts', []),
                        'manifest_artifacts': [
                            {
                                'file_path': artifact.get('file_path'),
                                'file_type': artifact.get('file_type'),
                                'role': artifact.get('role'),
                                'size_bytes': artifact.get('size_bytes'),
                            }
                            for artifact in manifest.get('artifacts', [])
                            if isinstance(artifact, dict)
                        ],
                        'execution': {
                            key: execution_evidence.get(key)
                            for key in (
                                'exit_code',
                                'version_exit_code',
                                'version_verified',
                                'binary_sha256',
                                'binary_version',
                                'toolchain_manifest_verified',
                                'toolchain_manifest_sha256',
                                'pro_path',
                                'log_path',
                            )
                        },
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            print(
                f'ERROR: Status is "{result["status"]}" (must be completed). '
                f'Bundle NOT written — no incomplete artifacts on disk.',
                file=sys.stderr,
            )
            return 1

        if 'manifest' not in result:
            print('ERROR: No manifest in result — cannot write manifest.json', file=sys.stderr)
            return 1
        result['approved_inputs'] = approved_inputs
        result['registry_snapshot'] = registry_snapshot
        result.update(release_semantics)
        # P1-10: Add explicit scope_mode to result.json so the consumer gate
        # can verify the bundle was produced in the same mode it's checking.
        result['scope_mode'] = 'poc' if effective_poc_mode else 'non_poc'
        # C0.8: Ensure explicit top-level region_key and elevation_band in
        # result.json. The runner may use 'region' but the POC scope validator
        # requires 'region_key'. Set both to be unambiguous.
        result['region_key'] = region_key
        result['elevation_band'] = elevation_band
        if decision_record_binding is not None:
            result['decision_record'] = decision_record_binding

        # Write result.json
        with open(staging_bundle / 'result.json', 'w') as f:
            json.dump(result, f, indent=2)

        # Write manifest.json with RELATIVE paths
        manifest_data = result['manifest']
        # C0-S3: Rebase paths to be relative to bundle root
        # G5: _rebase_manifest_paths_to_relative now returns None on external paths
        manifest_data = _rebase_manifest_paths_to_relative(
            manifest_data, staging_bundle, native_output_dir,
        )
        if manifest_data is None:
            print('ERROR: Manifest rebasing failed — external artifact paths rejected.',
                  file=sys.stderr)
            return 1
        with open(staging_bundle / 'manifest.json', 'w') as f:
            json.dump(manifest_data, f, indent=2)

        # Write invocation.json from real execution evidence
        evidence = result.get('execution_evidence')
        if evidence:
            invocation = {
                'binary_path': evidence['binary_path'],
                'binary_sha256': evidence['binary_sha256'],
                'binary_version': evidence['binary_version'],
                'command': evidence['command'],
                'command_sha256': evidence['command_sha256'],
                'exit_code': evidence['exit_code'],
                'started_at': evidence['started_at'],
                'finished_at': evidence['finished_at'],
                'toolchain_id': evidence['toolchain_id'],
                'run_id': evidence['run_id'],
                'stdout_sha256': evidence.get('stdout_sha256', ''),
                'stderr_sha256': evidence.get('stderr_sha256', ''),
                'version_exit_code': evidence.get('version_exit_code', -1),
                'version_verified': evidence.get('version_verified', False),
                'toolchain_manifest_sha256': evidence.get('toolchain_manifest_sha256', ''),
                'toolchain_manifest_verified': evidence.get('toolchain_manifest_verified', False),
                'image_id': evidence.get('image_id', ''),
                'image_archive_sha256': evidence.get('image_archive_sha256', ''),
                'image_repository_digest': evidence.get('image_repository_digest', ''),
                'image_identity_source': evidence.get('image_identity_source', ''),
                'log_path': evidence.get('log_path', ''),
                'interpreter_path': evidence.get('interpreter_path', ''),
                'interpreter_sha256': evidence.get('interpreter_sha256', ''),
            }
        else:
            # C0-S5: No evidence — fail closed
            invocation = {
                'binary_path': '', 'binary_sha256': '', 'binary_version': '',
                'command': '', 'command_sha256': '',
                'exit_code': -1,
                'version_exit_code': -1,
                'version_verified': False,
                'toolchain_manifest_sha256': '',
                'toolchain_manifest_verified': False,
                'image_id': '',
                'image_archive_sha256': '',
                'image_repository_digest': '',
                'image_identity_source': '',
                'started_at': '', 'finished_at': '',
                'toolchain_id': toolchain_id, 'run_id': run_id,
            }
        if not invocation.get('interpreter_sha256'):
            invocation.pop('interpreter_path', None)
            invocation.pop('interpreter_sha256', None)
        with open(staging_bundle / 'invocation.json', 'w') as f:
            json.dump(invocation, f, indent=2)

        # C0.31: The runtime toolchain manifest is mandatory for release.
        # No inferred/reconstructed manifest is acceptable.
        toolchain_manifest_data = evidence.get('toolchain_manifest') if evidence else None
        if not evidence or evidence.get('toolchain_manifest_verified') is not True:
            print(
                'ERROR: runtime toolchain manifest was not independently verified; '
                'release publication is blocked.',
                file=sys.stderr,
            )
            return 1
        if not isinstance(toolchain_manifest_data, dict):
            print('ERROR: runtime toolchain manifest is missing or not an object.', file=sys.stderr)
            return 1
        with open(staging_bundle / 'toolchain-manifest.json', 'w') as f:
            json.dump(toolchain_manifest_data, f, indent=2, sort_keys=True)

        # Bind the snapshot to the exact runtime toolchain-manifest bytes after
        # that file exists. Rewrite result.json so the snapshot hash remains a
        # hash of the final bundled snapshot, not a pre-execution placeholder.
        actual_toolchain_hash = hashlib.sha256(
            json.dumps(toolchain_manifest_data, indent=2, sort_keys=True).encode('utf-8')
        ).hexdigest()
        # G-R1.1.2: The registry is frozen BEFORE execution and must NOT be
        # mutated post-approval. The snapshot's toolchain manifest_sha256
        # remains the approved registry hash (content_sha256). The runtime
        # toolchain manifest hash is recorded separately as
        # toolchain_manifest_sha256 for the gate's runtime binding check.
        # If the runtime hash differs from the approved hash, the gate will
        # fail — which is the correct behavior.
        snapshot['records']['toolchain']['toolchain_manifest_sha256'] = actual_toolchain_hash
        # The manifest_sha256 stays as the approved content_sha256 (set earlier)
        registry_bundle_file = input_bundle_dir / 'approval-registry.json'
        frozen_registry_bytes = registry_bundle_file.read_bytes()
        frozen_registry_sha256 = hashlib.sha256(frozen_registry_bytes).hexdigest()
        snapshot['registry_sha256'] = frozen_registry_sha256
        snapshot_bytes = json.dumps(snapshot, sort_keys=True, indent=2).encode('utf-8')
        snapshot_path.write_bytes(snapshot_bytes)
        registry_snapshot = {
            'path': 'input-manifests/approval-registry-snapshot.json',
            'sha256': hashlib.sha256(snapshot_bytes).hexdigest(),
            'registry_sha256': frozen_registry_sha256,
            'registry_bundle_path': 'input-manifests/approval-registry.json',
        }
        result['registry_snapshot'] = registry_snapshot
        with open(staging_bundle / 'result.json', 'w') as f:
            json.dump(result, f, indent=2)

        print(f'\nStaged bundle: {staging_bundle}')
        print(f'  result.json: {(staging_bundle / "result.json").exists()}')
        print(f'  manifest.json: {(staging_bundle / "manifest.json").exists()}')
        print(f'  invocation.json: {(staging_bundle / "invocation.json").exists()}')
        print(f'  native-output/: {native_output_dir.exists()}')

        # G7: Invoke the release gate before claiming success
        # The producer must not claim a valid release bundle without self-verification
        # P0-1: Pass POC arguments to the self-gate so it validates the same
        # decision record and POC scope that the consumer gate will check.
        print('\n--- Producer self-verification: invoking release gate ---')
        from backend.scripts.release_gate import run_release_gate
        producer_poc_mode = effective_poc_mode
        gate_exit = run_release_gate(
            staging_bundle,
            expected_run_id=run_id,
            expected_registry_sha256=expected_registry_sha256,
            expected_decision_record_sha256=(
                expected_decision_record_sha256 if producer_poc_mode else ''
            ),
            poc_mode=producer_poc_mode,
        )
        if gate_exit != 0:
            print(
                f'ERROR: Release gate rejected the produced bundle (exit={gate_exit}). '
                f'Bundle is invalid — cannot claim release success.',
                file=sys.stderr,
            )
            return 1
        print('  OK: Release gate validated the staged bundle')

        try:
            published_bundle = publish_staging_directory(
                staging_bundle, output_bundle, approved_root
            )
            published = True  # C0.29: Mark as published so finally won't delete it
        except (OSError, RuntimeError, UnsafePathError) as exc:
            print(f'ERROR: atomic bundle publication failed: {exc}', file=sys.stderr)
            return 1
        print(f'Bundle published to: {published_bundle}')
        return 0
    except Exception as exc:
        # C0.29: Any unexpected exception must return nonzero with no silent residue
        print(
            f'ERROR: release orchestration failed with exception: '
            f'{type(exc).__name__}: {exc}',
            file=sys.stderr,
        )
        return 1
    finally:
        # C0.29: Always clean up staging unless it was successfully published.
        # A published bundle must NEVER be deleted by cleanup.
        _cleanup_staging()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='SNOWPACK release orchestrator — produces release bundles.'
    )
    parser.add_argument('--region', required=True, help='Region key')
    parser.add_argument('--elevation-band', required=True, help='Elevation band')
    parser.add_argument('--run-id', required=True, help='Explicit run ID')
    parser.add_argument('--toolchain-id', required=True, help='Toolchain manifest ID')
    parser.add_argument('--forcing-id', required=True, help='Forcing manifest ID')
    parser.add_argument('--geometry-id', required=True, help='Geometry manifest ID')
    parser.add_argument('--initial-state-manifest', required=True,
                        help='Initial snow/soil state contract JSON')
    parser.add_argument('--forecast-semantics-manifest', required=True,
                        help='Forecast cycle/window/member contract JSON')
    parser.add_argument('--engine', required=True, choices=('snowpack_direct', 'awsome'),
                        help='Single release engine; engine switching is forbidden')
    parser.add_argument('--manifest-registry', type=Path,
                        help='Approved SNOWPACK manifest registry JSON')
    parser.add_argument('--expected-registry-sha256', required=True,
                        help='Externally supplied SHA-256 of the approved registry bytes')
    parser.add_argument('--decision-record-path', type=Path, default=None,
                        help='Path to the Pir Panjal POC decision record JSON')
    parser.add_argument('--expected-decision-record-sha256', default='',
                        help='Externally supplied SHA-256 of the decision record bytes')
    parser.add_argument('--poc-mode', action='store_true', default=None,
                        help='Explicit POC mode flag. When set, decision-record-path and '
                             '--expected-decision-record-sha256 are both required. When not set, '
                             'POC mode is inferred from decision-record-path presence.')
    parser.add_argument('--output-bundle', required=True, type=Path, help='Bundle output directory')
    parser.add_argument('--dry-run', action='store_true', help='Validate without executing')
    args = parser.parse_args()

    return run_release_orchestration(
        region_key=args.region,
        elevation_band=args.elevation_band,
        run_id=args.run_id,
        toolchain_id=args.toolchain_id,
        forcing_id=args.forcing_id,
        geometry_id=args.geometry_id,
        initial_state_manifest_path=args.initial_state_manifest,
        forecast_semantics_manifest_path=args.forecast_semantics_manifest,
        engine=args.engine,
        output_bundle=args.output_bundle,
        dry_run=args.dry_run,
        manifest_registry_path=args.manifest_registry,
        expected_registry_sha256=args.expected_registry_sha256,
        decision_record_path=args.decision_record_path,
        expected_decision_record_sha256=args.expected_decision_record_sha256,
        poc_mode=args.poc_mode,
    )


if __name__ == '__main__':
    sys.exit(main())
