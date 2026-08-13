"""Tests for F14: Multi-Hazard Framework."""
from __future__ import annotations

import unittest
from typing import Any

from backend.common.multi_hazard import (
    DEFAULT_HAZARD_CONFIGS,
    HAZARD_AVALANCHE,
    HAZARD_FLOOD,
    HAZARD_LANDSLIDE,
    HAZARD_ROCKFALL,
    HazardAssessment,
    HazardConfig,
    MultiHazardResult,
    SUPPORTED_HAZARDS,
    assess_hazard,
    assess_multi_hazard,
    assess_multi_hazard_grid,
    get_hazard_metadata,
    risk_level_from_score,
)


class RiskLevelTests(unittest.TestCase):
    """Tests for risk level conversion."""

    def test_risk_level_boundaries(self) -> None:
        self.assertEqual(risk_level_from_score(0.0), 0)
        self.assertEqual(risk_level_from_score(0.4), 0)
        self.assertEqual(risk_level_from_score(0.5), 1)
        self.assertEqual(risk_level_from_score(1.4), 1)
        self.assertEqual(risk_level_from_score(1.5), 2)
        self.assertEqual(risk_level_from_score(2.5), 3)
        self.assertEqual(risk_level_from_score(3.5), 4)
        self.assertEqual(risk_level_from_score(4.5), 5)
        self.assertEqual(risk_level_from_score(5.0), 5)


class AssessHazardTests(unittest.TestCase):
    """Tests for single hazard assessment."""

    def test_avalanche_high_risk(self) -> None:
        factors = {
            'snow_load': 0.9,
            'slope_angle': 0.8,
            'temperature_delta': 0.7,
            'wind_transport': 0.6,
            'seismic_amplification': 0.3,
            'min_slope': 30.0,
            'min_snow_depth': 50.0,
        }
        result = assess_hazard(HAZARD_AVALANCHE, factors)
        self.assertIsInstance(result, HazardAssessment)
        self.assertEqual(result.hazard_type, HAZARD_AVALANCHE)
        self.assertGreater(result.risk_score, 2.0)
        self.assertTrue(result.trigger_met)
        self.assertGreater(result.confidence, 0.8)

    def test_avalanche_low_risk(self) -> None:
        factors = {
            'snow_load': 0.1,
            'slope_angle': 0.2,
            'temperature_delta': 0.1,
            'min_slope': 10.0,  # Below threshold
            'min_snow_depth': 10.0,  # Below threshold
        }
        result = assess_hazard(HAZARD_AVALANCHE, factors)
        self.assertLess(result.risk_score, 1.5)
        self.assertFalse(result.trigger_met)

    def test_landslide_triggered(self) -> None:
        factors = {
            'rainfall_24h': 0.9,
            'slope_angle': 0.7,
            'soil_saturation': 0.8,
            'lithology': 0.5,
            'seismic_amplification': 0.2,
            'min_slope': 20.0,
            'min_rainfall_24h': 60.0,
        }
        result = assess_hazard(HAZARD_LANDSLIDE, factors)
        self.assertGreater(result.risk_score, 2.0)
        self.assertTrue(result.trigger_met)

    def test_flood_assessment(self) -> None:
        factors = {
            'precipitation_72h': 0.85,
            'snowmelt_rate': 0.6,
            'river_proximity': 0.7,
            'glacial_lake_proximity': 0.5,
            'upstream_area': 0.4,
            'min_precipitation_72h': 120.0,
        }
        result = assess_hazard(HAZARD_FLOOD, factors)
        self.assertGreater(result.risk_score, 1.5)
        self.assertTrue(result.trigger_met)

    def test_rockfall_assessment(self) -> None:
        factors = {
            'thermal_stress': 0.8,
            'slope_angle': 0.9,
            'seismic_amplification': 0.4,
            'freeze_thaw_cycles': 0.7,
            'lithology': 0.5,
            'min_slope': 45.0,
        }
        result = assess_hazard(HAZARD_ROCKFALL, factors)
        self.assertGreater(result.risk_score, 2.0)
        self.assertTrue(result.trigger_met)

    def test_unknown_hazard_type(self) -> None:
        result = assess_hazard('unknown', {})
        self.assertEqual(result.risk_score, 0.0)
        self.assertEqual(result.risk_level, 0)
        self.assertFalse(result.trigger_met)

    def test_empty_factors(self) -> None:
        result = assess_hazard(HAZARD_AVALANCHE, {})
        self.assertEqual(result.risk_score, 0.0)
        self.assertFalse(result.trigger_met)
        self.assertEqual(result.confidence, 0.0)


class AssessMultiHazardTests(unittest.TestCase):
    """Tests for multi-hazard assessment."""

    def test_all_hazards_assessed(self) -> None:
        hazard_factors = {
            HAZARD_AVALANCHE: {'snow_load': 0.8, 'slope_angle': 0.7, 'min_slope': 30.0, 'min_snow_depth': 50.0},
            HAZARD_LANDSLIDE: {'rainfall_24h': 0.7, 'slope_angle': 0.6, 'min_slope': 20.0, 'min_rainfall_24h': 60.0},
            HAZARD_FLOOD: {'precipitation_72h': 0.6, 'min_precipitation_72h': 120.0},
            HAZARD_ROCKFALL: {'thermal_stress': 0.5, 'slope_angle': 0.8, 'min_slope': 45.0},
        }
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors=hazard_factors,
        )
        self.assertIsInstance(result, MultiHazardResult)
        self.assertEqual(len(result.hazard_assessments), 5)
        self.assertIn(HAZARD_AVALANCHE, result.hazard_assessments)
        self.assertIn(HAZARD_LANDSLIDE, result.hazard_assessments)

    def test_dominant_hazard(self) -> None:
        hazard_factors = {
            HAZARD_AVALANCHE: {'snow_load': 0.3, 'slope_angle': 0.3, 'min_slope': 30.0, 'min_snow_depth': 50.0},
            HAZARD_LANDSLIDE: {'rainfall_24h': 90.0, 'slope_angle': 35.0, 'min_slope': 20.0, 'min_rainfall_24h': 60.0},
        }
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors=hazard_factors,
            hazard_types=[HAZARD_AVALANCHE, HAZARD_LANDSLIDE],
        )
        self.assertEqual(result.dominant_hazard, HAZARD_LANDSLIDE)

    def test_composite_risk(self) -> None:
        hazard_factors = {
            HAZARD_AVALANCHE: {'snow_load': 0.8, 'slope_angle': 0.7, 'min_slope': 30.0, 'min_snow_depth': 50.0},
            HAZARD_LANDSLIDE: {'rainfall_24h': 0.2, 'min_slope': 5.0, 'min_rainfall_24h': 10.0},
        }
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors=hazard_factors,
            hazard_types=[HAZARD_AVALANCHE, HAZARD_LANDSLIDE],
        )
        self.assertGreater(result.composite_risk, 0.0)
        self.assertGreater(result.composite_risk_level, 0)

    def test_any_trigger_met(self) -> None:
        hazard_factors = {
            HAZARD_AVALANCHE: {'snow_load': 0.8, 'slope_angle': 0.7, 'min_slope': 30.0, 'min_snow_depth': 50.0},
            HAZARD_LANDSLIDE: {'rainfall_24h': 0.2, 'min_slope': 5.0, 'min_rainfall_24h': 10.0},
        }
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors=hazard_factors,
        )
        self.assertTrue(result.any_trigger_met)

    def test_no_triggers_met(self) -> None:
        hazard_factors = {
            HAZARD_AVALANCHE: {'snow_load': 0.1, 'min_slope': 5.0, 'min_snow_depth': 5.0},
        }
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors=hazard_factors,
            hazard_types=[HAZARD_AVALANCHE],
        )
        self.assertFalse(result.any_trigger_met)

    def test_empty_hazard_factors(self) -> None:
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors={},
        )
        self.assertEqual(result.composite_risk, 0.0)
        self.assertEqual(result.dominant_hazard, HAZARD_AVALANCHE)

    def test_subset_hazard_types(self) -> None:
        hazard_factors = {
            HAZARD_AVALANCHE: {'snow_load': 0.5, 'min_slope': 30.0, 'min_snow_depth': 50.0},
            HAZARD_FLOOD: {'precipitation_72h': 0.6, 'min_precipitation_72h': 120.0},
        }
        result = assess_multi_hazard(
            cell_lat=32.0,
            cell_lng=78.0,
            hazard_factors=hazard_factors,
            hazard_types=[HAZARD_AVALANCHE],
        )
        self.assertEqual(len(result.hazard_assessments), 1)
        self.assertIn(HAZARD_AVALANCHE, result.hazard_assessments)


class AssessMultiHazardGridTests(unittest.TestCase):
    """Tests for grid-level multi-hazard assessment."""

    def setUp(self) -> None:
        import backend.common.multi_hazard as mh
        mh.MULTI_HAZARD_ENABLED = True

    def tearDown(self) -> None:
        import backend.common.multi_hazard as mh
        mh.MULTI_HAZARD_ENABLED = False

    def test_grid_with_hazard_factors(self) -> None:
        cells = [
            {
                'lat': 32.0, 'lng': 78.0, 'row': 0, 'col': 0,
                'avalanche_snow_load': 0.8,
                'avalanche_slope_angle': 0.7,
                'avalanche_min_slope': 30.0,
                'avalanche_min_snow_depth': 50.0,
            },
            {
                'lat': 32.1, 'lng': 78.1, 'row': 0, 'col': 1,
                'landslide_rainfall_24h': 90.0,
                'landslide_slope_angle': 35.0,
                'landslide_min_slope': 20.0,
                'landslide_min_rainfall_24h': 60.0,
            },
        ]
        results = assess_multi_hazard_grid(cells)
        self.assertEqual(len(results), 2)
        self.assertIn('multi_hazard', results[0])
        self.assertIn('multi_hazard', results[1])
        self.assertEqual(results[0]['dominant_hazard'], HAZARD_AVALANCHE)
        self.assertEqual(results[1]['dominant_hazard'], HAZARD_LANDSLIDE)

    def test_grid_without_hazard_factors(self) -> None:
        cells = [
            {'lat': 32.0, 'lng': 78.0, 'row': 0, 'col': 0, 'riskScore': 3},
        ]
        results = assess_multi_hazard_grid(cells)
        self.assertEqual(len(results), 1)
        self.assertNotIn('multi_hazard', results[0])


class GetHazardMetadataTests(unittest.TestCase):
    """Tests for hazard metadata retrieval."""

    def test_metadata_contains_all_hazards(self) -> None:
        metadata = get_hazard_metadata()
        self.assertEqual(len(metadata), 5)
        for htype in SUPPORTED_HAZARDS:
            self.assertIn(htype, metadata)
            self.assertIn('display_name', metadata[htype])
            self.assertIn('color', metadata[htype])
            self.assertIn('icon', metadata[htype])
            self.assertIn('description', metadata[htype])

    def test_metadata_has_risk_weights(self) -> None:
        metadata = get_hazard_metadata()
        avalanche_meta = metadata[HAZARD_AVALANCHE]
        self.assertIn('risk_weights', avalanche_meta)
        self.assertIn('snow_load', avalanche_meta['risk_weights'])


class SupportedHazardsTests(unittest.TestCase):
    """Tests for supported hazard types."""

    def test_supported_hazards(self) -> None:
        self.assertIn(HAZARD_AVALANCHE, SUPPORTED_HAZARDS)
        self.assertIn(HAZARD_LANDSLIDE, SUPPORTED_HAZARDS)
        self.assertIn(HAZARD_FLOOD, SUPPORTED_HAZARDS)
        self.assertIn(HAZARD_ROCKFALL, SUPPORTED_HAZARDS)

    def test_default_configs_match(self) -> None:
        for htype in SUPPORTED_HAZARDS:
            self.assertIn(htype, DEFAULT_HAZARD_CONFIGS)
            cfg = DEFAULT_HAZARD_CONFIGS[htype]
            self.assertIsInstance(cfg, HazardConfig)
            self.assertEqual(cfg.hazard_type, htype)


if __name__ == '__main__':
    unittest.main()
