"""Tests for station_sensor_adapters.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.station_sensor_adapters import (
    InfrasoundArrayAdapter,
    XBandRadarAdapter,
    STATION_SENSOR_ENABLED,
)


class TestInfrasoundArrayAdapter(unittest.TestCase):
    def setUp(self):
        import backend.common.station_sensor_adapters as ss
        self._original = ss.STATION_SENSOR_ENABLED
        ss.STATION_SENSOR_ENABLED = True
        self.adapter = InfrasoundArrayAdapter()

    def tearDown(self):
        import backend.common.station_sensor_adapters as ss
        ss.STATION_SENSOR_ENABLED = self._original

    def test_sensor_name(self):
        self.assertEqual(self.adapter.sensor_name, 'infrasound_array')

    def test_available(self):
        self.assertTrue(self.adapter.available())

    def test_not_available_when_disabled(self):
        import backend.common.station_sensor_adapters as ss
        ss.STATION_SENSOR_ENABLED = False
        self.assertFalse(self.adapter.available())

    def test_query_returns_empty(self):
        results = self.adapter.query(
            region_key='great_himalaya',
            bbox=(30.0, 78.0, 31.0, 79.0),
            date_range=(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)),
        )
        self.assertEqual(results, [])

    def test_retrieve_returns_none(self):
        self.assertIsNone(self.adapter.retrieve('test_001'))

    def test_normalize(self):
        from backend.common.remote_sensing_adapter import SceneData
        scene = SceneData(scene_id='test_001', sensor='infrasound_array')
        result = self.adapter.normalize(scene)
        self.assertEqual(result['source'], 'infrasound_array')


class TestXBandRadarAdapter(unittest.TestCase):
    def setUp(self):
        import backend.common.station_sensor_adapters as ss
        self._original = ss.STATION_SENSOR_ENABLED
        ss.STATION_SENSOR_ENABLED = True
        self.adapter = XBandRadarAdapter()

    def tearDown(self):
        import backend.common.station_sensor_adapters as ss
        ss.STATION_SENSOR_ENABLED = self._original

    def test_sensor_name(self):
        self.assertEqual(self.adapter.sensor_name, 'xband_radar')

    def test_available(self):
        self.assertTrue(self.adapter.available())

    def test_query_returns_empty(self):
        results = self.adapter.query(
            region_key='great_himalaya',
            bbox=(30.0, 78.0, 31.0, 79.0),
            date_range=(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)),
        )
        self.assertEqual(results, [])

    def test_retrieve_returns_none(self):
        self.assertIsNone(self.adapter.retrieve('test_002'))

    def test_normalize(self):
        from backend.common.remote_sensing_adapter import SceneData
        scene = SceneData(scene_id='test_002', sensor='xband_radar')
        result = self.adapter.normalize(scene)
        self.assertEqual(result['source'], 'xband_radar')


if __name__ == '__main__':
    unittest.main()
