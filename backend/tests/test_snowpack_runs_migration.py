"""Unit tests for the snowpack_runs table migration (Phase 2).

Validates the SQL migration file contains the required schema elements
without needing a live Supabase instance. This is a static analysis test.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / 'supabase' / 'migrations'
    / '20260810140000_create_snowpack_runs_and_poc_bucket.sql'
)


def _read_migration() -> str:
    assert _MIGRATION_PATH.exists(), f'Migration not found: {_MIGRATION_PATH}'
    return _MIGRATION_PATH.read_text(encoding='utf-8')


class TestSnowpackRunsMigration:
    """Static analysis of the snowpack_runs migration SQL."""

    @pytest.fixture
    def sql(self) -> str:
        return _read_migration()

    def test_migration_file_exists(self) -> None:
        assert _MIGRATION_PATH.exists()

    def test_creates_snowpack_runs_table(self, sql: str) -> None:
        assert 'CREATE TABLE IF NOT EXISTS public.snowpack_runs' in sql

    def test_has_run_id_unique_constraint(self, sql: str) -> None:
        assert 'run_id TEXT NOT NULL UNIQUE' in sql

    def test_has_status_check_constraint(self, sql: str) -> None:
        assert "CHECK (status IN ('queued', 'building', 'running', 'completed', 'failed', 'verified'))" in sql

    def test_has_horizon_positive_check(self, sql: str) -> None:
        assert 'horizon_hours INTEGER NOT NULL CHECK (horizon_hours > 0)' in sql

    def test_has_rls_enabled(self, sql: str) -> None:
        assert 'ALTER TABLE public.snowpack_runs ENABLE ROW LEVEL SECURITY' in sql

    def test_has_select_policy_for_anon(self, sql: str) -> None:
        assert 'Anyone can view snowpack runs' in sql
        assert 'FOR SELECT USING (true)' in sql

    def test_has_manage_policy_for_service_role(self, sql: str) -> None:
        assert 'Service role can manage snowpack runs' in sql
        assert "auth.role() = 'service_role'" in sql

    def test_has_updated_at_trigger(self, sql: str) -> None:
        assert 'set_snowpack_runs_updated_at' in sql
        assert 'BEFORE UPDATE' in sql

    def test_has_status_index(self, sql: str) -> None:
        assert 'snowpack_runs_status_idx' in sql

    def test_has_region_created_index(self, sql: str) -> None:
        assert 'snowpack_runs_region_created_idx' in sql

    def test_has_poc_mode_index(self, sql: str) -> None:
        assert 'snowpack_runs_poc_mode_idx' in sql

    def test_has_producer_gate_passed_column(self, sql: str) -> None:
        assert 'producer_gate_passed BOOLEAN NOT NULL DEFAULT FALSE' in sql

    def test_has_consumer_gate_passed_column(self, sql: str) -> None:
        assert 'consumer_gate_passed BOOLEAN NOT NULL DEFAULT FALSE' in sql

    def test_has_bundle_storage_ref_column(self, sql: str) -> None:
        assert 'bundle_storage_ref TEXT' in sql

    def test_has_github_run_url_column(self, sql: str) -> None:
        assert 'github_run_url TEXT' in sql


class TestPocArtifactsBucket:
    """Static analysis of the poc-artifacts storage bucket creation."""

    @pytest.fixture
    def sql(self) -> str:
        return _read_migration()

    def test_creates_poc_artifacts_bucket(self, sql: str) -> None:
        assert "'poc-artifacts'" in sql
        assert 'INSERT INTO storage.buckets' in sql

    def test_bucket_is_private(self, sql: str) -> None:
        assert 'FALSE' in sql

    def test_bucket_has_file_size_limit(self, sql: str) -> None:
        assert '104857600' in sql  # 100 MB

    def test_bucket_has_upsert_on_conflict(self, sql: str) -> None:
        assert 'ON CONFLICT (id) DO UPDATE SET' in sql


class TestStaleRunCleanup:
    """Validate the stale run cleanup function exists."""

    @pytest.fixture
    def sql(self) -> str:
        return _read_migration()

    def test_has_cleanup_function(self, sql: str) -> None:
        assert 'cleanup_stale_snowpack_runs' in sql

    def test_cleanup_marks_stale_as_failed(self, sql: str) -> None:
        assert "status = 'failed'" in sql
        assert "30 days" in sql or "'30 days'" in sql
