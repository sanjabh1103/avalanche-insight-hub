from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.common.supabase_project_identity import (
    CANONICAL_PROJECT_REF,
    CANONICAL_SUPABASE_URL,
    SupabaseProjectIdentityError,
    assert_canonical_project_url,
    load_project_target,
    project_ref_from_url,
)


def test_canonical_manifest_loads() -> None:
    target = load_project_target()
    assert target.project_ref == CANONICAL_PROJECT_REF
    assert target.supabase_url == CANONICAL_SUPABASE_URL
    assert target.status == "active_healthy"


def test_project_ref_parser_rejects_noncanonical_urls() -> None:
    assert project_ref_from_url(CANONICAL_SUPABASE_URL) == CANONICAL_PROJECT_REF
    with pytest.raises(SupabaseProjectIdentityError):
        project_ref_from_url("https://eyyellmffzzujyssaayb.supabase.co/rest/v1")


def test_project_url_mismatch_fails_closed() -> None:
    with pytest.raises(SupabaseProjectIdentityError):
        assert_canonical_project_url("https://eyyellmffzzujyssaayb.supabase.co")


def test_manifest_mutation_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "MVP4" / "00_governance" / "SUPABASE_ACTIVE_PROJECT.json")
        .read_text(encoding="utf-8")
    )
    manifest["project_ref"] = "eyyellmffzzujyssaayb"
    mutated = tmp_path / "target.json"
    mutated.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SupabaseProjectIdentityError):
        load_project_target(mutated)
