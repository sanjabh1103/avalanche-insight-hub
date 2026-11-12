from __future__ import annotations

import json
import unittest

from backend.scripts.build_day_resolution_overlap_report import build_overlap_report


class DayResolutionOverlapReportTests(unittest.TestCase):
    def test_matches_explicit_day_intervals_without_creating_event_time(self) -> None:
        source_a = [
            {
                'external_id': 'hiaval-overlap',
                'event_time_start': '2024-01-10T00:00:00Z',
                'event_time_end': '2024-01-11T00:00:00Z',
                'timestamp_precision': 'day',
                'region_key': 'himalayas_nepal',
                'lat': 28.0,
                'lng': 86.0,
            },
            {
                'external_id': 'hiaval-independent',
                'event_time_start': '2025-02-01T00:00:00Z',
                'event_time_end': '2025-02-02T00:00:00Z',
                'timestamp_precision': 'day',
                'region_key': 'himalayas_nepal',
                'lat': 28.2,
                'lng': 86.2,
            },
        ]
        source_b = [
            {
                'external_id': 'bipad-overlap',
                'event_time_start': '2024-01-10T18:15:00Z',
                'event_time_end': '2024-01-11T18:15:00Z',
                'timestamp_precision': 'day',
                'region_key': 'himalayas_nepal',
                'lat': 28.0001,
                'lng': 86.0001,
            },
            {
                'external_id': 'bipad-independent',
                'event_time_start': '2023-12-02T18:15:00Z',
                'event_time_end': '2023-12-03T18:15:00Z',
                'timestamp_precision': 'day',
                'region_key': 'himalayas_nepal',
                'lat': 28.4,
                'lng': 86.4,
            },
        ]

        report = build_overlap_report(
            json.dumps(source_a, sort_keys=True).encode(),
            json.dumps(source_b, sort_keys=True).encode(),
            source_a,
            source_b,
            source_a_key='hiaval_hma',
            source_b_key='bipad_nepal_avalanche_candidate',
        )

        self.assertEqual(report['status'], 'computed_pending_review')
        self.assertEqual(report['overlap_count'], 1)
        self.assertEqual(report['source_a_non_overlap_count'], 1)
        self.assertEqual(report['source_b_non_overlap_count'], 1)
        self.assertEqual(report['independent_positive_source_count'], 2)
        self.assertTrue(report['matching_policy']['explicit_intervals_only'])
        self.assertNotIn('event_time', report['matches'][0])

    def test_invalid_or_missing_intervals_are_excluded(self) -> None:
        rows = [{
            'external_id': 'missing-interval',
            'timestamp_precision': 'day',
            'region_key': 'himalayas_nepal',
            'lat': 28.0,
            'lng': 86.0,
        }]

        report = build_overlap_report(
            b'a',
            b'b',
            rows,
            rows,
            source_a_key='a',
            source_b_key='b',
        )

        self.assertEqual(report['overlap_count'], 0)
        self.assertEqual(report['source_a_excluded_counts'], {'missing_or_invalid_interval': 1})
        self.assertEqual(report['source_b_excluded_counts'], {'missing_or_invalid_interval': 1})
        self.assertEqual(report['independent_positive_source_count'], 0)

    def test_accepts_everest_bounded_interval_precision_alias(self) -> None:
        source_a = [{
            'external_id': 'hiaval-day',
            'event_time_start': '2024-01-10T00:00:00Z',
            'event_time_end': '2024-01-11T00:00:00Z',
            'timestamp_precision': 'day',
            'region_key': 'himalayas_nepal',
            'lat': 28.0,
            'lng': 86.0,
        }]
        source_b = [{
            'external_id': 'everest-interval',
            'event_time_start': '2024-01-01T00:00:00Z',
            'event_time_end': '2024-01-13T00:00:00Z',
            'timestamp_precision': 'bounded_12_day_detection_interval',
            'region_key': 'himalayas_nepal',
            'lat': 28.0001,
            'lng': 86.0001,
        }]

        report = build_overlap_report(
            json.dumps(source_a, sort_keys=True).encode(),
            json.dumps(source_b, sort_keys=True).encode(),
            source_a,
            source_b,
            source_a_key='hiaval_hma',
            source_b_key='everest_sentinel1',
        )

        self.assertEqual(report['overlap_count'], 1)
        self.assertEqual(report['source_b_record_count'], 1)


if __name__ == '__main__':
    unittest.main()
