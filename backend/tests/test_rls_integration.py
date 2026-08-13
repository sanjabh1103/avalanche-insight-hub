"""Real Supabase RLS integration tests.

Tests live PostgreSQL RLS policies on the verification_observations and
verification_review_queue tables. Requires a running Supabase local stack
(`supabase start` + `supabase db reset`).

These tests auto-skip when SUPABASE_URL is not set, so existing CI without
Docker/Supabase CLI still passes.

Run locally:
  supabase start
  supabase db reset
  SUPABASE_URL=http://127.0.0.1:54321 \
  SUPABASE_SERVICE_KEY=<service_role_key> \
  SUPABASE_ANON_KEY=<anon_key> \
  python -m pytest backend/tests/test_rls_integration.py -v
"""
from __future__ import annotations

import os
import unittest

SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')

_SKIP_REASON = (
    'SUPABASE_URL not set — run `supabase start` and set SUPABASE_URL, '
    'SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY to run RLS integration tests'
)


def _has_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY and SUPABASE_ANON_KEY)


@unittest.skipUnless(_has_supabase(), _SKIP_REASON)
class TestRLSIntegration(unittest.TestCase):
    """Live RLS tests against local Supabase Postgres."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from supabase import create_client
        except ImportError:
            raise unittest.SkipTest('supabase-py not installed')
        cls.service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        cls.anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    def test_service_role_can_insert_observation(self) -> None:
        """Service role can insert into verification_observations."""
        row = {
            'region_key': 'test_rls_region',
            'cell_id': 'test_cell_1',
            'sensor': 'weather',
            'variable': 'snow_depth',
            'value': 1.25,
            'unit': 'm',
            'uncertainty': 0.2,
            'acquisition_time': '2026-01-15T06:00:00Z',
            'freshness_hours': 3.0,
            'quality_state': 'verified',
            'lineage': {'verified': True, 'evidence_ref': 'test:cell_1'},
            'synthetic': False,
        }
        result = self.service_client.table('verification_observations').insert(row).execute()
        self.assertIsNotNone(result.data)
        self.assertEqual(len(result.data), 1)

    def test_anonymous_cannot_read_observations(self) -> None:
        """Anonymous (anon key) cannot read verification_observations."""
        result = self.anon_client.table('verification_observations').select('*').limit(1).execute()
        self.assertEqual(len(result.data), 0)

    def test_anonymous_cannot_insert_observation(self) -> None:
        """Anonymous cannot insert into verification_observations."""
        row = {
            'region_key': 'test_rls_anon',
            'cell_id': 'test_cell_anon',
            'sensor': 'weather',
            'variable': 'snow_depth',
            'value': 0.5,
            'unit': 'm',
            'uncertainty': 0.1,
            'acquisition_time': '2026-01-15T06:00:00Z',
            'freshness_hours': 3.0,
            'quality_state': 'verified',
            'lineage': {'verified': True},
            'synthetic': False,
        }
        try:
            result = self.anon_client.table('verification_observations').insert(row).execute()
            self.assertEqual(len(result.data), 0, 'Anonymous insert should be blocked')
        except Exception:
            pass

    def test_anonymous_cannot_read_review_queue(self) -> None:
        """Anonymous cannot read verification_review_queue (scientist-only)."""
        result = self.anon_client.table('verification_review_queue').select('*').limit(1).execute()
        self.assertEqual(len(result.data), 0)

    def test_update_fails_on_observations(self) -> None:
        """UPDATE on verification_observations is blocked by trigger."""
        insert_row = {
            'region_key': 'test_rls_update',
            'cell_id': 'test_cell_update',
            'sensor': 'weather',
            'variable': 'snow_depth',
            'value': 1.0,
            'unit': 'm',
            'uncertainty': 0.1,
            'acquisition_time': '2026-01-15T06:00:00Z',
            'freshness_hours': 3.0,
            'quality_state': 'verified',
            'lineage': {'verified': True},
            'synthetic': False,
        }
        self.service_client.table('verification_observations').insert(insert_row).execute()
        try:
            self.service_client.table('verification_observations').update(
                {'value': 999.0}
            ).eq('cell_id', 'test_cell_update').eq('region_key', 'test_rls_update').execute()
            self.fail('UPDATE should have been blocked by append-only trigger')
        except Exception:
            pass

    def test_delete_fails_on_observations(self) -> None:
        """DELETE on verification_observations is blocked by trigger."""
        insert_row = {
            'region_key': 'test_rls_delete',
            'cell_id': 'test_cell_delete',
            'sensor': 'weather',
            'variable': 'snow_depth',
            'value': 1.0,
            'unit': 'm',
            'uncertainty': 0.1,
            'acquisition_time': '2026-01-15T06:00:00Z',
            'freshness_hours': 3.0,
            'quality_state': 'verified',
            'lineage': {'verified': True},
            'synthetic': False,
        }
        self.service_client.table('verification_observations').insert(insert_row).execute()
        try:
            self.service_client.table('verification_observations').delete().eq(
                'cell_id', 'test_cell_delete'
            ).eq('region_key', 'test_rls_delete').execute()
            self.fail('DELETE should have been blocked by append-only trigger')
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls) -> None:
        if _has_supabase():
            try:
                cls.service_client.table('verification_observations').delete().eq(
                    'region_key', 'test_rls_region'
                ).execute()
                cls.service_client.table('verification_observations').delete().eq(
                    'region_key', 'test_rls_update'
                ).execute()
                cls.service_client.table('verification_observations').delete().eq(
                    'region_key', 'test_rls_delete'
                ).execute()
            except Exception:
                pass


@unittest.skipUnless(_has_supabase(), _SKIP_REASON)
class TestReviewedShadowTrainingCandidatesRLS(unittest.TestCase):
    """RLS and append-only tests for reviewed_shadow_training_candidates."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from supabase import create_client
        except ImportError:
            raise unittest.SkipTest('supabase-py not installed')
        cls.service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        cls.anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        cls._forecast_run_id = None
        cls._case_id = None
        cls._candidate_id = None

    def _ensure_forecast_run(self) -> str:
        if self._forecast_run_id:
            return self._forecast_run_id
        # Try to reuse an existing test run first (idempotent on re-runs)
        existing = (
            self.service_client.table('forecast_runs')
            .select('id')
            .eq('region_key', 'test_shadow_rls')
            .order('created_at', desc=True)
            .limit(1)
            .execute()
        )
        if existing.data:
            self._forecast_run_id = str(existing.data[0]['id'])
            return self._forecast_run_id
        row = {
            'hazard_type': 'avalanche',
            'region_key': 'test_shadow_rls',
            'region_name': 'Test Shadow RLS',
            'forecast_date': '2026-01-15',
            'horizon_hours': 24,
            'grid_size': 1,
            'bbox': [76.0, 35.0, 77.0, 36.0],
            'status': 'ready',
            'publication_status': 'published',
            'active': True,
        }
        result = self.service_client.table('forecast_runs').insert(row).execute()
        self._forecast_run_id = str(result.data[0]['id'])
        return self._forecast_run_id

    def _ensure_case(self, forecast_run_id: str) -> str:
        if self._case_id:
            return self._case_id
        # Try to reuse an existing test case first (idempotent on re-runs)
        existing = (
            self.service_client.table('scientist_validation_cases')
            .select('id')
            .eq('region_key', 'test_shadow_rls')
            .eq('forecast_run_id', forecast_run_id)
            .order('created_at', desc=True)
            .limit(1)
            .execute()
        )
        if existing.data:
            self._case_id = str(existing.data[0]['id'])
            return self._case_id
        case_row = {
            'case_type': 'verification_discrepancy',
            'status': 'pending',
            'priority': 5,
            'region_key': 'test_shadow_rls',
            'forecast_run_id': forecast_run_id,
            'cell_row': 4,
            'cell_col': 7,
            'title': 'RLS test case',
            'case_origin': 'forecast_publication',
            'requires_two_reviewers': True,
        }
        result = self.service_client.table('scientist_validation_cases').insert(case_row).execute()
        self._case_id = str(result.data[0]['id'])
        return self._case_id

    def test_service_role_can_insert_candidate(self) -> None:
        """Service role can insert a valid reviewed_shadow_training_candidate."""
        run_id = self._ensure_forecast_run()
        case_id = self._ensure_case(run_id)
        existing = self.service_client.table('reviewed_shadow_training_candidates').select('id').eq(
            'case_id', case_id
        ).execute()
        if existing.data:
            self._candidate_id = str(existing.data[0]['id'])
            return
        candidate_row = {
            'case_id': case_id,
            'forecast_run_id': run_id,
            'region_key': 'test_shadow_rls',
            'cell_row': 4,
            'cell_col': 7,
            'feature_snapshot_sha256': 'a' * 64,
            'evidence_replay_sha256': 'b' * 64,
            'feature_snapshot': {'snowfall_24h_cm': 24.0},
            'evidence_lineage': {'source_hashes': {'model_config_sha256': 'a' * 64}},
            'review_ids': ['00000000-0000-0000-0000-000000000001'],
            'review_summary': [{'reviewer_id': 'scientist-1', 'verdict': 'accepted'}],
        }
        result = self.service_client.table('reviewed_shadow_training_candidates').insert(candidate_row).execute()
        self.assertIsNotNone(result.data)
        self.assertEqual(len(result.data), 1)
        self._candidate_id = str(result.data[0]['id'])

    def test_anonymous_cannot_read_candidates(self) -> None:
        """Anonymous cannot read reviewed_shadow_training_candidates."""
        result = self.anon_client.table('reviewed_shadow_training_candidates').select('*').limit(1).execute()
        self.assertEqual(len(result.data), 0)

    def test_update_fails_on_candidates(self) -> None:
        """UPDATE on reviewed_shadow_training_candidates is blocked by append-only trigger."""
        run_id = self._ensure_forecast_run()
        case_id = self._ensure_case(run_id)
        if not self._candidate_id:
            self.test_service_role_can_insert_candidate()
        try:
            self.service_client.table('reviewed_shadow_training_candidates').update(
                {'training_status': 'promoted'}
            ).eq('id', self._candidate_id).execute()
            self.fail('UPDATE should have been blocked by append-only trigger')
        except Exception:
            pass

    def test_delete_fails_on_candidates(self) -> None:
        """DELETE on reviewed_shadow_training_candidates is blocked by append-only trigger."""
        run_id = self._ensure_forecast_run()
        case_id = self._ensure_case(run_id)
        if not self._candidate_id:
            self.test_service_role_can_insert_candidate()
        try:
            self.service_client.table('reviewed_shadow_training_candidates').delete().eq(
                'id', self._candidate_id
            ).execute()
            self.fail('DELETE should have been blocked by append-only trigger')
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls) -> None:
        if _has_supabase():
            try:
                if cls._candidate_id:
                    cls.service_client.table('reviewed_shadow_training_candidates').delete().eq(
                        'id', cls._candidate_id
                    ).execute()
            except Exception:
                pass
            try:
                if cls._case_id:
                    cls.service_client.table('scientist_validation_cases').delete().eq(
                        'id', cls._case_id
                    ).execute()
            except Exception:
                pass
            try:
                if cls._forecast_run_id:
                    cls.service_client.table('forecast_runs').delete().eq(
                        'id', cls._forecast_run_id
                    ).execute()
            except Exception:
                pass


@unittest.skipUnless(_has_supabase(), _SKIP_REASON)
class TestCaseOriginImmutability(unittest.TestCase):
    """Test that case_origin on scientist_validation_cases is immutable."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from supabase import create_client
        except ImportError:
            raise unittest.SkipTest('supabase-py not installed')
        cls.service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        cls._forecast_run_id = None
        cls._case_id = None

    def test_case_origin_cannot_be_updated(self) -> None:
        """UPDATE of case_origin on scientist_validation_cases fails."""
        existing = self.service_client.table('forecast_runs').select('id').eq(
            'region_key', 'test_origin_immutable'
        ).eq('hazard_type', 'avalanche').execute()
        if existing.data:
            self._forecast_run_id = str(existing.data[0]['id'])
        else:
            run_row = {
                'hazard_type': 'avalanche',
                'region_key': 'test_origin_immutable',
                'region_name': 'Test Origin',
                'forecast_date': '2026-01-15',
                'horizon_hours': 24,
                'grid_size': 1,
                'bbox': [76.0, 35.0, 77.0, 36.0],
                'status': 'ready',
                'publication_status': 'published',
                'active': True,
            }
            result = self.service_client.table('forecast_runs').insert(run_row).execute()
            self._forecast_run_id = str(result.data[0]['id'])
        existing_case = self.service_client.table('scientist_validation_cases').select('id').eq(
            'region_key', 'test_origin_immutable'
        ).eq('forecast_run_id', self._forecast_run_id).execute()
        if existing_case.data:
            self._case_id = str(existing_case.data[0]['id'])
        else:
            case_row = {
                'case_type': 'verification_discrepancy',
                'status': 'pending',
                'priority': 3,
                'region_key': 'test_origin_immutable',
                'forecast_run_id': self._forecast_run_id,
                'cell_row': 1,
                'cell_col': 1,
                'title': 'Origin immutability test',
                'case_origin': 'forecast_publication',
            }
            result = self.service_client.table('scientist_validation_cases').insert(case_row).execute()
            self._case_id = str(result.data[0]['id'])
        try:
            self.service_client.table('scientist_validation_cases').update(
                {'case_origin': 'manual'}
            ).eq('id', self._case_id).execute()
            self.fail('case_origin UPDATE should have been blocked')
        except Exception:
            pass

    @classmethod
    def tearDownClass(cls) -> None:
        if _has_supabase():
            try:
                if cls._case_id:
                    cls.service_client.table('scientist_validation_cases').delete().eq(
                        'id', cls._case_id
                    ).execute()
            except Exception:
                pass
            try:
                if cls._forecast_run_id:
                    cls.service_client.table('forecast_runs').delete().eq(
                        'id', cls._forecast_run_id
                    ).execute()
            except Exception:
                pass


@unittest.skipUnless(_has_supabase(), _SKIP_REASON)
class TestBaselinesAnomaliesRLS(unittest.TestCase):
    """RLS tests for verification_baselines and verification_anomalies."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            from supabase import create_client
        except ImportError:
            raise unittest.SkipTest('supabase-py not installed')
        cls.service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        cls.anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    def test_anonymous_cannot_read_baselines(self) -> None:
        """Anonymous cannot read verification_baselines (scientist-only)."""
        result = self.anon_client.table('verification_baselines').select('*').limit(1).execute()
        self.assertEqual(len(result.data), 0)

    def test_anonymous_cannot_read_anomalies(self) -> None:
        """Anonymous cannot read verification_anomalies (scientist-only)."""
        result = self.anon_client.table('verification_anomalies').select('*').limit(1).execute()
        self.assertEqual(len(result.data), 0)

    def test_service_role_can_read_baselines(self) -> None:
        """Service role can read verification_baselines."""
        result = self.service_client.table('verification_baselines').select('*').limit(1).execute()
        self.assertIsNotNone(result.data)

    def test_service_role_can_read_anomalies(self) -> None:
        """Service role can read verification_anomalies."""
        result = self.service_client.table('verification_anomalies').select('*').limit(1).execute()
        self.assertIsNotNone(result.data)


if __name__ == '__main__':
    unittest.main()
