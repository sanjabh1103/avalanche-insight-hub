"""Native SNOWPACK output artifact manifest (Phase 5-prep + Phase 0.5 hardening).

Defines the expected outputs from a native SNOWPACK run and provides
validation that outputs are non-empty, hash-linked, and replayable.

Per Imp_plan.md Phase 5 exit gate:
  - actual native execution succeeds;
  - non-empty outputs are validated;
  - outputs are replayable and hash-linked;
  - native/fallback status is unambiguous;
  - no missing critical output is silently accepted.

Per Phase 0.5 false-green closure:
  - Manifest must verify file existence, file size, hash format, and actual
    hash equality against the directory.
  - A directory must not be assumed native merely because it contains expected
    suffixes.
  - 'completed' requires processed meteorology and execution log in addition
    to .smet/.pro/.sno/.haz.
  - Synthetic fixture files must not be represented as is_native_execution=True
    without explicit native_binary_invoked evidence.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.common.snowpack_paths import UnsafePathError, ensure_safe_directory


# Expected SNOWPACK output file extensions
SNOWPACK_OUTPUT_EXTENSIONS = frozenset({
    '.pro',    # Profile time series
    '.sno',    # Snow profile
    '.haz',    # Hazard file
    '.smet',   # Meteorological data (forcing and/or processed meteo)
    '.log',    # Log file
})

# Critical forcing/profile/hazard outputs that must be non-empty for a valid native run.
# The .smet file is the forcing artifact; .pro/.sno/.haz are native outputs.
CRITICAL_OUTPUT_EXTENSIONS = frozenset({'.smet', '.pro', '.sno', '.haz'})

# Phase 0.5: Additional outputs required for 'completed' status.
# Per codex audit: processed meteorology and execution log are required.
COMPLETED_REQUIRED_EXTENSIONS = frozenset({'.smet', '.pro', '.sno', '.haz', '.log'})

# R5: Suffixes are not scientific roles. These roles are the release contract.
# SNOWPACK can emit both processed forcing and a model time-series SMET. The
# latter is useful evidence but is optional for the completed release contract.
REQUIRED_ARTIFACT_ROLES = frozenset({
    'forcing_smet',
    'processed_meteo',
    'profile_pro',
    'snow_profile_sno',
    'hazard_haz',
    'execution_log',
})
OPTIONAL_ARTIFACT_ROLES = frozenset({'model_timeseries_smet'})
ARTIFACT_ROLES = REQUIRED_ARTIFACT_ROLES | OPTIONAL_ARTIFACT_ROLES

_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class ArtifactEntry:
    """A single artifact in a native output manifest."""
    file_path: str
    file_type: str           # Extension (e.g., '.pro')
    size_bytes: int
    sha256: str
    is_critical: bool        # True for .pro, .sno
    role: str = ''           # Semantic release role; suffix alone is insufficient


@dataclass(frozen=True)
class ArtifactManifest:
    """Manifest of all outputs from a native SNOWPACK run."""
    run_id: str
    region_key: str
    elevation_band: str
    aspect_class: str
    binary_version: str
    artifacts: tuple[ArtifactEntry, ...]
    is_native_execution: bool   # Must be True for a real manifest
    created_at: str             # ISO 8601
    # Phase 0.5: explicit evidence that a native binary was invoked.
    # A directory with expected suffixes alone must not set this to True.
    native_binary_invoked: bool = False
    # Phase 0.5: linked identifiers for completed-status validation.
    toolchain_id: str = ''
    forcing_manifest_id: str = ''
    geometry_manifest_id: str = ''

    def validate(self) -> list[str]:
        """Validate the manifest. Returns list of errors (empty = valid)."""
        errors: list[str] = []

        if not self.run_id:
            errors.append('ArtifactManifest: run_id is required')

        if not self.is_native_execution:
            errors.append(
                'ArtifactManifest: is_native_execution must be True. '
                'Dry-run paths must not produce an ArtifactManifest.'
            )
            return errors  # No point checking further

        # Phase 0.5: is_native_execution=True requires native_binary_invoked=True.
        # A directory with expected suffixes alone must not be treated as native.
        if not self.native_binary_invoked:
            errors.append(
                'ArtifactManifest: is_native_execution=True requires '
                'native_binary_invoked=True. Suffix presence alone is not native evidence.'
            )

        if not self.artifacts:
            errors.append('ArtifactManifest: must have at least one artifact')
            return errors

        # Check critical outputs are present and non-empty
        critical_found: set[str] = set()
        for art in self.artifacts:
            if art.file_type not in SNOWPACK_OUTPUT_EXTENSIONS:
                errors.append(
                    f'ArtifactManifest: unexpected file type "{art.file_type}" '
                    f'for {art.file_path}'
                )
            if art.role not in ARTIFACT_ROLES:
                errors.append(
                    f'ArtifactManifest: invalid or missing semantic role "{art.role}" '
                    f'for {art.file_path}'
                )
            role_suffix = {
                'forcing_smet': '.smet',
                'processed_meteo': '.smet',
                'model_timeseries_smet': '.smet',
                'profile_pro': '.pro',
                'snow_profile_sno': '.sno',
                'hazard_haz': '.haz',
                'execution_log': '.log',
            }.get(art.role)
            if role_suffix and art.file_type != role_suffix:
                errors.append(
                    f'ArtifactManifest: role {art.role} does not match file type {art.file_type}'
                )
            if art.size_bytes == 0:
                errors.append(
                    f'ArtifactManifest: {art.file_path} is empty (0 bytes). '
                    f'No missing critical output is silently accepted.'
                )
            if art.is_critical:
                critical_found.add(art.file_type)
            if not art.sha256:
                errors.append(
                    f'ArtifactManifest: {art.file_path} has no SHA-256 hash. '
                    f'Outputs must be hash-linked.'
                )
            elif not _SHA256_RE.fullmatch(art.sha256.lower()):
                errors.append(
                    f'ArtifactManifest: {art.file_path} has invalid SHA-256 format. '
                    f'Outputs must be hash-linked with a valid 64-char hex digest.'
                )

        missing_critical = CRITICAL_OUTPUT_EXTENSIONS - critical_found
        if missing_critical:
            errors.append(
                f'ArtifactManifest: missing critical outputs: {sorted(missing_critical)}. '
                f'Native execution must produce non-empty .smet, .pro, .sno, and .haz files.'
            )

        return errors

    def validate_completed(self) -> list[str]:
        """Phase 0.5: validate that this manifest supports a 'completed' status.

        Per codex audit, 'completed' requires:
          - native_binary_invoked=True
          - .smet, .pro, .sno, .haz, .log all present and non-empty
          - all hashes valid SHA-256
          - linked toolchain, forcing, geometry, and run identifiers
        """
        errors = self.validate()
        if errors:
            return errors

        # R5: completed requires every required semantic role, not merely
        # suffix presence. Optional native diagnostics may be included.
        found_types = {art.file_type for art in self.artifacts if art.size_bytes > 0}
        missing_completed = COMPLETED_REQUIRED_EXTENSIONS - found_types
        if missing_completed:
            errors.append(
                f'ArtifactManifest: completed status missing required outputs: '
                f'{sorted(missing_completed)} (requires .smet, .pro, .sno, .haz, .log)'
            )
        found_roles = {art.role for art in self.artifacts if art.size_bytes > 0}
        missing_roles = REQUIRED_ARTIFACT_ROLES - found_roles
        if missing_roles:
            errors.append(
                f'ArtifactManifest: completed status missing semantic roles: {sorted(missing_roles)}'
            )

        if not self.toolchain_id:
            errors.append('ArtifactManifest: completed requires toolchain_id')
        if not self.forcing_manifest_id:
            errors.append('ArtifactManifest: completed requires forcing_manifest_id')
        if not self.geometry_manifest_id:
            errors.append('ArtifactManifest: completed requires geometry_manifest_id')

        return errors


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a regular, non-symlink file."""
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'cannot hash symlink or non-regular file: {path}')
    except OSError as exc:
        raise ValueError(f'cannot inspect file for hashing: {path}') from exc
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def build_manifest_from_directory(
    *,
    run_id: str,
    region_key: str,
    elevation_band: str,
    aspect_class: str,
    binary_version: str,
    output_dir: Path,
    created_at: str,
    native_binary_invoked: bool = False,
    toolchain_id: str = '',
    forcing_manifest_id: str = '',
    geometry_manifest_id: str = '',
    artifact_roles: dict[str, str] | None = None,
) -> ArtifactManifest:
    """Build an ArtifactManifest from a directory of SNOWPACK outputs.

    Phase 0.5: native_binary_invoked must be explicitly set. A directory
    with expected suffixes alone does not constitute native execution evidence.
    """
    try:
        output_dir = ensure_safe_directory(output_dir)
    except (OSError, RuntimeError, UnsafePathError) as exc:
        raise ValueError(f'unsafe SNOWPACK output directory: {exc}') from exc

    artifacts: list[ArtifactEntry] = []
    for f in sorted(output_dir.iterdir()):
        if f.is_symlink() or not f.is_file():
            continue
        if f.suffix in SNOWPACK_OUTPUT_EXTENSIONS:
            default_role = {
                '.pro': 'profile_pro',
                '.sno': 'snow_profile_sno',
                '.haz': 'hazard_haz',
                '.log': 'execution_log',
                '.smet': 'processed_meteo' if 'meteo' in f.stem.lower() else 'forcing_smet',
            }[f.suffix]
            role = (artifact_roles or {}).get(str(f), (artifact_roles or {}).get(f.name, default_role))
            artifacts.append(ArtifactEntry(
                file_path=str(f),
                file_type=f.suffix,
                size_bytes=f.stat().st_size,
                sha256=compute_file_hash(f),
                is_critical=f.suffix in CRITICAL_OUTPUT_EXTENSIONS,
                role=role,
            ))

    return ArtifactManifest(
        run_id=run_id,
        region_key=region_key,
        elevation_band=elevation_band,
        aspect_class=aspect_class,
        binary_version=binary_version,
        artifacts=tuple(artifacts),
        is_native_execution=True,
        created_at=created_at,
        native_binary_invoked=native_binary_invoked,
        toolchain_id=toolchain_id,
        forcing_manifest_id=forcing_manifest_id,
        geometry_manifest_id=geometry_manifest_id,
    )


def verify_manifest_against_directory(
    manifest: ArtifactManifest,
    output_dir: Path,
) -> list[str]:
    """Phase 0.5: verify that a manifest matches the actual directory contents.

    Re-computes hashes from the directory and compares against the manifest.
    Detects:
      - files listed in manifest but missing from directory
      - files present in directory but not in manifest (stale/unexpected)
      - hash mismatches (tampering or corruption)
      - size mismatches

    Returns list of discrepancy strings (empty = manifest matches directory).
    """
    discrepancies: list[str] = []

    # Build actual directory index
    # G4: Use rglob('*') instead of iterdir() to catch files in subdirectories
    actual_files: dict[str, Path] = {}
    for f in sorted(output_dir.rglob('*')):
        if f.is_file() and not f.is_symlink() and f.suffix in SNOWPACK_OUTPUT_EXTENSIONS:
            actual_files[str(f)] = f

    # Check manifest entries against directory
    manifest_paths = {art.file_path for art in manifest.artifacts}
    for art in manifest.artifacts:
        path = Path(art.file_path)
        if not path.exists():
            discrepancies.append(f'Verify: {art.file_path} listed in manifest but missing from directory')
            continue
        if path.stat().st_size != art.size_bytes:
            discrepancies.append(
                f'Verify: {art.file_path} size mismatch '
                f'(manifest={art.size_bytes}, actual={path.stat().st_size})'
            )
        actual_hash = compute_file_hash(path)
        # G9: Use constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(actual_hash.lower(), art.sha256.lower()):
            discrepancies.append(
                f'Verify: {art.file_path} hash mismatch '
                f'(manifest={art.sha256[:16]}..., actual={actual_hash[:16]}...)'
            )

    # Check for unexpected files in directory (stale outputs)
    for actual_path_str in actual_files:
        if actual_path_str not in manifest_paths:
            discrepancies.append(
                f'Verify: {actual_path_str} exists in directory but not in manifest '
                f'(stale/unexpected output)'
            )

    return discrepancies


def is_clean_output_directory(output_dir: Path, expected_files: set[str] | None = None) -> bool:
    """Phase 0.5: check if an output directory is clean (no stale files).

    A clean directory either:
      - is empty, or
      - contains only files in the expected_files set (if provided)

    This prevents stale files from creating a false 'completed' status.
    """
    if not output_dir.exists():
        return True  # Non-existent is clean (will be created)
    for f in output_dir.iterdir():
        if f.is_file():
            if expected_files is None:
                return False  # Any file makes it non-clean
            if str(f) not in expected_files and f.name not in expected_files:
                return False
    return True


def manifest_to_json(manifest: ArtifactManifest) -> str:
    """Serialize an ArtifactManifest to JSON."""
    return json.dumps({
        'run_id': manifest.run_id,
        'region_key': manifest.region_key,
        'elevation_band': manifest.elevation_band,
        'aspect_class': manifest.aspect_class,
        'binary_version': manifest.binary_version,
        'is_native_execution': manifest.is_native_execution,
        'native_binary_invoked': manifest.native_binary_invoked,
        'toolchain_id': manifest.toolchain_id,
        'forcing_manifest_id': manifest.forcing_manifest_id,
        'geometry_manifest_id': manifest.geometry_manifest_id,
        'created_at': manifest.created_at,
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
    }, indent=2, sort_keys=True)
