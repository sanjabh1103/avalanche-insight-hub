"""Validation helpers for immutable SNOWPACK runtime identities."""

from __future__ import annotations

import re


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_IMAGE_ID = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
_SENTINEL_DIGESTS = frozenset({"0" * 64, "1" * 64})


def is_real_sha256(value: object) -> bool:
    """Return true only for a non-placeholder 64-hex SHA-256 digest."""

    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        return False
    return value.lower() not in _SENTINEL_DIGESTS


def is_real_image_id(value: object) -> bool:
    """Return true only for a non-placeholder Docker image ID."""

    if not isinstance(value, str):
        return False
    match = _IMAGE_ID.fullmatch(value)
    return match is not None and match.group(1).lower() not in _SENTINEL_DIGESTS
