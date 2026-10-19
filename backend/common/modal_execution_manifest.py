"""Modal execution manifest contract and builder.

Every Modal remote function must return a machine-verifiable execution manifest
bound to the run identity, GPU/device evidence, artifact hashes, and secret-
redaction status. This module defines the contract and provides helpers to
collect GPU identity, compute artifact hashes, and assemble the manifest.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence


MODAL_APP_NAME_DEFAULT = 'avalanche-modal-worker'
EXPECTED_MODAL_SDK_VERSION = '0.73.83'
EXPECTED_PYTHON_VERSION_PREFIX = '3.12.'
EXPECTED_TORCH_VERSION_PREFIX = '2.5.1'
EXPECTED_TORCHVISION_VERSION_PREFIX = '0.20.1'
EXPECTED_TORCHAUDIO_VERSION_PREFIX = '2.5.1'
TERMINAL_STATUSES = frozenset({'ok', 'completed_with_validation_gate_failure', 'error', 'failed', 'cancelled', 'not_found', 'timeout'})
NON_TERMINAL_STATUSES = frozenset({'accepted', 'pending', 'running'})
SHA256_PATTERN = re.compile(r'^[0-9a-fA-F]{64}$')
GIT_COMMIT_PATTERN = re.compile(r'^[0-9a-fA-F]{40}$')
VERSION_PATTERN = re.compile(r'^\d+\.\d+(?:\.\d+)?(?:[+.-][A-Za-z0-9._-]+)?$')
UNKNOWN_IDENTITIES = frozenset({'', 'unknown', 'unset', 'none', 'null', 'n/a'})
MAX_CLOCK_SKEW_SECONDS = 300


@dataclass(frozen=True)
class GPUEvidence:
    """GPU identity evidence collected at runtime inside the Modal container."""
    gpu_configured: str = ''
    gpu_device_name: str = ''
    cuda_available: bool = False
    cuda_version: str = ''
    device_count: int = 0
    nvidia_smi_summary: str = ''
    collection_error: str = ''


@dataclass(frozen=True)
class ArtifactDigest:
    """Hash digest of a single artifact file or directory."""
    path: str
    sha256: str
    size_bytes: int
    is_directory: bool = False


@dataclass(frozen=True)
class ModalExecutionManifest:
    """Machine-verifiable manifest produced by every Modal remote function."""
    manifest_version: str
    app_name: str
    function_name: str
    run_id: str
    compute_job_id: str
    call_id: str
    input_manifest_id: str
    input_manifest_hash: str
    source_commit: str
    model_version: str
    shadow_mode: bool
    allow_publish: bool
    terminal_status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    python_version: str
    modal_sdk_version: str
    torch_version: str
    torchvision_version: str
    torchaudio_version: str
    cuda_version: str
    image_identity: str
    image_archive_sha256: str
    repository_digest: str
    artifact_root: str
    volume_name: str
    volume_committed: bool
    gpu_evidence: GPUEvidence
    artifacts: list[ArtifactDigest] = field(default_factory=list)
    cost_estimate: str = ''
    cold_start_seconds: float = 0.0
    secret_redaction_status: str = ''
    official_warning_eligible: bool = False
    error_message: str = ''


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_gpu_evidence(gpu_configured: str = '') -> GPUEvidence:
    """Collect GPU identity evidence from inside the Modal container.

    Uses torch.cuda if available, and nvidia-smi as a secondary source.
    Never raises — returns collection_error on failure.
    """
    device_name = ''
    cuda_available = False
    cuda_version = ''
    device_count = 0
    nvidia_smi_summary = ''
    collection_error = ''

    try:
        import torch  # type: ignore[import-untyped]
        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            device_count = int(torch.cuda.device_count())
            if device_count > 0:
                device_name = str(torch.cuda.get_device_name(0))
                cuda_version = str(torch.version.cuda or '')
    except Exception as exc:
        collection_error = f'torch.cuda probe failed: {exc}'

    try:
        nvidia_smi_path = shutil.which('nvidia-smi')
        if nvidia_smi_path:
            result = subprocess.run(
                [nvidia_smi_path, '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                nvidia_smi_summary = result.stdout.strip()
    except Exception as exc:
        if collection_error:
            collection_error += f'; nvidia-smi probe failed: {exc}'
        else:
            collection_error = f'nvidia-smi probe failed: {exc}'

    return GPUEvidence(
        gpu_configured=gpu_configured,
        gpu_device_name=device_name,
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        device_count=device_count,
        nvidia_smi_summary=nvidia_smi_summary,
        collection_error=collection_error,
    )


def _assert_artifact_path_safe(path: Path, artifact_root: Path | None) -> Path:
    """Reject symlinks and enforce an optional artifact-root containment policy."""
    if path.is_symlink():
        raise ValueError(f'artifact path must not be a symlink: {path}')
    if artifact_root is None:
        return path
    if artifact_root.is_symlink():
        raise ValueError(f'artifact root must not be a symlink: {artifact_root}')
    root = artifact_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f'artifact path escapes artifact root: {path}') from exc
    return resolved


def _iter_regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dir_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in dir_names:
            directory_path = current_path / directory
            if directory_path.is_symlink():
                raise ValueError(f'artifact directory contains a symlink: {directory_path}')
        for filename in file_names:
            file_path = current_path / filename
            if file_path.is_symlink():
                raise ValueError(f'artifact directory contains a symlink: {file_path}')
            if not file_path.is_file():
                raise ValueError(f'artifact entry is not a regular file: {file_path}')
            files.append(file_path)
    return sorted(files)


def compute_artifact_digest(path: Path | str, *, artifact_root: Path | str | None = None) -> ArtifactDigest:
    """Compute a SHA-256 digest while enforcing symlink and root safety."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Artifact path does not exist: {p}')
    root = Path(artifact_root) if artifact_root is not None else None
    safe_path = _assert_artifact_path_safe(p, root)

    if safe_path.is_file():
        data = safe_path.read_bytes()
        return ArtifactDigest(
            path=str(safe_path),
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            is_directory=False,
        )

    hasher = hashlib.sha256()
    total_size = 0
    for file_path in _iter_regular_files(safe_path):
        hasher.update(str(file_path.relative_to(safe_path)).encode('utf-8'))
        hasher.update(b'\0')
        data = file_path.read_bytes()
        hasher.update(data)
        hasher.update(b'\0')
        total_size += len(data)

    return ArtifactDigest(
        path=str(safe_path),
        sha256=hasher.hexdigest(),
        size_bytes=total_size,
        is_directory=True,
    )


def compute_artifact_digests(
    paths: Sequence[Path | str],
    *,
    artifact_root: Path | str | None = None,
) -> list[ArtifactDigest]:
    """Compute digests for multiple artifact paths under one root."""
    return [compute_artifact_digest(p, artifact_root=artifact_root) for p in paths]


def _get_source_commit() -> str:
    """Get the current git source commit, or 'unknown' if not available."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return os.environ.get('MODAL_SOURCE_COMMIT', 'unknown')


def _get_modal_sdk_version() -> str:
    """Get the installed Modal SDK version."""
    try:
        import modal  # type: ignore[import-untyped]
        return str(getattr(modal, '__version__', 'unknown'))
    except Exception:
        return os.environ.get('MODAL_SDK_VERSION', 'unknown')


def _get_torch_version() -> str:
    """Get the installed Torch runtime version."""
    try:
        import torch  # type: ignore[import-untyped]
        return str(getattr(torch, '__version__', 'unknown'))
    except Exception:
        return os.environ.get('TORCH_VERSION', 'unknown')


def _get_torchvision_version() -> str:
    """Get the installed TorchVision runtime version."""
    try:
        import torchvision  # type: ignore[import-untyped]
        return str(getattr(torchvision, '__version__', 'unknown'))
    except Exception:
        return os.environ.get('TORCHVISION_VERSION', 'unknown')


def _get_torchaudio_version() -> str:
    """Get the installed TorchAudio runtime version."""
    try:
        import torchaudio  # type: ignore[import-untyped]
        return str(getattr(torchaudio, '__version__', 'unknown'))
    except Exception:
        return os.environ.get('TORCHAUDIO_VERSION', 'unknown')


def _get_cuda_version() -> str:
    """Get the CUDA runtime version reported by Torch."""
    try:
        import torch  # type: ignore[import-untyped]
        return str(getattr(getattr(torch, 'version', None), 'cuda', None) or 'unknown')
    except Exception:
        return os.environ.get('CUDA_VERSION', 'unknown')


def _get_image_identity() -> str:
    """Get the Modal image identity from environment or return 'unknown'."""
    return os.environ.get('MODAL_IMAGE_IDENTITY', 'unknown')


def _get_image_archive_sha256() -> str:
    """Get the immutable image archive digest from environment."""
    return os.environ.get('MODAL_IMAGE_ARCHIVE_SHA256', 'unknown')


def _get_repository_digest() -> str:
    """Get an optional immutable image repository digest."""
    return os.environ.get('MODAL_IMAGE_REPOSITORY_DIGEST', '')


def _get_volume_name() -> str:
    """Get the Modal volume name from environment or return 'unknown'."""
    return os.environ.get('MODAL_VOLUME_NAME', 'avalanche-artifacts')


def _redaction_status(payload: dict[str, Any]) -> str:
    """Check that no secret-like values appear in the payload.

    Scans string values for patterns that look like Modal tokens, bearer
    tokens, or Supabase keys. Returns 'passed' or 'failed: <details>'.
    """
    secret_patterns = [
        (re.compile(r'mod-[a-zA-Z0-9]{20,}', re.IGNORECASE), 'modal-token'),
        (re.compile(r'sk-[a-zA-Z0-9]{20,}', re.IGNORECASE), 'sk-key'),
        (re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.', re.IGNORECASE), 'jwt-prefix'),
    ]
    sensitive_keys = frozenset({
        'modal_token_id', 'modal_token_secret', 'modal_worker_token',
        'supabase_key', 'supabase_service_key', 'authorization',
        'bearer_token', 'api_key', 'secret',
    })

    def _scan(obj: Any, path: str) -> list[str]:
        violations: list[str] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = str(key).lower()
                child_path = f'{path}.{key}' if path else str(key)
                if key_lower in sensitive_keys and isinstance(value, str) and value.strip():
                    violations.append(f'sensitive key "{child_path}" has non-empty value')
                violations.extend(_scan(value, child_path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                violations.extend(_scan(item, f'{path}[{i}]'))
        elif isinstance(obj, str):
            for pattern, label in secret_patterns:
                if pattern.search(obj):
                    violations.append(f'secret pattern "{label}" found at "{path}"')
        return violations

    violations = _scan(payload, '')
    if violations:
        return 'failed: ' + '; '.join(violations[:3])
    return 'passed'


def build_execution_manifest(
    *,
    function_name: str,
    call_id: str,
    terminal_status: str,
    started_at: str,
    run_id: str = '',
    compute_job_id: str = '',
    input_manifest_id: str = '',
    input_manifest_hash: str = '',
    source_commit: str = '',
    model_version: str = '',
    shadow_mode: bool = True,
    allow_publish: bool = False,
    gpu_configured: str = '',
    artifact_paths: Sequence[Path | str] | None = None,
    artifact_root: Path | str | None = None,
    volume_name: str = '',
    volume_committed: bool = False,
    cold_start_seconds: float = 0.0,
    cost_estimate: str = '',
    completed_at: str | None = None,
    python_version: str = '',
    modal_sdk_version: str = '',
    torch_version: str = '',
    torchvision_version: str = '',
    torchaudio_version: str = '',
    cuda_version: str = '',
    image_identity: str = '',
    image_archive_sha256: str = '',
    repository_digest: str = '',
    error_message: str = '',
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete Modal execution manifest dictionary.

    Runtime identity values are captured from the container when omitted. The
    resulting manifest is deliberately allowed to be invalid so callers can
    inspect and reject it with ``validate_manifest`` before terminal success.
    """
    completed_at = completed_at or _utc_now_iso()
    artifact_root_value = str(artifact_root or os.environ.get('ARTIFACT_ROOT') or 'unknown')
    artifact_root_path = Path(artifact_root_value) if artifact_root_value not in UNKNOWN_IDENTITIES else None
    artifacts = (
        compute_artifact_digests(artifact_paths, artifact_root=artifact_root_path)
        if artifact_paths
        else []
    )
    start_value = str(started_at)
    end_value = str(completed_at)
    try:
        started_dt = datetime.fromisoformat(start_value.replace('Z', '+00:00'))
        completed_dt = datetime.fromisoformat(end_value.replace('Z', '+00:00'))
        duration = (completed_dt - started_dt).total_seconds()
    except (TypeError, ValueError):
        duration = -1.0

    gpu_evidence = collect_gpu_evidence(gpu_configured)
    manifest = ModalExecutionManifest(
        manifest_version='1.1',
        app_name=os.environ.get('MODAL_APP_NAME', MODAL_APP_NAME_DEFAULT),
        function_name=function_name,
        run_id=str(run_id),
        compute_job_id=str(compute_job_id),
        call_id=str(call_id),
        input_manifest_id=str(input_manifest_id),
        input_manifest_hash=str(input_manifest_hash),
        source_commit=str(source_commit or _get_source_commit()),
        model_version=str(model_version),
        shadow_mode=shadow_mode,
        allow_publish=allow_publish,
        terminal_status=terminal_status,
        started_at=start_value,
        completed_at=end_value,
        duration_seconds=round(duration, 3),
        python_version=str(python_version or platform.python_version()),
        modal_sdk_version=str(modal_sdk_version or _get_modal_sdk_version()),
        torch_version=str(torch_version or _get_torch_version()),
        torchvision_version=str(torchvision_version or _get_torchvision_version()),
        torchaudio_version=str(torchaudio_version or _get_torchaudio_version()),
        cuda_version=str(cuda_version or _get_cuda_version()),
        image_identity=str(image_identity or _get_image_identity()),
        image_archive_sha256=str(image_archive_sha256 or _get_image_archive_sha256()),
        repository_digest=str(repository_digest or _get_repository_digest()),
        artifact_root=artifact_root_value,
        volume_name=str(volume_name or _get_volume_name()),
        volume_committed=volume_committed,
        gpu_evidence=gpu_evidence,
        artifacts=artifacts,
        cost_estimate=cost_estimate,
        cold_start_seconds=round(cold_start_seconds, 3),
        secret_redaction_status='',
        official_warning_eligible=False,
        error_message=error_message,
    )

    manifest_dict = asdict(manifest)
    combined = {**manifest_dict, **(extra_payload or {})}
    manifest_dict['secret_redaction_status'] = _redaction_status(combined)
    return manifest_dict


def is_terminal_success(status: str) -> bool:
    """Check if a status string represents a terminal success state."""
    return status in {'ok', 'completed_with_validation_gate_failure'}


def is_terminal_failure(status: str) -> bool:
    """Check if a status string represents a terminal failure state."""
    return status in {'error', 'failed', 'cancelled', 'not_found', 'timeout'}


def is_non_terminal(status: str) -> bool:
    """Check if a status string represents a non-terminal (still running) state."""
    return status in NON_TERMINAL_STATUSES


def _parse_utc(value: Any, field_name: str, violations: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        violations.append(f'{field_name} must be a non-empty ISO-8601 timestamp')
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        violations.append(f'{field_name} is not a valid ISO-8601 timestamp')
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        violations.append(f'{field_name} must be timezone-aware UTC')
        return None
    return parsed.astimezone(timezone.utc)


def _require_identity(manifest: dict[str, Any], field_name: str, violations: list[str]) -> str:
    value = str(manifest.get(field_name) or '').strip()
    if value.lower() in UNKNOWN_IDENTITIES:
        violations.append(f'{field_name} must be a known non-empty identity')
    return value


def validate_manifest(
    manifest: dict[str, Any],
    *,
    expected_run_id: str | None = None,
    expected_call_id: str | None = None,
    expected_compute_job_id: str | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Validate a Modal execution manifest and fail closed on weak identity."""
    violations: list[str] = []
    required_fields = [
        'manifest_version', 'app_name', 'function_name', 'run_id',
        'compute_job_id', 'call_id', 'input_manifest_id', 'input_manifest_hash',
        'source_commit', 'model_version', 'terminal_status', 'started_at',
        'completed_at', 'duration_seconds', 'python_version',
        'modal_sdk_version', 'torch_version', 'torchvision_version',
        'torchaudio_version', 'cuda_version', 'image_identity',
        'image_archive_sha256', 'artifact_root', 'volume_name',
        'volume_committed', 'shadow_mode', 'allow_publish', 'gpu_evidence',
        'secret_redaction_status', 'official_warning_eligible',
    ]
    for field_name in required_fields:
        if field_name not in manifest:
            violations.append(f'missing required field: {field_name}')

    status = str(manifest.get('terminal_status') or '').strip().lower()
    if status in NON_TERMINAL_STATUSES:
        violations.append(f'terminal_status is non-terminal: {status}')
    elif status not in TERMINAL_STATUSES:
        violations.append(f'terminal_status is not recognized: {status}')

    run_id = _require_identity(manifest, 'run_id', violations)
    call_id = _require_identity(manifest, 'call_id', violations)
    compute_job_id = _require_identity(manifest, 'compute_job_id', violations)
    _require_identity(manifest, 'input_manifest_id', violations)
    _require_identity(manifest, 'model_version', violations)
    source_commit = _require_identity(manifest, 'source_commit', violations)
    image_identity = _require_identity(manifest, 'image_identity', violations)
    _require_identity(manifest, 'artifact_root', violations)
    _require_identity(manifest, 'python_version', violations)
    modal_sdk_version = _require_identity(manifest, 'modal_sdk_version', violations)
    torch_version = _require_identity(manifest, 'torch_version', violations)
    torchvision_version = _require_identity(manifest, 'torchvision_version', violations)
    torchaudio_version = _require_identity(manifest, 'torchaudio_version', violations)
    cuda_version = _require_identity(manifest, 'cuda_version', violations)

    if source_commit and not GIT_COMMIT_PATTERN.fullmatch(source_commit):
        violations.append('source_commit must be a 40-character hexadecimal commit')
    if image_identity and image_identity.lower() in UNKNOWN_IDENTITIES:
        violations.append('image_identity must identify an immutable image')
    for field_name in ('input_manifest_hash', 'image_archive_sha256'):
        value = str(manifest.get(field_name) or '')
        if not SHA256_PATTERN.fullmatch(value):
            violations.append(f'{field_name} must be SHA-256')
    if modal_sdk_version and not VERSION_PATTERN.fullmatch(modal_sdk_version):
        violations.append('modal_sdk_version must be an actual version')
    version_fields = (
        ('python_version', str(manifest.get('python_version') or '')),
        ('torch_version', torch_version),
        ('torchvision_version', torchvision_version),
        ('torchaudio_version', torchaudio_version),
        ('cuda_version', cuda_version),
    )
    for field_name, value in version_fields:
        if value and value.lower() not in UNKNOWN_IDENTITIES and not VERSION_PATTERN.fullmatch(value):
            violations.append(f'{field_name} must be a version string')
    if not str(manifest.get('python_version') or '').startswith(EXPECTED_PYTHON_VERSION_PREFIX):
        violations.append(f'python_version must start with {EXPECTED_PYTHON_VERSION_PREFIX}')
    if not torch_version.startswith(EXPECTED_TORCH_VERSION_PREFIX):
        violations.append(f'torch_version must start with {EXPECTED_TORCH_VERSION_PREFIX}')
    if not torchvision_version.startswith(EXPECTED_TORCHVISION_VERSION_PREFIX):
        violations.append(f'torchvision_version must start with {EXPECTED_TORCHVISION_VERSION_PREFIX}')
    if not torchaudio_version.startswith(EXPECTED_TORCHAUDIO_VERSION_PREFIX):
        violations.append(f'torchaudio_version must start with {EXPECTED_TORCHAUDIO_VERSION_PREFIX}')
    if modal_sdk_version != EXPECTED_MODAL_SDK_VERSION:
        violations.append(f'modal_sdk_version must equal {EXPECTED_MODAL_SDK_VERSION}')

    for expected, actual, field_name in (
        (expected_run_id, run_id, 'run_id'),
        (expected_call_id, call_id, 'call_id'),
        (expected_compute_job_id, compute_job_id, 'compute_job_id'),
    ):
        if expected is not None and str(expected) != actual:
            violations.append(f'{field_name} does not match expected identity')

    started = _parse_utc(manifest.get('started_at'), 'started_at', violations)
    completed = _parse_utc(manifest.get('completed_at'), 'completed_at', violations)
    reference_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if started is not None and started > reference_now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        violations.append('started_at is in the future beyond clock skew')
    if completed is not None and completed > reference_now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        violations.append('completed_at is in the future beyond clock skew')
    if started is not None and completed is not None and completed < started:
        violations.append('completed_at must be >= started_at')
    try:
        duration = float(manifest.get('duration_seconds'))
        if duration < 0:
            violations.append('duration_seconds must be non-negative')
        if started is not None and completed is not None and abs(duration - (completed - started).total_seconds()) > 5:
            violations.append('duration_seconds does not match timestamps')
    except (TypeError, ValueError):
        violations.append('duration_seconds must be numeric')

    if manifest.get('allow_publish') is True:
        violations.append('allow_publish must be False for shadow-only POC')
    if manifest.get('official_warning_eligible') is True:
        violations.append('official_warning_eligible must be False')
    if manifest.get('shadow_mode') is not True:
        violations.append('shadow_mode must be True for POC')

    redaction = str(manifest.get('secret_redaction_status') or '')
    if not redaction.startswith('passed'):
        violations.append(f'secret redaction check failed: {redaction}')

    gpu = manifest.get('gpu_evidence') or {}
    if not isinstance(gpu, dict):
        violations.append('gpu_evidence must be an object')
    else:
        gpu_config = str(gpu.get('gpu_configured') or '')
        if gpu_config and not gpu.get('cuda_available'):
            violations.append(f'GPU configured as "{gpu_config}" but cuda_available is False')

    artifact_root_value = str(manifest.get('artifact_root') or '')
    artifact_root = Path(artifact_root_value) if artifact_root_value.lower() not in UNKNOWN_IDENTITIES else None
    if artifact_root is not None:
        try:
            root = artifact_root.resolve(strict=True)
            if artifact_root.is_symlink():
                violations.append('artifact_root must not be a symlink')
            for artifact in manifest.get('artifacts') or []:
                if not isinstance(artifact, dict):
                    violations.append('artifact entry must be an object')
                    continue
                artifact_path = Path(str(artifact.get('path') or ''))
                try:
                    safe_path = _assert_artifact_path_safe(artifact_path, root)
                    if safe_path != artifact_path.resolve(strict=False):
                        violations.append('artifact path resolution is unstable')
                except (OSError, ValueError) as exc:
                    violations.append(str(exc))
                sha = str(artifact.get('sha256') or '')
                if not SHA256_PATTERN.fullmatch(sha):
                    violations.append(f'artifact sha256 is not valid: {sha}')
        except OSError as exc:
            violations.append(f'artifact_root is not usable: {exc}')
    else:
        violations.append('artifact_root must be a known path')

    if status in {'ok', 'completed_with_validation_gate_failure'} and manifest.get('volume_committed') is not True:
        violations.append('successful terminal manifest requires volume_committed=True')
    return violations
