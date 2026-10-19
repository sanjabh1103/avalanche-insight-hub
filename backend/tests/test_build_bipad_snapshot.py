from __future__ import annotations

import json
import unittest

from backend.scripts.build_bipad_snapshot import build_snapshot


class BipadSnapshotTests(unittest.TestCase):
    def _payload(self) -> bytes:
        return json.dumps({
            'count': 5,
            'results': [
                {
                    'id': 101,
                    'hazard': 3,
                    'incidentOn': '2024-04-01T00:00:00+05:45',
                    'point': {'type': 'Point', 'coordinates': [86.7, 27.9]},
                    'verified': True,
                    'approved': True,
                    'title': 'Day-resolution avalanche',
                    'source': 'nepal_police',
                    'dataSource': 'drr_api',
                },
                {
                    'id': 102,
                    'hazard': 3,
                    'incidentOn': '2025-01-02T06:30:00+05:45',
                    'point': {'type': 'Point', 'coordinates': [86.8, 27.8]},
                    'verified': True,
                    'approved': True,
                    'title': 'Clock-time candidate',
                    'incidentTimePrecision': 'timestamp',
                },
                {
                    'id': 103,
                    'hazard': 2,
                    'incidentOn': '2024-04-02T00:00:00+05:45',
                    'point': {'type': 'Point', 'coordinates': [86.7, 27.9]},
                    'verified': True,
                    'approved': True,
                },
                {
                    'id': 104,
                    'hazard': 3,
                    'incidentOn': '2024-04-03T00:00:00+05:45',
                    'point': {'type': 'Point', 'coordinates': [81.1, 29.7]},
                    'verified': True,
                    'approved': True,
                },
                {
                    'id': 105,
                    'hazard': 3,
                    'incidentOn': '2024-04-04T00:00:00+05:45',
                    'point': {'type': 'Point', 'coordinates': [86.7, 27.9]},
                    'verified': False,
                    'approved': True,
                },
            ],
        }, sort_keys=True).encode('utf-8')

    def test_day_rows_preserve_interval_without_fabricated_event_time(self) -> None:
        rows, manifest = build_snapshot(
            self._payload(),
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )

        self.assertEqual(len(rows), 2)
        day_row = rows[0]
        self.assertNotIn('event_time', day_row)
        self.assertEqual(day_row['timestamp_precision'], 'day')
        self.assertEqual(day_row['event_time_start'], '2024-03-31T18:15:00Z')
        self.assertEqual(day_row['event_time_end'], '2024-04-01T18:15:00Z')
        self.assertEqual(day_row['origin_source_family'], 'bipad_drr_api')
        self.assertEqual(day_row['event_group_id'], 'bipad:101')
        self.assertFalse(day_row['training_eligible'])
        self.assertEqual(manifest['exact_timestamp_record_count'], 1)
        self.assertEqual(manifest['positive_season_ids'], ['2023-2024', '2024-2025'])
        self.assertEqual(manifest['review_status'], 'pending_rights_and_overlap_review')
        self.assertFalse(manifest['training_eligible'])

    def test_snapshot_is_stable_and_exclusions_are_explicit(self) -> None:
        payload = self._payload()
        first_rows, first_manifest = build_snapshot(
            payload,
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )
        second_rows, second_manifest = build_snapshot(
            payload,
            target_regions={'himalayas_nepal': (27.0, 85.0, 29.0, 87.5)},
        )

        self.assertEqual(first_rows, second_rows)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest['excluded_record_counts']['unsupported_hazard'], 1)
        self.assertEqual(first_manifest['excluded_record_counts']['outside_target_regions'], 1)
        self.assertEqual(first_manifest['excluded_record_counts']['unverified_or_unapproved'], 1)
        self.assertEqual(first_manifest['required_independent_positive_sources'], [
            'bipad_nepal_avalanche_candidate',
            'hiaval_hma',
        ])


if __name__ == '__main__':
    unittest.main()
