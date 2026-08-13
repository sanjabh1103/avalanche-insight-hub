"""Tests for PartnerCellInputContract — per-cell input validation and builder."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.ravafcast_cell_input import (
    PartnerCellInputContract,
    compute_schema_hash,
    build_cell_inputs,
    normalize_weather_sample,
    to_feature_weather_sample,
    VALID_WINDOW_TYPES,
)
from backend.common.real_features import HourlyWeatherSample, select_hourly_weather_sample


def _make_valid_weather(**overrides) -> dict:
    defaults = dict(
        air_temp_c=-5.0,
        relative_humidity=80.0,
        pressure_hpa=650.0,
        precip_mm=2.5,
        wind_speed_ms=15.0,
        wind_dir_deg=270.0,
        wind_gust_ms=25.0,
        shortwave_radiation=200.0,
        source_id="open-meteo",
        source_timestamp="2026-07-18T06:00:00+00:00",
    )
    defaults.update(overrides)
    return defaults


def _make_valid_contract(**overrides) -> PartnerCellInputContract:
    defaults = dict(
        region_key="pir_panjal",
        pixel_id="pir_panjal_0_0",
        row=0,
        col=0,
        timestamp="2026-07-18T06:00:00+00:00",
        issue_slot="06",
        latitude=32.0,
        longitude=77.0,
        elevation_m=3500.0,
        crs="EPSG:4326",
        air_temp_c=-5.0,
        relative_humidity=80.0,
        pressure_hpa=650.0,
        precip_mm=2.5,
        wind_speed_ms=15.0,
        wind_dir_deg=270.0,
        wind_gust_ms=25.0,
        shortwave_radiation=200.0,
        source_id="open-meteo",
        source_timestamp="2026-07-18T06:00:00+00:00",
        retrieval_time="2026-07-18T06:00:00+00:00",
        schema_hash="a" * 64,
        missingness="complete",
        fallback=False,
        training_eligible=False,
        window_type="instantaneous",
        window_start="2026-07-18T06:00:00+00:00",
        window_end="2026-07-18T06:00:00+00:00",
    )
    defaults.update(overrides)
    return PartnerCellInputContract(**defaults)


class PartnerCellInputContractValidationTests(unittest.TestCase):
    def test_normalize_open_meteo_aliases_preserves_sample_lineage(self) -> None:
        normalized = normalize_weather_sample(
            {
                'temperature_2m': -8.5,
                'relativehumidity_2m': 82.0,
                'surface_pressure': 650.0,
                'precipitation_24h_mm': 3.2,
                'windspeed_10m': 14.0,
                'winddirection_10m': 270.0,
                'windgusts_10m': 22.0,
                'shortwave_radiation_instant': 120.0,
                'time': '2026-07-18T06:00:00+00:00',
                'retrieval_time': '2026-07-18T06:17:00+00:00',
            },
            fallback_timestamp='2026-07-18T06:17:00+00:00',
        )
        self.assertEqual(normalized['missingness'], 'complete')
        self.assertEqual(normalized['air_temp_c'], -8.5)
        self.assertEqual(normalized['precip_mm'], 3.2)
        self.assertEqual(normalized['source_timestamp'], '2026-07-18T06:00:00+00:00')
        self.assertEqual(normalized['retrieval_time'], '2026-07-18T06:17:00+00:00')

    def test_normalize_missing_fields_is_partial(self) -> None:
        normalized = normalize_weather_sample(
            {'temperature_2m': -2.0},
            fallback_timestamp='2026-07-18T06:17:00+00:00',
        )
        self.assertEqual(normalized['missingness'], 'partial')
        self.assertIn('relative_humidity', normalized['missing_fields'])

    def test_feature_adapter_maps_canonical_values_before_model_input(self) -> None:
        normalized = normalize_weather_sample(
            {
                'temperature_2m': -11.0,
                'relativehumidity_2m': 76.0,
                'surface_pressure': 640.0,
                'precipitation_24h_mm': 4.0,
                'windspeed_10m': 18.0,
                'winddirection_10m': 250.0,
                'windgusts_10m': 27.0,
                'shortwave_radiation_instant': 90.0,
                'time': '2026-07-18T12:00:00+00:00',
            },
            fallback_timestamp='2026-07-18T12:17:00+00:00',
        )
        feature_sample = to_feature_weather_sample(
            normalized,
            original={'temperature_2m': 999.0, 'pressure_level_value': 12.0},
        )
        self.assertEqual(feature_sample['temperature_2m'], -11.0)
        self.assertEqual(feature_sample['precipitation_24h'], 4.0)
        self.assertEqual(feature_sample['winddirection_10m'], 250.0)
        self.assertEqual(feature_sample['pressure_level_value'], 12.0)
        self.assertEqual(feature_sample['source_timestamp'], '2026-07-18T12:00:00+00:00')

    def test_hourly_selector_retains_profile_retrieval_time(self) -> None:
        selected = select_hourly_weather_sample(
            {
                'source': 'open-meteo-batch',
                'retrieval_time': '2026-07-18T06:17:00+00:00',
                'samples': [HourlyWeatherSample(
                    timestamp='2026-07-18T06:00:00+00:00',
                    values={'temperature_2m': -5.0},
                )],
            },
            datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(selected['retrieval_time'], '2026-07-18T06:17:00+00:00')

    def test_valid_contract_passes(self) -> None:
        c = _make_valid_contract()
        c.validate()

    def test_empty_region_key_fails(self) -> None:
        c = _make_valid_contract(region_key="")
        with self.assertRaises(ValueError, msg="region_key must not be empty"):
            c.validate()

    def test_empty_pixel_id_fails(self) -> None:
        c = _make_valid_contract(pixel_id="")
        with self.assertRaises(ValueError, msg="pixel_id must not be empty"):
            c.validate()

    def test_negative_row_fails(self) -> None:
        c = _make_valid_contract(row=-1)
        with self.assertRaises(ValueError, msg="row/col must be >= 0"):
            c.validate()

    def test_latitude_out_of_range_fails(self) -> None:
        c = _make_valid_contract(latitude=91.0)
        with self.assertRaises(ValueError, msg="latitude out of range"):
            c.validate()

    def test_longitude_out_of_range_fails(self) -> None:
        c = _make_valid_contract(longitude=181.0)
        with self.assertRaises(ValueError, msg="longitude out of range"):
            c.validate()

    def test_elevation_out_of_range_fails(self) -> None:
        c = _make_valid_contract(elevation_m=10000.0)
        with self.assertRaises(ValueError, msg="elevation_m out of range"):
            c.validate()

    def test_invalid_window_type_fails(self) -> None:
        c = _make_valid_contract(window_type="hourly")
        with self.assertRaises(ValueError, msg="window_type"):
            c.validate()

    def test_training_eligible_true_fails(self) -> None:
        c = _make_valid_contract(training_eligible=True)
        with self.assertRaises(ValueError, msg="training_eligible must be False"):
            c.validate()

    def test_invalid_missingness_fails(self) -> None:
        c = _make_valid_contract(missingness="unknown")
        with self.assertRaises(ValueError, msg="invalid missingness"):
            c.validate()

    def test_empty_crs_fails(self) -> None:
        c = _make_valid_contract(crs="")
        with self.assertRaises(ValueError, msg="crs must not be empty"):
            c.validate()

    def test_empty_issue_slot_fails(self) -> None:
        c = _make_valid_contract(issue_slot="")
        with self.assertRaises(ValueError, msg="issue_slot must not be empty"):
            c.validate()


class ComputeSchemaHashTests(unittest.TestCase):
    def test_hash_is_deterministic(self) -> None:
        payload = {"b": 2, "a": 1}
        h1 = compute_schema_hash(payload)
        h2 = compute_schema_hash(payload)
        self.assertEqual(h1, h2)

    def test_hash_is_order_independent(self) -> None:
        h1 = compute_schema_hash({"a": 1, "b": 2})
        h2 = compute_schema_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_hash_changes_on_content_change(self) -> None:
        h1 = compute_schema_hash({"a": 1})
        h2 = compute_schema_hash({"a": 2})
        self.assertNotEqual(h1, h2)

    def test_hash_is_hex_string(self) -> None:
        h = compute_schema_hash({"a": 1})
        self.assertEqual(len(h), 64)
        int(h, 16)  # Should not raise


class BuildCellInputsTests(unittest.TestCase):
    def test_2x2_grid_builds_four_contracts(self) -> None:
        grid = [
            {"lat": 32.0, "lng": 77.0, "row": 0, "col": 0, "elevation_m": 3500.0},
            {"lat": 32.0, "lng": 77.1, "row": 0, "col": 1, "elevation_m": 3400.0},
            {"lat": 32.1, "lng": 77.0, "row": 1, "col": 0, "elevation_m": 3600.0},
            {"lat": 32.1, "lng": 77.1, "row": 1, "col": 1, "elevation_m": 3500.0},
        ]
        weather = [
            _make_valid_weather(air_temp_c=-5.0, relative_humidity=80.0, pressure_hpa=650.0),
            _make_valid_weather(air_temp_c=-4.0, relative_humidity=75.0, pressure_hpa=655.0),
            _make_valid_weather(air_temp_c=-6.0, relative_humidity=85.0, pressure_hpa=645.0),
            _make_valid_weather(air_temp_c=-5.5, relative_humidity=82.0, pressure_hpa=648.0),
        ]
        contracts = build_cell_inputs(
            grid, weather, issue_slot="06",
            timestamp="2026-07-18T06:00:00+00:00",
            region_key="pir_panjal",
        )
        self.assertEqual(len(contracts), 4)
        for c in contracts:
            c.validate()
            self.assertFalse(c.training_eligible)
            self.assertEqual(c.issue_slot, "06")

    def test_length_mismatch_raises(self) -> None:
        grid = [{"lat": 32.0, "lng": 77.0, "row": 0, "col": 0}]
        weather = [{}, {}]
        with self.assertRaises(ValueError, msg="length mismatch"):
            build_cell_inputs(grid, weather, "06", "2026-07-18T06:00:00+00:00")

    def test_pixel_ids_are_stable(self) -> None:
        grid = [
            {"lat": 32.0, "lng": 77.0, "row": 0, "col": 0},
            {"lat": 32.0, "lng": 77.1, "row": 0, "col": 1},
        ]
        weather = [_make_valid_weather(air_temp_c=-5.0), _make_valid_weather(air_temp_c=-4.0)]
        contracts = build_cell_inputs(
            grid, weather, "06", "2026-07-18T06:00:00+00:00",
            region_key="test_region",
        )
        self.assertEqual(contracts[0].pixel_id, "test_region_0_0")
        self.assertEqual(contracts[1].pixel_id, "test_region_0_1")

    def test_missing_data_records_fallback(self) -> None:
        grid = [{"lat": 32.0, "lng": 77.0, "row": 0, "col": 0}]
        weather = [_make_valid_weather(missingness="partial", fallback=True)]
        contracts = build_cell_inputs(
            grid, weather, "06", "2026-07-18T06:00:00+00:00",
        )
        self.assertTrue(contracts[0].fallback)
        self.assertEqual(contracts[0].missingness, "partial")
        self.assertFalse(contracts[0].training_eligible)

    def test_six_hour_window_type(self) -> None:
        grid = [{"lat": 32.0, "lng": 77.0, "row": 0, "col": 0}]
        weather = [_make_valid_weather()]
        contracts = build_cell_inputs(
            grid, weather, "06", "2026-07-18T06:00:00+00:00",
            window_type="six_hour_aggregate",
            window_start="2026-07-18T00:00:00+00:00",
            window_end="2026-07-18T06:00:00+00:00",
        )
        self.assertEqual(contracts[0].window_type, "six_hour_aggregate")
        contracts[0].validate()

    def test_projected_grid_crs_is_preserved(self) -> None:
        grid = [{
            "lat": 32.0, "lng": 77.0, "row": 0, "col": 0,
            "elevation_m": 3500.0, "crs": "EPSG:32643",
            "grid_manifest_hash": "b" * 64,
        }]
        contracts = build_cell_inputs(
            grid, [_make_valid_weather()], "06",
            "2026-07-18T06:00:00+00:00", region_key="test_region",
        )
        self.assertEqual(contracts[0].crs, "EPSG:32643")


if __name__ == "__main__":
    unittest.main()


class PartnerCellInputHardenedValidationTests(unittest.TestCase):
    """G8: Tests for hardened validation — NaN, CRS, schema_hash, source_timestamp."""

    def test_nan_weather_rejected(self) -> None:
        c = _make_valid_contract(air_temp_c=float('nan'))
        with self.assertRaises(ValueError) as cm:
            c.validate()
        self.assertIn('finite number', str(cm.exception))

    def test_inf_weather_rejected(self) -> None:
        c = _make_valid_contract(wind_speed_ms=float('inf'))
        with self.assertRaises(ValueError) as cm:
            c.validate()
        self.assertIn('finite number', str(cm.exception))

    def test_invalid_crs_rejected(self) -> None:
        c = _make_valid_contract(crs="WGS84")
        with self.assertRaises(ValueError) as cm:
            c.validate()
        self.assertIn("EPSG:", str(cm.exception))

    def test_empty_source_timestamp_rejected(self) -> None:
        c = _make_valid_contract(source_timestamp="")
        with self.assertRaises(ValueError) as cm:
            c.validate()
        self.assertIn('source_timestamp', str(cm.exception))

    def test_short_schema_hash_rejected(self) -> None:
        c = _make_valid_contract(schema_hash="abc123")
        with self.assertRaises(ValueError) as cm:
            c.validate()
        self.assertIn('64 chars', str(cm.exception))

    def test_non_hex_schema_hash_rejected(self) -> None:
        c = _make_valid_contract(schema_hash="z" * 64)
        with self.assertRaises(ValueError) as cm:
            c.validate()
        self.assertIn('hex string', str(cm.exception))

    def test_missing_weather_key_raises_keyerror(self) -> None:
        grid = [{"lat": 32.0, "lng": 77.0, "row": 0, "col": 0}]
        weather = [{"air_temp_c": -5.0}]  # missing required keys
        with self.assertRaises(KeyError):
            build_cell_inputs(grid, weather, "06", "2026-07-18T06:00:00+00:00")
