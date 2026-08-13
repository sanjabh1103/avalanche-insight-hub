"""Contract and adversarial tests for the candidate Pir Panjal case."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.common.pir_panjal_poc_case import (
    PirPanjalPocCaseError,
    load_pir_panjal_poc_case,
    validate_pir_panjal_forcing_consistency,
    validate_pir_panjal_poc_case_bytes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = REPO_ROOT / "docs" / "MVP4" / "00_governance" / "PIR_PANJAL_POC_CASE_MANIFEST.json"


class PirPanjalPocCaseTests(unittest.TestCase):
    def test_candidate_case_loads_and_is_not_native_ready(self) -> None:
        # Candidate bindings point at optional local/open-data artifacts that
        # are intentionally not committed to either GitHub repository. The
        # hosted workflow applies the stricter verify_files=True gate once an
        # approved bundle has been supplied; this test checks case semantics.
        case = load_pir_panjal_poc_case(CASE_PATH, repository_root=REPO_ROOT, verify_files=False)
        self.assertEqual(case.region_key, "pir_panjal_nw_himalaya")
        self.assertEqual(case.elevation_band, "middle")
        self.assertEqual(case.horizon_hours, 48)
        self.assertEqual(case.ensemble_members, 1)
        self.assertFalse(case.native_execution_allowed)
        self.assertEqual(case.event["location_name"], "Gulmarg")

    def test_case_rejects_wrong_region(self) -> None:
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        record["region_key"] = "himalayas_nepal"
        with self.assertRaisesRegex(PirPanjalPocCaseError, "region_key"):
            validate_pir_panjal_poc_case_bytes(json.dumps(record).encode("utf-8"))

    def test_case_rejects_approved_geometry(self) -> None:
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        record["site"]["approved"] = True
        with self.assertRaisesRegex(PirPanjalPocCaseError, "approved"):
            validate_pir_panjal_poc_case_bytes(json.dumps(record).encode("utf-8"))

    def test_case_rejects_non_48_hour_window(self) -> None:
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        record["evaluation_window"]["end"] = "2024-02-23T00:00:00Z"
        with self.assertRaisesRegex(PirPanjalPocCaseError, "exactly 48"):
            validate_pir_panjal_poc_case_bytes(json.dumps(record).encode("utf-8"))

    def test_case_rejects_naive_timestamp(self) -> None:
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        record["initial_state"]["start"] = "2023-10-01T00:00:00"
        with self.assertRaisesRegex(PirPanjalPocCaseError, "UTC"):
            validate_pir_panjal_poc_case_bytes(json.dumps(record).encode("utf-8"))

    def test_case_rejects_path_traversal(self) -> None:
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        record["file_bindings"]["dem_tile"]["path"] = "../outside.hgt"
        with self.assertRaisesRegex(PirPanjalPocCaseError, "safe relative"):
            validate_pir_panjal_poc_case_bytes(json.dumps(record).encode("utf-8"))

    def test_case_rejects_tampered_bound_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.json"
            source.write_text("original", encoding="utf-8")
            record = {
                "schema_version": "pir_panjal_poc_case_v1",
                "case_id": "case",
                "region_key": "pir_panjal_nw_himalaya",
                "elevation_band": "middle",
                "elevation_min_m": 3200,
                "elevation_max_m": 4000,
                "horizon_hours": 48,
                "ensemble_members": 1,
                "case_status": "retrospective_candidate",
                "evidence_class": "pipeline-proof-only",
                "approved": False,
                "scientific_validation_eligible": False,
                "official_warning_eligible": False,
                "selection_rationale": "test",
                "site": {
                    "site_id": "site",
                    "latitude": 34.0,
                    "longitude": 74.0,
                    "dem_elevation_m": 3359.0,
                    "slope_deg": 30.0,
                    "aspect_deg": 0.0,
                    "geometry_status": "candidate_fixture",
                    "approval_state": "candidate_only",
                    "approved": False,
                    "source_point_index": 0,
                    "source_elevation_m": 3500.0,
                    "site_to_source_point_km": 1.0,
                },
                "primary_event": {
                    "event_id": "event",
                    "source": "HiAVAL",
                    "source_row_sha256": "a" * 64,
                    "event_time_start": "2024-02-22T00:00:00Z",
                    "event_time_end": "2024-02-23T00:00:00Z",
                    "event_type": "snow avalanches",
                    "location_name": "Gulmarg",
                    "distance_from_site_km": 1.0,
                    "timestamp_precision": "day",
                    "rights": "CC BY 4.0",
                    "rights_status": "research_only",
                    "site_specific_validation": False,
                    "is_accuracy_label": False,
                },
                "evaluation_window": {
                    "start": "2024-02-22T00:00:00Z",
                    "end": "2024-02-24T00:00:00Z",
                },
                "forcing": {
                    "status": "candidate_fixture",
                    "source_id": "source",
                    "model_id": "model",
                    "license_review_status": "pending",
                    "snapshot_manifest": {"path": "source.json", "sha256": "a" * 64},
                    "raw_source_points": {"path": "source.json", "sha256": "a" * 64},
                },
                "initial_state": {
                    "strategy": "early_season_spinup",
                    "start": "2023-10-01T00:00:00Z",
                    "status": "candidate_assumption",
                    "approved": False,
                },
                "file_bindings": {
                    "snapshot_manifest": {"path": "source.json", "sha256": "a" * 64},
                    "raw_source_points": {"path": "source.json", "sha256": "a" * 64},
                    "dem_tile": {"path": "source.json", "sha256": "a" * 64},
                    "event_inventory": {"path": "source.json", "sha256": "a" * 64},
                },
            }
            source.write_text("tampered", encoding="utf-8")
            manifest = root / "case.json"
            manifest.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(PirPanjalPocCaseError, "sha256 mismatch"):
                load_pir_panjal_poc_case(manifest, repository_root=root, verify_files=True)

    def test_forcing_binding_rejects_source_model_drift(self) -> None:
        case = load_pir_panjal_poc_case(CASE_PATH, repository_root=REPO_ROOT, verify_files=False)
        # Candidate forcing artifacts are intentionally ignored and are not
        # available in a clean GitHub checkout. Build the smallest exact
        # contract in memory so this test verifies source/model drift rather
        # than depending on a workstation-local artifact.
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        window = record["evaluation_window"]
        forcing = {
            "case_id": case.case_id,
            "region_key": case.region_key,
            "elevation_band": case.elevation_band,
            "horizon_hours": case.horizon_hours,
            "ensemble_members": case.ensemble_members,
            "source_id": case.forcing["source_id"],
            "model_id": case.forcing["model_id"],
            "forecast_role": case.forcing["forecast_role"],
            "license_review_status": case.forcing["license_review_status"],
            "target_resolution_m": case.forcing["target_resolution_m"],
            "source_native_resolution_m": case.forcing["source_native_resolution_m"],
            "effective_information_scale_m": case.forcing["effective_information_scale_m"],
            "no_3km_skill_claim": case.forcing["no_3km_skill_claim"],
            "target_site": dict(case.site),
            "valid_from": case.initial_state["start"],
            "valid_to": window["end"],
            "initial_state_manifest_sha256": case.initial_state["manifest_sha256"],
            "sample_count": 3504,
            "production_eligible": False,
            "native_execution_ready": False,
        }
        forcing["source_id"] = "unexpected_source"
        with self.assertRaisesRegex(PirPanjalPocCaseError, "source_id mismatch"):
            validate_pir_panjal_forcing_consistency(case, forcing)

    def test_forcing_binding_accepts_exact_case_copy(self) -> None:
        case = load_pir_panjal_poc_case(CASE_PATH, repository_root=REPO_ROOT, verify_files=False)
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        window = record["evaluation_window"]
        forcing = {
            "case_id": case.case_id,
            "region_key": case.region_key,
            "elevation_band": case.elevation_band,
            "horizon_hours": case.horizon_hours,
            "ensemble_members": case.ensemble_members,
            "source_id": case.forcing["source_id"],
            "model_id": case.forcing["model_id"],
            "forecast_role": case.forcing["forecast_role"],
            "license_review_status": case.forcing["license_review_status"],
            "target_resolution_m": case.forcing["target_resolution_m"],
            "source_native_resolution_m": case.forcing["source_native_resolution_m"],
            "effective_information_scale_m": case.forcing["effective_information_scale_m"],
            "no_3km_skill_claim": case.forcing["no_3km_skill_claim"],
            "target_site": dict(case.site),
            "valid_from": case.initial_state["start"],
            "valid_to": window["end"],
            "initial_state_manifest_sha256": case.initial_state["manifest_sha256"],
            "sample_count": 3504,
            "production_eligible": False,
            "native_execution_ready": False,
        }
        validate_pir_panjal_forcing_consistency(case, forcing)

    def test_forcing_binding_accepts_one_source_warmup_hour(self) -> None:
        case = load_pir_panjal_poc_case(CASE_PATH, repository_root=REPO_ROOT, verify_files=False)
        record = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        window = record["evaluation_window"]
        forcing = {
            "case_id": case.case_id,
            "region_key": case.region_key,
            "elevation_band": case.elevation_band,
            "horizon_hours": case.horizon_hours,
            "ensemble_members": case.ensemble_members,
            "source_id": case.forcing["source_id"],
            "model_id": case.forcing["model_id"],
            "forecast_role": case.forcing["forecast_role"],
            "license_review_status": case.forcing["license_review_status"],
            "target_resolution_m": case.forcing["target_resolution_m"],
            "source_native_resolution_m": case.forcing["source_native_resolution_m"],
            "effective_information_scale_m": case.forcing["effective_information_scale_m"],
            "no_3km_skill_claim": case.forcing["no_3km_skill_claim"],
            "target_site": dict(case.site),
            "valid_from": case.initial_state["start"],
            "valid_to": window["end"],
            "source_window": {
                "start": "2023-09-29T00:00:00Z",
                "end": window["end"],
            },
            "warmup_hours": 48,
            "source_sample_count": 3552,
            "initial_state_manifest_sha256": case.initial_state["manifest_sha256"],
            "sample_count": 3504,
            "production_eligible": False,
            "native_execution_ready": False,
        }
        validate_pir_panjal_forcing_consistency(case, forcing)


if __name__ == "__main__":
    unittest.main()
