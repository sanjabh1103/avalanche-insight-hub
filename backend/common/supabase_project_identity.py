"""Fail-closed identity checks for the restored Supabase deployment.

The project reference is intentionally kept in a small governance manifest so
workflows, scripts, and tests can validate the same target. This module does
not contain credentials and does not claim that identity proves deployment or
data parity.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


CANONICAL_PROJECT_REF = "eyyellmffzzujyssaayb"
CANONICAL_SUPABASE_URL = f"https://{CANONICAL_PROJECT_REF}.supabase.co"
_PROJECT_URL_RE = re.compile(r"^https://([a-z0-9]+)\.supabase\.co/?$")


class SupabaseProjectIdentityError(ValueError):
    """Raised when a target manifest or URL is unsafe/inconsistent."""


@dataclass(frozen=True)
class SupabaseProjectTarget:
    project_ref: str
    supabase_url: str
    status: str


def project_ref_from_url(url: str) -> str:
    """Extract a strict Supabase project ref from a canonical URL."""
    if not isinstance(url, str):
        raise SupabaseProjectIdentityError("Supabase URL must be a string")
    match = _PROJECT_URL_RE.fullmatch(url.strip())
    if not match:
        raise SupabaseProjectIdentityError(
            "Supabase URL must be exactly https://<project-ref>.supabase.co"
        )
    return match.group(1)


def load_project_target(path: Path | None = None) -> SupabaseProjectTarget:
    """Load and validate the canonical target manifest."""
    manifest_path = path or (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "MVP4"
        / "00_governance"
        / "SUPABASE_ACTIVE_PROJECT.json"
    )
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupabaseProjectIdentityError(
            f"Cannot load Supabase project manifest: {manifest_path}"
        ) from exc
    if not isinstance(data, dict):
        raise SupabaseProjectIdentityError("Supabase project manifest must be an object")

    project_ref = data.get("project_ref")
    supabase_url = data.get("supabase_url")
    status = data.get("status")
    if not isinstance(project_ref, str) or not project_ref:
        raise SupabaseProjectIdentityError("project_ref is required")
    if not isinstance(supabase_url, str):
        raise SupabaseProjectIdentityError("supabase_url is required")
    if not isinstance(status, str) or status != "active_healthy":
        raise SupabaseProjectIdentityError("target status must be active_healthy")
    if project_ref_from_url(supabase_url) != project_ref:
        raise SupabaseProjectIdentityError("project_ref and supabase_url disagree")
    if project_ref != CANONICAL_PROJECT_REF or supabase_url.rstrip("/") != CANONICAL_SUPABASE_URL:
        raise SupabaseProjectIdentityError(
            "Supabase project manifest does not match the canonical restored target"
        )
    return SupabaseProjectTarget(
        project_ref=project_ref,
        supabase_url=supabase_url.rstrip("/"),
        status=status,
    )


def assert_canonical_project_url(url: str, *, target: SupabaseProjectTarget | None = None) -> None:
    """Raise unless ``url`` targets the canonical active project."""
    expected = target or load_project_target()
    if project_ref_from_url(url) != expected.project_ref:
        raise SupabaseProjectIdentityError(
            f"Supabase project mismatch: expected {expected.project_ref}"
        )
