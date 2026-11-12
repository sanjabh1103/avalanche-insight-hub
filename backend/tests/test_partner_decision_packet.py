"""Tests for Partner_decision_packet.py — P10: Partner decision packet.

P10 exit gate: A single decision packet presents the verified inventory,
parser coverage, Swiss limitations, literature conformance, and parallel
lane readiness.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.common.Partner_decision_packet import (
    PartnerDecisionPacket,
    build_decision_packet,
    save_decision_packet,
    load_decision_packet,
    build_strategic_answer,
    verify_decision_packet_hash,
    verify_decision_packet_provenance,
)


class TestDecisionPacket(unittest.TestCase):
    """P10: The decision packet aggregates all P1-P9 evidence."""

    def test_packet_has_all_sections(self) -> None:
        """P10 exit gate: The packet has sections for P1-P9 and the strategic answer."""
        packet = build_decision_packet()
        d = packet.to_dict()
        self.assertIn('danger_semantics', d)  # P1
        self.assertIn('archive_discovery', d)  # P2
        self.assertIn('parser_coverage', d)  # P3
        self.assertIn('public_candidates', d)  # P4
        self.assertIn('coverage_audit', d)  # P5
        self.assertIn('swiss_reference', d)  # P6
        self.assertIn('swiss_conformance', d)  # P7
        self.assertIn('literature_matrix', d)  # P8
        self.assertIn('parallel_lanes', d)  # P9
        self.assertIn('strategic_answer', d)  # P10

    def test_packet_schema_version(self) -> None:
        packet = build_decision_packet()
        self.assertEqual(packet.schema_version, 'Partner_decision_packet_v1')

    def test_danger_semantics_complete(self) -> None:
        """P1 evidence is included in the packet."""
        packet = build_decision_packet()
        self.assertEqual(packet.danger_semantics['status'], 'complete')
        self.assertTrue(packet.danger_semantics['semantics_table_exists'])
        self.assertTrue(packet.danger_semantics['level_3_is_orange_not_high'])

    def test_parser_coverage_runs_real_parser(self) -> None:
        """P3 evidence comes from the real parser, not hardcoded values."""
        packet = build_decision_packet()
        # Status should reflect actual parser execution
        self.assertIn(packet.parser_coverage['status'], ('complete', 'fixture_parsed_but_blocked', 'parsed_zero_rows', 'fixture_missing', 'parser_error'))
        self.assertTrue(packet.parser_coverage['side_by_side_parser'])
        # If fixture exists, rows should be from real parsing (not hardcoded 25)
        if packet.parser_coverage['status'] in ('complete', 'fixture_parsed_but_blocked', 'parsed_zero_rows'):
            self.assertIsInstance(packet.parser_coverage['live_bulletin_rows_extracted'], int)
            # The real parser extracts 30+ rows, not the previously hardcoded 25
            self.assertNotEqual(packet.parser_coverage['live_bulletin_rows_extracted'], 25,
                                'Parser coverage must not use the old hardcoded value of 25')

    def test_parser_status_not_complete_when_provenance_unverified(self) -> None:
        """G1: Parser status must NOT be 'complete' when is_complete=False.
        
        If provenance is unverified, status must be 'fixture_parsed_but_blocked',
        never 'complete'. This is a negative-first test.
        """
        packet = build_decision_packet()
        if packet.parser_coverage.get('parse_error') == 'rows_missing_provenance':
            self.assertNotEqual(packet.parser_coverage['status'], 'complete',
                                'Status must not be complete when provenance is unverified')
            self.assertEqual(packet.parser_coverage['status'], 'fixture_parsed_but_blocked')
            self.assertFalse(packet.parser_coverage.get('is_complete', True),
                             'is_complete must be False when provenance is unverified')

    def test_parser_coverage_not_hardcoded(self) -> None:
        """The district list must come from real parsing, not a hardcoded list."""
        packet = build_decision_packet()
        districts = packet.parser_coverage['live_bulletin_districts']
        # If districts were extracted, they should NOT match the old hardcoded list exactly
        old_hardcoded = ['Poonch', 'Rajouri', 'Reasi', 'Ramban', 'Doda', 'Kishtwar',
                         'Udhampur', 'Anantnag', 'Baramulla', 'Kupwara', 'Bandipora',
                         'Ganderbal', 'Kargil', 'Leh', 'Chamba', 'Lahaul-Spiti',
                         'Kullu', 'Kinnaur', 'Shimla', 'Uttarkashi', 'Chamoli',
                         'Rudraprayag', 'Pithoragarh', 'Bagheshwar',
                         'North Sikkim', 'East Sikkim']
        if districts:
            self.assertNotEqual(districts, old_hardcoded,
                                'District list must not match the old hardcoded list')

    def test_swiss_reference_uuid_verified(self) -> None:
        """P6 UUID and retrieval snapshot state are represented honestly."""
        packet = build_decision_packet()
        self.assertTrue(packet.swiss_reference['doi_based_id_fixed'])
        self.assertEqual(packet.swiss_reference['uuid'], '54d7dc19-e70c-4998-bfb6-caffe41c83e6')
        if packet.swiss_reference['status'] == 'content_verified_snapshot':
            self.assertIsInstance(packet.swiss_reference['rf2_size_bytes'], int)
            self.assertRegex(packet.swiss_reference['rf2_content_hash'], r'^[0-9a-f]{64}$')
            self.assertEqual(packet.swiss_reference['rf2_total_rows'], 29296)
            self.assertEqual(packet.swiss_reference['rf2_level_5_count'], 82)
        else:
            self.assertNotIsInstance(packet.swiss_reference['rf1_size_bytes'], int)
            self.assertNotIsInstance(packet.swiss_reference['rf2_size_bytes'], int)
            self.assertIn('unverified', str(packet.swiss_reference['rf1_size_bytes']))
            self.assertIn('unverified', str(packet.swiss_reference['rf2_size_bytes']))
            self.assertEqual(packet.swiss_reference['status'], 'metadata_identity_asserted')

    def test_g7_swiss_reference_has_metadata_verification(self) -> None:
        """G7: Swiss reference must have granular metadata verification fields."""
        packet = build_decision_packet()
        meta = packet.swiss_reference.get('metadata_verification', {})
        self.assertIn('uuid_verified', meta)
        self.assertTrue(meta['uuid_verified'])
        self.assertIn('api_response_hash_verified', meta)
        self.assertIsInstance(meta['api_response_hash_verified'], bool)
        self.assertIn('resource_urls_verified', meta)
        self.assertIsInstance(meta['resource_urls_verified'], bool)
        self.assertIn('license_verified', meta)
        self.assertIsInstance(meta['license_verified'], bool)
        self.assertIn('byte_sizes_verified', meta)
        self.assertIsInstance(meta['byte_sizes_verified'], bool)
        self.assertIn('content_hashes_verified', meta)
        self.assertIsInstance(meta['content_hashes_verified'], bool)

    def test_swiss_conformance_documented(self) -> None:
        """P7 evidence is included in the packet."""
        packet = build_decision_packet()
        # G8: conformance_status now reflects separate verification dimensions
        self.assertNotEqual(packet.swiss_conformance['conformance_status'], 'conformant_with_paper')
        self.assertIn('paper', packet.swiss_conformance['conformance_status'])
        self.assertFalse(packet.swiss_conformance['denylist_change_needed'])

    def test_literature_matrix_included(self) -> None:
        """P8 evidence is included in the packet."""
        packet = build_decision_packet()
        self.assertGreater(packet.literature_matrix['total_papers'], 0)
        self.assertIn('key_finding', packet.literature_matrix)

    def test_parallel_lanes_included(self) -> None:
        """P9 evidence is included in the packet.

        G11: Track 1 is now BLOCKED (requires Partner-approved station data).
        T2A can still proceed without Partner approval.
        """
        packet = build_decision_packet()
        # G11: Not all lanes can proceed — Track 1 is blocked
        self.assertFalse(packet.parallel_lanes['all_can_proceed'],
                         'Track 1 is blocked — not all lanes can proceed')
        self.assertFalse(packet.parallel_lanes['none_require_Partner_approval'],
                         'Track 1 requires Partner approval')
        # T2A can only undergo engineering preparation; feature generation is
        # blocked until source contracts and Partner label gates pass.
        self.assertEqual(packet.parallel_lanes['lanes_can_proceed'], 0)
        self.assertEqual(packet.parallel_lanes['engineering_preparation_allowed_count'], 2)

    def test_strategic_answer_exists(self) -> None:
        """P10: The strategic answer is included."""
        packet = build_decision_packet()
        answer = packet.strategic_answer
        self.assertIn('question', answer)
        self.assertIn('answer', answer)
        self.assertIn('recommended_path', answer)
        self.assertIn('conclusion', answer)

    def test_strategic_answer_addresses_both_alternatives(self) -> None:
        """The strategic answer addresses both deep research and guesstimation."""
        answer = build_strategic_answer()
        self.assertIn('what_deep_research_provides', answer)
        self.assertIn('what_guesstimation_cannot_replace', answer)
        self.assertIn('risk_of_guesstimation', answer)

    def test_strategic_answer_qualified_parallel_preparation(self) -> None:
        """The strategic answer qualifies P9 lanes as specification, not implementation."""
        answer = build_strategic_answer()
        self.assertIn('recommended_path', answer)
        path = answer['recommended_path']
        # Must mention P9/parallel AND acknowledge implementation gap
        p9_step = [s for s in path if 'P9' in s or 'parallel' in s.lower()]
        self.assertTrue(len(p9_step) > 0, 'Must reference P9 parallel lanes')
        self.assertTrue(any('IMPLEMENT' in s or 'specification' in s.lower() or 'currently' in s.lower()
                           for s in p9_step),
                        'Must qualify that lanes are specification, not implementation')

    def test_strategic_answer_blocks_conditional_training(self) -> None:
        """The strategic answer blocks P11 conditional training until Partner approval."""
        answer = build_strategic_answer()
        path = answer['recommended_path']
        self.assertTrue(any('P11' in step and 'block' in step.lower() for step in path))

    def test_strategic_answer_no_fictional_class(self) -> None:
        """The strategic answer must NOT reference the fictional PartnerReviewedLabelImportV1."""
        answer = build_strategic_answer()
        risk_text = answer.get('risk_of_guesstimation', '')
        self.assertNotIn('PartnerReviewedLabelImportV1', risk_text,
                         'Must not reference fictional PartnerReviewedLabelImportV1 class')
        # Should mention the actual gap honestly
        self.assertIn('conversion path', risk_text.lower())

    def test_g10_strategic_answer_uses_dynamic_counts(self) -> None:
        """G10: Strategic answer must use dynamic counts from matrix, not hardcoded '2 use the full 5-level scale'."""
        answer = build_strategic_answer()
        deep_research = answer.get('what_deep_research_provides', [])
        # Must NOT contain the old hardcoded string
        hardcoded_old = '2 use the full 5-level scale (conformant)'
        for item in deep_research:
            self.assertNotIn(hardcoded_old, item,
                             f'Must not contain hardcoded "{hardcoded_old}" — use dynamic counts')
        # Should contain dynamic count from matrix
        from backend.common.Partner_literature_matrix import build_matrix_summary
        matrix = build_matrix_summary()
        conformant_count = matrix['conformant_count']
        verified_count = matrix['verified_count']
        # At least one item should mention the conformant count dynamically
        found_dynamic = any(str(conformant_count) in item for item in deep_research)
        self.assertTrue(found_dynamic,
                        f'Strategic answer must mention conformant count ({conformant_count}) dynamically')

    def test_g10_strategic_answer_no_unverified_swiss_counts(self) -> None:
        """G10: Strategic answer must not cite stale unverified Swiss counts."""
        answer = build_strategic_answer()
        all_text = json.dumps(answer)
        # Must NOT contain the old unverified Swiss counts
        self.assertNotIn('82 in Swiss data', all_text)
        # It must retain an explicit evidence qualifier: either the counts are
        # unverified, or they come from a content-verified snapshot rather than
        # being presented as a live Partner label source.
        guesstimation = answer.get('what_guesstimation_cannot_replace', [])
        found_qualifier = any(
            'UNVERIFIED' in item
            or 'unverified' in item.lower()
            or 'self-hashed RF2 retrieval snapshot' in item
            for item in guesstimation
        )
        self.assertTrue(found_qualifier,
                        'Strategic answer must qualify the Swiss evidence state')

    def test_g16_packet_has_provenance(self) -> None:
        """G16: Decision packet must have provenance with code revision and source hashes."""
        packet = build_decision_packet()
        self.assertIn('provenance', packet.to_dict())
        prov = packet.provenance
        self.assertIn('code_revision', prov)
        self.assertIn('source_file_hashes', prov)
        self.assertIn('source_file_count', prov)
        self.assertIn('generation_command', prov)
        self.assertIn('test_command', prov)
        # Source file hashes should include key modules
        self.assertIn('backend/common/Partner_decision_packet.py', prov['source_file_hashes'])
        self.assertIn('backend/common/Partner_bulletin_adapter.py', prov['source_file_hashes'])
        self.assertIn('backend/common/Partner_reviewed_label_conversion.py', prov['source_file_hashes'])

    def test_g16_provenance_source_hashes_are_valid_sha256(self) -> None:
        """G16: Source file hashes must be valid 64-character hex strings."""
        packet = build_decision_packet()
        prov = packet.provenance
        for filename, hash_val in prov['source_file_hashes'].items():
            if hash_val != 'file not found':
                self.assertEqual(len(hash_val), 64,
                                 f'{filename} hash must be 64 chars, got {len(hash_val)}')
                try:
                    int(hash_val, 16)
                except ValueError:
                    self.fail(f'{filename} hash is not valid hex: {hash_val}')

    def test_g16_provenance_binds_inputs_and_save_operation(self) -> None:
        packet = build_decision_packet()
        provenance = packet.provenance
        self.assertIn('input_file_hashes', provenance)
        self.assertIn('artifact_path', provenance)
        self.assertIn('save_command', provenance)
        self.assertIn('packet_hash_scope', provenance)

    def test_g16_provenance_recomputes_current_source_and_input_bytes(self) -> None:
        packet = build_decision_packet()
        valid, errors = verify_decision_packet_provenance(packet.to_dict())

        self.assertTrue(valid, errors)
        self.assertEqual(errors, [])

    def test_g16_provenance_rejects_mutated_recorded_hash(self) -> None:
        packet = build_decision_packet().to_dict()
        first_source = next(iter(packet['provenance']['source_file_hashes']))
        packet['provenance']['source_file_hashes'][first_source] = '0' * 64

        valid, errors = verify_decision_packet_provenance(packet)

        self.assertFalse(valid)
        self.assertTrue(any('hash mismatch' in error for error in errors))

    def test_g16_saved_packet_sidecar_matches_packet_hash(self) -> None:
        """The detached digest must bind to the canonical packet bytes."""
        packet = build_decision_packet()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'decision_packet.json'
            packet_hash = save_decision_packet(packet, path)
            sidecar_tokens = path.with_suffix(path.suffix + '.sha256').read_text(
                encoding='utf-8'
            ).split()
            self.assertGreaterEqual(len(sidecar_tokens), 1)
            self.assertEqual(sidecar_tokens[0], packet_hash)
            self.assertEqual(sidecar_tokens[0], load_decision_packet(path)['provenance']['packet_sha256'])

    def test_known_gaps_recorded(self) -> None:
        """Known gaps (F/G/H/I/J/K) must be explicitly recorded so they cannot be silently reintroduced."""
        packet = build_decision_packet()
        self.assertGreater(len(packet.known_gaps), 0)
        gap_ids = [g.split(':')[0] for g in packet.known_gaps]
        for expected_gap in ('GAP-F', 'GAP-G', 'GAP-H', 'GAP-I', 'GAP-J', 'GAP-K'):
            self.assertIn(expected_gap, gap_ids, f'{expected_gap} must be recorded in known_gaps')


class TestSaveLoadPacket(unittest.TestCase):
    """P10: Packet persistence."""

    def test_save_and_load(self) -> None:
        packet = build_decision_packet()
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_decision_packet(packet, path)
            loaded = load_decision_packet(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded['schema_version'], 'Partner_decision_packet_v1')
            self.assertIn('strategic_answer', loaded)
            self.assertTrue(verify_decision_packet_hash(loaded))
        finally:
            path.unlink()


if __name__ == '__main__':
    unittest.main()
