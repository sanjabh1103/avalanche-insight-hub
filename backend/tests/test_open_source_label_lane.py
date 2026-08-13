from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.common.open_source_label_lane import (
    build_open_source_label_manifest,
    load_open_source_label_events,
)
from backend.common.training_dataset import fetch_training_events


class OpenSourceLabelLaneTests(unittest.TestCase):
    def _snapshot(self, root: Path) -> Path:
        path = root / 'french_epa.jsonl'
        path.write_text(
            json.dumps({
                'source_key': 'french_epa_historical',
                'external_id': 'epa-1946-0001',
                'region_key': 'french_alps',
                'event_time': '2020-01-15T12:00:00Z',
                'timestamp_precision': 'exact',
                'lat': 45.2,
                'lng': 6.7,
                'label_confidence': 0.8,
                'geometry_ref': 'epa/2020/0001.geojson',
            }) + '\n',
            encoding='utf-8',
        )
        return path

    def test_staging_is_default_and_license_gate_is_explicit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = self._snapshot(Path(tmpdir))
            staged = load_open_source_label_events(path)
            reviewed = load_open_source_label_events(
                path,
                requested_role='shadow_training',
                license_review_id='license-review-french-epa',
            )

        self.assertEqual(staged[0]['source'], 'french_epa_historical')
        self.assertFalse(staged[0]['training_eligible'])
        self.assertTrue(reviewed[0]['training_eligible'])
        self.assertEqual(reviewed[0]['label_source'], 'french_epa_historical')
        self.assertEqual(reviewed[0]['source_event_id'], 'epa-1946-0001')
        self.assertEqual(reviewed[0]['location'], 'SRID=4326;POINT(6.7 45.2)')
        self.assertEqual(reviewed[0]['review_basis'], 'open_source_occurrence')

    def test_manifest_hashes_the_exact_source_snapshot(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = self._snapshot(Path(tmpdir))
            manifest = build_open_source_label_manifest(
                path,
                requested_role='shadow_training',
                license_review_id='license-review-french-epa',
            )

        self.assertEqual(manifest['version'], 'open_source_label_manifest_v1')
        self.assertEqual(manifest['record_count'], 1)
        self.assertEqual(manifest['training_eligible_count'], 1)
        self.assertEqual(manifest['source_key'], 'french_epa_historical')
        self.assertRegex(manifest['snapshot_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(manifest['season_ids'], ['2019-2020'])
        self.assertFalse(manifest['coverage_gate']['passed'])

    def test_manifest_reports_multi_season_coverage_and_later_holdout(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'french_epa_multi_season.jsonl'
            records = [
                {
                    'source_key': 'french_epa_historical',
                    'external_id': f'epa-{year}-0001',
                    'region_key': 'french_alps',
                    'event_time': f'{year}-01-15T12:00:00Z',
                    'timestamp_precision': 'exact',
                    'lat': 45.2,
                    'lng': 6.7,
                    'label_confidence': 0.8,
                }
                for year in (2020, 2021, 2022)
            ]
            path.write_text('\n'.join(json.dumps(record) for record in records) + '\n', encoding='utf-8')
            manifest = build_open_source_label_manifest(
                path,
                requested_role='shadow_training',
                license_review_id='license-review-french-epa',
            )

        self.assertEqual(manifest['season_ids'], ['2019-2020', '2020-2021', '2021-2022'])
        self.assertEqual(manifest['coverage_gate']['observed_season_count'], 3)
        self.assertTrue(manifest['coverage_gate']['passed'])
        self.assertEqual(manifest['coverage_gate']['later_season_holdout'], '2021-2022')
        self.assertEqual(manifest['source_season_counts']['french_epa_historical']['2020-2021'], 1)

    def test_himalayan_season_uses_november_boundary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hiaval_boundary.jsonl'
            records = [
                {
                    'source_key': 'hiaval_hma',
                    'external_id': 'hiaval-october',
                    'region_key': 'himalayas_nepal',
                    'event_time': '2025-10-31T12:00:00Z',
                    'timestamp_precision': 'exact',
                    'lat': 28.0,
                    'lng': 86.0,
                    'label_confidence': 0.7,
                },
                {
                    'source_key': 'hiaval_hma',
                    'external_id': 'hiaval-november',
                    'region_key': 'himalayas_nepal',
                    'event_time': '2025-11-01T12:00:00Z',
                    'timestamp_precision': 'exact',
                    'lat': 28.0,
                    'lng': 86.0,
                    'label_confidence': 0.7,
                },
            ]
            path.write_text('\n'.join(json.dumps(record) for record in records) + '\n', encoding='utf-8')
            manifest = build_open_source_label_manifest(
                path,
                requested_role='shadow_training',
                license_review_id='license-review-hiaval',
            )

        self.assertEqual(manifest['season_ids'], ['2024-2025', '2025-2026'])
        self.assertEqual(manifest['season_start_months']['himalayas_nepal'], 11)

    def test_training_role_requires_coordinates_and_confidence(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'invalid.json'
            path.write_text(json.dumps({
                'source_key': 'french_epa_historical',
                'external_id': 'epa-invalid',
                'region_key': 'french_alps',
                'event_time': '2020-01-15T12:00:00Z',
            }), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'lat/lng'):
                load_open_source_label_events(
                    path,
                    requested_role='shadow_training',
                    license_review_id='license-review-french-epa',
                )

    def test_day_precision_preserves_interval_and_provenance_fields(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hiaval_day.jsonl'
            path.write_text(json.dumps({
                'source_key': 'hiaval_hma',
                'external_id': 'hiaval-day-1',
                'event_group_id': 'hiaval:day-1',
                'origin_source_family': 'hiaval_literature_database',
                'region_key': 'himalayas_nepal',
                'event_time': '2025-11-01T00:00:00Z',
                'event_time_start': '2025-11-01T00:00:00Z',
                'event_time_end': '2025-11-02T00:00:00Z',
                'timestamp_precision': 'day',
                'lat': 28.0,
                'lng': 86.0,
                'label_confidence': 0.7,
            }) + '\n', encoding='utf-8')

            events = load_open_source_label_events(path)

        self.assertEqual(events[0]['timestamp'], '2025-11-01T00:00:00Z')
        self.assertEqual(events[0]['event_time_start'], '2025-11-01T00:00:00Z')
        self.assertEqual(events[0]['event_time_end'], '2025-11-02T00:00:00Z')
        self.assertEqual(events[0]['timestamp_precision'], 'day')
        self.assertEqual(events[0]['event_group_id'], 'hiaval:day-1')
        self.assertEqual(events[0]['origin_source_family'], 'hiaval_literature_database')

    def test_day_precision_cannot_enter_timestamp_training_lane(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hiaval_day_training.jsonl'
            path.write_text(json.dumps({
                'source_key': 'hiaval_hma',
                'external_id': 'hiaval-day-training-1',
                'region_key': 'himalayas_nepal',
                'event_time': '2025-11-01T00:00:00Z',
                'event_time_start': '2025-11-01T00:00:00Z',
                'event_time_end': '2025-11-02T00:00:00Z',
                'timestamp_precision': 'day',
                'lat': 28.0,
                'lng': 86.0,
                'label_confidence': 0.7,
                'license_review_id': 'license-review-hiaval',
            }) + '\n', encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'interval-aware training'):
                load_open_source_label_events(
                    path,
                    requested_role='shadow_training',
                    license_review_id='license-review-hiaval',
                )

    @patch('backend.common.training_dataset.has_supabase_credentials', return_value=False)
    def test_training_event_loader_can_use_explicit_reviewed_snapshot_without_station_data(
        self,
        _has_credentials,
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            path = self._snapshot(Path(tmpdir))
            with patch.dict(os.environ, {
                'OPEN_SOURCE_LABEL_SNAPSHOT': str(path),
                'OPEN_SOURCE_LABEL_ROLE': 'shadow_training',
                'OPEN_SOURCE_LABEL_LICENSE_REVIEW_ID': 'license-review-french-epa',
            }, clear=False):
                events = fetch_training_events(region_keys=['french_alps'])

        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['training_eligible'])
        self.assertEqual(events[0]['source'], 'french_epa_historical')


if __name__ == '__main__':
    unittest.main()
