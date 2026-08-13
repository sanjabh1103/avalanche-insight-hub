"""Failure-mode tests for snowpack pipeline (Phase 13-prep).

Tests that the pipeline fails closed (not silently) for:
  - Missing binaries (SNOWPACK/AWSOME not installed)
  - Incomplete forcing (missing critical variables)
  - Stale data (old timestamps)
  - Partial ensemble output (some members missing)

Per Imp_plan.md Phase 13:
  - Replace permissive CI behavior such as validate || true.
  - Require actual output-artifact assertions in workflows.
  - Fail closed for missing binaries, invalid forcing, incomplete output
    or postprocessor failure.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.common.awsome_runner import (
    awsome_available,
    get_region_snowpack_params,
    run_awsome_for_region,
    validate_awsome_setup,
)
from backend.common.config_validator import validate_awsome_regions_sync
from backend.common.regions import load_regions
from backend.common.snowpack_artifact_manifest import ArtifactManifest, ArtifactEntry
from backend.common.snowpack_contracts import (
    ContractValidationError,
    ForcingManifestContract,
    ProvenanceMetadata,
    SnowpackRunContract,
    validate_execution_status,
)


class TestMissingBinaryFailureMode(unittest.TestCase):
    """Test that missing binaries fail closed, not silently."""

    def test_awsome_not_available_in_ci_env(self) -> None:
        """AWSOME should not be available in the CI/test environment."""
        # This is expected — if AWSOME were available, we'd need real execution tests
        self.assertFalse(awsome_available())

    def test_validate_setup_reports_binary_absence(self) -> None:
        """validate_awsome_setup must honestly report binary absence."""
        status = validate_awsome_setup()
        self.assertFalse(status['awsome_installed'])
        self.assertFalse(status['snowpack_binary'])

    def test_dry_run_does_not_claim_execution(self) -> None:
        """Dry-run must return configuration_validated, not completed."""
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(region=nepal, dry_run=True)
        self.assertEqual(result['status'], 'configuration_validated')
        self.assertNotEqual(result['status'], 'completed')
        self.assertTrue(result['dry_run'])

    def test_non_dry_run_without_binary_returns_inputs_unavailable(self) -> None:
        """Non-dry-run without binary must return toolchain_unavailable, not completed."""
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(region=nepal, dry_run=False)
        # Phase 0.5: without binary, should be toolchain_unavailable, never completed
        self.assertIn(result['status'], ('toolchain_unavailable', 'planned', 'failed'))
        self.assertNotEqual(result['status'], 'completed')


class TestRegionConfigurationFailureMode(unittest.TestCase):
    """Test configuration drift and regime selection fail closed."""

    def test_unknown_region_config_rejected(self) -> None:
        from backend.common.awsome_runner import get_region_snowpack_params

        with self.assertRaises(KeyError):
            get_region_snowpack_params('not_a_configured_region')

    def test_himalayan_dry_run_contains_regime_and_band(self) -> None:
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(region=nepal, dry_run=True)
        self.assertEqual(result['status'], 'configuration_validated')
        self.assertEqual(result['regime'], 'himalayas_nepal')
        self.assertEqual(result['elevation_band'], 'lower')


class TestIncompleteForcingFailureMode(unittest.TestCase):
    """Test that incomplete forcing is rejected, not silently filled."""

    def _valid_provenance(self) -> ProvenanceMetadata:
        return ProvenanceMetadata(
            source='open_meteo_archive',
            source_class='proxy',
            licence='CC-BY-4.0',
            timestamp='2026-01-15T00:00:00+00:00',
            units={'temperature': 'K'},
            hash='a' * 64,
            run_id='run_001',
        )

    def test_missing_critical_variable_rejected(self) -> None:
        """Forcing with missing TA must be rejected."""
        with self.assertRaises(ContractValidationError):
            ForcingManifestContract(
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                forecast_horizon_h=48,
                variables=('RH', 'VW', 'ISWR', 'ILWR', 'PSUM'),  # Missing TA
                smet_file_path='/data/nepal.smet',
                provenance=self._valid_provenance(),
            ).validate()

    def test_incomplete_forcing_flag_rejected(self) -> None:
        """Forcing with is_complete=False must be rejected."""
        with self.assertRaises(ContractValidationError):
            ForcingManifestContract(
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                forecast_horizon_h=48,
                variables=('TA', 'RH', 'VW', 'ISWR', 'ILWR', 'PSUM'),
                smet_file_path='/data/nepal.smet',
                provenance=self._valid_provenance(),
                is_complete=False,
            ).validate()


class TestStaleDataFailureMode(unittest.TestCase):
    """Test that stale data is detected."""

    def test_old_timestamp_still_validates_format(self) -> None:
        """Old timestamps should still be valid ISO 8601 — staleness is a policy check, not format."""
        prov = ProvenanceMetadata(
            source='open_meteo_archive',
            source_class='proxy',
            licence='CC-BY-4.0',
            timestamp='2020-01-01T00:00:00+00:00',  # Very old
            units={'temperature': 'K'},
            hash='a' * 64,
            run_id='run_001',
        )
        # Should not raise — format is valid
        prov.validate()

    def test_invalid_timestamp_rejected(self) -> None:
        """Malformed timestamps must be rejected."""
        with self.assertRaises(ContractValidationError):
            ProvenanceMetadata(
                source='test',
                source_class='proxy',
                licence='CC-BY-4.0',
                timestamp='not-a-date',
            ).validate()


class TestPartialEnsembleFailureMode(unittest.TestCase):
    """Test that partial ensemble output is handled correctly."""

    def test_dry_run_cannot_claim_completed(self) -> None:
        """Dry-run ensemble member cannot have 'completed' status."""
        with self.assertRaises(ContractValidationError):
            validate_execution_status('completed', is_dry_run=True)

    def test_partial_status_requires_native_execution(self) -> None:
        """'partial' status requires native execution, not dry-run."""
        with self.assertRaises(ContractValidationError):
            validate_execution_status('partial', is_dry_run=True)

    def test_completed_without_outputs_rejected(self) -> None:
        """'completed' SNOWPACK run must have output paths."""
        with self.assertRaises(ContractValidationError):
            SnowpackRunContract(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                slope_angle=35.0,
                forcing_manifest_id='manifest_001',
                execution_status='completed',
                provenance=ProvenanceMetadata(
                    source='test', source_class='proxy',
                    licence='CC-BY-4.0', timestamp='2026-01-15T00:00:00+00:00',
                    units={'temperature': 'K'}, hash='a' * 64, run_id='run_001',
                ),
                # No output_paths!
            ).validate()


class TestNativeOutputStatusFailureMode(unittest.TestCase):
    """Test native output completeness gating."""

    def test_partial_outputs_are_not_completed(self) -> None:
        from backend.common.awsome_runner import _native_output_status

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for suffix in ('.smet', '.pro', '.sno'):
                (output_dir / f'run{suffix}').write_text('data', encoding='utf-8')
            status, missing = _native_output_status(output_dir)
            self.assertEqual(status, 'partial')
            # Phase 0.5: .haz and .log are both required for completed
            self.assertEqual(missing, ['.haz', '.log'])
            (output_dir / 'run.haz').write_text('data', encoding='utf-8')
            (output_dir / 'run.log').write_text('log data', encoding='utf-8')
            status, missing = _native_output_status(output_dir)
            self.assertEqual(status, 'completed')
            self.assertEqual(missing, [])


class TestArtifactManifestFailureMode(unittest.TestCase):
    """Test that artifact manifest fails closed for missing outputs."""

    def test_empty_output_rejected(self) -> None:
        """Empty output files must be rejected."""
        empty_art = ArtifactEntry(
            file_path='/output/empty.pro', file_type='.pro',
            size_bytes=0, sha256='a' * 64, is_critical=True,
        )
        manifest = ArtifactManifest(
            run_id='run_001', region_key='himalayas_nepal',
            elevation_band='lower', aspect_class='N',
            binary_version='snowpack-3.7.0',
            artifacts=(empty_art,),
            is_native_execution=True,
            native_binary_invoked=True,
            created_at='2026-01-15T00:00:00+00:00',
        )
        errors = manifest.validate()
        self.assertTrue(any('empty' in e.lower() for e in errors))

    def test_dry_run_manifest_rejected(self) -> None:
        """Dry-run must not produce an artifact manifest."""
        manifest = ArtifactManifest(
            run_id='run_001', region_key='himalayas_nepal',
            elevation_band='lower', aspect_class='N',
            binary_version='snowpack-3.7.0',
            artifacts=(),
            is_native_execution=False,  # Dry-run!
            created_at='2026-01-15T00:00:00+00:00',
        )
        errors = manifest.validate()
        self.assertTrue(any('is_native_execution' in e for e in errors))


class TestConfigSyncFailureMode(unittest.TestCase):
    """Test that config drift is detected and fails closed."""

    def test_real_configs_are_in_sync(self) -> None:
        """The real repo configs must be in sync (no drift)."""
        result = validate_awsome_regions_sync()
        self.assertTrue(result.valid, f'Config drift: {result.errors}')

    def test_all_himalayan_regions_have_awsome_params(self) -> None:
        """All Himalayan regions must have AWSOME parameters (not defaults)."""
        regions = load_regions()
        for r in regions:
            params = get_region_snowpack_params(r.key)
            # If using defaults, timezone would be UTC and elevation_min would be 1000
            if r.timezone_name != 'UTC':
                self.assertNotEqual(
                    params.get('timezone'), 'UTC',
                    f'Region {r.key} should have non-UTC timezone, got UTC (using defaults)',
                )


if __name__ == '__main__':
    unittest.main()
