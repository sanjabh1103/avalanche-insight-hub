"""Authoritative execution gate for the Partner Track 1 and T2A lanes.

The contract modules are useful only when they sit in front of the workers.
This module therefore performs three separate kinds of verification before a
non-framework operation is authorized:

* packet and authority validation;
* content verification against bytes under a bounded resolver root; and
* fitted-artifact verification against a track/namespace/lineage registry.

Generic legacy worker requests deliberately return ``None`` from
``authorize_lane_payload``. They remain generic/diagnostic requests and cannot
be labelled as Track 1 or T2A. An explicit Partner request must supply every
packet, registry, resolver, and feature input; there is no ``latest`` or
fallback lane.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.Partner_decision_packet import (
    load_decision_packet,
    verify_decision_packet_hash,
    verify_decision_packet_provenance,
)

from .artifact_registry import ArtifactNamespaceError, ArtifactRegistry
from .authority_registry import AuthorityRegistry, AuthorityValidationError
from .content_resolver import ContentResolutionError, ContentResolver
from .experiment_manifest import ManifestValidationError, TrackExperimentManifestV1
from .lane_preflight import OperationMode, run_lane_preflight
from .label_record import PartnerLabelInventoryV1, LabelValidationError
from .packet_loaders import PacketValidationError, TrackPreflightContextV1


class LaneExecutionError(ValueError):
    """Raised when a lane execution request is blocked."""

    def __init__(
        self,
        message: str,
        *,
        blocker_codes: tuple[str, ...] = (),
        blocker_messages: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.blocker_codes = tuple(blocker_codes)
        self.blocker_messages = tuple(blocker_messages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "blocked",
            "reason": str(self),
            "blocker_codes": list(self.blocker_codes),
            "blocker_messages": list(self.blocker_messages),
        }


# Stable blocker codes are part of the audit/worker API. Do not replace these
# with free-form exceptions at a production boundary.
BLOCKER_MISSING_CONTEXT = "E001_missing_context"
BLOCKER_MISSING_MANIFEST = "E002_missing_manifest"
BLOCKER_MISSING_REGISTRY = "E003_missing_registry"
BLOCKER_AUTHORITY_FAILED = "E004_authority_verification_failed"
BLOCKER_RIGHTS_INSUFFICIENT = "E005_rights_insufficient_for_track"
BLOCKER_FEATURE_INVALID = "E006_feature_validation_failed"
BLOCKER_CLAIM_STATE_INSUFFICIENT = "E007_claim_state_insufficient"
BLOCKER_TRACK_MISMATCH = "E008_track_mismatch"
BLOCKER_APPROVAL_NOT_COVERED = "E009_approval_does_not_cover_track"
BLOCKER_PROMOTION_EVIDENCE_MISSING = "E010_promotion_evidence_missing"
BLOCKER_LABEL_INVENTORY_MISSING = "E011_label_inventory_missing"
BLOCKER_CLAIM_STATE_NOT_TRAINING_ELIGIBLE = "E012_claim_state_not_training_eligible"
BLOCKER_MISSING_CONTENT_RESOLVER = "E013_missing_content_resolver"
BLOCKER_CONTENT_UNVERIFIED = "E014_content_unverified"
BLOCKER_MISSING_ARTIFACT_REGISTRY = "E015_missing_artifact_registry"
BLOCKER_ARTIFACT_VERIFICATION_FAILED = "E016_artifact_verification_failed"
BLOCKER_PROMOTION_APPROVAL_FAILED = "E017_promotion_approval_failed"
BLOCKER_CRYPTO_APPROVAL_UNAVAILABLE = "E018_cryptographic_approval_unavailable"
BLOCKER_MALFORMED_CONTEXT = "E019_malformed_context"
BLOCKER_RUNTIME_REQUEST_INVALID = "E020_invalid_runtime_lane_request"
BLOCKER_MISSING_AUTHORITY_ID = "E021_missing_authority_id"
BLOCKER_PROMOTION_RIGHTS_MISSING = "E022_promotion_rights_missing"
BLOCKER_SERVING_RIGHTS_MISSING = "E023_serving_rights_missing"
BLOCKER_MISSING_EVIDENCE_PACKET = "E024_missing_evidence_packet"
BLOCKER_EVIDENCE_PACKET_INVALID = "E025_invalid_evidence_packet"
BLOCKER_EVIDENCE_PACKET_BLOCKED = "E026_evidence_packet_blocks_operation"

_EXPLICIT_TRACKS = {"track1", "t2a"}


@dataclass
class GateDecision:
    """Structured authorization evidence returned by every gate attempt."""

    allowed: bool
    track: str
    operation_mode: OperationMode
    blocker_codes: list[str] = field(default_factory=list)
    blocker_messages: list[str] = field(default_factory=list)
    manifest_digest: str = ""
    registry_digest: str = ""
    content_digests: dict[str, str] = field(default_factory=dict)
    artifact_namespace: str = ""
    verified_artifact_ids: tuple[str, ...] = ()
    artifact_evidence: dict[str, dict[str, str]] = field(default_factory=dict)
    verification_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    authority_id: str = ""
    evidence_packet_sha256: str = ""
    evidence_packet_status: str = ""

    def raise_if_blocked(self) -> None:
        if not self.allowed:
            raise LaneExecutionError(
                f"Lane execution blocked for track '{self.track}' "
                f"mode '{self.operation_mode.value}': "
                f"codes={self.blocker_codes}, messages={self.blocker_messages}",
                blocker_codes=tuple(self.blocker_codes),
                blocker_messages=tuple(self.blocker_messages),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "track": self.track,
            "operation_mode": self.operation_mode.value,
            "blocker_codes": list(self.blocker_codes),
            "blocker_messages": list(self.blocker_messages),
            "manifest_digest": self.manifest_digest,
            "registry_digest": self.registry_digest,
            "content_digests": dict(self.content_digests),
            "artifact_namespace": self.artifact_namespace,
            "verified_artifact_ids": list(self.verified_artifact_ids),
            "artifact_evidence": dict(self.artifact_evidence),
            "verification_timestamp": self.verification_timestamp.isoformat(),
            "authority_id": self.authority_id,
            "evidence_packet_sha256": self.evidence_packet_sha256,
            "evidence_packet_status": self.evidence_packet_status,
        }


def _compute_registry_digest(registry: AuthorityRegistry) -> str:
    """Digest all authority, approval, rights, and revocation state."""
    payload = registry.to_dict()
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _compute_artifact_registry_digest(registry: ArtifactRegistry) -> str:
    return hashlib.sha256(
        json.dumps(registry.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _compute_manifest_digest(manifest: TrackExperimentManifestV1) -> str:
    return hashlib.sha256(
        json.dumps(
            manifest.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _check_track_rights(
    preflight_context: TrackPreflightContextV1,
    track: str,
    mode: OperationMode,
) -> list[str]:
    """Return rights blockers for the exact operation, never a broad proxy right."""
    rights = preflight_context.rights
    if mode in (OperationMode.TRAINING, OperationMode.EVALUATION):
        required = f"ml_training_{track}"
    elif mode == OperationMode.PROMOTION:
        required = f"ml_promotion_{track}"
    elif mode == OperationMode.SERVE:
        required = f"ml_serving_{track}"
    else:
        return []

    blockers: list[str] = []
    if required not in rights.permitted_uses:
        blockers.append(
            f"rights do not permit '{required}'; permitted: {rights.permitted_uses}"
        )
    if mode == OperationMode.SERVE and "public_disclosure" not in rights.permitted_uses:
        blockers.append(
            "serving requires explicit public_disclosure rights; "
            f"permitted: {rights.permitted_uses}"
        )
    return blockers


def _required_content_targets(context: TrackPreflightContextV1) -> list[tuple[str, str]]:
    targets = [
        ("label_inventory", context.label_inventory_hash),
        ("split_manifest", context.split_manifest_hash),
        ("reference_geometry", context.reference_unit.geometry_hash),
    ]
    if context.track == "t2a" and context.forcing_source is not None:
        targets.append(("forcing_source", context.forcing_source.source_hash))
    if context.track == "track1" and context.station_source is not None:
        targets.append(("station_source", context.station_source.source_hash))
    return targets


def _verify_context_content(
    context: TrackPreflightContextV1,
    resolver: ContentResolver,
) -> tuple[dict[str, str], list[str]]:
    """Verify every required context hash against one bounded byte source."""
    digests: dict[str, str] = {}
    blockers: list[str] = []
    for key, declared_hash in _required_content_targets(context):
        relative_path = context.content_paths.get(key)
        if not relative_path:
            blockers.append(f"content_paths is missing required '{key}' binding")
            continue
        try:
            if key == "label_inventory":
                payload, result = resolver.load_json_and_verify(declared_hash, relative_path)
                loaded = PartnerLabelInventoryV1.from_dict(payload)
                if context.label_inventory is None:
                    raise ContentResolutionError(
                        "context must carry label_inventory records, not only its hash"
                    )
                if loaded.to_dict() != context.label_inventory.to_dict():
                    raise ContentResolutionError(
                        "label inventory packet records do not match the content-bound inventory"
                    )
            else:
                result = resolver.resolve_and_verify(declared_hash, relative_path)
            digests[key] = result.actual_hash
        except (ContentResolutionError, LabelValidationError, OSError, ValueError) as exc:
            blockers.append(f"{key}: {exc}")
    return digests, blockers


def _verify_manifest_evidence_content(
    manifest: TrackExperimentManifestV1,
    mode: OperationMode,
    resolver: ContentResolver,
) -> tuple[dict[str, str], list[str]]:
    """Verify report/independent-observation hashes when they are claim-bearing."""
    digests: dict[str, str] = {}
    blockers: list[str] = []
    evidence: list[tuple[str, str]] = []
    if manifest.evaluation_report_hash:
        evidence.append(("evaluation_report", manifest.evaluation_report_hash))
    evidence.extend(
        (f"independent_observation_{index}", value)
        for index, value in enumerate(manifest.independent_observation_hashes)
    )
    if mode in (OperationMode.PROMOTION, OperationMode.SERVE):
        if "evaluation_report" not in manifest.evidence_paths:
            blockers.append("evaluation_report evidence path is required")
        if not manifest.independent_observation_hashes:
            blockers.append("at least one independent observation is required")
    for key, declared_hash in evidence:
        relative_path = manifest.evidence_paths.get(key)
        if not relative_path:
            blockers.append(f"evidence_paths is missing '{key}'")
            continue
        try:
            result = resolver.resolve_and_verify(declared_hash, relative_path)
            digests[key] = result.actual_hash
        except ContentResolutionError as exc:
            blockers.append(f"{key}: {exc}")
    return digests, blockers


def _verify_artifacts(
    *,
    mode: OperationMode,
    track: str,
    manifest: TrackExperimentManifestV1 | None,
    resolver: ContentResolver,
    registry: ArtifactRegistry,
) -> tuple[tuple[str, ...], dict[str, dict[str, str]], list[str]]:
    """Verify fitted artifacts and complete lineage for fitted operations."""
    if manifest is None:
        return (), {}, []
    artifact_ids = tuple(manifest.fitted_artifact_ids)
    requires_fitted = mode in (OperationMode.EVALUATION, OperationMode.PROMOTION, OperationMode.SERVE)
    if requires_fitted and not artifact_ids:
        return (), {}, [f"mode '{mode.value}' requires registered fitted_artifact_ids"]

    namespace = f"{track}_{mode.value}"
    verified: list[str] = []
    evidence: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    for artifact_id in artifact_ids:
        try:
            artifact = registry.verify_artifact_for_track(
                artifact_id,
                track,
                namespace,
                feature_hash=manifest.feature_hash,
                source_hash=manifest.source_hash,
                split_hash=manifest.split_hash,
                content_resolver=resolver,
                require_content=True,
            )
            verified.append(artifact.artifact_id)
            evidence[artifact.artifact_id] = {
                "namespace": artifact.namespace,
                "content_hash": artifact.content_hash,
                "content_path": artifact.content_path,
            }
        except ArtifactNamespaceError as exc:
            blockers.append(str(exc))
    return tuple(verified), evidence, blockers


def _blocked_decision(
    *,
    track: str,
    mode: OperationMode,
    codes: list[str],
    messages: list[str],
) -> GateDecision:
    return GateDecision(
        allowed=False,
        track=track,
        operation_mode=mode,
        blocker_codes=codes,
        blocker_messages=messages,
        artifact_namespace=f"{track}_{mode.value}",
    )


def _authorize_lane_execution(
    *,
    mode: OperationMode,
    track: str,
    preflight_context: TrackPreflightContextV1 | None,
    experiment_manifest: TrackExperimentManifestV1 | None,
    authority_registry: AuthorityRegistry | None,
    content_resolver: ContentResolver | None = None,
    artifact_registry: ArtifactRegistry | None = None,
    feature_names: list[str] | None,
    evidence_packet_sha256: str = "",
) -> GateDecision:
    """Authorize one lane operation through the complete fail-closed chain."""
    blocker_codes: list[str] = []
    blocker_messages: list[str] = []
    feature_names = feature_names if isinstance(feature_names, list) else []

    if not isinstance(mode, OperationMode):
        try:
            mode = OperationMode(str(mode))
        except (TypeError, ValueError):
            return _blocked_decision(
                track=str(track),
                mode=OperationMode.FRAMEWORK,
                codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
                messages=[f"unknown operation mode: {mode!r}"],
            )
    if track not in _EXPLICIT_TRACKS:
        return _blocked_decision(
            track=str(track),
            mode=mode,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=[f"track must be one of {sorted(_EXPLICIT_TRACKS)}; got {track!r}"],
        )

    if preflight_context is None or not isinstance(preflight_context, TrackPreflightContextV1):
        blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
        blocker_messages.append("preflight_context must be a TrackPreflightContextV1 instance")
    if mode != OperationMode.FRAMEWORK and experiment_manifest is None:
        blocker_codes.append(BLOCKER_MISSING_MANIFEST)
        blocker_messages.append(f"experiment_manifest is mandatory for mode '{mode.value}'")
    if mode != OperationMode.FRAMEWORK and authority_registry is None:
        blocker_codes.append(BLOCKER_MISSING_REGISTRY)
        blocker_messages.append(f"authority_registry is mandatory for mode '{mode.value}'")
    if mode != OperationMode.FRAMEWORK and content_resolver is None:
        blocker_codes.append(BLOCKER_MISSING_CONTENT_RESOLVER)
        blocker_messages.append(f"content_resolver is mandatory for mode '{mode.value}'")
    if mode != OperationMode.FRAMEWORK and artifact_registry is None:
        blocker_codes.append(BLOCKER_MISSING_ARTIFACT_REGISTRY)
        blocker_messages.append(f"artifact_registry is mandatory for mode '{mode.value}'")

    preflight = None
    if isinstance(preflight_context, TrackPreflightContextV1):
        try:
            preflight = run_lane_preflight(
                mode=mode,
                track=track,
                preflight_context=preflight_context,
                feature_names=feature_names,
                experiment_manifest=experiment_manifest,
            )
            if not preflight.allowed:
                for message in preflight.blockers:
                    lower = message.lower()
                    if "mandatory" in lower and "manifest" in lower:
                        code = BLOCKER_MISSING_MANIFEST
                    elif "feature_validation" in lower:
                        code = BLOCKER_FEATURE_INVALID
                    elif "track mismatch" in lower:
                        code = BLOCKER_TRACK_MISMATCH
                    elif "approval does not cover" in lower:
                        code = BLOCKER_APPROVAL_NOT_COVERED
                    elif "claim_state" in lower or "rejected" in lower:
                        code = BLOCKER_CLAIM_STATE_INSUFFICIENT
                    else:
                        code = BLOCKER_MISSING_CONTEXT
                    blocker_codes.append(code)
                    blocker_messages.append(message)
        except (AttributeError, TypeError, PacketValidationError, ManifestValidationError, ValueError) as exc:
            blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
            blocker_messages.append(f"preflight evaluation failed closed: {exc}")

    authority_id = ""
    if isinstance(preflight_context, TrackPreflightContextV1) and authority_registry is not None:
        approval = preflight_context.approval
        try:
            if mode != OperationMode.FRAMEWORK and not approval.authority_id.strip():
                blocker_codes.append(BLOCKER_MISSING_AUTHORITY_ID)
                blocker_messages.append("approval.authority_id is mandatory at the runtime boundary")
            authority = authority_registry.verify_approval(
                approval_id=approval.approval_id,
                signer_name=approval.signer,
                signer_role=approval.signer_role,
                signature_hash=approval.signature_hash,
                approved_tracks=approval.approved_tracks,
                approved_at=approval.approved_at,
                authority_id=approval.authority_id or None,
            )
            authority_id = authority.authority_id
        except AuthorityValidationError as exc:
            blocker_codes.append(BLOCKER_AUTHORITY_FAILED)
            blocker_messages.append(f"authority verification failed: {exc}")
        except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
            blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
            blocker_messages.append(f"authority verification failed closed: {exc}")

    if isinstance(preflight_context, TrackPreflightContextV1):
        try:
            for message in _check_track_rights(preflight_context, track, mode):
                code = (
                    BLOCKER_PROMOTION_RIGHTS_MISSING
                    if mode == OperationMode.PROMOTION
                    else BLOCKER_SERVING_RIGHTS_MISSING
                    if mode == OperationMode.SERVE
                    else BLOCKER_RIGHTS_INSUFFICIENT
                )
                blocker_codes.append(code)
                blocker_messages.append(message)
        except (AttributeError, TypeError, ValueError) as exc:
            blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
            blocker_messages.append(f"rights evaluation failed closed: {exc}")

    content_digests: dict[str, str] = {}
    if mode != OperationMode.FRAMEWORK and isinstance(preflight_context, TrackPreflightContextV1) and content_resolver is not None:
        try:
            content_digests, content_blockers = _verify_context_content(
                preflight_context,
                content_resolver,
            )
            for message in content_blockers:
                blocker_codes.append(BLOCKER_CONTENT_UNVERIFIED)
                blocker_messages.append(message)
        except (AttributeError, TypeError, ValueError) as exc:
            blocker_codes.append(BLOCKER_CONTENT_UNVERIFIED)
            blocker_messages.append(f"context content verification failed closed: {exc}")

    if mode == OperationMode.TRAINING and isinstance(preflight_context, TrackPreflightContextV1):
        inventory = preflight_context.label_inventory
        if inventory is None:
            blocker_codes.append(BLOCKER_LABEL_INVENTORY_MISSING)
            blocker_messages.append("training requires actual Partner label_inventory records")
        elif hasattr(inventory, "training_eligibility_blockers"):
            try:
                for message in inventory.training_eligibility_blockers():
                    blocker_codes.append(BLOCKER_CLAIM_STATE_NOT_TRAINING_ELIGIBLE)
                    blocker_messages.append(f"label inventory is not training-eligible: {message}")
            except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
                blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
                blocker_messages.append(f"label inventory evaluation failed closed: {exc}")
        else:
            blocker_codes.append(BLOCKER_LABEL_INVENTORY_MISSING)
            blocker_messages.append("label_inventory does not implement Partner training eligibility")
        if isinstance(experiment_manifest, TrackExperimentManifestV1) and experiment_manifest.claim_state not in {
            "training_eligible", "trained", "evaluated", "promotion_eligible",
        }:
            blocker_codes.append(BLOCKER_CLAIM_STATE_NOT_TRAINING_ELIGIBLE)
            blocker_messages.append(
                "training requires manifest claim_state >= 'training_eligible'; "
                f"got '{experiment_manifest.claim_state}'"
            )

    manifest_digest = ""
    if experiment_manifest is not None:
        if not isinstance(experiment_manifest, TrackExperimentManifestV1):
            blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
            blocker_messages.append("experiment_manifest must be TrackExperimentManifestV1")
        else:
            try:
                manifest_digest = _compute_manifest_digest(experiment_manifest)
            except (AttributeError, TypeError, ValueError) as exc:
                blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
                blocker_messages.append(f"manifest digest failed closed: {exc}")

    registry_digest = ""
    artifact_registry_digest = ""
    if authority_registry is not None:
        try:
            registry_digest = _compute_registry_digest(authority_registry)
        except (AttributeError, TypeError, ValueError) as exc:
            blocker_codes.append(BLOCKER_AUTHORITY_FAILED)
            blocker_messages.append(f"authority registry digest failed closed: {exc}")
    if artifact_registry is not None:
        try:
            artifact_registry_digest = _compute_artifact_registry_digest(artifact_registry)
            registry_digest = hashlib.sha256(
                f"{registry_digest}:{artifact_registry_digest}".encode("utf-8")
            ).hexdigest()
        except (AttributeError, TypeError, ValueError) as exc:
            blocker_codes.append(BLOCKER_ARTIFACT_VERIFICATION_FAILED)
            blocker_messages.append(f"artifact registry digest failed closed: {exc}")

    verified_artifact_ids: tuple[str, ...] = ()
    artifact_evidence: dict[str, dict[str, str]] = {}
    if (
        mode != OperationMode.FRAMEWORK
        and isinstance(experiment_manifest, TrackExperimentManifestV1)
        and content_resolver is not None
        and artifact_registry is not None
    ):
        try:
            verified_artifact_ids, artifact_evidence, artifact_blockers = _verify_artifacts(
                mode=mode,
                track=track,
                manifest=experiment_manifest,
                resolver=content_resolver,
                registry=artifact_registry,
            )
            for message in artifact_blockers:
                blocker_codes.append(BLOCKER_ARTIFACT_VERIFICATION_FAILED)
                blocker_messages.append(message)
        except (AttributeError, TypeError, ValueError) as exc:
            blocker_codes.append(BLOCKER_ARTIFACT_VERIFICATION_FAILED)
            blocker_messages.append(f"artifact verification failed closed: {exc}")

    if (
        mode in (OperationMode.EVALUATION, OperationMode.PROMOTION, OperationMode.SERVE)
        and isinstance(experiment_manifest, TrackExperimentManifestV1)
        and content_resolver is not None
    ):
        try:
            evidence_digests, evidence_blockers = _verify_manifest_evidence_content(
                experiment_manifest,
                mode,
                content_resolver,
            )
            content_digests.update(evidence_digests)
            for message in evidence_blockers:
                blocker_codes.append(BLOCKER_PROMOTION_EVIDENCE_MISSING)
                blocker_messages.append(message)
        except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
            blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
            blocker_messages.append(f"manifest evidence verification failed closed: {exc}")

    if mode == OperationMode.PROMOTION and isinstance(experiment_manifest, TrackExperimentManifestV1):
        if not experiment_manifest.evaluation_report_hash:
            blocker_codes.append(BLOCKER_PROMOTION_EVIDENCE_MISSING)
            blocker_messages.append("promotion requires evaluation_report_hash")
        if not experiment_manifest.independent_observation_hashes:
            blocker_codes.append(BLOCKER_PROMOTION_EVIDENCE_MISSING)
            blocker_messages.append("promotion requires independent_observation_hashes")
        if not experiment_manifest.Partner_approval_id:
            blocker_codes.append(BLOCKER_PROMOTION_EVIDENCE_MISSING)
            blocker_messages.append("promotion requires Partner_approval_id")
        if experiment_manifest.claim_state != "evaluated":
            blocker_codes.append(BLOCKER_CLAIM_STATE_INSUFFICIENT)
            blocker_messages.append("promotion requires exact claim_state='evaluated'")
        if authority_registry is not None:
            try:
                authority_registry.verify_registered_approval(
                    experiment_manifest.Partner_approval_id,
                    track,
                    require_cryptographic=True,
                )
            except AuthorityValidationError as exc:
                blocker_codes.append(BLOCKER_PROMOTION_APPROVAL_FAILED)
                blocker_messages.append(f"promotion approval registry verification failed: {exc}")
                if "cryptographic" in str(exc).lower():
                    blocker_codes.append(BLOCKER_CRYPTO_APPROVAL_UNAVAILABLE)
                    blocker_messages.append(
                        "promotion remains blocked until Partner PKI/equivalent signature verification is supplied"
                    )
            except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
                blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
                blocker_messages.append(f"promotion approval verification failed closed: {exc}")

    if mode == OperationMode.SERVE and isinstance(experiment_manifest, TrackExperimentManifestV1):
        if experiment_manifest.claim_state != "promotion_eligible":
            blocker_codes.append(BLOCKER_CLAIM_STATE_INSUFFICIENT)
            blocker_messages.append("serving requires exact claim_state='promotion_eligible'")
        if authority_registry is not None:
            try:
                authority_registry.verify_registered_approval(
                    experiment_manifest.Partner_approval_id,
                    track,
                    require_cryptographic=True,
                )
            except AuthorityValidationError as exc:
                blocker_codes.append(BLOCKER_PROMOTION_APPROVAL_FAILED)
                blocker_messages.append(f"serving approval registry verification failed: {exc}")
                if "cryptographic" in str(exc).lower():
                    blocker_codes.append(BLOCKER_CRYPTO_APPROVAL_UNAVAILABLE)
                    blocker_messages.append(
                        "serving remains blocked until Partner PKI/equivalent signature verification is supplied"
                    )
            except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
                blocker_codes.append(BLOCKER_MALFORMED_CONTEXT)
                blocker_messages.append(f"serving approval verification failed closed: {exc}")

    if mode != OperationMode.FRAMEWORK and artifact_registry_digest:
        # Training may legitimately have no fitted model yet. Preserve a
        # non-empty, explicit artifact-registry evidence record so a passing
        # decision cannot be confused with the old namespace-only scaffold.
        artifact_evidence.setdefault(
            "registry_snapshot",
            {
                "registry_digest": artifact_registry_digest,
                "operation_mode": mode.value,
            },
        )

    return GateDecision(
        allowed=not blocker_codes,
        track=track,
        operation_mode=mode,
        blocker_codes=blocker_codes,
        blocker_messages=blocker_messages,
        manifest_digest=manifest_digest,
        registry_digest=registry_digest,
        content_digests=content_digests,
        artifact_namespace=f"{track}_{mode.value}",
        verified_artifact_ids=verified_artifact_ids,
        artifact_evidence=artifact_evidence,
        authority_id=authority_id,
        evidence_packet_sha256=evidence_packet_sha256,
        evidence_packet_status='verified' if evidence_packet_sha256 else '',
    )


def authorize_lane_execution(
    *,
    mode: OperationMode,
    track: str,
    preflight_context: TrackPreflightContextV1 | None,
    experiment_manifest: TrackExperimentManifestV1 | None,
    authority_registry: AuthorityRegistry | None,
    content_resolver: ContentResolver | None = None,
    artifact_registry: ArtifactRegistry | None = None,
    feature_names: list[str] | None,
    evidence_packet_sha256: str = "",
) -> GateDecision:
    """Return a structured blocker for malformed direct caller objects.

    Packet loaders normally catch malformed JSON. This outer boundary also
    protects direct Python callers from leaking AttributeError/TypeError into
    a worker submission path.
    """
    try:
        return _authorize_lane_execution(
            mode=mode,
            track=track,
            preflight_context=preflight_context,
            experiment_manifest=experiment_manifest,
            authority_registry=authority_registry,
            content_resolver=content_resolver,
            artifact_registry=artifact_registry,
            feature_names=feature_names,
            evidence_packet_sha256=evidence_packet_sha256,
        )
    except LaneExecutionError as exc:
        safe_track = str(track) if track is not None else "unknown"
        try:
            safe_mode = mode if isinstance(mode, OperationMode) else OperationMode(str(mode))
        except (TypeError, ValueError):
            safe_mode = OperationMode.FRAMEWORK
        return _blocked_decision(
            track=safe_track,
            mode=safe_mode,
            codes=list(exc.blocker_codes) or [BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=list(exc.blocker_messages) or [str(exc)],
        )
    except (AttributeError, KeyError, IndexError, OverflowError, OSError, TypeError, ValueError) as exc:
        safe_track = str(track) if track is not None else "unknown"
        try:
            safe_mode = mode if isinstance(mode, OperationMode) else OperationMode(str(mode))
        except (TypeError, ValueError):
            safe_mode = OperationMode.FRAMEWORK
        return _blocked_decision(
            track=safe_track,
            mode=safe_mode,
            codes=[BLOCKER_MALFORMED_CONTEXT],
            messages=[f"lane authorization failed closed: {exc}"],
        )


def assert_lane_execution(**kwargs: Any) -> GateDecision:
    """Authorize and raise before a worker/subprocess can start."""
    decision = authorize_lane_execution(**kwargs)
    decision.raise_if_blocked()
    return decision


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_explicit_lane_request(payload: Any) -> bool:
    """Return true only when a caller intentionally requests a Partner lane."""
    if not isinstance(payload, dict):
        return False
    return (
        _is_truthy(payload.get("Partner_lane"))
        or "track" in payload
        or "Partner_track" in payload
    )


def _load_json_object(path_value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        raise LaneExecutionError(f"{field_name} is mandatory for an explicit Partner lane")
    path = Path(path_value)
    if not path.is_absolute():
        raise LaneExecutionError(f"{field_name} must be an explicit absolute packet path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LaneExecutionError(f"cannot load {field_name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LaneExecutionError(f"{field_name} must contain a JSON object")
    return payload


def _load_and_authorize_evidence_packet(
    path_value: Any,
    *,
    track: str,
    mode: OperationMode,
) -> tuple[str, str, list[str]]:
    """Load the packet used by the production boundary and check its permission."""
    if not isinstance(path_value, str) or not path_value.strip():
        return '', '', ["decision_packet_path is mandatory for non-framework lane operations"]
    packet_path = Path(path_value)
    if not packet_path.is_absolute():
        return '', '', ["decision_packet_path must be an explicit absolute packet path"]
    try:
        payload = load_decision_packet(packet_path)
    except (OSError, ValueError, TypeError) as exc:
        return '', '', [f'decision packet failed closed: {exc}']
    if payload is None:
        return '', '', [f'decision packet does not exist: {path_value}']
    if not verify_decision_packet_hash(payload):
        return '', '', ['decision packet self-hash is missing or invalid']
    try:
        provenance_valid, provenance_errors = verify_decision_packet_provenance(
            payload,
            repo_root=Path(__file__).resolve().parents[3],
        )
    except (OSError, TypeError, ValueError) as exc:
        return '', '', [f'decision packet provenance verification failed closed: {exc}']
    if not provenance_valid:
        return '', '', [f'decision packet provenance is invalid: {provenance_errors}']
    provenance = payload.get('provenance', {})
    packet_hash = str(provenance.get('packet_sha256') or '') if isinstance(provenance, dict) else ''
    readiness = payload.get('execution_readiness')
    if not isinstance(readiness, dict):
        return packet_hash, '', ['decision packet has no execution_readiness section']
    permissions = readiness.get('track_permissions')
    track_permissions = permissions.get(track) if isinstance(permissions, dict) else None
    permission_key = {
        OperationMode.TRAINING: 'training',
        OperationMode.EVALUATION: 'evaluation',
        OperationMode.PROMOTION: 'promotion',
        OperationMode.SERVE: 'serve',
    }.get(mode)
    if not isinstance(track_permissions, dict) or not permission_key:
        return packet_hash, str(readiness.get('status') or ''), [
            f'decision packet has no permission for track={track}, mode={mode.value}'
        ]
    if track_permissions.get(permission_key) is not True:
        return packet_hash, str(readiness.get('status') or ''), [
            f'decision packet blocks track={track}, mode={mode.value}; '
            f'permission={track_permissions.get(permission_key)!r}'
        ]
    return packet_hash, str(readiness.get('status') or ''), []


def authorize_lane_payload(
    payload: dict[str, Any],
    *,
    worker_mode: str | None = None,
) -> GateDecision | None:
    """Load and authorize an explicit production lane request.

    A payload without ``track``/``Partner_lane`` is intentionally outside this
    gate and returns ``None``. An explicit request with any missing or malformed
    packet returns a structured blocked decision.
    """
    if not isinstance(payload, dict):
        return _blocked_decision(
            track="unknown",
            mode=OperationMode.FRAMEWORK,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=["lane payload must be a non-empty JSON object"],
        )
    if not payload:
        return _blocked_decision(
            track="unknown",
            mode=OperationMode.FRAMEWORK,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=["lane payload must be a non-empty JSON object"],
        )
    if not is_explicit_lane_request(payload):
        return None
    track = str(payload.get("track") or payload.get("Partner_track") or "unknown")
    if track not in _EXPLICIT_TRACKS:
        return _blocked_decision(
            track=track,
            mode=OperationMode.FRAMEWORK,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=[f"track must be one of {sorted(_EXPLICIT_TRACKS)}; got {track!r}"],
        )
    raw_mode = payload.get("operation_mode")
    try:
        mode = OperationMode(str(raw_mode))
    except (TypeError, ValueError):
        return _blocked_decision(
            track=track,
            mode=OperationMode.FRAMEWORK,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=[
                "explicit Partner lane requests require operation_mode in "
                "{training,evaluation,promotion,serve,framework}"
            ],
        )
    expected_modes = {
        "train-mtslstm": OperationMode.TRAINING,
        "train-sar-unet": OperationMode.TRAINING,
        "infer-mtslstm": OperationMode.SERVE,
        "sar-segment": OperationMode.SERVE,
        "evaluate-release": OperationMode.EVALUATION,
    }
    expected_mode = expected_modes.get(str(worker_mode))
    if expected_mode is not None and mode != expected_mode:
        return _blocked_decision(
            track=track,
            mode=mode,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=[
                f"operation_mode '{mode.value}' does not match worker mode "
                f"'{worker_mode}' (requires '{expected_mode.value}')"
            ],
        )

    evidence_packet_sha256 = ''
    evidence_packet_status = ''
    if mode != OperationMode.FRAMEWORK:
        evidence_packet_sha256, evidence_packet_status, evidence_blockers = _load_and_authorize_evidence_packet(
            payload.get('decision_packet_path'),
            track=track,
            mode=mode,
        )
        if evidence_blockers:
            missing_packet = not payload.get('decision_packet_path')
            permission_blocked = any('blocks track=' in message for message in evidence_blockers)
            code = (
                BLOCKER_MISSING_EVIDENCE_PACKET
                if missing_packet
                else BLOCKER_EVIDENCE_PACKET_BLOCKED
                if permission_blocked
                else BLOCKER_EVIDENCE_PACKET_INVALID
            )
            return _blocked_decision(
                track=track,
                mode=mode,
                codes=[code],
                messages=evidence_blockers,
            )

    required_fields = (
        "preflight_context_path", "experiment_manifest_path", "authority_registry_path",
        "artifact_registry_path", "content_base_path", "feature_names",
    )
    missing = [field_name for field_name in required_fields if field_name not in payload]
    if missing:
        return _blocked_decision(
            track=track,
            mode=mode,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=[f"explicit Partner request missing required fields: {missing}"],
        )
    if not isinstance(payload.get("feature_names"), list) or not all(
        isinstance(feature, str) for feature in payload["feature_names"]
    ):
        return _blocked_decision(
            track=track,
            mode=mode,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=["feature_names must be a list of strings"],
        )

    try:
        context = TrackPreflightContextV1.from_dict(
            _load_json_object(payload["preflight_context_path"], "preflight_context_path")
        )
        manifest = TrackExperimentManifestV1.from_dict(
            _load_json_object(payload["experiment_manifest_path"], "experiment_manifest_path")
        )
        authority_registry = AuthorityRegistry.from_dict(
            _load_json_object(payload["authority_registry_path"], "authority_registry_path")
        )
        artifact_registry = ArtifactRegistry.from_dict(
            _load_json_object(payload["artifact_registry_path"], "artifact_registry_path")
        )
        content_base_value = payload["content_base_path"]
        if not isinstance(content_base_value, str) or not content_base_value.strip():
            raise LaneExecutionError("content_base_path must be a non-empty absolute path")
        content_base = Path(content_base_value)
        if not content_base.is_absolute():
            raise LaneExecutionError("content_base_path must be an explicit absolute path")
        resolver = ContentResolver(content_base)
    except (
        LaneExecutionError,
        PacketValidationError,
        ManifestValidationError,
        AuthorityValidationError,
        ArtifactNamespaceError,
        LabelValidationError,
        ContentResolutionError,
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        return _blocked_decision(
            track=track,
            mode=mode,
            codes=[BLOCKER_RUNTIME_REQUEST_INVALID],
            messages=[f"explicit Partner packet loading failed closed: {exc}"],
        )

    decision = authorize_lane_execution(
        mode=mode,
        track=track,
        preflight_context=context,
        experiment_manifest=manifest,
        authority_registry=authority_registry,
        content_resolver=resolver,
        artifact_registry=artifact_registry,
        feature_names=payload["feature_names"],
        evidence_packet_sha256=evidence_packet_sha256,
    )
    decision.evidence_packet_status = evidence_packet_status
    return decision


def assert_lane_payload(payload: dict[str, Any], *, worker_mode: str | None = None) -> GateDecision | None:
    """Production convenience wrapper; raises before execution on a Partner block."""
    decision = authorize_lane_payload(payload, worker_mode=worker_mode)
    if decision is not None:
        decision.raise_if_blocked()
    return decision
