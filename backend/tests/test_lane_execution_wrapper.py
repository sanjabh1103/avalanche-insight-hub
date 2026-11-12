"""Tests for lane execution wrapper (P1/P2 v3).

Tests verify that:
- Valid execution with complete context, manifest, and registry passes
- Missing registry blocks non-framework modes
- Unregistered signer blocks execution
- Publication-only rights block training
- Track-specific rights are enforced
- Missing manifest blocks non-framework modes
- Promotion evidence is verified
- Structured gate decision contains digests and blocker codes
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.common.track_contracts.lane_execution_wrapper import (
    authorize_lane_execution,
    authorize_lane_payload,
    assert_lane_execution,
    LaneExecutionError,
    GateDecision,
    BLOCKER_MISSING_REGISTRY,
    BLOCKER_AUTHORITY_FAILED,
    BLOCKER_RIGHTS_INSUFFICIENT,
    BLOCKER_MISSING_MANIFEST,
    BLOCKER_PROMOTION_EVIDENCE_MISSING,
    BLOCKER_ARTIFACT_VERIFICATION_FAILED,
    BLOCKER_MALFORMED_CONTEXT,
    BLOCKER_RUNTIME_REQUEST_INVALID,
)
from backend.common.track_contracts.lane_preflight import OperationMode
from backend.common.track_contracts.packet_loaders import (
    ApprovalPacketV1,
    ReferenceUnitV1,
    IssueValidityRuleV1,
    RightsManifestV1,
    ForcingSourceManifestV1,
    TrackPreflightContextV1,
)
from backend.common.track_contracts.experiment_manifest import TrackExperimentManifestV1
from backend.common.track_contracts.authority_registry import (
    ApprovalRecordV1,
    AuthorityRegistry,
    AuthorityRecord,
)
from backend.common.track_contracts.content_resolver import ContentResolver
from backend.common.track_contracts.artifact_registry import ArtifactBindingV1, ArtifactRegistry
from backend.common.track_contracts.label_record import (
    PartnerLabelRecordV1,
    PartnerLabelInventoryV1,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


_VALID_HEX = "a" * 64
_TEST_CONTENT_ROOT = Path(tempfile.mkdtemp(prefix="Partner-wrapper-content-"))


def _write_json(name: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    (_TEST_CONTENT_ROOT / name).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _registry_with_smith() -> AuthorityRegistry:
    reg = AuthorityRegistry()
    reg.register(AuthorityRecord(
        authority_id="Partner_auth_001",
        name="Dr. Smith",
        role="Lead Scientist",
        active=True,
        registered_at=_utc(2026, 1, 1),
        approved_tracks=("track1", "t2a"),
    ))
    return reg


def _valid_t2a_context(rights_uses: tuple[str, ...] = ("ml_training_t2a",)) -> TrackPreflightContextV1:
    inventory = _valid_label_inventory()
    label_hash = _write_json("label_inventory.json", inventory.to_dict())
    split_hash = _write_json("split_manifest.json", {"split": "synthetic-v1"})
    geometry_hash = _write_json("reference_geometry.json", {"geometry": "synthetic-v1"})
    forcing_hash = _write_json("forcing_source.json", {"forcing": "synthetic-v1"})
    return TrackPreflightContextV1(
        track="t2a",
        approval=ApprovalPacketV1(
            approval_id="Partner_001", scope="m0_m1_combined",
            signer="Dr. Smith", signer_role="Lead Scientist",
            signature_hash=_VALID_HEX, approved_at=_utc(2026, 8, 18, 6),
            approved_tracks=("track1", "t2a"),
            authority_id="Partner_auth_001",
        ),
        reference_unit=ReferenceUnitV1(
            reference_unit_name="pir_panjal", latitude=34.02, longitude=74.35,
            elevation_m=3730.0, elevation_band="3000-4000m",
            aspect_applicability="all", geometry_hash=geometry_hash,
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
            permitted_uses=rights_uses,
            prohibited_uses=(), license_review_id="lic_001",
            license_review_status="approved",
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        ),
        label_inventory_hash=label_hash,
        split_manifest_hash=split_hash,
        label_inventory=inventory,
        content_paths={
            "label_inventory": "label_inventory.json",
            "split_manifest": "split_manifest.json",
            "reference_geometry": "reference_geometry.json",
            "forcing_source": "forcing_source.json",
        },
        forcing_source=ForcingSourceManifestV1(
            provider="Open-Meteo", model_id="gfs_seamless",
            run_id_format="YYYY-MM-DDTHH:MM UTC", native_resolution_m=3000.0,
            assimilation_disclosure="assimilates obs",
            source_hash=forcing_hash, license_review_id="lic_002",
            license_review_status="approved", permitted_track="t2a",
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        ),
    )


def _valid_manifest(track="t2a", claim_state="training_eligible") -> TrackExperimentManifestV1:
    context = _valid_t2a_context()
    return TrackExperimentManifestV1(
        track=track, experiment_id="exp_001",
        target_hash=context.label_inventory_hash,
        source_hash=context.forcing_source.source_hash,
        feature_hash=_VALID_HEX,
        split_hash=context.split_manifest_hash,
        approvals=("Partner_001",), claim_state=claim_state,
    )


def _valid_label_inventory(reference_unit="pir_panjal") -> PartnerLabelInventoryV1:
    """Create a valid 5-level label inventory."""
    records = []
    seasons = ("winter_2025", "winter_2026")
    for level in (1, 2, 3, 4, 5):
        for index, season in enumerate(seasons):
            issue = _utc(2025 + index, 1, 1, 6)
            records.append(PartnerLabelRecordV1(
                level=level, reference_unit=reference_unit,
                issue_time=issue,
                valid_time_start=issue,
                valid_time_end=issue.replace(day=2),
                geography="pir_panjal", elevation_band="3000-4000m",
                aspect_applicability="all", issuer="Partner", revision=0,
                provenance="Partner_bulletin", rights_status="approved",
                quality_status="reviewed", approved_by="Dr. Smith",
                approved_at=issue, season=season,
            ))
    return PartnerLabelInventoryV1(
        records=records, reference_unit=reference_unit,
        seasons_covered=list(seasons),
        record_counts_by_level={1: 2, 2: 2, 3: 2, 4: 2, 5: 2},
        level_5_support=True,
        support_policy_id="synthetic-Partner-policy-v1",
        support_policy_hash=_VALID_HEX,
        support_policy_signed_by="Dr. Smith",
        minimum_seasons=2,
        minimum_support_by_level={1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
        source_hash=_VALID_HEX,
    )


def _runtime_gate_kwargs():
    return {
        "content_resolver": ContentResolver(_TEST_CONTENT_ROOT),
        "artifact_registry": ArtifactRegistry(),
    }


def _valid_t2a_features():
    return ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
            "precipitation", "snowfall", "shortwave_radiation",
            "elevation", "slope", "aspect", "terrain_roughness"]


class TestValidExecution(unittest.TestCase):

    def test_valid_training_passes(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertTrue(decision.allowed, f"Blockers: {decision.blocker_messages}")
        self.assertEqual(decision.authority_id, "Partner_auth_001")
        self.assertTrue(decision.manifest_digest)
        self.assertTrue(decision.registry_digest)
        self.assertTrue(decision.content_digests)
        self.assertIn("registry_snapshot", decision.artifact_evidence)
        self.assertEqual(decision.artifact_namespace, "t2a_training")

    def test_assert_does_not_raise(self):
        assert_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )

    def test_framework_mode_passes_without_registry(self):
        decision = authorize_lane_execution(
            mode=OperationMode.FRAMEWORK,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=None,
            authority_registry=None,
            feature_names=_valid_t2a_features(),
        )
        self.assertTrue(decision.allowed)


class TestFailClosedRuntimeInputs(unittest.TestCase):

    def test_lane_execution_error_preserves_structured_blockers(self):
        decision = GateDecision(
            allowed=False,
            track="t2a",
            operation_mode=OperationMode.TRAINING,
            blocker_codes=[BLOCKER_MALFORMED_CONTEXT],
            blocker_messages=["context is malformed"],
        )

        with self.assertRaises(LaneExecutionError) as caught:
            decision.raise_if_blocked()

        self.assertEqual(caught.exception.blocker_codes, (BLOCKER_MALFORMED_CONTEXT,))
        self.assertEqual(caught.exception.blocker_messages, ("context is malformed",))
        self.assertEqual(caught.exception.to_dict()["blocker_codes"], [BLOCKER_MALFORMED_CONTEXT])

    def test_malformed_direct_registry_is_a_structured_blocker(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=object(),  # type: ignore[arg-type]
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )

        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_MALFORMED_CONTEXT, decision.blocker_codes)

    def test_empty_and_non_object_payloads_are_blocked(self):
        for payload in (None, {}, [], "not-json-object"):
            with self.subTest(payload=payload):
                decision = authorize_lane_payload(payload)  # type: ignore[arg-type]
                self.assertIsNotNone(decision)
                self.assertFalse(decision.allowed)
                self.assertIn(BLOCKER_RUNTIME_REQUEST_INVALID, decision.blocker_codes)

    def test_present_null_track_cannot_fall_through_as_generic(self):
        decision = authorize_lane_payload({"track": None, "operation_mode": "training"})

        self.assertIsNotNone(decision)
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_RUNTIME_REQUEST_INVALID, decision.blocker_codes)

    def test_nonempty_generic_payload_remains_outside_lane_gate(self):
        self.assertIsNone(authorize_lane_payload({"dataset_snapshot_id": "latest"}))


class TestMissingRegistryBlocked(unittest.TestCase):

    def test_training_without_registry_blocked(self):
        """CRITICAL: training without authority registry must be blocked."""
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=None,
            feature_names=_valid_t2a_features(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_MISSING_REGISTRY, decision.blocker_codes)


class TestUnregisteredSignerBlocked(unittest.TestCase):

    def test_unregistered_signer_blocked(self):
        """CRITICAL: unregistered signer with valid-looking hash must be blocked."""
        # Empty registry — no authorities registered
        empty_registry = AuthorityRegistry()
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=empty_registry,
            feature_names=_valid_t2a_features(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_AUTHORITY_FAILED, decision.blocker_codes)


class TestPublicationOnlyRightsBlocked(unittest.TestCase):

    def test_publication_only_rights_blocked_for_training(self):
        """CRITICAL: publication-only rights must NOT authorize training."""
        ctx = _valid_t2a_context(rights_uses=("scientific_publication",))
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_RIGHTS_INSUFFICIENT, decision.blocker_codes)

    def test_track_specific_rights_required(self):
        """T2A training requires ml_training_t2a, not just ml_training_track1."""
        ctx = _valid_t2a_context(rights_uses=("ml_training_track1",))  # wrong track
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_RIGHTS_INSUFFICIENT, decision.blocker_codes)

    def test_correct_track_rights_pass(self):
        ctx = _valid_t2a_context(rights_uses=("ml_training_t2a",))
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertTrue(decision.allowed, f"Blockers: {decision.blocker_messages}")


class TestMissingManifestBlocked(unittest.TestCase):

    def test_training_without_manifest_blocked(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=None,
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_MISSING_MANIFEST, decision.blocker_codes)


class TestTrainingEligibility(unittest.TestCase):

    def test_training_without_label_inventory_blocked(self):
        """Training must require actual label_inventory, not just hash."""
        ctx = _valid_t2a_context()
        ctx_no_inv = TrackPreflightContextV1(
            track=ctx.track, approval=ctx.approval,
            reference_unit=ctx.reference_unit,
            issue_validity_rule=ctx.issue_validity_rule,
            rights=ctx.rights,
            label_inventory_hash=ctx.label_inventory_hash,
            split_manifest_hash=ctx.split_manifest_hash,
            forcing_source=ctx.forcing_source,
            label_inventory=None,  # MISSING
        )
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=ctx_no_inv,
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)

    def test_training_with_gates_passed_claim_state_blocked(self):
        """Training must require claim_state >= training_eligible."""
        ctx = _valid_t2a_context()
        manifest = _valid_manifest(claim_state="gates_passed")  # too low
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=manifest,
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)

    def test_training_with_training_eligible_passes(self):
        ctx = _valid_t2a_context()
        manifest = _valid_manifest(claim_state="training_eligible")
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=manifest,
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertTrue(decision.allowed, f"Blockers: {decision.blocker_messages}")


class TestPromotionEvidence(unittest.TestCase):

    def test_promotion_without_evidence_blocked(self):
        manifest = _valid_manifest(claim_state="evaluated")
        decision = authorize_lane_execution(
            mode=OperationMode.PROMOTION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=manifest,
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_PROMOTION_EVIDENCE_MISSING, decision.blocker_codes)

    def test_promotion_with_fake_evidence_blocked(self):
        """Fake non-empty IDs must be validated, not just presence-checked."""
        manifest = TrackExperimentManifestV1(
            track="t2a", experiment_id="exp_001",
            target_hash=_VALID_HEX, source_hash=_VALID_HEX,
            feature_hash=_VALID_HEX, split_hash=_VALID_HEX,
            approvals=("Partner_001",), claim_state="evaluated",
            evaluation_report_hash="fake_report_id",  # not a hash
            independent_observation_hashes=("fake_obs",),  # not a hash
            Partner_approval_id="fake_approval",  # not resolvable
        )
        decision = authorize_lane_execution(
            mode=OperationMode.PROMOTION,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=manifest,
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
        )
        self.assertFalse(decision.allowed)

    def test_evaluated_all_hex_evidence_without_fitted_artifact_blocked(self):
        """A format-valid manifest must not bypass fitted-artifact verification."""
        ctx = _valid_t2a_context(rights_uses=("ml_promotion_t2a",))
        manifest = TrackExperimentManifestV1(
            track="t2a", experiment_id="exp_002",
            target_hash=ctx.label_inventory_hash,
            source_hash=ctx.forcing_source.source_hash,
            feature_hash=_VALID_HEX,
            split_hash=ctx.split_manifest_hash,
            approvals=("Partner_001",), claim_state="evaluated",
            evaluation_report_hash="b" * 64,
            independent_observation_hashes=("c" * 64,),
            Partner_approval_id="Partner-promotion-001",
        )
        decision = authorize_lane_execution(
            mode=OperationMode.PROMOTION,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=manifest,
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn(BLOCKER_ARTIFACT_VERIFICATION_FAILED, decision.blocker_codes)

    def test_verified_promotion_requires_content_bound_artifact_and_approval(self):
        ctx = _valid_t2a_context(rights_uses=("ml_promotion_t2a",))
        report_hash = _write_json("evaluation_report.json", {"status": "frozen", "f1": 0.8})
        observation_hash = _write_json("independent_observation.json", {"obs": "independent"})
        artifact_bytes = b"synthetic-fitted-model-v1"
        (_TEST_CONTENT_ROOT / "fitted-model.bin").write_bytes(artifact_bytes)
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        manifest = TrackExperimentManifestV1(
            track="t2a", experiment_id="exp-promotable",
            target_hash=ctx.label_inventory_hash,
            source_hash=ctx.forcing_source.source_hash,
            feature_hash=_VALID_HEX,
            split_hash=ctx.split_manifest_hash,
            approvals=("Partner_001",), claim_state="evaluated",
            fitted_artifact_ids=("model-promotion-001",),
            evaluation_report_hash=report_hash,
            independent_observation_hashes=(observation_hash,),
            Partner_approval_id="promo-verified",
            evidence_paths={
                "evaluation_report": "evaluation_report.json",
                "independent_observation_0": "independent_observation.json",
            },
        )
        registry = _registry_with_smith()
        registry.cryptographic_verifier = lambda approval: approval.approval_id == "promo-verified"
        registry.register_approval(ApprovalRecordV1(
            approval_id="promo-verified", authority_id="Partner_auth_001",
            approved_tracks=("t2a",), approved_at=_utc(2026, 8, 18, 6),
            signature_hash=_VALID_HEX,
        ))
        artifacts = ArtifactRegistry()
        artifacts.register(ArtifactBindingV1(
            artifact_id="model-promotion-001", artifact_type="model", track="t2a",
            feature_hash=_VALID_HEX, source_hash=ctx.forcing_source.source_hash,
            split_hash=ctx.split_manifest_hash, namespace="t2a_promotion",
            created_at="2026-08-18T06:00:00+00:00",
            content_hash=artifact_hash, content_path="fitted-model.bin",
        ))
        decision = authorize_lane_execution(
            mode=OperationMode.PROMOTION,
            track="t2a",
            preflight_context=ctx,
            experiment_manifest=manifest,
            authority_registry=registry,
            feature_names=_valid_t2a_features(),
            content_resolver=ContentResolver(_TEST_CONTENT_ROOT),
            artifact_registry=artifacts,
        )
        self.assertTrue(decision.allowed, decision.blocker_messages)
        self.assertEqual(decision.verified_artifact_ids, ("model-promotion-001",))
        self.assertIn("evaluation_report", decision.content_digests)
        self.assertIn("independent_observation_0", decision.content_digests)
        self.assertIn("model-promotion-001", decision.artifact_evidence)


class TestGateDecisionStructure(unittest.TestCase):

    def test_decision_contains_manifest_digest(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertTrue(decision.manifest_digest)
        self.assertEqual(len(decision.manifest_digest), 64)

    def test_decision_contains_registry_digest(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertTrue(decision.registry_digest)
        self.assertEqual(len(decision.registry_digest), 64)

    def test_decision_contains_artifact_namespace(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertEqual(decision.artifact_namespace, "t2a_training")

    def test_decision_contains_authority_id(self):
        decision = authorize_lane_execution(
            mode=OperationMode.TRAINING,
            track="t2a",
            preflight_context=_valid_t2a_context(),
            experiment_manifest=_valid_manifest(),
            authority_registry=_registry_with_smith(),
            feature_names=_valid_t2a_features(),
            **_runtime_gate_kwargs(),
        )
        self.assertEqual(decision.authority_id, "Partner_auth_001")

    def test_assert_raises_on_blocked(self):
        with self.assertRaises(LaneExecutionError):
            assert_lane_execution(
                mode=OperationMode.TRAINING,
                track="t2a",
                preflight_context=_valid_t2a_context(),
                experiment_manifest=None,
                authority_registry=None,
                feature_names=_valid_t2a_features(),
            )


if __name__ == "__main__":
    unittest.main()
