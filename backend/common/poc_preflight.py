"""POC preflight checks for storage providers, Docker, Modal, and disk headroom.

Phase 1 of the Cortex POC audit action plan.

Every unavailable external service must produce an explicit blocked/not_run
result. No preflight may return false success. Secrets are redacted in all
outputs.

Supabase auth note:
  The Supabase CLI login token (sbp_...) is for the Management API (dashboard
  operations like `projects list`). The application uses the
  SUPABASE_SERVICE_ROLE_KEY (JWT) for REST/Storage API calls. These are two
  different auth systems. A CLI "Unauthorized" does NOT mean the service role
  key is invalid for Storage REST calls.

  This preflight tests the actual Storage REST API path using the service role
  key, not the CLI.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import requests

from backend.common.supabase_project_identity import (
    CANONICAL_PROJECT_REF,
    project_ref_from_url,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PreflightStatus(str, Enum):
    PASS = 'pass'
    BLOCKED = 'blocked'
    NOT_RUN = 'not_run'
    SKIPPED = 'skipped'


@dataclass(frozen=True)
class PreflightResult:
    """Result of a single preflight check."""
    check_name: str
    status: PreflightStatus
    detail: str = ''
    http_status: int | None = None
    error_class: str = ''
    redacted: bool = True

    @property
    def is_pass(self) -> bool:
        return self.status == PreflightStatus.PASS

    @property
    def is_blocked(self) -> bool:
        return self.status == PreflightStatus.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            'check_name': self.check_name,
            'status': self.status.value,
            'detail': self.detail,
            'http_status': self.http_status,
            'error_class': self.error_class,
            'redacted': self.redacted,
        }


def _redact(value: str, visible: int = 8) -> str:
    """Redact a secret value, showing only the first `visible` characters."""
    if not value:
        return '<empty>'
    if len(value) <= visible:
        return f'{value[:visible]}***'
    return f'{value[:visible]}...{len(value) - visible} chars redacted'


# ---------------------------------------------------------------------------
# Supabase Storage REST API preflight
# ---------------------------------------------------------------------------

_SUPABASE_STORAGE_TIMEOUT = 15


def supabase_storage_preflight(
    *,
    supabase_url: str | None = None,
    service_role_key: str | None = None,
    expected_project_ref: str | None = None,
    bucket: str = 'poc-artifacts',
) -> PreflightResult:
    """Test Supabase Storage REST API connectivity using the service role key.

    This tests the actual API path used by storage_io.py, not the CLI.
    Classifies failures without retrying auth/quota failures.

    Returns PreflightResult with:
      - PASS: Storage API responded with 200 on bucket list
      - BLOCKED: 401 (auth), 402 (quota), 403 (forbidden), or connection error
      - NOT_RUN: credentials missing
    """
    url = supabase_url or os.environ.get('SUPABASE_URL')
    key = service_role_key or os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

    if not url or not key:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.NOT_RUN,
            detail='SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
        )

    # The restored POC has one canonical target. Callers may supply an
    # explicit expected ref for a negative test or a separately governed
    # environment, but omission must not disable identity enforcement.
    expected = expected_project_ref or CANONICAL_PROJECT_REF
    try:
        actual_ref = project_ref_from_url(url)
    except ValueError:
        actual_ref = ''
    if actual_ref != expected:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail=f'Project ref mismatch: expected {expected}, got {actual_ref}',
            error_class='ProjectRefMismatch',
        )

    storage_url = f"{url.rstrip('/')}/storage/v1/bucket"
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
    }

    try:
        response = requests.get(storage_url, headers=headers, timeout=_SUPABASE_STORAGE_TIMEOUT)
    except requests.Timeout:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail=f'Storage API timed out after {_SUPABASE_STORAGE_TIMEOUT}s',
            error_class='Timeout',
        )
    except requests.ConnectionError as exc:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail=f'Connection error: {exc}',
            error_class='ConnectionError',
        )

    if response.ok:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.PASS,
            detail=f'Storage API reachable, key={_redact(key)}',
            http_status=response.status_code,
        )

    # Classify non-OK responses — no retry on auth/quota
    status = response.status_code
    if status == 401:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail=f'Unauthorized (401): service role key rejected. key={_redact(key)}',
            http_status=401,
            error_class='AuthRejected',
        )
    if status == 402:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail='Payment Required (402): quota or billing restriction. Provider must be repaired.',
            http_status=402,
            error_class='QuotaBlocked',
        )
    if status == 403:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail='Forbidden (403): RLS or policy blocking service role access.',
            http_status=403,
            error_class='Forbidden',
        )
    if status == 404:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail=f'Not Found (404): {url} may be wrong project or paused.',
            http_status=404,
            error_class='NotFound',
        )
    if 500 <= status < 600:
        return PreflightResult(
            check_name='supabase_storage',
            status=PreflightStatus.BLOCKED,
            detail=f'Server error ({status}): {response.text[:200]}',
            http_status=status,
            error_class='ServerError',
        )

    return PreflightResult(
        check_name='supabase_storage',
        status=PreflightStatus.BLOCKED,
        detail=f'Unexpected status {status}: {response.text[:200]}',
        http_status=status,
        error_class='UnexpectedStatus',
    )


# ---------------------------------------------------------------------------
# Supabase project identity check
# ---------------------------------------------------------------------------

def supabase_project_identity_check(
    *,
    supabase_url: str | None = None,
    expected_project_ref: str | None = None,
) -> PreflightResult:
    """Verify that the configured Supabase URL matches the expected project ref."""
    url = supabase_url or os.environ.get('SUPABASE_URL')
    expected = expected_project_ref or os.environ.get('SUPABASE_PROJECT_REF') or CANONICAL_PROJECT_REF

    if not url:
        return PreflightResult(
            check_name='supabase_project_identity',
            status=PreflightStatus.NOT_RUN,
            detail='SUPABASE_URL not set',
        )
    if not expected:
        return PreflightResult(
            check_name='supabase_project_identity',
            status=PreflightStatus.NOT_RUN,
            detail='Expected project ref not supplied',
        )

    try:
        actual_ref = project_ref_from_url(url)
    except ValueError:
        actual_ref = ''

    if actual_ref == expected:
        return PreflightResult(
            check_name='supabase_project_identity',
            status=PreflightStatus.PASS,
            detail=f'Project ref matches: {expected}',
        )

    return PreflightResult(
        check_name='supabase_project_identity',
        status=PreflightStatus.BLOCKED,
        detail=f'Project ref mismatch: URL has {actual_ref}, expected {expected}',
        error_class='ProjectRefMismatch',
    )


# ---------------------------------------------------------------------------
# Docker preflight
# ---------------------------------------------------------------------------

def docker_daemon_preflight(
    *,
    min_disk_gb: float = 5.0,
) -> PreflightResult:
    """Check Docker daemon reachability, API version, and disk headroom.

    Returns BLOCKED if Docker is not reachable or disk space is below minimum.
    """
    docker_path = shutil.which('docker')
    if not docker_path:
        return PreflightResult(
            check_name='docker_daemon',
            status=PreflightStatus.BLOCKED,
            detail='docker binary not found in PATH',
            error_class='DockerNotFound',
        )

    try:
        result = subprocess.run(
            ['docker', 'version', '--format', '{{.Server.Version}}'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return PreflightResult(
            check_name='docker_daemon',
            status=PreflightStatus.BLOCKED,
            detail='docker version timed out (daemon may not be running)',
            error_class='DockerTimeout',
        )

    if result.returncode != 0:
        return PreflightResult(
            check_name='docker_daemon',
            status=PreflightStatus.BLOCKED,
            detail=f'docker version failed: {result.stderr.strip()[:200]}',
            error_class='DockerDaemonUnreachable',
        )

    version = result.stdout.strip()

    # Check disk headroom
    disk_result = _disk_headroom_check(min_gb=min_disk_gb)
    if disk_result.is_blocked:
        return PreflightResult(
            check_name='docker_daemon',
            status=PreflightStatus.BLOCKED,
            detail=f'Docker {version} reachable but disk headroom insufficient: {disk_result.detail}',
            error_class='InsufficientDiskHeadroom',
        )

    return PreflightResult(
        check_name='docker_daemon',
        status=PreflightStatus.PASS,
        detail=f'Docker {version} reachable, disk headroom OK ({disk_result.detail})',
    )


def docker_system_df() -> dict[str, Any] | None:
    """Run `docker system df` and return parsed output.

    Returns None if Docker is not available.
    """
    docker_path = shutil.which('docker')
    if not docker_path:
        return None

    try:
        result = subprocess.run(
            ['docker', 'system', 'df', '--format', '{{json .}}'],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None

    if result.returncode != 0:
        return None

    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    import json
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return entries if entries else None


# ---------------------------------------------------------------------------
# Disk headroom check
# ---------------------------------------------------------------------------

def _disk_headroom_check(*, min_gb: float = 5.0, path: str = '/') -> PreflightResult:
    """Check available disk space against minimum threshold."""
    stat = shutil.disk_usage(path)
    free_gb = stat.free / (1024 ** 3)
    if free_gb < min_gb:
        return PreflightResult(
            check_name='disk_headroom',
            status=PreflightStatus.BLOCKED,
            detail=f'{free_gb:.1f} GB free at {path}, need {min_gb:.1f} GB',
            error_class='InsufficientDisk',
        )
    return PreflightResult(
        check_name='disk_headroom',
        status=PreflightStatus.PASS,
        detail=f'{free_gb:.1f} GB free at {path}',
    )


def disk_preflight(*, min_gb: float = 5.0, path: str = '/') -> PreflightResult:
    """Public disk headroom preflight."""
    return _disk_headroom_check(min_gb=min_gb, path=path)


# ---------------------------------------------------------------------------
# Modal preflight
# ---------------------------------------------------------------------------

def modal_preflight(
    *,
    modal_token_id: str | None = None,
    modal_token_secret: str | None = None,
    modal_worker_url: str | None = None,
) -> PreflightResult:
    """Check Modal credentials and endpoint availability.

    Returns NOT_RUN if credentials are missing — never false success.
    Returns BLOCKED if credentials exist but endpoint is unreachable.
    """
    token_id = modal_token_id or os.environ.get('MODAL_TOKEN_ID')
    token_secret = modal_token_secret or os.environ.get('MODAL_TOKEN_SECRET')
    worker_url = modal_worker_url or os.environ.get('MODAL_WORKER_URL')

    if not token_id or not token_secret:
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.NOT_RUN,
            detail='MODAL_TOKEN_ID or MODAL_TOKEN_SECRET not set',
        )

    if not worker_url:
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.NOT_RUN,
            detail='MODAL_WORKER_URL not set',
        )

    # Light endpoint check — just verify it resolves, don't submit a job
    try:
        response = requests.get(
            worker_url,
            timeout=10,
            allow_redirects=False,
        )
    except requests.Timeout:
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.BLOCKED,
            detail=f'Modal endpoint timed out: {worker_url}',
            error_class='ModalTimeout',
        )
    except requests.ConnectionError as exc:
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.BLOCKED,
            detail=f'Modal endpoint unreachable: {exc}',
            error_class='ModalConnectionError',
        )

    # 401/403 means endpoint exists but auth is needed — that's expected for a protected API
    if response.status_code in (401, 403):
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.PASS,
            detail=f'Modal endpoint reachable (auth required, {response.status_code}). token_id={_redact(token_id)}',
            http_status=response.status_code,
        )

    if response.ok:
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.PASS,
            detail=f'Modal endpoint reachable: {worker_url}',
            http_status=response.status_code,
        )

    if 500 <= response.status_code < 600:
        return PreflightResult(
            check_name='modal',
            status=PreflightStatus.BLOCKED,
            detail=f'Modal server error ({response.status_code})',
            http_status=response.status_code,
            error_class='ModalServerError',
        )

    return PreflightResult(
        check_name='modal',
        status=PreflightStatus.BLOCKED,
        detail=f'Modal endpoint returned {response.status_code}',
        http_status=response.status_code,
        error_class='ModalUnexpectedStatus',
    )


# ---------------------------------------------------------------------------
# Unified preflight runner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PreflightReport:
    """Aggregated preflight results for all POC infrastructure."""
    results: tuple[PreflightResult, ...]
    overall_status: PreflightStatus

    @property
    def all_pass(self) -> bool:
        return all(r.is_pass for r in self.results)

    @property
    def any_blocked(self) -> bool:
        return any(r.is_blocked for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            'overall_status': self.overall_status.value,
            'checks': [r.to_dict() for r in self.results],
        }

    def summary(self) -> str:
        lines = [f'POC Preflight Report — overall: {self.overall_status.value}']
        for r in self.results:
            icon = '✓' if r.is_pass else ('✗' if r.is_blocked else '○')
            lines.append(f'  {icon} {r.check_name}: {r.status.value} — {r.detail}')
        return '\n'.join(lines)


def run_all_preflights(
    *,
    expected_supabase_project_ref: str | None = None,
    supabase_bucket: str = 'poc-artifacts',
    min_disk_gb: float = 5.0,
    check_modal: bool = True,
    check_docker: bool = True,
) -> PreflightReport:
    """Run all POC preflight checks and return an aggregated report.

    The overall status is:
      - PASS if all checks pass
      - BLOCKED if any check is blocked
      - NOT_RUN if no checks are blocked but some are not_run
    """
    results: list[PreflightResult] = []

    # Supabase checks
    results.append(supabase_project_identity_check(
        expected_project_ref=expected_supabase_project_ref,
    ))
    results.append(supabase_storage_preflight(
        expected_project_ref=expected_supabase_project_ref,
        bucket=supabase_bucket,
    ))

    # Disk check
    results.append(disk_preflight(min_gb=min_disk_gb))

    # Docker check
    if check_docker:
        results.append(docker_daemon_preflight(min_disk_gb=min_disk_gb))
    else:
        results.append(PreflightResult(
            check_name='docker_daemon',
            status=PreflightStatus.SKIPPED,
            detail='Docker check skipped by caller',
        ))

    # Modal check
    if check_modal:
        results.append(modal_preflight())
    else:
        results.append(PreflightResult(
            check_name='modal',
            status=PreflightStatus.SKIPPED,
            detail='Modal check skipped by caller',
        ))

    # Determine overall status
    if all(r.is_pass for r in results):
        overall = PreflightStatus.PASS
    elif any(r.is_blocked for r in results):
        overall = PreflightStatus.BLOCKED
    else:
        overall = PreflightStatus.NOT_RUN

    return PreflightReport(
        results=tuple(results),
        overall_status=overall,
    )
