"""Negative-first tests for lane source contracts."""
from __future__ import annotations

import unittest

from backend.common.Partner_lane_sources import (
    PartnerLaneSourceContractV1,
    SOURCE_CONTRACT_STATUS_CONTENT_VERIFIED,
    build_lane_source_contracts,
    content_schema_hash,
    validate_lane_source_contracts,
)


class TestLaneSourceContracts(unittest.TestCase):
    def test_t2a_plan_is_station_free_and_blocked_without_bytes(self) -> None:
        contracts = build_lane_source_contracts('t2a')
        self.assertEqual({item.source_kind for item in contracts}, {'forcing', 'terrain'})
        result = validate_lane_source_contracts('t2a', contracts)
        self.assertFalse(result.allowed)
        self.assertTrue(result.blocker_messages)

    def test_track1_requires_station_anchor_contract(self) -> None:
        contracts = build_lane_source_contracts('track1')
        result = validate_lane_source_contracts('track1', contracts[:1])
        self.assertFalse(result.allowed)
        self.assertTrue(any('missing required source kinds' in item for item in result.blocker_messages))

    def test_cross_lane_station_contract_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PartnerLaneSourceContractV1(
                source_id='bad', track='t2a', source_kind='station_anchor', provider='Partner'
            )

    def test_content_verified_source_requires_rights_and_hashes(self) -> None:
        schema_hash = content_schema_hash({'columns': ['temperature', 'wind']})
        contract = PartnerLaneSourceContractV1(
            source_id='forcing', track='t2a', source_kind='forcing', provider='test',
            source_hash='a' * 64, schema_hash=schema_hash,
            rights_status='approved', permitted_track='t2a',
            temporal_coverage='2025-11/2026-05', spatial_coverage='pir-panjal',
            status=SOURCE_CONTRACT_STATUS_CONTENT_VERIFIED,
        )
        self.assertTrue(contract.feature_generation_ready)
        self.assertEqual(content_schema_hash({'columns': ['temperature', 'wind']}), schema_hash)

    def test_lane_summary_contains_source_contracts(self) -> None:
        from backend.common.Partner_parallel_lanes import build_lane_summary
        summary = build_lane_summary()
        self.assertIn('source_contracts', summary)
        self.assertIn('t2a', summary['source_contracts'])
        self.assertIn('track1', summary['source_contracts'])


if __name__ == '__main__':
    unittest.main()
