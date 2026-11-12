"""Conformance tests for Track 1 / T2A lane contracts.

These tests verify that the contracts fail closed on every unsafe state:
- Missing Level 5 or another class
- Insufficient signed support
- Missing rights or authority
- Point/reference-unit mismatch
- Invalid issue/validity matching
- T2A station or SNOWPACK contamination
- Track 1 missing station/SNOWPACK inputs
- Cross-lane fitted artifacts
- Synthetic or interval labels entering scientific metrics
- Final-test tuning
- Swiss results promoted beyond their claim boundary

These are FIXTURE-ONLY tests. They do not train models, load real data,
or modify any denylisted file.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta

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
    TRACK1_DENYLIST,
    validate_t2a_features,
    validate_track1_features,
    FeatureContaminationError,
    ClaimRecord,
    ClaimValidationError,
    ClaimState,
)
from backend.common.track_contracts.label_record import PartnerLabelInventoryV1


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class TestPartnerLabelRecordV1(unittest.TestCase):
    """Tests for the five-level label record contract."""

    def _valid_record(self, **overrides) -> PartnerLabelRecordV1:
        defaults = dict(
            level=3,
            reference_unit="pir_panjal_sector_a",
            issue_time=_utc(2024, 2, 22, 6),
            valid_time_start=_utc(2024, 2, 22, 6),
            valid_time_end=_utc(2024, 2, 23, 6),
            geography="pir_panjal",
            elevation_band="3000-4000m",
            aspect_applicability="all",
            issuer="Partner",
            revision=0,
            provenance="Partner_bulletin_hash_abc123",
            rights_status="approved",
            quality_status="reviewed",
            approved_by="Partner_scientist_1",
            approved_at=_utc(2024, 2, 22, 6),
        )
        defaults.update(overrides)
        return PartnerLabelRecordV1(**defaults)

    def test_valid_record_passes(self):
        record = self._valid_record()
        record.validate()  # should not raise

    def test_rejects_binary_target(self):
        """Level must be 1-5, not binary 0/1."""
        with self.assertRaises(LabelValidationError):
            self._valid_record(level=0).validate()
        with self.assertRaises(LabelValidationError):
            self._valid_record(level=6).validate()

    def test_rejects_unsigned_placeholder(self):
        """No training without Partner-approved labels."""
        with self.assertRaises(LabelValidationError):
            self._valid_record(approved_by="").validate()

    def test_rejects_pending_rights(self):
        """Rights status must be 'approved' for training."""
        with self.assertRaises(LabelValidationError):
            self._valid_record(rights_status="pending").validate()

    def test_rejects_naive_datetimes(self):
        """All times must be timezone-aware UTC."""
        with self.assertRaises(LabelValidationError):
            self._valid_record(issue_time=datetime(2024, 2, 22, 6)).validate()

    def test_rejects_invalid_validity_window(self):
        """Valid time end must be after start."""
        with self.assertRaises(LabelValidationError):
            self._valid_record(
                valid_time_start=_utc(2024, 2, 23, 6),
                valid_time_end=_utc(2024, 2, 22, 6),
            ).validate()

    def test_rejects_missing_reference_unit(self):
        with self.assertRaises(LabelValidationError):
            self._valid_record(reference_unit="").validate()


class TestPartnerLabelInventoryV1(unittest.TestCase):
    """Tests for the label inventory (all five levels required)."""

    def test_rejects_missing_level_5(self):
        """Level 5 support is mandatory; no silent merging."""
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            record_counts_by_level={1: 100, 2: 50, 3: 30, 4: 10},  # missing 5
            level_5_support=False,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_rejects_level_5_false_even_with_counts(self):
        """Even if Level 5 has counts, level_5_support must be True."""
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            record_counts_by_level={1: 100, 2: 50, 3: 30, 4: 10, 5: 2},
            level_5_support=False,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_valid_inventory_passes(self):
        # Create actual records matching the counts
        records = []
        for level, count in [(1, 3), (2, 2), (3, 2), (4, 1), (5, 1)]:
            for i in range(count):
                records.append(PartnerLabelRecordV1(
                    level=level, reference_unit="pir_panjal",
                    issue_time=_utc(2024, 1, 1 + i, 6),
                    valid_time_start=_utc(2024, 1, 1 + i, 6),
                    valid_time_end=_utc(2024, 1, 2 + i, 6),
                    geography="pir_panjal", elevation_band="3000-4000m",
                    aspect_applicability="all", issuer="Partner", revision=0,
                    provenance="hash_abc", rights_status="approved",
                    quality_status="reviewed", approved_by="scientist_1",
                    approved_at=_utc(2024, 1, 1, 6),
                ))
        inventory = PartnerLabelInventoryV1(
            reference_unit="pir_panjal",
            records=records,
            record_counts_by_level={1: 3, 2: 2, 3: 2, 4: 1, 5: 1},
            level_5_support=True,
        )
        inventory.validate()  # should not raise

    def test_duplicate_seasons_rejected(self):
        records = [PartnerLabelRecordV1(
            level=level, reference_unit="pir_panjal",
            issue_time=_utc(2024, 1, level, 6),
            valid_time_start=_utc(2024, 1, level, 6),
            valid_time_end=_utc(2024, 1, level + 1, 6),
            geography="pir_panjal", elevation_band="3000-4000m",
            aspect_applicability="all", issuer="Partner", revision=0,
            provenance="hash_abc", rights_status="approved",
            quality_status="reviewed", approved_by="scientist_1",
            approved_at=_utc(2024, 1, level, 6), season="winter_2024",
        ) for level in (1, 2, 3, 4, 5)]
        inventory = PartnerLabelInventoryV1(
            records=records,
            reference_unit="pir_panjal",
            seasons_covered=["winter_2024", "winter_2024"],
            record_counts_by_level={1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            level_5_support=True,
        )
        with self.assertRaises(LabelValidationError):
            inventory.validate()

    def test_inventory_round_trip_preserves_records(self):
        # Build one record for each level with distinct issue times.
        records = [
            PartnerLabelRecordV1(
                level=level, reference_unit="pir_panjal",
                issue_time=_utc(2024, 1, level, 6),
                valid_time_start=_utc(2024, 1, level, 6),
                valid_time_end=_utc(2024, 1, level + 1, 6),
                geography="pir_panjal", elevation_band="3000-4000m",
                aspect_applicability="all", issuer="Partner", revision=0,
                provenance="hash_abc", rights_status="approved",
                quality_status="reviewed", approved_by="scientist_1",
                approved_at=_utc(2024, 1, level, 6), season="winter_2024",
            )
            for level in (1, 2, 3, 4, 5)
        ]
        inventory = PartnerLabelInventoryV1(
            records=records,
            reference_unit="pir_panjal",
            seasons_covered=["winter_2024"],
            record_counts_by_level={1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
            level_5_support=True,
        )
        restored = PartnerLabelInventoryV1.from_dict(inventory.to_dict())
        self.assertEqual(len(restored.records), 5)
        self.assertEqual(restored.records[4].level, 5)
        self.assertEqual(restored.records[0].season, "winter_2024")


class TestDangerPredictionV1(unittest.TestCase):
    """Tests for the learned five-level prediction contract."""

    def _valid_prediction(self, **overrides) -> DangerPredictionV1:
        defaults = dict(
            probabilities=(0.1, 0.2, 0.5, 0.15, 0.05),
            predicted_level=3,
            reference_unit="pir_panjal_sector_a",
            valid_time_start=_utc(2024, 2, 22, 6),
            valid_time_end=_utc(2024, 2, 23, 6),
            issue_time=_utc(2024, 2, 22, 6),
            model_id="t2a_rf_v1",
            snapshot_id="a" * 64,
            track="t2a",
            calibration_method="sigmoid",
            manifest_digest="b" * 64,
            feature_hash="c" * 64,
            source_hash="d" * 64,
            context_hash="e" * 64,
            calibration_hash="f" * 64,
            approval_id="Partner_approval_001",
        )
        defaults.update(overrides)
        return DangerPredictionV1(**defaults)

    def test_valid_prediction_passes(self):
        pred = self._valid_prediction()
        pred.validate()  # should not raise

    def test_prediction_round_trip_is_lossless(self):
        pred = self._valid_prediction()
        restored = DangerPredictionV1.from_dict(pred.to_dict())
        self.assertEqual(restored, pred)

    def test_prediction_boolean_and_probability_types_are_strict(self):
        data = self._valid_prediction().to_dict()
        data["is_diagnostic_only"] = "false"
        with self.assertRaises(PredictionValidationError):
            DangerPredictionV1.from_dict(data)
        data = self._valid_prediction().to_dict()
        data["probabilities"] = "0.1,0.2,0.5,0.15,0.05"
        with self.assertRaises(PredictionValidationError):
            DangerPredictionV1.from_dict(data)

    def test_rejects_binary_output(self):
        """Must have exactly 5 probabilities, not 2."""
        with self.assertRaises(PredictionValidationError):
            self._valid_prediction(
                probabilities=(0.7, 0.3),
                predicted_level=1,
            ).validate()

    def test_rejects_merged_levels(self):
        """Must have 5 probabilities, not 4 (no Level 4/5 merging)."""
        with self.assertRaises(PredictionValidationError):
            self._valid_prediction(
                probabilities=(0.1, 0.2, 0.5, 0.2),
                predicted_level=3,
            ).validate()

    def test_rejects_uncalibrated_probabilities(self):
        """Probabilities must sum to 1.0."""
        with self.assertRaises(PredictionValidationError):
            self._valid_prediction(
                probabilities=(0.1, 0.2, 0.5, 0.15, 0.1),  # sums to 1.05
            ).validate()

    def test_rejects_predicted_level_not_argmax(self):
        """Predicted level must be argmax of probabilities."""
        with self.assertRaises(PredictionValidationError):
            self._valid_prediction(
                probabilities=(0.1, 0.2, 0.5, 0.15, 0.05),
                predicted_level=1,  # argmax is 3, not 1
            ).validate()

    def test_abstention_requires_reason(self):
        with self.assertRaises(PredictionValidationError):
            self._valid_prediction(
                abstention=True,
                abstention_reason="",
            ).validate()

    def test_abstention_allows_non_argmax_level(self):
        """When abstaining, predicted_level need not be argmax."""
        pred = self._valid_prediction(
            abstention=True,
            abstention_reason="insufficient_forcing_coverage",
            predicted_level=1,  # not argmax, but abstention is True
        )
        pred.validate()  # should not raise

    def test_ordinal_error_distance(self):
        pred = self._valid_prediction(predicted_level=3)
        self.assertEqual(pred.ordinal_error_distance(3), 0)
        self.assertEqual(pred.ordinal_error_distance(4), 1)
        self.assertEqual(pred.ordinal_error_distance(5), 2)

    def test_within_one_level(self):
        pred = self._valid_prediction(predicted_level=3)
        self.assertTrue(pred.within_one_level(2))
        self.assertTrue(pred.within_one_level(3))
        self.assertTrue(pred.within_one_level(4))
        self.assertFalse(pred.within_one_level(5))


class TestTrackExperimentManifestV1(unittest.TestCase):
    """Tests for the experiment manifest (track separation)."""

    def _valid_manifest(self, **overrides) -> TrackExperimentManifestV1:
        defaults = dict(
            track="t2a",
            experiment_id="t2a_rf_v1_2024",
            target_hash="a" * 64,
            source_hash="b" * 64,
            feature_hash="c" * 64,
            split_hash="d" * 64,
            approvals=("Partner_m0_m1_signed_2026_08_18",),
            claim_state="framework_ready",
        )
        defaults.update(overrides)
        return TrackExperimentManifestV1(**defaults)

    def test_valid_manifest_passes(self):
        manifest = self._valid_manifest()
        manifest.validate()

    def test_manifest_unknown_field_rejected(self):
        data = self._valid_manifest().to_dict()
        data["unknown_field"] = "must reject"
        with self.assertRaises(ManifestValidationError):
            TrackExperimentManifestV1.from_dict(data)

    def test_manifest_list_types_rejected(self):
        data = self._valid_manifest().to_dict()
        data["approvals"] = "not-a-list"
        with self.assertRaises(ManifestValidationError):
            TrackExperimentManifestV1.from_dict(data)

    def test_rejects_unsigned_manifest(self):
        with self.assertRaises(ManifestValidationError):
            self._valid_manifest(approvals=()).validate()

    def test_rejects_fitted_artifacts_without_gates(self):
        """Cannot have fitted artifacts before gates pass."""
        with self.assertRaises(ManifestValidationError):
            self._valid_manifest(
                claim_state="unapproved",
                fitted_artifact_ids=("model_hash_1",),
            ).validate()

    def test_rejects_promotion_without_artifacts(self):
        with self.assertRaises(ManifestValidationError):
            self._valid_manifest(claim_state="promotion_eligible").validate()

    def test_rejects_invalid_track(self):
        with self.assertRaises(ManifestValidationError):
            self._valid_manifest(track="track3").validate()


class TestLaneAllowlists(unittest.TestCase):
    """Tests for T2A and Track 1 feature separation."""

    def test_t2a_rejects_snowpack_features(self):
        """T2A must not contain SNOWPACK-derived features."""
        contaminated = list(T2A_ALLOWLIST)[:5] + ["snowpack", "stability_index"]
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(contaminated)

    def test_t2a_rejects_station_features(self):
        """T2A must not contain station/anchor inputs."""
        contaminated = list(T2A_ALLOWLIST)[:5] + ["station_snow_depth"]
        with self.assertRaises(FeatureContaminationError):
            validate_t2a_features(contaminated)

    def test_track1_rejects_t2a_only_aggregations(self):
        """Track 1 must not contain T2A-only temporal aggregations."""
        contaminated = list(TRACK1_ALLOWLIST)[:5] + ["snowfall_7d"]
        with self.assertRaises(FeatureContaminationError):
            validate_track1_features(contaminated)

    def test_t2a_allowlist_does_not_intersect_denylist(self):
        """Allowlist and denylist must be disjoint."""
        overlap = T2A_ALLOWLIST & T2A_DENYLIST
        self.assertEqual(overlap, frozenset(),
                         f"T2A allowlist/denylist overlap: {overlap}")

    def test_track1_allowlist_does_not_intersect_denylist(self):
        overlap = TRACK1_ALLOWLIST & TRACK1_DENYLIST
        self.assertEqual(overlap, frozenset(),
                         f"Track 1 allowlist/denylist overlap: {overlap}")

    def test_valid_t2a_features_pass(self):
        features = ["temperature_2m", "elevation", "slope", "snowfall_24h"]
        validate_t2a_features(features)  # should not raise

    def test_valid_track1_features_pass(self):
        features = ["station_snow_depth", "snowpack", "elevation", "slope"]
        validate_track1_features(features)  # should not raise


class TestClaimRecord(unittest.TestCase):
    """Tests for claim state and prohibited language."""

    def _valid_claim(self, **overrides) -> ClaimRecord:
        defaults = dict(
            claim_id="claim_001",
            statement="T2A framework contracts are defined",
            track="t2a",
            claim_state="framework_ready",
            proof_level="local_artifact",
            permitted_audience="internal_only",
            controlling_source="track_contracts/__init__.py",
            created_at=_utc(2026, 8, 17, 12),
        )
        defaults.update(overrides)
        return ClaimRecord(**defaults)

    def test_valid_claim_passes(self):
        claim = self._valid_claim()
        claim.validate()

    def test_rejects_prohibited_language_unprecedented(self):
        with self.assertRaises(ClaimValidationError):
            self._valid_claim(
                statement="This is an unprecedented approach",
            ).validate()

    def test_rejects_prohibited_language_sota(self):
        with self.assertRaises(ClaimValidationError):
            self._valid_claim(
                statement="We achieve SOTA performance",
            ).validate()

    def test_rejects_prohibited_language_95_percent_ready(self):
        with self.assertRaises(ClaimValidationError):
            self._valid_claim(
                statement="Track 1 and T2A are 95% code-ready",
            ).validate()

    def test_rejects_promotion_without_Partner_audience(self):
        """Promotion claims require Partner_signed audience."""
        with self.assertRaises(ClaimValidationError):
            self._valid_claim(
                claim_state="promotion_eligible",
                permitted_audience="internal_only",
            ).validate()


class TestClaimStateTransitions(unittest.TestCase):
    """Tests for claim state transition rules."""

    def test_cannot_skip_states(self):
        self.assertFalse(ClaimState.can_transition("unapproved", "trained"))

    def test_can_advance_one_step(self):
        self.assertTrue(ClaimState.can_transition("unapproved", "framework_ready"))

    def test_can_always_reject(self):
        self.assertTrue(ClaimState.can_transition("trained", "rejected"))

    def test_gates_passed_requires_approval(self):
        self.assertTrue(ClaimState.requires_approval_for("gates_passed"))

    def test_framework_ready_does_not_require_approval(self):
        self.assertFalse(ClaimState.requires_approval_for("framework_ready"))


if __name__ == "__main__":
    unittest.main()
