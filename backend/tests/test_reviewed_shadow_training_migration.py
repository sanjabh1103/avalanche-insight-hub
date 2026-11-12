"""Static contract checks for the reviewed shadow-training database boundary."""
from __future__ import annotations

import unittest
from pathlib import Path


class TestReviewedShadowTrainingMigration(unittest.TestCase):
    def test_migration_is_append_only_and_shadow_only(self) -> None:
        migrations_dir = Path(__file__).resolve().parents[2] / 'supabase' / 'migrations'
        sql_parts: list[str] = []
        for pattern in (
            '20260714170000_reviewed_shadow_training_candidates.sql',
            '20260714170001_materialize_reviewed_shadow_training_candidate.sql',
        ):
            sql_parts.append((migrations_dir / pattern).read_text(encoding='utf-8').lower())
        sql = '\n'.join(sql_parts)

        self.assertIn('verification_discrepancy', sql)
        self.assertIn('case_origin', sql)
        self.assertIn('forecast_publication', sql)
        self.assertIn('create table if not exists public.reviewed_shadow_training_candidates', sql)
        self.assertIn('production_eligible = false', sql)
        self.assertIn('before update or delete on public.reviewed_shadow_training_candidates', sql)
        self.assertIn('scientist or admin read reviewed shadow candidates', sql)
        self.assertIn('materialize_reviewed_shadow_training_candidate', sql)
        self.assertIn('label_quality_verdict = \'label_reliable\'', sql)
        # Keep the static migration contract aligned with the Python preflight.
        self.assertIn('observation_times_utc', sql)
        self.assertIn('source_freshness_hours', sql)
        self.assertIn('alignment,grid,forecast_grid_id', sql)
        self.assertIn("source_value !~ '^[0-9a-f]{64}$'", sql)
        self.assertIn('review_count < required_reviewer_count', sql)
        self.assertIn('distinct_reviewer_count < required_reviewer_count', sql)
        self.assertIn('distinct_verdict_count <> 1', sql)
        self.assertIn("claim_impact <> 'block'", sql)
        self.assertNotIn('for all to authenticated', sql)


if __name__ == '__main__':
    unittest.main()
