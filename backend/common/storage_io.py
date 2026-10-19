from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import quote

import requests

from backend.common.supabase_io import SupabaseError, _base_url, _headers

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_STORAGE_ATTEMPTS = 5


def _retry_delay_seconds(*, attempt: int, response: requests.Response | None) -> float:
    retry_after = 0.0
    if response is not None:
        retry_after_header = response.headers.get('Retry-After')
        if retry_after_header:
            try:
                retry_after = float(retry_after_header)
            except ValueError:
                retry_after = 0.0
    return max(float(2 ** attempt), retry_after)


def _request_with_retry(
    *,
    operation: str,
    request: Any,
) -> requests.Response:
    last_error: Exception | None = None
    last_response: requests.Response | None = None
    for attempt in range(_MAX_STORAGE_ATTEMPTS):
        try:
            response = request()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            last_response = None
        else:
            if response.ok:
                return response
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                raise SupabaseError(
                    f'{operation} failed ({response.status_code}): {response.text}',
                )
            last_error = None
            last_response = response
        if attempt < _MAX_STORAGE_ATTEMPTS - 1:
            time.sleep(_retry_delay_seconds(attempt=attempt, response=last_response))
    if last_response is not None:
        raise SupabaseError(
            f'{operation} failed ({last_response.status_code}): {last_response.text}',
        )
    raise SupabaseError(
        f'{operation} failed after {_MAX_STORAGE_ATTEMPTS} attempts: {last_error}',
    )


def _storage_object_url(*, bucket: str, object_path: str, authenticated: bool) -> str:
    auth_path = 'authenticated/' if authenticated else ''
    return f"{_base_url()}/storage/v1/object/{auth_path}{bucket}/{quote(object_path, safe='/')}"


def _storage_download_request(*, bucket: str, object_path: str) -> requests.Response:
    return requests.get(
        _storage_object_url(bucket=bucket, object_path=object_path, authenticated=True),
        headers={
            key: value
            for key, value in _headers().items()
            if key in {'apikey', 'Authorization'}
        },
        timeout=120,
    )


def _parse_json_error_payload(response: requests.Response) -> Any | None:
    text = response.text.strip()
    if not text:
        return None
    content_type = str(response.headers.get('Content-Type') or '').lower()
    if 'json' not in content_type and not text.startswith(('{', '[')):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_ambiguous_html_bad_request(response: requests.Response) -> bool:
    if response.status_code != 400:
        return False
    if _parse_json_error_payload(response) is not None:
        return False
    content_type = str(response.headers.get('Content-Type') or '').lower()
    text = response.text.lstrip().lower()
    return (
        'text/html' in content_type
        or 'application/xhtml+xml' in content_type
        or text.startswith('<!doctype html')
        or text.startswith('<html')
        or text.startswith('<')
    )


def storage_upload_bytes(
    *,
    bucket: str,
    object_path: str,
    payload: bytes,
    content_type: str = 'application/octet-stream',
    upsert: bool = True,
) -> str:
    operation = f'STORAGE UPLOAD {bucket}/{object_path}'
    last_error: Exception | None = None
    last_response: requests.Response | None = None
    last_verification_error: str | None = None
    for attempt in range(_MAX_STORAGE_ATTEMPTS):
        try:
            response = requests.post(
                _storage_object_url(bucket=bucket, object_path=object_path, authenticated=False),
                headers={
                    **_headers(),
                    'Content-Type': content_type,
                    'x-upsert': 'true' if upsert else 'false',
                },
                data=payload,
                timeout=120,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            last_response = None
            last_verification_error = None
        else:
            if response.ok:
                return f'{bucket}/{object_path}'
            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_error = None
                last_response = response
                last_verification_error = None
            elif _is_ambiguous_html_bad_request(response):
                try:
                    downloaded = storage_download_bytes(bucket=bucket, object_path=object_path)
                except SupabaseError as exc:
                    last_error = exc
                    last_response = response
                    last_verification_error = f'object verification failed: {exc}'
                else:
                    if downloaded == payload:
                        return f'{bucket}/{object_path}'
                    last_error = None
                    last_response = response
                    last_verification_error = 'uploaded object bytes differ from attempted payload'
            else:
                raise SupabaseError(
                    f'{operation} failed ({response.status_code}): {response.text}',
                )
        if attempt < _MAX_STORAGE_ATTEMPTS - 1:
            time.sleep(_retry_delay_seconds(attempt=attempt, response=last_response))
    if last_verification_error is not None and last_response is not None:
        raise SupabaseError(
            f'{operation} failed ({last_response.status_code}) after verification: {last_verification_error}; original response: {last_response.text}',
        )
    if last_response is not None:
        raise SupabaseError(
            f'{operation} failed ({last_response.status_code}): {last_response.text}',
        )
    raise SupabaseError(
        f'{operation} failed after {_MAX_STORAGE_ATTEMPTS} attempts: {last_error}',
    )
    return f'{bucket}/{object_path}'


def storage_download_bytes(
    *,
    bucket: str,
    object_path: str,
) -> bytes:
    response = _request_with_retry(
        operation=f'STORAGE DOWNLOAD {bucket}/{object_path}',
        request=lambda: _storage_download_request(bucket=bucket, object_path=object_path),
    )
    return response.content


def storage_upsert_json(
    *,
    bucket: str,
    object_path: str,
    payload: dict[str, Any],
    upsert: bool = True,
) -> str:
    import json

    return storage_upload_bytes(
        bucket=bucket,
        object_path=object_path,
        payload=json.dumps(payload, indent=2, sort_keys=True).encode('utf-8'),
        content_type='application/json',
        upsert=upsert,
    )
