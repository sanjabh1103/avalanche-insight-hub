from __future__ import annotations

import unittest

import numpy as np

from backend.open_forcing.contracts import OpenForcingContractError
from backend.open_forcing.downscaling import (
    EffectiveResolution,
    downscale_shortwave_radiation,
    downscale_temperature_celsius,
    redistribute_precipitation_mm,
    terrain_radiation_factor,
    transform_wind_vector,
)


class OpenForcingDownscalingTests(unittest.TestCase):
    def test_temperature_lapse_is_monotonic_and_resolution_is_conservative(self) -> None:
        lower, metadata = downscale_temperature_celsius(
            -4.0,
            source_elevation_m=2000.0,
            target_elevation_m=3000.0,
            source_id="era5_land",
            native_resolution_m=9000.0,
            target_resolution_m=500.0,
        )
        self.assertAlmostEqual(lower, -10.5)
        self.assertEqual(metadata.effective_information_scale_m, 9000.0)
        self.assertEqual(metadata.method, "elevation_lapse_correction")

    def test_precipitation_redistribution_preserves_area_total(self) -> None:
        values, metadata = redistribute_precipitation_mm(
            12.0,
            [1.0, 2.0, 0.0],
            source_id="gpm_imerg_early",
            native_resolution_m=10000.0,
            target_resolution_m=500.0,
        )
        self.assertTrue(np.all(values >= 0.0))
        self.assertAlmostEqual(float(values.sum()), 12.0, places=12)
        self.assertEqual(metadata.effective_information_scale_m, 10000.0)

    def test_precipitation_rejects_empty_or_zero_support(self) -> None:
        for weights in ([], [0.0, 0.0]):
            with self.assertRaises(OpenForcingContractError):
                redistribute_precipitation_mm(
                    2.0,
                    weights,
                    source_id="gpm_imerg_early",
                    native_resolution_m=10000.0,
                    target_resolution_m=500.0,
                )

    def test_radiation_factor_is_bounded_and_flat_reference_is_one(self) -> None:
        self.assertAlmostEqual(
            terrain_radiation_factor(
                slope_deg=0.0,
                aspect_deg=0.0,
                solar_zenith_deg=30.0,
                solar_azimuth_deg=180.0,
            ),
            1.0,
        )
        shaded = terrain_radiation_factor(
            slope_deg=60.0,
            aspect_deg=0.0,
            solar_zenith_deg=60.0,
            solar_azimuth_deg=180.0,
        )
        self.assertGreaterEqual(shaded, 0.0)
        self.assertLessEqual(shaded, 3.0)

    def test_radiation_output_is_non_negative(self) -> None:
        output, metadata = downscale_shortwave_radiation(
            100.0,
            slope_deg=30.0,
            aspect_deg=90.0,
            solar_zenith_deg=45.0,
            solar_azimuth_deg=90.0,
            source_id="open_meteo_nwp",
            native_resolution_m=9000.0,
            target_resolution_m=500.0,
        )
        self.assertGreaterEqual(output, 0.0)
        self.assertEqual(metadata.method, "terrain_incidence_shortwave_adjustment")

    def test_wind_vector_does_not_change_direction_without_explicit_factor(self) -> None:
        vector, metadata = transform_wind_vector(
            3.0,
            4.0,
            source_id="open_meteo_nwp",
            native_resolution_m=9000.0,
            target_resolution_m=500.0,
        )
        self.assertAlmostEqual(vector.speed_ms, 5.0)
        self.assertAlmostEqual(vector.u_ms / vector.v_ms, 3.0 / 4.0)
        self.assertEqual(metadata.method, "vector_preserving_wind_exposure_adjustment")

    def test_resolution_contract_rejects_finer_effective_scale(self) -> None:
        with self.assertRaises(OpenForcingContractError):
            EffectiveResolution(
                source_id="era5_land",
                native_resolution_m=9000.0,
                target_resolution_m=500.0,
                effective_information_scale_m=250.0,
                method="invalid",
            ).validate()


if __name__ == "__main__":
    unittest.main()
