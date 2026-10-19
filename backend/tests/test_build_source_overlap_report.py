from __future__ import annotations

import json
import unittest

from backend.scripts.build_source_overlap_report import build_overlap_report


class SourceOverlapReportTests(unittest.TestCase):
    def test_matches_once_and_preserves_independent_rows(self) -> None:
        source_a = [
            {
                'external_id': 'hiaval-overlap',
                'event_time': '2024-01-10T12:00:00Z',
                'region_key': 'himalayas_nepal',
                'lat': 28.0,
                'lng': 86.0,
            },
            {
                'external_id': 'hiaval-independent',
                'event_time': '2025-02-01T12:00:00Z',
                'region_key': 'himalayas_nepal',
                'lat': 28.2,
                'lng': 86.2,
            },
        ]
        source_b = [
            {
                'id': 'gee-overlap',
                'timestamp': '2024-01-10T13:00:00Z',
                'region_key': 'himalayas_nepal',
                'lat': 28.0001,
                'lng': 86.0001,
                'source_scene_ids': ['S1_OVERLAP'],
            },
            {
                'id': 'gee-independent',
                'timestamp': '2023-12-02T13:00:00Z',
                'region_key': 'himalayas_nepal',
                'lat': 28.4,
                'lng': 86.4,
                'source_scene_ids': ['S1_INDEPENDENT'],
            },
        ]
        first_payload = json.dumps(source_a, sort_keys=True).encode()
        second_payload = json.dumps(source_b, sort_keys=True).encode()

        report = build_overlap_report(
            first_payload,
            second_payload,
            source_a,
            source_b,
            source_a_key='hiaval_hma',
            source_b_key='gee_sar',
        )

        self.assertEqual(report['status'], 'computed_pending_review')
        self.assertEqual(report['overlap_count'], 1)
        self.assertEqual(report['source_a_non_overlap_count'], 1)
        self.assertEqual(report['source_b_non_overlap_count'], 1)
        self.assertEqual(report['independent_positive_source_count'], 2)
        self.assertTrue(report['same_event_must_not_count_as_independent'])
        self.assertEqual(report['matches'][0]['source_b_scene_ids'], ['S1_OVERLAP'])

    def test_review_status_requires_explicit_reviewer(self) -> None:
        rows = [{
            'id': 'event-1',
            'event_time': '2024-01-10T12:00:00Z',
            'region_key': 'himalayas_nepal',
            'lat': 28.0,
            'lng': 86.0,
        }]
        scene_rows = [{
            'id': 'scene-event-1',
            'timestamp': '2024-01-10T12:00:00Z',
            'region_key': 'himalayas_nepal',
            'lat': 28.4,
            'lng': 86.4,
            'source_scene_ids': ['S1'],
        }]
        with self.assertRaises(ValueError):
            build_overlap_report(
                b'a', b'b', rows, scene_rows,
                source_a_key='hiaval_hma',
                source_b_key='gee_sar',
                mark_reviewed=True,
            )

        report = build_overlap_report(
            b'a', b'b', rows, scene_rows,
            source_a_key='hiaval_hma',
            source_b_key='gee_sar',
            mark_reviewed=True,
            reviewed_by='scientist-review-1',
        )
        self.assertEqual(report['status'], 'reviewed')
        self.assertEqual(report['reviewed_by'], 'scientist-review-1')


if __name__ == '__main__':
    unittest.main()
