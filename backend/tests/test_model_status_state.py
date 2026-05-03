from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.common.model_status_state import (
    build_autonomous_evidence_summary,
    build_drift_mode_state,
    build_dynamic_model_candidate,
    build_stability_summary,
    resolve_active_candidate_artifact_dir,
    resolve_active_model_state,
)


class ModelStatusStateTests(unittest.TestCase):
    def test_build_drift_mode_state_distinguishes_ready_blocked_and_monitoring(self) -> None:
        self.assertEqual(
            build_drift_mode_state({'ready_for_activation': True, 'blocked_gate': None, 'enabled': True}),
            'ready_for_manual_activation',
        )
        self.assertEqual(
            build_drift_mode_state({'ready_for_activation': False, 'blocked_gate': 'pss_gate', 'enabled': True}),
            'blocked_by_gate',
        )
        self.assertEqual(
            build_drift_mode_state({'enabled': True, 'last_trained_at': '2026-05-03T00:00:00+00:00'}),
            'candidate_retrained',
        )
        self.assertEqual(build_drift_mode_state({}), 'guarded_monitoring_only')

    def test_build_stability_summary_classifies_unstable_seed_runs(self) -> None:
        summary = build_stability_summary(
            [
                {
                    'seed': 7,
                    'pss_reported': 0.58,
                    'optimal_threshold': 0.41,
                    'brier_score': 0.16,
                    'selected_features': ['snowfall_24h', 'wind_loading', 'slope'],
                },
                {
                    'seed': 8,
                    'pss_reported': 0.51,
                    'optimal_threshold': 0.56,
                    'brier_score': 0.21,
                    'selected_features': ['snowfall_24h', 'temperature_2m'],
                },
            ],
            primary_seed=7,
        )

        self.assertEqual(summary['classification'], 'unstable')
        self.assertEqual(summary['seed_count'], 2)
        self.assertGreater(summary['threshold_drift'], 0.1)

    def test_build_autonomous_evidence_summary_splits_manual_and_autonomous_sources(self) -> None:
        summary = build_autonomous_evidence_summary(
            {
                'training_dataset_version': 'real_event_join_v1',
                'positive_count': 12,
                'negative_count': 36,
                'training_row_count': 48,
                'event_source_counts': {
                    'field_report': 3,
                    'sar_unet': 6,
                    'gemini_news': 3,
                },
                'source_training_weight_sums': {
                    'field_report': 2.1,
                    'sar_unet': 5.4,
                    'gemini_news': 2.5,
                },
                'source_region_counts': {
                    'field_report': 1,
                    'sar_unet': 3,
                    'gemini_news': 2,
                },
                'region_keys': ['davos', 'drass', 'kargil'],
            },
            sar_volume_stats={
                'sar_unet_promoted_count': 6,
                'sar_unet_promoted_region_count': 3,
                'sar_unet_promoted_scene_date_count': 4,
            },
        )

        self.assertEqual(summary['manual_positive_count'], 3)
        self.assertEqual(summary['autonomous_positive_count'], 9)
        self.assertEqual(summary['promoted_sar_volume']['sar_unet_promoted_count'], 6)
        self.assertAlmostEqual(summary['weighted_source_contributions']['sar_unet'], 0.54, places=2)

    def test_resolve_active_model_state_keeps_rf_active_until_candidate_is_explicitly_active(self) -> None:
        bundle = {
            'created_at': '2026-04-29T00:00:00+00:00',
            'surrogate_model_version': 'rf_surrogate_v2',
            'dynamic_model_version': 'mts-lstm-shadow-2',
            'metrics': {
                'pss_reported': 0.61,
                'pss_gate_passed': True,
            },
            'lstm_head_meta': {
                'enabled': True,
                'promotion_gate_passed': True,
                'shadow_quality_gate_passed': True,
                'sar_release_gate_passed': True,
                'sar_volume_gate_passed': True,
                'production_eligibility_gate_passed': True,
                'dynamic_model_type': 'mts_lstm_v1',
                'dynamic_model_version': 'mts-lstm-shadow-2',
            },
        }
        candidate = build_dynamic_model_candidate(bundle)

        state = resolve_active_model_state(None, candidate, bundle)

        self.assertEqual(state['active_model_type'], 'surrogate_rf_v1')
        self.assertEqual(state['active_model_version'], 'rf_surrogate_v2')
        self.assertFalse(state['use_dynamic_inference'])
        self.assertTrue(state['shadow_mode_active'])

    def test_resolve_active_candidate_artifact_dir_uses_activated_candidate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir)
            artifact_dir = artifact_root / '20260429T120000Z'
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / 'model.joblib').write_bytes(b'placeholder')

            resolved = resolve_active_candidate_artifact_dir(
                artifact_root,
                {
                    'active_model_type': 'mts_lstm_v1',
                    'active_model_version': 'mts-lstm-shadow-2',
                    'dynamic_model_candidate': {
                        'dynamic_model_type': 'mts_lstm_v1',
                        'dynamic_model_version': 'mts-lstm-shadow-2',
                        'ready_for_activation': True,
                        'artifact_ref': {
                            'artifact_dir': str(artifact_dir),
                        },
                    },
                },
            )

        self.assertEqual(resolved, artifact_dir.resolve())


if __name__ == '__main__':
    unittest.main()
