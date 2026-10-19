"""Tests for AWS station adapter — numeric field rejection."""
from __future__ import annotations

import json
import unittest

from backend.common.aws_station_adapter import (
    _parse_csv_feed,
    _parse_json_feed,
    validate_aws_feed_schema,
)


class TestParseCsvFeed(unittest.TestCase):
    def test_valid_row_with_numeric_fields(self) -> None:
        csv_text = (
            'station_id,observed_at,air_temp_c,snow_depth_cm,wind_speed_ms,latitude,longitude,elevation_m\n'
            'ST001,2026-01-15T08:00:00Z,-5.0,120.0,15.0,34.5,77.0,3500.0\n'
        )
        rows = _parse_csv_feed(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['station_id'], 'ST001')
        self.assertEqual(rows[0]['air_temp_c'], -5.0)

    def test_row_with_missing_numeric_field_skipped(self) -> None:
        csv_text = (
            'station_id,observed_at,air_temp_c,snow_depth_cm\n'
            'ST001,2026-01-15T08:00:00Z,,120.0\n'
        )
        rows = _parse_csv_feed(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertNotIn('air_temp_c', rows[0])
        self.assertEqual(rows[0]['snow_depth_cm'], 120.0)

    def test_row_with_non_numeric_value_rejected(self) -> None:
        csv_text = (
            'station_id,observed_at,air_temp_c,snow_depth_cm\n'
            'ST001,2026-01-15T08:00:00Z,invalid,120.0\n'
        )
        rows = _parse_csv_feed(csv_text)
        self.assertEqual(len(rows), 0)

    def test_row_with_missing_station_id_rejected(self) -> None:
        csv_text = (
            'station_id,observed_at,air_temp_c\n'
            ',2026-01-15T08:00:00Z,-5.0\n'
        )
        rows = _parse_csv_feed(csv_text)
        self.assertEqual(len(rows), 0)


class TestParseJsonFeed(unittest.TestCase):
    def test_valid_json_array(self) -> None:
        data = json.dumps([
            {
                'station_id': 'ST001',
                'observed_at': '2026-01-15T08:00:00Z',
                'air_temp_c': -5.0,
                'snow_depth_cm': 120.0,
            },
        ])
        rows = _parse_json_feed(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['station_id'], 'ST001')

    def test_json_with_none_numeric_passes_through(self) -> None:
        data = json.dumps([
            {
                'station_id': 'ST001',
                'observed_at': '2026-01-15T08:00:00Z',
                'air_temp_c': None,
            },
        ])
        rows = _parse_json_feed(data)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['air_temp_c'])


class TestValidateAwsFeedSchema(unittest.TestCase):
    def test_valid_schema(self) -> None:
        records = [{
            'station_id': 'ST001',
            'observed_at': '2026-01-15T08:00:00Z',
            'air_temp_c': -5.0,
        }]
        errors = validate_aws_feed_schema(records)
        self.assertEqual(len(errors), 0)

    def test_missing_station_id(self) -> None:
        records = [{'observed_at': '2026-01-15', 'air_temp_c': -5.0}]
        errors = validate_aws_feed_schema(records)
        self.assertGreater(len(errors), 0)

    def test_missing_observed_at(self) -> None:
        records = [{'station_id': 'ST001', 'air_temp_c': -5.0}]
        errors = validate_aws_feed_schema(records)
        self.assertGreater(len(errors), 0)


if __name__ == '__main__':
    unittest.main()
