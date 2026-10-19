from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.scripts.activate_dynamic_model_candidate import activate_dynamic_model_candidate
from backend.common.scientist_review_gate import ReviewDecision


def _ready_candidate_row() -> dict:
    return {
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

    @patch.dict(os.environ, {'RESEARCH_MODEL_GATE_ENABLED': 'false'})
    @patch('backend.scripts.activate_dynamic_model_candidate.patch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    @patch('backend.scripts.activate_dynamic_model_candidate.evaluate_scientist_review_gate')
    def test_gate_disabled_activation_proceeds_with_release_decision(
        self,
        review_gate_mock,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        review_gate_mock.return_value = ReviewDecision(
            stage='model_activation', approved=True, blocked=False,
            needs_review=False, reason='approved',
        )
        fetch_latest_model_status_row_mock.return_value = _ready_candidate_row()

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
        self.assertIn('release_decision', payload)
        self.assertTrue(payload['release_decision']['allowed'])

    @patch('backend.scripts.activate_dynamic_model_candidate.patch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    @patch('backend.scripts.activate_dynamic_model_candidate.evaluate_scientist_review_gate')
    def test_execute_activation_blocks_without_scientist_approval(
        self,
        review_gate_mock,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        review_gate_mock.return_value = ReviewDecision(
            stage='model_activation', approved=False, blocked=True,
            needs_review=True, reason='no approved case',
        )
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

        self.assertFalse(result.get('activation_applied', False))
        self.assertIn('scientist_review', result['blockers'])
        patch_latest_model_status_row_mock.assert_not_called()

    @patch.dict(os.environ, {'RESEARCH_MODEL_GATE_ENABLED': 'true'})
    @patch('backend.scripts.activate_dynamic_model_candidate.patch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    @patch('backend.scripts.activate_dynamic_model_candidate.evaluate_scientist_review_gate')
    def test_gate_enabled_non_baseline_candidate_blocked_by_release_policy(
        self,
        review_gate_mock,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
        patch_latest_model_status_row_mock,
    ) -> None:
        review_gate_mock.return_value = ReviewDecision(
            stage='model_activation', approved=True, blocked=False,
            needs_review=False, reason='approved',
        )
        fetch_latest_model_status_row_mock.return_value = _ready_candidate_row()

        result = activate_dynamic_model_candidate(
            execute_activation=True,
            required_candidate_version='mts-lstm-shadow-2',
        )

        self.assertEqual(result['action'], 'blocked')
        self.assertIn('release_policy', result['blockers'])
        self.assertIn('release_decision', result)
        self.assertFalse(result['release_decision']['allowed'])
        patch_latest_model_status_row_mock.assert_not_called()

    @patch.dict(os.environ, {'RESEARCH_MODEL_GATE_ENABLED': 'true'})
    @patch('backend.scripts.activate_dynamic_model_candidate.patch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    def test_release_decision_present_when_execute_activation_with_blockers(
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

        result = activate_dynamic_model_candidate(execute_activation=True)

        self.assertIn('release_decision', result)
        self.assertFalse(result['release_decision']['allowed'])
        patch_latest_model_status_row_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
