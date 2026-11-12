"""Adversarial regression tests for Track 1/T2A lane contracts.

These tests encode the specific fail-open cases identified in the Codex
audit. They MUST all pass after the contracts are hardened.

Each test is named to match the audit gap ID (G2-G5, G9, G11).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.track_contracts import (
    PartnerLabelRecordV1,
    LabelValidationError,
    DangerPredictionV1,
    PredictionValidationError,
    TrackExperimentManifestV1,
    ManifestValidationError,
    T2A_ALLOWLIST,
    T2A_DENYLIST,
    TRACK1_ALLOWLIST,
    validate_t2a_features,
    validate_track1_features,
    FeatureContaminationError,
    ClaimRecord,
    ClaimValidationError,
    ClaimState,
)
from backend.common.track_contracts.label_record import PartnerLabelInventoryV1
from backend.common.track_contracts.lane_allowlists import (
    normalize_feature_name,
    check_feature_lineage,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class TestG2EmptyFeatureListFailsClosed(unittest.TestCase):
    """G2: Lane feature gates fail open — empty T2A and Track 1 feature lists pass."""

    def test_empty_t2a_features_rejected(self):
        """Empty feature list must NOT pass T2A validation."""
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features([])

    def test_empty_track1_features_rejected(self):
        """Empty feature list must NOT pass Track 1 validation."""
        with self.assertRaises(FeatureContaminationError):
            validate_track1_features([])

    def test_single_feature_t2a_rejected(self):
        """A single feature is insufficient for T2A — require minimum families."""
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(["elevation"])

    def test_t2a_requires_open_forcing_family(self):
        """T2A must have at least one open-forcing feature, not just terrain."""
        terrain_only = ["elevation", "slope", "aspect", "terrain_roughness",
                        "curvature_proxy", "northness", "eastness", "aspect_loading"]
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(terrain_only)

    def test_t2a_requires_terrain_family(self):
        """T2A must have at least one terrain feature, not just forcing."""
        forcing_only = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
                        "precipitation", "snowfall", "shortwave_radiation"]
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(forcing_only)

    def test_track1_requires_station_family(self):
        """Track 1 must have at least one station/anchor feature."""
        no_station = ["elevation", "slope", "aspect", "snowpack", "ram_hardness",
                      "shear_strength", "stability_index"]
        with self.assertRaises(FeatureContaminationError):
            validate_track1_features(no_station)

    def test_track1_requires_snowpack_family(self):
        """Track 1 must have at least one SNOWPACK feature."""
        no_snowpack = ["elevation", "slope", "aspect", "station_snow_depth",
                       "station_temperature", "station_wind"]
        with self.assertRaises(FeatureContaminationError):
            validate_track1_features(no_snowpack)

    def test_denylist_variant_snowpack_uppercase_rejected(self):
        """Denylist must catch 'SNOWPACK' not just 'snowpack'."""
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(["temperature_2m", "elevation", "slope", "SNOWPACK"])

    def test_denylist_variant_station_camelcase_rejected(self):
        """Denylist must catch 'stationSnowDepth' not just 'station_snow_depth'."""
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(["temperature_2m", "elevation", "slope", "stationSnowDepth"])

    def test_denylist_variant_snowpack_with_spaces_rejected(self):
        """Denylist must catch 'snow pack' and 'snow-pack' variants."""
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(["temperature_2m", "elevation", "slope", "snow pack"])

    def test_denylist_variant_stability_index_abbrev_rejected(self):
        """Denylist must catch 'ssi', 'SSI', 'Sk38', 'sk38' — SNOWPACK stability aliases."""
        for variant in ["ssi", "SSI", "Sk38", "sk38", "Sn38", "sn38"]:
            with self.assertRaises(FeatureContaminationError):
                validate_t2a_features(["temperature_2m", "elevation", "slope", variant])


class TestG3LabelInventoryFabricatedCounts(unittest.TestCase):
    """G3: Label inventory accepts false evidence — fabricated counts pass."""

    def test_empty_inventory_rejected(self):
        """Empty inventory with no records must NOT pass."""
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=[],
            record_counts_by_level={1: 100, 2: 50, 3: 30, 4: 10, 5: 2},
            level_5_support=True,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_fabricated_counts_rejected(self):
        """Counts that don't match actual records must NOT pass."""
        # Create 2 real records but claim 100 in counts
        record = PartnerLabelRecordV1(
            level=3, reference_unit="pir_panjal",
            issue_time=_utc(2024, 2, 22, 6),
            valid_time_start=_utc(2024, 2, 22, 6),
            valid_time_end=_utc(2024, 2, 23, 6),
            geography="pir_panjal", elevation_band="3000-4000m",
            aspect_applicability="all", issuer="Partner", revision=0,
            provenance="hash_abc", rights_status="approved",
            quality_status="reviewed", approved_by="scientist_1",
            approved_at=_utc(2024, 2, 22, 6),
        )
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=[record, record],
            record_counts_by_level={1: 100, 2: 50, 3: 30, 4: 10, 5: 2},  # fabricated
            level_5_support=True,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_counts_must_be_recomputed_from_records(self):
        """Counts must match actual record levels, not caller-supplied values."""
        records = []
        for level in [1, 2, 3, 4, 5]:
            records.append(PartnerLabelRecordV1(
                level=level, reference_unit="pir_panjal",
                issue_time=_utc(2024, 2, 22, 6),
                valid_time_start=_utc(2024, 2, 22, 6),
                valid_time_end=_utc(2024, 2, 23, 6),
                geography="pir_panjal", elevation_band="3000-4000m",
                aspect_applicability="all", issuer="Partner", revision=0,
                provenance="hash_abc", rights_status="approved",
                quality_status="reviewed", approved_by="scientist_1",
                approved_at=_utc(2024, 2, 22, 6),
            ))
        # Correct counts should pass
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=records,
            record_counts_by_level={1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            level_5_support=True,
        )
        inventory.validate()  # should not raise

    def test_level_5_support_requires_actual_level_5_records(self):
        """level_5_support=True must not pass if no Level 5 records exist."""
        records = []
        for level in [1, 2, 3, 4]:  # no level 5
            records.append(PartnerLabelRecordV1(
                level=level, reference_unit="pir_panjal",
                issue_time=_utc(2024, 2, 22, 6),
                valid_time_start=_utc(2024, 2, 22, 6),
                valid_time_end=_utc(2024, 2, 23, 6),
                geography="pir_panjal", elevation_band="3000-4000m",
                aspect_applicability="all", issuer="Partner", revision=0,
                provenance="hash_abc", rights_status="approved",
                quality_status="reviewed", approved_by="scientist_1",
                approved_at=_utc(2024, 2, 22, 6),
            ))
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=records,
            record_counts_by_level={1: 1, 2: 1, 3: 1, 4: 1, 5: 0},
            level_5_support=True,  # claims support but no level 5 records
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_duplicate_revisions_rejected(self):
        """Same level+issue_time+reference_unit with same revision is invalid."""
        base = PartnerLabelRecordV1(
            level=3, reference_unit="pir_panjal",
            issue_time=_utc(2024, 2, 22, 6),
            valid_time_start=_utc(2024, 2, 22, 6),
            valid_time_end=_utc(2024, 2, 23, 6),
            geography="pir_panjal", elevation_band="3000-4000m",
            aspect_applicability="all", issuer="Partner", revision=0,
            provenance="hash_abc", rights_status="approved",
            quality_status="reviewed", approved_by="scientist_1",
            approved_at=_utc(2024, 2, 22, 6),
        )
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=[base, base],  # exact duplicate
            record_counts_by_level={3: 2},
            level_5_support=False,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_inconsistent_reference_units_rejected(self):
        """All records must share the inventory's reference_unit."""
        r1 = PartnerLabelRecordV1(
            level=3, reference_unit="pir_panjal",
            issue_time=_utc(2024, 2, 22, 6),
            valid_time_start=_utc(2024, 2, 22, 6),
            valid_time_end=_utc(2024, 2, 23, 6),
            geography="pir_panjal", elevation_band="3000-4000m",
            aspect_applicability="all", issuer="Partner", revision=0,
            provenance="hash_abc", rights_status="approved",
            quality_status="reviewed", approved_by="scientist_1",
            approved_at=_utc(2024, 2, 22, 6),
        )
        r2 = PartnerLabelRecordV1(
            level=4, reference_unit="different_region",
            issue_time=_utc(2024, 2, 23, 6),
            valid_time_start=_utc(2024, 2, 23, 6),
            valid_time_end=_utc(2024, 2, 24, 6),
            geography="different_region", elevation_band="3000-4000m",
            aspect_applicability="all", issuer="Partner", revision=0,
            provenance="hash_def", rights_status="approved",
            quality_status="reviewed", approved_by="scientist_1",
            approved_at=_utc(2024, 2, 23, 6),
        )
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=[r1, r2],
            record_counts_by_level={3: 1, 4: 1},
            level_5_support=False,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()


class TestG4ClaimStateTransitionsUnsafe(unittest.TestCase):
    """G4: Claim-state transitions are unsafe — rejected→framework_ready allowed."""

    def test_rejected_to_framework_ready_rejected(self):
        """A rejected claim cannot transition to framework_ready."""
        self.assertFalse(ClaimState.can_transition("rejected", "framework_ready"))

    def test_rejected_is_terminal(self):
        """Rejected state cannot transition to ANY non-rejected state."""
        for target in ("unapproved", "framework_ready", "gates_passed",
                       "training_eligible", "trained", "evaluated",
                       "promotion_eligible"):
            self.assertFalse(ClaimState.can_transition("rejected", target),
                             f"rejected→{target} should be forbidden")

    def test_public_operational_claim_requires_evidence(self):
        """A claim with 'operational readiness' language must fail without evidence."""
        with self.assertRaises(ClaimValidationError):
            ClaimRecord(
                claim_id="c1",
                statement="System has operational readiness",
                track="t2a",
                claim_state="framework_ready",
                proof_level="local_artifact",
                permitted_audience="internal_only",
                controlling_source="test",
                created_at=_utc(2026, 8, 17),
            ).validate()

    def test_validated_himalayan_accuracy_requires_himalayan_validated_proof(self):
        """A claim of 'validated Himalayan accuracy' requires himalayan_validated proof level."""
        with self.assertRaises(ClaimValidationError):
            ClaimRecord(
                claim_id="c2",
                statement="We have validated Himalayan accuracy",
                track="t2a",
                claim_state="evaluated",
                proof_level="local_artifact",  # insufficient
                permitted_audience="Partner_review",
                controlling_source="test",
                created_at=_utc(2026, 8, 17),
            ).validate()

    def test_state_must_match_proof_level(self):
        """Claim state must be consistent with proof level."""
        # gates_passed requires at least swiss_reproduction or higher proof
        with self.assertRaises(ClaimValidationError):
            ClaimRecord(
                claim_id="c3",
                statement="Gates have passed",
                track="t2a",
                claim_state="gates_passed",
                proof_level="none",  # no proof but claiming gates passed
                permitted_audience="Partner_signed",
                controlling_source="test",
                created_at=_utc(2026, 8, 17),
            ).validate()


class TestG5PromotionGateIncomplete(unittest.TestCase):
    """G5: Promotion gate is incomplete — no evaluation evidence required."""

    def test_promotion_requires_evaluated_state(self):
        """Cannot jump from trained to promotion_eligible."""
        self.assertFalse(ClaimState.can_transition("trained", "promotion_eligible"))

    def test_promotion_manifest_requires_evaluation_artifacts(self):
        """Manifest with promotion_eligible must have evaluation evidence."""
        with self.assertRaises(ManifestValidationError):
            TrackExperimentManifestV1(
                track="t2a",
                experiment_id="exp1",
                target_hash="a" * 64,
                source_hash="b" * 64,
                feature_hash="c" * 64,
                split_hash="d" * 64,
                approvals=("approval_1",),
                claim_state="promotion_eligible",
                fitted_artifact_ids=("model_1",),  # has model but no evaluation
            ).validate()

    def test_promotion_requires_independent_observations(self):
        """Promotion must declare independent observation evidence."""
        with self.assertRaises(ManifestValidationError):
            TrackExperimentManifestV1(
                track="t2a",
                experiment_id="exp1",
                target_hash="a" * 64,
                source_hash="b" * 64,
                feature_hash="c" * 64,
                split_hash="d" * 64,
                approvals=("approval_1",),
                claim_state="promotion_eligible",
                fitted_artifact_ids=("model_1",),
            ).validate()

    def test_hash_must_be_real_hexadecimal(self):
        """Hashes must be valid 64-char hexadecimal, not just any 64-char string."""
        with self.assertRaises(ManifestValidationError):
            TrackExperimentManifestV1(
                track="t2a",
                experiment_id="exp1",
                target_hash="z" * 64,  # 'z' is not hex
                source_hash="b" * 64,
                feature_hash="c" * 64,
                split_hash="d" * 64,
                approvals=("approval_1",),
                claim_state="framework_ready",
            ).validate()


class TestG9PredictionPermitsNonPublishable(unittest.TestCase):
    """G9: Prediction contract permits non-publishable output — calibration_method='none' accepted."""

    def test_uncalibrated_prediction_rejected_for_publishable_track(self):
        """calibration_method='none' must be rejected for publishable predictions."""
        with self.assertRaises(PredictionValidationError):
            DangerPredictionV1(
                probabilities=(0.1, 0.2, 0.5, 0.15, 0.05),
                predicted_level=3,
                reference_unit="pir_panjal",
                valid_time_start=_utc(2024, 2, 22, 6),
                valid_time_end=_utc(2024, 2, 23, 6),
                issue_time=_utc(2024, 2, 22, 6),
                model_id="t2a_rf_v1",
                snapshot_id="a" * 64,
                track="t2a",
                calibration_method="none",  # uncalibrated
            ).validate()

    def test_uncalibrated_prediction_allowed_only_with_diagnostic_flag(self):
        """Uncalibrated predictions allowed only with explicit diagnostic status."""
        pred = DangerPredictionV1(
            probabilities=(0.1, 0.2, 0.5, 0.15, 0.05),
            predicted_level=3,
            reference_unit="pir_panjal",
            valid_time_start=_utc(2024, 2, 22, 6),
            valid_time_end=_utc(2024, 2, 23, 6),
            issue_time=_utc(2024, 2, 22, 6),
            model_id="t2a_rf_v1",
            snapshot_id="a" * 64,
            track="t2a",
            calibration_method="none",
            is_diagnostic_only=True,
        )
        pred.validate()  # should pass with diagnostic flag


class TestG11PublicAPIIncomplete(unittest.TestCase):
    """G11: Public package API is incomplete — PartnerLabelInventoryV1 not exported."""

    def test_Partner_label_inventory_exported(self):
        """PartnerLabelInventoryV1 must be importable from track_contracts."""
        from backend.common.track_contracts import PartnerLabelInventoryV1
        self.assertIsNotNone(PartnerLabelInventoryV1)

    def test_label_validation_error_exported(self):
        """LabelValidationError must be importable from track_contracts."""
        from backend.common.track_contracts import LabelValidationError
        self.assertIsNotNone(LabelValidationError)

    def test_normalize_feature_name_exported(self):
        """normalize_feature_name must be importable from track_contracts."""
        from backend.common.track_contracts import normalize_feature_name
        self.assertIsNotNone(normalize_feature_name)

    def test_check_feature_lineage_exported(self):
        """check_feature_lineage must be importable from track_contracts."""
        from backend.common.track_contracts import check_feature_lineage
        self.assertIsNotNone(check_feature_lineage)


if __name__ == "__main__":
    unittest.main()
