"""Tests for swiss_conformance_audit.py — P7: Swiss conformance decision.

P7 exit gate: The Level 5 merge is documented as a conformance decision;
no denylist change is needed because the reproduction code matches the paper.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import hashlib
import json
import tempfile

from backend.common.swiss_conformance_audit import (
    SwissConformanceDecision,
    build_conformance_decision,
    load_swiss_verification_snapshot,
    save_swiss_verification_snapshot,
    verify_swiss_level_5_merge,
)


class TestSwissConformanceDecision(unittest.TestCase):
    """P7: The Level 5 merge is documented and conformant."""

    def test_conformance_status_is_conformant(self) -> None:
        """G8: Conformance status reflects separate verification dimensions."""
        decision = build_conformance_decision()
        # G8: No longer 'conformant_with_paper' — now reflects partial verification
        self.assertNotEqual(decision.conformance_status, 'conformant_with_paper')
        self.assertIn('paper', decision.conformance_status)
        self.assertIn('code', decision.conformance_status)

    def test_swiss_uses_4_levels(self) -> None:
        decision = build_conformance_decision()
        self.assertEqual(decision.swiss_reproduction_labels, (1, 2, 3, 4))
        self.assertTrue(decision.swiss_reproduction_clips_level_5)

    def test_swiss_counts_are_unverified(self) -> None:
        """Swiss data file is not present — counts must be marked unverified."""
        decision = build_conformance_decision()
        self.assertFalse(decision.swiss_rf2_counts_verified,
                         'Counts must be unverified when Swiss data file is not present')

    def test_g8_separate_verification_dimensions(self) -> None:
        """G8: Swiss conformance must have 4 separate verification dimensions."""
        decision = build_conformance_decision()
        # Paper policy is documented (RAvaFcast uses 4-level scale)
        self.assertTrue(decision.paper_policy_documented)
        # Code transform is verified (train_rf4.py clips to 1-4)
        self.assertTrue(decision.code_transform_verified)
        # Dataset is NOT verified (data file not present)
        self.assertFalse(decision.dataset_verified)
        # Runtime reproduction is NOT verified
        self.assertFalse(decision.runtime_reproduction_verified)

    def test_g8_conformance_status_reflects_partial_verification(self) -> None:
        """G8: Conformance status must reflect that only paper+code are verified."""
        decision = build_conformance_decision()
        # Status should NOT be 'conformant_with_paper' (too broad)
        # Should indicate partial verification
        self.assertNotEqual(decision.conformance_status, 'conformant_with_paper')
        self.assertIn('paper', decision.conformance_status)
        self.assertIn('code', decision.conformance_status)
        self.assertIn('dataset', decision.conformance_status)

    def test_Partner_uses_5_levels(self) -> None:
        decision = build_conformance_decision()
        self.assertTrue(decision.Partner_uses_5_levels)
        self.assertEqual(decision.Partner_level_5_label, 'black')  # P1: Partner color
        self.assertEqual(decision.Partner_level_5_eaws_name, 'very_high')  # P1: EAWS

    def test_no_denylist_change_needed(self) -> None:
        """P7 exit gate: no denylist change is needed."""
        decision = build_conformance_decision()
        self.assertFalse(decision.denylist_change_needed)
        self.assertFalse(decision.planner_approval_needed)

    def test_can_use_swiss_as_reference_with_caveat(self) -> None:
        decision = build_conformance_decision()
        self.assertTrue(decision.can_use_swiss_as_reference)
        self.assertIsNotNone(decision.caveat)
        self.assertIn('Level 5', decision.caveat)

    def test_to_dict(self) -> None:
        decision = build_conformance_decision()
        d = decision.to_dict()
        self.assertEqual(d['schema_version'], 'swiss_conformance_audit_v1')
        # G8: conformance_status no longer 'conformant_with_paper'
        self.assertNotEqual(d['conformance_status'], 'conformant_with_paper')
        # G8: should have separate verification dimensions
        self.assertIn('paper_policy_documented', d)
        self.assertIn('code_transform_verified', d)
        self.assertIn('dataset_verified', d)
        self.assertIn('runtime_reproduction_verified', d)

    def test_frozen_dataclass(self) -> None:
        decision = build_conformance_decision()
        with self.assertRaises((AttributeError, TypeError)):
            decision.conformance_status = 'non_conformant'  # type: ignore[misc]


class TestVerifySwissLevel5Merge(unittest.TestCase):
    """P7: Verification of the Swiss Level 5 merge behavior."""

    def test_verification_returns_result(self) -> None:
        result = verify_swiss_level_5_merge()
        # Either verified (data exists) or not (data missing)
        self.assertIn('verified', result)
        if result['verified']:
            self.assertIn('level_5_count', result)
            self.assertGreater(result['level_5_count'], 0)  # 82 Level 5 entries
            self.assertEqual(result['clip_target'], '1-4')

    def test_n7_cwd_independence(self) -> None:
        """N7: verify_swiss_level_5_merge() must work regardless of working directory."""
        import os
        original_cwd = os.getcwd()
        try:
            # Change to a different directory (temp dir)
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                result = verify_swiss_level_5_merge()
                # Should still produce a valid result (verified or not)
                # Path resolution uses __file__, not CWD
                self.assertIn('verified', result)
        finally:
            os.chdir(original_cwd)

    def test_content_verification_requires_valid_schema_and_hash(self) -> None:
        csv_bytes = b'id,dangerLevel\n1,5\n2,4\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / 'rf2.csv'
            data_path.write_bytes(csv_bytes)
            expected = hashlib.sha256(csv_bytes).hexdigest()
            result = verify_swiss_level_5_merge(data_path, expected_sha256=expected)
            self.assertTrue(result['verified'])
            self.assertEqual(result['content_sha256'], expected)
            self.assertEqual(result['total_rows'], 2)
            self.assertEqual(result['level_5_count'], 1)
            self.assertEqual(result['danger_column'], 'dangerLevel')

            mismatch = verify_swiss_level_5_merge(data_path, expected_sha256='a' * 64)
            self.assertFalse(mismatch['verified'])
            self.assertIn('hash mismatch', mismatch['reason'])

    def test_invalid_danger_values_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / 'rf2.csv'
            data_path.write_text('id,danger_level\n1,5\n2,6\n', encoding='utf-8')
            result = verify_swiss_level_5_merge(data_path)
            self.assertFalse(result['verified'])
            self.assertEqual(result['invalid_danger_level_rows'], 1)

    def test_verified_result_round_trips_as_self_hashed_snapshot(self) -> None:
        csv_bytes = b'id,DangerLevel\n1,5\n2,1\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / 'rf2.csv'
            snapshot_path = Path(tmpdir) / 'snapshot.json'
            data_path.write_bytes(csv_bytes)
            result = verify_swiss_level_5_merge(data_path)
            snapshot_hash = save_swiss_verification_snapshot(
                result,
                snapshot_path,
                metadata_response_sha256='b' * 64,
            )
            loaded = load_swiss_verification_snapshot(snapshot_path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded['snapshot_sha256'], snapshot_hash)
            self.assertFalse(loaded['raw_bytes_retained'])
            self.assertEqual(loaded['content_sha256'], result['content_sha256'])

            tampered = json.loads(snapshot_path.read_text(encoding='utf-8'))
            tampered['level_5_count'] = 999
            snapshot_path.write_text(json.dumps(tampered), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                load_swiss_verification_snapshot(snapshot_path)

    def test_unverified_result_cannot_be_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, 'only a verified'):
                save_swiss_verification_snapshot(
                    {'verified': False}, Path(tmpdir) / 'snapshot.json'
                )


if __name__ == '__main__':
    unittest.main()
