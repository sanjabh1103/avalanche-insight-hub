"""Regression contracts for the public RPC repair migration."""

from __future__ import annotations

import unittest
from pathlib import Path


_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260811180000_repair_public_rpc_contracts.sql"
)


class PublicRpcContractMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = _MIGRATION.read_text(encoding="utf-8")

    def test_migration_exists_and_repairs_elevation_type(self) -> None:
        self.assertIn(
            "e.elevation_m::double precision AS elevation_m",
            self.sql,
        )

    def test_promotion_function_qualifies_event_id(self) -> None:
        self.assertIn(
            "FROM public.avalanche_events AS e",
            self.sql,
        )
        self.assertIn(
            "WHERE e.id = p_event_id",
            self.sql,
        )
        self.assertIn(
            "UPDATE public.avalanche_events AS e",
            self.sql,
        )

    def test_migration_regrants_both_functions(self) -> None:
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.fetch_labeler_events",
            self.sql,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION public.promote_event_verification",
            self.sql,
        )


if __name__ == "__main__":
    unittest.main()
