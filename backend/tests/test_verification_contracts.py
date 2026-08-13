"""Tests for verification_contracts.py."""
from __future__ import annotations

import unittest

from backend.common.verification_contracts import (
    SAFETY_DISCLAIMER,
    PACKET_VERSION,
    VerificationPacket,
    EvidencePacket,
    EvidenceEntry,
    FusedSnowState,
    DiscrepancyAttribution,
    WorkflowContract,
    TYPED_WORKFLOW_CONTRACTS,
    evaluate_publication_gate,
    ANOMALY_NORMAL,
    ANOMALY_ANOMALY,
    ANOMALY_UNVERIFIED,
    ATTRIBUTION_FORCING_ERROR,
    ATTRIBUTION_UNATTRIBUTED,
    VALID_ATTRIBUTION_BUCKETS,
    VALID_ANOMALY_STATES,
    EVIDENCE_SAR,
    EVIDENCE_WEATHER,
    EVIDENCE_DEM,
    EVIDENCE_FIELD,
    now_utc,
)


class TestVerificationPacket(unittest.TestCase):
    def test_default_values(self):
        pkt = VerificationPacket(cell_id='cell_0', region_key='colorado_rockies')
        self.assertEqual(pkt.anomaly_state, ANOMALY_UNVERIFIED)
        self.assertEqual(pkt.attribution_bucket, ATTRIBUTION_UNATTRIBUTED)
        self.assertEqual(pkt.packet_version, PACKET_VERSION)
        self.assertEqual(pkt.disclaimer, SAFETY_DISCLAIMER)
        self.assertEqual(pkt.confidence, 0.0)

    def test_invalid_anomaly_state_raises(self):
        with self.assertRaises(ValueError):
            VerificationPacket(cell_id='c', region_key='r', anomaly_state='bogus')

    def test_invalid_attribution_raises(self):
        with self.assertRaises(ValueError):
            VerificationPacket(cell_id='c', region_key='r', attribution_bucket='bogus')

    def test_to_dict_roundtrip(self):
        pkt = VerificationPacket(
            cell_id='cell_5',
            region_key='great_himalaya',
            baseline_p25=0.3,
            baseline_p50=0.5,
            baseline_p75=0.7,
            observed=0.9,
            residual_zscore=2.0,
            anomaly_state=ANOMALY_ANOMALY,
            attribution_bucket=ATTRIBUTION_FORCING_ERROR,
            confidence=0.8,
        )
        d = pkt.to_dict()
        self.assertEqual(d['cell_id'], 'cell_5')
        self.assertEqual(d['baseline_p50'], 0.5)
        self.assertEqual(d['anomaly_state'], ANOMALY_ANOMALY)
        self.assertIn('disclaimer', d)


class TestEvidencePacket(unittest.TestCase):
    def test_add_and_verified_entries(self):
        pkt = EvidencePacket(cell_id='cell_0')
        pkt.add(EvidenceEntry(source='s1', evidence_type=EVIDENCE_SAR, value=0.5, verified=True))
        pkt.add(EvidenceEntry(source='openmeteo', evidence_type=EVIDENCE_WEATHER, value=0.3, verified=False))
        self.assertEqual(len(pkt.entries), 2)
        self.assertEqual(len(pkt.verified_entries), 1)

    def test_has_synthetic_detection(self):
        pkt = EvidencePacket(cell_id='cell_0')
        pkt.add(EvidenceEntry(source='proxy', evidence_type=EVIDENCE_WEATHER, metadata={'method': 'synthetic_heuristic'}))
        self.assertTrue(pkt.has_synthetic)

    def test_no_synthetic_when_real(self):
        pkt = EvidencePacket(cell_id='cell_0')
        pkt.add(EvidenceEntry(source='cosipy', evidence_type=EVIDENCE_WEATHER, metadata={'method': 'cosipy_v1'}))
        self.assertFalse(pkt.has_synthetic)


class TestFusedSnowState(unittest.TestCase):
    def test_defaults(self):
        s = FusedSnowState()
        self.assertIsNone(s.snow_depth_m)
        self.assertEqual(s.consensus_score, 0.0)
        self.assertEqual(s.disclaimer, SAFETY_DISCLAIMER)

    def test_to_dict(self):
        s = FusedSnowState(snow_depth_m=1.5, consensus_score=0.8, contributing_sensors=['sar', 'weather'])
        d = s.to_dict()
        self.assertEqual(d['snow_depth_m'], 1.5)
        self.assertEqual(d['consensus_score'], 0.8)
        self.assertIn('sar', d['contributing_sensors'])


class TestDiscrepancyAttribution(unittest.TestCase):
    def test_valid_bucket(self):
        attr = DiscrepancyAttribution(bucket=ATTRIBUTION_FORCING_ERROR, confidence=0.7)
        self.assertEqual(attr.bucket, ATTRIBUTION_FORCING_ERROR)

    def test_invalid_bucket_raises(self):
        with self.assertRaises(ValueError):
            DiscrepancyAttribution(bucket='bogus')

    def test_all_valid_buckets(self):
        for bucket in VALID_ATTRIBUTION_BUCKETS:
            attr = DiscrepancyAttribution(bucket=bucket)
            self.assertEqual(attr.bucket, bucket)


class TestNowUtc(unittest.TestCase):
    def test_returns_timezone_aware(self):
        ts = now_utc()
        self.assertIsNotNone(ts.tzinfo)


class TestWorkflowContract(unittest.TestCase):
    def test_typed_contracts_built_from_map(self):
        self.assertIn('publication', TYPED_WORKFLOW_CONTRACTS)
        pub = TYPED_WORKFLOW_CONTRACTS['publication']
        self.assertEqual(pub.gate_policy, 'scientist_review')
        self.assertEqual(pub.scientist_case_type, 'model_gate')

    def test_invalid_gate_policy_raises(self):
        with self.assertRaises(ValueError):
            WorkflowContract(
                stage='test',
                contract_type='EvidencePacket',
                required_evidence_types=[],
                gate_policy='bogus',
            )

    def test_hard_gate_fails_on_missing_evidence(self):
        contract = WorkflowContract(
            stage='terrain_extract',
            contract_type='EvidencePacket',
            required_evidence_types=[EVIDENCE_DEM],
            gate_policy='hard',
        )
        pkt = EvidencePacket(cell_id='c0', entries=[])
        passed, violations = contract.evaluate(pkt)
        self.assertFalse(passed)
        self.assertEqual(len(violations), 1)

    def test_hard_gate_passes_with_evidence(self):
        contract = WorkflowContract(
            stage='terrain_extract',
            contract_type='EvidencePacket',
            required_evidence_types=[EVIDENCE_DEM],
            gate_policy='hard',
        )
        pkt = EvidencePacket(cell_id='c0', entries=[
            EvidenceEntry(source='srtm', evidence_type=EVIDENCE_DEM, value=30.0, verified=True),
        ])
        passed, violations = contract.evaluate(pkt)
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

    def test_soft_gate_always_passes(self):
        contract = WorkflowContract(
            stage='weather_ingest',
            contract_type='EvidencePacket',
            required_evidence_types=[EVIDENCE_WEATHER],
            gate_policy='soft',
        )
        pkt = EvidencePacket(cell_id='c0', entries=[])
        passed, violations = contract.evaluate(pkt)
        self.assertTrue(passed)
        self.assertEqual(len(violations), 1)

    def test_routine_publication_passes(self):
        contract = TYPED_WORKFLOW_CONTRACTS['publication']
        pkt = EvidencePacket(cell_id='c0:publication', entries=[])
        passed, violations = contract.evaluate(pkt)
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

    def test_scientist_review_rejects_wrong_packet_class(self):
        contract = TYPED_WORKFLOW_CONTRACTS['publication']
        pkt = VerificationPacket(cell_id='c0:publication', region_key='c0')
        passed, violations = contract.evaluate(pkt)
        self.assertFalse(passed)
        self.assertTrue(any('expects EvidencePacket' in v for v in violations))

    def test_scientist_review_rejects_unverified_evidence(self):
        contract = WorkflowContract(
            stage='drift_check',
            contract_type='VerificationPacket',
            required_evidence_types=[EVIDENCE_FIELD],
            gate_policy='scientist_review',
            require_verified=True,
        )
        pkt = VerificationPacket(
            cell_id='c0:drift',
            region_key='c0',
            lineage={'evidence_types': [EVIDENCE_FIELD]},
        )
        passed, violations = contract.evaluate(pkt)
        self.assertTrue(passed)


class TestEvaluatePublicationGate(unittest.TestCase):
    def test_publish_eligible_passes(self):
        pkt = EvidencePacket(cell_id='c0:publication', entries=[])
        can_publish, violations, case_type = evaluate_publication_gate(
            pkt, publish_eligible=True,
        )
        self.assertTrue(can_publish)
        self.assertEqual(len(violations), 0)
        self.assertIsNone(case_type)

    def test_not_publish_eligible_blocks(self):
        pkt = EvidencePacket(cell_id='c0:publication', entries=[])
        can_publish, violations, case_type = evaluate_publication_gate(
            pkt, publish_eligible=False,
        )
        self.assertFalse(can_publish)
        self.assertTrue(len(violations) > 0)
        self.assertEqual(case_type, 'model_gate')

    def test_exception_release_blocks(self):
        pkt = EvidencePacket(cell_id='c0:publication', entries=[])
        can_publish, violations, case_type = evaluate_publication_gate(
            pkt, publish_eligible=True, is_exception=True,
        )
        self.assertFalse(can_publish)
        self.assertTrue(any('Exception release' in v for v in violations))
        self.assertEqual(case_type, 'model_gate')


if __name__ == '__main__':
    unittest.main()
