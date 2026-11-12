from pathlib import Path
import unittest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260806120000_knowledge_graph_model_endpoint.sql"
)
SNAPSHOT_BUCKET_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260807120000_create_knowledge_graph_snapshot_bucket.sql"
)


class KnowledgeGraphModelMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION_PATH.read_text(encoding="utf-8")
        cls.snapshot_bucket_sql = SNAPSHOT_BUCKET_MIGRATION_PATH.read_text(encoding="utf-8")

    def test_model_control_rpcs_are_not_publicly_callable(self) -> None:
        public_rpc_signatures = (
            "public.check_model_rate_limit(UUID)",
            "public.reserve_model_usage(UUID, INTEGER, NUMERIC)",
            "public.cleanup_expired_model_cache()",
        )
        for signature in public_rpc_signatures:
            with self.subTest(signature=signature):
                self.assertNotIn(
                    f"GRANT EXECUTE ON FUNCTION {signature} TO anon, authenticated",
                    self.sql,
                )
                self.assertIn(
                    f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC",
                    self.sql,
                )
                self.assertIn(
                    f"REVOKE ALL ON FUNCTION {signature} FROM anon, authenticated",
                    self.sql,
                )
                self.assertIn(
                    f"GRANT EXECUTE ON FUNCTION {signature} TO service_role",
                    self.sql,
                )

    def test_security_definer_functions_pin_search_path(self) -> None:
        self.assertEqual(self.sql.count("SECURITY DEFINER\nSET search_path = public"), 3)

    def test_knowledge_graph_snapshot_bucket_is_private_and_bounded(self) -> None:
        self.assertIn("'knowledge-graph-snapshots'", self.snapshot_bucket_sql)
        self.assertIn("FALSE", self.snapshot_bucket_sql)
        self.assertIn("52428800", self.snapshot_bucket_sql)
        self.assertIn("ARRAY['application/json']", self.snapshot_bucket_sql)
        self.assertIn("ON CONFLICT (id) DO UPDATE", self.snapshot_bucket_sql)
        self.assertNotIn("CREATE POLICY", self.snapshot_bucket_sql)


if __name__ == "__main__":
    unittest.main()
