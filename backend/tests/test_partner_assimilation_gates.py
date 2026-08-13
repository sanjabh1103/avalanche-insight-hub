"""Regression tests for partner observation assimilation gates.

Verifies that _assimilate_partner_observations enforces:
- Station registry (only registered stations accepted)
- QC status (fail = rejected)
- Temporal matching (stale observations rejected)
- Elevation gate (large elevation diff rejected)
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.daily_inference import _assimilate_partner_observations


@dataclass(frozen=True)
class MockObs:
    station_id: str
    observed_at: str
    latitude: float | None
    longitude: float | None
    elevation_m: float | None
    values: dict[str, float]
    units: dict[str, str]
    qc_status: str
    source_hash: str
    review_status: str
    source: str

    @property
    def station_identity(self) -> dict[str, Any]:
        return {
            'station_id': self.station_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'elevation_m': self.elevation_m,
        }


class PartnerAssimilationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.weather = {
            'downscaled_temperature_c': -5.0,
            'snowfall_24h_cm': 10.0,
            'windspeed_10m': 5.0,
            'precipitation_24h_mm': 2.0,
            'snow_depth_cm': 50.0,
        }
        self.center_lat = 34.0
        self.center_lng = 74.0
        self.forecast_time = pd.Timestamp('2026-04-29T06:00:00Z')

    def _make_obs(
        self,
        station_id: str = 'STN-001',
        observed_at: str = '2026-04-29T05:00:00Z',
        lat: float = 34.01,
        lng: float = 74.01,
        elevation_m: float | None = 3000.0,
        qc_status: str = 'pass',
        values: dict[str, float] | None = None,
        review_status: str = 'reviewed',
    ) -> MockObs:
        return MockObs(
            station_id=station_id,
            observed_at=observed_at,
            latitude=lat,
            longitude=lng,
            elevation_m=elevation_m,
            values=values or {'air_temp_c': -7.0, 'snowfall_cm': 12.0},
            units={'air_temp_c': 'celsius', 'snowfall_cm': 'cm'},
            qc_status=qc_status,
            source_hash='abc123',
            review_status=review_status,
            source='aws_live_feed',
        )

    def test_station_registry_rejects_unregistered(self) -> None:
        obs = [self._make_obs(station_id='UNKNOWN-STN')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            station_registry={'STN-001', 'STN-002'},
        )
        self.assertEqual(len(matched), 0)

    def test_station_registry_accepts_registered(self) -> None:
        obs = [self._make_obs(station_id='STN-001')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            station_registry={'STN-001', 'STN-002'},
        )
        self.assertEqual(len(matched), 1)

    def test_qc_fail_rejected(self) -> None:
        obs = [self._make_obs(qc_status='fail')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
        )
        self.assertEqual(len(matched), 0)

    def test_qc_pass_accepted(self) -> None:
        obs = [self._make_obs(qc_status='pass')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
        )
        self.assertEqual(len(matched), 1)

    def test_temporal_gate_rejects_stale(self) -> None:
        obs = [self._make_obs(observed_at='2026-04-28T00:00:00Z')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            forecast_time=self.forecast_time,
            max_temporal_delta_hours=6.0,
        )
        self.assertEqual(len(matched), 0)

    def test_temporal_gate_accepts_recent(self) -> None:
        obs = [self._make_obs(observed_at='2026-04-29T04:00:00Z')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            forecast_time=self.forecast_time,
            max_temporal_delta_hours=6.0,
        )
        self.assertEqual(len(matched), 1)

    def test_elevation_gate_rejects_large_diff(self) -> None:
        obs = [self._make_obs(elevation_m=100.0)]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            center_elevation_m=3000.0,
            max_elevation_diff_m=500.0,
        )
        self.assertEqual(len(matched), 0)

    def test_elevation_gate_accepts_small_diff(self) -> None:
        obs = [self._make_obs(elevation_m=2800.0)]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            center_elevation_m=3000.0,
            max_elevation_diff_m=500.0,
        )
        self.assertEqual(len(matched), 1)

    def test_backward_compatible_without_gates(self) -> None:
        """Without optional gates, behavior matches original (backward compatible)."""
        obs = [self._make_obs()]
        assimilated, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(assimilated['downscaled_temperature_c'], -7.0)

    def test_snowpack_obs_with_coordinates_matched(self) -> None:
        """A SNOWPACK observation with coordinates inside radius is matched."""
        obs = self._make_obs(
            station_id='SP-001',
            values={'snow_depth_cm': 120.0},
        )
        obs = MockObs(
            station_id=obs.station_id,
            observed_at=obs.observed_at,
            latitude=34.01,
            longitude=74.01,
            elevation_m=3000.0,
            values={'snow_depth_cm': 120.0},
            units={'snow_depth_cm': 'cm'},
            qc_status='pass',
            source_hash=obs.source_hash,
            review_status='reviewed',
            source='Partner_snowpack_1d',
        )
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, [obs],
            forecast_time=self.forecast_time,
            max_temporal_delta_hours=6.0,
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]['station_id'], 'SP-001')

    def test_registry_loader_parses_example_file(self) -> None:
        """Registry loader parses the example JSON file correctly."""
        import json
        import tempfile
        from backend.common.partner_assimilation_config import load_station_registry

        registry_data = {
            'stations': [
                {'station_id': 'STN-A', 'latitude': 34.0, 'longitude': 74.0, 'elevation_m': 3000.0},
                {'station_id': 'STN-B', 'latitude': 34.1, 'longitude': 74.1, 'elevation_m': 3200.0},
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry_data, f)
            f.flush()
            result = load_station_registry(f.name)
        self.assertIsNotNone(result)
        self.assertEqual(result, {'STN-A', 'STN-B'})

    def test_registry_loader_malformed_raises(self) -> None:
        """Malformed registry JSON raises an error (fail closed)."""
        import tempfile
        from backend.common.partner_assimilation_config import load_station_registry

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{invalid json')
            f.flush()
            with self.assertRaises(Exception):
                load_station_registry(f.name)

    def test_registry_loader_unset_env_returns_none(self) -> None:
        """Unset env var returns None (backward compatible)."""
        import os
        from backend.common.partner_assimilation_config import load_station_registry

        old = os.environ.pop('PARTNER_STATION_REGISTRY_PATH', None)
        try:
            result = load_station_registry()
            self.assertIsNone(result)
        finally:
            if old is not None:
                os.environ['PARTNER_STATION_REGISTRY_PATH'] = old

    def test_require_reviewed_rejects_unreviewed(self) -> None:
        """require_reviewed=True rejects review_status='unreviewed'."""
        obs = [self._make_obs(review_status='unreviewed')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            require_reviewed=True,
        )
        self.assertEqual(len(matched), 0)

    def test_require_reviewed_accepts_reviewed(self) -> None:
        """require_reviewed=True accepts review_status='reviewed'."""
        obs = [self._make_obs(review_status='reviewed')]
        _, matched = _assimilate_partner_observations(
            self.weather, self.center_lat, self.center_lng, obs,
            require_reviewed=True,
        )
        self.assertEqual(len(matched), 1)


if __name__ == '__main__':
    unittest.main()
