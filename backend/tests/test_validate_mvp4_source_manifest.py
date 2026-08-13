from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.validate_mvp4_source_manifest import validate_source_manifest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / 'schemas/source_manifest_request.template.json'


def _approved_manifest(payload: bytes, event_rows: bytes | None = None) -> dict:
    manifest = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))
    manifest.update({
        'source_id': 'independent_hma_source',
        'source_name': 'Independent HMA avalanche release catalog',
        'source_owner': 'Reviewed data owner',
        'source_url': 'https://example.invalid/source',
        'source_reference': 'release-2026-08',
        'source_role': 'core',
        'review_status': 'approved',
        'license_review_id': 'license-review-2026-08',
        'training_eligible': True,
        'production_scoring_eligible': False,
        'evidence_refs': ['evidence/source-review.json'],
    })
    manifest['license'].update({
        'status': 'permissive_core_reviewed',
        'reuse_scope': 'model training and approved internal review',
        'terms_url': 'https://example.invalid/terms',
    })
    manifest['coverage'].update({
        'regions': ['himalayas_nepal'],
        'positive_seasons': ['2021-2022', '2022-2023', '2023-2024'],
        'exact_time_positive_seasons': ['2021-2022', '2022-2023', '2023-2024'],
        'coverage_note': 'Three reviewed Nepal snow seasons.',
    })
    manifest['time_semantics'].update({
        'event_time_field': 'release_time',
        'event_time_kind': 'source_reported_avalanche_occurrence_time',
        'timezone': 'UTC',
        'precision': 'exact',
        'release_time_proven': True,
        'source_time_is_avalanche_occurrence_time': True,
    })
    manifest['spatial_semantics'].update({
        'geometry_type': 'point',
        'coordinate_reference': 'EPSG:4326',
        'coordinate_precision': 'exact_event_point',
        'has_exact_coordinates': True,
    })
    manifest['provenance'].update({
        'source_hash': hashlib.sha256(payload).hexdigest(),
        'source_hash_algorithm': 'sha256',
        'retrieved_at': '2026-08-03T12:00:00+00:00',
        'version_or_commit': 'release-2026-08',
    })
    canonical_event_rows = event_rows or b'canonical event rows are supplied separately\n'
    manifest['event_rows_sha256'] = hashlib.sha256(canonical_event_rows).hexdigest()
    manifest['independence'].update({
        'origin_source_family': 'independent_release_catalog',
        'independent_of_source_ids': ['hiaval_hma', 'gee_sar_scene_aware'],
        'independence_status': 'independent_after_overlap_review',
        'overlap_review_status': 'clean',
    })
    return manifest


def _valid_event_row() -> dict:
    return {
        'source_event_id': 'independent-event-1',
        'event_group_id': 'independent-event-1',
        'origin_source_family': 'independent_release_catalog',
        'source_key': 'independent_hma_source',
        'label_source': 'independent_hma_source',
        'region_key': 'himalayas_nepal',
        'event_time': '2023-12-04T05:30:00Z',
        'timestamp_precision': 'exact',
        'lat': 28.2,
        'lng': 86.8,
        'label': 1,
        'source_reference': 'source-row-1',
    }


class ValidateMvp4SourceManifestTests(unittest.TestCase):
    def test_request_template_is_blocked_and_never_accepted_as_core(self) -> None:
        manifest = json.loads(TEMPLATE_PATH.read_text(encoding='utf-8'))

        report = validate_source_manifest(manifest)

        self.assertFalse(report['passed'])
        self.assertEqual(report['decision'], 'blocked_source_request_pending')
        self.assertTrue(any('review_status' in error for error in report['errors']))
        self.assertTrue(any('training_eligible' in error for error in report['errors']))

    def test_approved_core_manifest_requires_and_matches_payload(self) -> None:
        payload = b'event_id,release_time\nsource-1,2023-12-04T05:30:00Z\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / 'source.csv'
            payload_path.write_bytes(payload)
            events_path = Path(tmpdir) / 'events.jsonl'
            event_rows = json.dumps(_valid_event_row(), sort_keys=True).encode() + b'\n'
            events_path.write_bytes(event_rows)

            report = validate_source_manifest(
                _approved_manifest(payload, event_rows),
                payload_path=payload_path,
                events_path=events_path,
            )

        self.assertTrue(report['passed'])
        self.assertEqual(report['decision'], 'source_manifest_accepted_for_normalization')
        self.assertEqual(report['checks']['payload_hash']['actual_sha256'], hashlib.sha256(payload).hexdigest())

    def test_payload_hash_mismatch_is_fail_closed(self) -> None:
        payload = b'actual payload\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / 'source.csv'
            payload_path.write_bytes(payload)
            manifest = _approved_manifest(b'different payload\n')

            report = validate_source_manifest(manifest, payload_path=payload_path)

        self.assertFalse(report['passed'])
        self.assertEqual(report['decision'], 'blocked_invalid_source_manifest')
        self.assertTrue(any('payload hash mismatch' in error for error in report['errors']))

    def test_core_manifest_without_payload_is_blocked(self) -> None:
        payload = b'event_id,release_time\nsource-1,2023-12-04T05:30:00Z\n'

        report = validate_source_manifest(_approved_manifest(payload))

        self.assertFalse(report['passed'])
        self.assertEqual(report['decision'], 'blocked_invalid_source_manifest')
        self.assertTrue(any('payload path is required' in error for error in report['errors']))

    def test_core_manifest_without_event_rows_is_blocked(self) -> None:
        payload = b'event_id,release_time\nsource-1,2023-12-04T05:30:00Z\n'

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / 'source.csv'
            payload_path.write_bytes(payload)
            report = validate_source_manifest(
                _approved_manifest(payload),
                payload_path=payload_path,
            )

        self.assertFalse(report['passed'])
        self.assertTrue(any('event rows path is required' in error for error in report['errors']))

    def test_canonical_exact_event_rows_are_checked_when_supplied(self) -> None:
        payload = b'event_id,release_time\nsource-1,2023-12-04T05:30:00Z\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload_path = root / 'source.csv'
            payload_path.write_bytes(payload)
            events_path = root / 'events.jsonl'
            events_path.write_text(
                json.dumps(_valid_event_row(), sort_keys=True) + '\n',
                encoding='utf-8',
            )
            event_rows = events_path.read_bytes()

            report = validate_source_manifest(
                _approved_manifest(payload, event_rows),
                payload_path=payload_path,
                events_path=events_path,
            )

        self.assertTrue(report['passed'])
        self.assertTrue(report['checks']['event_rows']['passed'])
        self.assertEqual(report['checks']['event_rows']['row_count'], 1)

    def test_canonical_day_row_cannot_enter_exact_time_intake(self) -> None:
        payload = b'event_id,release_time\nsource-1,2023-12-04T05:30:00Z\n'
        row = _valid_event_row()
        row.update({
            'timestamp_precision': 'day',
            'event_time_start': '2023-12-04T00:00:00Z',
            'event_time_end': '2023-12-05T00:00:00Z',
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload_path = root / 'source.csv'
            payload_path.write_bytes(payload)
            events_path = root / 'events.jsonl'
            events_path.write_text(json.dumps(row) + '\n', encoding='utf-8')
            event_rows = events_path.read_bytes()

            report = validate_source_manifest(
                _approved_manifest(payload, event_rows),
                payload_path=payload_path,
                events_path=events_path,
            )

        self.assertFalse(report['passed'])
        self.assertFalse(report['checks']['event_rows']['passed'])
        self.assertTrue(any('event rows' in error for error in report['errors']))

    def test_canonical_event_hash_mismatch_is_fail_closed(self) -> None:
        payload = b'event_id,release_time\nsource-1,2023-12-04T05:30:00Z\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload_path = root / 'source.csv'
            payload_path.write_bytes(payload)
            events_path = root / 'events.jsonl'
            event_rows = json.dumps(_valid_event_row(), sort_keys=True).encode() + b'\n'
            events_path.write_bytes(event_rows)

            report = validate_source_manifest(
                _approved_manifest(payload, b'different canonical rows\n'),
                payload_path=payload_path,
                events_path=events_path,
            )

        self.assertFalse(report['passed'])
        self.assertTrue(any('event_rows_sha256' in error for error in report['errors']))


if __name__ == '__main__':
    unittest.main()
