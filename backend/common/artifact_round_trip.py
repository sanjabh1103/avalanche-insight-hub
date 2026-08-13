"""POC artifact round-trip: upload, download, and verify artifact bundles.

Phase 3 of the Cortex POC audit action plan.

This module wires storage_io.py into the POC execution flow. It provides:
  - Provider selection (supabase, local_only)
  - Bundle creation from a directory of SNOWPACK output artifacts
  - Upload to the selected provider
  - Download and SHA-256 verification
  - Explicit success/blocked results — never false success

GitHub Actions artifacts are a workflow-level fallback (actions/upload-artifact@v4),
not a Python library path. The provider selection documents this option but
the Python round-trip supports Supabase and local-only.

Non-claims:
  - This is a pipeline transfer proof, not a scientific validation.
  - A successful round-trip proves bytes survived upload/download, not that
    the snowpack model is correct.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from backend.common.poc_preflight import PreflightStatus, PreflightResult
from backend.common.storage_io import storage_upload_bytes, storage_download_bytes
from backend.common.supabase_io import SupabaseError


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

class ArtifactProvider(str, Enum):
    SUPABASE = 'supabase'
    LOCAL_ONLY = 'local_only'


class RoundTripStatus(str, Enum):
    SUCCESS = 'success'
    BLOCKED = 'blocked'
    NOT_RUN = 'not_run'


class BundleValidationError(ValueError):
    """Raised when a bundle contains an unsafe or malformed path/manifest."""


_BUNDLE_MANIFEST_NAME = '_bundle_manifest.json'
_BUNDLE_SCHEMA_VERSION = 'poc_artifact_bundle_v1'
_SHA256_PATTERN = re.compile(r'^[0-9a-fA-F]{64}$')
_OBJECT_PREFIX_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$')


@dataclass(frozen=True)
class RoundTripResult:
    """Result of an artifact round-trip operation."""
    status: RoundTripStatus
    provider: str
    detail: str
    uploaded_files: tuple[str, ...] = ()
    downloaded_files: tuple[str, ...] = ()
    verified: bool = False
    sha256_mismatches: tuple[str, ...] = ()
    error_class: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'status': self.status.value,
            'provider': self.provider,
            'detail': self.detail,
            'uploaded_files': list(self.uploaded_files),
            'downloaded_files': list(self.downloaded_files),
            'verified': self.verified,
            'sha256_mismatches': list(self.sha256_mismatches),
            'error_class': self.error_class,
        }


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def _validate_relative_bundle_path(value: Any) -> str:
    """Return a safe relative POSIX path or raise ``BundleValidationError``."""
    if not isinstance(value, str) or not value:
        raise BundleValidationError('bundle path must be a non-empty string')
    if '\x00' in value or '\\' in value:
        raise BundleValidationError(f'unsafe bundle path: {value!r}')
    if value.startswith('/') or PurePosixPath(value).is_absolute():
        raise BundleValidationError(f'absolute bundle path is not allowed: {value!r}')
    if PureWindowsPath(value).is_absolute() or (len(value) >= 2 and value[1] == ':'):
        raise BundleValidationError(f'drive-qualified bundle path is not allowed: {value!r}')
    parts = value.split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise BundleValidationError(f'non-canonical bundle path is not allowed: {value!r}')
    return value


def _validate_object_prefix(value: str) -> str:
    """Validate the storage prefix used to bind a bundle to one run."""
    if not isinstance(value, str) or not _OBJECT_PREFIX_PATTERN.fullmatch(value):
        raise BundleValidationError(
            'object_prefix must contain only safe relative path characters '
            '(letters, digits, dot, underscore, hyphen, slash)'
        )
    _validate_relative_bundle_path(value)
    return value


def _ensure_safe_source_directory(source_dir: Path) -> Path:
    if not source_dir.exists() or not source_dir.is_dir() or source_dir.is_symlink():
        raise BundleValidationError(f'source directory is missing or unsafe: {source_dir}')
    try:
        return source_dir.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BundleValidationError(f'cannot resolve source directory: {exc}') from exc


def _iter_bundle_files(source_dir: Path) -> list[tuple[Path, str]]:
    root = _ensure_safe_source_directory(source_dir)
    files: list[tuple[Path, str]] = []
    for path in sorted(root.rglob('*'), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise BundleValidationError(f'symlinks are not allowed in bundles: {path}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise BundleValidationError(f'non-regular bundle entry is not allowed: {path}')
        relative = _validate_relative_bundle_path(path.relative_to(root).as_posix())
        if relative == _BUNDLE_MANIFEST_NAME:
            raise BundleValidationError(
                f'{_BUNDLE_MANIFEST_NAME} is reserved for the transport manifest'
            )
        files.append((path, relative))
    return files


def _validate_bundle_manifest(
    manifest: Any,
    *,
    expected_object_prefix: str | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise BundleValidationError('bundle manifest root must be a JSON object')
    if manifest.get('schema_version') != _BUNDLE_SCHEMA_VERSION:
        raise BundleValidationError('unsupported or missing bundle manifest schema_version')
    file_count = manifest.get('file_count')
    if type(file_count) is not int or file_count < 1:
        raise BundleValidationError('bundle manifest file_count must be a positive integer')
    files = manifest.get('files')
    if not isinstance(files, list) or len(files) != file_count:
        raise BundleValidationError('bundle manifest files must match file_count')
    if expected_object_prefix is not None:
        _validate_object_prefix(expected_object_prefix)
        if manifest.get('object_prefix') != expected_object_prefix:
            raise BundleValidationError(
                'bundle manifest object_prefix does not match the requested run prefix'
            )
    elif 'object_prefix' in manifest:
        _validate_object_prefix(manifest['object_prefix'])

    seen_paths: set[str] = set()
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise BundleValidationError(f'bundle manifest files[{index}] must be an object')
        relative = _validate_relative_bundle_path(entry.get('path'))
        if relative in seen_paths:
            raise BundleValidationError(f'duplicate bundle manifest path: {relative}')
        seen_paths.add(relative)
        size_bytes = entry.get('size_bytes')
        if type(size_bytes) is not int or size_bytes < 0:
            raise BundleValidationError(f'{relative}: size_bytes must be a non-negative integer')
        if not isinstance(entry.get('sha256'), str) or not _SHA256_PATTERN.fullmatch(entry['sha256']):
            raise BundleValidationError(f'{relative}: sha256 must be a 64-character hex digest')
    return manifest


def _safe_download_target(root: Path, relative: str) -> Path:
    """Resolve a download target while rejecting symlinked parents and escapes."""
    _validate_relative_bundle_path(relative)
    root_resolved = root.resolve()
    target = root / relative
    current = target.parent
    while current != root:
        if current.is_symlink():
            raise BundleValidationError(f'symlinked download parent is not allowed: {current}')
        if current == current.parent:
            raise BundleValidationError(f'download target escaped root: {relative}')
        current = current.parent
    if target.is_symlink():
        raise BundleValidationError(f'symlinked download target is not allowed: {target}')
    try:
        if not target.resolve().is_relative_to(root_resolved):
            raise BundleValidationError(f'download target escaped root: {relative}')
    except (OSError, RuntimeError) as exc:
        raise BundleValidationError(f'cannot resolve download target: {exc}') from exc
    return target


def _validate_manifest_json_bytes(payload: bytes, *, expected_object_prefix: str | None = None) -> dict[str, Any]:
    try:
        decoded = payload.decode('utf-8')
        manifest = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleValidationError(f'bundle manifest is malformed UTF-8/JSON: {exc}') from exc
    return _validate_bundle_manifest(manifest, expected_object_prefix=expected_object_prefix)


@contextmanager
def _storage_credentials(*, supabase_url: str | None, service_role_key: str | None):
    """Make explicit helper credentials visible to the existing storage adapter.

    ``storage_io`` intentionally reads credentials from the process environment.
    This narrow context keeps the public helper arguments truthful without
    persisting credentials or printing them.
    """
    original_url = os.environ.get('SUPABASE_URL')
    original_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if supabase_url is not None:
        os.environ['SUPABASE_URL'] = supabase_url
    if service_role_key is not None:
        os.environ['SUPABASE_SERVICE_ROLE_KEY'] = service_role_key
    try:
        yield
    finally:
        if original_url is None:
            os.environ.pop('SUPABASE_URL', None)
        else:
            os.environ['SUPABASE_URL'] = original_url
        if original_key is None:
            os.environ.pop('SUPABASE_SERVICE_ROLE_KEY', None)
        else:
            os.environ['SUPABASE_SERVICE_ROLE_KEY'] = original_key


def build_bundle_manifest(source_dir: Path) -> dict[str, Any]:
    """Build a manifest of all files in a directory with their SHA-256 hashes.

    The manifest itself is included in the upload so the downloader can verify
    every file survived the round-trip.
    """
    entries = []
    for path, relative in _iter_bundle_files(source_dir):
        entries.append({
            'path': relative,
            'size_bytes': path.stat().st_size,
            'sha256': _sha256_file(path),
        })
    manifest = {
        'schema_version': _BUNDLE_SCHEMA_VERSION,
        'file_count': len(entries),
        'files': entries,
    }
    if entries:
        return manifest
    return manifest


def verify_bundle(
    downloaded_dir: Path,
    expected_manifest: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Verify that all files in the downloaded directory match the expected manifest.

    Returns (all_match, mismatches_list).
    """
    mismatches = []
    try:
        _validate_bundle_manifest(expected_manifest)
    except BundleValidationError as exc:
        return False, [f'manifest invalid: {exc}']
    root = downloaded_dir
    if not root.exists() or not root.is_dir() or root.is_symlink():
        return False, ['downloaded bundle directory is missing or unsafe']
    expected_paths: set[str] = set()
    for entry in expected_manifest['files']:
        rel = entry['path']
        expected_paths.add(rel)
        expected_sha = entry['sha256']
        expected_size = entry['size_bytes']
        try:
            local_path = _safe_download_target(root, rel)
        except BundleValidationError as exc:
            mismatches.append(f'{rel}: {exc}')
            continue

        if not local_path.exists():
            mismatches.append(f'{rel}: missing')
            continue

        if not local_path.is_file() or local_path.is_symlink():
            mismatches.append(f'{rel}: not a regular non-symlink file')
            continue

        actual_size = local_path.stat().st_size
        if actual_size != expected_size:
            mismatches.append(f'{rel}: size mismatch {actual_size} != {expected_size}')
            continue

        actual_sha = _sha256_file(local_path)
        if actual_sha != expected_sha:
            mismatches.append(f'{rel}: sha256 mismatch {actual_sha} != {expected_sha}')

    try:
        actual_paths = {
            path.relative_to(root).as_posix()
            for path in root.rglob('*')
            if path.is_file()
        }
        if any(path.is_symlink() for path in root.rglob('*')):
            mismatches.append('bundle contains a symlink')
        for extra in sorted(actual_paths - expected_paths):
            mismatches.append(f'{extra}: unexpected file')
    except (OSError, RuntimeError) as exc:
        mismatches.append(f'cannot enumerate downloaded bundle: {exc}')

    return len(mismatches) == 0, mismatches


def _content_type_for_path(relative: str) -> str:
    if relative.endswith('.json'):
        return 'application/json'
    if relative.endswith(('.log', '.smet')):
        return 'text/plain'
    return 'application/octet-stream'


def upload_supabase_bundle(
    source_dir: Path,
    *,
    bucket: str = 'poc-artifacts',
    object_prefix: str,
    supabase_url: str | None = None,
    service_role_key: str | None = None,
) -> RoundTripResult:
    """Upload one complete bundle recursively; independent download is separate.

    This function never reports ``verified=True``. The consumer-side download
    and release gate must establish verification after transfer.
    """
    url = supabase_url or os.environ.get('SUPABASE_URL')
    key = service_role_key or os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        return RoundTripResult(
            status=RoundTripStatus.NOT_RUN,
            provider='supabase',
            detail='SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
        )
    try:
        _validate_object_prefix(object_prefix)
        manifest = build_bundle_manifest(source_dir)
        if manifest['file_count'] == 0:
            return RoundTripResult(
                status=RoundTripStatus.BLOCKED,
                provider='supabase',
                detail='Source directory is empty — nothing to upload',
                error_class='EmptySource',
            )
        manifest['object_prefix'] = object_prefix
        _validate_bundle_manifest(manifest, expected_object_prefix=object_prefix)
    except BundleValidationError as exc:
        return RoundTripResult(
            status=RoundTripStatus.BLOCKED,
            provider='supabase',
            detail=str(exc),
            error_class=type(exc).__name__,
        )

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode('utf-8')
    manifest_object = f'{object_prefix}/{_BUNDLE_MANIFEST_NAME}'
    uploaded_files: list[str] = []
    try:
        with _storage_credentials(supabase_url=url, service_role_key=key):
            storage_upload_bytes(
                bucket=bucket,
                object_path=manifest_object,
                payload=manifest_bytes,
                content_type='application/json',
            )
            uploaded_files.append(manifest_object)
            for entry in manifest['files']:
                relative = entry['path']
                storage_object = f'{object_prefix}/{relative}'
                storage_upload_bytes(
                    bucket=bucket,
                    object_path=storage_object,
                    payload=(source_dir / relative).read_bytes(),
                    content_type=_content_type_for_path(relative),
                )
                uploaded_files.append(storage_object)
    except (SupabaseError, OSError, BundleValidationError) as exc:
        return RoundTripResult(
            status=RoundTripStatus.BLOCKED,
            provider='supabase',
            detail=f'Bundle upload failed: {exc}',
            uploaded_files=tuple(uploaded_files),
            error_class=type(exc).__name__,
        )
    return RoundTripResult(
        status=RoundTripStatus.SUCCESS,
        provider='supabase',
        detail=(
            f'Bundle upload completed; independent download pending: '
            f'{len(uploaded_files)} objects'
        ),
        uploaded_files=tuple(uploaded_files),
        verified=False,
    )


def download_supabase_bundle(
    output_dir: Path,
    *,
    bucket: str = 'poc-artifacts',
    object_prefix: str,
    supabase_url: str | None = None,
    service_role_key: str | None = None,
) -> RoundTripResult:
    """Download one complete bundle into a clean directory and verify hashes."""
    url = supabase_url or os.environ.get('SUPABASE_URL')
    key = service_role_key or os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        return RoundTripResult(
            status=RoundTripStatus.NOT_RUN,
            provider='supabase',
            detail='SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
        )
    try:
        _validate_object_prefix(object_prefix)
    except BundleValidationError as exc:
        return RoundTripResult(
            status=RoundTripStatus.BLOCKED,
            provider='supabase',
            detail=str(exc),
            error_class=type(exc).__name__,
        )
    if output_dir.exists():
        if output_dir.is_symlink() or not output_dir.is_dir() or any(output_dir.iterdir()):
            return RoundTripResult(
                status=RoundTripStatus.BLOCKED,
                provider='supabase',
                detail='Download output directory must be absent or an empty regular directory',
                error_class='UnsafeOutputDirectory',
            )
    else:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir()

    manifest_object = f'{object_prefix}/{_BUNDLE_MANIFEST_NAME}'
    downloaded_files: list[str] = []
    try:
        with _storage_credentials(supabase_url=url, service_role_key=key):
            manifest_bytes = storage_download_bytes(
                bucket=bucket,
                object_path=manifest_object,
            )
            manifest = _validate_manifest_json_bytes(
                manifest_bytes,
                expected_object_prefix=object_prefix,
            )
            for entry in manifest['files']:
                relative = entry['path']
                local_path = _safe_download_target(output_dir, relative)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                payload = storage_download_bytes(
                    bucket=bucket,
                    object_path=f'{object_prefix}/{relative}',
                )
                local_path.write_bytes(payload)
                downloaded_files.append(f'{object_prefix}/{relative}')
    except (SupabaseError, BundleValidationError, OSError) as exc:
        return RoundTripResult(
            status=RoundTripStatus.BLOCKED,
            provider='supabase',
            detail=f'Bundle download failed: {exc}',
            downloaded_files=tuple(downloaded_files),
            error_class=type(exc).__name__,
        )

    verified, mismatches = verify_bundle(output_dir, manifest)
    return RoundTripResult(
        status=RoundTripStatus.SUCCESS if verified else RoundTripStatus.BLOCKED,
        provider='supabase',
        detail=(
            f'Bundle download and verification {"passed" if verified else "failed"}: '
            f'{len(downloaded_files)} files'
        ),
        downloaded_files=tuple([manifest_object, *downloaded_files]),
        verified=verified,
        sha256_mismatches=tuple(mismatches),
        error_class='' if verified else 'Sha256Mismatch',
    )


# ---------------------------------------------------------------------------
# Supabase round-trip
# ---------------------------------------------------------------------------

def supabase_round_trip(
    source_dir: Path,
    *,
    bucket: str = 'poc-artifacts',
    object_prefix: str = 'poc-round-trip',
    supabase_url: str | None = None,
    service_role_key: str | None = None,
) -> RoundTripResult:
    """Upload all files from source_dir to Supabase Storage, download them back,
    and verify SHA-256 integrity.

    Uses the service role key (JWT) for Storage REST API access.
    Does NOT use the Supabase CLI.
    """
    uploaded = upload_supabase_bundle(
        source_dir,
        bucket=bucket,
        object_prefix=object_prefix,
        supabase_url=supabase_url,
        service_role_key=service_role_key,
    )
    if uploaded.status != RoundTripStatus.SUCCESS:
        return uploaded

    with tempfile.TemporaryDirectory() as tmp:
        downloaded = download_supabase_bundle(
            Path(tmp) / 'downloaded-bundle',
            bucket=bucket,
            object_prefix=object_prefix,
            supabase_url=supabase_url,
            service_role_key=service_role_key,
        )

    return RoundTripResult(
        status=downloaded.status,
        provider='supabase',
        detail=(
            f'Round-trip {"verified" if downloaded.verified else "FAILED"}: '
            f'{len(uploaded.uploaded_files)} uploaded, '
            f'{len(downloaded.downloaded_files)} downloaded'
        ),
        uploaded_files=uploaded.uploaded_files,
        downloaded_files=downloaded.downloaded_files,
        verified=downloaded.verified,
        sha256_mismatches=downloaded.sha256_mismatches,
        error_class=downloaded.error_class,
    )


# ---------------------------------------------------------------------------
# Local-only round-trip (copy + verify, no network)
# ---------------------------------------------------------------------------

def local_round_trip(source_dir: Path) -> RoundTripResult:
    """Copy files to a temp dir and verify SHA-256 integrity.

    This is a no-network fallback that proves the bundle manifest and
    verification logic work correctly without requiring Supabase.
    """
    import shutil

    manifest = build_bundle_manifest(source_dir)
    if manifest['file_count'] == 0:
        return RoundTripResult(
            status=RoundTripStatus.BLOCKED,
            provider='local_only',
            detail='Source directory is empty — nothing to round-trip',
            error_class='EmptySource',
        )

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / 'round_trip'
        dest.mkdir()
        shutil.copytree(source_dir, dest, dirs_exist_ok=True)
        verified, mismatches = verify_bundle(dest, manifest)

    return RoundTripResult(
        status=RoundTripStatus.SUCCESS if verified else RoundTripStatus.BLOCKED,
        provider='local_only',
        detail=f'Local round-trip {"verified" if verified else "FAILED"}: {manifest["file_count"]} files',
        uploaded_files=tuple(f['path'] for f in manifest['files']),
        downloaded_files=tuple(f['path'] for f in manifest['files']),
        verified=verified,
        sha256_mismatches=tuple(mismatches),
        error_class='' if verified else 'Sha256Mismatch',
    )


# ---------------------------------------------------------------------------
# Provider selection and dispatch
# ---------------------------------------------------------------------------

def select_provider(
    *,
    prefer: ArtifactProvider | None = None,
    supabase_preflight_result: PreflightResult | None = None,
) -> ArtifactProvider:
    """Select the artifact provider based on preference and preflight results.

    If Supabase preflight passed, use Supabase.
    If Supabase is blocked or not_run, fall back to local_only.
    """
    if prefer == ArtifactProvider.LOCAL_ONLY:
        return ArtifactProvider.LOCAL_ONLY

    if prefer == ArtifactProvider.SUPABASE:
        if supabase_preflight_result and supabase_preflight_result.is_pass:
            return ArtifactProvider.SUPABASE
        return ArtifactProvider.LOCAL_ONLY

    # Auto-select: prefer Supabase if preflight passed
    if supabase_preflight_result and supabase_preflight_result.is_pass:
        return ArtifactProvider.SUPABASE
    return ArtifactProvider.LOCAL_ONLY


def execute_round_trip(
    source_dir: Path,
    *,
    provider: ArtifactProvider | None = None,
    supabase_preflight_result: PreflightResult | None = None,
    bucket: str = 'poc-artifacts',
    object_prefix: str = 'poc-round-trip',
) -> RoundTripResult:
    """Execute artifact round-trip with the selected provider.

    Falls back to local_only if Supabase is not available.
    """
    selected = select_provider(
        prefer=provider,
        supabase_preflight_result=supabase_preflight_result,
    )

    if selected == ArtifactProvider.SUPABASE:
        return supabase_round_trip(
            source_dir,
            bucket=bucket,
            object_prefix=object_prefix,
        )

    return local_round_trip(source_dir)
