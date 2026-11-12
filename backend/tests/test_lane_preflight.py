"""Integration tests for lane preflight gate (P0 v2).

Tests verify that:
- A complete valid preflight passes for each operation mode
- Missing manifest is a HARD BLOCKER for all modes except FRAMEWORK
- Wrong track blocks execution
- Contaminated features block execution
- Insufficient claim state blocks per-mode requirements
- The gate is wired and discoverable via import
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.track_contracts.lane_preflight import (
    run_lane_preflight,
    assert_lane_authorized,
    LanePreflightError,
    PreflightResult,
    OperationMode,
)
from backend.common.track_contracts.packet_loaders import (
    ApprovalPacketV1,
    ReferenceUnitV1,
    IssueValidityRuleV1,
    RightsManifestV1,
    ForcingSourceManifestV1,
    TrackPreflightContextV1,
)
from backend.common.track_contracts.experiment_manifest import TrackExperimentManifestV1


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


_VALID_HEX = "a" * 64


def _valid_t2a_context() -> TrackPreflightContextV1:
    return TrackPreflightContextV1(
        track="t2a",
        approval=ApprovalPacketV1(
            approval_id="Partner_001", scope="m0_m1_combined",
            signer="Dr. Smith", signer_role="Lead Scientist",
            signature_hash=_VALID_HEX, approved_at=_utc(2026, 8, 18, 6),
            approved_tracks=("track1", "t2a"),
        ),
        reference_unit=ReferenceUnitV1(
            reference_unit_name="pir_panjal", latitude=34.02, longitude=74.35,
            elevation_m=3730.0, elevation_band="3000-4000m",
            aspect_applicability="all", geometry_hash=_VALID_HEX,
            coordinate_system="EPSG:4326", approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        ),
        issue_validity_rule=IssueValidityRuleV1(
            issue_cadence_hours=6, issue_slots_utc=(0, 6, 12, 18),
            validity_window_hours=24, timezone="UTC", horizon_hours=72,
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        ),
        rights=RightsManifestV1(
            data_source="Partner", rights_holder="Partner",
            permitted_uses=("ml_training_t2a",),
            prohibited_uses=(), license_review_id="lic_001",
            license_review_status="approved",
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        ),
        label_inventory_hash=_VALID_HEX,
        split_manifest_hash=_VALID_HEX,
        forcing_source=ForcingSourceManifestV1(
            provider="Open-Meteo", model_id="gfs_seamless",
            run_id_format="YYYY-MM-DDTHH:MM UTC", native_resolution_m=3000.0,
            assimilation_disclosure="assimilates obs",
            source_hash=_VALID_HEX, license_review_id="lic_002",
            license_review_status="approved", permitted_track="t2a",
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        ),
    )


def _valid_t2a_features() -> list[str]:
    return ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
            "precipitation", "snowfall", "shortwave_radiation",
            "elevation", "slope", "aspect", "terrain_roughness"]


def _valid_manifest(track: str = "t2a", claim_state: str = "gates_passed") -> TrackExperimentManifestV1:
    return TrackExperimentManifestV1(
        track=track,
        experiment_id="exp_001",
        target_hash=_VALID_HEX,
        source_hash=_VALID_HEX,
        feature_hash=_VALID_HEX,
        split_hash=_VALID_HEX,
        approvals=("Partner_001",),
        claim_state=claim_state,
    )


class TestLanePreflightValid(unittest.TestCase):

    def test_valid_framework_mode_passes_without_manifest(self):
        """FRAMEWORK mode is the ONLY mode that doesn't require a manifest."""
        result = run_lane_preflight(
            mode=OperationMode.FRAMEWORK,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=None,
        )
        self.assertTrue(result.allowed, f"Blockers: {result.blockers}")

    def test_valid_training_mode_passes(self):
        result = run_lane_preflight(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=_valid_manifest("t2a", "gates_passed"),
        )
        self.assertTrue(result.allowed, f"Blockers: {result.blockers}")

    def test_valid_evaluation_mode_passes(self):
        result = run_lane_preflight(
            mode=OperationMode.EVALUATION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=_valid_manifest("t2a", "trained"),
        )
        self.assertTrue(result.allowed, f"Blockers: {result.blockers}")

    def test_assert_lane_authorized_does_not_raise(self):
        assert_lane_authorized(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=_valid_manifest("t2a", "gates_passed"),
        )


class TestLanePreflightFailClosed(unittest.TestCase):

    def test_training_without_manifest_is_blocked(self):
        """CRITICAL: training mode MUST block when manifest is None."""
        result = run_lane_preflight(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=None,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("MANDATORY" in b for b in result.blockers))

    def test_evaluation_without_manifest_is_blocked(self):
        result = run_lane_preflight(
            mode=OperationMode.EVALUATION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=None,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("MANDATORY" in b for b in result.blockers))

    def test_promotion_without_manifest_is_blocked(self):
        result = run_lane_preflight(
            mode=OperationMode.PROMOTION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=None,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("MANDATORY" in b for b in result.blockers))

    def test_serve_without_manifest_is_blocked(self):
        result = run_lane_preflight(
            mode=OperationMode.SERVE,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=None,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("MANDATORY" in b for b in result.blockers))

    def test_contaminated_features_blocked(self):
        features = _valid_t2a_features() + ["snowpack"]
        result = run_lane_preflight(
            mode=OperationMode.FRAMEWORK,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=features,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("feature_validation" in b for b in result.blockers))

    def test_wrong_track_blocked(self):
        result = run_lane_preflight(
            mode=OperationMode.FRAMEWORK,
            track="track1",
            preflight_context=_valid_t2a_context(),  # t2a context
            feature_names=_valid_t2a_features(),
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("track mismatch" in b for b in result.blockers))

    def test_insufficient_claim_state_for_training_blocked(self):
        manifest = _valid_manifest("t2a", "unapproved")  # too low for training
        result = run_lane_preflight(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=manifest,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("insufficient" in b for b in result.blockers))

    def test_insufficient_claim_state_for_evaluation_blocked(self):
        manifest = _valid_manifest("t2a", "gates_passed")  # too low for evaluation
        result = run_lane_preflight(
            mode=OperationMode.EVALUATION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=manifest,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("insufficient" in b for b in result.blockers))

    def test_insufficient_claim_state_for_promotion_blocked(self):
        manifest = _valid_manifest("t2a", "trained")  # too low for promotion
        result = run_lane_preflight(
            mode=OperationMode.PROMOTION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=_valid_t2a_features(),
            experiment_manifest=manifest,
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("insufficient" in b for b in result.blockers))

    def test_approval_not_covering_track_blocked(self):
        ctx = TrackPreflightContextV1(
            track="t2a",
            approval=ApprovalPacketV1(
                approval_id="Partner_002", scope="m0_m1_combined",
                signer="Dr. Smith", signer_role="Lead Scientist",
                signature_hash=_VALID_HEX, approved_at=_utc(2026, 8, 18, 6),
                approved_tracks=("track1",),  # doesn't include t2a
            ),
            reference_unit=_valid_t2a_context().reference_unit,
            issue_validity_rule=_valid_t2a_context().issue_validity_rule,
            rights=_valid_t2a_context().rights,
            label_inventory_hash=_VALID_HEX,
            split_manifest_hash=_VALID_HEX,
            forcing_source=_valid_t2a_context().forcing_source,
        )
        result = run_lane_preflight(
            mode=OperationMode.FRAMEWORK,
            track="t2a",
            preflight_context=ctx,
            feature_names=_valid_t2a_features(),
        )
        self.assertFalse(result.allowed)
        self.assertTrue(any("approval does not cover" in b for b in result.blockers))

    def test_assert_raises_on_blocked(self):
        with self.assertRaises(LanePreflightError):
            assert_lane_authorized(
                mode=OperationMode.TRAINING,
                track="t2a",
                preflight_context=_valid_t2a_context(),
                feature_names=_valid_t2a_features(),
                experiment_manifest=None,  # missing manifest
            )

    def test_empty_features_blocked(self):
        result = run_lane_preflight(
            mode=OperationMode.FRAMEWORK,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            feature_names=[],
        )
        self.assertFalse(result.allowed)


if __name__ == "__main__":
    unittest.main()
