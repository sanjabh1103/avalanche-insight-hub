"""Tests for F14-detail: Multi-Hazard Full Implementation."""
from __future__ import annotations

import unittest
import math
import numpy as np

from backend.common.multi_hazard import (
    HAZARD_AVALANCHE,
    HAZARD_FLOOD,
    HAZARD_LANDSLIDE,
    HAZARD_ROCKFALL,
    assess_hazard_detailed,
)
from backend.common.landslide_model import (
    LandslideCellInput,
    LandslideConfig,
    assess_landslide_risk,
    assess_landslide_grid,
    compute_factor_of_safety,
)
from backend.common.debris_flow import (
    DebrisFlowInput,
    DebrisFlowConfig,
    GLOFInput,
    GLOFConfig,
    assess_debris_flow_risk,
    assess_glof_risk,
    assess_debris_flow_grid,
    caine_threshold,
    REGIONAL_FACTORS,
)


class FactorOfSafetyTests(unittest.TestCase):
    """Tests for infinite slope stability model."""

    def test_flat_ground_very_stable(self) -> None:
        fs = compute_factor_of_safety(
            slope_deg=0.0, soil_depth_m=3.0,
            cohesion_kpa=15.0, friction_angle_deg=30.0,
            soil_unit_weight=18.0, saturated_unit_weight=20.0,
        )
        self.assertGreater(fs, 5.0)

    def test_steep_slope_less_stable(self) -> None:
        fs_flat = compute_factor_of_safety(
            slope_deg=10.0, soil_depth_m=3.0,
            cohesion_kpa=15.0, friction_angle_deg=30.0,
            soil_unit_weight=18.0, saturated_unit_weight=20.0,
        )
        fs_steep = compute_factor_of_safety(
            slope_deg=45.0, soil_depth_m=3.0,
            cohesion_kpa=15.0, friction_angle_deg=30.0,
            soil_unit_weight=18.0, saturated_unit_weight=20.0,
        )
        self.assertGreater(fs_flat, fs_steep)

    def test_saturation_reduces_stability(self) -> None:
        fs_dry = compute_factor_of_safety(
            slope_deg=30.0, soil_depth_m=3.0,
            cohesion_kpa=15.0, friction_angle_deg=30.0,
            soil_unit_weight=18.0, saturated_unit_weight=20.0,
            saturation=0.0,
        )
        fs_wet = compute_factor_of_safety(
            slope_deg=30.0, soil_depth_m=3.0,
            cohesion_kpa=15.0, friction_angle_deg=30.0,
            soil_unit_weight=18.0, saturated_unit_weight=20.0,
            saturation=1.0,
        )
        self.assertGreater(fs_dry, fs_wet)

    def test_zero_depth_returns_stable(self) -> None:
        fs = compute_factor_of_safety(
            slope_deg=30.0, soil_depth_m=0.0,
            cohesion_kpa=15.0, friction_angle_deg=30.0,
            soil_unit_weight=18.0, saturated_unit_weight=20.0,
        )
        self.assertGreater(fs, 5.0)


class LandslideRiskTests(unittest.TestCase):
    """Tests for landslide susceptibility assessment."""

    def test_high_rainfall_steep_slope(self) -> None:
        cell = LandslideCellInput(
            slope_deg=40.0,
            rainfall_24h_mm=80.0,
            soil_saturation=0.8,
            lithology_factor=0.7,
        )
        result = assess_landslide_risk(cell)
        self.assertEqual(result.hazard_type, HAZARD_LANDSLIDE)
        self.assertGreater(result.risk_score, 2.0)
        self.assertTrue(result.trigger_met)
        self.assertIn('factor_of_safety', result.metadata)

    def test_flat_terrain_low_risk(self) -> None:
        cell = LandslideCellInput(
            slope_deg=5.0,
            rainfall_24h_mm=10.0,
        )
        result = assess_landslide_risk(cell)
        self.assertLess(result.risk_score, 1.5)
        self.assertFalse(result.trigger_met)

    def test_saturated_slope_higher_risk(self) -> None:
        cell_dry = LandslideCellInput(
            slope_deg=35.0, rainfall_24h_mm=60.0,
            soil_saturation=0.2,
        )
        cell_wet = LandslideCellInput(
            slope_deg=35.0, rainfall_24h_mm=60.0,
            soil_saturation=0.9,
        )
        result_dry = assess_landslide_risk(cell_dry)
        result_wet = assess_landslide_risk(cell_wet)
        self.assertGreater(result_wet.risk_score, result_dry.risk_score)

    def test_seismic_amplification_increases_risk(self) -> None:
        cell_no_seismic = LandslideCellInput(
            slope_deg=35.0, rainfall_24h_mm=60.0,
            seismic_amplification=0.0,
        )
        cell_seismic = LandslideCellInput(
            slope_deg=35.0, rainfall_24h_mm=60.0,
            seismic_amplification=0.5,
        )
        result_no = assess_landslide_risk(cell_no_seismic)
        result_yes = assess_landslide_risk(cell_seismic)
        self.assertGreater(result_yes.risk_score, result_no.risk_score)

    def test_contributing_factors_present(self) -> None:
        cell = LandslideCellInput(
            slope_deg=30.0, rainfall_24h_mm=50.0,
            soil_saturation=0.5, lithology_factor=0.6,
        )
        result = assess_landslide_risk(cell)
        self.assertIn('slope_angle', result.contributing_factors)
        self.assertIn('rainfall_24h', result.contributing_factors)
        self.assertIn('factor_of_safety', result.contributing_factors)

    def test_landslide_grid(self) -> None:
        cells = [
            {'slope_deg': 40.0, 'rainfall_24h_mm': 80.0, 'soil_saturation': 0.7},
            {'slope_deg': 5.0, 'rainfall_24h_mm': 5.0},
        ]
        results = assess_landslide_grid(cells)
        self.assertEqual(len(results), 2)
        self.assertIn('landslide_risk', results[0])
        self.assertIn('landslide_risk', results[1])
        self.assertGreater(
            results[0]['landslide_risk']['risk_score'],
            results[1]['landslide_risk']['risk_score'],
        )


class CaineThresholdTests(unittest.TestCase):
    """Tests for Caine (1980) debris flow threshold."""

    def test_threshold_decreases_with_duration(self) -> None:
        short = caine_threshold(1.0)
        long = caine_threshold(12.0)
        self.assertGreater(short, long)

    def test_regional_factor_applied(self) -> None:
        cfg_pir = DebrisFlowConfig(regional_factor=0.8)
        cfg_karakoram = DebrisFlowConfig(regional_factor=1.2)
        t_pir = caine_threshold(6.0, config=cfg_pir)
        t_karakoram = caine_threshold(6.0, config=cfg_karakoram)
        self.assertLess(t_pir, t_karakoram)

    def test_zero_duration_returns_high(self) -> None:
        t = caine_threshold(0.0)
        self.assertGreater(t, 100.0)

    def test_known_value(self) -> None:
        # Caine: I = 14.82 * D^(-0.39)
        # At D=1: I = 14.82
        t = caine_threshold(1.0, config=DebrisFlowConfig(regional_factor=1.0))
        self.assertAlmostEqual(t, 14.82, places=1)


class DebrisFlowRiskTests(unittest.TestCase):
    """Tests for debris flow trigger assessment."""

    def test_high_intensity_triggers(self) -> None:
        cell = DebrisFlowInput(
            rainfall_intensity_mmhr=30.0,
            rainfall_duration_hr=3.0,
            slope_deg=25.0,
            sediment_availability=0.8,
        )
        result = assess_debris_flow_risk(cell)
        self.assertGreater(result.risk_score, 2.0)
        self.assertTrue(result.trigger_met)

    def test_low_intensity_no_trigger(self) -> None:
        cell = DebrisFlowInput(
            rainfall_intensity_mmhr=2.0,
            rainfall_duration_hr=6.0,
            slope_deg=20.0,
        )
        result = assess_debris_flow_risk(cell)
        self.assertLess(result.risk_score, 1.5)
        self.assertFalse(result.trigger_met)

    def test_burn_scar_amplifies(self) -> None:
        cell_no_burn = DebrisFlowInput(
            rainfall_intensity_mmhr=12.0,
            rainfall_duration_hr=3.0,
            slope_deg=25.0,
            burn_scar=False,
        )
        cell_burn = DebrisFlowInput(
            rainfall_intensity_mmhr=12.0,
            rainfall_duration_hr=3.0,
            slope_deg=25.0,
            burn_scar=True,
        )
        r_no = assess_debris_flow_risk(cell_no_burn)
        r_burn = assess_debris_flow_risk(cell_burn)
        self.assertGreater(r_burn.risk_score, r_no.risk_score)

    def test_regional_factor(self) -> None:
        cell_pir = DebrisFlowInput(
            rainfall_intensity_mmhr=15.0,
            rainfall_duration_hr=3.0,
            slope_deg=25.0,
            region_key='pir_panjal',
        )
        cell_karakoram = DebrisFlowInput(
            rainfall_intensity_mmhr=15.0,
            rainfall_duration_hr=3.0,
            slope_deg=25.0,
            region_key='karakoram',
        )
        r_pir = assess_debris_flow_risk(cell_pir)
        r_karakoram = assess_debris_flow_risk(cell_karakoram)
        # Pir Panjal has lower threshold, so more likely to trigger
        self.assertGreaterEqual(r_pir.risk_score, r_karakoram.risk_score)

    def test_debris_flow_grid(self) -> None:
        cells = [
            {'rainfall_intensity_mmhr': 25.0, 'rainfall_duration_hr': 3.0, 'slope_deg': 25.0},
            {'rainfall_intensity_mmhr': 1.0, 'rainfall_duration_hr': 6.0, 'slope_deg': 10.0},
        ]
        results = assess_debris_flow_grid(cells)
        self.assertEqual(len(results), 2)
        self.assertIn('debris_flow_risk', results[0])
        self.assertIn('debris_flow_risk', results[1])


class GLOFRiskTests(unittest.TestCase):
    """Tests for GLOF trigger assessment."""

    def test_no_lake_no_risk(self) -> None:
        cell = GLOFInput(
            glacial_lake_present=False,
            lake_area_km2=0.0,
        )
        result = assess_glof_risk(cell)
        self.assertEqual(result.risk_score, 0.0)
        self.assertFalse(result.trigger_met)

    def test_temp_spike_and_unstable_dam_triggers(self) -> None:
        cell = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=0.5,
            temperature_2m_c=15.0,
            temp_7d_mean_c=5.0,
            ice_dam_stability=0.2,
            downstream_population=5000,
        )
        result = assess_glof_risk(cell)
        self.assertTrue(result.trigger_met)
        self.assertGreater(result.risk_score, 3.0)

    def test_stable_dam_no_trigger(self) -> None:
        cell = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=0.5,
            temperature_2m_c=15.0,
            temp_7d_mean_c=5.0,
            ice_dam_stability=0.9,
        )
        result = assess_glof_risk(cell)
        self.assertFalse(result.trigger_met)

    def test_no_temp_spike_no_trigger(self) -> None:
        cell = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=0.5,
            temperature_2m_c=10.0,
            temp_7d_mean_c=9.0,
            ice_dam_stability=0.1,
        )
        result = assess_glof_risk(cell)
        self.assertFalse(result.trigger_met)

    def test_larger_lake_higher_risk(self) -> None:
        cell_small = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=0.05,
            temperature_2m_c=12.0,
            temp_7d_mean_c=5.0,
            ice_dam_stability=0.5,
        )
        cell_large = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=1.0,
            temperature_2m_c=12.0,
            temp_7d_mean_c=5.0,
            ice_dam_stability=0.5,
        )
        r_small = assess_glof_risk(cell_small)
        r_large = assess_glof_risk(cell_large)
        self.assertGreater(r_large.risk_score, r_small.risk_score)

    def test_downstream_population_amplifies(self) -> None:
        cell_low_pop = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=0.5,
            temperature_2m_c=12.0,
            temp_7d_mean_c=5.0,
            ice_dam_stability=0.2,
            downstream_population=100,
        )
        cell_high_pop = GLOFInput(
            glacial_lake_present=True,
            lake_area_km2=0.5,
            temperature_2m_c=12.0,
            temp_7d_mean_c=5.0,
            ice_dam_stability=0.2,
            downstream_population=50000,
        )
        r_low = assess_glof_risk(cell_low_pop)
        r_high = assess_glof_risk(cell_high_pop)
        self.assertGreater(r_high.risk_score, r_low.risk_score)


class AssessHazardDetailedTests(unittest.TestCase):
    """Tests for the integrated assess_hazard_detailed function."""

    def test_landslide_detailed(self) -> None:
        factors = {
            'slope_angle': 35.0,
            'rainfall_24h': 70.0,
            'soil_saturation': 0.6,
            'lithology': 0.6,
        }
        result = assess_hazard_detailed(HAZARD_LANDSLIDE, factors)
        self.assertEqual(result.hazard_type, HAZARD_LANDSLIDE)
        self.assertGreater(result.risk_score, 1.0)
        self.assertIn('factor_of_safety', result.metadata)

    def test_flood_detailed_glof(self) -> None:
        factors = {
            'glacial_lake_proximity': 0.5,
            'temperature_2m': 15.0,
            'temp_7d_mean': 5.0,
            'ice_dam_stability': 0.2,
        }
        result = assess_hazard_detailed(HAZARD_FLOOD, factors)
        self.assertEqual(result.hazard_type, HAZARD_FLOOD)
        self.assertTrue(result.trigger_met)

    def test_debris_flow_detailed(self) -> None:
        factors = {
            'rainfall_intensity': 25.0,
            'rainfall_duration': 3.0,
            'slope_angle': 25.0,
        }
        result = assess_hazard_detailed('debris_flow', factors)
        self.assertEqual(result.hazard_type, 'debris_flow')
        self.assertGreater(result.risk_score, 1.0)

    def test_avalanche_falls_back_to_generic(self) -> None:
        factors = {
            'snow_load': 0.8,
            'slope_angle': 0.7,
            'min_slope': 30.0,
            'min_snow_depth': 50.0,
        }
        result = assess_hazard_detailed(HAZARD_AVALANCHE, factors)
        self.assertEqual(result.hazard_type, HAZARD_AVALANCHE)
        # Should use generic weighted scoring, no model-specific metadata
        self.assertNotIn('factor_of_safety', result.metadata)

    def test_rockfall_falls_back_to_generic(self) -> None:
        factors = {
            'thermal_stress': 0.7,
            'slope_angle': 0.8,
            'min_slope': 45.0,
        }
        result = assess_hazard_detailed(HAZARD_ROCKFALL, factors)
        self.assertEqual(result.hazard_type, HAZARD_ROCKFALL)


if __name__ == '__main__':
    unittest.main()
