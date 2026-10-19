"""Tests for scientist review gate and workflow contract map."""
import os
import unittest
from unittest.mock import patch

from backend.common.verification_contracts import (
    EvidenceEntry,
    EvidencePacket,
    VerificationPacket,
    WORKFLOW_CONTRACT_MAP,
    validate_workflow_contract,
    EVIDENCE_WEATHER,
    EVIDENCE_DEM,
    EVIDENCE_SAR,
    EVIDENCE_FIELD,
    ANOMALY_NORMAL,
    ATTRIBUTION_UNATTRIBUTED,
)
from backend.common.scientist_review_gate import (
    ReviewDecision,
    evaluate_scientist_review_gate,
    _check_scientist_validation_case,
)


class WorkflowContractMapTests(unittest.TestCase):
    def test_contract_map_covers_all_pipeline_stages(self) -> None:
        expected_stages = {
            'weather_ingest', 'terrain_extract', 'sar_extract',
            'snowpack_physics', 'risk_fusion', 'publication', 'drift_check',
            'model_activation',
        }
        self.assertEqual(set(WORKFLOW_CONTRACT_MAP.keys()), expected_stages)

    def test_contract_map_has_required_keys(self) -> None:
        for stage, contract in WORKFLOW_CONTRACT_MAP.items():
            self.assertIn('contract_type', contract, f'{stage} missing contract_type')
            self.assertIn('required_evidence_types', contract, f'{stage} missing required_evidence_types')
            self.assertIn('gate_policy', contract, f'{stage} missing gate_policy')
            self.assertIn('description', contract, f'{stage} missing description')

    def test_validate_contract_passes_with_required_evidence(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        packet.add(EvidenceEntry(source='open-meteo', evidence_type=EVIDENCE_WEATHER, verified=True))
        violations = validate_workflow_contract('weather_ingest', packet)
        self.assertEqual(violations, [])

    def test_validate_contract_fails_with_missing_evidence(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        packet.add(EvidenceEntry(source='copernicus', evidence_type=EVIDENCE_SAR, verified=True))
        violations = validate_workflow_contract('weather_ingest', packet)
        self.assertEqual(len(violations), 1)
        self.assertIn(EVIDENCE_WEATHER, violations[0])

    def test_validate_contract_unknown_stage(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        violations = validate_workflow_contract('unknown_stage', packet)
        self.assertEqual(len(violations), 1)
        self.assertIn('unknown_stage', violations[0])

    def test_validate_contract_with_verification_packet(self) -> None:
        packet = VerificationPacket(
            cell_id='test-cell',
            region_key='colorado_rockies',
            anomaly_state=ANOMALY_NORMAL,
            attribution_bucket=ATTRIBUTION_UNATTRIBUTED,
            lineage={'evidence_types': [EVIDENCE_WEATHER, EVIDENCE_DEM]},
        )
        violations = validate_workflow_contract('risk_fusion', packet)
        self.assertEqual(violations, [])


class ScientistReviewGateTests(unittest.TestCase):
    def test_dry_run_auto_approves(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate('publication', packet, dry_run=True)
        self.assertTrue(decision.approved)
        self.assertFalse(decision.blocked)
        self.assertFalse(decision.needs_review)

    def test_override_is_deprecated_and_does_not_bypass(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate('publication', packet, override=True)
        self.assertFalse(decision.approved)
        self.assertTrue(decision.blocked)

    def test_unknown_stage_blocks(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate('nonexistent', packet)
        self.assertFalse(decision.approved)
        self.assertTrue(decision.blocked)

    def test_scientist_review_stage_blocks_without_approved_case(self) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate('publication', packet)
        self.assertFalse(decision.approved)
        self.assertTrue(decision.blocked)
        self.assertTrue(decision.needs_review)

    @patch('backend.common.scientist_review_gate._check_scientist_validation_case', return_value='case-123')
    def test_scientist_review_approves_with_approved_case(self, _mock) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate(
            'publication', packet, region_key='colorado_rockies', gate_key='publish_2026-05-08',
        )
        self.assertTrue(decision.approved)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.metadata.get('case_id'), 'case-123')

    @patch('backend.common.scientist_review_gate._check_scientist_validation_case', return_value='case-123')
    def test_model_activation_rejects_wrong_packet_class_even_with_case(self, _mock) -> None:
        decision = evaluate_scientist_review_gate(
            'model_activation', EvidencePacket(cell_id='candidate'),
            region_key='global', gate_key='mts_lstm_promotion_gate',
        )
        self.assertFalse(decision.approved)
        self.assertTrue(decision.blocked)
        self.assertTrue(any('expects VerificationPacket' in item for item in decision.contract_violations))

    @patch('backend.common.scientist_review_gate._check_scientist_validation_case', return_value=None)
    def test_scientist_review_blocks_with_no_credentials(self, _mock) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate(
            'publication', packet, region_key='colorado_rockies', gate_key='publish_2026-05-08',
        )
        self.assertFalse(decision.approved)
        self.assertTrue(decision.blocked)

    def test_hard_gate_with_valid_evidence_approves(self) -> None:
        packet = VerificationPacket(
            cell_id='test-cell',
            region_key='colorado_rockies',
            anomaly_state=ANOMALY_NORMAL,
            attribution_bucket=ATTRIBUTION_UNATTRIBUTED,
            lineage={'evidence_types': [EVIDENCE_WEATHER, EVIDENCE_DEM]},
        )
        decision = evaluate_scientist_review_gate('risk_fusion', packet)
        self.assertTrue(decision.approved)
        self.assertFalse(decision.needs_review)

    def test_hard_gate_with_missing_evidence_needs_review(self) -> None:
        packet = VerificationPacket(
            cell_id='test-cell',
            region_key='colorado_rockies',
            anomaly_state=ANOMALY_NORMAL,
            attribution_bucket=ATTRIBUTION_UNATTRIBUTED,
            lineage={'evidence_types': [EVIDENCE_WEATHER]},
        )
        decision = evaluate_scientist_review_gate('risk_fusion', packet)
        self.assertFalse(decision.approved)
        self.assertTrue(decision.needs_review)
        self.assertGreater(len(decision.contract_violations), 0)

    def test_review_decision_to_dict(self) -> None:
        decision = ReviewDecision(
            stage='publication',
            approved=False,
            blocked=False,
            needs_review=True,
            reason='test reason',
        )
        d = decision.to_dict()
        self.assertEqual(d['stage'], 'publication')
        self.assertFalse(d['approved'])
        self.assertTrue(d['needs_review'])

    @patch.dict(os.environ, {'SCIENTIST_REVIEW_ENABLED': 'false'}, clear=False)
    @patch('backend.common.scientist_review_gate._check_scientist_validation_case', return_value=None)
    def test_environment_flag_cannot_disable_gate(self, _check_mock) -> None:
        packet = EvidencePacket(cell_id='test-cell')
        decision = evaluate_scientist_review_gate('publication', packet)
        self.assertFalse(decision.approved)
        self.assertTrue(decision.blocked)


class ScientistValidationLookupTests(unittest.TestCase):
    @patch('backend.common.supabase_io.has_supabase_credentials', return_value=True)
    @patch('backend.common.supabase_io.rest_get')
    def test_reviewed_case_with_accepted_review_is_approved(self, rest_get_mock, _credentials_mock) -> None:
        def rows_for(table, *, params, **_kwargs):
            if table == 'scientist_validation_cases':
                return [{'id': 'case-1', 'requires_two_reviewers': False}]
            if table == 'scientist_validation_reviews':
                return [{'id': 'review-1', 'reviewer_id': 'scientist-1'}]
            raise AssertionError(f'unexpected table: {table}')

        rest_get_mock.side_effect = rows_for
        case_id = _check_scientist_validation_case('colorado_rockies', 'publish_2026-05-08')
        self.assertEqual(case_id, 'case-1')

        case_params = rest_get_mock.call_args_list[0].kwargs['params']
        self.assertIn('reviewed', case_params['status'])

    @patch('backend.common.supabase_io.has_supabase_credentials', return_value=True)
    @patch('backend.common.supabase_io.rest_get', return_value=[])
    def test_pending_case_is_not_approved(self, _rest_get_mock, _credentials_mock) -> None:
        self.assertIsNone(
            _check_scientist_validation_case('colorado_rockies', 'publish_2026-05-08')
        )


if __name__ == '__main__':
    unittest.main()
