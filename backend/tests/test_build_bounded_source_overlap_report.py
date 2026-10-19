from __future__ import annotations

import json
import unittest

from backend.scripts.build_bounded_source_overlap_report import build_overlap_report


class BoundedSourceOverlapReportTests(unittest.TestCase):
    def test_exact_event_matches_only_inside_bounded_interval(self) -> None:
        source_a = [{
            'external_id': 'hiaval-overlap',
            'event_time': '2018-01-05T12:00:00Z',
            'region_key': 'himalayas_nepal',
            'lat': 27.9,
            'lng': 86.7,
        }, {
            'external_id': 'hiaval-independent',
            'event_time': '2025-02-01T12:00:00Z',
            'region_key': 'himalayas_nepal',
            'lat': 28.2,
            'lng': 86.2,
        }]
        source_b = [{
            'external_id': 'everest-interval',
            'event_time_start': '2018-01-01T00:00:00Z',
            'event_time_end': '2018-01-13T00:00:00Z',
            'region_key': 'himalayas_nepal',
            'lat': 27.9001,
            'lng': 86.7001,
        }, {
            'external_id': 'everest-unmatched',
            'event_time_start': '2019-01-01T00:00:00Z',
            'event_time_end': '2019-01-13T00:00:00Z',
            'region_key': 'himalayas_nepal',
            'lat': 27.9,
            'lng': 86.7,
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
        self.assertEqual(report['source_a_non_overlap_count'], 1)
        self.assertEqual(report['source_b_non_overlap_count'], 1)
        self.assertEqual(report['independent_positive_source_count'], 2)
        self.assertTrue(report['matching_policy']['source_b_requires_explicit_start_end_interval'])
        self.assertEqual(report['matches'][0]['source_b_interval_start'], '2018-01-01')

    def test_missing_exact_time_is_excluded_not_fabricated(self) -> None:
        report = build_overlap_report(
            b'{"external_id":"a","region_key":"himalayas_nepal","lat":28,"lng":86}\n',
            b'{"external_id":"b","event_time_start":"2018-01-01T00:00:00Z","event_time_end":"2018-01-13T00:00:00Z","region_key":"himalayas_nepal","lat":28,"lng":86}\n',
            [{'external_id': 'a', 'region_key': 'himalayas_nepal', 'lat': 28, 'lng': 86}],
            [{'external_id': 'b', 'event_time_start': '2018-01-01T00:00:00Z', 'event_time_end': '2018-01-13T00:00:00Z', 'region_key': 'himalayas_nepal', 'lat': 28, 'lng': 86}],
            source_a_key='hiaval_hma',
            source_b_key='everest_sentinel1',
        )

        self.assertEqual(report['source_a_record_count'], 0)
        self.assertEqual(report['source_a_excluded_counts']['missing_exact_event_time'], 1)
        self.assertEqual(report['overlap_count'], 0)

    def test_review_status_requires_explicit_reviewer(self) -> None:
        rows_a = [{
            'external_id': 'a', 'event_time': '2018-01-05T00:00:00Z',
            'region_key': 'himalayas_nepal', 'lat': 28, 'lng': 86,
        }]
        rows_b = [{
            'external_id': 'b', 'event_time_start': '2018-01-01T00:00:00Z',
            'event_time_end': '2018-01-13T00:00:00Z',
            'region_key': 'himalayas_nepal', 'lat': 28, 'lng': 86,
        }]
        with self.assertRaises(ValueError):
            build_overlap_report(
                b'a', b'b', rows_a, rows_b,
                source_a_key='hiaval_hma', source_b_key='everest_sentinel1',
                mark_reviewed=True,
            )
        report = build_overlap_report(
            b'a', b'b', rows_a, rows_b,
            source_a_key='hiaval_hma', source_b_key='everest_sentinel1',
            mark_reviewed=True,
            reviewed_by='local-source-audit',
        )
        self.assertEqual(report['status'], 'reviewed')
        self.assertEqual(report['reviewed_by'], 'local-source-audit')


if __name__ == '__main__':
    unittest.main()
