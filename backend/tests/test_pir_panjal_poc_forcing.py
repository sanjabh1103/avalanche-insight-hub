"""Fail-closed unit tests for the candidate winter forcing builder."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts.build_pir_panjal_poc_forcing import (
    PirPanjalForcingBuildError,
    _normalize_response,
)


def _response() -> dict[str, object]:
    return {
        "hourly_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "windspeed_10m": "km/h",
            "winddirection_10m": "°",
            "surface_pressure": "hPa",
            "shortwave_radiation": "W/m²",
            "precipitation": "mm",
            "cloud_cover": "%",
            "terrestrial_radiation": "W/m²",
        },
        "hourly": {
            "time": ["2024-02-22T00:00", "2024-02-22T01:00"],
            "temperature_2m": [-8.0, -7.5],
            "relative_humidity_2m": [80.0, 82.0],
            "windspeed_10m": [10.0, 12.0],
            "winddirection_10m": [180.0, 190.0],
            "surface_pressure": [650.0, 651.0],
            "shortwave_radiation": [0.0, 20.0],
            "precipitation": [0.5, 0.6],
            "cloud_cover": [90.0, 95.0],
            "terrestrial_radiation": [100.0, 110.0],
        },
        "latitude": 34.021875,
        "longitude": 74.347536,
        "elevation": 3727.0,
    }


class PirPanjalPocForcingTests(unittest.TestCase):
    def test_mapping_and_interpolation_contracts_are_explicit(self) -> None:
        root = Path(__file__).resolve().parents[2]
        mapping = __import__("json").loads(
            (root / "config/snowpack_poc/ravafcast-snowpack-mapping.json").read_text(encoding="utf-8")
        )
        policy = __import__("json").loads(
            (root / "config/snowpack_poc/meteoio-interpolation-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(mapping["schema_version"], "snowpack_ravafcast_mapping_v1")
        terrestrial = next(item for item in mapping["mapping"] if item["source"] == "terrestrial_radiation")
        self.assertEqual(terrestrial["target"], "none")
        self.assertFalse(policy["interpolation_enabled_for_current_run"])
        self.assertEqual(policy["recommended_profile_if_a_gap_occurs"]["maximum_missing_duration_seconds"], 3600)
        self.assertIn("any unresolved core field gap remains", policy["failure_threshold"]["abort_before_native_run_when"])

    def test_corrected_v2_registry_record_is_hash_bound(self) -> None:
        from backend.common.snowpack_manifest_registry import resolve_approved_manifest

        record = resolve_approved_manifest(
            "pir-panjal-open-meteo-gfs-seamless-2023-10-01-2024-02-24-v2",
            kind="forcing",
            expected_region="pir_panjal_nw_himalaya",
            expected_elevation_band="middle",
        )
        self.assertEqual(record["payload_sha256"], "7f517d182e60f81c1d2a570db4f0d625edd4511f1e6e0fef4e268c456d36ed81")
        self.assertEqual(record["mapping_contract_sha256"], "bb9d60a7673527cc20c6d1791bd936406f00be1e32315399d3cbe8f5b4ed293a")
        self.assertEqual(record["meteoio_policy_sha256"], "a4d1d50fddf47d76026c6bbc93f258ecf59c44856b17d72e01778ffa46e8e0ac")
        self.assertTrue(Path(record["resolved_mapping_contract_path"]).is_file())
        self.assertTrue(Path(record["resolved_meteoio_policy_path"]).is_file())
        payload = __import__("json").loads(Path(record["resolved_payload_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 3552)
        self.assertIn("precipitation_phase", payload[0])
        self.assertNotIn("terrestrial_radiation", payload[0])
        self.assertIn("source_terrestrial_radiation", payload[0])
        self.assertIn("cloud_cover", payload[0])
        self.assertIsNone(payload[0]["snowfall"])

    def test_canonical_forecast_semantics_selects_corrected_forcing(self) -> None:
        semantics = __import__("json").loads(
            (Path(__file__).resolve().parents[2] / "config/snowpack_poc/forecast-semantics.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            semantics["contract"]["forcing_manifest_id"],
            "pir-panjal-open-meteo-gfs-seamless-2023-10-01-2024-02-24-v2",
        )

    def test_normalization_converts_kmh_to_ms_and_preserves_hourly_utc(self) -> None:
        records, units, metadata = _normalize_response(
            _response(),
            start=datetime(2024, 2, 22, tzinfo=timezone.utc),
            end_exclusive=datetime(2024, 2, 22, 2, tzinfo=timezone.utc),
        )
        self.assertAlmostEqual(records[0]["wind_speed_10m"], 10.0 / 3.6)
        self.assertEqual(records[0]["wind_direction_10m"], 180.0)
        self.assertEqual(records[0]["time"], "2024-02-22T00:00:00Z")
        self.assertEqual(units["windspeed_10m"], "km/h")
        self.assertIsNone(records[0]["snowfall"])
        self.assertIsNone(records[0]["snow_depth"])
        self.assertEqual(metadata["provider_latitude"], 34.021875)
        self.assertEqual(metadata["provider_elevation_m"], 3727.0)

    def test_optional_null_is_preserved_without_zero_substitution(self) -> None:
        response = _response()
        hourly = response["hourly"]
        assert isinstance(hourly, dict)
        hourly["snowfall"] = [None, 0.4]
        records, _, _ = _normalize_response(
            response,
            start=datetime(2024, 2, 22, tzinfo=timezone.utc),
            end_exclusive=datetime(2024, 2, 22, 2, tzinfo=timezone.utc),
        )
        self.assertIsNone(records[0]["snowfall"])
        self.assertEqual(records[1]["snowfall"], 0.4)

    def test_terrestrial_radiation_is_optional_provenance(self) -> None:
        response = _response()
        hourly = response["hourly"]
        assert isinstance(hourly, dict)
        hourly.pop("terrestrial_radiation")
        records, _, _ = _normalize_response(
            response,
            start=datetime(2024, 2, 22, tzinfo=timezone.utc),
            end_exclusive=datetime(2024, 2, 22, 2, tzinfo=timezone.utc),
        )
        self.assertIsNone(records[0]["terrestrial_radiation"])

    def test_missing_required_value_fails_without_default(self) -> None:
        response = _response()
        hourly = response["hourly"]
        assert isinstance(hourly, dict)
        hourly["precipitation"] = [None, 0.6]
        with self.assertRaisesRegex(PirPanjalForcingBuildError, "precipitation"):
            _normalize_response(
                response,
                start=datetime(2024, 2, 22, tzinfo=timezone.utc),
                end_exclusive=datetime(2024, 2, 22, 2, tzinfo=timezone.utc),
            )

    def test_non_contiguous_timeline_fails(self) -> None:
        response = _response()
        hourly = response["hourly"]
        assert isinstance(hourly, dict)
        hourly["time"] = ["2024-02-22T00:00", "2024-02-22T02:00"]
        with self.assertRaisesRegex(PirPanjalForcingBuildError, "contiguous"):
            _normalize_response(
                response,
                start=datetime(2024, 2, 22, tzinfo=timezone.utc),
                end_exclusive=datetime(2024, 2, 22, 3, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
