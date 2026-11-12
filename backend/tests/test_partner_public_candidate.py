"""Tests for Partner_public_candidate.py — P4: Public candidate inventory.

P4 exit gate: Every fetched candidate is complete, partial, duplicate, or failed;
no public candidate can enter preflight as a training label.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backend.common.Partner_public_candidate import (
    PublicBulletinCandidateV1,
    build_candidate_from_parse_result,
    detect_duplicate,
    build_candidate_manifest,
    save_candidate_manifest,
    load_candidate_manifest,
    PARSE_COMPLETE,
    PARSE_PARTIAL,
    PARSE_DUPLICATE,
    PARSE_FAILED,
    AUTHORITY_STATUS_UNREVIEWED,
    RIGHTS_STATUS_PENDING,
)


class TestPublicBulletinCandidateV1(unittest.TestCase):
    """P4: PublicBulletinCandidateV1 dataclass properties."""

    def test_training_eligible_is_always_false(self) -> None:
        """P4 exit gate: no public candidate can enter preflight as a training label."""
        candidate = build_candidate_from_parse_result(
            bulletin_id='Partner_AWB_30-Apr-2026',
            source_url='https://Partner.gov.in/Partner_AWB_30-Apr-2026.pdf',
            pdf_bytes=b'test content',
            parse_status=PARSE_COMPLETE,
            issue_date=date(2026, 4, 30),
        )
        self.assertFalse(candidate.training_eligible)
        self.assertFalse(candidate.can_enter_training)

    def test_authority_status_is_always_unreviewed(self) -> None:
        candidate = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='https://example.com/test.pdf',
            pdf_bytes=b'test', parse_status=PARSE_COMPLETE,
        )
        self.assertEqual(candidate.authority_status, AUTHORITY_STATUS_UNREVIEWED)

    def test_rights_status_is_always_pending(self) -> None:
        candidate = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='https://example.com/test.pdf',
            pdf_bytes=b'test', parse_status=PARSE_COMPLETE,
        )
        self.assertEqual(candidate.rights_status, RIGHTS_STATUS_PENDING)

    def test_observed_sha256_is_computed(self) -> None:
        content = b'test pdf content'
        candidate = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='https://example.com/test.pdf',
            pdf_bytes=content, parse_status=PARSE_COMPLETE,
        )
        expected = hashlib.sha256(content).hexdigest()
        self.assertEqual(candidate.observed_sha256, expected)

    def test_to_dict_includes_all_fields(self) -> None:
        candidate = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='https://example.com/test.pdf',
            pdf_bytes=b'test', parse_status=PARSE_COMPLETE,
            issue_date=date(2026, 4, 30),
            valid_from=date(2026, 4, 30),
            valid_until=date(2026, 5, 1),
            rows=[{'district': 'Poonch', 'danger_level': 1}],
        )
        d = candidate.to_dict()
        self.assertEqual(d['bulletin_id'], 'TEST')
        self.assertEqual(d['parse_status'], PARSE_COMPLETE)
        self.assertEqual(d['issue_date'], '2026-04-30')
        self.assertEqual(d['valid_until'], '2026-05-01')
        self.assertEqual(d['row_count'], 1)
        self.assertFalse(d['training_eligible'])
        self.assertEqual(d['authority_status'], AUTHORITY_STATUS_UNREVIEWED)

    def test_to_dict_from_dict_round_trip(self) -> None:
        """N6: to_dict() -> from_dict() round-trip preserves all fields and invariants."""
        candidate = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='https://example.com/test.pdf',
            pdf_bytes=b'test', parse_status=PARSE_COMPLETE,
            issue_date=date(2026, 4, 30),
            valid_from=date(2026, 4, 30),
            valid_until=date(2026, 5, 1),
            rows=[{'district': 'Poonch', 'danger_level': 1}],
        )
        d = candidate.to_dict()
        restored = PublicBulletinCandidateV1.from_dict(d)
        self.assertEqual(restored.bulletin_id, candidate.bulletin_id)
        self.assertEqual(restored.observed_sha256, candidate.observed_sha256)
        self.assertEqual(restored.parse_status, candidate.parse_status)
        self.assertEqual(restored.training_eligible, False)
        self.assertEqual(restored.authority_status, AUTHORITY_STATUS_UNREVIEWED)
        self.assertEqual(restored.rights_status, RIGHTS_STATUS_PENDING)
        self.assertEqual(restored.row_count, candidate.row_count)

    def test_frozen_dataclass(self) -> None:
        """Candidates are immutable."""
        candidate = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='https://example.com/test.pdf',
            pdf_bytes=b'test', parse_status=PARSE_COMPLETE,
        )
        with self.assertRaises((AttributeError, TypeError)):
            candidate.training_eligible = True  # type: ignore[misc]

    def test_g4_construction_with_training_eligible_true_raises(self) -> None:
        """G4 negative-first: Constructing with training_eligible=True must raise ValueError."""
        with self.assertRaises(ValueError, msg='training_eligible=True must be rejected'):
            PublicBulletinCandidateV1(
                bulletin_id='TEST',
                source_url='https://example.com/test.pdf',
                observed_sha256='a' * 64,
                parse_status=PARSE_COMPLETE,
                issue_date=None,
                valid_from=None,
                valid_until=None,
                bulletin_number=None,
                row_count=0,
                training_eligible=True,  # This must be rejected
            )

    def test_g4_construction_with_approved_authority_raises(self) -> None:
        """G4 negative-first: Constructing with authority_status='approved' must raise."""
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1(
                bulletin_id='TEST',
                source_url='https://example.com/test.pdf',
                observed_sha256='a' * 64,
                parse_status=PARSE_COMPLETE,
                issue_date=None,
                valid_from=None,
                valid_until=None,
                bulletin_number=None,
                row_count=0,
                authority_status='approved',  # This must be rejected
            )

    def test_g4_construction_with_approved_rights_raises(self) -> None:
        """G4 negative-first: Constructing with rights_status='approved' must raise."""
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1(
                bulletin_id='TEST',
                source_url='https://example.com/test.pdf',
                observed_sha256='a' * 64,
                parse_status=PARSE_COMPLETE,
                issue_date=None,
                valid_from=None,
                valid_until=None,
                bulletin_number=None,
                row_count=0,
                rights_status='approved',  # This must be rejected
            )

    def test_g4_construction_with_invalid_sha256_raises(self) -> None:
        """G4 negative-first: Constructing with invalid SHA-256 must raise."""
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1(
                bulletin_id='TEST',
                source_url='https://example.com/test.pdf',
                observed_sha256='not-a-hex-string',  # Invalid
                parse_status=PARSE_COMPLETE,
                issue_date=None,
                valid_from=None,
                valid_until=None,
                bulletin_number=None,
                row_count=0,
            )

    def test_g4_construction_with_short_sha256_raises(self) -> None:
        """G4 negative-first: Constructing with short SHA-256 must raise."""
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1(
                bulletin_id='TEST',
                source_url='https://example.com/test.pdf',
                observed_sha256='abc123',  # Too short
                parse_status=PARSE_COMPLETE,
                issue_date=None,
                valid_from=None,
                valid_until=None,
                bulletin_number=None,
                row_count=0,
            )

    def test_g4_from_dict_rejects_invariant_overrides(self) -> None:
        """G4: untrusted JSON cannot silently acquire or lose privileges."""
        # Input dict with malicious overrides must be rejected, not normalized.
        malicious = {
            'bulletin_id': 'TEST',
            'source_url': 'https://example.com/test.pdf',
            'observed_sha256': 'a' * 64,
            'parse_status': PARSE_COMPLETE,
            'issue_date': None,
            'valid_from': None,
            'valid_until': None,
            'bulletin_number': None,
            'row_count': 0,
            'training_eligible': True,  # Must be forced to False
            'authority_status': 'approved',  # Must be forced to 'unreviewed'
            'rights_status': 'approved',  # Must be forced to 'pending'
        }
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1.from_dict(malicious)

    def test_from_dict_rejects_unknown_fields(self) -> None:
        payload = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='url', pdf_bytes=b'test',
            parse_status=PARSE_COMPLETE,
        ).to_dict()
        payload['unexpected'] = 'must not be ignored'
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1.from_dict(payload)

    def test_from_dict_rejects_inconsistent_row_count(self) -> None:
        payload = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='url', pdf_bytes=b'test',
            parse_status=PARSE_COMPLETE,
            rows=[{'district': 'Poonch', 'danger_level': 1}],
        ).to_dict()
        payload['row_count'] = 0
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1.from_dict(payload)

    def test_from_dict_rejects_invalid_validity_order(self) -> None:
        payload = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='url', pdf_bytes=b'test',
            parse_status=PARSE_COMPLETE,
            valid_from=date(2026, 4, 30),
            valid_until=date(2026, 5, 1),
        ).to_dict()
        payload['valid_from'] = '2026-05-02'
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1.from_dict(payload)

    def test_g4_from_dict_rejects_invalid_sha256(self) -> None:
        """G4: from_dict() must reject invalid SHA-256 via __post_init__."""
        malicious = {
            'bulletin_id': 'TEST',
            'source_url': 'https://example.com/test.pdf',
            'observed_sha256': 'invalid',
            'parse_status': PARSE_COMPLETE,
            'issue_date': None,
            'valid_from': None,
            'valid_until': None,
            'bulletin_number': None,
            'row_count': 0,
        }
        with self.assertRaises(ValueError):
            PublicBulletinCandidateV1.from_dict(malicious)

    def test_is_complete_property(self) -> None:
        complete = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='url', pdf_bytes=b'test',
            parse_status=PARSE_COMPLETE,
        )
        partial = build_candidate_from_parse_result(
            bulletin_id='TEST', source_url='url', pdf_bytes=b'test',
            parse_status=PARSE_PARTIAL,
        )
        self.assertTrue(complete.is_complete)
        self.assertFalse(partial.is_complete)
        self.assertTrue(partial.is_parseable)


class TestDuplicateDetection(unittest.TestCase):
    """P4: Duplicate detection by hash."""

    def test_detect_duplicate_finds_match(self) -> None:
        content = b'same content'
        c1 = build_candidate_from_parse_result(
            bulletin_id='B1', source_url='url1', pdf_bytes=content,
            parse_status=PARSE_COMPLETE,
        )
        c2 = build_candidate_from_parse_result(
            bulletin_id='B2', source_url='url2', pdf_bytes=content,
            parse_status=PARSE_COMPLETE,
        )
        match = detect_duplicate(c2, [c1])
        self.assertIsNotNone(match)
        self.assertEqual(match.bulletin_id, 'B1')

    def test_detect_duplicate_no_match(self) -> None:
        c1 = build_candidate_from_parse_result(
            bulletin_id='B1', source_url='url1', pdf_bytes=b'content1',
            parse_status=PARSE_COMPLETE,
        )
        c2 = build_candidate_from_parse_result(
            bulletin_id='B2', source_url='url2', pdf_bytes=b'content2',
            parse_status=PARSE_COMPLETE,
        )
        match = detect_duplicate(c2, [c1])
        self.assertIsNone(match)


class TestCandidateManifest(unittest.TestCase):
    """P4: Manifest building and eligibility verification."""

    def test_manifest_counts_by_status(self) -> None:
        candidates = [
            build_candidate_from_parse_result('B1', 'url1', b'c1', PARSE_COMPLETE),
            build_candidate_from_parse_result('B2', 'url2', b'c2', PARSE_PARTIAL),
            build_candidate_from_parse_result('B3', 'url3', b'c3', PARSE_FAILED),
        ]
        manifest = build_candidate_manifest(candidates)
        self.assertEqual(manifest['total_candidates'], 3)
        self.assertEqual(manifest['complete'], 1)
        self.assertEqual(manifest['partial'], 1)
        self.assertEqual(manifest['failed'], 1)

    def test_manifest_verifies_all_ineligible(self) -> None:
        """P4 exit gate: all candidates must have training_eligible=false."""
        candidates = [
            build_candidate_from_parse_result('B1', 'url1', b'c1', PARSE_COMPLETE),
            build_candidate_from_parse_result('B2', 'url2', b'c2', PARSE_PARTIAL),
        ]
        manifest = build_candidate_manifest(candidates)
        self.assertTrue(manifest['all_training_ineligible'])
        self.assertTrue(manifest['authority_status_all_unreviewed'])
        self.assertTrue(manifest['rights_status_all_pending'])

    def test_manifest_unique_by_hash(self) -> None:
        content = b'same'
        candidates = [
            build_candidate_from_parse_result('B1', 'url1', content, PARSE_COMPLETE),
            build_candidate_from_parse_result('B2', 'url2', content, PARSE_COMPLETE),
            build_candidate_from_parse_result('B3', 'url3', b'different', PARSE_COMPLETE),
        ]
        manifest = build_candidate_manifest(candidates)
        self.assertEqual(manifest['unique_by_hash'], 2)


class TestSaveLoadManifest(unittest.TestCase):
    """P4: Manifest persistence."""

    def test_save_and_load(self) -> None:
        candidates = [
            build_candidate_from_parse_result('B1', 'url1', b'c1', PARSE_COMPLETE),
        ]
        manifest = build_candidate_manifest(candidates)
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_candidate_manifest(manifest, path)
            loaded = load_candidate_manifest(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded['total_candidates'], 1)
        finally:
            path.unlink()


if __name__ == '__main__':
    unittest.main()
