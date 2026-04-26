from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

from backend.common.supabase_io import SupabaseError, _base_url, _headers


def storage_upload_bytes(
    *,
    bucket: str,
    object_path: str,
    payload: bytes,
    content_type: str = 'application/octet-stream',
    upsert: bool = True,
) -> str:
    response = requests.post(
        f"{_base_url()}/storage/v1/object/{bucket}/{quote(object_path, safe='/')}",
        headers={
            **_headers(),
            'Content-Type': content_type,
            'x-upsert': 'true' if upsert else 'false',
        },
        data=payload,
        timeout=120,
    )
    if not response.ok:
        raise SupabaseError(
            f'STORAGE UPLOAD {bucket}/{object_path} failed ({response.status_code}): {response.text}',
    )
    return f'{bucket}/{object_path}'


def storage_download_bytes(
    *,
    bucket: str,
    object_path: str,
) -> bytes:
    response = requests.get(
        f"{_base_url()}/storage/v1/object/authenticated/{bucket}/{quote(object_path, safe='/')}",
        headers={
            key: value
            for key, value in _headers().items()
            if key in {'apikey', 'Authorization'}
        },
        timeout=120,
    )
    if not response.ok:
        raise SupabaseError(
            f'STORAGE DOWNLOAD {bucket}/{object_path} failed ({response.status_code}): {response.text}',
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
