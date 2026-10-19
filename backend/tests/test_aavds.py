"""Tests for AAVDS adapter."""
from __future__ import annotations

import unittest
import json
import os
import tempfile
from datetime import datetime, timezone

from backend.common.aavds_adapter import (
    AAVDSEvent,
    AAVDSAdapter,
)


class AAVDSEventTests(unittest.TestCase):
    """Tests for AAVDSEvent dataclass."""

    def test_create_event(self) -> None:
        event = AAVDSEvent(
            event_id='test_001',
            timestamp=datetime.now(timezone.utc),
            lat=32.0,
            lng=78.0,
            detection_confidence=0.85,
            signal_type='auto_luminescent',
        )
        self.assertEqual(event.event_id, 'test_001')
        self.assertEqual(event.signal_type, 'auto_luminescent')
        self.assertIsNone(event.victim_id)


class AAVDSAdapterTests(unittest.TestCase):
    """Tests for AAVDS adapter ingestion."""

    def setUp(self) -> None:
        self.adapter = AAVDSAdapter(enabled=True)

    def test_ingest_dict_valid(self) -> None:
        event = self.adapter.ingest_dict({
            'event_id': 'aavds_001',
            'timestamp': '2026-06-25T10:00:00Z',
            'lat': 32.5,
            'lng': 78.0,
            'detection_confidence': 0.9,
            'signal_type': 'auto_luminescent',
            'victim_id': 'V001',
            'burial_depth_m': 1.5,
        })
        self.assertEqual(event.event_id, 'aavds_001')
        self.assertEqual(event.victim_id, 'V001')
        self.assertEqual(event.burial_depth_m, 1.5)
        self.assertEqual(len(self.adapter.events), 1)

    def test_ingest_dict_missing_required(self) -> None:
        with self.assertRaises(KeyError):
            self.adapter.ingest_dict({'lat': 32.0, 'lng': 78.0})

    def test_ingest_dict_invalid_lat(self) -> None:
        with self.assertRaises(ValueError):
            self.adapter.ingest_dict({
                'event_id': 'test',
                'lat': 200.0,
                'lng': 78.0,
                'detection_confidence': 0.5,
            })

    def test_ingest_dict_invalid_confidence(self) -> None:
        with self.assertRaises(ValueError):
            self.adapter.ingest_dict({
                'event_id': 'test',
                'lat': 32.0,
                'lng': 78.0,
                'detection_confidence': 1.5,
            })

    def test_ingest_file(self) -> None:
        data = [
            {
                'event_id': 'f001',
                'timestamp': '2026-06-25T08:00:00Z',
                'lat': 32.0,
                'lng': 78.0,
                'detection_confidence': 0.8,
                'signal_type': 'auto_luminescent',
            },
            {
                'event_id': 'f002',
                'timestamp': '2026-06-25T09:00:00Z',
                'lat': 32.1,
                'lng': 78.1,
                'detection_confidence': 0.6,
                'signal_type': 'thermal',
            },
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()
            try:
                events = self.adapter.ingest_file(f.name)
                self.assertEqual(len(events), 2)
                self.assertEqual(events[0].event_id, 'f001')
                self.assertEqual(events[1].signal_type, 'thermal')
            finally:
                os.unlink(f.name)

    def test_ingest_file_with_invalid_entries(self) -> None:
        data = [
            {'event_id': 'ok', 'lat': 32.0, 'lng': 78.0, 'detection_confidence': 0.5},
            {'event_id': 'bad', 'lat': 999.0, 'lng': 78.0, 'detection_confidence': 0.5},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            f.flush()
            try:
                events = self.adapter.ingest_file(f.name)
                self.assertEqual(len(events), 1)  # Only valid one
            finally:
                os.unlink(f.name)

    def test_get_events_in_bounds(self) -> None:
        self.adapter.ingest_dict({
            'event_id': 'in',
            'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.5,
        })
        self.adapter.ingest_dict({
            'event_id': 'out',
            'lat': 40.0, 'lng': 90.0,
            'detection_confidence': 0.5,
        })
        in_bounds = self.adapter.get_events_in_bounds(
            min_lat=30, max_lat=35, min_lng=75, max_lng=80,
        )
        self.assertEqual(len(in_bounds), 1)
        self.assertEqual(in_bounds[0].event_id, 'in')

    def test_get_high_confidence_events(self) -> None:
        self.adapter.ingest_dict({
            'event_id': 'high', 'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.9,
        })
        self.adapter.ingest_dict({
            'event_id': 'low', 'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.3,
        })
        high = self.adapter.get_high_confidence_events(0.7)
        self.assertEqual(len(high), 1)
        self.assertEqual(high[0].event_id, 'high')

    def test_to_geojson(self) -> None:
        self.adapter.ingest_dict({
            'event_id': 'g001', 'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.85,
        })
        geojson = self.adapter.to_geojson()
        self.assertEqual(geojson['type'], 'FeatureCollection')
        self.assertEqual(len(geojson['features']), 1)
        self.assertEqual(geojson['features'][0]['geometry']['type'], 'Point')

    def test_clear(self) -> None:
        self.adapter.ingest_dict({
            'event_id': 'c001', 'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.5,
        })
        self.assertEqual(len(self.adapter.events), 1)
        self.adapter.clear()
        self.assertEqual(len(self.adapter.events), 0)

    def test_get_status(self) -> None:
        status = self.adapter.get_status()
        self.assertIn('enabled', status)
        self.assertIn('event_count', status)

    def test_timestamp_from_epoch(self) -> None:
        event = self.adapter.ingest_dict({
            'event_id': 'ts_test',
            'timestamp': 1719331200,  # epoch
            'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.5,
        })
        self.assertIsNotNone(event.timestamp.tzinfo)

    def test_default_timestamp(self) -> None:
        event = self.adapter.ingest_dict({
            'event_id': 'ts_default',
            'lat': 32.0, 'lng': 78.0,
            'detection_confidence': 0.5,
        })
        self.assertIsNotNone(event.timestamp)


if __name__ == '__main__':
    unittest.main()
