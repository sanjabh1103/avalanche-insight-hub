"""Tests for AWS/eDMRG validation pipeline."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.common.edmrg_adapter import EdmrgRecord
from backend.common.edmrg_validation import (
    StationValidationResult,
    ValidationReport,
    run_validation_pipeline,
    validate_station_observations,
)


def _make_record(
    station_id: str = 'STN001',
    timestamp: datetime | None = None,
    temp_c: float = -5.0,
    wind_ms: float = 8.0,
    snow_cm: float = 120.0,
) -> EdmrgRecord:
    ts = timestamp or datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
    return EdmrgRecord(
        station_id=station_id,
        timestamp=ts,
        cadence='manned_3h',
        fields={
            'temperature_c': temp_c,
            'wind_speed_ms': wind_ms,
            'snow_depth_cm': snow_cm,
        },
    )


def _make_forecast_samples(
    base_time: datetime,
    temp_c: float = -5.0,
    wind_ms: float = 8.0,
    snow_cm: float = 120.0,
    n: int = 24,
) -> list[dict]:
    samples = []
    for i in range(n):
        ts = base_time + timedelta(hours=i)
        samples.append({
            'timestamp': ts.isoformat(),
            'values': {
                'temperature_2m': temp_c + i * 0.1,
                'windspeed_10m': wind_ms,
                'snow_depth': snow_cm,
            },
        })
    return samples


class ValidateStationObservationsTests(unittest.TestCase):
    def test_passes_when_forecast_matches_observations(self) -> None:
        base_time = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
        records = [_make_record(timestamp=base_time + timedelta(hours=i)) for i in range(8)]
        forecast = _make_forecast_samples(base_time, temp_c=-5.0, wind_ms=8.0, snow_cm=120.0)

        result = validate_station_observations(records, forecast, 'STN001')
        self.assertTrue(result.passed)
        self.assertEqual(result.station_id, 'STN001')
        self.assertEqual(result.n_observations, 8)
        self.assertEqual(len(result.anomalies), 0)

    def test_fails_on_large_temp_bias(self) -> None:
        base_time = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
        records = [_make_record(timestamp=base_time + timedelta(hours=i), temp_c=-10.0) for i in range(8)]
        forecast = _make_forecast_samples(base_time, temp_c=-2.0)

        result = validate_station_observations(records, forecast, 'STN001')
        self.assertFalse(result.passed)
        self.assertTrue(any('temp_bias' in a for a in result.anomalies))

    def test_fails_on_large_wind_bias(self) -> None:
        base_time = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
        records = [_make_record(timestamp=base_time + timedelta(hours=i), wind_ms=2.0) for i in range(8)]
        forecast = _make_forecast_samples(base_time, wind_ms=15.0)

        result = validate_station_observations(records, forecast, 'STN001')
        self.assertFalse(result.passed)
        self.assertTrue(any('wind_bias' in a for a in result.anomalies))

    def test_fails_on_large_snow_depth_bias(self) -> None:
        base_time = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
        records = [_make_record(timestamp=base_time + timedelta(hours=i), snow_cm=50.0) for i in range(8)]
        forecast = _make_forecast_samples(base_time, snow_cm=200.0)

        result = validate_station_observations(records, forecast, 'STN001')
        self.assertFalse(result.passed)
        self.assertTrue(any('snow_depth_bias' in a for a in result.anomalies))

    def test_empty_records_returns_passed_with_zero_obs(self) -> None:
        result = validate_station_observations([], [], 'STN001')
        self.assertTrue(result.passed)
        self.assertEqual(result.n_observations, 0)


class RunValidationPipelineTests(unittest.TestCase):
    def test_groups_by_station_and_aggregates(self) -> None:
        base_time = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_record(station_id='STN001', timestamp=base_time + timedelta(hours=i))
            for i in range(4)
        ] + [
            _make_record(station_id='STN002', timestamp=base_time + timedelta(hours=i), temp_c=-3.0)
            for i in range(4)
        ]
        forecast = _make_forecast_samples(base_time, temp_c=-5.0)

        report = run_validation_pipeline(records, forecast)
        self.assertEqual(len(report.stations), 2)
        self.assertEqual(report.total_observations, 8)
        self.assertTrue(report.overall_passed)

    def test_overall_fails_if_any_station_fails(self) -> None:
        base_time = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)
        records = [
            _make_record(station_id='STN001', timestamp=base_time + timedelta(hours=i))
            for i in range(4)
        ] + [
            _make_record(station_id='STN002', timestamp=base_time + timedelta(hours=i), temp_c=20.0)
            for i in range(4)
        ]
        forecast = _make_forecast_samples(base_time, temp_c=-5.0)

        report = run_validation_pipeline(records, forecast)
        self.assertFalse(report.overall_passed)
        self.assertGreater(report.total_anomalies, 0)


if __name__ == '__main__':
    unittest.main()
