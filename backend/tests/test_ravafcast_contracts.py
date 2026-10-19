"""Tests for ravafcast_contracts — fail-closed validation for candidate modules.

Verifies that all contracts fail closed on:
- Invalid labels
- Missing coordinates
- Binary risk_score → multiclass conversion (prohibited)
- Empty/None contracts
- N/A dimensions cannot be scored
"""

import unittest

from backend.common.ravafcast_contracts import (
    ContractViolationError,
    LabelContract,
    StationContract,
    SnowpackContract,
    GridCRSContract,
    RegionElevationContract,
    EvidenceCaseContract,
    compute_provenance_hash,
    utc_now_iso,
)


class TestLabelContract(unittest.TestCase):

    def _valid_contract(self) -> LabelContract:
        return LabelContract(
            labels=(1, 2, 3, 4),
            label_names=("Low", "Moderate", "High", "Very High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner-Scientist-1",
            approved_at="2026-07-18T00:00:00Z",
        )

    def test_valid_contract_passes(self):
        c = self._valid_contract()
        c.validate()  # should not raise

    def test_empty_labels_fail(self):
        c = LabelContract(
            labels=(),
            label_names=(),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_label_name_mismatch_fails(self):
        c = LabelContract(
            labels=(1, 2, 3, 4),
            label_names=("Low", "Moderate", "High"),  # 3 names, 4 labels
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_invalid_missing_label_policy_fails(self):
        c = LabelContract(
            labels=(1, 2),
            label_names=("Low", "High"),
            missing_label_policy="guess",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_no_approver_fails(self):
        c = LabelContract(
            labels=(1, 2),
            label_names=("Low", "High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_valid_probability_vector_passes(self):
        c = self._valid_contract()
        c.validate_probability_vector([0.25, 0.25, 0.25, 0.25])

    def test_wrong_length_probability_fails(self):
        c = self._valid_contract()
        with self.assertRaises(ContractViolationError):
            c.validate_probability_vector([0.5, 0.5])  # 2 probs, 4 labels

    def test_non_normalized_probability_fails(self):
        c = self._valid_contract()
        with self.assertRaises(ContractViolationError):
            c.validate_probability_vector([0.1, 0.1, 0.1, 0.1])  # sum=0.4

    def test_negative_probability_fails(self):
        c = self._valid_contract()
        with self.assertRaises(ContractViolationError):
            c.validate_probability_vector([-0.1, 0.4, 0.4, 0.3])

    def test_binary_risk_score_conversion_rejected(self):
        """Binary risk_score must NEVER be converted to multiclass danger."""
        c = self._valid_contract()
        with self.assertRaises(ContractViolationError):
            c.reject_binary_risk_score(0.65)

    def test_duplicate_labels_fail(self):
        c = LabelContract(
            labels=(1, 2, 2, 4),
            label_names=("Low", "Moderate", "High", "Very High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_unsorted_labels_fail(self):
        c = LabelContract(
            labels=(4, 3, 2, 1),
            label_names=("Very High", "High", "Moderate", "Low"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_duplicate_label_names_fail(self):
        c = LabelContract(
            labels=(1, 2, 3, 4),
            label_names=("Low", "Low", "High", "Very High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_missing_approved_at_fails(self):
        c = LabelContract(
            labels=(1, 2),
            label_names=("Low", "High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_invalid_approved_at_fails(self):
        c = LabelContract(
            labels=(1, 2),
            label_names=("Low", "High"),
            missing_label_policy="reject",
            forecast_window_hours=24,
            approved_by="Partner",
            approved_at="not-a-date",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_nan_probability_fails(self):
        c = self._valid_contract()
        with self.assertRaises(ContractViolationError):
            c.validate_probability_vector([float('nan'), 0.3, 0.3, 0.4])

    def test_inf_probability_fails(self):
        c = self._valid_contract()
        with self.assertRaises(ContractViolationError):
            c.validate_probability_vector([float('inf'), 0.3, 0.3, 0.4])


class TestStationContract(unittest.TestCase):

    def _valid_station(self) -> dict:
        return {
            "station_id": "Partner-001",
            "latitude": 32.5,
            "longitude": 77.0,
            "elevation_m": 3000,
            "timestamp": "2026-07-18T06:00:00Z",
            "air_temp_c": -5.0,
            "wind_speed_ms": 12.0,
            "precip_mm": 2.5,
        }

    def test_valid_station_passes(self):
        sc = StationContract()
        sc.validate_station(self._valid_station())

    def test_missing_required_field_fails(self):
        sc = StationContract()
        station = self._valid_station()
        del station["latitude"]
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_none_required_field_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["elevation_m"] = None
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_invalid_latitude_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["latitude"] = 95.0
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_invalid_longitude_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["longitude"] = -200.0
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_extreme_elevation_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["elevation_m"] = 20000
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_nan_latitude_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["latitude"] = float('nan')
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_inf_temperature_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["air_temp_c"] = float('inf')
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_invalid_timestamp_string_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["timestamp"] = "not-a-date"
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_empty_station_id_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["station_id"] = ""
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)

    def test_whitespace_station_id_fails(self):
        sc = StationContract()
        station = self._valid_station()
        station["station_id"] = "   "
        with self.assertRaises(ContractViolationError):
            sc.validate_station(station)


class TestSnowpackContract(unittest.TestCase):

    def _valid_profile(self) -> dict:
        return {
            "layer_depth_m": 0.5,
            "grain_type": "rounded grains",
            "hardness": "4F",
            "temperature_c": -8.0,
            "swe_mm": 150.0,
        }

    def test_valid_profile_passes(self):
        sp = SnowpackContract()
        sp.validate_profile(self._valid_profile())

    def test_missing_field_reject_policy_fails(self):
        sp = SnowpackContract(missingness_policy="reject")
        profile = self._valid_profile()
        del profile["grain_type"]
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)

    def test_missing_field_skip_policy_ok(self):
        sp = SnowpackContract(missingness_policy="skip")
        profile = self._valid_profile()
        del profile["grain_type"]
        sp.validate_profile(profile)  # should not raise

    def test_negative_depth_fails(self):
        sp = SnowpackContract()
        profile = self._valid_profile()
        profile["layer_depth_m"] = -1.0
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)

    def test_invalid_missingness_policy_fails(self):
        sp = SnowpackContract(missingness_policy="guess")
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(self._valid_profile())

    def test_nan_depth_fails(self):
        sp = SnowpackContract()
        profile = self._valid_profile()
        profile["layer_depth_m"] = float('nan')
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)

    def test_inf_temperature_fails(self):
        sp = SnowpackContract()
        profile = self._valid_profile()
        profile["temperature_c"] = float('inf')
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)

    def test_nan_swe_fails(self):
        sp = SnowpackContract()
        profile = self._valid_profile()
        profile["swe_mm"] = float('nan')
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)

    def test_invalid_observation_time_fails(self):
        sp = SnowpackContract()
        profile = self._valid_profile()
        profile["observation_time"] = "not-a-date"
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)

    def test_non_bool_is_proxy_fails(self):
        sp = SnowpackContract()
        profile = self._valid_profile()
        profile["is_proxy"] = "yes"
        with self.assertRaises(ContractViolationError):
            sp.validate_profile(profile)


class TestGridCRSContract(unittest.TestCase):

    def test_valid_degree_grid_passes(self):
        c = GridCRSContract(
            crs="EPSG:4326",
            dem_source="COP30",
            cell_size_degrees=0.5,
        )
        c.validate()

    def test_valid_utm_grid_passes(self):
        c = GridCRSContract(
            crs="EPSG:32644",
            dem_source="SRTM",
            cell_size_meters=500.0,
        )
        c.validate()

    def test_missing_crs_fails(self):
        c = GridCRSContract(crs="", dem_source="COP30", cell_size_degrees=0.5)
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_missing_both_cell_sizes_fails(self):
        c = GridCRSContract(crs="EPSG:4326", dem_source="COP30")
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_negative_cell_size_fails(self):
        c = GridCRSContract(
            crs="EPSG:4326", dem_source="COP30", cell_size_degrees=-1.0
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_both_cell_sizes_fails(self):
        c = GridCRSContract(
            crs="EPSG:4326", dem_source="COP30",
            cell_size_degrees=0.5, cell_size_meters=500.0,
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_degree_size_with_projected_crs_fails(self):
        c = GridCRSContract(
            crs="EPSG:32644", dem_source="SRTM", cell_size_degrees=0.5,
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_meter_size_with_geographic_crs_fails(self):
        c = GridCRSContract(
            crs="EPSG:4326", dem_source="COP30", cell_size_meters=500.0,
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_nan_cell_size_fails(self):
        c = GridCRSContract(
            crs="EPSG:4326", dem_source="COP30", cell_size_degrees=float('nan'),
        )
        with self.assertRaises(ContractViolationError):
            c.validate()


class TestRegionElevationContract(unittest.TestCase):

    def test_valid_contract_passes(self):
        c = RegionElevationContract(
            pilot_region_id="Partner-PILOT-01",
            pilot_region_name="Leh-Ladakh",
            elevation_bands_m=(2400, 3000, 3600, 4200),
            approved_by="Partner-Scientist-2",
            approved_at="2026-07-18T00:00:00Z",
        )
        c.validate()
        self.assertTrue(c.is_Partner_approved)

    def test_empty_region_id_fails(self):
        c = RegionElevationContract(
            pilot_region_id="",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 3000),
            approved_by="Partner",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_unsorted_bands_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(3600, 2400, 4200),
            approved_by="Partner",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_no_approver_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 3000),
            approved_by="",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_not_approved_returns_false(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 3000),
            approved_by="",
        )
        self.assertFalse(c.is_Partner_approved)

    def test_empty_region_name_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="",
            elevation_bands_m=(2400, 3000),
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_whitespace_region_name_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="   ",
            elevation_bands_m=(2400, 3000),
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_duplicate_bands_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 2400, 3000),
            approved_by="Partner",
            approved_at="2026-07-18T00:00:00Z",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_missing_approved_at_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 3000),
            approved_by="Partner",
            approved_at="",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_invalid_approved_at_fails(self):
        c = RegionElevationContract(
            pilot_region_id="R1",
            pilot_region_name="Test",
            elevation_bands_m=(2400, 3000),
            approved_by="Partner",
            approved_at="not-a-date",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()


class TestEvidenceCaseContract(unittest.TestCase):

    def test_valid_contract_passes(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner-Scientist-3",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="Partner-bulletin-2026-07",
        )
        c.validate()

    def test_missing_hash_fails(self):
        c = EvidenceCaseContract(
            provenance_hash="",
            reviewer="Partner",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_missing_reviewer_fails(self):
        c = EvidenceCaseContract(
            provenance_hash="abc123",
            reviewer="",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_short_hash_fails(self):
        c = EvidenceCaseContract(
            provenance_hash="abc123",
            reviewer="Partner",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_inverted_time_window_fails(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner",
            valid_from="2026-07-19T00:00:00Z",
            valid_to="2026-07-18T00:00:00Z",
            truth_set_reference="ref",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_same_time_window_fails(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-18T00:00:00Z",
            truth_set_reference="ref",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_invalid_metric_fails(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
            metrics=("brier", "mse"),
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_invalid_decision_fails(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
            decision="approve",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()

    def test_valid_decision_select_passes(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner",
            valid_from="2026-07-18T00:00:00Z",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
            decision="select",
        )
        c.validate()

    def test_invalid_valid_from_fails(self):
        c = EvidenceCaseContract(
            provenance_hash=compute_provenance_hash({"test": True}),
            reviewer="Partner",
            valid_from="not-a-date",
            valid_to="2026-07-19T00:00:00Z",
            truth_set_reference="ref",
        )
        with self.assertRaises(ContractViolationError):
            c.validate()


class TestUtilities(unittest.TestCase):

    def test_provenance_hash_deterministic(self):
        h1 = compute_provenance_hash({"a": 1, "b": 2})
        h2 = compute_provenance_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_provenance_hash_different_payloads(self):
        h1 = compute_provenance_hash({"a": 1})
        h2 = compute_provenance_hash({"a": 2})
        self.assertNotEqual(h1, h2)

    def test_provenance_hash_rejects_non_serializable(self):
        with self.assertRaises(ContractViolationError):
            compute_provenance_hash({"obj": object()})

    def test_utc_now_iso_returns_string(self):
        ts = utc_now_iso()
        self.assertIsInstance(ts, str)
        self.assertIn("T", ts)


if __name__ == "__main__":
    unittest.main()
