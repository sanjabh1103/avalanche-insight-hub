"""Track 1 / T2A / T2B lane contracts for Partner five-level danger-level ML.

This module is ADDITIVE. It does not modify any denylisted file, existing
model, or active inference path. It provides fail-closed contracts that
reject binary targets, incomplete five-class outputs, unsigned placeholders,
and cross-lane contamination.

The learned-output contract is SEPARATE from the existing rule-weighted
shadow danger semantics in ``shadow_danger_semantics.py``. That module
remains a threshold-based shadow diagnostic; this module defines the
learned ML output contract required by the Partner approval request.
"""

from __future__ import annotations

from .label_record import (
    PartnerLabelRecordV1,
    PartnerLabelInventoryV1,
    LabelValidationError,
    load_label_inventory_from_json,
)
from .prediction import DangerPredictionV1, PredictionValidationError
from .experiment_manifest import TrackExperimentManifestV1, ManifestValidationError
from .lane_allowlists import (
    TRACK1_ALLOWLIST,
    T2A_ALLOWLIST,
    T2A_DENYLIST,
    TRACK1_DENYLIST,
    T2A_FORCING_FEATURES,
    T2A_TERRAIN_FEATURES,
    TRACK1_STATION_FEATURES,
    TRACK1_SNOWPACK_FEATURES,
    validate_t2a_features,
    validate_track1_features,
    check_no_overlap,
    normalize_feature_name,
    check_feature_lineage,
    FeatureContaminationError,
)
from .claim_state import ClaimState, ClaimRecord, ClaimValidationError
from .packet_loaders import (
    ApprovalPacketV1,
    ReferenceUnitV1,
    IssueValidityRuleV1,
    RightsManifestV1,
    ForcingSourceManifestV1,
    StationAnchorManifestV1,
    TrackPreflightContextV1,
    PacketValidationError,
)
from .lane_preflight import (
    run_lane_preflight,
    assert_lane_authorized,
    LanePreflightError,
    PreflightResult,
    OperationMode,
)
from .authority_registry import (
    AuthorityRecord,
    ApprovalRecordV1,
    AuthorityRegistry,
    AuthorityValidationError,
)
from .lane_execution_wrapper import (
    authorize_lane_execution,
    assert_lane_execution,
    LaneExecutionError,
    GateDecision,
    authorize_lane_payload,
    assert_lane_payload,
    is_explicit_lane_request,
)
from .content_resolver import (
    ContentResolver,
    ContentResolutionError,
    ContentVerificationResult,
)
from .artifact_registry import (
    ArtifactBindingV1,
    ArtifactRegistry,
    ArtifactNamespaceError,
)

__all__ = [
    "PartnerLabelRecordV1",
    "PartnerLabelInventoryV1",
    "LabelValidationError",
    "load_label_inventory_from_json",
    "DangerPredictionV1",
    "PredictionValidationError",
    "TrackExperimentManifestV1",
    "ManifestValidationError",
    "TRACK1_ALLOWLIST",
    "T2A_ALLOWLIST",
    "T2A_DENYLIST",
    "TRACK1_DENYLIST",
    "T2A_FORCING_FEATURES",
    "T2A_TERRAIN_FEATURES",
    "TRACK1_STATION_FEATURES",
    "TRACK1_SNOWPACK_FEATURES",
    "validate_t2a_features",
    "validate_track1_features",
    "check_no_overlap",
    "normalize_feature_name",
    "check_feature_lineage",
    "FeatureContaminationError",
    "ClaimState",
    "ClaimRecord",
    "ClaimValidationError",
    "ApprovalPacketV1",
    "ReferenceUnitV1",
    "IssueValidityRuleV1",
    "RightsManifestV1",
    "ForcingSourceManifestV1",
    "StationAnchorManifestV1",
    "TrackPreflightContextV1",
    "PacketValidationError",
    "run_lane_preflight",
    "assert_lane_authorized",
    "LanePreflightError",
    "PreflightResult",
    "OperationMode",
    "AuthorityRecord",
    "ApprovalRecordV1",
    "AuthorityRegistry",
    "AuthorityValidationError",
    "authorize_lane_execution",
    "assert_lane_execution",
    "LaneExecutionError",
    "GateDecision",
    "authorize_lane_payload",
    "assert_lane_payload",
    "is_explicit_lane_request",
    "ContentResolver",
    "ContentResolutionError",
    "ContentVerificationResult",
    "ArtifactBindingV1",
    "ArtifactRegistry",
    "ArtifactNamespaceError",
]
