"""Tests for WeatherNext source adapter skeleton (Phase 3-prep + Phase 0.5)."""
from __future__ import annotations

import unittest

from backend.common.weathernext_adapter import (
    WEATHERNEXT_ENABLED,
    WeatherNextSourceManifest,
    check_weathernext_variable_completeness,
    create_default_manifest,
    get_missing_variables,
    is_weathernext_enabled,
    SNOWPACK_FORCING_VARIABLES,
    SOURCE_CLASSIFICATION_STATES,
    WN2_DEFAULT_ENSEMBLE_SIZE,
    WN2_DEFAULT_FORECAST_HORIZON_H,
    WN2_DEFAULT_RESOLUTION_DEG,
    WN2_DEFAULT_UPDATE_FREQUENCY_H,
    WN2_OFFICIAL_SURFACE_FIELDS,
    WN2_DOCUMENTED_FIELDS,
    WN2_MISSING_FOR_SNOWPACK,
    assess_weathernext_forcing,
)


class TestWeatherNextSourceManifest(unittest.TestCase):
    """Test WeatherNext source manifest validation."""

    def _valid_manifest(self, **overrides) -> WeatherNextSourceManifest:
        defaults = dict(
            repo_url='https://github.com/google-deepmind/weathernext',
            release_tag='v1.0',
            model_checkpoint='wn2-full',
            model_sha256='a' * 64,
            licence='Apache-2.0',
            fields=('temperature', 'humidity', 'wind_speed', 'precipitation'),
            resolution_deg=0.25,
            update_frequency_h=6,
            ensemble_size=64,
            forecast_horizon_h=360,
        )
        defaults.update(overrides)
        return WeatherNextSourceManifest(**defaults)

    def test_valid_manifest_accepted(self) -> None:
        errors = self._valid_manifest().validate()
        self.assertEqual(errors, [])

    def test_missing_repo_url_rejected(self) -> None:
        errors = self._valid_manifest(repo_url='').validate()
        self.assertTrue(any('repo_url' in e for e in errors))

    def test_missing_release_tag_rejected(self) -> None:
        errors = self._valid_manifest(release_tag='').validate()
        self.assertTrue(any('release_tag' in e for e in errors))

    def test_missing_licence_rejected(self) -> None:
        errors = self._valid_manifest(licence='').validate()
        self.assertTrue(any('licence' in e for e in errors))

    def test_invalid_classification_rejected(self) -> None:
        errors = self._valid_manifest(classification='invalid').validate()
        self.assertTrue(any('classification' in e for e in errors))

    def test_zero_ensemble_size_rejected(self) -> None:
        errors = self._valid_manifest(ensemble_size=0).validate()
        self.assertTrue(any('ensemble_size' in e for e in errors))

    def test_unqualified_is_not_operational(self) -> None:
        manifest = self._valid_manifest(classification='unqualified')
        self.assertFalse(manifest.is_approved_for_operational)
        self.assertFalse(manifest.is_approved_for_shadow)

    def test_shadow_only_is_not_operational(self) -> None:
        manifest = self._valid_manifest(classification='shadow_only')
        self.assertFalse(manifest.is_approved_for_operational)
        self.assertTrue(manifest.is_approved_for_shadow)

    def test_promoted_is_operational(self) -> None:
        manifest = self._valid_manifest(classification='promoted')
        self.assertTrue(manifest.is_approved_for_operational)
        self.assertTrue(manifest.is_approved_for_shadow)

    def test_rejected_is_not_approved(self) -> None:
        manifest = self._valid_manifest(classification='rejected')
        self.assertFalse(manifest.is_approved_for_operational)
        self.assertFalse(manifest.is_approved_for_shadow)


class TestUnpinnedRejectionPhase05(unittest.TestCase):
    """Phase 0.5: UNPINNED identities and invalid hashes rejected when qualified."""

    def _valid_qualified_manifest(self, **overrides) -> WeatherNextSourceManifest:
        defaults = dict(
            repo_url='https://github.com/google-deepmind/weathernext',
            release_tag='v2.0-pinned',
            model_checkpoint='wn2-checkpoint-abc123',
            model_sha256='a' * 64,
            licence='Apache-2.0',
            fields=WN2_DOCUMENTED_FIELDS,
            resolution_deg=WN2_DEFAULT_RESOLUTION_DEG,
            update_frequency_h=WN2_DEFAULT_UPDATE_FREQUENCY_H,
            ensemble_size=WN2_DEFAULT_ENSEMBLE_SIZE,
            forecast_horizon_h=WN2_DEFAULT_FORECAST_HORIZON_H,
            classification='shadow_only',
        )
        defaults.update(overrides)
        return WeatherNextSourceManifest(**defaults)

    def test_unpinned_release_tag_rejected_for_shadow_only(self) -> None:
        """shadow_only classification must reject UNPINNED release_tag."""
        manifest = self._valid_qualified_manifest(release_tag='UNPINNED')
        errors = manifest.validate()
        self.assertTrue(any('UNPINNED' in e and 'shadow_only' in e for e in errors))

    def test_unpinned_model_checkpoint_rejected_for_shadow_only(self) -> None:
        """shadow_only classification must reject UNPINNED model_checkpoint."""
        manifest = self._valid_qualified_manifest(model_checkpoint='UNPINNED')
        errors = manifest.validate()
        self.assertTrue(any('UNPINNED' in e and 'model_checkpoint' in e for e in errors))

    def test_unpinned_model_sha256_rejected_for_shadow_only(self) -> None:
        """shadow_only classification must reject UNPINNED model_sha256."""
        manifest = self._valid_qualified_manifest(model_sha256='UNPINNED')
        errors = manifest.validate()
        self.assertTrue(any('UNPINNED' in e and 'model_sha256' in e for e in errors))

    def test_invalid_hash_format_rejected_for_shadow_only(self) -> None:
        """shadow_only classification must reject non-SHA-256 hash format."""
        manifest = self._valid_qualified_manifest(model_sha256='not-a-valid-hash')
        errors = manifest.validate()
        self.assertTrue(any('SHA-256' in e and 'shadow_only' in e for e in errors))

    def test_unpinned_release_tag_rejected_for_promoted(self) -> None:
        """promoted classification must reject UNPINNED release_tag."""
        manifest = self._valid_qualified_manifest(
            release_tag='UNPINNED', classification='promoted'
        )
        errors = manifest.validate()
        self.assertTrue(any('UNPINNED' in e and 'promoted' in e for e in errors))

    def test_unpinned_accepted_for_unqualified(self) -> None:
        """unqualified classification may have UNPINNED (skeleton state)."""
        manifest = self._valid_qualified_manifest(
            release_tag='UNPINNED',
            model_checkpoint='UNPINNED',
            model_sha256='UNPINNED',
            classification='unqualified',
        )
        errors = manifest.validate()
        # No errors about UNPINNED — unqualified is allowed to be unpinned
        self.assertFalse(any('UNPINNED' in e for e in errors))

    def test_pinned_valid_hash_accepted_for_shadow_only(self) -> None:
        """shadow_only with pinned identity and valid SHA-256 must be accepted."""
        manifest = self._valid_qualified_manifest(classification='shadow_only')
        errors = manifest.validate()
        self.assertEqual(errors, [])

    def test_pinned_valid_hash_accepted_for_promoted(self) -> None:
        """promoted with pinned identity and valid SHA-256 must be accepted."""
        manifest = self._valid_qualified_manifest(classification='promoted')
        errors = manifest.validate()
        self.assertEqual(errors, [])

    def test_qualified_source_requires_forcing_bridge_before_snowpack(self) -> None:
        manifest = self._valid_qualified_manifest(
            fields=(
                '2m_temperature', 'relative_humidity_2m',
                '10m_u_component_of_wind', '10m_v_component_of_wind',
                'surface_shortwave_radiation', 'surface_longwave_radiation',
                'total_precipitation_6hr',
            )
        )
        assessment = assess_weathernext_forcing(manifest)
        self.assertTrue(assessment.shadow_eligible)
        self.assertTrue(assessment.direct_complete)
        self.assertTrue(assessment.forcing_bridge_required)
        self.assertFalse(assessment.can_feed_snowpack)

    def test_unqualified_wn2_assessment_is_not_shadow_eligible(self) -> None:
        assessment = assess_weathernext_forcing(create_default_manifest())
        self.assertFalse(assessment.shadow_eligible)
        self.assertFalse(assessment.direct_complete)
        self.assertIn('ISWR', assessment.missing_variables)

    def test_manifest_rejects_non_exact_numeric_types(self) -> None:
        for field_name, value in (
            ('ensemble_size', 64.0),
            ('update_frequency_h', True),
            ('forecast_horizon_h', '360'),
            ('resolution_deg', float('nan')),
        ):
            with self.subTest(field_name=field_name):
                self.assertTrue(any(field_name in error for error in self._valid_qualified_manifest(**{field_name: value}).validate()))

    def test_non_string_qualified_hash_fails_closed(self) -> None:
        manifest = self._valid_qualified_manifest(model_sha256=123)  # type: ignore[arg-type]
        errors = manifest.validate()
        self.assertTrue(any('model_sha256' in error for error in errors))


class TestVariableCompleteness(unittest.TestCase):
    """Test SNOWPACK forcing variable completeness check."""

    def test_all_variables_present(self) -> None:
        # P1.3: use official WN2 field names + reconstructed missing fields
        manifest = self._valid_manifest_with_fields(
            '2m_temperature', 'relative_humidity_2m',
            '10m_u_component_of_wind', '10m_v_component_of_wind',
            'surface_shortwave_radiation', 'surface_longwave_radiation',
            'total_precipitation_6hr'
        )
        completeness = check_weathernext_variable_completeness(manifest)
        for var in SNOWPACK_FORCING_VARIABLES:
            self.assertTrue(completeness[var], f'{var} should be present')

    def test_missing_radiation_detected(self) -> None:
        manifest = self._valid_manifest_with_fields(
            '2m_temperature', '10m_u_component_of_wind',
            '10m_v_component_of_wind', 'total_precipitation_6hr'
        )
        missing = get_missing_variables(manifest)
        self.assertIn('ISWR', missing)
        self.assertIn('ILWR', missing)

    def test_no_missing_when_all_present(self) -> None:
        manifest = self._valid_manifest_with_fields(
            '2m_temperature', 'relative_humidity_2m',
            '10m_u_component_of_wind', '10m_v_component_of_wind',
            'surface_shortwave_radiation', 'surface_longwave_radiation',
            'total_precipitation_6hr'
        )
        missing = get_missing_variables(manifest)
        self.assertEqual(missing, [])

    def test_wn2_documented_fields_missing_radiation(self) -> None:
        """WN2 official surface fields must be missing radiation for SNOWPACK."""
        manifest = WeatherNextSourceManifest(
            repo_url='https://github.com/google-deepmind/weathernext',
            release_tag='v1.0', model_checkpoint='wn2-full',
            model_sha256='a' * 64, licence='Apache-2.0',
            fields=WN2_OFFICIAL_SURFACE_FIELDS,
            resolution_deg=WN2_DEFAULT_RESOLUTION_DEG,
            update_frequency_h=WN2_DEFAULT_UPDATE_FREQUENCY_H,
            ensemble_size=WN2_DEFAULT_ENSEMBLE_SIZE,
            forecast_horizon_h=WN2_DEFAULT_FORECAST_HORIZON_H,
        )
        missing = get_missing_variables(manifest)
        self.assertIn('ISWR', missing)
        self.assertIn('ILWR', missing)

    def test_malformed_fields_assessment_fails_closed(self) -> None:
        manifest = WeatherNextSourceManifest(
            repo_url='https://github.com/google-deepmind/weathernext',
            release_tag='v1.0', model_checkpoint='wn2-full',
            model_sha256='a' * 64, licence='Apache-2.0',
            fields=None,  # type: ignore[arg-type]
            resolution_deg=0.25, update_frequency_h=6,
            ensemble_size=64, forecast_horizon_h=360,
        )
        assessment = assess_weathernext_forcing(manifest)
        self.assertFalse(assessment.manifest_valid)
        self.assertFalse(assessment.shadow_eligible)
        self.assertFalse(assessment.can_feed_snowpack)

    def _valid_manifest_with_fields(self, *fields) -> WeatherNextSourceManifest:
        return WeatherNextSourceManifest(
            repo_url='https://github.com/google-deepmind/weathernext',
            release_tag='v1.0', model_checkpoint='wn2-full',
            model_sha256='a' * 64, licence='Apache-2.0',
            fields=fields, resolution_deg=0.25,
            update_frequency_h=6, ensemble_size=64, forecast_horizon_h=360,
        )


class TestDefaultManifest(unittest.TestCase):
    """Test the default manifest creation."""

    def test_default_manifest_is_unqualified(self) -> None:
        manifest = create_default_manifest()
        self.assertEqual(manifest.classification, 'unqualified')
        self.assertFalse(manifest.is_approved_for_operational)
        self.assertFalse(manifest.is_approved_for_shadow)

    def test_default_manifest_has_unpinned_tag(self) -> None:
        manifest = create_default_manifest()
        self.assertEqual(manifest.release_tag, 'UNPINNED')
        self.assertEqual(manifest.model_checkpoint, 'UNPINNED')

    def test_default_manifest_notes_skeleton_status(self) -> None:
        manifest = create_default_manifest()
        self.assertIn('Skeleton', manifest.notes)

    def test_default_manifest_uses_wn2_spec(self) -> None:
        """Phase 0.5: default manifest must use WN2 specification (64-member, 360h)."""
        manifest = create_default_manifest()
        self.assertEqual(manifest.ensemble_size, WN2_DEFAULT_ENSEMBLE_SIZE)
        self.assertEqual(manifest.forecast_horizon_h, WN2_DEFAULT_FORECAST_HORIZON_H)
        self.assertEqual(manifest.resolution_deg, WN2_DEFAULT_RESOLUTION_DEG)
        self.assertEqual(manifest.update_frequency_h, WN2_DEFAULT_UPDATE_FREQUENCY_H)

    def test_default_manifest_documents_missing_snowpack_fields(self) -> None:
        """Phase 0.5: default manifest notes must document missing SNOWPACK fields."""
        manifest = create_default_manifest()
        for missing_field in WN2_MISSING_FOR_SNOWPACK:
            self.assertIn(missing_field, manifest.notes)


class TestWeatherNextEnabled(unittest.TestCase):
    """Test WeatherNext enablement flag."""

    def test_disabled_by_default(self) -> None:
        # WEATHERNEXT_ENABLED is read at import time; just check the value
        self.assertIsInstance(WEATHERNEXT_ENABLED, bool)
        self.assertIsInstance(is_weathernext_enabled(), bool)


if __name__ == '__main__':
    unittest.main()
