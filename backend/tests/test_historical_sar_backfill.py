from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from backend.historical_sar_backfill import _scenes_mean_timestamp


class _Value:
    def __init__(self, value):
        self.value = value

    def getInfo(self):
        return self.value


class _Collection:
    def filterBounds(self, _geometry):
        return self

    def filterDate(self, _start, _end):
        return self

    def filter(self, _predicate):
        return self

    def size(self):
        return _Value(3)

    def aggregate_mean(self, _property):
        return _Value(None)


class _EE:
    class Geometry:
        @staticmethod
        def Rectangle(_bbox):
            return object()

    class Filter:
        @staticmethod
        def listContains(*_args):
            return object()

        @staticmethod
        def eq(*_args):
            return object()

    @staticmethod
    def ImageCollection(_name):
        return _Collection()


class HistoricalSarBackfillTests(unittest.TestCase):
    def test_missing_mean_sensing_time_does_not_use_window_midpoint(self) -> None:
        region = SimpleNamespace(bbox=(27.0, 85.0, 29.0, 87.5))
        start = datetime(2023, 11, 1, tzinfo=timezone.utc)
        end = datetime(2023, 11, 8, tzinfo=timezone.utc)

        scene_count, scene_timestamp = _scenes_mean_timestamp(_EE, region, start, end)

        self.assertEqual(scene_count, 3)
        self.assertIsNone(scene_timestamp)


if __name__ == "__main__":
    unittest.main()
