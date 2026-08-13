"""Tests for Himalayan regime configuration (Phase 1b)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.config_validator import HIMALAYAN_REGION_KEYS
from backend.common.himalayan_regimes import (
    ElevationBand,
    HimalayanRegime,
    RegimeValidationError,
    get_regime,
    load_himalayan_regimes,
    validate_all_regimes,
    validate_regime,
    VALID_ASPECT_CLASSES,
    VALID_OBSERVATION_COVERAGE,
    VALID_PROBLEM_TYPES,
    VALID_SEASONAL_PHASES,
)
from backend.common.regions import repo_root


class TestHimalayanRegimesLoaded(unittest.TestCase):
    """Test that the real Himalayan regime config loads correctly."""

    def test_all_five_himalayan_regions_have_regimes(self) -> None:
        """Every Himalayan region key must have a regime configuration."""
        regimes = load_himalayan_regimes()
        for key in HIMALAYAN_REGION_KEYS:
            self.assertIn(
                key,
                regimes,
                f'Himalayan region "{key}" has no regime configuration',
            )

    def test_nepal_is_tier_a(self) -> None:
        """Nepal must be Tier A."""
        regime = get_regime('himalayas_nepal')
        self.assertIsNotNone(regime)
        self.assertEqual(regime.tier, 'A')

    def test_nw_himalaya_regions_are_tier_b(self) -> None:
        """Pir Panjal, Shamshabari, Great Himalaya, Karakoram must be Tier B."""
        for key in ('pir_panjal_nw_himalaya', 'shamshabari_nw_himalaya',
                     'great_himalaya_nw_himalaya', 'karakoram_&_ladakh'):
            regime = get_regime(key)
            self.assertIsNotNone(regime, f'{key} has no regime')
            self.assertEqual(regime.tier, 'B', f'{key} should be Tier B')

    def test_all_regimes_valid(self) -> None:
        """All regimes in the real config must pass validation."""
        errors = validate_all_regimes()
        self.assertEqual(
            errors,
            [],
            'Regime validation errors:\n' + '\n'.join(errors),
        )

    def test_every_regime_has_elevation_bands(self) -> None:
        """Every regime must have at least one elevation band."""
        regimes = load_himalayan_regimes()
        for key, regime in regimes.items():
            self.assertGreater(
                len(regime.elevation_bands),
                0,
                f'{key} has no elevation bands',
            )

    def test_every_regime_has_seasonal_phases(self) -> None:
        """Every regime must have all four seasonal phases."""
        regimes = load_himalayan_regimes()
        for key, regime in regimes.items():
            self.assertEqual(
                len(regime.seasonal_phases),
                4,
                f'{key} must have 4 seasonal phases, got {regime.seasonal_phases}',
            )

    def test_nepal_bands_differ_from_western_himalaya(self) -> None:
        """Nepal elevation bands must not be identical to Western Himalaya bands."""
        nepal = get_regime('himalayas_nepal')
        pir_panjal = get_regime('pir_panjal_nw_himalaya')
        self.assertIsNotNone(nepal)
        self.assertIsNotNone(pir_panjal)
        nepal_bands = {(b.elevation_min_m, b.elevation_max_m) for b in nepal.elevation_bands}
        pp_bands = {(b.elevation_min_m, b.elevation_max_m) for b in pir_panjal.elevation_bands}
        self.assertNotEqual(
            nepal_bands,
            pp_bands,
            'Nepal elevation bands must not be copied from Pir Panjal',
        )

    def test_karakoram_has_no_wet_snow_as_primary(self) -> None:
        """Karakoram/Ladakh (polar-dry) should not list wet_snow as a primary problem."""
        regime = get_regime('karakoram_&_ladakh')
        self.assertIsNotNone(regime)
        self.assertNotIn(
            'wet_snow',
            regime.expected_problem_types,
            'Karakoram/Ladakh is polar-dry; wet snow should not be a primary expected problem',
        )

    def test_calibration_version_is_candidate(self) -> None:
        """All regimes must be labelled as candidate calibration (not validated)."""
        regimes = load_himalayan_regimes()
        for key, regime in regimes.items():
            self.assertTrue(
                regime.calibration_version.startswith('candidate'),
                f'{key} calibration_version must start with "candidate", '
                f'got {regime.calibration_version}',
            )

    def test_observation_coverage_is_sparse_or_worse(self) -> None:
        """All elevation bands must have sparse or worse observation coverage."""
        regimes = load_himalayan_regimes()
        for key, regime in regimes.items():
            for band in regime.elevation_bands:
                self.assertIn(
                    band.observation_coverage,
                    ('sparse', 'very_sparse', 'no_direct_observations'),
                    f'{key}/{band.name} observation_coverage must be sparse or worse, '
                    f'got {band.observation_coverage}',
                )


class TestRegimeValidation(unittest.TestCase):
    """Test the regime validation logic with synthetic configs."""

    def test_invalid_tier_rejected(self) -> None:
        regime = HimalayanRegime(
            region_key='test',
            tier='C',
            climate_class='continental',
            seasonal_phases=('storm_new_snow',),
            elevation_bands=(),
            expected_problem_types=('storm_slab',),
            calibration_version='candidate_v0',
        )
        errors = validate_regime(regime)
        self.assertTrue(any('tier' in e for e in errors))

    def test_inverted_elevation_band_rejected(self) -> None:
        band = ElevationBand(
            name='test',
            elevation_min_m=5000,
            elevation_max_m=3000,
            dominant_processes=('storm_new_snow',),
            aspect_classes=('N',),
            observation_coverage='sparse',
        )
        regime = HimalayanRegime(
            region_key='test',
            tier='A',
            climate_class='continental',
            seasonal_phases=('storm_new_snow',),
            elevation_bands=(band,),
            expected_problem_types=('storm_slab',),
            calibration_version='candidate_v0',
        )
        errors = validate_regime(regime)
        self.assertTrue(any('elevation_min' in e for e in errors))

    def test_non_contiguous_bands_rejected(self) -> None:
        band1 = ElevationBand(
            name='lower', elevation_min_m=3000, elevation_max_m=4000,
            dominant_processes=('storm_new_snow',),
            aspect_classes=('N',), observation_coverage='sparse',
        )
        band2 = ElevationBand(
            name='upper', elevation_min_m=4500, elevation_max_m=5000,
            dominant_processes=('wind_slab',),
            aspect_classes=('N',), observation_coverage='sparse',
        )
        regime = HimalayanRegime(
            region_key='test', tier='A', climate_class='continental',
            seasonal_phases=('storm_new_snow',),
            elevation_bands=(band1, band2),
            expected_problem_types=('storm_slab',),
            calibration_version='candidate_v0',
        )
        errors = validate_regime(regime)
        self.assertTrue(any('contiguous' in e for e in errors))

    def test_invalid_seasonal_phase_rejected(self) -> None:
        regime = HimalayanRegime(
            region_key='test', tier='A', climate_class='continental',
            seasonal_phases=('invalid_phase',),
            elevation_bands=(),
            expected_problem_types=('storm_slab',),
            calibration_version='candidate_v0',
        )
        errors = validate_regime(regime)
        self.assertTrue(any('seasonal_phase' in e for e in errors))


if __name__ == '__main__':
    unittest.main()
