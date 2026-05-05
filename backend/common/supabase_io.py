from __future__ import annotations

from typing import Any

import requests

from backend.common.config import load_settings


class SupabaseError(RuntimeError):
    pass


def has_supabase_credentials() -> bool:
    settings = load_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _base_url() -> str:
    settings = load_settings()
    if not settings.supabase_url:
        raise SupabaseError('SUPABASE_URL is required for this operation')
    return settings.supabase_url.rstrip('/')


def _headers() -> dict[str, str]:
    settings = load_settings()
    if not settings.supabase_service_role_key:
        raise SupabaseError('SUPABASE_SERVICE_ROLE_KEY is required for this operation')
    return {
        'apikey': settings.supabase_service_role_key,
        'Authorization': f"Bearer {settings.supabase_service_role_key}",
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }


def _json_response_payload(response: requests.Response) -> list[dict[str, Any]]:
    text = response.text.strip()
    if not text:
        return []
    data = response.json()
    return data if isinstance(data, list) else [data]


def rest_get(table: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    response = requests.get(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        params=params or {},
        timeout=30,
    )
    if not response.ok:
        raise SupabaseError(f'GET {table} failed ({response.status_code}): {response.text}')
    return _json_response_payload(response)


LATEST_MODEL_STATUS_ORDER = 'last_inference.desc.nullslast,last_trained.desc.nullslast'


def fetch_latest_model_status_row(select: str = '*') -> dict[str, Any] | None:
    rows = rest_get(
        'model_status',
        {
            'select': select,
            'order': LATEST_MODEL_STATUS_ORDER,
            'limit': '1',
        },
    )
    return rows[0] if rows else None

def rest_upsert(
    table: str,
    records: list[dict[str, Any]],
    on_conflict: str | None = None,
    *,
    returning: str = 'representation',
    timeout_seconds: int = 60,
) -> list[dict[str, Any]]:
    params = {'on_conflict': on_conflict} if on_conflict else None
    response = requests.post(
        f"{_base_url()}/rest/v1/{table}",
        headers={**_headers(), 'Prefer': f'resolution=merge-duplicates,return={returning}'},
        params=params,
        json=records,
        timeout=timeout_seconds,
    )
    if not response.ok:
        raise SupabaseError(f'UPSERT {table} failed ({response.status_code}): {response.text}')
    return _json_response_payload(response)


def rest_insert(
    table: str,
    records: list[dict[str, Any]],
    *,
    returning: str = 'representation',
    timeout_seconds: int = 60,
) -> list[dict[str, Any]]:
    response = requests.post(
        f"{_base_url()}/rest/v1/{table}",
        headers={**_headers(), 'Prefer': f'return={returning}'},
        json=records,
        timeout=timeout_seconds,
    )
    if not response.ok:
        raise SupabaseError(f'INSERT {table} failed ({response.status_code}): {response.text}')
    return _json_response_payload(response)


def rest_delete(table: str, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    response = requests.delete(
        f"{_base_url()}/rest/v1/{table}",
        headers={**_headers(), 'Prefer': 'return=representation'},
        params=filters or {},
        timeout=60,
    )
    if not response.ok:
        raise SupabaseError(f'DELETE {table} failed ({response.status_code}): {response.text}')
    return _json_response_payload(response)


def patch_first_row(table: str, values: dict[str, Any], filters: dict[str, str] | None = None) -> dict[str, Any] | None:
    query = {'select': 'id'}
    if filters:
        query.update({key: f'eq.{value}' for key, value in filters.items()})
    rows = rest_get(table, query)
    if not rows:
        return None
    row_id = rows[0].get('id')
    if not row_id:
        return None
    response = requests.patch(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        params={'id': f'eq.{row_id}'},
        json=values,
        timeout=30,
    )
    if not response.ok:
        raise SupabaseError(f'PATCH {table} failed ({response.status_code}): {response.text}')
    data = _json_response_payload(response)
    return data[0] if data else None


def patch_row_by_id(
    table: str,
    row_id: str,
    values: dict[str, Any],
    *,
    returning: str = 'representation',
    timeout_seconds: int = 30,
) -> dict[str, Any] | None:
    response = requests.patch(
        f"{_base_url()}/rest/v1/{table}",
        headers={**_headers(), 'Prefer': f'return={returning}'},
        params={'id': f'eq.{row_id}'},
        json=values,
        timeout=timeout_seconds,
    )
    if not response.ok:
        raise SupabaseError(f'PATCH {table} failed ({response.status_code}): {response.text}')
    data = _json_response_payload(response)
    return data[0] if data else None


def patch_latest_model_status_row(
    values: dict[str, Any],
    *,
    returning: str = 'representation',
    timeout_seconds: int = 30,
) -> dict[str, Any] | None:
    row = fetch_latest_model_status_row(select='id')
    row_id = row.get('id') if row else None
    if row_id is None:
        return None
    return patch_row_by_id(
        'model_status',
        str(row_id),
        values,
        returning=returning,
        timeout_seconds=timeout_seconds,
    )


def rest_rpc(
    function_name: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_seconds: int = 60,
) -> Any:
    response = requests.post(
        f"{_base_url()}/rest/v1/rpc/{function_name}",
        headers=_headers(),
        json=payload or {},
        timeout=timeout_seconds,
    )
    if not response.ok:
        raise SupabaseError(
            f'RPC {function_name} failed ({response.status_code}): {response.text}',
        )
    if not response.text.strip():
        return None
    return response.json()
