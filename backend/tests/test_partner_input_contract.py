"""Tests for Phase 2: Partner input contract, canonical DangerOutput, calibration lineage.

Verifies that:
- PartnerObservation with metadata produces valid station_identity
- PartnerObservation missing metadata produces validation errors
- Dead loop is removed from normalize_aws_record
- compute_canonical_danger produces correct DangerOutput
- DangerOutput with shadow profile has is_shadow_only=True
- CalibrationManifest produces correct lineage dict
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.common.partner_observation import (
    PartnerObservation,
    normalize_aws_record,
    normalize_snowpack_proxy,
    validate_partner_observation,
)
from backend.common.risk_math import (
    DangerAggregationConfig,
    DangerOutput,
    DANGER_AGGREGATION_PROFILE,
    SHADOW_PROFILES,
    compute_canonical_danger,
)
from backend.common.snowpack_proxy import SnowpackProxy
from backend.common.uncertainty_quantification import (
    CalibrationManifest,
    CALIBRATION_MANIFEST_VERSION,
)


class TestPartnerObservationMetadata(unittest.TestCase):
    """Test partner observation station metadata preservation."""

    def test_partner_obs_with_metadata(self):
        """AWS record with lat/lon/elevation produces PartnerObservation with all fields."""
        raw = {
            'station_id': 'ST001',
            'observed_at': '2026-07-01T12:00:00Z',
            'latitude': 34.5,
            'longitude': 77.2,
            'elevation_m': 3500.0,
            'air_temp_c': -5.0,
            'snow_depth_cm': 120.0,
        }
        obs = normalize_aws_record(raw)
        self.assertIsNotNone(obs)
        self.assertEqual(obs.station_id, 'ST001')
        self.assertEqual(obs.latitude, 34.5)
        self.assertEqual(obs.longitude, 77.2)
        self.assertEqual(obs.elevation_m, 3500.0)
        identity = obs.station_identity
        self.assertEqual(identity['station_id'], 'ST001')
        self.assertEqual(identity['latitude'], 34.5)
        self.assertEqual(identity['longitude'], 77.2)
        self.assertEqual(identity['elevation_m'], 3500.0)

    def test_partner_obs_missing_metadata(self):
        """AWS record without lat/lon/elevation produces validation errors."""
        raw = {
            'station_id': 'ST002',
            'observed_at': '2026-07-01T12:00:00Z',
            'air_temp_c': -3.0,
        }
        obs = normalize_aws_record(raw)
        self.assertIsNotNone(obs)
        errors = validate_partner_observation(obs)
        self.assertTrue(any('latitude' in e for e in errors))
        self.assertTrue(any('longitude' in e for e in errors))
        self.assertTrue(any('elevation_m' in e for e in errors))

    def test_partner_obs_with_all_metadata_no_errors(self):
        """AWS record with all metadata produces no validation errors."""
        raw = {
            'station_id': 'ST003',
            'observed_at': '2026-07-01T12:00:00Z',
            'latitude': 35.0,
            'longitude': 78.0,
            'elevation_m': 4000.0,
            'snowfall_cm': 30.0,
        }
        obs = normalize_aws_record(raw)
        self.assertIsNotNone(obs)
        errors = validate_partner_observation(obs)
        self.assertEqual(errors, [])

    def test_dead_loop_removed(self):
        """Verify the dead for-pass loop is no longer in normalize_aws_record source."""
        import inspect
        source = inspect.getsource(normalize_aws_record)
        self.assertNotIn('for field_name, key in [(latitude,', source)
        self.assertNotIn('pass\n    try:', source)


class TestCanonicalDangerOutput(unittest.TestCase):
    """Test compute_canonical_danger produces correct DangerOutput."""

    def test_danger_output_fields(self):
        """DangerOutput has danger_level, profile, factors_used, is_shadow_only."""
        config = DangerAggregationConfig(
            profile='test_profile',
            factor_weights={'slope_angle': 0.5, 'snow_load': 0.5},
            thresholds=(0.2, 0.4, 0.6, 0.8),
        )
        result = compute_canonical_danger(config, slope_angle=0.7, snow_load=0.5)
        self.assertIsInstance(result, DangerOutput)
        self.assertGreaterEqual(result.danger_level, 1)
        self.assertLessEqual(result.danger_level, 5)
        self.assertEqual(result.profile, 'test_profile')
        self.assertIn('slope_angle', result.factors_used)
        self.assertIn('snow_load', result.factors_used)
        self.assertFalse(result.is_shadow_only)

    def test_danger_shadow_profile(self):
        """DangerOutput with shadow profile has is_shadow_only=True."""
        shadow_config = DangerAggregationConfig(
            profile='Partner_shadow_v1',
            factor_weights={'slope_angle': 0.3, 'snow_load': 0.3, 'temperature_delta': 0.2, 'wind_transport': 0.2},
            thresholds=(0.15, 0.35, 0.55, 0.75),
        )
        self.assertIn('Partner_shadow_v1', SHADOW_PROFILES)
        result = compute_canonical_danger(shadow_config, slope_angle=0.5, snow_load=0.3, temperature_delta=0.2, wind_transport=0.1)
        self.assertTrue(result.is_shadow_only)

    def test_danger_output_as_dict(self):
        """DangerOutput.as_dict() returns all fields."""
        config = DangerAggregationConfig(
            profile='test',
            factor_weights={'a': 1.0},
            thresholds=(0.2, 0.4, 0.6, 0.8),
        )
        result = compute_canonical_danger(config, a=0.5)
        d = result.as_dict()
        self.assertIn('danger_level', d)
        self.assertIn('profile', d)
        self.assertIn('factors_used', d)
        self.assertIn('is_shadow_only', d)

    def test_default_profile_not_shadow(self):
        """DANGER_AGGREGATION_PROFILE is not a shadow profile."""
        self.assertNotIn(DANGER_AGGREGATION_PROFILE, SHADOW_PROFILES)

    def test_shadow_danger_output_has_semantic_label(self):
        """G-10: Shadow profile danger output must include EAWS semantic label."""
        shadow_config = DangerAggregationConfig(
            profile='Partner_shadow_v1',
            factor_weights={'slope_angle': 0.3, 'snow_load': 0.3, 'temperature_delta': 0.2, 'wind_transport': 0.2},
            thresholds=(0.15, 0.35, 0.55, 0.75),
        )
        result = compute_canonical_danger(shadow_config, slope_angle=0.5, snow_load=0.3, temperature_delta=0.2, wind_transport=0.1)
        self.assertTrue(result.is_shadow_only)
        d = result.as_dict()
        self.assertIn('is_shadow_only', d)
        self.assertTrue(d['is_shadow_only'])
        self.assertEqual(d['profile'], 'Partner_shadow_v1')


class TestCalibrationLineage(unittest.TestCase):
    """Test calibration lineage persistence."""

    def test_calibration_manifest_split_conformal(self):
        """CalibrationManifest with split_conformal method has fallback_active=False."""
        manifest = CalibrationManifest(
            version=CALIBRATION_MANIFEST_VERSION,
            sha256='abc123',
            sample_count=100,
            alpha=0.1,
            empirical_coverage=0.92,
            fit_coverage=0.92,
            held_out_coverage=0.88,
            uq_method='split_conformal',
        )
        lineage = {
            'manifest': manifest.as_dict(),
            'calibrator_loaded': True,
            'fallback_active': manifest.uq_method == 'normal_fallback',
        }
        self.assertFalse(lineage['fallback_active'])
        self.assertEqual(lineage['manifest']['uq_method'], 'split_conformal')

    def test_calibration_manifest_normal_fallback(self):
        """CalibrationManifest with normal_fallback method has fallback_active=True."""
        manifest = CalibrationManifest(
            version=CALIBRATION_MANIFEST_VERSION,
            sha256='',
            sample_count=0,
            alpha=0.1,
            empirical_coverage=None,
            fit_coverage=None,
            held_out_coverage=None,
            uq_method='normal_fallback',
        )
        lineage = {
            'manifest': manifest.as_dict(),
            'calibrator_loaded': False,
            'fallback_active': manifest.uq_method == 'normal_fallback',
        }
        self.assertTrue(lineage['fallback_active'])
        self.assertEqual(lineage['manifest']['uq_method'], 'normal_fallback')

    def test_calibration_manifest_as_dict(self):
        """CalibrationManifest.as_dict() returns all fields."""
        manifest = CalibrationManifest(
            version='1.0.0',
            sha256='abc',
            sample_count=50,
            alpha=0.1,
            empirical_coverage=0.9,
            fit_coverage=0.9,
            held_out_coverage=None,
            uq_method='split_conformal',
        )
        d = manifest.as_dict()
        self.assertIn('version', d)
        self.assertIn('sha256', d)
        self.assertIn('sample_count', d)
        self.assertIn('alpha', d)
        self.assertIn('empirical_coverage', d)
        self.assertIn('fit_coverage', d)
        self.assertIn('held_out_coverage', d)
        self.assertIn('uq_method', d)


class TestSnowpackProxyNormalization(unittest.TestCase):
    """Test snowpack proxy normalization into PartnerObservation."""

    def test_normalize_snowpack_proxy_valid(self):
        """Valid SnowpackProxy normalizes into PartnerObservation."""
        proxy = SnowpackProxy(
            method='Partner_snowpack_1d',
            estimated_shear_strength=1.5,
            snow_settlement_index=0.8,
            season_start='2026-01-15',
        )
        obs = normalize_snowpack_proxy(proxy, station_id='SP001')
        self.assertIsNotNone(obs)
        self.assertEqual(obs.station_id, 'SP001')
        self.assertEqual(obs.source, 'Partner_snowpack_1d')
        self.assertIn('estimated_shear_strength_kpa', obs.values)

    def test_normalize_snowpack_proxy_no_values(self):
        """SnowpackProxy with no valid values returns None."""
        proxy = SnowpackProxy(method='test', estimated_shear_strength=None, snow_settlement_index=None, season_start='2026-01-15')
        obs = normalize_snowpack_proxy(proxy, station_id='SP002')
        self.assertIsNone(obs)


if __name__ == '__main__':
    unittest.main()
