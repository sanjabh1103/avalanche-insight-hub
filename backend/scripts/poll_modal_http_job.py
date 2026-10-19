"""Submit and prove terminal completion of an authenticated Modal HTTP job.

This wrapper is used by GitHub Actions Modal jobs. It persists the initial
submission response separately from the terminal response, polls until a
terminal state, and rejects terminal success without a valid execution
manifest and artifact digest.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.common.modal_execution_manifest import (
    is_non_terminal,
    is_terminal_success,
    validate_manifest,
)


DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 3600
TERMINAL_FAILURE_STATUSES = frozenset({'error', 'failed', 'cancelled', 'not_found', 'timeout'})
RequestFn = Callable[[str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]]
PollerFn = Callable[[str], tuple[int, dict[str, Any]]]


class ModalJobError(RuntimeError):
    """Raised when a Modal job cannot produce terminal proof."""


def _reject_whitespace(value: str, field_name: str) -> str:
    """A10: Reject identity fields with leading/trailing whitespace.

    Trust-anchor strings (run_id, compute_job_id, call_id) must not have
    whitespace — silently stripping could mask injection or spoofing.
    """
    if value != value.strip():
        raise ModalJobError(
            f'{field_name} must not have leading or trailing whitespace, got {value!r}'
        )
    return value


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _validate_response_shape(
    response: Any,
    *,
    context: str,
) -> tuple[int, dict[str, Any]]:
    """A6: Validate that a requester/poller response is a 2-tuple of (int, dict).

    Prevents raw ValueError/TypeError from tuple unpacking when the response
    is None, a 1-tuple, a 3-tuple, a string, or any other malformed shape.
    """
    if response is None:
        raise ModalJobError(f'{context} returned None, expected (int, dict)')
    if not isinstance(response, tuple):
        raise ModalJobError(
            f'{context} must return a 2-tuple (int, dict), got '
            f'{type(response).__name__}: {response!r}'
        )
    if len(response) != 2:
        raise ModalJobError(
            f'{context} must return exactly 2 values, got {len(response)}: '
            f'{response!r}'
        )
    status_code, body = response
    if type(status_code) is not int:
        raise ModalJobError(
            f'{context} status_code must be an integer, got '
            f'{type(status_code).__name__}: {status_code!r}'
        )
    if not isinstance(body, dict):
        raise ModalJobError(
            f'{context} body must be a dict, got '
            f'{type(body).__name__}: {body!r}'
        )
    return status_code, body


def _http_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    *,
    worker_token: str,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, sort_keys=True).encode('utf-8')
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {worker_token}',
    }
    if body is not None:
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=300) as response:  # nosec B310 - worker_url is scheme-validated in run_job
            # C0.7: Strict UTF-8 decoding for success responses too
            try:
                raw = response.read().decode('utf-8')
            except UnicodeDecodeError:
                raise ModalJobError('Modal HTTP success body is not valid UTF-8') from None
            # A2: urllib response.status is always int, but verify to prevent
            # silent float-to-int conversion if the HTTP library changes.
            if type(response.status) is not int:
                raise ModalJobError(
                    f'HTTP response status must be an integer, got '
                    f'{type(response.status).__name__}: {response.status!r}'
                )
            status_code = response.status
    except HTTPError as exc:
        # C0.7: Use strict UTF-8 decoding — errors='replace' masks malformed responses
        try:
            raw = exc.read().decode('utf-8')
        except UnicodeDecodeError:
            raise ModalJobError('Modal HTTP error body is not valid UTF-8') from None
        # A2: Same strict type check for error responses.
        if type(exc.code) is not int:
            raise ModalJobError(
                f'HTTP error code must be an integer, got '
                f'{type(exc.code).__name__}: {exc.code!r}'
            )
        status_code = exc.code
    except URLError as exc:
        raise ModalJobError(f'Modal HTTP request failed: {exc.reason}') from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModalJobError(f'Modal response was not JSON (HTTP {status_code})') from exc
    if not isinstance(parsed, dict):
        raise ModalJobError(f'Modal response was not a JSON object (HTTP {status_code})')
    return status_code, parsed


def poll_until_terminal(
    poller: PollerFn,
    *,
    call_id: str,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Poll until a terminal body status; HTTP 200 is not sufficient.

    G6: Validates call_id independently for defense in depth — even if the
    caller bypasses run_job() and calls poll_until_terminal() directly.
    G8: Requires poller response body to be a dict before calling .get().
    G9: Requires timeout and poll_interval to be non-negative integers.
    """
    # G6: Defense-in-depth — validate call_id before it reaches the poller.
    _validate_safe_identity(call_id, 'call_id')
    # P2/G9: Require exact int types for timeout and poll_interval — do not
    # silently truncate floats or convert numeric strings.
    if type(timeout_seconds) is not int:
        raise ModalJobError(
            f'timeout_seconds must be an integer, got {type(timeout_seconds).__name__}: '
            f'{timeout_seconds!r}'
        )
    if type(poll_interval_seconds) is not int:
        raise ModalJobError(
            f'poll_interval_seconds must be an integer, got {type(poll_interval_seconds).__name__}: '
            f'{poll_interval_seconds!r}'
        )
    if timeout_seconds < 1:
        raise ModalJobError(f'timeout_seconds must be >= 1, got {timeout_seconds}')
    if poll_interval_seconds < 0:
        raise ModalJobError(f'poll_interval_seconds must be >= 0, got {poll_interval_seconds}')
    deadline = time.monotonic() + timeout_seconds
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f'Modal call {call_id} exceeded {timeout_seconds}s timeout')
        status_code, body = _validate_response_shape(
            poller(call_id),
            context='poller response',
        )
        raw_body_status = body.get('status')
        if not isinstance(raw_body_status, str):
            raise ModalJobError(
                f'poller response status must be a string, got '
                f'{type(raw_body_status).__name__}: {raw_body_status!r}'
            )
        body_status = raw_body_status.strip().lower()
        if status_code == 202 or is_non_terminal(body_status):
            time.sleep(poll_interval_seconds)
            continue
        if status_code < 200 or status_code >= 300:
            raise ModalJobError(f'Modal poll failed with HTTP {status_code}')
        if not body_status:
            raise ModalJobError('Modal terminal response is missing status')
        if body_status in TERMINAL_FAILURE_STATUSES:
            return body
        if is_terminal_success(body_status):
            return body
        raise ModalJobError(f'Modal response has unrecognized terminal status: {body_status}')


_SAFE_ID_PATTERN = re.compile(r'^[A-Za-z0-9._:-]{1,256}$')
# P2/G2: Reject dot-only segments that are valid path traversal tokens.
# '.', '..', and '...' are accepted by the regex but are dangerous when
# interpolated into URLs or file paths.
_DOT_ONLY_PATTERN = re.compile(r'^\.+$')

# P2/G3: Shared route allowlist — used by both argparse choices and run_job.
# This prevents programmatic callers from bypassing the CLI allowlist.
SUPPORTED_ROUTES = frozenset(('sar-segment', 'train-sar-unet', 'train-mtslstm', 'infer-mtslstm', 'evaluate-release'))


def _validate_safe_identity(value: str, field_name: str) -> None:
    """G8/G2/G4/G5: Validate safe ID syntax, type, and path-segment semantics.

    Rejects:
    - Non-string types (None, int, list, etc.) — G4
    - Empty strings — G4
    - Strings exceeding 256 characters — G8
    - Strings with characters outside [A-Za-z0-9._:-] — G8
    - Dot-only segments (., .., ...) — G2 path traversal
    - Strings containing path separators (/) or URL delimiters (?, #) — G2
    """
    # G4: Type check BEFORE any string method call — prevents AttributeError.
    if not isinstance(value, str):
        raise ModalJobError(
            f'{field_name} must be a string, got {type(value).__name__}: {value!r}'
        )
    if not value or not _SAFE_ID_PATTERN.fullmatch(value):
        raise ModalJobError(
            f'{field_name} must be a non-empty string of at most 256 characters '
            f'containing only [A-Za-z0-9._:-], got {value!r}'
        )
    # G2: Reject dot-only segments — these are path traversal tokens.
    if _DOT_ONLY_PATTERN.fullmatch(value):
        raise ModalJobError(
            f'{field_name} must not be a dot-only segment (., .., ...), got {value!r}'
        )


def _validate_submission_contract(
    submission: dict[str, Any],
    *,
    expected_run_id: str,
    expected_compute_job_id: str,
) -> str:
    """Validate the submission response and return the provider call_id.

    G6: Require an explicit 'accepted' submission status. A bare HTTP 200 with
    a call_id is not sufficient — the provider must acknowledge the job.
    G2: Validate run_id and compute_job_id against independently supplied
    pre-submission values, never against the terminal response itself.
    G9: Require all top-level identity fields (run_id, compute_job_id, call_id)
    at submission. A response that omits them is rejected even if the manifest
    would contain them.
    P1/G10: Require status to be a string — do not str()-coerce non-string types.
    """
    # P1/G10: Require status to be a string — do not str()-coerce.
    raw_submission_status = submission.get('status')
    if not isinstance(raw_submission_status, str):
        raise ModalJobError(
            f'Modal submission status must be a string, got '
            f'{type(raw_submission_status).__name__}: {raw_submission_status!r}'
        )
    submission_status = raw_submission_status.strip().lower()
    if submission_status != 'accepted':
        raise ModalJobError(
            f'Modal submission status must be "accepted", got {submission_status!r}'
        )
    # G5: Require provider call_id to already be a string — do not silently
    # stringify non-string values (e.g. 123 → '123', True → 'True').
    raw_call_id = submission.get('call_id')
    if not isinstance(raw_call_id, str):
        raise ModalJobError(
            f'Modal submission call_id must be a string, got '
            f'{type(raw_call_id).__name__}: {raw_call_id!r}'
        )
    call_id = _reject_whitespace(raw_call_id, 'submission call_id')
    if not call_id:
        raise ModalJobError('Modal submission did not return call_id')
    # G8: Validate call_id syntax — it is interpolated into the poll URL
    # (f'{worker_url}/{route}/result/{call_id}') and must not contain path
    # traversal sequences like ../escape, query/fragment injectors, or
    # overlength values. A compromised provider could return a malicious ID.
    _validate_safe_identity(call_id, 'call_id')
    # G5/G9: Require run_id at submission — must be a string, not optional.
    raw_run_id = submission.get('run_id')
    if not isinstance(raw_run_id, str):
        raise ModalJobError(
            f'Modal submission run_id must be a string, got '
            f'{type(raw_run_id).__name__}: {raw_run_id!r}'
        )
    submission_run_id = _reject_whitespace(raw_run_id, 'submission run_id')
    if not submission_run_id:
        raise ModalJobError('Modal submission did not return run_id')
    if submission_run_id != expected_run_id:
        raise ModalJobError(
            f'submission run_id mismatch: expected={expected_run_id!r}, '
            f'got={submission_run_id!r}'
        )
    # G5/G9: Require compute_job_id at submission — must be a string.
    raw_compute_id = submission.get('compute_job_id')
    if not isinstance(raw_compute_id, str):
        raise ModalJobError(
            f'Modal submission compute_job_id must be a string, got '
            f'{type(raw_compute_id).__name__}: {raw_compute_id!r}'
        )
    submission_compute_id = _reject_whitespace(raw_compute_id, 'submission compute_job_id')
    if not submission_compute_id:
        raise ModalJobError('Modal submission did not return compute_job_id')
    if submission_compute_id != expected_compute_job_id:
        raise ModalJobError(
            f'submission compute_job_id mismatch: expected={expected_compute_job_id!r}, '
            f'got={submission_compute_id!r}'
        )
    return call_id


def _validate_terminal_result(
    terminal: dict[str, Any],
    *,
    run_id: str,
    call_id: str,
    expected_compute_job_id: str,
) -> None:
    # P1/G6: Require terminal call_id to be a string — do not str()-coerce.
    raw_terminal_call_id = terminal.get('call_id')
    if not isinstance(raw_terminal_call_id, str):
        raise ModalJobError(
            f'terminal response call_id must be a string, got '
            f'{type(raw_terminal_call_id).__name__}: {raw_terminal_call_id!r}'
        )
    if _reject_whitespace(raw_terminal_call_id, 'terminal call_id') != call_id:
        raise ModalJobError('terminal response call_id does not match submission')
    # Status field — check type before str() coercion for status comparison.
    raw_status = terminal.get('status')
    if not isinstance(raw_status, str):
        raise ModalJobError(
            f'terminal response status must be a string, got '
            f'{type(raw_status).__name__}: {raw_status!r}'
        )
    if not is_terminal_success(raw_status.strip().lower()):
        raise ModalJobError(
            f'Modal job did not complete successfully: {raw_status or "missing status"}'
        )
    # G9: Require top-level run_id at terminal — must be a string.
    raw_terminal_run_id = terminal.get('run_id')
    if not isinstance(raw_terminal_run_id, str):
        raise ModalJobError(
            f'terminal response run_id must be a string, got '
            f'{type(raw_terminal_run_id).__name__}: {raw_terminal_run_id!r}'
        )
    terminal_run_id = _reject_whitespace(raw_terminal_run_id, 'terminal run_id')
    if not terminal_run_id:
        raise ModalJobError('terminal response is missing top-level run_id')
    if terminal_run_id != run_id:
        raise ModalJobError(
            f'terminal run_id mismatch: expected={run_id!r}, got={terminal_run_id!r}'
        )
    # G2: Validate terminal compute_job_id — must be a string.
    raw_terminal_compute_id = terminal.get('compute_job_id')
    if not isinstance(raw_terminal_compute_id, str):
        raise ModalJobError(
            f'terminal response compute_job_id must be a string, got '
            f'{type(raw_terminal_compute_id).__name__}: {raw_terminal_compute_id!r}'
        )
    terminal_compute_id = _reject_whitespace(raw_terminal_compute_id, 'terminal compute_job_id')
    if not terminal_compute_id:
        raise ModalJobError('terminal response is missing top-level compute_job_id')
    if terminal_compute_id != expected_compute_job_id:
        raise ModalJobError(
            f'terminal compute_job_id mismatch: expected={expected_compute_job_id!r}, '
            f'got={terminal_compute_id!r}'
        )
    manifest = terminal.get('execution_manifest')
    if not isinstance(manifest, dict):
        raise ModalJobError('terminal response is missing execution_manifest')
    # G2: Validate manifest IDs against the same independent pre-submission values.
    violations = validate_manifest(
        manifest,
        expected_run_id=run_id,
        expected_call_id=call_id,
        expected_compute_job_id=expected_compute_job_id,
    )
    if violations:
        raise ModalJobError('execution manifest validation failed: ' + '; '.join(violations))
    if not manifest.get('artifacts'):
        raise ModalJobError('terminal execution manifest contains no artifact digests')


def run_job(
    *,
    worker_url: str,
    worker_token: str,
    route: str,
    payload: dict[str, Any],
    request: RequestFn | None = None,
    submission_output: Path | None = None,
    terminal_output: Path | None = None,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    expected_run_id: str | None = None,
    expected_compute_job_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Submit, poll, validate, and persist one Modal job.

    G2/G6: The expected_run_id and expected_compute_job_id are captured
    BEFORE the POST request and used as independent trust anchors for
    submission, terminal, and manifest validation. They are never derived
    from the terminal response itself.
    """
    # G4: Validate types BEFORE calling .strip() or dict() — prevents
    # AttributeError on non-string types (None, int, list).
    if not isinstance(worker_url, str):
        raise ModalJobError(f'worker_url must be a string, got {type(worker_url).__name__}: {worker_url!r}')
    if not isinstance(worker_token, str):
        raise ModalJobError(f'worker_token must be a string, got {type(worker_token).__name__}: {worker_token!r}')
    if not isinstance(route, str):
        raise ModalJobError(f'route must be a string, got {type(route).__name__}: {route!r}')
    if not isinstance(payload, dict):
        raise ModalJobError(f'payload must be a dict, got {type(payload).__name__}: {payload!r}')
    # P1/G9: Validate timeout and poll_interval BEFORE any network call.
    # This prevents a POST request from being sent when parameters are invalid.
    if type(timeout_seconds) is not int:
        raise ModalJobError(
            f'timeout_seconds must be an integer, got {type(timeout_seconds).__name__}: '
            f'{timeout_seconds!r}'
        )
    if type(poll_interval_seconds) is not int:
        raise ModalJobError(
            f'poll_interval_seconds must be an integer, got {type(poll_interval_seconds).__name__}: '
            f'{poll_interval_seconds!r}'
        )
    if timeout_seconds < 1:
        raise ModalJobError(f'timeout_seconds must be >= 1, got {timeout_seconds}')
    if poll_interval_seconds < 0:
        raise ModalJobError(f'poll_interval_seconds must be >= 0, got {poll_interval_seconds}')
    if not worker_url.strip() or not worker_token.strip():
        raise ModalJobError('MODAL_WORKER_URL and MODAL_WORKER_TOKEN are required')
    parsed_url = urlparse(worker_url)
    if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
        raise ModalJobError('MODAL_WORKER_URL must be an absolute http or https URL')
    payload = dict(payload)
    payload.setdefault('source_commit', os.environ.get('GITHUB_SHA', ''))
    payload.setdefault('input_manifest_id', os.environ.get('MODAL_INPUT_MANIFEST_ID', ''))
    payload.setdefault('input_manifest_hash', os.environ.get('MODAL_INPUT_MANIFEST_SHA256', ''))
    payload.setdefault('model_version', os.environ.get('MODAL_MODEL_VERSION', ''))
    # P1/G4: Require payload.run_id to already be a string — do not str()-coerce.
    raw_payload_run_id = payload.get('run_id')
    if raw_payload_run_id is not None and not isinstance(raw_payload_run_id, str):
        raise ModalJobError(
            f'payload.run_id must be a string, got {type(raw_payload_run_id).__name__}: '
            f'{raw_payload_run_id!r}'
        )
    run_id = _reject_whitespace(raw_payload_run_id or '', 'payload.run_id')
    if not run_id:
        raise ModalJobError('payload.run_id is required for terminal proof')
    # P1/G5: Type-check expected_run_id — must be a string if supplied.
    if expected_run_id is not None and not isinstance(expected_run_id, str):
        raise ModalJobError(
            f'expected_run_id must be a string, got {type(expected_run_id).__name__}: '
            f'{expected_run_id!r}'
        )
    # G2: Capture the independent expected_run_id BEFORE submission. If the
    # caller does not supply one, use the payload run_id as the trust anchor.
    independent_run_id = _reject_whitespace(expected_run_id or run_id, 'expected_run_id')
    if not independent_run_id:
        raise ModalJobError('expected_run_id is required for terminal proof')
    # G8: Reject payload/CLI run-ID disagreement instead of silently overwriting.
    if expected_run_id and _reject_whitespace(expected_run_id, 'expected_run_id') != run_id:
        raise ModalJobError(
            f'payload run_id ({run_id!r}) does not match --expected-run-id '
            f'({expected_run_id!r}); refusing to silently overwrite'
        )
    # P1/G4: Require payload.compute_job_id to already be a string.
    raw_payload_compute_id = payload.get('compute_job_id')
    if raw_payload_compute_id is not None and not isinstance(raw_payload_compute_id, str):
        raise ModalJobError(
            f'payload.compute_job_id must be a string, got {type(raw_payload_compute_id).__name__}: '
            f'{raw_payload_compute_id!r}'
        )
    payload_compute_id = _reject_whitespace(raw_payload_compute_id or '', 'payload.compute_job_id')
    # P1/G5: Type-check expected_compute_job_id.
    if expected_compute_job_id is not None and not isinstance(expected_compute_job_id, str):
        raise ModalJobError(
            f'expected_compute_job_id must be a string, got {type(expected_compute_job_id).__name__}: '
            f'{expected_compute_job_id!r}'
        )
    compute_job_id = _reject_whitespace(
        expected_compute_job_id or payload_compute_id or '',
        'compute_job_id',
    )
    # G8: Reject payload/CLI compute-ID disagreement.
    if expected_compute_job_id and payload_compute_id and _reject_whitespace(expected_compute_job_id, 'expected_compute_job_id') != payload_compute_id:
        raise ModalJobError(
            f'payload compute_job_id ({payload_compute_id!r}) does not match '
            f'--expected-compute-job-id ({expected_compute_job_id!r}); refusing to silently overwrite'
        )
    if not compute_job_id:
        # Generate a deterministic client compute ID from run_id + route so
        # the submission, terminal, and manifest all bind to the same value.
        compute_job_id = f'client-{independent_run_id}-{route}'
    # G8: Validate safe ID syntax and maximum length (reject injection attempts).
    _validate_safe_identity(independent_run_id, 'run_id')
    _validate_safe_identity(compute_job_id, 'compute_job_id')
    # Set the payload IDs to the independently captured values (these are the
    # same values — we only set them if they were generated, not if they disagreed).
    payload['compute_job_id'] = compute_job_id
    payload['run_id'] = independent_run_id
    # P2/G7: Reject leading/trailing slashes and surrounding whitespace instead
    # of silently normalizing them. A caller passing '/sar-segment/' or
    # ' sar-segment ' should get an error, not a silent fix.
    if route != route.strip():
        raise ModalJobError(
            f'route must not have leading or trailing whitespace, got {route!r}'
        )
    if route.startswith('/') or route.endswith('/'):
        raise ModalJobError(
            f'route must not have leading or trailing slashes, got {route!r}'
        )
    if not route:
        raise ModalJobError('route is required')
    # G8: Validate route syntax — it is interpolated into the submission and
    # poll URLs. The CLI argparse uses choices=() but run_job may be called
    # programmatically with an unsafe route (e.g. '../admin/delete').
    _validate_safe_identity(route, 'route')
    # G3: Semantic route validation — reject routes that are not in the
    # shared SUPPORTED_ROUTES allowlist. This prevents programmatic callers
    # from bypassing the CLI argparse choices constraint.
    if route not in SUPPORTED_ROUTES:
        raise ModalJobError(
            f'route {route!r} is not supported. Allowed routes: '
            f'{sorted(SUPPORTED_ROUTES)}'
        )
    requester = request or (lambda method, url, body: _http_request(method, url, body, worker_token=worker_token))

    submission_status, submission = _validate_response_shape(
        requester('POST', f'{worker_url.rstrip("/")}/{route}', payload),
        context='submission response',
    )
    if submission_status < 200 or submission_status >= 300:
        raise ModalJobError(f'Modal submission failed with HTTP {submission_status}')
    # G6: Validate the submission contract against independent pre-submission
    # values. Require explicit 'accepted' status.
    call_id = _validate_submission_contract(
        submission,
        expected_run_id=independent_run_id,
        expected_compute_job_id=compute_job_id,
    )
    _write_json(submission_output, submission)

    def _poll(call: str) -> tuple[int, dict[str, Any]]:
        return requester('GET', f'{worker_url.rstrip("/")}/{route}/result/{call}', None)

    try:
        terminal = poll_until_terminal(
            _poll,
            call_id=call_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )
    except TimeoutError:
        raise
    _validate_terminal_result(
        terminal,
        run_id=independent_run_id,
        call_id=call_id,
        expected_compute_job_id=compute_job_id,
    )
    _write_json(terminal_output, terminal)
    return submission, terminal


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Submit and prove one Modal HTTP job')
    parser.add_argument('--route', required=True, choices=sorted(SUPPORTED_ROUTES))
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--submission-output', type=Path, required=True)
    parser.add_argument('--terminal-output', type=Path, required=True)
    parser.add_argument('--poll-interval-seconds', type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument('--expected-run-id', default='',
                        help='Independent run ID trust anchor (defaults to payload.run_id)')
    parser.add_argument('--expected-compute-job-id', default='',
                        help='Independent compute job ID trust anchor')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = json.loads(args.payload.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ModalJobError('payload must be a JSON object')
        payload.setdefault('run_id', f'{os.environ.get("GITHUB_RUN_ID", "")}-{os.environ.get("GITHUB_RUN_ATTEMPT", "")}')
        # P1/G10: Do not str()-coerce payload.run_id — require it to be a string.
        raw_run_id = payload.get('run_id')
        if not isinstance(raw_run_id, str):
            raise ModalJobError(
                f'payload.run_id must be a string, got {type(raw_run_id).__name__}: {raw_run_id!r}'
            )
        if not raw_run_id.strip('-'):
            raise ModalJobError('GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT are required when payload.run_id is absent')
        submission, terminal = run_job(
            worker_url=os.environ.get('MODAL_WORKER_URL', ''),
            worker_token=os.environ.get('MODAL_WORKER_TOKEN', ''),
            route=args.route,
            payload=payload,
            submission_output=args.submission_output,
            terminal_output=args.terminal_output,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
            expected_run_id=args.expected_run_id or None,
            expected_compute_job_id=args.expected_compute_job_id or None,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({'submission': submission, 'terminal': terminal}, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
