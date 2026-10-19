"""Release gate CLI for SNOWPACK native execution (Phase 0.5 P0.8).

This is the REAL release gate. It calls:
  - validate_completed() to check all completed-status requirements
  - verify_manifest_against_directory() to verify hashes against actual files
  - run_id match between result JSON and manifest

CRITICAL SECURITY RULES (learned from Codex audit):
  1. NEVER recompute expected hashes. When rebasing paths, PRESERVE the original
     sha256 and size_bytes from the manifest. Recomputing would replace the
     integrity check with the tampered value.
  2. Only status == "completed" is releaseable. Use an allowlist, not a denylist.
  3. run_id is required. Never fall back to as_of or other fields.
  4. Require exactly one result.json and one manifest.json.
  5. Every manifest artifact must map one-to-one to a downloaded file.

Usage:
  python -m backend.scripts.release_gate --artifacts-dir <dir> \
    --expected-run-id <id> --expected-registry-sha256 <sha256>

Exit codes:
  0 = gate passed (release bundle contract, verified hashes, completed semantics)
  1 = gate failed (missing artifacts, hash mismatch, incomplete, stale, or cross-run)

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from datetime import datetime, timedelta
from typing import Any

from backend.common.snowpack_artifact_manifest import (
    ArtifactEntry,
    ArtifactManifest,
    compute_file_hash,
    verify_manifest_against_directory,
)
from backend.common.snowpack_paths import UnsafePathError, ensure_safe_file, ensure_safe_directory
from backend.common.snowpack_contracts import (
    validate_release_manifest_id,
    validate_release_run_id,
)
from backend.common.snowpack_release_semantics import (
    ReleaseSemanticsError,
    load_forecast_semantics_manifest,
    load_initial_state_manifest,
    validate_initial_state_binding,
    validate_release_semantics_context,
)
from backend.common.snowpack_toolchain_identity import is_real_image_id, is_real_sha256

# Only this status is releaseable. Allowlist, not denylist.
_RELEASEABLE_STATUS = 'completed'

# Required files in a release bundle
_REQUIRED_BUNDLE_FILES = ('result.json', 'manifest.json', 'invocation.json')
_SHA256_PATTERN = re.compile(r'^[0-9a-fA-F]{64}$')

# R1.1 cross-verification constants
_FIXED_REGISTRY_BUNDLE_PATH = 'input-manifests/approval-registry.json'
_SUPPORTED_REGISTRY_SCHEMAS = frozenset({'snowpack_manifest_registry_v1'})
_MAX_REGISTRY_BYTES = 1 * 1024 * 1024  # 1 MiB
_REQUIRED_REGISTRY_RECORD_FIELDS = frozenset({
    'id', 'kind', 'content_sha256', 'source', 'licence', 'units',
    'region', 'elevation_band', 'valid_from', 'valid_to', 'approval_state',
})
_APPROVAL_VALIDITY_FIELDS = ('approval_valid_from', 'approval_valid_to')

_RELEASE_ARTIFACT_ROLE_SUFFIXES = {
    'forcing_smet': '.smet',
    'processed_meteo': '.smet',
    'model_timeseries_smet': '.smet',
    'profile_pro': '.pro',
    'snow_profile_sno': '.sno',
    'hazard_haz': '.haz',
    'execution_log': '.log',
}


def _schema_string(data: dict[str, Any], field: str, errors: list[str], *, required: bool = True) -> None:
    value = data.get(field)
    if field not in data:
        if required:
            errors.append(f'{field} is required')
    elif not isinstance(value, str) or not value:
        errors.append(f'{field} must be a non-empty string')


def _schema_bool(data: dict[str, Any], field: str, errors: list[str], *, required: bool = True) -> None:
    if field not in data:
        if required:
            errors.append(f'{field} is required')
    elif type(data[field]) is not bool:
        errors.append(f'{field} must be a boolean')


def _schema_sha256(data: dict[str, Any], field: str, errors: list[str], *, required: bool = True) -> None:
    if field not in data:
        if required:
            errors.append(f'{field} is required')
    elif not isinstance(data[field], str) or not _SHA256_PATTERN.fullmatch(data[field]):
        errors.append(f'{field} must be a 64-character hexadecimal SHA-256 string')


def _validate_result_schema(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return [f'result.json root must be a JSON object, got {type(data).__name__}']
    errors: list[str] = []
    _schema_string(data, 'run_id', errors)
    _schema_string(data, 'status', errors)
    _schema_string(data, 'engine', errors)
    for field in ('toolchain_manifest_id', 'forcing_manifest_id', 'geometry_manifest_id'):
        _schema_string(data, field, errors)
    approved_inputs = data.get('approved_inputs')
    if not isinstance(approved_inputs, dict):
        errors.append('approved_inputs must be a JSON object')
    else:
        for kind in ('forcing', 'geometry'):
            entry = approved_inputs.get(kind)
            if not isinstance(entry, dict):
                errors.append(f'approved_inputs.{kind} must be a JSON object')
                continue
            for field in ('manifest_id', 'manifest_path', 'payload_path', 'manifest_sha256', 'payload_sha256'):
                if not isinstance(entry.get(field), str) or not entry[field]:
                    errors.append(f'approved_inputs.{kind}.{field} must be a non-empty string')
            for field in ('manifest_sha256', 'payload_sha256'):
                if isinstance(entry.get(field), str) and not _SHA256_PATTERN.fullmatch(entry[field]):
                    errors.append(f'approved_inputs.{kind}.{field} must be SHA-256')
            contract_files = entry.get('contract_files')
            if contract_files is not None:
                if not isinstance(contract_files, dict):
                    errors.append(f'approved_inputs.{kind}.contract_files must be a JSON object')
                else:
                    for contract_name, contract in contract_files.items():
                        if not isinstance(contract_name, str) or not isinstance(contract, dict):
                            errors.append(f'approved_inputs.{kind}.contract_files entries must be objects')
                            continue
                        if not isinstance(contract.get('path'), str) or not contract['path']:
                            errors.append(f'approved_inputs.{kind}.contract_files.{contract_name}.path is required')
                        if not isinstance(contract.get('sha256'), str) or not _SHA256_PATTERN.fullmatch(contract['sha256']):
                            errors.append(f'approved_inputs.{kind}.contract_files.{contract_name}.sha256 must be SHA-256')
    registry_snapshot = data.get('registry_snapshot')
    if not isinstance(registry_snapshot, dict):
        errors.append('registry_snapshot must be a JSON object')
    else:
        for field in ('path', 'sha256', 'registry_sha256', 'registry_bundle_path'):
            if not isinstance(registry_snapshot.get(field), str) or not registry_snapshot[field]:
                errors.append(f'registry_snapshot.{field} must be a non-empty string')
        for field in ('sha256', 'registry_sha256'):
            if isinstance(registry_snapshot.get(field), str) and not _SHA256_PATTERN.fullmatch(registry_snapshot[field]):
                errors.append(f'registry_snapshot.{field} must be SHA-256')
    _schema_bool(data, 'no_fallback', errors)
    for name in ('initial_state', 'forecast_semantics'):
        descriptor = data.get(name)
        if not isinstance(descriptor, dict):
            errors.append(f'{name} must be a JSON object')
            continue
        for field in ('manifest_path', 'manifest_sha256'):
            if not isinstance(descriptor.get(field), str) or not descriptor[field]:
                errors.append(f'{name}.{field} must be a non-empty string')
        if isinstance(descriptor.get('manifest_sha256'), str) and not _SHA256_PATTERN.fullmatch(
            descriptor['manifest_sha256']
        ):
            errors.append(f'{name}.manifest_sha256 must be SHA-256')
    state_descriptor = data.get('initial_state')
    if isinstance(state_descriptor, dict):
        for field in ('state_id', 'state_sha256'):
            if not isinstance(state_descriptor.get(field), str) or not state_descriptor[field]:
                errors.append(f'initial_state.{field} must be a non-empty string')
        if isinstance(state_descriptor.get('state_sha256'), str) and not _SHA256_PATTERN.fullmatch(
            state_descriptor['state_sha256']
        ):
            errors.append('initial_state.state_sha256 must be SHA-256')
        if 'payload_path' in state_descriptor:
            if not isinstance(state_descriptor.get('payload_path'), str) or not state_descriptor['payload_path']:
                errors.append('initial_state.payload_path must be a non-empty string')
            if not isinstance(state_descriptor.get('payload_sha256'), str) or not state_descriptor['payload_sha256']:
                errors.append('initial_state.payload_sha256 is required with payload_path')
            elif not _SHA256_PATTERN.fullmatch(state_descriptor['payload_sha256']):
                errors.append('initial_state.payload_sha256 must be SHA-256')
    forecast_descriptor = data.get('forecast_semantics')
    if isinstance(forecast_descriptor, dict):
        if not isinstance(forecast_descriptor.get('forcing_manifest_id'), str) or not forecast_descriptor['forcing_manifest_id']:
            errors.append('forecast_semantics.forcing_manifest_id must be a non-empty string')
    if 'native_binary_invoked' in data and type(data['native_binary_invoked']) is not bool:
        errors.append('native_binary_invoked must be a boolean')
    return errors


def _validate_manifest_schema(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return [f'manifest.json root must be a JSON object, got {type(data).__name__}']
    errors: list[str] = []
    for field in ('run_id', 'region_key', 'elevation_band', 'aspect_class', 'binary_version', 'created_at'):
        _schema_string(data, field, errors)
    _schema_bool(data, 'is_native_execution', errors)
    _schema_bool(data, 'native_binary_invoked', errors)
    for field in ('toolchain_id', 'forcing_manifest_id', 'geometry_manifest_id'):
        _schema_string(data, field, errors)
    artifacts = data.get('artifacts')
    if not isinstance(artifacts, list):
        errors.append('artifacts must be a JSON list')
        return errors
    for index, artifact in enumerate(artifacts):
        prefix = f'artifacts[{index}]'
        if not isinstance(artifact, dict):
            errors.append(f'{prefix} must be a JSON object')
            continue
        for field in ('file_path', 'file_type', 'sha256', 'role'):
            if field not in artifact or not isinstance(artifact[field], str) or not artifact[field]:
                errors.append(f'{prefix}.{field} must be a non-empty string')
        if 'sha256' in artifact and isinstance(artifact['sha256'], str) and not _SHA256_PATTERN.fullmatch(artifact['sha256']):
            errors.append(f'{prefix}.sha256 must be a 64-character hexadecimal SHA-256 string')
        if 'size_bytes' not in artifact or type(artifact.get('size_bytes')) is not int or artifact['size_bytes'] < 0:
            errors.append(f'{prefix}.size_bytes must be a non-negative integer')
        if 'is_critical' not in artifact or type(artifact.get('is_critical')) is not bool:
            errors.append(f'{prefix}.is_critical must be a boolean')
    return errors


def _validate_invocation_schema(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return [f'invocation.json root must be a JSON object, got {type(data).__name__}']
    errors: list[str] = []
    if 'image_digest' in data:
        errors.append(
            'image_digest is a deprecated ambiguous field; use image_id, '
            'image_archive_sha256, and image_repository_digest'
        )
    for field in ('binary_path', 'binary_version', 'command', 'started_at', 'finished_at', 'toolchain_id', 'run_id'):
        _schema_string(data, field, errors)
    for field in ('binary_sha256', 'command_sha256'):
        _schema_sha256(data, field, errors)
    if 'exit_code' not in data or type(data.get('exit_code')) is not int:
        errors.append('exit_code must be an integer')
    if 'version_exit_code' not in data or type(data.get('version_exit_code')) is not int:
        errors.append('version_exit_code must be an integer')
    _schema_bool(data, 'version_verified', errors)
    _schema_string(data, 'image_id', errors)
    _schema_sha256(data, 'image_archive_sha256', errors)
    if data.get('image_repository_digest') and (
        not isinstance(data['image_repository_digest'], str)
        or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', data['image_repository_digest'])
    ):
        errors.append('image_repository_digest must be empty or sha256:<64 hex>')
    _schema_string(data, 'image_identity_source', errors)
    for field in (
        'stdout_sha256', 'stderr_sha256', 'interpreter_sha256',
        'toolchain_manifest_sha256',
    ):
        if field in data and (
            not isinstance(data[field], str)
            or not _SHA256_PATTERN.fullmatch(data[field])
        ):
            errors.append(f'{field} must be a 64-character hexadecimal SHA-256 string')
    if 'toolchain_manifest_verified' not in data or type(data.get('toolchain_manifest_verified')) is not bool:
        errors.append('toolchain_manifest_verified must be a boolean')
    return errors


def _is_safe_bundle_file(path: Path, bundle_root: Path) -> bool:
    """C0-S10: Verify a file is a regular (non-symlink) file within the bundle.

    Uses Path.is_relative_to() for containment — never string prefix checks,
    which allow sibling-prefix escapes (e.g., /tmp/bundle_evil passes for
    /tmp/bundle).
    """
    try:
        ensure_safe_directory(bundle_root)
        ensure_safe_file(path, root=bundle_root)
        return True
    except (OSError, RuntimeError, UnsafePathError):
        return False


def _read_bundle_file_atomically(path: Path, bundle_root: Path) -> bytes | None:
    """Open and read a bundle file atomically with O_NOFOLLOW to prevent TOCTOU.

    G-R1.1.3: The symlink check and file read must be a single atomic
    operation. We open with O_NOFOLLOW (rejects symlinks), fstat to verify
    it's a regular file, then read from the same file descriptor.
    Returns None if the file is unsafe, a symlink, or outside the bundle.
    """
    import os
    try:
        ensure_safe_directory(bundle_root)
        ensure_safe_file(path, root=bundle_root)
    except (OSError, RuntimeError, UnsafePathError):
        return None
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        import stat
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        # Read in chunks to handle large files safely
        chunks: list[bytes] = []
        remaining = st.st_size
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)
    finally:
        os.close(fd)


def _bundle_input_file(relative: object, artifacts_dir: Path, label: str) -> Path | None:
    """Resolve one semantics input under input-manifests/ only."""
    if not isinstance(relative, str) or _validate_relative_path(relative) is None:
        print(f'ERROR: {label} path is not a safe relative POSIX path', file=sys.stderr)
        return None
    parts = PurePosixPath(relative).parts
    if len(parts) < 2 or parts[0] != 'input-manifests':
        print(f'ERROR: {label} path must be under input-manifests/', file=sys.stderr)
        return None
    candidate = artifacts_dir / relative
    if not _is_safe_bundle_file(candidate, artifacts_dir):
        print(f'ERROR: {label} is missing, unsafe, or symlinked', file=sys.stderr)
        return None
    return candidate


def _validate_release_semantics_bundle(
    result_data: dict[str, Any],
    manifest: ArtifactManifest,
    artifacts_dir: Path,
    run_id: str,
) -> list[str]:
    """Independently verify state/forecast manifests and their payload hashes."""
    errors: list[str] = []
    state_descriptor = result_data.get('initial_state')
    forecast_descriptor = result_data.get('forecast_semantics')
    if not isinstance(state_descriptor, dict) or not isinstance(forecast_descriptor, dict):
        return ['result.json must contain initial_state and forecast_semantics descriptors']

    state_path = _bundle_input_file(
        state_descriptor.get('manifest_path'), artifacts_dir, 'initial-state manifest'
    )
    forecast_path = _bundle_input_file(
        forecast_descriptor.get('manifest_path'), artifacts_dir, 'forecast-semantics manifest'
    )
    if state_path is None or forecast_path is None:
        return ['release semantics manifest path validation failed']

    try:
        if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_descriptor.get('manifest_sha256'):
            errors.append('initial-state manifest hash does not match result.json')
        if hashlib.sha256(forecast_path.read_bytes()).hexdigest() != forecast_descriptor.get('manifest_sha256'):
            errors.append('forecast-semantics manifest hash does not match result.json')
        state, _ = load_initial_state_manifest(state_path)
        forecast, _ = load_forecast_semantics_manifest(forecast_path)
        if state.state_id != state_descriptor.get('state_id'):
            errors.append('initial-state state_id does not match result.json')
        if state.state_sha256 != state_descriptor.get('state_sha256'):
            errors.append('initial-state state_sha256 does not match result.json')
        if forecast.forcing_manifest_id != forecast_descriptor.get('forcing_manifest_id'):
            errors.append('forecast-semantics forcing ID does not match result.json')
        payload_path: Path | None = None
        payload_relative = state_descriptor.get('payload_path')
        if state.state_type == 'profile':
            payload_path = _bundle_input_file(
                payload_relative, artifacts_dir, 'initial-state profile payload'
            )
            if payload_path is None:
                errors.append('profile initial state requires a safe bundled payload')
            elif state.state_file_path != payload_relative:
                errors.append('initial-state profile path does not match result payload path')
            elif hashlib.sha256(payload_path.read_bytes()).hexdigest() != state_descriptor.get('payload_sha256'):
                errors.append('initial-state profile payload hash does not match result.json')
        elif payload_relative is not None:
            errors.append('snow_free initial state must not carry a profile payload')
        validate_initial_state_binding(state, bundle_root=artifacts_dir, payload_path=payload_path)
        validate_release_semantics_context(
            state=state,
            forecast=forecast,
            run_id=run_id,
            region_key=manifest.region_key,
            elevation_band=manifest.elevation_band,
            forcing_manifest_id=manifest.forcing_manifest_id,
        )
    except (OSError, RuntimeError, ReleaseSemanticsError, TypeError, ValueError) as exc:
        errors.append(f'release semantics validation failed: {exc}')
    return errors


def _load_result_json(artifacts_dir: Path) -> dict | None:
    """Load exactly one result.json file. Returns None on failure."""
    result_path = artifacts_dir / 'result.json'
    if not result_path.exists():
        print('ERROR: result.json not found in artifacts directory', file=sys.stderr)
        return None
    # C0-S10: Reject symlinked metadata files
    if not _is_safe_bundle_file(result_path, artifacts_dir):
        print('ERROR: result.json is a symlink or resolves outside the bundle', file=sys.stderr)
        return None
    # G1: Malformed JSON must fail closed, not crash
    # G4: Valid JSON of wrong type (list, string, null) must also fail closed
    try:
        with open(result_path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(
                f'ERROR: result.json root must be a JSON object, '
                f'got {type(data).__name__}.',
                file=sys.stderr,
            )
            return None
        return data
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, TypeError) as e:
        print(f'ERROR: result.json is malformed JSON: {e}', file=sys.stderr)
        return None


def _load_manifest(artifacts_dir: Path) -> tuple[dict, Path] | None:
    """Load exactly one manifest.json file. Returns None on failure."""
    manifest_path = artifacts_dir / 'manifest.json'
    if not manifest_path.exists():
        print('ERROR: manifest.json not found in artifacts directory', file=sys.stderr)
        return None
    # C0-S10: Reject symlinked metadata files
    if not _is_safe_bundle_file(manifest_path, artifacts_dir):
        print('ERROR: manifest.json is a symlink or resolves outside the bundle', file=sys.stderr)
        return None
    # G1: Malformed JSON must fail closed, not crash
    # G4: Valid JSON of wrong type (list, string, null) must also fail closed
    try:
        with open(manifest_path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(
                f'ERROR: manifest.json root must be a JSON object, '
                f'got {type(data).__name__}.',
                file=sys.stderr,
            )
            return None
        return data, manifest_path
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, TypeError) as e:
        print(f'ERROR: manifest.json is malformed JSON: {e}', file=sys.stderr)
        return None


def _load_invocation(artifacts_dir: Path) -> dict | None:
    """Load invocation.json (execution attestation). Returns None on failure."""
    invoc_path = artifacts_dir / 'invocation.json'
    if not invoc_path.exists():
        print('ERROR: invocation.json not found in artifacts directory', file=sys.stderr)
        return None
    # C0-S10: Reject symlinked metadata files
    if not _is_safe_bundle_file(invoc_path, artifacts_dir):
        print('ERROR: invocation.json is a symlink or resolves outside the bundle', file=sys.stderr)
        return None
    # G1: Malformed JSON must fail closed, not crash
    # G4: Valid JSON of wrong type (list, string, null) must also fail closed
    try:
        with open(invoc_path, encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(
                f'ERROR: invocation.json root must be a JSON object, '
                f'got {type(data).__name__}.',
                file=sys.stderr,
            )
            return None
        return data
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, TypeError) as e:
        print(f'ERROR: invocation.json is malformed JSON: {e}', file=sys.stderr)
        return None


def _validate_invocation(invocation: dict) -> list[str]:
    """Validate execution attestation contains required fields.

    C0-S6: Strict validation — not just field presence, but:
      - SHA-256 format (64 hex characters)
      - Timestamp ordering (started_at < finished_at)
      - Exit code must be 0
      - run_id binding (if present, must match)
      - G10: command_sha256 must match SHA-256 of command field
    """
    import hashlib
    import re

    errors: list[str] = []
    required_fields = (
        'binary_path',       # Resolved path to the SNOWPACK binary
        'binary_sha256',     # SHA-256 of the binary executable
        'binary_version',    # Version string from `snowpack --version`
        'command',           # Full command line
        'command_sha256',    # SHA-256 of the command string
        'exit_code',         # Process exit code (must be 0)
        'started_at',        # ISO 8601 timestamp
        'finished_at',       # ISO 8601 timestamp
        'toolchain_id',      # Toolchain manifest ID
        'run_id',            # Run ID binding (C0-S6)
        'toolchain_manifest_sha256',  # Hash of bundled runtime manifest
        'toolchain_manifest_verified',  # Independent runtime binding
        'image_id',  # Local Docker image ID from immutable preflight image
        'image_archive_sha256',  # SHA-256 of the transferred image archive
        'image_identity_source',
    )
    for field in required_fields:
        if field not in invocation:
            errors.append(f'invocation.json: missing required field "{field}"')
        elif not invocation[field] and invocation[field] != 0:
            errors.append(f'invocation.json: field "{field}" is empty')

    # Exit code must be 0
    if 'exit_code' in invocation and invocation['exit_code'] != 0:
        errors.append(
            f'invocation.json: exit_code is {invocation["exit_code"]} (must be 0)'
        )

    # C0.14: Successful native execution requires an independently successful version probe.
    if invocation.get('version_verified') is not True:
        errors.append('invocation.json: version_verified must be boolean True')
    if 'version_exit_code' in invocation and invocation['version_exit_code'] != 0:
        errors.append(
            f'invocation.json: version_exit_code is {invocation["version_exit_code"]} (must be 0)'
        )
    if invocation.get('toolchain_manifest_verified') is not True:
        errors.append('invocation.json: toolchain_manifest_verified must be boolean True')
    if not is_real_image_id(invocation.get('image_id')):
        errors.append('invocation.json: image_id must be a non-placeholder sha256:<64 hex>')
    if not is_real_sha256(invocation.get('image_archive_sha256')):
        errors.append('invocation.json: image_archive_sha256 must be non-placeholder 64 hex')
    if invocation.get('image_repository_digest') and not is_real_image_id(
        invocation['image_repository_digest']
    ):
        errors.append(
            'invocation.json: image_repository_digest must be empty or a '
            'non-placeholder sha256:<64 hex>'
        )
    if invocation.get('image_identity_source') not in {
        'local_id_and_archive', 'registry_digest_and_archive'
    }:
        errors.append(
            'invocation.json: image_identity_source must identify local/archive or registry/archive evidence'
        )

    # C0-S6: Validate SHA-256 format (64 hex characters)
    sha256_pattern = re.compile(r'^[0-9a-fA-F]{64}$')
    for hash_field in (
        'binary_sha256', 'command_sha256', 'toolchain_manifest_sha256'
    ):
        if hash_field in invocation and invocation[hash_field]:
            if not sha256_pattern.match(str(invocation[hash_field])):
                errors.append(
                    f'invocation.json: {hash_field} is not a valid SHA-256 '
                    f'(must be 64 hex characters)'
                )

    # G10: Verify command_sha256 matches actual SHA-256 of command field
    if 'command' in invocation and 'command_sha256' in invocation:
        if invocation['command'] and invocation['command_sha256']:
            actual_cmd_hash = hashlib.sha256(
                str(invocation['command']).encode()
            ).hexdigest()
            if actual_cmd_hash != invocation['command_sha256']:
                errors.append(
                    f'invocation.json: command_sha256 does not match SHA-256 of '
                    f'command field (expected {actual_cmd_hash[:16]}..., '
                    f'got {str(invocation["command_sha256"])[:16]}...)'
                )

    # C0-S6: Validate timestamp ordering (started_at < finished_at)
    if 'started_at' in invocation and 'finished_at' in invocation:
        try:
            started = datetime.fromisoformat(str(invocation['started_at']))
            finished = datetime.fromisoformat(str(invocation['finished_at']))
            for field, value, parsed in (
                ('started_at', invocation['started_at'], started),
                ('finished_at', invocation['finished_at'], finished),
            ):
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    errors.append(
                        f'invocation.json: {field} must be timezone-aware UTC ISO-8601 '
                        f'(got {value!r})'
                    )
                elif parsed.utcoffset() != timedelta(0):
                    errors.append(
                        f'invocation.json: {field} must use UTC offset +00:00 '
                        f'(got {value!r})'
                    )
            if started >= finished:
                errors.append(
                    f'invocation.json: started_at ({invocation["started_at"]}) '
                    f'must be before finished_at ({invocation["finished_at"]})'
                )
        except (ValueError, TypeError) as e:
            errors.append(f'invocation.json: invalid timestamp format: {e}')

    return errors


def _validate_relative_path(path_str: str) -> str | None:
    """Validate that a manifest path is a safe relative POSIX path.

    Returns the cleaned path string if valid, None if invalid.
    Rejects: absolute paths, .., backslashes, null bytes, drive prefixes,
    empty paths.
    """
    if not path_str or not isinstance(path_str, str):
        return None
    # Reject null bytes
    if '\x00' in path_str:
        return None
    # Reject backslashes (Windows path separator — not allowed in POSIX bundles)
    if '\\' in path_str:
        return None
    # Reject absolute paths using Path semantics plus explicit Windows-drive
    # validation because this process may run on POSIX while validating a
    # cross-platform bundle.
    try:
        if Path(path_str).is_absolute():
            return None
    except (TypeError, ValueError):
        return None
    if len(path_str) >= 2 and path_str[1] == ':':
        return None  # Windows drive prefix (e.g., C:)
    if PureWindowsPath(path_str).is_absolute():
        return None
    # Reject any path component that is '..' — lexical traversal check
    parts = path_str.replace('\\', '/').split('/')
    if '..' in parts:
        return None
    # Reject empty components (e.g., 'a//b')
    if any(not p for p in parts):
        return None
    return path_str


def _check_no_symlinks_in_chain(path: Path, root: Path) -> bool:
    """Check that no component in the path chain (from root to path) is a symlink.

    Returns True if safe (no symlinks), False if any symlink found.
    """
    try:
        # Check the path itself
        if path.is_symlink():
            return False
        # Check each parent directory up to (but not including) root
        current = path.parent
        root_resolved = root.resolve()
        while current != current.parent:  # stop at filesystem root
            if current == root:
                break
            if current.is_symlink():
                return False
            current = current.parent
    except (OSError, RuntimeError):
        return False
    return True


def _rebase_artifact_paths(
    artifacts: tuple[ArtifactEntry, ...],
    artifacts_dir: Path,
) -> tuple[ArtifactEntry, ...] | None:
    """Rebase manifest paths to the downloaded artifact directory.

    SIXTH-PASS SECURITY RULES (no fallbacks, no basename recovery):
      1. Every manifest path MUST be relative, POSIX-normalized, nonempty.
         Reject absolute paths, .., backslashes, null bytes, drive prefixes.
      2. Map EXACTLY: bundle_root / relative_path. No basename recovery.
         No recursive search. No fallback. If the path doesn't exist, FAIL.
      3. Reject symlinks on the original path AND every parent directory.
      4. PRESERVE the original sha256 and size_bytes from the manifest.
         NEVER recompute expected hashes.
      5. After resolution, verify the resolved path is still within the bundle.

    Returns None if any artifact cannot be safely located (fail closed).
    """
    rebased: list[ArtifactEntry] = []
    artifacts_dir_resolved = artifacts_dir.resolve()
    seen_roles: set[str] = set()

    for art in artifacts:
        original_str = art.file_path

        # G1/G2: Lexical validation — reject traversal, absolute, backslash, null
        cleaned = _validate_relative_path(original_str)
        if cleaned is None:
            print(
                f'ERROR: Manifest path "{original_str}" is not a valid relative '
                f'POSIX path. Rejecting: absolute, "..", backslash, null byte, '
                f'or drive prefix paths are not allowed.',
                file=sys.stderr,
            )
            return None

        # R2: native semantic artifacts belong only to the native-output tree.
        # Input manifests and arbitrary bundle files must never satisfy the
        # native-output release contract, even when their suffixes look valid.
        parts = cleaned.split('/')
        if not parts or parts[0] != 'native-output' or len(parts) < 2:
            print(
                f'ERROR: semantic artifact path "{original_str}" must be a '
                f'relative file under native-output/.',
                file=sys.stderr,
            )
            return None
        if art.role not in _RELEASE_ARTIFACT_ROLE_SUFFIXES:
            print(
                f'ERROR: unsupported semantic artifact role {art.role!r}.',
                file=sys.stderr,
            )
            return None
        if art.role in seen_roles:
            print(
                f'ERROR: duplicate semantic artifact role {art.role!r}. '
                f'Each release role must map to exactly one native output.',
                file=sys.stderr,
            )
            return None
        expected_suffix = _RELEASE_ARTIFACT_ROLE_SUFFIXES[art.role]
        if art.file_type != expected_suffix or not cleaned.endswith(expected_suffix):
            print(
                f'ERROR: role {art.role!r} must map to a {expected_suffix} '
                f'file under native-output/.',
                file=sys.stderr,
            )
            return None
        seen_roles.add(art.role)

        # Map exactly: bundle_root / relative_path
        candidate = artifacts_dir / cleaned

        # G3: Check for symlinks in the entire path chain BEFORE resolving
        if not _check_no_symlinks_in_chain(candidate, artifacts_dir):
            print(
                f'ERROR: Path "{candidate}" or one of its parent directories '
                f'is a symlink. Symlinks are not allowed in release bundles.',
                file=sys.stderr,
            )
            return None

        # File must exist
        if not candidate.exists():
            print(
                f'ERROR: Artifact "{cleaned}" not found within bundle directory '
                f'{artifacts_dir}. External and traversal paths are rejected. '
                f'No basename fallback — manifest paths must be exact.',
                file=sys.stderr,
            )
            return None

        # Must be a regular file (not directory, not symlink, not special)
        if not candidate.is_file():
            print(
                f'ERROR: Artifact "{cleaned}" is not a regular file.',
                file=sys.stderr,
            )
            return None

        # G2: After resolution, verify containment (defense in depth)
        try:
            candidate_resolved = candidate.resolve()
            if not candidate_resolved.is_relative_to(artifacts_dir_resolved):
                print(
                    f'ERROR: Path "{candidate}" resolves outside the bundle '
                    f'directory. Possible symlink escape.',
                    file=sys.stderr,
                )
                return None
        except (OSError, RuntimeError) as e:
            print(f'ERROR: Cannot resolve path "{candidate}": {e}', file=sys.stderr)
            return None

        rebased.append(ArtifactEntry(
            file_path=str(candidate),
            file_type=art.file_type,
            size_bytes=art.size_bytes,      # PRESERVED from manifest
            sha256=art.sha256,              # PRESERVED from manifest
            is_critical=art.is_critical,
            role=art.role,
        ))

    required_release_roles = {
        'forcing_smet', 'processed_meteo', 'profile_pro',
        'snow_profile_sno', 'hazard_haz', 'execution_log',
    }
    missing_roles = required_release_roles - seen_roles
    if missing_roles:
        print(
            f'ERROR: release manifest is missing semantic artifact roles: '
            f'{sorted(missing_roles)}.',
            file=sys.stderr,
        )
        return None

    return tuple(rebased)


def _reconstruct_manifest(data: Any) -> ArtifactManifest | None:
    """Reconstruct an ArtifactManifest from JSON data.

    G4: Returns None on any type or schema error instead of raising.
    The caller must check for None and fail closed.
    """
    if not isinstance(data, dict):
        print(
            f'ERROR: manifest.json root must be a JSON object, got {type(data).__name__}.',
            file=sys.stderr,
        )
        return None
    try:
        artifacts_list = data.get('artifacts', [])
        if not isinstance(artifacts_list, list):
            print(
                f'ERROR: manifest.json "artifacts" must be a list, '
                f'got {type(artifacts_list).__name__}.',
                file=sys.stderr,
            )
            return None
        artifacts = tuple(
            ArtifactEntry(
                file_path=a['file_path'],
                file_type=a['file_type'],
                size_bytes=a['size_bytes'],
                sha256=a['sha256'],
                is_critical=a['is_critical'],
                role=a['role'],
            )
            for a in artifacts_list
        )
        return ArtifactManifest(
            run_id=data['run_id'],
            region_key=data['region_key'],
            elevation_band=data['elevation_band'],
            aspect_class=data['aspect_class'],
            binary_version=data['binary_version'],
            artifacts=artifacts,
        is_native_execution=data['is_native_execution'],
        native_binary_invoked=data.get('native_binary_invoked', False),
        created_at=data['created_at'],
        toolchain_id=data.get('toolchain_id', ''),
        forcing_manifest_id=data.get('forcing_manifest_id', ''),
        geometry_manifest_id=data.get('geometry_manifest_id', ''),
    )
    except (KeyError, TypeError, ValueError) as e:
        print(
            f'ERROR: manifest.json has missing or invalid fields: {e}',
            file=sys.stderr,
        )
        return None


def _run_release_gate(
    artifacts_dir: Path,
    expected_run_id: str = '',
    expected_registry_sha256: str = '',
    expected_decision_record_sha256: str = '',
    poc_mode: bool = False,
) -> int:
    """Run the release gate. Returns 0 on success, 1 on failure."""
    print('=== SNOWPACK RELEASE GATE ===')
    print(f'Artifacts directory: {artifacts_dir}')

    try:
        artifacts_dir = ensure_safe_directory(artifacts_dir)
    except (OSError, RuntimeError, UnsafePathError) as exc:
        print(f'ERROR: unsafe artifacts directory: {exc}', file=sys.stderr)
        return 1

    # R1: the bundled approval snapshot is not its own trust anchor. The
    # caller must supply the expected registry digest from an external control
    # plane (for example a protected CI variable or release attestation).
    if not isinstance(expected_registry_sha256, str) or not _SHA256_PATTERN.fullmatch(
        expected_registry_sha256
    ):
        print(
            'ERROR: an externally supplied expected_registry_sha256 is required '
            'and must be a 64-character hexadecimal SHA-256 digest.',
            file=sys.stderr,
        )
        return 1

    # C0.4: Decision record layout state machine. The decision-record/
    # directory is an explicit POC artifact with strict containment rules:
    #   - POC mode: exactly one JSON + one .sha256, no other files, no symlinks
    #   - Non-POC mode: decision-record/ directory AND digest must be absent
    # The bundled decision record is never its own trust anchor.
    # P1-9: Use lexists() to detect broken symlinks (exists() follows symlinks).
    import os.path as _ospath
    decision_record_dir = artifacts_dir / 'decision-record'
    decision_record_file = decision_record_dir / 'PIR_PANJAL_POC_DECISION_RECORD.json'
    decision_record_hash_file = decision_record_dir / 'decision-record.sha256'
    has_dr_dir = _ospath.lexists(str(decision_record_dir))
    has_decision_record = decision_record_file.is_file()
    # R0: Track both the raw non-empty check and the valid SHA-256 check.
    # Non-POC mode must reject ANY non-empty digest, not just valid SHA-256.
    raw_dr_digest = (expected_decision_record_sha256 or '').strip()
    has_any_dr_digest = bool(raw_dr_digest)
    has_expected_dr_digest = bool(_SHA256_PATTERN.fullmatch(raw_dr_digest))

    # P1-9: Reject symlinked decision-record/ directory itself (including broken symlinks)
    if has_dr_dir and decision_record_dir.is_symlink():
        print('ERROR: decision-record/ directory itself is a symlink', file=sys.stderr)
        return 1

    # P0-2: POC mode REQUIRES a valid decision record digest
    if poc_mode and not has_expected_dr_digest:
        print(
            'ERROR: POC mode requires a valid externally supplied '
            'expected_decision_record_sha256 (64-character hex string). '
            f'Got: {raw_dr_digest!r}',
            file=sys.stderr,
        )
        return 1

    # R0/P0-3: Non-POC mode rejects ANY decision-record path or digest.
    # R0: Reject ANY non-empty digest, not just valid SHA-256 format.
    # A malformed digest in non-POC mode is still POC intent and must fail.
    if not poc_mode:
        if has_dr_dir:
            print(
                'ERROR: decision-record/ path present in non-POC mode. '
                'Non-POC bundles must not contain a decision record.',
                file=sys.stderr,
            )
            return 1
        if has_any_dr_digest:
            print(
                'ERROR: expected_decision_record_sha256 supplied in non-POC mode. '
                'Non-POC bundles must not supply a decision record digest '
                f'(got: {raw_dr_digest!r}).',
                file=sys.stderr,
            )
            return 1

    # P0-2: POC mode requires the decision record file to be present
    if poc_mode and has_expected_dr_digest and not has_decision_record:
        print(
            'ERROR: POC mode requires a decision record file but the bundle '
            'does not contain one.',
            file=sys.stderr,
        )
        return 1

    # G3: If the decision record is present but no expected digest is supplied, fail.
    if has_decision_record and not has_expected_dr_digest:
        print(
            'ERROR: bundle contains a decision record but no externally '
            'supplied expected_decision_record_sha256 was provided.',
            file=sys.stderr,
        )
        return 1

    # C0.4: Strict layout validation — exactly 2 files, no extras, no symlinks
    if has_decision_record:
        if not decision_record_dir.is_dir():
            print('ERROR: decision-record exists but is not a regular directory', file=sys.stderr)
            return 1
        dr_files = list(decision_record_dir.iterdir())
        # Reject any symlink in the directory
        for item in dr_files:
            if item.is_symlink():
                print(
                    f'ERROR: decision-record/ contains a symlink: {item.name}',
                    file=sys.stderr,
                )
                return 1
        # C0.4: Exactly 2 files — one JSON + one .sha256, no extras
        if len(dr_files) != 2:
            print(
                f'ERROR: decision-record/ must contain exactly 2 files '
                f'(one JSON + one .sha256), found {len(dr_files)}: '
                f'{[f.name for f in dr_files]}',
                file=sys.stderr,
            )
            return 1
        dr_json_files = [f for f in dr_files if f.suffix == '.json']
        if len(dr_json_files) != 1:
            print(
                f'ERROR: decision-record/ must contain exactly one JSON file, '
                f'found {len(dr_json_files)}.',
                file=sys.stderr,
            )
            return 1
        if not decision_record_hash_file.is_file():
            print(
                'ERROR: decision-record/ must contain decision-record.sha256.',
                file=sys.stderr,
            )
            return 1
        # C0.4: Validate the hash file is exactly one 64-char hex digest
        try:
            hash_content = decision_record_hash_file.read_text(encoding='utf-8').strip()
        except OSError as exc:
            print(f'ERROR: cannot read decision-record.sha256: {exc}', file=sys.stderr)
            return 1
        if not _SHA256_PATTERN.fullmatch(hash_content):
            print(
                f'ERROR: decision-record.sha256 must be a 64-character hex digest, '
                f'got {hash_content!r}',
                file=sys.stderr,
            )
            return 1

    # Step 1: Load result.json (exactly one, by exact name)
    print('\n--- Step 1: Load result.json ---')
    result_data = _load_result_json(artifacts_dir)
    if result_data is None:
        return 1
    result_schema_errors = _validate_result_schema(result_data)
    if result_schema_errors:
        print('ERROR: result.json schema validation failed:', file=sys.stderr)
        for error in result_schema_errors:
            print(f'  - {error}', file=sys.stderr)
        return 1

    # P1-10: Verify scope_mode in result.json matches the gate's poc_mode
    result_scope_mode = str(result_data.get('scope_mode') or '').strip()
    expected_scope_mode = 'poc' if poc_mode else 'non_poc'
    if result_scope_mode != expected_scope_mode:
        print(
            f'ERROR: result.json scope_mode ({result_scope_mode!r}) does not match '
            f'gate mode ({expected_scope_mode!r}). Producer and consumer must agree.',
            file=sys.stderr,
        )
        return 1

    # G0.2: run_id is a validated release identity. No generated fallback.
    result_run_id = result_data.get('run_id')
    try:
        result_run_id = validate_release_run_id(result_run_id)
    except ValueError as exc:
        print(f'ERROR: invalid result.json run_id: {exc}', file=sys.stderr)
        return 1

    result_status = result_data.get('status', '')
    print(f'  Result run_id: {result_run_id}')
    print(f'  Result status: {result_status}')

    # P0.8 critical fix: allowlist, not denylist. Only "completed" is releaseable.
    if result_status != _RELEASEABLE_STATUS:
        print(
            f'ERROR: Result status is "{result_status}" — cannot release. '
            f'Only "{_RELEASEABLE_STATUS}" is releaseable.',
            file=sys.stderr,
        )
        return 1

    # C0.1: Decision record byte-level validation. The full cross-layer
    # semantic validation (DR x result x manifest x forecast) is deferred to
    # Step 4c after all artifacts are loaded.
    dr_parsed = None
    if has_decision_record:
        print('\n--- Step 1.5: Validate decision record bytes ---')
        try:
            from backend.common.pir_panjal_decision_record import (
                DecisionRecordError,
                validate_decision_record_bytes,
            )
        except ImportError as exc:
            print(f'ERROR: cannot import decision record loader: {exc}', file=sys.stderr)
            return 1
        try:
            dr_bytes = decision_record_file.read_bytes()
        except OSError as exc:
            print(f'ERROR: cannot read decision record: {exc}', file=sys.stderr)
            return 1
        dr_actual_hash = hashlib.sha256(dr_bytes).hexdigest()
        if dr_actual_hash.lower() != expected_decision_record_sha256.lower():
            print(
                f'ERROR: decision record byte hash mismatch: '
                f'expected={expected_decision_record_sha256!r}, '
                f'actual={dr_actual_hash!r}',
                file=sys.stderr,
            )
            return 1
        print(f'  OK: decision record hash matches expected digest')
        try:
            bundled_hash = decision_record_hash_file.read_text(encoding='utf-8').strip()
            if bundled_hash.lower() != dr_actual_hash.lower():
                print(
                    f'ERROR: decision-record.sha256 ({bundled_hash!r}) does not '
                    f'match actual file hash ({dr_actual_hash!r})',
                    file=sys.stderr,
                )
                return 1
        except OSError as exc:
            print(f'ERROR: cannot read decision-record.sha256: {exc}', file=sys.stderr)
            return 1
        try:
            dr_parsed = validate_decision_record_bytes(dr_bytes, expected_sha256=expected_decision_record_sha256)
        except DecisionRecordError as exc:
            print(f'ERROR: decision record semantic validation failed: {exc}', file=sys.stderr)
            return 1
        print(f'  OK: decision record parsed: sector={dr_parsed.selected_sector}, '
              f'band={dr_parsed.elevation_band}, horizon={dr_parsed.headline_horizon_hours}h, '
              f'ensemble={dr_parsed.ensemble_members}')

    # Step 2: Load manifest.json (exactly one, by exact name)
    print('\n--- Step 2: Load manifest.json ---')
    manifest_result = _load_manifest(artifacts_dir)
    if manifest_result is None:
        return 1
    manifest_data, manifest_path = manifest_result
    manifest_schema_errors = _validate_manifest_schema(manifest_data)
    if manifest_schema_errors:
        print('ERROR: manifest.json schema validation failed:', file=sys.stderr)
        for error in manifest_schema_errors:
            print(f'  - {error}', file=sys.stderr)
        return 1
    manifest = _reconstruct_manifest(manifest_data)
    # G4: _reconstruct_manifest returns None on type/schema errors
    if manifest is None:
        return 1
    print(f'  Manifest run_id: {manifest.run_id}')
    print(f'  Manifest path: {manifest_path}')

    # G18: Reject empty manifest early — don't waste time on path rebasing
    if not manifest.artifacts:
        print('ERROR: manifest.json has no artifacts. Cannot release empty bundle.', file=sys.stderr)
        return 1

    # G15: Resource limits — reject excessive file counts
    _MAX_ARTIFACT_COUNT = 1000
    if len(manifest.artifacts) > _MAX_ARTIFACT_COUNT:
        print(
            f'ERROR: manifest.json has {len(manifest.artifacts)} artifacts '
            f'(max {_MAX_ARTIFACT_COUNT}). Possible DoS or misconfiguration.',
            file=sys.stderr,
        )
        return 1

    # Step 3: Verify run_id match (cross-run contamination check)
    print('\n--- Step 3: Verify run_id match ---')
    try:
        manifest_run_id = validate_release_run_id(manifest.run_id)
    except ValueError as exc:
        print(f'ERROR: invalid manifest.json run_id: {exc}', file=sys.stderr)
        return 1

    if result_run_id != manifest_run_id:
        print(
            f'ERROR: run_id mismatch — result={result_run_id}, '
            f'manifest={manifest_run_id}. Cross-run contamination detected.',
            file=sys.stderr,
        )
        return 1
    print(f'  OK: run_id match — {manifest_run_id}')

    # Check expected_run_id if provided (CI run identity)
    if expected_run_id:
        try:
            expected_run_id = validate_release_run_id(expected_run_id)
        except ValueError as exc:
            print(f'ERROR: invalid expected_run_id: {exc}', file=sys.stderr)
            return 1
        if manifest_run_id != expected_run_id:
            print(
                f'ERROR: run_id mismatch — manifest={manifest_run_id}, '
                f'expected={expected_run_id}',
                file=sys.stderr,
            )
            return 1
        print(f'  OK: matches expected run_id — {expected_run_id}')

    # Step 4: Verify native_binary_invoked AND execution attestation
    print('\n--- Step 4: Verify native binary invocation + attestation ---')
    # G17: Strict boolean check — truthy non-boolean values must NOT pass
    if manifest.native_binary_invoked is not True:
        print(
            f'ERROR: native_binary_invoked is {manifest.native_binary_invoked!r} '
            f'(must be boolean True, not truthy)',
            file=sys.stderr,
        )
        return 1

    # C0-S7/G2: Require no_fallback == true (strict boolean, not truthy)
    result_no_fallback = result_data.get('no_fallback', False)
    if result_no_fallback is not True:
        print(
            f'ERROR: result.json no_fallback is {result_no_fallback!r} '
            f'(must be boolean True, not truthy). '
            'Release bundles must be in acceptance mode (no fallback).',
            file=sys.stderr,
        )
        return 1
    print('  OK: no_fallback=true (acceptance mode confirmed)')

    # G0.12: Load and validate local subprocess integrity evidence.
    # This is not a signed or externally trusted attestation.
    invocation = _load_invocation(artifacts_dir)
    if invocation is None:
        return 1
    invocation_schema_errors = _validate_invocation_schema(invocation)
    if invocation_schema_errors:
        print('ERROR: invocation.json schema validation failed:', file=sys.stderr)
        for error in invocation_schema_errors:
            print(f'  - {error}', file=sys.stderr)
        return 1

    invoc_errors = _validate_invocation(invocation)
    if invoc_errors:
        print('ERROR: invocation.json validation failed:', file=sys.stderr)
        for err in invoc_errors:
            print(f'  - {err}', file=sys.stderr)
        return 1

    # G0.5: Require exact cross-layer identity equality.
    identity_pairs = (
        ('result.toolchain_manifest_id', result_data.get('toolchain_manifest_id'), manifest.toolchain_id),
        ('manifest.toolchain_id', manifest.toolchain_id, invocation.get('toolchain_id')),
        ('result.run_id', result_run_id, invocation.get('run_id')),
        ('result.forcing_manifest_id', result_data.get('forcing_manifest_id'), manifest.forcing_manifest_id),
        ('result.geometry_manifest_id', result_data.get('geometry_manifest_id'), manifest.geometry_manifest_id),
    )
    for label, left, right in identity_pairs:
        if left != right:
            print(
                f'ERROR: {label} identity mismatch: {left!r} != {right!r}',
                file=sys.stderr,
            )
            return 1

    # R4: validate every release manifest identity at the consumer boundary;
    # non-empty strings alone are not sufficient.
    identity_fields = (
        ('result.forcing_manifest_id', result_data.get('forcing_manifest_id')),
        ('result.geometry_manifest_id', result_data.get('geometry_manifest_id')),
        ('result.toolchain_manifest_id', result_data.get('toolchain_manifest_id')),
        ('manifest.forcing_manifest_id', manifest.forcing_manifest_id),
        ('manifest.geometry_manifest_id', manifest.geometry_manifest_id),
        ('manifest.toolchain_id', manifest.toolchain_id),
        ('invocation.toolchain_id', invocation.get('toolchain_id')),
    )
    for field, value in identity_fields:
        try:
            validate_release_manifest_id(value, field=field)
        except ValueError as exc:
            print(f'ERROR: invalid release manifest identity: {exc}', file=sys.stderr)
            return 1
    for kind, id_field in (
        ('forcing', 'forcing_manifest_id'),
        ('geometry', 'geometry_manifest_id'),
    ):
        approved_entry = result_data.get('approved_inputs', {}).get(kind, {})
        try:
            validate_release_manifest_id(
                approved_entry.get('manifest_id'),
                field=f'approved_inputs.{kind}.manifest_id',
            )
        except ValueError as exc:
            print(f'ERROR: invalid approved input identity: {exc}', file=sys.stderr)
            return 1

    # C2-prep: state and forecast semantics are a consumer-side release
    # requirement. A producer's local validation is not sufficient evidence.
    print('\n--- Step 4b: Verify initial state and forecast semantics ---')
    semantics_errors = _validate_release_semantics_bundle(
        result_data, manifest, artifacts_dir, result_run_id,
    )
    if semantics_errors:
        print('ERROR: release semantics validation failed:', file=sys.stderr)
        for error in semantics_errors:
            print(f'  - {error}', file=sys.stderr)
        return 1
    print('  OK: initial state and forecast semantics are hash/context bound')

    # C0.1/C0.2/C0.3/C0.8: Cross-layer POC scope validation.
    # Validate that decision record, result.json, artifact manifest, and
    # forecast semantics all agree on region, band, horizon, and ensemble.
    if dr_parsed is not None:
        print('\n--- Step 4c: Cross-layer POC scope validation ---')
        # Load the forecast semantics for cross-validation
        forecast_descriptor = result_data.get('forecast_semantics')
        if not isinstance(forecast_descriptor, dict):
            print('ERROR: result.json forecast_semantics descriptor missing for POC cross-validation', file=sys.stderr)
            return 1
        forecast_path = _bundle_input_file(
            forecast_descriptor.get('manifest_path'), artifacts_dir, 'forecast-semantics manifest'
        )
        if forecast_path is None:
            print('ERROR: forecast semantics manifest path invalid for POC cross-validation', file=sys.stderr)
            return 1
        try:
            forecast_semantics, _ = load_forecast_semantics_manifest(forecast_path)
        except (OSError, ReleaseSemanticsError) as exc:
            print(f'ERROR: cannot load forecast semantics for POC cross-validation: {exc}', file=sys.stderr)
            return 1
        try:
            from backend.common.poc_scope_contract import PocScopeError, validate_poc_scope_consistency
            poc_binding = validate_poc_scope_consistency(
                decision_record=dr_parsed,
                result_data=result_data,
                manifest=manifest,
                forecast=forecast_semantics,
                expected_decision_record_sha256=expected_decision_record_sha256,
                poc_mode=poc_mode,
            )
        except PocScopeError as exc:
            print(f'ERROR: POC scope consistency validation failed: {exc}', file=sys.stderr)
            return 1
        print(f'  OK: POC scope consistent across all layers:')
        print(f'    region={poc_binding.region_key}, band={poc_binding.elevation_band}, '
              f'horizon={poc_binding.headline_horizon_hours}h, ensemble={poc_binding.ensemble_members}')
        print(f'    track={poc_binding.track_id}, evidence={poc_binding.evidence_class}, '
              f'official_warning={poc_binding.official_warning_eligible}')

    # G0.2: Invocation run_id must be valid and exactly equal to result/manifest.
    try:
        validate_release_run_id(invocation.get('run_id'))
    except ValueError as exc:
        print(f'ERROR: invalid invocation.json run_id: {exc}', file=sys.stderr)
        return 1

    print('  OK: native_binary_invoked=True')
    print('  OK: local invocation integrity evidence validated (not signed trust)')
    print('  OK: run_id bound in attestation')

    # Step 5: Rebase artifact paths (PRESERVE hashes, never recompute)
    print('\n--- Step 5: Rebase artifact paths ---')
    rebased_artifacts = _rebase_artifact_paths(manifest.artifacts, artifacts_dir)
    if rebased_artifacts is None:
        print('ERROR: Cannot rebase artifact paths. Gate fails.', file=sys.stderr)
        return 1

    # Rebuild manifest with rebased paths but ORIGINAL hashes
    rebased_manifest = ArtifactManifest(
        run_id=manifest.run_id,
        region_key=manifest.region_key,
        elevation_band=manifest.elevation_band,
        aspect_class=manifest.aspect_class,
        binary_version=manifest.binary_version,
        artifacts=rebased_artifacts,
        is_native_execution=manifest.is_native_execution,
        native_binary_invoked=manifest.native_binary_invoked,
        created_at=manifest.created_at,
        toolchain_id=manifest.toolchain_id,
        forcing_manifest_id=manifest.forcing_manifest_id,
        geometry_manifest_id=manifest.geometry_manifest_id,
    )
    print(f'  OK: {len(rebased_artifacts)} artifacts rebased (hashes preserved)')

    # Step 6: Call validate_completed() — completed semantics check
    print('\n--- Step 6: Validate completed semantics ---')
    completed_errors = rebased_manifest.validate_completed()
    if completed_errors:
        print('ERROR: validate_completed() failed:', file=sys.stderr)
        for err in completed_errors:
            print(f'  - {err}', file=sys.stderr)
        return 1
    print('  OK: validate_completed() passed')

    # Step 7: Call verify_manifest_against_directory() — hash verification
    # This recomputes hashes from the ACTUAL files and compares against the
    # PRESERVED manifest hashes. If a file was tampered, the hash will NOT match.
    print('\n--- Step 7: Verify manifest hashes against directory ---')
    output_dir = artifacts_dir
    # If all rebased paths point to the same parent, use that as output_dir
    if rebased_artifacts:
        parents = {Path(a.file_path).parent for a in rebased_artifacts}
        if len(parents) == 1:
            output_dir = parents.pop()

    discrepancies = verify_manifest_against_directory(rebased_manifest, output_dir)

    if discrepancies:
        print('ERROR: verify_manifest_against_directory() failed:', file=sys.stderr)
        for d in discrepancies:
            print(f'  - {d}', file=sys.stderr)
        return 1
    print('  OK: All hashes verified against directory (no tampering detected)')

    # Step 8: Verify required file extensions are present and non-empty
    print('\n--- Step 8: Verify required output files ---')
    required_suffixes = {'.smet', '.pro', '.sno', '.haz', '.log'}
    found_suffixes: set[str] = set()
    native_output_dir = artifacts_dir / 'native-output'
    if not native_output_dir.is_dir() or native_output_dir.is_symlink():
        print('ERROR: native-output/ directory is missing or unsafe', file=sys.stderr)
        return 1
    for f in native_output_dir.rglob('*'):
        # G3: Reject symlinks — only count real files toward required suffixes
        if f.is_file() and not f.is_symlink() and f.suffix in required_suffixes and f.stat().st_size > 0:
            found_suffixes.add(f.suffix)

    missing = required_suffixes - found_suffixes
    if missing:
        print(f'ERROR: Missing required non-empty artifacts: {sorted(missing)}', file=sys.stderr)
        return 1
    print(f'  OK: All required suffixes present: {sorted(found_suffixes)}')

    # G0.7: Verify approved forcing/geometry bytes are present in the bundle
    # and match the approved IDs and recorded hashes.
    approved_inputs = result_data.get('approved_inputs', {})
    for kind, id_field in (
        ('forcing', 'forcing_manifest_id'),
        ('geometry', 'geometry_manifest_id'),
    ):
        entry = approved_inputs.get(kind, {})
        if entry.get('manifest_id') != result_data.get(id_field):
            print(f'ERROR: approved {kind} manifest ID does not match result ID', file=sys.stderr)
            return 1
        for path_field, hash_field in (
            ('manifest_path', 'manifest_sha256'),
            ('payload_path', 'payload_sha256'),
        ):
            relative = entry.get(path_field, '')
            relative_posix = PurePosixPath(relative) if isinstance(relative, str) else PurePosixPath('.')
            if (
                not isinstance(relative, str)
                or relative_posix.is_absolute()
                or not relative_posix.parts
                or relative_posix.parts[0] != 'input-manifests'
            ):
                print(f'ERROR: approved {kind} {path_field} is outside input-manifests/', file=sys.stderr)
                return 1
            if _validate_relative_path(relative) is None:
                print(f'ERROR: approved {kind} {path_field} is unsafe', file=sys.stderr)
                return 1
            candidate = artifacts_dir / relative
            if not _is_safe_bundle_file(candidate, artifacts_dir):
                print(f'ERROR: approved {kind} {path_field} is not a safe bundle file', file=sys.stderr)
                return 1
            actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual_hash != entry.get(hash_field):
                print(f'ERROR: approved {kind} {path_field} hash mismatch', file=sys.stderr)
                return 1
        contract_files = entry.get('contract_files', {})
        if contract_files:
            if kind != 'forcing' or not isinstance(contract_files, dict):
                print(f'ERROR: approved {kind} contract_files are invalid', file=sys.stderr)
                return 1
            for contract_name, contract in contract_files.items():
                if not isinstance(contract_name, str) or not isinstance(contract, dict):
                    print(f'ERROR: approved {kind} contract entry is invalid', file=sys.stderr)
                    return 1
                relative = contract.get('path', '')
                if (
                    not isinstance(relative, str)
                    or PurePosixPath(relative).parts[:2] != ('input-manifests', 'forcing-contracts')
                    or _validate_relative_path(relative) is None
                ):
                    print('ERROR: approved forcing contract path is unsafe', file=sys.stderr)
                    return 1
                candidate = artifacts_dir / relative
                if not _is_safe_bundle_file(candidate, artifacts_dir):
                    print('ERROR: approved forcing contract is missing or unsafe', file=sys.stderr)
                    return 1
                if hashlib.sha256(candidate.read_bytes()).hexdigest() != contract.get('sha256'):
                    print('ERROR: approved forcing contract hash mismatch', file=sys.stderr)
                    return 1
        try:
            input_manifest = json.loads(
                (artifacts_dir / entry['manifest_path']).read_text(encoding='utf-8')
            )
            if not isinstance(input_manifest, dict) or input_manifest.get('id') != entry['manifest_id'] or input_manifest.get('kind') != kind:
                print(f'ERROR: approved {kind} manifest semantics do not match its ID/kind', file=sys.stderr)
                return 1
        except (UnicodeDecodeError, OSError, json.JSONDecodeError, TypeError):
            print(f'ERROR: approved {kind} manifest is not valid JSON', file=sys.stderr)
            return 1
    registry_snapshot = result_data.get('registry_snapshot', {})
    snapshot_relative = registry_snapshot.get('path', '')
    snapshot_path = artifacts_dir / snapshot_relative
    if (
        not isinstance(snapshot_relative, str)
        or _validate_relative_path(snapshot_relative) is None
        or PurePosixPath(snapshot_relative).parts[:1] != ('input-manifests',)
        or not _is_safe_bundle_file(snapshot_path, artifacts_dir)
    ):
        print('ERROR: registry approval snapshot path is unsafe or missing', file=sys.stderr)
        return 1
    snapshot_bytes = snapshot_path.read_bytes()
    if hashlib.sha256(snapshot_bytes).hexdigest() != registry_snapshot.get('sha256'):
        print('ERROR: registry approval snapshot hash mismatch', file=sys.stderr)
        return 1
    try:
        snapshot = json.loads(snapshot_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        print('ERROR: registry approval snapshot is not valid UTF-8 JSON', file=sys.stderr)
        return 1
    if not isinstance(snapshot, dict) or snapshot.get('schema_version') != 'snowpack_approval_snapshot_v1':
        print('ERROR: registry approval snapshot schema is invalid', file=sys.stderr)
        return 1
    snapshot_registry_sha256 = snapshot.get('registry_sha256')
    if snapshot_registry_sha256 != registry_snapshot.get('registry_sha256'):
        print('ERROR: registry snapshot digest disagrees with result.json', file=sys.stderr)
        return 1
    if snapshot_registry_sha256 != expected_registry_sha256:
        print(
            'ERROR: bundled approval registry digest does not match the externally '
            'supplied expected registry digest.',
            file=sys.stderr,
        )
        return 1
    if snapshot.get('source_registry_version') != 'snowpack_manifest_registry_v1':
        print('ERROR: registry snapshot source_registry_version is invalid', file=sys.stderr)
        return 1
    records = snapshot.get('records', {})
    if not isinstance(records, dict):
        print('ERROR: registry approval snapshot records are invalid', file=sys.stderr)
        return 1
    for kind, id_field in (
        ('forcing', 'forcing_manifest_id'),
        ('geometry', 'geometry_manifest_id'),
        ('toolchain', 'toolchain_manifest_id'),
    ):
        record = records.get(kind)
        if (
            not isinstance(record, dict)
            or record.get('id') != result_data.get(id_field)
            or record.get('kind') != kind
            or record.get('approval_state') != 'approved'
            or record.get('region') != manifest.region_key
            or record.get('elevation_band') != manifest.elevation_band
        ):
            print(f'ERROR: registry snapshot {kind} record does not match approved result identity/context', file=sys.stderr)
            return 1
        try:
            validate_release_manifest_id(record.get('id'), field=f'registry_snapshot.records.{kind}.id')
        except ValueError as exc:
            print(f'ERROR: invalid snapshot manifest identity: {exc}', file=sys.stderr)
            return 1
        if record.get('source_registry_version') != 'snowpack_manifest_registry_v1':
            print(f'ERROR: registry snapshot {kind} source version is invalid', file=sys.stderr)
            return 1
        if record.get('region') != manifest.region_key or record.get('elevation_band') != manifest.elevation_band:
            print(f'ERROR: registry snapshot {kind} region/elevation binding is invalid', file=sys.stderr)
            return 1
        if kind in {'forcing', 'geometry'}:
            approved_entry = approved_inputs[kind]
            if record.get('manifest_sha256') != approved_entry.get('manifest_sha256'):
                print(f'ERROR: registry snapshot {kind} manifest hash is not bound to bundled input', file=sys.stderr)
                return 1
            if record.get('payload_sha256') != approved_entry.get('payload_sha256'):
                print(f'ERROR: registry snapshot {kind} payload hash is not bound to bundled input', file=sys.stderr)
                return 1
        else:
            if not _SHA256_PATTERN.fullmatch(str(record.get('manifest_sha256', ''))):
                print('ERROR: registry snapshot toolchain manifest_sha256 is invalid', file=sys.stderr)
                return 1
    print('  OK: approval registry snapshot is bundled, hashed, and identity-bound')

    # R1.1: Independent registry-root trust anchor (hardened).
    # The snapshot's registry_sha256 is a *claim* by the producer. The actual
    # registry bytes must be bundled, hashed independently, and compared against
    # the externally supplied expected_registry_sha256.
    #
    # G-R1.1.1: The expected hash must not be sourceable from inside the bundle.
    # G-R1.1.3: The file must be opened atomically (O_NOFOLLOW) to prevent TOCTOU.
    # G-R1.1.7: The registry path is fixed, not read from attacker-controlled result.json.
    # G-R1.1.8: The registry size must be bounded.
    registry_bundle_path = artifacts_dir / _FIXED_REGISTRY_BUNDLE_PATH
    registry_bytes = _read_bundle_file_atomically(registry_bundle_path, artifacts_dir)
    if registry_bytes is None:
        print('ERROR: bundled approval registry is missing, a symlink, a directory, or outside bundle', file=sys.stderr)
        return 1
    if len(registry_bytes) > _MAX_REGISTRY_BYTES:
        print(f'ERROR: bundled approval registry exceeds size limit ({len(registry_bytes)} > {_MAX_REGISTRY_BYTES} bytes)', file=sys.stderr)
        return 1
    actual_registry_sha256 = hashlib.sha256(registry_bytes).hexdigest()
    # G-R1.1.1: Warn if the expected hash matches a hash found inside the
    # bundle. This is not a hard failure because the snapshot legitimately
    # records the registry hash — but the caller MUST source the expected hash
    # from an out-of-band channel (protected CI variable, signed release config,
    # or separate approval). The gate cannot verify provenance; it can only
    # verify that the hash matches the actual bytes.
    internal_hashes = set()
    for field in ('registry_sha256', 'sha256'):
        val = registry_snapshot.get(field)
        if isinstance(val, str) and _SHA256_PATTERN.fullmatch(val):
            internal_hashes.add(val)
    snap_registry_claim = snapshot.get('registry_sha256')
    if isinstance(snap_registry_claim, str) and _SHA256_PATTERN.fullmatch(snap_registry_claim):
        internal_hashes.add(snap_registry_claim)
    if expected_registry_sha256 in internal_hashes:
        print(
            'WARNING: expected_registry_sha256 matches a hash found inside the bundle. '
            'Ensure this value was sourced from an out-of-band channel, not from bundle metadata.',
            file=sys.stderr,
        )
    if actual_registry_sha256 != expected_registry_sha256:
        print(
            'ERROR: bundled approval registry SHA-256 does not match the externally '
            'supplied expected registry digest. The registry root of trust is broken.',
            file=sys.stderr,
        )
        return 1
    # Also verify the snapshot's registry_sha256 claim matches the actual bytes
    if snapshot.get('registry_sha256') != actual_registry_sha256:
        print(
            'ERROR: snapshot registry_sha256 claim does not match the actual bundled '
            'registry byte hash. The snapshot is not a trustworthy summary of the registry.',
            file=sys.stderr,
        )
        return 1
    # Parse the registry strictly
    try:
        bundled_registry = json.loads(registry_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        print('ERROR: bundled approval registry is not valid UTF-8 JSON', file=sys.stderr)
        return 1
    if not isinstance(bundled_registry, dict):
        print('ERROR: bundled approval registry root must be a JSON object', file=sys.stderr)
        return 1
    # G-R1.1.5: Schema version must be in the supported set
    registry_schema = bundled_registry.get('schema_version')
    if registry_schema not in _SUPPORTED_REGISTRY_SCHEMAS:
        print(
            f'ERROR: bundled approval registry schema_version {registry_schema!r} '
            f'is not in the supported set {sorted(_SUPPORTED_REGISTRY_SCHEMAS)}.',
            file=sys.stderr,
        )
        return 1
    registry_manifests = bundled_registry.get('manifests')
    if not isinstance(registry_manifests, list) or not registry_manifests:
        print('ERROR: bundled approval registry manifests must be a non-empty list', file=sys.stderr)
        return 1
    # Build a lookup of registry records by ID, rejecting duplicates
    registry_by_id: dict[str, dict[str, Any]] = {}
    for reg_record in registry_manifests:
        if not isinstance(reg_record, dict):
            print('ERROR: bundled approval registry contains a non-object record', file=sys.stderr)
            return 1
        reg_id = reg_record.get('id')
        if not isinstance(reg_id, str) or not reg_id:
            print('ERROR: bundled approval registry record has missing or invalid id', file=sys.stderr)
            return 1
        if reg_id in registry_by_id:
            print(f'ERROR: bundled approval registry has duplicate manifest ID: {reg_id}', file=sys.stderr)
            return 1
        # G-R1.1.5 (Phase 5): Verify all required fields are present
        missing_fields = _REQUIRED_REGISTRY_RECORD_FIELDS - set(reg_record.keys())
        if missing_fields:
            print(f'ERROR: registry record {reg_id} is missing required fields: {sorted(missing_fields)}', file=sys.stderr)
            return 1
        registry_by_id[reg_id] = reg_record
    # Determine the run timestamp for validity checks
    run_timestamp = result_data.get('created_at') or result_data.get('finished_at') or ''
    if not isinstance(run_timestamp, str) or not run_timestamp:
        run_timestamp = invocation.get('finished_at') or invocation.get('started_at') or ''
    # Verify each selected snapshot record exists in the registry with matching hashes
    selected_ids = set()
    for kind, id_field in (
        ('forcing', 'forcing_manifest_id'),
        ('geometry', 'geometry_manifest_id'),
        ('toolchain', 'toolchain_manifest_id'),
    ):
        snap_record = records.get(kind, {})
        selected_id = snap_record.get('id')
        if selected_id not in registry_by_id:
            print(f'ERROR: registry does not contain the selected {kind} record ID: {selected_id}', file=sys.stderr)
            return 1
        selected_ids.add(selected_id)
        reg_record = registry_by_id[selected_id]
        if reg_record.get('kind') != kind:
            print(f'ERROR: registry record {selected_id} has kind {reg_record.get("kind")!r}, expected {kind!r}', file=sys.stderr)
            return 1
        if reg_record.get('approval_state') != 'approved':
            print(f'ERROR: registry record {selected_id} is not approved (state={reg_record.get("approval_state")!r})', file=sys.stderr)
            return 1
        if reg_record.get('region') != manifest.region_key:
            print(f'ERROR: registry record {selected_id} region {reg_record.get("region")!r} != manifest region {manifest.region_key!r}', file=sys.stderr)
            return 1
        if reg_record.get('elevation_band') != manifest.elevation_band:
            print(f'ERROR: registry record {selected_id} elevation {reg_record.get("elevation_band")!r} != manifest elevation {manifest.elevation_band!r}', file=sys.stderr)
            return 1
        # G-R1.1.6: Verify execution approval validity against the run
        # timestamp.  ``valid_from``/``valid_to`` remain the historical data
        # window; the separate approval window prevents a retrospective
        # record from expiring simply because it is replayed later.  Legacy
        # registries without the new fields retain the old fail-closed
        # behavior until migrated.
        approval_valid_from = reg_record.get('approval_valid_from', '')
        approval_valid_to = reg_record.get('approval_valid_to', '')
        if bool(approval_valid_from) != bool(approval_valid_to):
            print(
                f'ERROR: registry record {selected_id} must provide both '
                'approval_valid_from and approval_valid_to',
                file=sys.stderr,
            )
            return 1
        valid_from = approval_valid_from or reg_record.get('valid_from', '')
        valid_to = approval_valid_to or reg_record.get('valid_to', '')
        if isinstance(run_timestamp, str) and run_timestamp:
            try:
                from datetime import datetime
                run_dt = datetime.fromisoformat(run_timestamp.replace('Z', '+00:00'))
                if isinstance(valid_from, str) and valid_from:
                    from_dt = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
                    if run_dt < from_dt:
                        print(f'ERROR: registry record {selected_id} is not yet valid (valid_from={valid_from}, run={run_timestamp})', file=sys.stderr)
                        return 1
                if isinstance(valid_to, str) and valid_to:
                    to_dt = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))
                    if run_dt > to_dt:
                        print(f'ERROR: registry record {selected_id} is expired (valid_to={valid_to}, run={run_timestamp})', file=sys.stderr)
                        return 1
            except (ValueError, TypeError):
                print(f'ERROR: registry record {selected_id} has invalid validity timestamps', file=sys.stderr)
                return 1
        # Verify the registry's content_sha256 matches the snapshot's manifest_sha256
        reg_content_hash = reg_record.get('content_sha256', '')
        if not isinstance(reg_content_hash, str) or not _SHA256_PATTERN.fullmatch(reg_content_hash):
            print(f'ERROR: registry record {selected_id} content_sha256 is not a valid SHA-256', file=sys.stderr)
            return 1
        if reg_content_hash != snap_record.get('manifest_sha256'):
            print(f'ERROR: registry record {selected_id} content_sha256 does not match snapshot manifest_sha256', file=sys.stderr)
            return 1
        # For forcing/geometry, verify payload_sha256
        if kind in ('forcing', 'geometry'):
            reg_payload_hash = reg_record.get('payload_sha256', '')
            if not isinstance(reg_payload_hash, str) or not _SHA256_PATTERN.fullmatch(reg_payload_hash):
                print(f'ERROR: registry record {selected_id} payload_sha256 is not a valid SHA-256', file=sys.stderr)
                return 1
            if reg_payload_hash != snap_record.get('payload_sha256'):
                print(f'ERROR: registry record {selected_id} payload_sha256 does not match snapshot payload_sha256', file=sys.stderr)
                return 1
    # G-R1.1.4 + G-R1.1.9: Verify no unapproved records exist for the same
    # region/elevation as the run. This prevents an attacker from bundling an
    # unapproved alternative for the same context.
    for reg_id, reg_record in registry_by_id.items():
        if reg_id in selected_ids:
            continue
        if (
            reg_record.get('region') == manifest.region_key
            and reg_record.get('elevation_band') == manifest.elevation_band
            and reg_record.get('approval_state') != 'approved'
        ):
            print(
                f'ERROR: registry contains unapproved record {reg_id} for the same '
                f'region/elevation ({manifest.region_key}/{manifest.elevation_band}) as the run.',
                file=sys.stderr,
            )
            return 1
    print('  OK: approval registry bytes are independently hashed and trust-anchored')

    # G16: Reject unexpected top-level files in bundle root
    # Only result.json, manifest.json, invocation.json, toolchain-manifest.json,
    # input-manifests/, native-output/, and decision-record/ (POC mode only) are allowed
    allowed_top_level = {
        'result.json', 'manifest.json', 'invocation.json',
        'toolchain-manifest.json', 'input-manifests', 'native-output',
        'decision-record',
    }
    for item in artifacts_dir.iterdir():
        if item.name not in allowed_top_level:
            print(
                f'ERROR: Unexpected top-level item "{item.name}" in bundle root. '
                f'Only {sorted(allowed_top_level)} are allowed.',
                file=sys.stderr,
            )
            return 1
    print('  OK: No unexpected top-level files')

    # C0.31: Verify toolchain-manifest.json is present and bound to invocation
    print('\n--- Step 9: Verify toolchain manifest binding ---')
    toolchain_manifest_path = artifacts_dir / 'toolchain-manifest.json'
    if not toolchain_manifest_path.exists():
        print('ERROR: toolchain-manifest.json not found in bundle', file=sys.stderr)
        return 1
    if not _is_safe_bundle_file(toolchain_manifest_path, artifacts_dir):
        print('ERROR: toolchain-manifest.json is a symlink or outside bundle', file=sys.stderr)
        return 1
    try:
        with open(toolchain_manifest_path, encoding='utf-8') as f:
            tc_manifest = json.load(f)
        if not isinstance(tc_manifest, dict):
            print('ERROR: toolchain-manifest.json root must be a JSON object', file=sys.stderr)
            return 1
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, TypeError) as e:
        print(f'ERROR: toolchain-manifest.json is malformed: {e}', file=sys.stderr)
        return 1
    if 'image_digest' in tc_manifest:
        print(
            'ERROR: toolchain-manifest.json contains deprecated ambiguous image_digest',
            file=sys.stderr,
        )
        return 1

    # C0.31: Verify the invocation binds to the exact bytes in the bundle.
    actual_toolchain_hash = hashlib.sha256(
        json.dumps(tc_manifest, indent=2, sort_keys=True).encode('utf-8')
    ).hexdigest()
    if invocation.get('toolchain_manifest_sha256') != actual_toolchain_hash:
        print(
            'ERROR: toolchain_manifest_sha256 does not match bundled '
            'toolchain-manifest.json',
            file=sys.stderr,
        )
        return 1
    if tc_manifest.get('schema_version') != 'snowpack_toolchain_manifest_v1':
        print(
            'ERROR: toolchain-manifest.json schema_version must be '
            'snowpack_toolchain_manifest_v1',
            file=sys.stderr,
        )
        return 1
    for commit_field in ('meteoio_commit', 'snowpack_commit'):
        if not re.fullmatch(r'[0-9a-fA-F]{40}', str(tc_manifest.get(commit_field, ''))):
            print(
                f'ERROR: toolchain-manifest.json {commit_field} must be an exact 40-hex commit',
                file=sys.stderr,
            )
            return 1
    required_toolchain_fields = (
        'schema_version', 'toolchain_id', 'meteoio_commit', 'snowpack_commit',
        'binary_path', 'binary_sha256', 'binary_version', 'image_id',
        'image_archive_sha256', 'image_identity_source',
    )
    missing_toolchain_fields = [
        field for field in required_toolchain_fields if not tc_manifest.get(field)
    ]
    if missing_toolchain_fields:
        print(
            f'ERROR: toolchain-manifest.json missing required fields: '
            f'{missing_toolchain_fields}',
            file=sys.stderr,
        )
        return 1
    if not is_real_image_id(tc_manifest['image_id']):
        print('ERROR: toolchain-manifest.json image_id is missing or placeholder', file=sys.stderr)
        return 1
    if not is_real_sha256(tc_manifest['image_archive_sha256']):
        print('ERROR: toolchain-manifest.json image_archive_sha256 is missing or placeholder', file=sys.stderr)
        return 1
    if tc_manifest.get('image_repository_digest') and not is_real_image_id(
        tc_manifest['image_repository_digest']
    ):
        print('ERROR: toolchain-manifest.json image_repository_digest is invalid or placeholder', file=sys.stderr)
        return 1
    if tc_manifest.get('image_identity_source') not in {
        'local_id_and_archive', 'registry_digest_and_archive'
    }:
        print('ERROR: toolchain-manifest.json image_identity_source is invalid', file=sys.stderr)
        return 1
    if tc_manifest['toolchain_id'] != manifest.toolchain_id:
        print('ERROR: runtime toolchain ID does not match artifact manifest', file=sys.stderr)
        return 1
    if invocation.get('toolchain_id') != tc_manifest['toolchain_id']:
        print('ERROR: invocation toolchain ID does not match runtime manifest', file=sys.stderr)
        return 1
    if invocation.get('image_id') != tc_manifest['image_id']:
        print('ERROR: invocation image_id does not match toolchain manifest', file=sys.stderr)
        return 1
    if invocation.get('image_archive_sha256') != tc_manifest['image_archive_sha256']:
        print('ERROR: invocation image_archive_sha256 does not match toolchain manifest', file=sys.stderr)
        return 1
    if invocation.get('image_repository_digest', '') != tc_manifest.get('image_repository_digest', ''):
        print('ERROR: invocation image_repository_digest does not match toolchain manifest', file=sys.stderr)
        return 1
    if invocation.get('image_identity_source') != tc_manifest['image_identity_source']:
        print('ERROR: invocation image_identity_source does not match toolchain manifest', file=sys.stderr)
        return 1
    print('  OK: toolchain manifest byte hash bound to invocation and separated image identities')

    # C0.31: Verify manifest.binary_version == invocation.binary_version
    tc_binary_version = tc_manifest.get('binary_version', '')
    invoc_binary_version = invocation.get('binary_version', '')
    if tc_binary_version and invoc_binary_version:
        if tc_binary_version != invoc_binary_version:
            print(
                f'ERROR: binary_version mismatch — toolchain-manifest={tc_binary_version}, '
                f'invocation={invoc_binary_version}. Evidence must be cryptographically bound.',
                file=sys.stderr,
            )
            return 1
        print(f'  OK: binary_version bound — {tc_binary_version[:60]}')
    else:
        print('ERROR: binary_version missing from toolchain-manifest or invocation', file=sys.stderr)
        return 1

    toolchain_snapshot = records.get('toolchain', {})
    # G-R1.1.2: manifest_sha256 is the approved registry content_sha256.
    # toolchain_manifest_sha256 is the runtime toolchain-manifest.json hash.
    # The runtime hash must match the bundled toolchain-manifest.json.
    if toolchain_snapshot.get('toolchain_manifest_sha256') != actual_toolchain_hash:
        print(
            'ERROR: registry snapshot toolchain_manifest_sha256 does not match '
            'the bundled toolchain-manifest.json.',
            file=sys.stderr,
        )
        return 1

    # C0.31: Verify binary_sha256 matches between toolchain manifest and invocation
    tc_binary_sha = tc_manifest.get('binary_sha256', '')
    invoc_binary_sha = invocation.get('binary_sha256', '')
    if tc_binary_sha and invoc_binary_sha:
        if tc_binary_sha != invoc_binary_sha:
            print(
                f'ERROR: binary_sha256 mismatch — toolchain-manifest={tc_binary_sha[:16]}..., '
                f'invocation={invoc_binary_sha[:16]}...',
                file=sys.stderr,
            )
            return 1
        print('  OK: binary_sha256 bound')
    else:
        print('ERROR: binary_sha256 missing from toolchain-manifest or invocation', file=sys.stderr)
        return 1

    # C0.31: Verify toolchain_id matches between toolchain manifest and invocation
    tc_toolchain_id = tc_manifest.get('toolchain_id', tc_manifest.get('snowpack_commit', ''))
    invoc_toolchain_id = invocation.get('toolchain_id', '')
    if invoc_toolchain_id and tc_toolchain_id and invoc_toolchain_id != tc_toolchain_id:
        # The toolchain manifest may use commit hashes as IDs; only fail if
        # both are explicitly set and differ
        if tc_manifest.get('toolchain_id') and invoc_toolchain_id:
            if tc_manifest['toolchain_id'] != invoc_toolchain_id:
                print(
                    f'ERROR: toolchain_id mismatch — toolchain-manifest={tc_manifest.get("toolchain_id")}, '
                    f'invocation={invoc_toolchain_id}',
                    file=sys.stderr,
                )
                return 1
    print('  OK: toolchain manifest verified and bound to invocation')

    # Gate passed
    print('\n=== RELEASE GATE PASSED ===')
    print('Release bundle contract passed.')
    print('Manifest hashes validated against directory (no tampering).')
    print('validate_completed() semantics enforced.')
    print('native_binary_invoked=True confirmed (local attestation, not signed).')
    print('run_id match confirmed.')
    print('toolchain-manifest.json verified and bound to invocation.')
    print('Only "completed" status accepted.')
    print('No dry-run, fake, stale, or cross-run artifacts accepted.')
    return 0


def run_release_gate(
    artifacts_dir: Path,
    expected_run_id: str = '',
    expected_registry_sha256: str = '',
    expected_decision_record_sha256: str = '',
    poc_mode: bool = False,
) -> int:
    """Run the gate with a final fail-closed exception boundary.

    P2/G11: Distinguish validation rejections from internal defects.
    - VALIDATION_REJECTED: malformed or untrusted input — the gate correctly
      rejected the bundle. Exit 1 with a clear validation message.
    - INTERNAL_GATE_ERROR: unexpected implementation defect (AttributeError,
      ImportError, RecursionError, etc.) — the gate failed due to a code bug,
      not a validation failure. Exit 1 with a distinct machine-readable label.
    Both paths exit 1 (fail-closed), but the taxonomy makes it possible to
    distinguish "the bundle was bad" from "the gate has a bug."
    """
    # Validation-rejection exception types: these are expected when the input
    # bundle is malformed, untrusted, or inconsistent. They are NOT code bugs.
    # G6: Split exceptions into validation vs infrastructure.
    # _VALIDATION_EXCEPTIONS: explicit domain validation errors from bad bundles.
    # _INFRASTRUCTURE_EXCEPTIONS: disk I/O, code bugs, and unexpected failures.
    # Note: ValueError is NOT in _VALIDATION_EXCEPTIONS because it is too broad —
    # internal code bugs raise ValueError too. Only explicit domain exceptions
    # (UnicodeDecodeError, json.JSONDecodeError, UnsafePathError, ReleaseSemanticsError,
    # DecisionRecordError, PocScopeError) are validation failures.
    _VALIDATION_EXCEPTIONS = (
        UnicodeDecodeError,
        json.JSONDecodeError,
        UnsafePathError,
        ReleaseSemanticsError,
    )
    # Import domain-specific validation exceptions.
    try:
        from backend.common.pir_panjal_decision_record import DecisionRecordError
        _VALIDATION_EXCEPTIONS = (*_VALIDATION_EXCEPTIONS, DecisionRecordError)
    except ImportError:
        pass
    try:
        from backend.common.poc_scope_contract import PocScopeError
        _VALIDATION_EXCEPTIONS = (*_VALIDATION_EXCEPTIONS, PocScopeError)
    except ImportError:
        pass

    # G6: FileNotFoundError and PermissionError are validation (bad input path),
    # but infrastructure OSErrors (disk I/O, hardware, timeout) are internal.
    _INFRASTRUCTURE_ERRNOS = {
        errno.ENOSPC,   # No space left on device
        errno.EDQUOT,   # Disk quota exceeded
        errno.EIO,      # I/O error (hardware)
        errno.EBUSY,    # Device or resource busy
        errno.ETIMEDOUT,  # Connection timed out
        errno.ECONNRESET,  # Connection reset by peer
        errno.ENETRESET,   # Network dropped connection on reset
    }

    try:
        return _run_release_gate(
            artifacts_dir,
            expected_run_id,
            expected_registry_sha256,
            expected_decision_record_sha256,
            poc_mode,
        )
    except _VALIDATION_EXCEPTIONS as exc:
        # VALIDATION_REJECTED: the bundle was correctly rejected.
        print(
            f'ERROR: VALIDATION_REJECTED: release gate rejected bundle: '
            f'{type(exc).__name__}: {exc}',
            file=sys.stderr,
        )
        return 1
    except FileNotFoundError as exc:
        # FileNotFoundError is a subclass of OSError — bad input path.
        print(
            f'ERROR: VALIDATION_REJECTED: release gate rejected bundle: '
            f'FileNotFoundError: {exc}',
            file=sys.stderr,
        )
        return 1
    except PermissionError as exc:
        # PermissionError is a subclass of OSError — bad input permissions.
        print(
            f'ERROR: VALIDATION_REJECTED: release gate rejected bundle: '
            f'PermissionError: {exc}',
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        # G6: Distinguish infrastructure OSErrors (ENOSPC, EIO, EBUSY, etc.)
        # from other OSErrors. Hardware/disk I/O failures are NOT validation
        # failures — they are infrastructure defects.
        if exc.errno in _INFRASTRUCTURE_ERRNOS:
            print(
                f'ERROR: INTERNAL_GATE_ERROR: infrastructure failure '
                f'(disk/hardware I/O): OSError({exc.errno}): {exc}',
                file=sys.stderr,
            )
        else:
            # Other OSErrors (e.g. EINVAL from bad path) are validation.
            print(
                f'ERROR: VALIDATION_REJECTED: release gate rejected bundle: '
                f'OSError({exc.errno}): {exc}',
                file=sys.stderr,
            )
        return 1
    except (ValueError, KeyError, TypeError, RuntimeError, AttributeError,
            ImportError, RecursionError, MemoryError) as exc:
        # G6: These exception types indicate internal code defects, not
        # validation failures. ValueError from an internal bug is a code bug;
        # KeyError from a missing dict key in internal logic is a code bug;
        # TypeError from calling a method on None is a code bug.
        print(
            f'ERROR: INTERNAL_GATE_ERROR: release gate encountered an unexpected '
            f'implementation defect (not a validation failure): '
            f'{type(exc).__name__}: {exc}',
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        # INTERNAL_GATE_ERROR: unexpected implementation defect. The gate
        # still fails closed (exit 1), but the label distinguishes it from
        # a normal validation rejection. This helps diagnose code bugs vs
        # bad input.
        print(
            f'ERROR: INTERNAL_GATE_ERROR: release gate encountered an unexpected '
            f'implementation defect (not a validation failure): '
            f'{type(exc).__name__}: {exc}',
            file=sys.stderr,
        )
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description='SNOWPACK release gate — validates release bundle contract (local attestation, not signed).'
    )
    parser.add_argument(
        '--artifacts-dir',
        type=Path,
        required=True,
        help='Directory containing native execution artifacts.',
    )
    parser.add_argument(
        '--expected-run-id',
        type=str,
        default='',
        help='Expected run_id (for cross-run contamination check).',
    )
    parser.add_argument(
        '--expected-registry-sha256',
        type=str,
        required=True,
        help=(
            'Externally supplied SHA-256 of the approved manifest registry. '
            'The bundled snapshot is not a trust anchor.'
        ),
    )
    parser.add_argument(
        '--expected-decision-record-sha256',
        type=str,
        default='',
        help=(
            'Externally supplied SHA-256 of the Pir Panjal POC decision record. '
            'Required when the bundle contains a decision record.'
        ),
    )
    parser.add_argument(
        '--poc-mode',
        action='store_true',
        default=False,
        help=(
            'Enable POC mode. Required when the bundle contains a decision-record/ '
            'directory. Non-POC mode rejects any decision-record/ directory.'
        ),
    )
    args = parser.parse_args()

    exit_code = run_release_gate(
        artifacts_dir=args.artifacts_dir,
        expected_run_id=args.expected_run_id,
        expected_registry_sha256=args.expected_registry_sha256,
        expected_decision_record_sha256=args.expected_decision_record_sha256,
        poc_mode=args.poc_mode,
    )
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
