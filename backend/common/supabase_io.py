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


def rest_get(table: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    response = requests.get(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        params=params or {},
        timeout=30,
    )
    if not response.ok:
        raise SupabaseError(f'GET {table} failed ({response.status_code}): {response.text}')
    data = response.json()
    return data if isinstance(data, list) else [data]


def rest_upsert(table: str, records: list[dict[str, Any]], on_conflict: str | None = None) -> list[dict[str, Any]]:
    params = {'on_conflict': on_conflict} if on_conflict else None
    response = requests.post(
        f"{_base_url()}/rest/v1/{table}",
        headers={**_headers(), 'Prefer': 'resolution=merge-duplicates,return=representation'},
        params=params,
        json=records,
        timeout=60,
    )
    if not response.ok:
        raise SupabaseError(f'UPSERT {table} failed ({response.status_code}): {response.text}')
    data = response.json()
    return data if isinstance(data, list) else [data]


def rest_insert(table: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    response = requests.post(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        json=records,
        timeout=60,
    )
    if not response.ok:
        raise SupabaseError(f'INSERT {table} failed ({response.status_code}): {response.text}')
    data = response.json()
    return data if isinstance(data, list) else [data]


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
    data = response.json()
    return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
