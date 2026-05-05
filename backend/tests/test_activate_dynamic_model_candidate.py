from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.scripts.activate_dynamic_model_candidate import activate_dynamic_model_candidate


class ActivateDynamicModelCandidateTests(unittest.TestCase):
    @patch('backend.scripts.activate_dynamic_model_candidate.patch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    def test_dry_run_reports_blockers_without_patch(
        self,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        fetch_latest_model_status_row_mock.return_value = {
            'dynamic_model_candidate': {
                'enabled': True,
                'dynamic_model_type': 'mts_lstm_v1',
                'dynamic_model_version': 'mts-lstm-shadow-2',
                'ready_for_activation': False,
                'blocked_gate': 'sar_release_gate',
                'gates': {
                    'shadow_quality_gate_passed': True,
                    'sar_release_gate_passed': False,
                    'sar_volume_gate_passed': True,
                    'production_eligibility_gate_passed': False,
                },
            },
            'active_model_type': 'surrogate_rf_v1',
            'active_model_version': 'rf_surrogate_v2',
        }

        result = activate_dynamic_model_candidate(execute_activation=False)

        self.assertEqual(result['action'], 'dry_run')
        self.assertIn('sar_release_gate', result['blockers'])
        patch_latest_model_status_row_mock.assert_not_called()

    @patch('backend.scripts.activate_dynamic_model_candidate.patch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    def test_execute_activation_patches_model_status_when_candidate_is_ready(
        self,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        fetch_latest_model_status_row_mock.return_value = {
            'dynamic_model_candidate': {
                'enabled': True,
                'dynamic_model_type': 'mts_lstm_v1',
                'dynamic_model_version': 'mts-lstm-shadow-2',
                'ready_for_activation': True,
                'gates': {
                    'shadow_quality_gate_passed': True,
                    'sar_release_gate_passed': True,
                    'sar_volume_gate_passed': True,
                    'production_eligibility_gate_passed': True,
                },
            },
            'active_model_type': 'surrogate_rf_v1',
            'active_model_version': 'rf_surrogate_v2',
        }

        result = activate_dynamic_model_candidate(
            execute_activation=True,
            required_candidate_version='mts-lstm-shadow-2',
        )

        self.assertTrue(result['activation_applied'])
        payload = patch_latest_model_status_row_mock.call_args.args[0]
        self.assertEqual(payload['active_model_type'], 'mts_lstm_v1')
        self.assertEqual(payload['active_model_version'], 'mts-lstm-shadow-2')
        self.assertTrue(payload['promotion_gate_passed'])
        self.assertFalse(payload['shadow_mode_active'])


if __name__ == '__main__':
    unittest.main()
