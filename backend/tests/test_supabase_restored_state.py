from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.scripts.verify_supabase_restored_state import (
    _capacity_snapshot,
    _count_from_content_range,
    _storage_reference_audit,
)


class TestSupabaseRestoredStateInventory(unittest.TestCase):
    def test_content_range_header_is_case_insensitive(self) -> None:
        self.assertEqual(
            _count_from_content_range({"Content-Range": "0-0/16"}),
            16,
        )

    def test_storage_reference_audit_counts_missing_objects(self) -> None:
        rows = [
            {
                "id": "run-present",
                "manifest_storage_ref": "forecast-products/a/manifest.json",
                "runout_storage_ref": "forecast-products/a/runouts.json.gz",
            },
            {
                "id": "run-missing",
                "manifest_storage_ref": "forecast-products/b/manifest.json",
                "runout_storage_ref": None,
            },
        ]
        result = _storage_reference_audit(
            rows,
            {"forecast-products": ["a/manifest.json", "a/runouts.json.gz"]},
        )
        self.assertEqual(result["checked_reference_count"], 3)
        self.assertEqual(result["missing_reference_count"], 1)
        self.assertEqual(result["missing_references"][0]["run_id"], "run-missing")

    def test_malformed_reference_fails_closed_as_missing(self) -> None:
        result = _storage_reference_audit(
            [{
                "id": "run-invalid",
                "manifest_storage_ref": "not-a-bucket-reference",
                "runout_storage_ref": None,
            }],
            {},
        )
        self.assertEqual(result["missing_reference_count"], 1)

    def test_storage_reference_audit_reports_missing_hourly_payloads(self) -> None:
        result = _storage_reference_audit(
            [{
                "id": "run-hourly",
                "manifest_storage_ref": "forecast-products/a/manifest.json",
                "runout_storage_ref": None,
                "hourly_storage_refs": [
                    "forecast-products/a/hour-0.json",
                    "forecast-products/a/hour-1.json",
                ],
            }],
            {"forecast-products": ["a/manifest.json", "a/hour-0.json"]},
        )
        self.assertEqual(result["hourly_checked_reference_count"], 2)
        self.assertEqual(result["hourly_missing_reference_count"], 1)
        self.assertEqual(result["hourly_missing_reference_samples"][0]["run_id"], "run-hourly")

    def test_capacity_snapshot_accepts_one_service_role_row(self) -> None:
        payload = [{
            "database_bytes": 80,
            "database_limit_bytes": 500,
            "storage_bytes": 70,
            "storage_limit_bytes": 1_000,
            "database_status": "ok",
            "storage_status": "ok",
        }]
        with patch(
            "backend.scripts.verify_supabase_restored_state._request_json",
            return_value=(200, {}, payload),
        ) as request:
            result = _capacity_snapshot("https://eyyellmffzzujyssaayb.supabase.co", "key")

        self.assertEqual(result, payload[0])
        request.assert_called_once()

    def test_capacity_snapshot_rejects_missing_rpc_row(self) -> None:
        with patch(
            "backend.scripts.verify_supabase_restored_state._request_json",
            return_value=(200, {}, []),
        ):
            with self.assertRaisesRegex(RuntimeError, "capacity snapshot"):
                _capacity_snapshot("https://eyyellmffzzujyssaayb.supabase.co", "key")


if __name__ == "__main__":
    unittest.main()
