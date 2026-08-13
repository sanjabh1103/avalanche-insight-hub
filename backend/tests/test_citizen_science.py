"""Tests for Citizen-Science module."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.citizen_science import (
    CitizenReport,
    CitizenScienceManager,
    RateLimiter,
    CITIZEN_LABEL_CONFIDENCE,
    CITIZEN_LABEL_SOURCE,
    create_report,
    validate_report,
    report_to_weak_label,
    report_to_supabase_row,
    reports_to_geojson,
)


class ValidateReportTests(unittest.TestCase):
    """Tests for report validation."""

    def test_valid_report(self) -> None:
        is_valid, msg = validate_report(lat=32.0, lng=78.0, description='Saw a large avalanche near the pass')
        self.assertTrue(is_valid)
        self.assertEqual(msg, '')

    def test_invalid_lat(self) -> None:
        is_valid, msg = validate_report(lat=200.0, lng=78.0, description='Valid description here')
        self.assertFalse(is_valid)
        self.assertIn('Latitude', msg)

    def test_invalid_lng(self) -> None:
        is_valid, msg = validate_report(lat=32.0, lng=400.0, description='Valid description here')
        self.assertFalse(is_valid)
        self.assertIn('Longitude', msg)

    def test_short_description(self) -> None:
        is_valid, msg = validate_report(lat=32.0, lng=78.0, description='short')
        self.assertFalse(is_valid)
        self.assertIn('10 characters', msg)

    def test_empty_description(self) -> None:
        is_valid, msg = validate_report(lat=32.0, lng=78.0, description='')
        self.assertFalse(is_valid)

    def test_long_description(self) -> None:
        is_valid, msg = validate_report(lat=32.0, lng=78.0, description='x' * 2001)
        self.assertFalse(is_valid)
        self.assertIn('2000', msg)


class CreateReportTests(unittest.TestCase):
    """Tests for report creation."""

    def test_create_valid_report(self) -> None:
        report = create_report(
            lat=32.0,
            lng=78.0,
            description='Large avalanche observed on north face',
        )
        self.assertIsNotNone(report.report_id)
        self.assertEqual(report.lat, 32.0)
        self.assertEqual(report.status, 'pending')
        self.assertEqual(report.confidence, CITIZEN_LABEL_CONFIDENCE)

    def test_create_report_with_optional_fields(self) -> None:
        report = create_report(
            lat=32.0,
            lng=78.0,
            description='Medium avalanche with powder cloud',
            photo_url='https://example.com/photo.jpg',
            estimated_size='medium',
            weather_conditions='Heavy snowfall',
        )
        self.assertEqual(report.estimated_size, 'medium')
        self.assertEqual(report.weather_conditions, 'Heavy snowfall')
        self.assertIsNotNone(report.photo_url)

    def test_create_anonymous_report(self) -> None:
        report = create_report(
            lat=32.0,
            lng=78.0,
            description='Anonymous avalanche sighting report',
        )
        self.assertIsNone(report.reporter_id)

    def test_create_invalid_report_raises(self) -> None:
        with self.assertRaises(ValueError):
            create_report(lat=999.0, lng=78.0, description='Valid description here')


class RateLimiterTests(unittest.TestCase):
    """Tests for rate limiting."""

    def test_allows_under_limit(self) -> None:
        limiter = RateLimiter(max_per_hour=5)
        for _ in range(5):
            self.assertTrue(limiter.check('192.168.1.1'))

    def test_blocks_over_limit(self) -> None:
        limiter = RateLimiter(max_per_hour=3)
        for _ in range(3):
            self.assertTrue(limiter.check('10.0.0.1'))
        self.assertFalse(limiter.check('10.0.0.1'))

    def test_different_ips_independent(self) -> None:
        limiter = RateLimiter(max_per_hour=2)
        self.assertTrue(limiter.check('ip1'))
        self.assertTrue(limiter.check('ip2'))
        self.assertTrue(limiter.check('ip1'))
        self.assertFalse(limiter.check('ip1'))
        self.assertTrue(limiter.check('ip2'))

    def test_remaining(self) -> None:
        limiter = RateLimiter(max_per_hour=5)
        limiter.check('ip_test')
        limiter.check('ip_test')
        self.assertEqual(limiter.remaining('ip_test'), 3)


class ReportConversionTests(unittest.TestCase):
    """Tests for report conversion functions."""

    def test_report_to_weak_label(self) -> None:
        report = create_report(
            lat=32.0, lng=78.0,
            description='Avalanche observation for labeling',
        )
        label = report_to_weak_label(report)
        self.assertEqual(label['label_source'], CITIZEN_LABEL_SOURCE)
        self.assertEqual(label['confidence'], CITIZEN_LABEL_CONFIDENCE)
        self.assertEqual(label['lat'], 32.0)
        self.assertEqual(label['lng'], 78.0)
        self.assertEqual(label['report_id'], report.report_id)

    def test_report_to_supabase_row(self) -> None:
        report = create_report(
            lat=32.0, lng=78.0,
            description='Avalanche observation for Supabase',
            photo_url='https://example.com/p.jpg',
        )
        row = report_to_supabase_row(report)
        self.assertEqual(row['report_id'], report.report_id)
        self.assertEqual(row['lat'], 32.0)
        self.assertEqual(row['status'], 'pending')
        self.assertEqual(row['photo_url'], 'https://example.com/p.jpg')
        self.assertEqual(row['confidence'], CITIZEN_LABEL_CONFIDENCE)

    def test_reports_to_geojson(self) -> None:
        reports = [
            create_report(lat=32.0, lng=78.0, description='First avalanche report here'),
            create_report(lat=33.0, lng=79.0, description='Second avalanche report here'),
        ]
        geojson = reports_to_geojson(reports)
        self.assertEqual(geojson['type'], 'FeatureCollection')
        self.assertEqual(len(geojson['features']), 2)
        self.assertEqual(geojson['features'][0]['geometry']['type'], 'Point')


class CitizenScienceManagerTests(unittest.TestCase):
    """Tests for the manager."""

    def test_submit_report_success(self) -> None:
        manager = CitizenScienceManager(rate_limit_per_hour=5)
        report, msg = manager.submit_report(
            ip='192.168.1.1',
            lat=32.0,
            lng=78.0,
            description='Avalanche near the summit ridge',
        )
        self.assertIsNotNone(report)
        self.assertIn('successfully', msg)
        self.assertEqual(len(manager.reports), 1)

    def test_submit_report_rate_limited(self) -> None:
        manager = CitizenScienceManager(rate_limit_per_hour=2)
        for _ in range(2):
            r, _ = manager.submit_report(
                ip='10.0.0.1', lat=32.0, lng=78.0,
                description='Avalanche observation number one',
            )
            self.assertIsNotNone(r)
        report, msg = manager.submit_report(
            ip='10.0.0.1', lat=32.0, lng=78.0,
            description='Avalanche observation number three',
        )
        self.assertIsNone(report)
        self.assertIn('Rate limit', msg)

    def test_submit_report_invalid(self) -> None:
        manager = CitizenScienceManager()
        report, msg = manager.submit_report(
            ip='192.168.1.1',
            lat=999.0,
            lng=78.0,
            description='Invalid location report',
        )
        self.assertIsNone(report)
        self.assertIn('Latitude', msg)

    def test_get_weak_labels(self) -> None:
        manager = CitizenScienceManager()
        manager.submit_report(
            ip='ip1', lat=32.0, lng=78.0,
            description='First report for weak labels',
        )
        manager.submit_report(
            ip='ip1', lat=33.0, lng=79.0,
            description='Second report for weak labels',
        )
        labels = manager.get_weak_labels()
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0]['label_source'], CITIZEN_LABEL_SOURCE)

    def test_get_status(self) -> None:
        manager = CitizenScienceManager()
        manager.submit_report(
            ip='ip1', lat=32.0, lng=78.0,
            description='Status check report here',
        )
        status = manager.get_status()
        self.assertEqual(status['total_reports'], 1)
        self.assertEqual(status['pending_reports'], 1)


if __name__ == '__main__':
    unittest.main()
