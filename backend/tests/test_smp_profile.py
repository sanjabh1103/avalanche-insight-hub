"""Tests for SMP profile preservation (Phase 7-prep)."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.common.smp_profile import (
    SMPDerivedLayer,
    SMPProfile,
    SMPInputUnavailable,
    SMPRawLineage,
    SMPSample,
    align_smp_to_snowpack_depth,
    ingest_smp_profile_files,
)


def _valid_layer(**overrides) -> SMPDerivedLayer:
    defaults = dict(
        depth_mm=100.0,
        thickness_mm=10.0,
        density_kgm3=300.0,
        density_uncertainty=30.0,
        ssa_m2_kg=15.0,
        ssa_uncertainty=3.0,
        grain_type_estimate='faceted',
        grain_type_confidence=0.7,
    )
    defaults.update(overrides)
    return SMPDerivedLayer(**defaults)


def _valid_profile(**overrides) -> SMPProfile:
    defaults = dict(
        profile_id='smp_001',
        station_id='station_01',
        latitude=28.0,
        longitude=86.25,
        elevation_m=4000.0,
        timestamp='2026-01-15T00:00:00+00:00',
        snow_depth_mm=500.0,
        device_serial='SMP5-001',
        operator='test_operator',
        processing_version='snowmicropyn-v2',
        raw_samples=(
            SMPSample(depth_mm=0.0, force_n=0.01),
            SMPSample(depth_mm=100.0, force_n=0.15),
            SMPSample(depth_mm=200.0, force_n=0.30),
        ),
        derived_layers=(_valid_layer(), _valid_layer(depth_mm=200.0)),
        depth_reference='ground',
    )
    defaults.update(overrides)
    return SMPProfile(**defaults)


class TestSMPProfileValidation(unittest.TestCase):
    """Test SMP profile validation."""

    def test_valid_profile_accepted(self) -> None:
        errors = _valid_profile().validate()
        self.assertEqual(errors, [])

    def test_missing_profile_id_rejected(self) -> None:
        errors = _valid_profile(profile_id='').validate()
        self.assertTrue(any('profile_id' in e for e in errors))

    def test_missing_device_serial_rejected(self) -> None:
        errors = _valid_profile(device_serial='').validate()
        self.assertTrue(any('device_serial' in e for e in errors))

    def test_zero_snow_depth_rejected(self) -> None:
        errors = _valid_profile(snow_depth_mm=0).validate()
        self.assertTrue(any('snow_depth_mm' in e for e in errors))

    def test_invalid_timestamp_rejected(self) -> None:
        errors = _valid_profile(timestamp='not-a-date').validate()
        self.assertTrue(any('timestamp' in e for e in errors))

    def test_naive_timestamp_rejected(self) -> None:
        errors = _valid_profile(timestamp='2026-01-15T00:00:00').validate()
        self.assertTrue(any('timezone-aware UTC' in e for e in errors))

    def test_non_string_timestamp_rejected(self) -> None:
        errors = _valid_profile(timestamp=123).validate()  # type: ignore[arg-type]
        self.assertTrue(any('timestamp' in e for e in errors))

    def test_sample_outside_snow_depth_rejected(self) -> None:
        errors = _valid_profile(
            raw_samples=(SMPSample(depth_mm=600.0, force_n=0.1),)
        ).validate()
        self.assertTrue(any('raw sample' in e.lower() for e in errors))

    def test_zero_uncertainty_rejected(self) -> None:
        """Derived layers must have uncertainty."""
        layer = _valid_layer(density_uncertainty=0.0)
        errors = _valid_profile(derived_layers=(layer,)).validate()
        self.assertTrue(any('uncertainty' in e for e in errors))

    def test_out_of_range_confidence_rejected(self) -> None:
        layer = _valid_layer(grain_type_confidence=1.5)
        errors = _valid_profile(derived_layers=(layer,)).validate()
        self.assertTrue(any('grain_type_confidence' in e for e in errors))

    def test_non_numeric_layer_uncertainty_rejected(self) -> None:
        layer = _valid_layer(density_uncertainty='bad')  # type: ignore[arg-type]
        errors = _valid_profile(derived_layers=(layer,)).validate()
        self.assertTrue(any('density uncertainty' in e.lower() for e in errors))

    def test_raw_lineage_is_validated_when_present(self) -> None:
        lineage = SMPRawLineage(
            pnt_filename='S37M0876.pnt',
            pnt_sha256='a' * 64,
            ini_filename='S37M0876.ini',
            ini_sha256='b' * 64,
            processor_name='snowmicropyn',
            processor_version='1.2.1',
            processor_git_hash='c' * 40,
        )
        self.assertEqual(_valid_profile(raw_lineage=lineage).validate(), [])

    def test_non_string_raw_hash_rejected(self) -> None:
        lineage = SMPRawLineage(
            pnt_filename='S37M0876.pnt',
            pnt_sha256=123,  # type: ignore[arg-type]
            ini_filename='S37M0876.ini',
            ini_sha256='b' * 64,
            processor_name='snowmicropyn',
            processor_version='1.2.1',
            processor_git_hash='c' * 40,
        )
        errors = _valid_profile(raw_lineage=lineage).validate()
        self.assertTrue(any('pnt_sha256' in e for e in errors))


class TestProfilePreservation(unittest.TestCase):
    """Test that profile structure is preserved, not reduced to scalars."""

    def test_profile_has_raw_samples(self) -> None:
        profile = _valid_profile()
        self.assertTrue(profile.has_raw_data)
        self.assertEqual(profile.n_samples, 3)

    def test_profile_has_derived_layers(self) -> None:
        profile = _valid_profile()
        self.assertTrue(profile.has_derived_layers)
        self.assertEqual(profile.n_layers, 2)

    def test_scalar_proxy_derivable_but_profile_preserved(self) -> None:
        """Scalar proxies can be derived, but the full profile is preserved."""
        profile = _valid_profile()
        proxy = profile.to_scalar_proxy()
        self.assertIsNotNone(proxy['estimated_shear_strength_kpa'])
        self.assertIsNotNone(proxy['snow_settlement_index'])
        # The full profile is still available
        self.assertEqual(profile.n_layers, 2)
        self.assertEqual(profile.n_samples, 3)

    def test_empty_profile_scalar_proxy_returns_none(self) -> None:
        profile = _valid_profile(derived_layers=())
        proxy = profile.to_scalar_proxy()
        self.assertIsNone(proxy['estimated_shear_strength_kpa'])
        self.assertIsNone(proxy['snow_settlement_index'])

    def test_is_calibrated_defaults_false(self) -> None:
        """Profiles must default to uncalibrated."""
        profile = _valid_profile()
        self.assertFalse(profile.is_calibrated)


class TestDepthAlignment(unittest.TestCase):
    """Test SMP to SNOWPACK depth reference alignment."""

    def test_ground_to_ground_no_change(self) -> None:
        profile = _valid_profile(depth_reference='ground')
        aligned = align_smp_to_snowpack_depth(profile, 'ground')
        self.assertEqual(aligned.depth_reference, 'ground')
        self.assertEqual(aligned.raw_samples[0].depth_mm, profile.raw_samples[0].depth_mm)

    def test_ground_to_surface_conversion(self) -> None:
        profile = _valid_profile(depth_reference='ground', snow_depth_mm=500.0)
        aligned = align_smp_to_snowpack_depth(profile, 'surface')
        self.assertEqual(aligned.depth_reference, 'surface')
        # Ground depth 0 → surface depth 500
        self.assertAlmostEqual(aligned.raw_samples[0].depth_mm, 500.0)
        # Ground depth 100 → surface depth 400
        self.assertAlmostEqual(aligned.raw_samples[1].depth_mm, 400.0)

    def test_surface_to_ground_conversion(self) -> None:
        profile = _valid_profile(depth_reference='surface', snow_depth_mm=500.0)
        aligned = align_smp_to_snowpack_depth(profile, 'ground')
        self.assertEqual(aligned.depth_reference, 'ground')
        # Surface depth 0 → ground depth 500
        self.assertAlmostEqual(aligned.raw_samples[0].depth_mm, 500.0)

    def test_derived_layers_also_aligned(self) -> None:
        profile = _valid_profile(depth_reference='ground', snow_depth_mm=500.0)
        aligned = align_smp_to_snowpack_depth(profile, 'surface')
        # Original layer at ground depth 100 → surface depth 400
        self.assertAlmostEqual(aligned.derived_layers[0].depth_mm, 400.0)


class TestSMPRawIngestion(unittest.TestCase):
    """Test raw-pair containment and processor lineage without binary fixtures."""

    def test_ingestion_preserves_raw_pair_hashes_and_processor_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pnt = root / 'S37M0876.pnt'
            ini = root / 'S37M0876.ini'
            pnt_bytes = b'raw-pnt-bytes'
            ini_bytes = b'[markers]\n'
            pnt.write_bytes(pnt_bytes)
            ini.write_bytes(ini_bytes)
            loaded = ingest_smp_profile_files(
                pnt,
                ini,
                processor_name='snowmicropyn',
                processor_version='1.2.1',
                processor_git_hash='c' * 40,
                profile_loader=lambda _pnt, _ini: _valid_profile(),
            )
            self.assertIsNotNone(loaded.raw_lineage)
            assert loaded.raw_lineage is not None
            self.assertEqual(loaded.raw_lineage.pnt_sha256, hashlib.sha256(pnt_bytes).hexdigest())
            self.assertEqual(loaded.raw_lineage.ini_sha256, hashlib.sha256(ini_bytes).hexdigest())
            self.assertEqual(loaded.raw_lineage.processor_version, '1.2.1')
            self.assertFalse(loaded.is_calibrated)

    def test_mismatched_stems_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pnt = root / 'one.pnt'
            ini = root / 'two.ini'
            pnt.write_bytes(b'pnt')
            ini.write_bytes(b'ini')
            with self.assertRaises(SMPInputUnavailable):
                ingest_smp_profile_files(
                    pnt, ini, processor_name='snowmicropyn',
                    processor_version='1.2.1', processor_git_hash='c' * 40,
                    profile_loader=lambda _pnt, _ini: _valid_profile(),
                )

    def test_symlinked_raw_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.pnt'
            source.write_bytes(b'pnt')
            pnt = root / 'S37M0876.pnt'
            pnt.symlink_to(source)
            ini = root / 'S37M0876.ini'
            ini.write_bytes(b'ini')
            with self.assertRaises(SMPInputUnavailable):
                ingest_smp_profile_files(
                    pnt, ini, processor_name='snowmicropyn',
                    processor_version='1.2.1', processor_git_hash='c' * 40,
                    profile_loader=lambda _pnt, _ini: _valid_profile(),
                )

    def test_input_mutation_during_processing_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pnt = root / 'S37M0876.pnt'
            ini = root / 'S37M0876.ini'
            pnt.write_bytes(b'original-pnt')
            ini.write_bytes(b'[markers]\n')

            def mutating_loader(_pnt: Path, _ini: Path) -> SMPProfile:
                pnt.write_bytes(b'mutated-pnt')
                return _valid_profile()

            with self.assertRaisesRegex(SMPInputUnavailable, 'changed during processing'):
                ingest_smp_profile_files(
                    pnt, ini, processor_name='snowmicropyn',
                    processor_version='1.2.1', processor_git_hash='c' * 40,
                    profile_loader=mutating_loader,
                )


if __name__ == '__main__':
    unittest.main()
