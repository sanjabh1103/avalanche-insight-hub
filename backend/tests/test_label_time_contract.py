from __future__ import annotations

import unittest

from backend.common.label_time_contract import (
    has_approved_occurrence_time_review,
    LABEL_TIME_CONTRACT_EXACT_V1,
    LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
    inspect_label_time_row,
    validate_label_time_rows,
)


class LabelTimeContractTests(unittest.TestCase):
    def test_exact_occurrence_time_review_requires_explicit_semantics_and_review_id(self) -> None:
        reviewed = {
            'event_time': '2025-02-01T18:00:00Z',
            'timestamp_precision': 'timestamp',
            'event_time_semantics': 'independent_observed_occurrence_time',
            'source_time_review_status': 'approved_occurrence_time',
            'source_time_review_id': 'review-1',
        }

        self.assertTrue(has_approved_occurrence_time_review(reviewed))
        self.assertFalse(has_approved_occurrence_time_review({**reviewed, 'source_time_review_id': ''}))
        self.assertFalse(has_approved_occurrence_time_review({**reviewed, 'event_time_semantics': 'sentinel_observation_time'}))

    def test_exact_occurrence_time_review_can_be_declared_by_source_manifest(self) -> None:
        row = {
            'event_time': '2025-02-01T18:00:00Z',
            'timestamp_precision': 'timestamp',
        }
        source_manifest = {
            'event_time_semantics': 'source_reported_occurrence_time',
            'source_time_review_status': 'approved_occurrence_time',
            'source_time_review_id': 'review-2',
        }

        self.assertTrue(has_approved_occurrence_time_review(row, source_manifest=source_manifest))

    def test_day_row_requires_only_an_explicit_day_interval(self) -> None:
        inspection = inspect_label_time_row({
            'timestamp_precision': 'day',
            'event_time_start': '2024-01-10T00:00:00Z',
            'event_time_end': '2024-01-11T00:00:00Z',
            'feature_cutoff_at': '2024-01-09T00:00:00Z',
        })

        self.assertTrue(inspection['valid'])
        self.assertEqual(inspection['precision'], 'day')
        self.assertEqual(inspection['interval_start'], '2024-01-10T00:00:00Z')
        self.assertEqual(inspection['interval_end'], '2024-01-11T00:00:00Z')

    def test_interval_row_is_valid_without_fabricating_event_time(self) -> None:
        report = validate_label_time_rows([
            {
                'precision': 'interval',
                'interval_start': '2025-02-01T18:00:00Z',
                'interval_end': '2025-02-03T18:00:00Z',
                'feature_cutoff_at': '2025-02-01T00:00:00Z',
            },
        ], contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1)

        self.assertTrue(report['passed'])
        self.assertEqual(report['precision_counts'], {'interval': 1})
        self.assertEqual(report['invalid_row_count'], 0)

    def test_exact_row_requires_a_timezone_aware_event_time(self) -> None:
        inspection = inspect_label_time_row({
            'precision': 'exact',
            'event_time': '2025-02-01T18:00:00Z',
            'feature_cutoff_at': '2025-02-01T17:00:00Z',
        })

        self.assertTrue(inspection['valid'])
        self.assertEqual(inspection['precision'], 'exact')
        self.assertEqual(inspection['interval_start'], '2025-02-01T18:00:00Z')

    def test_censored_row_rejects_exact_time_placeholder(self) -> None:
        inspection = inspect_label_time_row({
            'precision': 'day',
            'interval_start': '2024-01-10T00:00:00Z',
            'interval_end': '2024-01-11T00:00:00Z',
            'event_time': '2024-01-10T00:00:00Z',
            'feature_cutoff_at': '2024-01-09T00:00:00Z',
        })

        self.assertFalse(inspection['valid'])
        self.assertIn('censored_row_contains_exact_time', {
            issue['code'] for issue in inspection['errors']
        })

    def test_cutoff_after_interval_start_is_leakage(self) -> None:
        inspection = inspect_label_time_row({
            'precision': 'interval',
            'interval_start': '2024-01-10T00:00:00Z',
            'interval_end': '2024-01-12T00:00:00Z',
            'feature_cutoff_at': '2024-01-10T00:00:01Z',
        })

        self.assertFalse(inspection['valid'])
        self.assertIn('feature_cutoff_after_occurrence_start', {
            issue['code'] for issue in inspection['errors']
        })

    def test_missing_or_naive_bounds_fail_closed(self) -> None:
        report = validate_label_time_rows([
            {
                'precision': 'day',
                'interval_start': '2024-01-10T00:00:00',
                'interval_end': '2024-01-11T00:00:00Z',
            },
        ], contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1)

        self.assertFalse(report['passed'])
        self.assertIn('invalid_or_naive_interval_start', report['error_counts'])
        self.assertIn('missing_feature_cutoff', report['error_counts'])

    def test_missing_feature_cutoff_fails_under_exact_contract_too(self) -> None:
        report = validate_label_time_rows([
            {
                'precision': 'exact',
                'event_time': '2024-01-10T12:00:00Z',
            },
        ], contract=LABEL_TIME_CONTRACT_EXACT_V1)

        self.assertFalse(report['passed'])
        self.assertIn('missing_feature_cutoff', report['error_counts'])

    def test_exact_contract_does_not_allow_interval_rows(self) -> None:
        row = {
            'precision': 'day',
            'interval_start': '2024-01-10T00:00:00Z',
            'interval_end': '2024-01-11T00:00:00Z',
            'feature_cutoff_at': '2024-01-09T00:00:00Z',
        }
        report = validate_label_time_rows([row], contract=LABEL_TIME_CONTRACT_EXACT_V1)

        self.assertFalse(report['passed'])
        self.assertIn('interval_precision_not_allowed_by_exact_contract', report['error_counts'])
        self.assertNotIn('event_time', row)


if __name__ == '__main__':
    unittest.main()
