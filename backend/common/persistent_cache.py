"""Persistent cache with TTL — Postgres-backed with in-memory fallback.

Replaces in-process dict caches (_GIBS_TILE_CACHE, _REGION_SENSOR_HISTORY_CACHE)
with content-addressed Postgres storage that survives worker restarts.

Env flags:
  PERSISTENT_CACHE_ENABLED — use Postgres backend (default: false → in-memory)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

PERSISTENT_CACHE_ENABLED = os.getenv('PERSISTENT_CACHE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

_MEM_CACHE: dict[str, tuple[Any, float | None]] = {}


def _now_ts() -> float:
    return time.time()


def get_cached(key: str) -> dict[str, Any] | None:
    """Retrieve a cached value by key.

    Returns None if key is missing or expired.
    """
    if PERSISTENT_CACHE_ENABLED:
        return _get_cached_pg(key)
    return _get_cached_mem(key)


def set_cached(key: str, value: dict[str, Any], ttl_seconds: float = 86400.0) -> None:
    """Store a value in cache with TTL in seconds."""
    if PERSISTENT_CACHE_ENABLED:
        _set_cached_pg(key, value, ttl_seconds)
    else:
        _set_cached_mem(key, value, ttl_seconds)


def cleanup_expired() -> int:
    """Delete expired entries. Returns count of entries removed."""
    if PERSISTENT_CACHE_ENABLED:
        return _cleanup_expired_pg()
    return _cleanup_expired_mem()


def clear_all() -> None:
    """Clear all cached entries (for testing)."""
    _MEM_CACHE.clear()


def _get_cached_mem(key: str) -> dict[str, Any] | None:
    entry = _MEM_CACHE.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at is not None and _now_ts() > expires_at:
        del _MEM_CACHE[key]
        return None
    return value


def _set_cached_mem(key: str, value: dict[str, Any], ttl_seconds: float) -> None:
    expires_at = _now_ts() + ttl_seconds if ttl_seconds > 0 else None
    _MEM_CACHE[key] = (value, expires_at)


def _cleanup_expired_mem() -> int:
    now = _now_ts()
    expired_keys = [
        k for k, (_, exp) in _MEM_CACHE.items()
        if exp is not None and now > exp
    ]
    for k in expired_keys:
        del _MEM_CACHE[k]
    return len(expired_keys)


def _get_cached_pg(key: str) -> dict[str, Any] | None:
    try:
        from backend.common.supabase_io import has_supabase_credentials, rest_get
    except ImportError:
        return _get_cached_mem(key)

    if not has_supabase_credentials():
        return _get_cached_mem(key)

    try:
        rows = rest_get(
            'persistent_cache',
            params={'select': 'value,expires_at', 'key': f'eq.{key}', 'limit': '1'},
        )
        if not rows:
            return None
        row = rows[0]
        expires_at = row.get('expires_at')
        if expires_at:
            exp_dt = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > exp_dt:
                return None
        return row.get('value')
    except Exception:
        return _get_cached_mem(key)


def _set_cached_pg(key: str, value: dict[str, Any], ttl_seconds: float) -> None:
    try:
        from backend.common.supabase_io import has_supabase_credentials, rest_upsert
    except ImportError:
        _set_cached_mem(key, value, ttl_seconds)
        return

    if not has_supabase_credentials():
        _set_cached_mem(key, value, ttl_seconds)
        return

    try:
        from datetime import timedelta
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds > 0 else None
        rest_upsert('persistent_cache', [{
            'key': key,
            'value': json.dumps(value),
            'expires_at': expires_at,
        }], on_conflict='key')
    except Exception:
        _set_cached_mem(key, value, ttl_seconds)


def _cleanup_expired_pg() -> int:
    try:
        from backend.common.supabase_io import has_supabase_credentials, rest_delete
    except ImportError:
        return _cleanup_expired_mem()

    if not has_supabase_credentials():
        return _cleanup_expired_mem()

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        deleted = rest_delete('persistent_cache', filters={'expires_at': f'lt.{now_iso}'})
        return len(deleted) if deleted else 0
    except Exception:
        return _cleanup_expired_mem()
