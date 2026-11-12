"""Fail-closed contracts for the forecast Storage retention worker."""

import unittest
import os
import sys
from unittest.mock import Mock, patch

from backend.scripts import cleanup_old_storage as cleanup


class CleanupOldStorageTests(unittest.TestCase):
    def test_db_connection_prefers_explicit_ipv4_pooler_settings(self) -> None:
        connection = Mock()
        psycopg2 = Mock()
        psycopg2.connect.return_value = connection
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://eyyellmffzzujyssaayb.supabase.co",
                "SUPABASE_DB_PASSWORD": "p" * 12,
                "SUPABASE_DB_HOST": "aws-0-ap-south-1.pooler.supabase.com",
                "SUPABASE_DB_PORT": "6543",
                "SUPABASE_DB_USER": "postgres.eyyellmffzzujyssaayb",
                "SUPABASE_DB_NAME": "postgres",
            },
        ), patch.dict(sys.modules, {"psycopg2": psycopg2}):
            self.assertIs(cleanup._get_db_connection(), connection)

        psycopg2.connect.assert_called_once_with(
            host="aws-0-ap-south-1.pooler.supabase.com",
            port=6543,
            user="postgres.eyyellmffzzujyssaayb",
            password="p" * 12,
            dbname="postgres",
            connect_timeout=10,
            sslmode="require",
        )
        connection.autocommit = True

    def test_storage_cleanup_excludes_published_or_ready_runs(self) -> None:
        self.assertFalse(
            cleanup._is_storage_cleanup_eligible(
                {"active": False, "status": "ready", "publication_status": "draft"}
            )
        )
        self.assertFalse(
            cleanup._is_storage_cleanup_eligible(
                {"active": False, "status": "failed", "publication_status": "published"}
            )
        )
        self.assertTrue(
            cleanup._is_storage_cleanup_eligible(
                {"active": False, "status": "failed", "publication_status": "draft"}
            )
        )

    def test_quota_precheck_requires_a_database_measurement(self) -> None:
        with patch.object(cleanup, "_get_db_connection", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "quota pre-check requires"):
                cleanup._check_storage_quota()

    def test_quota_precheck_fails_closed_on_measurement_error(self) -> None:
        connection = Mock()
        with patch.object(cleanup, "_get_db_connection", return_value=connection):
            with patch.object(
                cleanup,
                "_sql_get_storage_usage",
                side_effect=RuntimeError("measurement unavailable"),
            ):
                with self.assertRaisesRegex(RuntimeError, "quota pre-check failed"):
                    cleanup._check_storage_quota()
        connection.close.assert_called_once()

    def test_main_returns_failure_when_storage_deletion_fails(self) -> None:
        run = {"id": "run-1", "region_key": "pir_panjal", "hazard_type": "avalanche"}
        with patch.object(cleanup, "has_supabase_credentials", return_value=True), \
                patch.object(cleanup, "_check_storage_quota", return_value=(False, {})), \
                patch.object(cleanup, "_fetch_old_non_active_runs", return_value=[run]), \
                patch.object(cleanup, "_collect_run_objects", return_value=["forecast-products/run-1.json"]), \
                patch.object(cleanup, "_get_s3_client", return_value=None), \
                patch.object(cleanup, "_delete_storage_object", return_value=False), \
                patch.object(cleanup, "_log_storage_usage_after", return_value=True):
            self.assertEqual(cleanup.main(), 1)

    def test_main_returns_failure_when_post_cleanup_measurement_fails(self) -> None:
        with patch.object(cleanup, "has_supabase_credentials", return_value=True), \
                patch.object(cleanup, "_check_storage_quota", return_value=(False, {})), \
                patch.object(cleanup, "_fetch_old_non_active_runs", return_value=[]), \
                patch.object(cleanup, "_log_storage_usage_after", return_value=False):
            self.assertEqual(cleanup.main(), 1)


if __name__ == "__main__":
    unittest.main()
