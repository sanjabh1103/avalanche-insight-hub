"""Tests for partner observation normalization."""
from __future__ import annotations

import unittest

from backend.common.partner_observation import (
    PartnerObservation,
    normalize_aws_record,
    normalize_snowpack_proxy,
    validate_observation_against_registry,
)
from backend.common.snowpack_proxy import SnowpackProxy


class NormalizeAWSRecordTests(unittest.TestCase):
    def test_valid_record_with_numeric_fields(self) -> None:
        raw = {
            'station_id': 'ST001',
            'observed_at': '2026-01-15T08:00:00Z',
            'air_temp_c': -5.0,
            'snow_depth_cm': 120.0,
            'wind_speed_ms': 15.0,
            'latitude': 34.5,
            'longitude': 77.0,
            'elevation_m': 3500.0,
        }
        obs = normalize_aws_record(raw)
        self.assertIsNotNone(obs)
        self.assertEqual(obs.station_id, 'ST001')
        self.assertEqual(obs.values['air_temp_c'], -5.0)
        self.assertEqual(obs.latitude, 34.5)
        self.assertEqual(obs.longitude, 77.0)
        self.assertEqual(obs.elevation_m, 3500.0)
        self.assertEqual(obs.source, 'aws_live_feed')
        self.assertEqual(obs.qc_status, 'unchecked')
        self.assertTrue(len(obs.source_hash) == 64)

    def test_missing_station_id_returns_none(self) -> None:
        raw = {'observed_at': '2026-01-15T08:00:00Z', 'air_temp_c': -5.0}
        self.assertIsNone(normalize_aws_record(raw))

    def test_missing_observed_at_returns_none(self) -> None:
        raw = {'station_id': 'ST001', 'air_temp_c': -5.0}
        self.assertIsNone(normalize_aws_record(raw))

    def test_non_numeric_value_returns_none(self) -> None:
        raw = {
            'station_id': 'ST001',
            'observed_at': '2026-01-15T08:00:00Z',
            'air_temp_c': 'invalid',
        }
        self.assertIsNone(normalize_aws_record(raw))

    def test_no_numeric_fields_returns_none(self) -> None:
        raw = {
            'station_id': 'ST001',
            'observed_at': '2026-01-15T08:00:00Z',
        }
        self.assertIsNone(normalize_aws_record(raw))

    def test_partial_numeric_fields_accepted(self) -> None:
        raw = {
            'station_id': 'ST001',
            'observed_at': '2026-01-15T08:00:00Z',
            'air_temp_c': -5.0,
        }
        obs = normalize_aws_record(raw)
        self.assertIsNotNone(obs)
        self.assertEqual(len(obs.values), 1)
        self.assertIn('air_temp_c', obs.values)

    def test_source_hash_deterministic(self) -> None:
        raw = {
            'station_id': 'ST001',
            'observed_at': '2026-01-15T08:00:00Z',
            'air_temp_c': -5.0,
        }
        obs1 = normalize_aws_record(raw)
        obs2 = normalize_aws_record(raw)
        self.assertEqual(obs1.source_hash, obs2.source_hash)

    def test_different_values_different_hash(self) -> None:
        raw1 = {'station_id': 'ST001', 'observed_at': '2026-01-15', 'air_temp_c': -5.0}
        raw2 = {'station_id': 'ST001', 'observed_at': '2026-01-15', 'air_temp_c': -10.0}
        obs1 = normalize_aws_record(raw1)
        obs2 = normalize_aws_record(raw2)
        self.assertNotEqual(obs1.source_hash, obs2.source_hash)


class NormalizeSnowpackProxyTests(unittest.TestCase):
    def test_valid_proxy(self) -> None:
        proxy = SnowpackProxy(
            estimated_shear_strength=5.0,
            snow_settlement_index=0.7,
            season_start='2025-11-01',
            method='Partner_snowpack_1d',
        )
        obs = normalize_snowpack_proxy(proxy, station_id='SP001')
        self.assertIsNotNone(obs)
        self.assertEqual(obs.station_id, 'SP001')
        self.assertEqual(obs.values['estimated_shear_strength_kpa'], 5.0)
        self.assertEqual(obs.values['snow_settlement_index'], 0.7)
        self.assertEqual(obs.source, 'Partner_snowpack_1d')

    def test_missing_station_id_returns_none(self) -> None:
        proxy = SnowpackProxy(
            estimated_shear_strength=5.0,
            snow_settlement_index=0.7,
            season_start='2025-11-01',
            method='Partner_snowpack_1d',
        )
        self.assertIsNone(normalize_snowpack_proxy(proxy, station_id=''))


class TestRegistryValidation(unittest.TestCase):
    """G-06: Test validate_observation_against_registry."""

    def _make_obs(self, station_id='ST001', lat=34.5, lon=77.0, elev=3500.0) -> PartnerObservation:
        return PartnerObservation(
            station_id=station_id,
            observed_at='2026-01-15T08:00:00Z',
            latitude=lat,
            longitude=lon,
            elevation_m=elev,
            values={'air_temp_c': -5.0},
            units={'air_temp_c': 'celsius'},
            qc_status='unchecked',
            source_hash='abc123',
            review_status='unreviewed',
            source='aws_live_feed',
        )

    def test_registry_none_fails_closed(self):
        """No registry configured — validation fails closed (returns errors, not skip)."""
        from backend.common.partner_observation import validate_observation_against_registry
        obs = self._make_obs()
        errors = validate_observation_against_registry(obs, None)
        self.assertGreater(len(errors), 0, 'None registry must fail closed')

    def test_station_not_in_registry(self):
        """Station ID not in registry produces error."""
        from backend.common.partner_observation import validate_observation_against_registry
        from backend.common.partner_assimilation_config import StationRecord
        registry = {'OTHER_ST': StationRecord('OTHER_ST', 35.0, 78.0, 3600.0, {})}
        obs = self._make_obs(station_id='ST001')
        errors = validate_observation_against_registry(obs, registry)
        self.assertEqual(len(errors), 1)
        self.assertIn('not in station registry', errors[0])

    def test_matching_registry_no_errors(self):
        """Observation matching registry metadata produces no errors."""
        from backend.common.partner_observation import validate_observation_against_registry
        from backend.common.partner_assimilation_config import StationRecord
        registry = {'ST001': StationRecord('ST001', 34.5, 77.0, 3500.0, {'air_temp_c': 'celsius'})}
        obs = self._make_obs()
        errors = validate_observation_against_registry(obs, registry)
        self.assertEqual(errors, [])

    def test_coordinate_mismatch_detected(self):
        """Large coordinate difference from registry is flagged."""
        from backend.common.partner_observation import validate_observation_against_registry
        from backend.common.partner_assimilation_config import StationRecord
        registry = {'ST001': StationRecord('ST001', 40.0, 80.0, 3500.0, {})}
        obs = self._make_obs(lat=34.5, lon=77.0)
        errors = validate_observation_against_registry(obs, registry)
        self.assertTrue(any('latitude' in e for e in errors))
        self.assertTrue(any('longitude' in e for e in errors))

    def test_elevation_mismatch_detected(self):
        """Large elevation difference from registry is flagged."""
        from backend.common.partner_observation import validate_observation_against_registry
        from backend.common.partner_assimilation_config import StationRecord
        registry = {'ST001': StationRecord('ST001', 34.5, 77.0, 5000.0, {})}
        obs = self._make_obs(elev=3500.0)
        errors = validate_observation_against_registry(obs, registry)
        self.assertTrue(any('elevation' in e for e in errors))

    def test_unit_mismatch_detected(self):
        """Unit inconsistency between observation and registry is flagged."""
        from backend.common.partner_observation import validate_observation_against_registry
        from backend.common.partner_assimilation_config import StationRecord
        registry = {'ST001': StationRecord('ST001', 34.5, 77.0, 3500.0, {'air_temp_c': 'fahrenheit'})}
        obs = self._make_obs()
        errors = validate_observation_against_registry(obs, registry)
        self.assertTrue(any('unit mismatch' in e for e in errors))


class TestStationRegistryWithMetadata(unittest.TestCase):
    """G-06: Test load_station_registry_with_metadata."""

    def test_no_path_returns_none(self):
        """No registry path configured returns None."""
        from backend.common.partner_assimilation_config import load_station_registry_with_metadata
        import os
        old = os.environ.get('PARTNER_STATION_REGISTRY_PATH', '')
        os.environ.pop('PARTNER_STATION_REGISTRY_PATH', None)
        try:
            result = load_station_registry_with_metadata()
            self.assertIsNone(result)
        finally:
            if old:
                os.environ['PARTNER_STATION_REGISTRY_PATH'] = old

    def test_loads_full_metadata(self):
        """Registry with coordinates, elevation, and units loads correctly."""
        import json
        import tempfile
        from pathlib import Path
        from backend.common.partner_assimilation_config import load_station_registry_with_metadata
        registry_data = {
            'stations': [
                {
                    'station_id': 'ST001',
                    'latitude': 34.5,
                    'longitude': 77.0,
                    'elevation_m': 3500.0,
                    'units': {'air_temp_c': 'celsius'},
                },
                {
                    'station_id': 'ST002',
                    'latitude': 35.0,
                    'longitude': 78.0,
                    'elevation_m': 4000.0,
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry_data, f)
            reg_path = f.name
        try:
            result = load_station_registry_with_metadata(reg_path)
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 2)
            self.assertIn('ST001', result)
            self.assertEqual(result['ST001'].latitude, 34.5)
            self.assertEqual(result['ST001'].elevation_m, 3500.0)
            self.assertEqual(result['ST001'].units, {'air_temp_c': 'celsius'})
            self.assertEqual(result['ST002'].units, {})
        finally:
            Path(reg_path).unlink()


class TestValidateObservationAgainstRegistry(unittest.TestCase):
    """G-06: Tests for partner observation validation against station metadata registry."""

    def _make_obs(self, station_id: str = 'ST001') -> PartnerObservation:
        return PartnerObservation(
            station_id=station_id,
            observed_at='2026-01-15T08:00:00Z',
            latitude=32.5,
            longitude=77.0,
            elevation_m=3500.0,
            values={'air_temp_c': -5.0, 'snow_depth_cm': 120.0, 'wind_speed_kmh': 15.0},
            units={'air_temp_c': 'celsius', 'snow_depth_cm': 'cm', 'wind_speed_kmh': 'kmh'},
            qc_status='pass',
            source_hash='abc123',
            review_status='reviewed',
            source='aws',
        )

    def test_unknown_station_rejected(self):
        """Observation from unknown station ID is rejected."""
        from backend.common.partner_assimilation_config import StationRecord
        registry = {
            'KNOWN_STN': StationRecord(
                station_id='KNOWN_STN', latitude=32.0, longitude=77.0,
                elevation_m=3000.0, units={},
            ),
        }
        obs = self._make_obs(station_id='UNKNOWN_STN')
        errors = validate_observation_against_registry(obs, registry)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any('UNKNOWN_STN' in e or 'not_in_registry' in e for e in errors))

    def test_known_station_accepted(self):
        """Observation from known station with matching metadata is accepted."""
        from backend.common.partner_assimilation_config import StationRecord
        registry = {
            'ST001': StationRecord(
                station_id='ST001', latitude=32.5, longitude=77.0,
                elevation_m=3500.0, units={},
            ),
        }
        obs = self._make_obs(station_id='ST001')
        errors = validate_observation_against_registry(obs, registry)
        self.assertEqual(len(errors), 0)

    def test_none_registry_returns_errors(self):
        """None registry returns errors (fail-closed) — observations must be rejected."""
        obs = self._make_obs()
        errors = validate_observation_against_registry(obs, None)
        self.assertIsInstance(errors, list)
        self.assertGreater(len(errors), 0, 'None registry must produce errors (fail-closed)')
        self.assertTrue(any('not configured' in e or 'registry' in e.lower() for e in errors))

    def test_empty_registry_rejects(self):
        """Empty registry rejects all observations."""
        obs = self._make_obs()
        errors = validate_observation_against_registry(obs, {})
        self.assertGreater(len(errors), 0)


if __name__ == '__main__':
    unittest.main()
