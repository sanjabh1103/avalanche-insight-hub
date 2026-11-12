"""Regression tests for the scoped Snowpack code-local hardening changes."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.common.meteoio_openmeteo import NativeExecutionEvidence, generate_snowpack_config
from backend.common.snowpack_physics import SnowpackPhysicsResult, fetch_weather_history_for_snowpack
from backend.scripts.run_pir_panjal_poc_vertical_slice import _build_rf_comparison


def _complete_archive_response() -> dict[str, object]:
    return {
        "hourly": {
            "time": ["2025-01-14T00:00", "2025-01-14T01:00"],
            "temperature_2m": [-10.0, -12.0],
            "precipitation": [0.0, 0.1],
            "snowfall": [0.0, 0.1],
            "snow_depth": [0.5, 0.55],
            "windspeed_10m": [5.0, 3.0],
            "winddirection_10m": [180.0, 190.0],
            "relative_humidity_2m": [80.0, 85.0],
            "shortwave_radiation": [0.0, 0.0],
            "cloud_cover": [50.0, 60.0],
            "surface_pressure": [700.0, 700.0],
        }
    }


class SnowpackCodeLocalHardeningTests(unittest.TestCase):
    def test_archive_missing_value_returns_empty_without_zero_fill(self) -> None:
        response = _complete_archive_response()
        hourly = response["hourly"]
        assert isinstance(hourly, dict)
        hourly["snow_depth"] = [0.5, None]
        mock_response = MagicMock()
        mock_response.json.return_value = response
        with patch("requests.get", return_value=mock_response):
            result = fetch_weather_history_for_snowpack(
                lat=34.0,
                lng=74.25,
                as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
                max_days=7,
            )
        self.assertEqual(result, [])

    def test_native_cell_binds_coordinates_and_output_directory(self) -> None:
        import backend.common.snowpack_physics as physics_module

        samples = [
            {
                "time": "2025-01-14T00:00:00Z",
                "temperature_2m": -10.0,
                "relative_humidity_2m": 80.0,
                "windspeed_10m": 5.0,
                "winddirection_10m": 180.0,
                "shortwave_radiation": 0.0,
                "cloud_cover": 50.0,
                "precipitation": 0.0,
                "snow_depth": 0.5,
            },
            {
                "time": "2025-01-14T01:00:00Z",
                "temperature_2m": -12.0,
                "relative_humidity_2m": 85.0,
                "windspeed_10m": 3.0,
                "winddirection_10m": 190.0,
                "shortwave_radiation": 0.0,
                "cloud_cover": 60.0,
                "precipitation": 0.1,
                "snow_depth": 0.55,
            },
        ]
        parsed = {
            "weak_layer_depth_m": 0.1,
            "weak_layer_grain_type": "rounded",
            "weak_layer_shear_strength_kpa": 1.0,
            "snowpack_stability_index": 1.0,
            "temperature_gradient_per_m": 0.1,
            "liquid_water_content_pct": 0.0,
            "layer_count": 2,
            "snow_height_m": 0.55,
            "bulk_density_kgm3": 300.0,
            "layers": [],
        }
        captured: dict[str, object] = {}

        def fake_native(**kwargs: object) -> NativeExecutionEvidence:
            config_path = kwargs["config_path"]
            output_dir = kwargs["output_dir"]
            assert isinstance(config_path, Path)
            assert isinstance(output_dir, Path)
            captured["config"] = config_path.read_text(encoding="utf-8")
            captured["output_dir"] = output_dir
            return NativeExecutionEvidence(
                pro_path=str(output_dir / "cell_34.0000_74.2500_native.pro"),
                success=True,
            )

        with patch.object(physics_module, "snowpack_binary_available", return_value=True), \
             patch.object(physics_module, "run_snowpack_native", side_effect=fake_native), \
             patch.object(physics_module, "parse_snowpack_pro", return_value=parsed):
            result = physics_module.run_snowpack_native_cell(
                lat=34.0,
                lng=74.25,
                elevation_m=3359.0,
                weather_history=samples,
                as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
                slope_angle=31.8,
                aspect=6.2,
            )

        self.assertEqual(result.method, "snowpack_native")
        config = str(captured["config"])
        self.assertIn("COORDPARAM = 43", config)
        self.assertIn("METEOPATH = ", config)
        self.assertIn("SNOWPATH = ", config)
        self.assertIsInstance(captured["output_dir"], Path)

    def test_rf_bridge_withholds_unavailable_snowfall(self) -> None:
        physics = SnowpackPhysicsResult(
            weak_layer_depth_m=0.1,
            weak_layer_grain_type="rounded",
            weak_layer_shear_strength_kpa=1.0,
            snowpack_stability_index=1.0,
            temperature_gradient_per_m=0.1,
            liquid_water_content_pct=0.0,
            layer_count=2,
            snow_height_m=0.55,
            bulk_density_kgm3=300.0,
            method="snowpack_native",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forcing_dir = root / "forcing"
            forcing_dir.mkdir()
            (forcing_dir / "corrected-samples.json").write_text(
                json.dumps([
                    {"time": "2025-01-14T00:00:00Z", "wind_speed_10m": 5.0, "wind_direction_10m": 180.0, "precipitation": 0.0, "temperature_2m": -10.0},
                    {"time": "2025-01-14T01:00:00Z", "wind_speed_10m": 3.0, "wind_direction_10m": 190.0, "precipitation": 0.1, "temperature_2m": -12.0},
                ]),
                encoding="utf-8",
            )
            model_path = root / "model.joblib"
            model_path.write_bytes(b"model")
            result = _build_rf_comparison(
                model_path=model_path,
                forcing_dir=forcing_dir,
                site={"dem_elevation_m": 3359.0, "latitude": 34.0, "longitude": 74.25, "aspect_deg": 6.2, "slope_deg": 31.8},
                physics=physics,
                as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
            )
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(result["missing_features"], ["snowfall_24h"])
        self.assertEqual(result["feature_quality"]["snowfall_24h"], "unavailable")
        self.assertIn("no zero substitute", result["reason"])
        self.assertNotIn("snowfall_24h was set to zero", " ".join(result["limitations"]))

    def test_generated_config_declares_hourly_precipitation_resampling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "snowpack.ini"
            generate_snowpack_config(
                output_path=config_path,
                season_start_date="2023-10-01",
                end_date="2024-02-24",
                latitude=34.021875,
                longitude=74.347536111,
            )
            content = config_path.read_text(encoding="utf-8")

        self.assertIn("CALCULATION_STEP_LENGTH = 60.0", content)
        self.assertIn("PSUM::resample = accumulate", content)
        self.assertIn("PSUM::accumulate::period = 3600", content)


if __name__ == "__main__":
    unittest.main()
