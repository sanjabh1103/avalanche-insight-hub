"""Track experiment manifest contract.

Binds a track experiment to its approvals, target hash, source hash,
feature hash, split hash, fitted-artifact IDs, and claim status.

This ensures that Track 1, T2A, and T2B remain separate in data, contracts,
models, storage, claims, and approvals — as required by the Partner approval
request (page 2, Track separation decision) and PlanB.md (P0 blind spot:
"Track 2B can collapse into Track 1").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any


class ManifestValidationError(ValueError):
    """Raised when a track experiment manifest fails validation."""


def _reject_unknown_fields(data: dict[str, Any], known: set[str]) -> None:
    unknown = set(data) - known
    if unknown:
        raise ManifestValidationError(
            f"TrackExperimentManifestV1: unknown fields rejected: {sorted(unknown)}"
        )


VALID_TRACKS = ("track1", "t2a", "t2b")
VALID_CLAIM_STATES = (
    "unapproved",
    "framework_ready",
    "gates_passed",
    "training_eligible",
    "trained",
    "evaluated",
    "promotion_eligible",
    "rejected",
)


@dataclass(frozen=True)
class TrackExperimentManifestV1:
    """Immutable manifest binding a track experiment to its evidence chain.

    This manifest is created BEFORE training and updated only when a gate
    passes. It prevents:
    - Cross-lane contamination (Track 1 features in T2A, etc.)
    - Training without signed approvals
    - Promotion without evaluation
    - Missing provenance hashes
    """

    track: str  # track1, t2a, t2b
    experiment_id: str  # unique experiment identifier
    target_hash: str  # SHA-256 of the label inventory
    source_hash: str  # SHA-256 of the source/forcing manifest
    feature_hash: str  # SHA-256 of the feature whitelist
    split_hash: str  # SHA-256 of the frozen split manifest
    approvals: tuple[str, ...]  # list of signed approval IDs
    claim_state: str  # current claim state
    fitted_artifact_ids: tuple[str, ...] = ()  # model artifact hashes
    evaluation_report_hash: str = ""  # SHA-256 of frozen evaluation report
    independent_observation_hashes: tuple[str, ...] = ()  # independent observation evidence
    Partner_approval_id: str = ""  # Partner sign-off ID for promotion
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""
    evidence_paths: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        _HEX_RE = re.compile(r'^[0-9a-f]{64}$')
        if self.track not in VALID_TRACKS:
            raise ManifestValidationError(
                f"track must be one of {VALID_TRACKS}; got {self.track}"
            )
        if not self.experiment_id.strip():
            raise ManifestValidationError("experiment_id is required")
        # Hashes must be valid 64-char hexadecimal (not just any 64-char string)
        for hash_name, hash_value in [
            ("target_hash", self.target_hash),
            ("source_hash", self.source_hash),
            ("feature_hash", self.feature_hash),
            ("split_hash", self.split_hash),
        ]:
            if not _HEX_RE.fullmatch(hash_value.lower()):
                raise ManifestValidationError(
                    f"{hash_name} must be a valid 64-char hexadecimal SHA-256; "
                    f"got non-hex characters"
                )
        if not self.approvals:
            raise ManifestValidationError(
                "at least one signed approval ID is required"
            )
        if any(not isinstance(approval, str) or not approval.strip() for approval in self.approvals):
            raise ManifestValidationError("approvals must contain non-empty strings")
        if self.claim_state not in VALID_CLAIM_STATES:
            raise ManifestValidationError(
                f"claim_state must be one of {VALID_CLAIM_STATES}; "
                f"got {self.claim_state}"
            )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timezone.utc.utcoffset(self.created_at):
            raise ManifestValidationError("created_at must be timezone-aware UTC")
        if any(not isinstance(artifact_id, str) or not artifact_id.strip() for artifact_id in self.fitted_artifact_ids):
            raise ManifestValidationError("fitted_artifact_ids must contain non-empty strings")
        if self.evaluation_report_hash and not _HEX_RE.fullmatch(self.evaluation_report_hash.lower()):
            raise ManifestValidationError("evaluation_report_hash must be a valid 64-char hexadecimal SHA-256")
        for observation_hash in self.independent_observation_hashes:
            if not _HEX_RE.fullmatch(str(observation_hash).lower()):
                raise ManifestValidationError(
                    "independent_observation_hashes must contain valid 64-char hexadecimal SHA-256 values"
                )
        allowed_evidence_keys = {"evaluation_report"} | {
            f"independent_observation_{index}"
            for index in range(len(self.independent_observation_hashes))
        }
        unknown_evidence = set(self.evidence_paths) - allowed_evidence_keys
        if unknown_evidence:
            raise ManifestValidationError(
                f"evidence_paths contains unsupported keys: {sorted(unknown_evidence)}"
            )
        for key, path in self.evidence_paths.items():
            if not isinstance(path, str) or not path.strip():
                raise ManifestValidationError(f"evidence_paths['{key}'] must be a non-empty path")
        # Training requires gates_passed or higher
        training_eligible_states = (
            "gates_passed",
            "training_eligible",
            "trained",
            "evaluated",
            "promotion_eligible",
        )
        if self.fitted_artifact_ids and self.claim_state not in training_eligible_states:
            raise ManifestValidationError(
                f"fitted artifacts require claim_state >= gates_passed; "
                f"got {self.claim_state}"
            )
        # Promotion requires evaluated state AND fitted artifacts AND evaluation evidence
        if self.claim_state == "promotion_eligible":
            if not self.fitted_artifact_ids:
                raise ManifestValidationError(
                    "promotion_eligible requires fitted artifacts"
                )
            if not self.evaluation_report_hash:
                raise ManifestValidationError(
                    "promotion_eligible requires evaluation_report_hash "
                    "(frozen evaluation evidence)"
                )
            if not self.independent_observation_hashes:
                raise ManifestValidationError(
                    "promotion_eligible requires independent_observation_hashes "
                    "(at least one independent observation)"
                )
            if not self.Partner_approval_id:
                raise ManifestValidationError(
                    "promotion_eligible requires Partner_approval_id "
                    "(Partner sign-off on promotion)"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "track_experiment_manifest_v1",
            "track": self.track,
            "experiment_id": self.experiment_id,
            "target_hash": self.target_hash,
            "source_hash": self.source_hash,
            "feature_hash": self.feature_hash,
            "split_hash": self.split_hash,
            "approvals": list(self.approvals),
            "claim_state": self.claim_state,
            "fitted_artifact_ids": list(self.fitted_artifact_ids),
            "evaluation_report_hash": self.evaluation_report_hash,
            "independent_observation_hashes": list(self.independent_observation_hashes),
            "Partner_approval_id": self.Partner_approval_id,
            "created_at": self.created_at.isoformat(),
            "notes": self.notes,
            "evidence_paths": dict(self.evidence_paths),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackExperimentManifestV1":
        """Create from dict with strict schema validation."""
        if not isinstance(data, dict):
            raise ManifestValidationError("manifest must be a JSON object")
        if data.get('schema') != 'track_experiment_manifest_v1':
            raise ManifestValidationError(
                f"wrong schema: expected 'track_experiment_manifest_v1', "
                f"got '{data.get('schema')}'"
            )
        _reject_unknown_fields(data, {
            'schema', 'track', 'experiment_id', 'target_hash', 'source_hash',
            'feature_hash', 'split_hash', 'approvals', 'claim_state',
            'fitted_artifact_ids', 'evaluation_report_hash',
            'independent_observation_hashes', 'Partner_approval_id', 'created_at', 'notes',
            'evidence_paths',
        })
        required = ['track', 'experiment_id', 'target_hash', 'source_hash',
                    'feature_hash', 'split_hash', 'approvals', 'claim_state']
        for field_name in required:
            if field_name not in data:
                raise ManifestValidationError(f"missing required field: {field_name}")
        list_fields = {
            'approvals': data['approvals'],
            'fitted_artifact_ids': data.get('fitted_artifact_ids', []),
            'independent_observation_hashes': data.get('independent_observation_hashes', []),
        }
        for field_name, value in list_fields.items():
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ManifestValidationError(f"{field_name} must be a list of strings")
        if 'evidence_paths' in data and not isinstance(data['evidence_paths'], dict):
            raise ManifestValidationError("evidence_paths must be an object")
        if 'created_at' in data and data['created_at'] is not None and not isinstance(data['created_at'], str):
            raise ManifestValidationError("created_at must be an ISO-8601 string")
        manifest = cls(
            track=data['track'],
            experiment_id=data['experiment_id'],
            target_hash=data['target_hash'],
            source_hash=data['source_hash'],
            feature_hash=data['feature_hash'],
            split_hash=data['split_hash'],
            approvals=tuple(data['approvals']),
            claim_state=data['claim_state'],
            fitted_artifact_ids=tuple(data.get('fitted_artifact_ids', [])),
            evaluation_report_hash=data.get('evaluation_report_hash', ''),
            independent_observation_hashes=tuple(data.get('independent_observation_hashes', [])),
            Partner_approval_id=data.get('Partner_approval_id', ''),
            created_at=(
                datetime.fromisoformat(data['created_at'])
                if data.get('created_at') is not None
                else datetime.now(timezone.utc)
            ),
            notes=data.get('notes', ''),
            evidence_paths=dict(data.get('evidence_paths', {})),
        )
        manifest.validate()
        return manifest
