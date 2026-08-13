"""Phase 0.5 false-green closure tests.

Tests that the pipeline fails closed (not silently) for:
  - Stale output files creating false 'completed' status
  - Missing manifest rejection
  - Hash tampering detection
  - Fake executable not counting as native evidence
  - Fallback forbidden in acceptance mode
  - Incomplete forcing and invalid time sequences
  - Band-elevation selection (Nepal lower uses band elevation, not region max)

Per codex audit Phase 0.5:
  - Every "green" path needs one test that fails on stale artifacts
  - Every "green" path needs one test that fails on fixture-as-native
  - The current environment must remain explicitly blocked, not falsely green.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.common.awsome_runner import (
    _band_elevation_midpoint,
    _clean_output_directory,
    _native_output_status,
    _representative_site_fixture,
    get_region_snowpack_params,
    run_awsome_for_region,
)
from backend.common.himalayan_regimes import get_regime
from backend.common.meteoio_openmeteo import (
    generate_snowpack_config,
    validate_smet_samples,
)
from backend.common.regions import load_regions
from backend.common.snowpack_artifact_manifest import (
    ArtifactEntry,
    ArtifactManifest,
    build_manifest_from_directory,
    compute_file_hash,
    is_clean_output_directory,
    manifest_to_json,
    verify_manifest_against_directory,
)
from backend.common.snowpack_contracts import (
    COMPLETED_REQUIRED_OUTPUT_SUFFIXES,
    ContractValidationError,
    ProvenanceMetadata,
    SnowpackRunContract,
    validate_completed_status,
    validate_execution_status,
)


_MINIMAL_SMET_WITH_COORDINATES = (
    'SMET 1.1 ASCII\n'
    '[HEADER]\n'
    'station_id = input\n'
    'latitude = 33.5\n'
    'longitude = 74.0\n'
    'altitude = 3500\n'
    '[DATA]\n'
)


class TestStaleOutputRejection(unittest.TestCase):
    """Test that stale output files cannot create a false 'completed' status."""

    def test_stale_files_in_output_dir_are_cleaned(self) -> None:
        """_clean_output_directory must remove stale files before a run."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / 'output'
            output_dir.mkdir()
            # Create stale files from a previous run
            (output_dir / 'stale.pro').write_text('stale profile', encoding='utf-8')
            (output_dir / 'stale.sno').write_text('stale snow', encoding='utf-8')
            (output_dir / 'stale.haz').write_text('stale hazard', encoding='utf-8')

            # Clean the directory
            _clean_output_directory(output_dir)

            # Directory should be empty
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_is_clean_output_directory_detects_stale_files(self) -> None:
        """is_clean_output_directory must detect stale files."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / 'output'
            output_dir.mkdir()
            (output_dir / 'stale.pro').write_text('stale', encoding='utf-8')

            # Not clean — has stale file
            self.assertFalse(is_clean_output_directory(output_dir))

            # Clean after removing stale file
            (output_dir / 'stale.pro').unlink()
            self.assertTrue(is_clean_output_directory(output_dir))

    def test_stale_suffixes_do_not_create_completed(self) -> None:
        """Stale files with expected suffixes must not create false completed."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            # Create stale files with ALL required suffixes
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (output_dir / f'stale{suffix}').write_text('stale data', encoding='utf-8')

            # Clean first, then verify empty
            _clean_output_directory(output_dir)
            self.assertEqual(list(output_dir.iterdir()), [])

            # Now _native_output_status should fail (no files)
            status, missing = _native_output_status(output_dir)
            self.assertEqual(status, 'partial')
            self.assertTrue(len(missing) > 0)

    def test_symlinked_output_directory_is_rejected_by_cleaner(self) -> None:
        """C0.13: Cleaner must not follow a symlinked output directory."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_dir = root / 'real-output'
            real_dir.mkdir()
            (real_dir / 'stale.pro').write_text('must remain', encoding='utf-8')
            symlink_dir = root / 'output'
            symlink_dir.symlink_to(real_dir)

            with self.assertRaises(Exception):
                _clean_output_directory(symlink_dir)
            self.assertEqual((real_dir / 'stale.pro').read_text(encoding='utf-8'), 'must remain')

    def test_symlinked_artifact_is_not_counted_as_native_output(self) -> None:
        """C0.13: Status must not count symlink targets as native outputs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / 'output'
            output_dir.mkdir()
            external = root / 'external.pro'
            external.write_text('external profile', encoding='utf-8')
            (output_dir / 'run.pro').symlink_to(external)

            status, missing = _native_output_status(output_dir)
            self.assertEqual(status, 'partial')
            self.assertIn('.pro', missing)

    def test_manifest_builder_excludes_symlink_artifact(self) -> None:
        """C0.13: Manifest discovery must not hash symlink targets."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / 'output'
            output_dir.mkdir()
            external = root / 'external.pro'
            external.write_text('external profile', encoding='utf-8')
            (output_dir / 'run.pro').symlink_to(external)

            manifest = build_manifest_from_directory(
                run_id='run_001', region_key='himalayas_nepal',
                elevation_band='lower', aspect_class='N',
                binary_version='snowpack-3.7.0', output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00', native_binary_invoked=True,
            )
            self.assertEqual(manifest.artifacts, ())


class TestMissingManifestRejection(unittest.TestCase):
    """Test that missing manifest validation prevents false completed."""

    def test_manifest_not_set_is_not_native(self) -> None:
        """A manifest with is_native_execution=False is rejected."""
        manifest = ArtifactManifest(
            run_id='run_001', region_key='himalayas_nepal',
            elevation_band='lower', aspect_class='N',
            binary_version='snowpack-3.7.0',
            artifacts=(),
            is_native_execution=False,
            created_at='2026-01-15T00:00:00+00:00',
        )
        errors = manifest.validate()
        self.assertTrue(any('is_native_execution' in e for e in errors))

    def test_suffix_presence_alone_is_not_native_evidence(self) -> None:
        """A directory with expected suffixes but no native_binary_invoked is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (output_dir / f'run{suffix}').write_text('data', encoding='utf-8')

            # Build manifest WITHOUT native_binary_invoked
            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=False,  # Key: suffixes alone don't prove native
            )
            errors = manifest.validate()
            self.assertTrue(any('native_binary_invoked' in e for e in errors))


class TestHashTampering(unittest.TestCase):
    """Test that hash tampering is detected by manifest verification."""

    def test_hash_mismatch_detected(self) -> None:
        """verify_manifest_against_directory must detect hash mismatches."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / 'run.pro').write_text('original content', encoding='utf-8')

            # Build manifest
            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
            )

            # Tamper with the file after manifest creation
            (output_dir / 'run.pro').write_text('tampered content', encoding='utf-8')

            # Verification should detect the hash mismatch
            discrepancies = verify_manifest_against_directory(manifest, output_dir)
            self.assertTrue(any('hash mismatch' in d.lower() for d in discrepancies))

    def test_size_mismatch_detected(self) -> None:
        """verify_manifest_against_directory must detect size mismatches."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / 'run.pro').write_text('original', encoding='utf-8')

            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
            )

            # Change file size without changing hash (append same content)
            (output_dir / 'run.pro').write_text('original but longer', encoding='utf-8')

            discrepancies = verify_manifest_against_directory(manifest, output_dir)
            self.assertTrue(
                any('size mismatch' in d.lower() or 'hash mismatch' in d.lower() for d in discrepancies)
            )

    def test_unexpected_file_in_directory_detected(self) -> None:
        """verify_manifest_against_directory must detect unexpected stale files."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / 'run.pro').write_text('profile', encoding='utf-8')

            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
            )

            # Add an unexpected file after manifest creation
            (output_dir / 'stale.sno').write_text('stale snow', encoding='utf-8')

            discrepancies = verify_manifest_against_directory(manifest, output_dir)
            self.assertTrue(any('stale' in d.lower() or 'not in manifest' in d.lower() for d in discrepancies))


class TestFakeExecutableNotNativeEvidence(unittest.TestCase):
    """Test that a fake executable does not count as native evidence in acceptance mode."""

    def test_fake_binary_produces_partial_not_completed(self) -> None:
        """A fake binary that produces only .pro must remain partial."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            fake_binary = bin_dir / 'snowpack'
            # Fake binary produces only .pro. The wrapper's captured log is
            # present, but the required native .sno/.haz/.smet artifacts are
            # still absent.
            fake_binary.write_text(
                '#!/bin/sh\n'
                'config=""\n'
                'previous=""\n'
                'for arg in "$@"; do\n'
                '  if [ "$previous" = "-c" ]; then config="$arg"; fi\n'
                '  previous="$arg"\n'
                'done\n'
                'printf "native profile\\n" > "$(dirname "$config")/input.pro"\n',
                encoding='utf-8',
            )
            fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)

            smet = root / 'input.smet'
            smet.write_text(_MINIMAL_SMET_WITH_COORDINATES, encoding='utf-8')
            output_dir = root / 'output'

            old_path = os.environ.get('PATH', '')
            os.environ['PATH'] = f'{bin_dir}{os.pathsep}{old_path}'
            try:
                from backend.common.meteoio_openmeteo import run_snowpack_native
                result = run_snowpack_native(
                    smet_path=smet,
                    output_dir=output_dir,
                )
            finally:
                os.environ['PATH'] = old_path

            # The fake binary produced .pro, but not .sno/.haz/.log
            self.assertIsNotNone(result)
            status, missing = _native_output_status(output_dir)
            self.assertEqual(status, 'partial')
            self.assertIn('.sno', missing)
            self.assertIn('.haz', missing)
            self.assertIn('.smet', missing)
            self.assertNotIn('.log', missing)


class TestFallbackForbiddenInAcceptanceMode(unittest.TestCase):
    """Test that fallback is forbidden in acceptance mode (no_fallback=true)."""

    def test_no_fallback_parameter_is_carried_in_result(self) -> None:
        """The no_fallback parameter must be carried in the result metadata."""
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(
            region=nepal,
            dry_run=True,
            no_fallback=True,
            engine='snowpack_direct',
            run_id='dry-run-acceptance',
            toolchain_manifest_id='tc_001',
            forcing_manifest_id='fm_001',
            geometry_manifest_id='gm_001',
        )
        self.assertTrue(result['no_fallback'])
        self.assertEqual(result['toolchain_manifest_id'], 'tc_001')
        self.assertEqual(result['forcing_manifest_id'], 'fm_001')
        self.assertEqual(result['geometry_manifest_id'], 'gm_001')

    def test_completed_status_requires_no_fallback(self) -> None:
        """validate_completed_status must reject completed when no_fallback=False."""
        violations = validate_completed_status(
            native_binary_invoked=True,
            output_dir_is_clean=True,
            output_suffixes_present={'smet', 'pro', 'sno', 'haz', 'log'},
            manifest_validated=True,
            has_hash_verification=True,
            no_fallback=False,  # Fallback was used!
            toolchain_id='tc_001',
            forcing_manifest_id='fm_001',
            geometry_manifest_id='gm_001',
            run_id='run_001',
        )
        self.assertTrue(any('fallback' in v.lower() for v in violations))

    def test_completed_status_requires_all_identifiers(self) -> None:
        """validate_completed_status must reject completed when identifiers are missing."""
        violations = validate_completed_status(
            native_binary_invoked=True,
            output_dir_is_clean=True,
            output_suffixes_present={'smet', 'pro', 'sno', 'haz', 'log'},
            manifest_validated=True,
            has_hash_verification=True,
            no_fallback=True,
            toolchain_id='',  # Missing!
            forcing_manifest_id='fm_001',
            geometry_manifest_id='gm_001',
            run_id='run_001',
        )
        self.assertTrue(any('toolchain' in v.lower() for v in violations))

    def test_completed_status_requires_clean_output_dir(self) -> None:
        """validate_completed_status must reject completed when output dir is not clean."""
        violations = validate_completed_status(
            native_binary_invoked=True,
            output_dir_is_clean=False,  # Stale files!
            output_suffixes_present={'smet', 'pro', 'sno', 'haz', 'log'},
            manifest_validated=True,
            has_hash_verification=True,
            no_fallback=True,
            toolchain_id='tc_001',
            forcing_manifest_id='fm_001',
            geometry_manifest_id='gm_001',
            run_id='run_001',
        )
        self.assertTrue(any('clean' in v.lower() or 'stale' in v.lower() for v in violations))

    def test_completed_status_requires_all_output_suffixes(self) -> None:
        """validate_completed_status must reject completed when output suffixes are missing."""
        violations = validate_completed_status(
            native_binary_invoked=True,
            output_dir_is_clean=True,
            output_suffixes_present={'smet', 'pro', 'sno'},  # Missing .haz, .log!
            manifest_validated=True,
            has_hash_verification=True,
            no_fallback=True,
            toolchain_id='tc_001',
            forcing_manifest_id='fm_001',
            geometry_manifest_id='gm_001',
            run_id='run_001',
        )
        self.assertTrue(any('missing' in v.lower() for v in violations))

    def test_completed_status_passes_with_all_requirements(self) -> None:
        """validate_completed_status must pass when all requirements are met."""
        violations = validate_completed_status(
            native_binary_invoked=True,
            output_dir_is_clean=True,
            output_suffixes_present={'.smet', '.pro', '.sno', '.haz', '.log'},
            manifest_validated=True,
            has_hash_verification=True,
            no_fallback=True,
            toolchain_id='tc_001',
            forcing_manifest_id='fm_001',
            geometry_manifest_id='gm_001',
            run_id='run_001',
        )
        self.assertEqual(violations, [])


class TestIncompleteForcingAndTimeSequences(unittest.TestCase):
    """Test that incomplete forcing and invalid time sequences are rejected."""

    def _valid_sample(self, time: str = '2026-01-15T00:00:00') -> dict:
        return {
            'time': time,
            'temperature_2m': -5.0,
            'relative_humidity_2m': 80.0,
            'windspeed_10m': 5.0,
            'shortwave_radiation': 200.0,
            'precipitation': 1.5,
            'cloud_cover': 50.0,
        }

    def test_incomplete_forcing_missing_shortwave_rejected(self) -> None:
        """Forcing missing shortwave radiation must be rejected."""
        sample = self._valid_sample()
        del sample['shortwave_radiation']
        sample.pop('reflected_shortwave_radiation', None)
        sample.pop('net_shortwave_radiation', None)
        with self.assertRaises(ValueError) as ctx:
            validate_smet_samples([sample], strict=True)
        self.assertIn('ISWR', str(ctx.exception))

    def test_incomplete_forcing_missing_precipitation_rejected(self) -> None:
        """Forcing missing precipitation must be rejected."""
        sample = self._valid_sample()
        del sample['precipitation']
        # Also remove any alternative precipitation keys if present
        sample.pop('snowfall', None)
        sample.pop('snow_depth', None)
        with self.assertRaises(ValueError) as ctx:
            validate_smet_samples([sample], strict=True)
        self.assertIn('PSUM', str(ctx.exception))

    def test_non_monotonic_time_sequence_rejected(self) -> None:
        """Non-monotonic timestamps must be rejected."""
        samples = [
            self._valid_sample('2026-01-15T02:00:00'),
            self._valid_sample('2026-01-15T01:00:00'),  # Goes backwards!
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_smet_samples(samples, strict=True)
        self.assertIn('non-monotonic', str(ctx.exception).lower())

    def test_duplicate_timestamps_rejected(self) -> None:
        """Duplicate timestamps must be rejected."""
        samples = [
            self._valid_sample('2026-01-15T01:00:00'),
            self._valid_sample('2026-01-15T01:00:00'),  # Duplicate!
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_smet_samples(samples, strict=True)
        self.assertIn('duplicate', str(ctx.exception).lower())

    def test_valid_monotonic_sequence_accepted(self) -> None:
        """A valid monotonic time sequence must be accepted."""
        samples = [
            self._valid_sample('2026-01-15T00:00:00'),
            self._valid_sample('2026-01-15T01:00:00'),
            self._valid_sample('2026-01-15T02:00:00'),
        ]
        validate_smet_samples(samples, strict=True)  # Should not raise


class TestBandElevationSelection(unittest.TestCase):
    """Test that the selected Himalayan band drives actual elevation, not region max."""

    def test_nepal_lower_band_uses_band_elevation_not_region_max(self) -> None:
        """Nepal 'lower' band (3500-4200m) must not use region elevation_max (5500m)."""
        regime = get_regime('himalayas_nepal')
        self.assertIsNotNone(regime)
        lower_band = regime.get_band('lower')
        self.assertIsNotNone(lower_band)

        midpoint = _band_elevation_midpoint(lower_band)
        # Lower band is 3500-4200m, midpoint is 3850m
        self.assertAlmostEqual(midpoint, 3850.0, delta=1.0)
        # Must NOT be 5500m (region elevation_max)
        self.assertNotAlmostEqual(midpoint, 5500.0, delta=100.0)

    def test_nepal_upper_band_uses_band_elevation(self) -> None:
        """Nepal 'upper' band (5000-5500m) must use band elevation."""
        regime = get_regime('himalayas_nepal')
        upper_band = regime.get_band('upper')
        self.assertIsNotNone(upper_band)

        midpoint = _band_elevation_midpoint(upper_band)
        # Upper band is 5000-5500m, midpoint is 5250m
        self.assertAlmostEqual(midpoint, 5250.0, delta=1.0)

    def test_representative_site_fixture_uses_band_elevation(self) -> None:
        """The representative site fixture must use band elevation, not region max."""
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        regime = get_regime('himalayas_nepal')
        lower_band = regime.get_band('lower')
        params = get_region_snowpack_params('himalayas_nepal')

        fixture = _representative_site_fixture(nepal, lower_band, params)

        # Fixture elevation must be band midpoint (3850m), not region max (5500m)
        self.assertAlmostEqual(fixture['elevation_m'], 3850.0, delta=1.0)
        self.assertNotAlmostEqual(fixture['elevation_m'], 5500.0, delta=100.0)
        # Must be labeled candidate-only
        self.assertTrue(fixture['candidate_only'])
        self.assertEqual(fixture['band_elevation_min_m'], 3500)
        self.assertEqual(fixture['band_elevation_max_m'], 4200)

    def test_dry_run_carries_band_elevation_in_site_fixture(self) -> None:
        """Dry-run result must carry the band-specific site fixture."""
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(
            region=nepal,
            dry_run=True,
            elevation_band='lower',
        )
        self.assertEqual(result['status'], 'configuration_validated')
        self.assertEqual(result['elevation_band'], 'lower')
        fixture = result['site_fixture']
        self.assertAlmostEqual(fixture['elevation_m'], 3850.0, delta=1.0)
        self.assertTrue(fixture['candidate_only'])


class TestStatusVocabularyExpansion(unittest.TestCase):
    """Test Phase 0.5 status vocabulary expansion."""

    def test_toolchain_unavailable_is_valid_status(self) -> None:
        """toolchain_unavailable must be a valid execution status."""
        validate_execution_status('toolchain_unavailable')  # Should not raise

    def test_native_running_is_valid_status(self) -> None:
        """native_running must be a valid execution status."""
        validate_execution_status('native_running')  # Should not raise

    def test_fallback_proxy_is_valid_status(self) -> None:
        """fallback_proxy must be a valid execution status."""
        validate_execution_status('fallback_proxy')  # Should not raise

    def test_toolchain_unavailable_allowed_for_dry_run(self) -> None:
        """toolchain_unavailable must be allowed for dry-run paths."""
        validate_execution_status('toolchain_unavailable', is_dry_run=True)  # Should not raise

    def test_fallback_proxy_allowed_for_dry_run(self) -> None:
        """fallback_proxy must be allowed for dry-run paths."""
        validate_execution_status('fallback_proxy', is_dry_run=True)  # Should not raise

    def test_native_running_prohibited_for_dry_run(self) -> None:
        """native_running must be prohibited for dry-run paths."""
        with self.assertRaises(ContractValidationError):
            validate_execution_status('native_running', is_dry_run=True)

    def test_non_dry_run_returns_toolchain_unavailable(self) -> None:
        """Non-dry-run without binary must return toolchain_unavailable, not skipped."""
        regions = load_regions()
        nepal = next(r for r in regions if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(region=nepal, dry_run=False)
        self.assertEqual(result['status'], 'toolchain_unavailable')


class TestCompletedStatusStrictRequirements(unittest.TestCase):
    """Test that 'completed' status has strict Phase 0.5 requirements."""

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

    def test_completed_requires_binary_version(self) -> None:
        """'completed' SnowpackRunContract must have binary_version."""
        with self.assertRaises(ContractValidationError):
            SnowpackRunContract(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                slope_angle=35.0,
                forcing_manifest_id='manifest_001',
                execution_status='completed',
                provenance=self._valid_provenance(),
                output_paths=('/output/run_001.pro',),
                # Missing binary_version!
            ).validate()

    def test_completed_with_binary_version_accepted(self) -> None:
        """'completed' with binary_version and output_paths must be accepted."""
        SnowpackRunContract(
            run_id='run_001',
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
            slope_angle=35.0,
            forcing_manifest_id='manifest_001',
            execution_status='completed',
            provenance=self._valid_provenance(),
            output_paths=('/output/run_001.pro',),
            binary_version='snowpack-3.7.0',
        ).validate()

    def test_completed_requires_forcing_manifest_id(self) -> None:
        """'completed' SnowpackRunContract must have forcing_manifest_id."""
        with self.assertRaises(ContractValidationError):
            SnowpackRunContract(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                slope_angle=35.0,
                forcing_manifest_id='',  # Empty!
                execution_status='completed',
                provenance=self._valid_provenance(),
                output_paths=('/output/run_001.pro',),
                binary_version='snowpack-3.7.0',
            ).validate()


class TestProcessedMeteoConfigOutput(unittest.TestCase):
    """Test that generate_snowpack_config requests processed-meteorology output."""

    def test_config_uses_official_paths_and_output_layout(self) -> None:
        """The generated INI must match the native SNOWPACK 3.7 contract."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / 'snowpack.ini'
            input_dir = root / 'input'
            output_dir = root / 'output'
            generate_snowpack_config(
                output_path=config_path,
                season_start_date='2025-11-01',
                end_date='2026-01-15',
                station_id='pir_panjal_mid',
                latitude=33.5,
                longitude=74.0,
                meteo_path=input_dir,
                output_dir=output_dir,
                experiment='poc',
            )
            content = config_path.read_text(encoding='utf-8')
            self.assertIn('COORDSYS = UTM', content)
            self.assertIn('COORDPARAM = 43S', content)
            self.assertIn(f'METEOPATH = {input_dir.resolve()}', content)
            self.assertIn('STATION1 = pir_panjal_mid', content)
            self.assertIn(f'METEOPATH = {output_dir.resolve()}', content)
            self.assertIn('EXPERIMENT = poc', content)
            self.assertIn('SNOW_WRITE = TRUE', content)
            self.assertNotIn('[Time]', content)
            self.assertNotIn('TIMEZONE =', content)
            self.assertNotRegex(content, r'(?m)^START\s*=')
            self.assertNotRegex(content, r'(?m)^END\s*=')

    def test_config_rejects_missing_coordinates(self) -> None:
        """Native config generation must not guess a projection zone."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'latitude and longitude'):
                generate_snowpack_config(
                    output_path=Path(tmp) / 'snowpack.ini',
                    season_start_date='2025-11-01',
                    end_date='2026-01-15',
                )

    def test_config_includes_processed_meteo_output(self) -> None:
        """generate_snowpack_config must include processed-meteo output directives."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'snowpack.ini'
            generate_snowpack_config(
                output_path=config_path,
                season_start_date='2025-11-01',
                end_date='2026-01-15',
                latitude=33.5,
                longitude=74.0,
            )
            content = config_path.read_text(encoding='utf-8')
            # SNOWPACK's documented output keys must be used. The previous
            # aliases were not verified against the native configuration.
            self.assertIn('WRITE_PROCESSED_METEO = TRUE', content)
            self.assertIn('PROF_FORMAT = PRO', content)
            self.assertIn('PROF_WRITE = TRUE', content)
            self.assertIn('OUT_HAZ = TRUE', content)
            self.assertIn('OUT_METEO = TRUE', content)
            self.assertIn('TS_WRITE = TRUE', content)
            self.assertIn('TS_FORMAT = SMET', content)
            self.assertIn('MEAS_TSS = FALSE', content)
            self.assertNotIn('METEO_OUT', content)
            self.assertNotIn('SNOW_PROFILE', content)
            self.assertNotIn('HAZARD =', content)

    def test_config_binds_profile_initial_state_format(self) -> None:
        """Profile initialization must select the documented SNOW plugin."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'snowpack.ini'
            profile_path = Path(tmp) / 'initial.caaml'
            generate_snowpack_config(
                output_path=config_path,
                season_start_date='2025-11-01',
                end_date='2026-01-15',
                initial_state_path=profile_path,
                latitude=33.5,
                longitude=74.0,
            )
            content = config_path.read_text(encoding='utf-8')
            self.assertIn('SNOW = CAAML', content)
            self.assertIn(f'SNOWPATH = {profile_path.parent.resolve()}', content)
            self.assertIn(f'SNOWFILE1 = {profile_path.name}', content)

    def test_config_rejects_unknown_initial_state_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate_snowpack_config(
                    output_path=Path(tmp) / 'snowpack.ini',
                    season_start_date='2025-11-01',
                    end_date='2026-01-15',
                    initial_state_path=Path(tmp) / 'initial.txt',
                    latitude=33.5,
                    longitude=74.0,
                )

    def test_config_binds_sno_initial_state_to_smet_plugin(self) -> None:
        """SNOWPACK .sno profiles use the SMET snow-profile plugin."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / 'snowpack.ini'
            profile_path = Path(tmp) / 'initial.sno'
            generate_snowpack_config(
                output_path=config_path,
                season_start_date='2025-11-01',
                end_date='2026-01-15',
                initial_state_path=profile_path,
                latitude=33.5,
                longitude=74.0,
            )
            content = config_path.read_text(encoding='utf-8')
            self.assertIn('SNOW = SMET', content)
            self.assertIn(f'SNOWFILE1 = {profile_path.name}', content)


class TestManifestCompletedValidation(unittest.TestCase):
    """Test that manifest.validate_completed() enforces strict completed requirements."""

    def test_completed_requires_log_file(self) -> None:
        """validate_completed must require .log in addition to .smet/.pro/.sno/.haz."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for suffix in ('.smet', '.pro', '.sno', '.haz'):
                (output_dir / f'run{suffix}').write_text('data', encoding='utf-8')
            # No .log file!

            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
                toolchain_id='tc_001',
                forcing_manifest_id='fm_001',
                geometry_manifest_id='gm_001',
            )
            errors = manifest.validate_completed()
            self.assertTrue(any('.log' in e for e in errors))

    def test_completed_requires_linked_identifiers(self) -> None:
        """validate_completed must require toolchain, forcing, and geometry IDs."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (output_dir / f'run{suffix}').write_text('data', encoding='utf-8')
            (output_dir / 'processed-meteo.smet').write_text('processed', encoding='utf-8')

            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
                # Missing toolchain_id, forcing_manifest_id, geometry_manifest_id!
            )
            errors = manifest.validate_completed()
            self.assertTrue(any('toolchain_id' in e for e in errors))
            self.assertTrue(any('forcing_manifest_id' in e for e in errors))
            self.assertTrue(any('geometry_manifest_id' in e for e in errors))

    def test_completed_passes_with_all_requirements(self) -> None:
        """validate_completed must pass when all requirements are met."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for suffix in ('.smet', '.pro', '.sno', '.haz', '.log'):
                (output_dir / f'run{suffix}').write_text('data', encoding='utf-8')
            (output_dir / 'processed-meteo.smet').write_text('processed', encoding='utf-8')

            manifest = build_manifest_from_directory(
                run_id='run_001',
                region_key='himalayas_nepal',
                elevation_band='lower',
                aspect_class='N',
                binary_version='snowpack-3.7.0',
                output_dir=output_dir,
                created_at='2026-01-15T00:00:00+00:00',
                native_binary_invoked=True,
                toolchain_id='tc_001',
                forcing_manifest_id='fm_001',
                geometry_manifest_id='gm_001',
            )
            errors = manifest.validate_completed()
            self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
