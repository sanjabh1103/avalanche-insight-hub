"""Adversarial regression tests for the Pir Panjal decision record runtime loader.

G3: Runtime refuses a missing, modified, wrong-sector, or wrong-band decision record.
G4: Bundle mutation fails even when all internal references are changed consistently,
because the trust root is the externally supplied expected digest.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.common.pir_panjal_decision_record import (
    DecisionRecordError,
    decision_record_manifest_binding,
    load_decision_record,
    validate_decision_record_bytes,
    validate_poc_scope,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PATH = REPO_ROOT / 'docs' / 'MVP4' / '00_governance' / 'PIR_PANJAL_POC_DECISION_RECORD.json'


def _canonical_record_dict() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding='utf-8'))


class DecisionRecordLoaderTests(unittest.TestCase):
    def test_load_canonical_record_succeeds(self) -> None:
        record = load_decision_record(RECORD_PATH)
        self.assertEqual(record.selected_sector, 'pir_panjal_nw_himalaya')
        self.assertEqual(record.elevation_band, 'middle')
        self.assertEqual(record.headline_horizon_hours, 48)
        self.assertEqual(record.track_id, 'track_1_indian_candidate')
        self.assertFalse(record.Partner_approved)
        self.assertFalse(record.official_warning_eligible)
        self.assertTrue(record.scope_hash_required)
        self.assertEqual(record.evidence_class, 'pipeline-proof-only')
        # The raw-byte hash must be a valid SHA-256
        self.assertEqual(len(record.decision_record_sha256), 64)

    def test_load_with_matching_expected_sha256_succeeds(self) -> None:
        raw = RECORD_PATH.read_bytes()
        expected = hashlib.sha256(raw).hexdigest()
        record = load_decision_record(RECORD_PATH, expected_sha256=expected)
        self.assertEqual(record.decision_record_sha256, expected)

    def test_load_with_mismatched_expected_sha256_fails(self) -> None:
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record(RECORD_PATH, expected_sha256='a' * 64)
        self.assertIn('byte hash mismatch', str(ctx.exception))

    def test_load_with_invalid_expected_sha256_format_fails(self) -> None:
        with self.assertRaises(DecisionRecordError):
            load_decision_record(RECORD_PATH, expected_sha256='not-a-hash')

    def test_missing_file_fails(self) -> None:
        with self.assertRaises(DecisionRecordError):
            load_decision_record('/nonexistent/path.json')

    def test_wrong_sector_fails(self) -> None:
        record = _canonical_record_dict()
        record['selected_sector'] = 'himalayas_nepal'
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('selected_sector', str(ctx.exception))

    def test_wrong_elevation_band_fails(self) -> None:
        record = _canonical_record_dict()
        record['representative_regime']['elevation_band'] = 'lower'
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('elevation_band', str(ctx.exception))

    def test_wrong_horizon_fails(self) -> None:
        record = _canonical_record_dict()
        record['forecast']['headline_horizon_hours'] = 24
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('headline_horizon_hours', str(ctx.exception))

    def test_Partner_approved_true_fails(self) -> None:
        record = _canonical_record_dict()
        record['Partner_approved'] = True
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('Partner_approved', str(ctx.exception))

    def test_official_warning_eligible_true_fails(self) -> None:
        record = _canonical_record_dict()
        record['official_warning_eligible'] = True
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('official_warning_eligible', str(ctx.exception))

    def test_missing_non_claim_fails(self) -> None:
        record = _canonical_record_dict()
        record['non_claims'] = record['non_claims'][:-1]
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('non_claims', str(ctx.exception))

    def test_wrong_engine_role_fails(self) -> None:
        record = _canonical_record_dict()
        record['engine_roles']['hybrid_ml'] = 'production'
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('hybrid_ml', str(ctx.exception))

    def test_scope_hash_required_false_fails(self) -> None:
        record = _canonical_record_dict()
        record['immutability']['scope_hash_required'] = False
        raw = json.dumps(record, sort_keys=True).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw)
        self.assertIn('scope_hash_required', str(ctx.exception))

    def test_self_consistent_mutation_fails_with_external_digest(self) -> None:
        """G4: Bundle mutation fails even when all internal references are changed
        consistently, because the trust root is the externally supplied digest."""
        raw = RECORD_PATH.read_bytes()
        expected_sha256 = hashlib.sha256(raw).hexdigest()
        # Mutate the record (change sector + band + horizon consistently)
        record = _canonical_record_dict()
        record['selected_sector'] = 'himalayas_nepal'
        record['representative_regime']['elevation_band'] = 'lower'
        record['forecast']['headline_horizon_hours'] = 24
        mutated_raw = json.dumps(record, sort_keys=True).encode('utf-8')
        # The mutated bytes have a different hash, so the external digest rejects
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(mutated_raw, expected_sha256=expected_sha256)
        self.assertIn('byte hash mismatch', str(ctx.exception))

    def test_malformed_json_fails(self) -> None:
        with self.assertRaises(DecisionRecordError):
            validate_decision_record_bytes(b'{not valid json')

    def test_non_object_json_fails(self) -> None:
        with self.assertRaises(DecisionRecordError):
            validate_decision_record_bytes(b'[]')

    def test_g7_malformed_utf8_fails_cleanly(self) -> None:
        """G7: Malformed UTF-8 bytes produce a controlled DecisionRecordError,
        not a UnicodeDecodeError traceback."""
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(b'{\xff\xfe\x00\x01}')
        self.assertIn('UTF-8', str(ctx.exception))

    def test_g7_malformed_utf8_with_expected_hash_fails_cleanly(self) -> None:
        """G7: Malformed UTF-8 with an expected hash still fails cleanly."""
        raw = b'{\xff\xfe\x00\x01}'
        expected = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_decision_record_bytes(raw, expected_sha256=expected)
        self.assertIn('UTF-8', str(ctx.exception))


class DecisionRecordScopeValidationTests(unittest.TestCase):
    def test_validate_poc_scope_matching_succeeds(self) -> None:
        record = load_decision_record(RECORD_PATH)
        validate_poc_scope(
            record,
            region_key='pir_panjal_nw_himalaya',
            elevation_band='middle',
            headline_horizon_hours=48,
        )

    def test_validate_poc_scope_wrong_region_fails(self) -> None:
        record = load_decision_record(RECORD_PATH)
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_poc_scope(
                record,
                region_key='himalayas_nepal',
                elevation_band='middle',
            )
        self.assertIn('region_key', str(ctx.exception))

    def test_validate_poc_scope_wrong_band_fails(self) -> None:
        record = load_decision_record(RECORD_PATH)
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_poc_scope(
                record,
                region_key='pir_panjal_nw_himalaya',
                elevation_band='lower',
            )
        self.assertIn('elevation_band', str(ctx.exception))

    def test_validate_poc_scope_wrong_horizon_fails(self) -> None:
        record = load_decision_record(RECORD_PATH)
        with self.assertRaises(DecisionRecordError) as ctx:
            validate_poc_scope(
                record,
                region_key='pir_panjal_nw_himalaya',
                elevation_band='middle',
                headline_horizon_hours=24,
            )
        self.assertIn('headline_horizon_hours', str(ctx.exception))


class DecisionRecordManifestBindingTests(unittest.TestCase):
    def test_manifest_binding_contains_all_required_fields(self) -> None:
        record = load_decision_record(RECORD_PATH)
        binding = decision_record_manifest_binding(record)
        self.assertIn('decision_id', binding)
        self.assertIn('decision_record_sha256', binding)
        self.assertIn('selected_sector', binding)
        self.assertIn('elevation_band', binding)
        self.assertIn('headline_horizon_hours', binding)
        self.assertIn('track_id', binding)
        self.assertIn('evidence_class', binding)
        self.assertIn('official_warning_eligible', binding)
        self.assertIn('scope_hash_required', binding)
        self.assertEqual(binding['selected_sector'], 'pir_panjal_nw_himalaya')
        self.assertEqual(binding['elevation_band'], 'middle')
        self.assertEqual(binding['headline_horizon_hours'], 48)
        self.assertFalse(binding['official_warning_eligible'])
        self.assertTrue(binding['scope_hash_required'])


if __name__ == '__main__':
    unittest.main()
