"""Tests for remote_sensing_adapter.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.remote_sensing_adapter import (
    RemoteSensingAdapter,
    SceneMetadata,
    SceneData,
)


class TestSceneMetadata(unittest.TestCase):
    def test_defaults(self):
        meta = SceneMetadata(scene_id='S1A_IW_20260101', sensor='sentinel1')
        self.assertEqual(meta.scene_id, 'S1A_IW_20260101')
        self.assertIsNone(meta.acquisition_time)
        self.assertIsNone(meta.orbit)
        self.assertIsNone(meta.cloud_cover)


class TestSceneData(unittest.TestCase):
    def test_defaults(self):
        data = SceneData(scene_id='S2A_20260101', sensor='sentinel2')
        self.assertEqual(data.scene_id, 'S2A_20260101')
        self.assertIsNone(data.raw_data)
        self.assertEqual(data.bands, {})


class TestABCConformance(unittest.TestCase):
    def test_cannot_instantiate_abc(self):
        with self.assertRaises(TypeError):
            RemoteSensingAdapter()

    def test_minimal_implementation(self):
        class TestAdapter(RemoteSensingAdapter):
            @property
            def sensor_name(self) -> str:
                return 'test'

            def available(self) -> bool:
                return True

            def query(self, *, region_key, bbox, date_range):
                return [SceneMetadata(scene_id='test_1', sensor='test')]

            def retrieve(self, scene_id):
                return SceneData(scene_id=scene_id, sensor='test')

            def normalize(self, scene_data):
                return {'source': 'test', 'scene_id': scene_data.scene_id}

        adapter = TestAdapter()
        self.assertEqual(adapter.sensor_name, 'test')
        self.assertTrue(adapter.available())
        results = adapter.query(
            region_key='test',
            bbox=(39.0, -107.0, 40.0, -106.0),
            date_range=(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, tzinfo=timezone.utc)),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].scene_id, 'test_1')

        scene = adapter.retrieve('test_1')
        self.assertIsNotNone(scene)
        normalized = adapter.normalize(scene)
        self.assertEqual(normalized['source'], 'test')


if __name__ == '__main__':
    unittest.main()
