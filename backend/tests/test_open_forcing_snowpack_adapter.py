from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.open_forcing.contracts import OpenForcingContractError
from backend.open_forcing.open_meteo_source import OpenMeteoRunRequest, parse_open_meteo_single_run
from backend.open_forcing.snowpack_adapter import (
    HimalayanSiteSpec,
    build_himalayan_snowpack_forcing,
    precipitation_phase_fraction,
    write_himalayan_smet,
)


_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "shortwave_radiation",
    "cloud_cover",
    "precipitation",
    "snow_depth",
    "terrestrial_radiation",
)


def _payload():
    request = OpenMeteoRunRequest(
        latitudes=(34.0,),
        longitudes=(75.0,),
        model_id="ecmwf_ifs025",
        run_id="2026-07-31T00:00",
        forecast_hours=3,
        hourly_variables=_VARIABLES,
    )
    response = {
        "latitude": 34.0,
        "longitude": 75.0,
        "hourly": {
            "time": [
                "2026-07-31T00:00",
                "2026-07-31T01:00",
                "2026-07-31T02:00",
            ],
            "temperature_2m": [-5.0, -1.0, 3.0],
            "relative_humidity_2m": [80.0, 82.0, 84.0],
            "wind_speed_10m": [4.0, 5.0, 6.0],
            "wind_direction_10m": [180.0, 200.0, 220.0],
            "shortwave_radiation": [0.0, 20.0, 100.0],
            "cloud_cover": [90.0, 80.0, 60.0],
            "precipitation": [0.5, 1.0, 0.0],
            "snow_depth": [0.4, 0.4, 0.35],
            "terrestrial_radiation": [0.0, 40.0, 120.0],
        },
    }
    raw = json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
    return parse_open_meteo_single_run(response, request, raw_payload=raw)


def _site(**overrides) -> HimalayanSiteSpec:
    values = dict(
        site_id="pir_panjal_lower_n_001",
        source_point_index=0,
        source_snapshot_id="snapshot-001",
        source_id="open_meteo_nwp",
        source_elevation_m=2500.0,
        target_elevation_m=3000.0,
        slope_deg=35.0,
        aspect_deg=180.0,
        native_resolution_m=9000.0,
        target_resolution_m=500.0,
        snow_temperature_c=-2.0,
        rain_temperature_c=2.0,
        exposure_factor=1.2,
    )
    values.update(overrides)
    return HimalayanSiteSpec(**values)


class HimalayanSnowpackAdapterTests(unittest.TestCase):
    def test_phase_fraction_is_bounded_and_explicit(self) -> None:
        self.assertEqual(
            precipitation_phase_fraction(-3.0, snow_temperature_c=-2.0, rain_temperature_c=2.0),
            0.0,
        )
        self.assertAlmostEqual(
            precipitation_phase_fraction(0.0, snow_temperature_c=-2.0, rain_temperature_c=2.0),
            0.5,
        )
        self.assertEqual(
            precipitation_phase_fraction(3.0, snow_temperature_c=-2.0, rain_temperature_c=2.0),
            1.0,
        )
        with self.assertRaises(OpenForcingContractError):
            precipitation_phase_fraction(0.0, snow_temperature_c=1.0, rain_temperature_c=1.0)

    def test_build_preserves_raw_corrected_and_smet_hashes(self) -> None:
        forcing = build_himalayan_snowpack_forcing(_payload(), _site())
        forcing.validate()
        self.assertEqual(len(forcing.raw_payload_sha256), 64)
        self.assertEqual(len(forcing.corrected_payload_sha256), 64)
        self.assertNotEqual(forcing.raw_payload_sha256, forcing.corrected_payload_sha256)
        self.assertAlmostEqual(forcing.samples[0]["temperature_2m"], -8.25)
        self.assertEqual(forcing.samples[0]["precipitation_phase"], 0.0)
        self.assertAlmostEqual(forcing.samples[2]["precipitation_phase"], 0.4375)
        self.assertNotIn("snow_depth", forcing.samples[0])
        self.assertEqual(forcing.samples[0]["source_snow_depth"], 0.4)
        self.assertIsNone(forcing.samples[0]["snowfall"])
        self.assertNotIn("terrestrial_radiation", forcing.samples[0])
        self.assertIn("source_terrestrial_radiation", forcing.samples[0])
        self.assertIn("cloud_cover", forcing.samples[0])
        self.assertIn("elevation_lapse_correction", {item.method for item in forcing.resolution_metadata})
        self.assertIn("vector_preserving_wind_exposure_adjustment", {item.method for item in forcing.resolution_metadata})

    def test_write_hashes_exact_smet_with_psum_phase(self) -> None:
        forcing = build_himalayan_snowpack_forcing(_payload(), _site())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pir_panjal_lower.smet"
            written = write_himalayan_smet(
                forcing,
                output_path=path,
                station_id="pir_panjal_lower_n_001",
                latitude=34.0,
                longitude=75.0,
            )
            content = path.read_text(encoding="utf-8")
            self.assertEqual(written.smet_sha256, __import__("hashlib").sha256(path.read_bytes()).hexdigest())
            self.assertIn("ncolumns         = 12", content)
            self.assertIn("PSUM_PH", content)
            self.assertIn("-999.0", content)
            data = content.split("[DATA]\n", 1)[1].strip().splitlines()
            self.assertEqual(len(data), 3)

    def test_smet_unit_vectors_use_meteoio_space_delimiters(self) -> None:
        forcing = build_himalayan_snowpack_forcing(_payload(), _site())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pir_panjal_middle.smet"
            write_himalayan_smet(
                forcing,
                output_path=path,
                station_id="pir_panjal_middle_n_001",
                latitude=34.0,
                longitude=75.0,
            )
            lines = path.read_text(encoding="utf-8").splitlines()
            offset = next(line for line in lines if line.startswith("units_offset"))
            multiplier = next(line for line in lines if line.startswith("units_multiplier"))
            fields = next(line for line in lines if line.startswith("fields"))
            self.assertIn("fields           = timestamp TA RH VW DW ISWR ILWR PSUM HS TSG TSS PSUM_PH", fields)
            self.assertIn("nodata            = -999", lines)
            self.assertIn("altitude         = 3000.0", lines)
            self.assertNotIn(",", offset)
            self.assertNotIn(",", multiplier)
            self.assertEqual(len(offset.split("=", 1)[1].split()), 12)
            self.assertEqual(len(multiplier.split("=", 1)[1].split()), 12)

    def test_terrain_adjustment_requires_explicit_solar_geometry(self) -> None:
        with self.assertRaisesRegex(OpenForcingContractError, "solar_zenith"):
            build_himalayan_snowpack_forcing(
                _payload(),
                _site(apply_shortwave_terrain=True),
            )

    def test_missing_radiation_and_precipitation_fail_closed(self) -> None:
        payload = _payload()
        record = dict(payload.points[0].records[0])
        record["cloud_cover"] = None
        record["precipitation"] = None
        record["snow_depth"] = None
        altered_point = payload.points[0]
        altered_point = type(altered_point)(
            point=altered_point.point,
            times=altered_point.times,
            records=(record,) + altered_point.records[1:],
        )
        altered_payload = type(payload)(
            request=payload.request,
            points=(altered_point,),
            raw_payload_sha256=payload.raw_payload_sha256,
        )
        with self.assertRaisesRegex(OpenForcingContractError, "longwave_radiation or cloud_cover"):
            build_himalayan_snowpack_forcing(altered_payload, _site())

    def test_terrestrial_radiation_is_provenance_not_longwave_input(self) -> None:
        payload = _payload()
        record = dict(payload.points[0].records[0])
        record["terrestrial_radiation"] = 1367.7
        record["cloud_cover"] = 50.0
        point = payload.points[0]
        altered_point = type(point)(point=point.point, times=point.times, records=(record,) + point.records[1:])
        altered_payload = type(payload)(
            request=payload.request,
            points=(altered_point,),
            raw_payload_sha256=payload.raw_payload_sha256,
        )
        forcing = build_himalayan_snowpack_forcing(altered_payload, _site())
        self.assertEqual(forcing.samples[0]["source_terrestrial_radiation"], 1367.7)
        self.assertNotIn("terrestrial_radiation", forcing.samples[0])
        self.assertIn("cloud_cover", forcing.samples[0])

    def test_non_neutral_precipitation_scale_requires_lineage(self) -> None:
        with self.assertRaisesRegex(OpenForcingContractError, "precipitation_scale_source"):
            _site(precipitation_scale=1.2).validate()

    def test_phase_thresholds_and_source_identity_are_required(self) -> None:
        with self.assertRaises(OpenForcingContractError):
            _site(source_snapshot_id="").validate()
        with self.assertRaises(OpenForcingContractError):
            _site(snow_temperature_c=1.0, rain_temperature_c=0.0).validate()


if __name__ == "__main__":
    unittest.main()
