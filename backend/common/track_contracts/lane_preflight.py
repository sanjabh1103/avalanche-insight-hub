"""Lane preflight gate — the single entry point for Track 1/T2A execution.

This module provides the runtime gate that must be invoked before any
Track 1 or T2A training, evaluation, inference, or promotion. It wires
the track contracts and packet loaders into the actual execution boundary.

Design principles (per Codex audit P0/P5):
- Additive: does not modify denylisted files (train_model.py, etc.)
- Fail-closed: rejects when manifest, approval, source, rights, or
  evaluation artifact is missing
- Operation modes: framework, training, evaluation, promotion, serve
- Manifest is MANDATORY for all modes except framework
- One shared preflight at the lane-specific training/prediction boundary
- The existing inference path cannot present a generic or proxy result
  as a Track 1/T2A result without a valid lane manifest

Usage:
    from backend.common.track_contracts.lane_preflight import (
        run_lane_preflight, OperationMode
    )
    result = run_lane_preflight(
        mode=OperationMode.TRAINING,
        track="t2a",
        preflight_context=ctx,
        feature_names=features,
        experiment_manifest=manifest,
    )
    if not result.allowed:
        raise LanePreflightError(result.blockers)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .packet_loaders import TrackPreflightContextV1, PacketValidationError
from .lane_allowlists import (
    validate_t2a_features,
    validate_track1_features,
    FeatureContaminationError,
)
from .experiment_manifest import TrackExperimentManifestV1, ManifestValidationError


class LanePreflightError(ValueError):
    """Raised when a lane preflight gate fails."""


class OperationMode(str, Enum):
    """Operation modes for lane execution.

    Each mode has different requirements:
    - FRAMEWORK: contract validation only (no manifest required)
    - TRAINING: requires manifest with claim_state >= gates_passed
    - EVALUATION: requires manifest with claim_state >= trained
    - PROMOTION: requires manifest with claim_state >= evaluated
    - SERVE: requires manifest with claim_state >= promotion_eligible
    """
    FRAMEWORK = "framework"
    TRAINING = "training"
    EVALUATION = "evaluation"
    PROMOTION = "promotion"
    SERVE = "serve"


# Minimum claim state required for each operation mode
_MODE_MIN_CLAIM_STATE: dict[OperationMode, str] = {
    OperationMode.FRAMEWORK: "unapproved",
    OperationMode.TRAINING: "gates_passed",
    OperationMode.EVALUATION: "trained",
    OperationMode.PROMOTION: "evaluated",
    OperationMode.SERVE: "promotion_eligible",
}

# Claim state ordering (from claim_state.py)
_CLAIM_STATE_ORDER = [
    "unapproved",
    "framework_ready",
    "gates_passed",
    "training_eligible",
    "trained",
    "evaluated",
    "promotion_eligible",
    "rejected",
]


def _claim_state_index(state: str) -> int:
    """Get the index of a claim state in the ordering."""
    try:
        return _CLAIM_STATE_ORDER.index(state)
    except ValueError:
        return -1


@dataclass
class PreflightResult:
    """Result of a lane preflight check."""

    allowed: bool
    track: str
    mode: OperationMode
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: TrackExperimentManifestV1 | None = None
    context: TrackPreflightContextV1 | None = None

    def raise_if_blocked(self) -> None:
        """Raise LanePreflightError if not allowed."""
        if not self.allowed:
            raise LanePreflightError(
                f"Lane preflight blocked for track '{self.track}' "
                f"mode '{self.mode.value}': {self.blockers}"
            )


def run_lane_preflight(
    *,
    mode: OperationMode,
    track: str,
    preflight_context: TrackPreflightContextV1,
    feature_names: list[str],
    experiment_manifest: TrackExperimentManifestV1 | None = None,
) -> PreflightResult:
    """Run the lane preflight gate.

    This is the SINGLE entry point that must be invoked before any
    Track 1 or T2A training, evaluation, inference, or promotion.

    Args:
        mode: Operation mode (framework, training, evaluation, promotion, serve)
        track: "track1" or "t2a"
        preflight_context: The validated Partner packet context
        feature_names: The feature list to be used
        experiment_manifest: Experiment manifest (MANDATORY for all modes
            except FRAMEWORK; providing None for other modes is a hard blocker)

    Returns:
        PreflightResult with allowed=True if all gates pass, or
        allowed=False with blockers if any gate fails.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    if not isinstance(preflight_context, TrackPreflightContextV1):
        return PreflightResult(
            allowed=False,
            track=str(track),
            mode=mode if isinstance(mode, OperationMode) else OperationMode.FRAMEWORK,
            blockers=["preflight_context must be a TrackPreflightContextV1 instance"],
            warnings=warnings,
            manifest=experiment_manifest,
            context=None,
        )

    # Gate 1: Manifest is mandatory for all modes except FRAMEWORK
    if mode != OperationMode.FRAMEWORK and experiment_manifest is None:
        blockers.append(
            f"experiment_manifest is MANDATORY for mode '{mode.value}'; "
            f"received None — execution blocked"
        )

    # Gate 2: Validate preflight context
    try:
        preflight_context.validate()
    except PacketValidationError as exc:
        blockers.append(f"preflight_context: {exc}")

    # Gate 3: Verify track matches context
    if preflight_context.track != track:
        blockers.append(
            f"track mismatch: preflight_context.track='{preflight_context.track}' "
            f"but requested track='{track}'"
        )

    # Gate 4: Validate feature list against track allowlist
    try:
        if track == "t2a":
            validate_t2a_features(feature_names)
        elif track == "track1":
            validate_track1_features(feature_names)
        else:
            blockers.append(f"unknown track: {track}")
    except FeatureContaminationError as exc:
        blockers.append(f"feature_validation: {exc}")

    # Gate 5: Validate experiment manifest (if provided)
    if experiment_manifest is not None:
        try:
            experiment_manifest.validate()
        except ManifestValidationError as exc:
            blockers.append(f"experiment_manifest: {exc}")

        # Verify manifest track matches
        if experiment_manifest.track != track:
            blockers.append(
                f"manifest track mismatch: manifest.track='{experiment_manifest.track}' "
                f"but requested track='{track}'"
            )

        # Verify manifest claim_state is sufficient for the requested mode
        min_state = _MODE_MIN_CLAIM_STATE.get(mode, "unapproved")
        min_idx = _claim_state_index(min_state)
        actual_idx = _claim_state_index(experiment_manifest.claim_state)
        if actual_idx < 0:
            blockers.append(
                f"manifest has unknown claim_state: '{experiment_manifest.claim_state}'"
            )
        elif experiment_manifest.claim_state == "rejected":
            blockers.append("manifest claim_state 'rejected' is terminal and cannot authorize execution")
        elif actual_idx < min_idx:
            blockers.append(
                f"manifest claim_state '{experiment_manifest.claim_state}' "
                f"is insufficient for mode '{mode.value}' "
                f"(requires >= '{min_state}')"
            )

    # Gate 6: Verify approval covers this track
    if track not in preflight_context.approval.approved_tracks:
        blockers.append(
            f"approval does not cover track '{track}'; "
            f"approved: {preflight_context.approval.approved_tracks}"
        )

    allowed = len(blockers) == 0
    return PreflightResult(
        allowed=allowed,
        track=track,
        mode=mode,
        blockers=blockers,
        warnings=warnings,
        manifest=experiment_manifest,
        context=preflight_context if allowed else None,
    )


def assert_lane_authorized(
    *,
    mode: OperationMode,
    track: str,
    preflight_context: TrackPreflightContextV1,
    feature_names: list[str],
    experiment_manifest: TrackExperimentManifestV1 | None = None,
) -> PreflightResult:
    """Run preflight and raise if blocked.

    This is the convenience function for use at the actual training/inference
    boundary. It raises LanePreflightError if any gate fails.
    """
    result = run_lane_preflight(
        mode=mode,
        track=track,
        preflight_context=preflight_context,
        feature_names=feature_names,
        experiment_manifest=experiment_manifest,
    )
    result.raise_if_blocked()
    return result
