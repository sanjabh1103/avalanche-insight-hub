"""Real COSIPY 2.0.0 smoke test, opt-in for the Python 3.12 gate.

The ordinary backend test suite does not download or JIT-compile COSIPY. The
dedicated CI job sets ``OPEN_FORCING_REAL_COSIPY=1`` and therefore fails if the
installed API, coupled input contract, or native output schema changes.
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from backend.open_forcing.cosipy_adapter import (
    CosipyForcingSeries,
    run_cosipy_coupled_reference,
)


def _deterministic_records() -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "time": start + timedelta(hours=index),
            "temperature_2m": -8.0 + 0.05 * index,
            "relative_humidity_2m": 80.0,
            "windspeed_10m": 3.0,
            "surface_pressure": 700.0,
            "shortwave_radiation": 50.0 if 7 <= index <= 16 else 0.0,
            "precipitation": 0.5,
            "cloud_cover": 80.0,
            "snowfall": 0.1,
        }
        for index in range(24)
    ]


@unittest.skipUnless(
    os.environ.get("OPEN_FORCING_REAL_COSIPY") == "1",
    "real COSIPY smoke is opt-in and requires the Python 3.12 environment gate",
)
class RealCosipySmokeTests(unittest.TestCase):
    def test_two_by_two_fixture_produces_native_profiles_and_bulk_outputs(self) -> None:
        records = _deterministic_records()
        cells = (
            (34.00, 75.00, 3000.0),
            (34.00, 75.01, 3050.0),
            (34.01, 75.00, 3100.0),
            (34.01, 75.01, 3150.0),
        )
        results = []
        for latitude, longitude, elevation in cells:
            forcing = CosipyForcingSeries.from_open_meteo_records(
                records,
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation,
            )
            result = run_cosipy_coupled_reference(forcing)
            self.assertEqual(result.engine_version, "2.0.0")
            self.assertFalse(result.production_eligible)
            self.assertFalse(result.training_eligible)
            self.assertFalse(result.stratigraphy_native)
            self.assertGreater(len(result.density_profile_kg_m3), 0)
            self.assertEqual(len(result.density_profile_kg_m3), len(result.temperature_profile_k))
            self.assertEqual(len(result.density_profile_kg_m3), len(result.liquid_water_content_m))
            self.assertIsNotNone(result.native_fields["snow_height_m"])
            self.assertIsNotNone(result.native_fields["surface_temperature_k"])
            self.assertEqual(
                set(result.native_fields),
                {
                    "snow_height_m",
                    "total_height_m",
                    "surface_temperature_k",
                    "layer_count",
                    "snow_water_equivalent_m",
                },
            )
            self.assertIsNotNone(result.snow_water_equivalent_m)
            self.assertGreaterEqual(float(result.snow_water_equivalent_m), 0.0)
            results.append(result)

        summary = [
            {
                "snow_height_m": result.native_fields["snow_height_m"],
                "snow_water_equivalent_m": result.snow_water_equivalent_m,
                "surface_temperature_k": result.native_fields["surface_temperature_k"],
                "layer_count": result.native_fields["layer_count"],
                "profile_layers": len(result.density_profile_kg_m3),
            }
            for result in results
        ]
        # Keep the CI artifact human-readable without embedding a forecast claim.
        print(json.dumps({"cells": len(results), "schema": summary}, sort_keys=True))
        self.assertEqual(len(results), 4)


if __name__ == "__main__":
    unittest.main()
