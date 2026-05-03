from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.common.label_governance import (
    GOVERNANCE_VERSION,
    RECENCY_HALF_LIFE_DAYS,
    derive_label_governance,
    governance_refresh_needed,
    materialize_label_governance,
)


class LabelGovernanceTests(unittest.TestCase):
    def test_combines_source_corroboration_and_recency_weights(self) -> None:
        now = datetime(2026, 4, 25, tzinfo=timezone.utc)
        governance = derive_label_governance({
            'timestamp': (now - timedelta(days=5)).isoformat(),
            'source': 'gemini_news',
            'fusion_source': 'newsdata_gemini',
            'source_model': 'gemini-flash-latest',
            'label_confidence': 0.8,
            'training_eligible': True,
            'metadata': {
                'corroboration_sources': ['gemini_news', 'newsdata'],
            },
        }, reference_time=now)

        self.assertTrue(governance.training_eligible)
        self.assertGreater(governance.training_weight, 0.5)
        self.assertGreater(governance.corroboration_weight, 1.0)
        self.assertLess(governance.recency_decay, 1.0)

    def test_low_label_confidence_flips_training_eligibility(self) -> None:
        governance = derive_label_governance({
            'timestamp': '2026-04-24T00:00:00Z',
            'source': 'gee_sar',
            'label_confidence': 0.3,
            'training_eligible': True,
        })

        self.assertFalse(governance.training_eligible)
        self.assertLess(governance.training_weight, 0.5)

    def test_weak_training_reason_penalizes_weight_without_excluding_event(self) -> None:
        governance = derive_label_governance({
            'timestamp': '2026-04-24T00:00:00Z',
            'source': 'gee_sar',
            'label_confidence': 0.8,
            'training_eligible': True,
            'training_eligible_reason': 'sar_low_coverage_weak_training',
        })

        self.assertTrue(governance.training_eligible)
        self.assertLess(governance.training_weight, 0.6)

    def test_audit_only_reason_forces_ineligible_training(self) -> None:
        governance = derive_label_governance({
            'timestamp': '2026-04-24T00:00:00Z',
            'source': 'gee_sar',
            'label_confidence': 0.8,
            'training_eligible': True,
            'training_eligible_reason': 'sar_single_pass_audit_only',
        })

        self.assertFalse(governance.training_eligible)
        self.assertLess(governance.training_weight, 0.3)

    def test_uses_raw_label_confidence_not_decayed_view_value(self) -> None:
        now = datetime(2026, 4, 25, tzinfo=timezone.utc)
        governance = derive_label_governance({
            'timestamp': (now - timedelta(days=RECENCY_HALF_LIFE_DAYS)).isoformat(),
            'source': 'gee_sar',
            'label_confidence': 0.8,
            'confidence_decayed': 0.1,
            'training_eligible': True,
        }, reference_time=now)

        self.assertAlmostEqual(governance.label_confidence, 0.8, places=3)
        self.assertAlmostEqual(governance.confidence_decayed, 0.4, places=3)

    def test_materialization_stamps_version_and_governed_at(self) -> None:
        payload = materialize_label_governance({
            'timestamp': '2026-04-24T00:00:00Z',
            'source': 'field_report',
            'label_confidence': 0.9,
            'training_eligible': True,
        }, reference_time=datetime(2026, 4, 25, tzinfo=timezone.utc))

        self.assertEqual(payload['governance_version'], GOVERNANCE_VERSION)
        self.assertIn('governed_at', payload)

    def test_refresh_needed_only_when_version_is_missing_or_stale(self) -> None:
        self.assertTrue(governance_refresh_needed({}))
        self.assertTrue(governance_refresh_needed({'governance_version': 'autonomous_label_governance_v1'}))
        self.assertFalse(governance_refresh_needed({'governance_version': GOVERNANCE_VERSION}))

    def test_sql_view_half_life_matches_python_constant(self) -> None:
        migration = Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' / '20260425153000_governance_consistency_and_versioning.sql'
        sql = migration.read_text(encoding='utf-8')

        self.assertIn(f'/ {RECENCY_HALF_LIFE_DAYS:.1f}', sql)
        self.assertIn('30-day half-life', sql)


if __name__ == '__main__':
    unittest.main()
