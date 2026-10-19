from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_zoneinfo(timezone_name: str | None) -> tuple[ZoneInfo, str, bool]:
    normalized = str(timezone_name or 'UTC').strip() or 'UTC'
    try:
        return ZoneInfo(normalized), normalized, False
    except ZoneInfoNotFoundError:
        return ZoneInfo('UTC'), 'UTC', True
