from __future__ import annotations

import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.scripts.build_reviewed_hma_catalog import build_catalog, write_catalog


class ReviewedHmaCatalogTests(unittest.TestCase):
    def _snapshot(self, root: Path, name: str, manifest: dict, rows: list[dict]) -> Path:
        path = root / name
        path.mkdir()
        payload = ''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n' for row in rows).encode()
        import hashlib
        manifest = {**manifest, 'events_path': 'events.jsonl', 'event_rows_sha256': hashlib.sha256(payload).hexdigest()}
        (path / 'events.jsonl').write_bytes(payload)
        (path / 'snapshot_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return path

    def _reviewed_overlap(self, exact: Path, bounded: Path) -> dict:
        exact_payload = (exact / 'events.jsonl').read_bytes()
        bounded_payload = (bounded / 'events.jsonl').read_bytes()
        return {
            'status': 'reviewed',
            'source_a': 'hiaval_hma',
            'source_b': 'everest_sentinel1',
            'source_a_sha256': hashlib.sha256(exact_payload).hexdigest(),
            'source_b_sha256': hashlib.sha256(bounded_payload).hexdigest(),
            'source_a_record_count': 1,
            'source_b_record_count': 1,
            'source_a_non_overlap_count': 1,
            'source_b_non_overlap_count': 1,
            'independent_positive_source_count': 2,
            'same_event_must_not_count_as_independent': True,
        }

    def test_catalog_keeps_mixed_time_precision_and_is_not_training_eligible(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            exact = self._snapshot(root, 'hiaval', {
                'source_key': 'hiaval_hma', 'source_sha256': 'a',
                'license': 'CC BY 4.0', 'license_status': 'permissive_core_reviewed',
            }, [{
                'source_key': 'hiaval_hma', 'external_id': 'h1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-05T00:00:00Z',
                'event_time_end': '2018-01-06T00:00:00Z', 'timestamp_precision': 'day',
            }])
            bounded = self._snapshot(root, 'everest', {
                'source_key': 'everest_sentinel1', 'source_archive_sha256': 'b',
                'license': 'CC BY 4.0', 'license_status': 'permissive_shadow_reviewed',
            }, [{
                'source_key': 'everest_sentinel1', 'external_id': 'e1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-01T00:00:00Z', 'event_time_end': '2018-01-13T00:00:00Z',
                'timestamp_precision': 'bounded_12_day_detection_interval',
            }])
            overlap = root / 'overlap.json'
            overlap.write_text(json.dumps(self._reviewed_overlap(exact, bounded)), encoding='utf-8')

            rows, manifest, overlap_payload = build_catalog(exact, bounded, overlap)
            output = root / 'out'
            write_catalog(output, rows, manifest, overlap_payload)

            self.assertEqual(manifest['source_keys'], ['everest_sentinel1', 'hiaval_hma'])
            self.assertEqual(manifest['included_record_count'], 2)
            self.assertEqual(manifest['exact_timestamp_record_count'], 0)
            self.assertEqual(manifest['bounded_interval_record_count'], 1)
            self.assertEqual(manifest['label_time_contract'], 'interval_censored_core_v1')
            self.assertEqual(manifest['positive_seasons_by_region']['himalayas_nepal'], ['2017-2018'])
            self.assertFalse(manifest['training_eligible'])
            self.assertTrue((output / 'source_overlap_report.json').exists())

    def test_catalog_rejects_unreviewed_overlap_report(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            exact = self._snapshot(root, 'hiaval', {'source_key': 'hiaval_hma'}, [{
                'source_key': 'hiaval_hma', 'external_id': 'h1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-05T00:00:00Z',
                'event_time_end': '2018-01-06T00:00:00Z', 'timestamp_precision': 'day',
            }])
            bounded = self._snapshot(root, 'everest', {'source_key': 'everest_sentinel1'}, [{
                'source_key': 'everest_sentinel1', 'external_id': 'e1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-01T00:00:00Z', 'event_time_end': '2018-01-13T00:00:00Z',
                'timestamp_precision': 'bounded_12_day_detection_interval',
            }])
            overlap = root / 'overlap.json'
            overlap.write_text(json.dumps({'status': 'computed_pending_review'}), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'overlap report must be reviewed'):
                build_catalog(exact, bounded, overlap)

    def test_catalog_rejects_exact_looking_time_on_day_row(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            exact = self._snapshot(root, 'hiaval', {'source_key': 'hiaval_hma'}, [{
                'source_key': 'hiaval_hma', 'external_id': 'h1', 'region_key': 'himalayas_nepal',
                'event_time': '2018-01-05T00:00:00Z', 'timestamp_precision': 'day',
            }])
            bounded = self._snapshot(root, 'everest', {'source_key': 'everest_sentinel1'}, [{
                'source_key': 'everest_sentinel1', 'external_id': 'e1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-01T00:00:00Z', 'event_time_end': '2018-01-13T00:00:00Z',
                'timestamp_precision': 'bounded_12_day_detection_interval',
            }])
            overlap = root / 'overlap.json'
            overlap.write_text(json.dumps({
                'status': 'reviewed', 'independent_positive_source_count': 2,
                'same_event_must_not_count_as_independent': True,
            }), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'exact-looking event_time'):
                build_catalog(exact, bounded, overlap)

    def test_catalog_rejects_overlap_hash_mismatch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            exact = self._snapshot(root, 'hiaval', {'source_key': 'hiaval_hma'}, [{
                'source_key': 'hiaval_hma', 'external_id': 'h1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-05T00:00:00Z',
                'event_time_end': '2018-01-06T00:00:00Z', 'timestamp_precision': 'day',
            }])
            bounded = self._snapshot(root, 'everest', {'source_key': 'everest_sentinel1'}, [{
                'source_key': 'everest_sentinel1', 'external_id': 'e1', 'region_key': 'himalayas_nepal',
                'event_time_start': '2018-01-01T00:00:00Z', 'event_time_end': '2018-01-13T00:00:00Z',
                'timestamp_precision': 'bounded_12_day_detection_interval',
            }])
            overlap_payload = self._reviewed_overlap(exact, bounded)
            overlap_payload['source_a_sha256'] = 'f' * 64
            overlap = root / 'overlap.json'
            overlap.write_text(json.dumps(overlap_payload), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'source_a_sha256 does not match'):
                build_catalog(exact, bounded, overlap)


if __name__ == '__main__':
    unittest.main()
