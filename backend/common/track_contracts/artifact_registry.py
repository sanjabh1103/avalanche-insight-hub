"""Lane artifact namespace isolation.

Per Codex audit P6: fitted artifacts must be lane-bound at runtime.
This module provides artifact binding that ties model, preprocessor,
feature, source, and split lineage to a specific track.

Track 1 artifacts cannot load for T2A, and vice versa.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ArtifactNamespaceError(ValueError):
    """Raised when artifact namespace isolation is violated."""


@dataclass(frozen=True)
class ArtifactBindingV1:
    """A lane-bound artifact binding.

    Ties an artifact (model, preprocessor, etc.) to a specific track,
    feature hash, source hash, split hash, and namespace.
    """

    artifact_id: str  # unique identifier
    artifact_type: str  # "model", "preprocessor", "feature_extractor"
    track: str  # "track1" or "t2a"
    feature_hash: str  # SHA-256 of the feature list
    source_hash: str  # SHA-256 of the data source
    split_hash: str  # SHA-256 of the split manifest
    namespace: str  # e.g., "t2a_training", "track1_serving"
    created_at: str  # ISO timestamp
    content_hash: str = ""  # SHA-256 of the serialized artifact bytes
    content_path: str = ""  # relative path under the ContentResolver root

    def validate(self) -> None:
        if self.track not in ("track1", "t2a"):
            raise ArtifactNamespaceError(
                f"track must be track1/t2a; got {self.track}"
            )
        if not self.artifact_id.strip():
            raise ArtifactNamespaceError("artifact_id is required")
        if self.artifact_type not in ("model", "preprocessor", "feature_extractor", "calibrator"):
            raise ArtifactNamespaceError(
                f"artifact_type must be model/preprocessor/feature_extractor/calibrator; "
                f"got {self.artifact_type}"
            )
        for hash_field in ("feature_hash", "source_hash", "split_hash"):
            value = getattr(self, hash_field)
            if not isinstance(value, str) or len(value) != 64:
                raise ArtifactNamespaceError(
                    f"{hash_field} must be 64-char hex; got {value}"
                )
            try:
                int(value, 16)
            except ValueError as exc:
                raise ArtifactNamespaceError(
                    f"{hash_field} must contain only hexadecimal characters"
                ) from exc
        if self.content_hash:
            if len(self.content_hash) != 64:
                raise ArtifactNamespaceError("content_hash must be a 64-char hexadecimal hash")
            try:
                int(self.content_hash, 16)
            except ValueError as exc:
                raise ArtifactNamespaceError("content_hash must be hexadecimal") from exc
        if bool(self.content_hash) != bool(self.content_path):
            raise ArtifactNamespaceError(
                "content_hash and content_path must be supplied together"
            )
        if self.content_path:
            content_path = Path(self.content_path)
            if content_path.is_absolute() or ".." in content_path.parts:
                raise ArtifactNamespaceError(
                    "content_path must be relative and cannot contain parent traversal"
                )
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            raise ArtifactNamespaceError("created_at is required")
        try:
            created_at = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ArtifactNamespaceError(
                "created_at must be a valid ISO-8601 timestamp"
            ) from exc
        if created_at.tzinfo is None or created_at.utcoffset() != timezone.utc.utcoffset(created_at):
            raise ArtifactNamespaceError("created_at must be an explicit UTC timestamp")
        # Namespace must start with the track
        if not self.namespace.startswith(self.track):
            raise ArtifactNamespaceError(
                f"namespace '{self.namespace}' must start with track '{self.track}'"
            )

    def matches_track(self, requested_track: str) -> bool:
        """Check if this artifact can be used for the requested track."""
        return self.track == requested_track

    def matches_namespace(self, requested_namespace: str) -> bool:
        """Check if this artifact belongs to the requested namespace."""
        return self.namespace == requested_namespace

    def matches_lineage(
        self,
        *,
        feature_hash: str,
        source_hash: str,
        split_hash: str,
    ) -> bool:
        """Check if this artifact's lineage matches the requested lineage."""
        return (
            self.feature_hash == feature_hash
            and self.source_hash == source_hash
            and self.split_hash == split_hash
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "artifact_binding_v1",
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "track": self.track,
            "feature_hash": self.feature_hash,
            "source_hash": self.source_hash,
            "split_hash": self.split_hash,
            "namespace": self.namespace,
            "created_at": self.created_at,
            "content_hash": self.content_hash,
            "content_path": self.content_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactBindingV1":
        if not isinstance(data, dict):
            raise ArtifactNamespaceError("artifact binding must be a JSON object")
        known = {
            "schema", "artifact_id", "artifact_type", "track", "feature_hash",
            "source_hash", "split_hash", "namespace", "created_at",
            "content_hash", "content_path",
        }
        unknown = set(data) - known
        if unknown:
            raise ArtifactNamespaceError(
                f"ArtifactBindingV1: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "artifact_binding_v1":
            raise ArtifactNamespaceError("wrong schema: expected 'artifact_binding_v1'")
        required = (
            "artifact_id", "artifact_type", "track", "feature_hash", "source_hash",
            "split_hash", "namespace", "created_at",
        )
        missing = [field_name for field_name in required if field_name not in data]
        if missing:
            raise ArtifactNamespaceError(f"missing required fields: {missing}")
        binding = cls(
            artifact_id=str(data["artifact_id"]),
            artifact_type=str(data["artifact_type"]),
            track=str(data["track"]),
            feature_hash=str(data["feature_hash"]),
            source_hash=str(data["source_hash"]),
            split_hash=str(data["split_hash"]),
            namespace=str(data["namespace"]),
            created_at=str(data["created_at"]),
            content_hash=str(data.get("content_hash", "")),
            content_path=str(data.get("content_path", "")),
        )
        binding.validate()
        return binding


class ArtifactRegistry:
    """Registry of lane-bound artifacts.

    Enforces that artifacts are only loaded for their bound track.
    Cross-lane artifact swaps are rejected.
    """

    def __init__(self):
        self._artifacts: dict[str, ArtifactBindingV1] = {}

    def register(self, artifact: ArtifactBindingV1) -> None:
        artifact.validate()
        if artifact.artifact_id in self._artifacts:
            raise ArtifactNamespaceError(
                f"duplicate artifact_id is rejected: '{artifact.artifact_id}'"
            )
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> ArtifactBindingV1 | None:
        return self._artifacts.get(artifact_id)

    def verify_artifact_for_track(
        self,
        artifact_id: str,
        requested_track: str,
        requested_namespace: str,
        *,
        feature_hash: str | None = None,
        source_hash: str | None = None,
        split_hash: str | None = None,
        content_resolver: Any | None = None,
        require_content: bool = False,
    ) -> ArtifactBindingV1:
        """Verify that an artifact can be used for the requested track.

        Raises ArtifactNamespaceError if:
        - Artifact is not registered
        - Artifact is bound to a different track (cross-lane swap)
        - Artifact namespace doesn't match
        - Artifact lineage doesn't match (if hashes provided)
        """
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ArtifactNamespaceError(
                f"artifact '{artifact_id}' is not registered"
            )
        if not artifact.matches_track(requested_track):
            raise ArtifactNamespaceError(
                f"cross-lane artifact swap: artifact '{artifact_id}' is bound "
                f"to track '{artifact.track}' but requested for track "
                f"'{requested_track}'"
            )
        if not artifact.matches_namespace(requested_namespace):
            raise ArtifactNamespaceError(
                f"namespace mismatch: artifact '{artifact_id}' has namespace "
                f"'{artifact.namespace}' but requested '{requested_namespace}'"
            )
        if feature_hash is not None and not artifact.matches_lineage(
            feature_hash=feature_hash,
            source_hash=source_hash or "",
            split_hash=split_hash or "",
        ):
            raise ArtifactNamespaceError(
                f"lineage mismatch for artifact '{artifact_id}': "
                f"declared lineage does not match requested lineage"
            )
        if require_content and (content_resolver is None or not artifact.content_hash or not artifact.content_path):
            raise ArtifactNamespaceError(
                f"artifact '{artifact_id}' has no content-bound bytes for this operation"
            )
        if artifact.content_hash and artifact.content_path:
            if content_resolver is None:
                if require_content:
                    raise ArtifactNamespaceError(
                        f"content resolver is required for artifact '{artifact_id}'"
                    )
            else:
                try:
                    content_resolver.resolve_and_verify(
                        artifact.content_hash,
                        artifact.content_path,
                    )
                except Exception as exc:
                    raise ArtifactNamespaceError(
                        f"artifact content verification failed for '{artifact_id}': {exc}"
                    ) from exc
        return artifact

    def list_artifacts_for_track(self, track: str) -> list[ArtifactBindingV1]:
        """List all artifacts bound to a specific track."""
        return [a for a in self._artifacts.values() if a.track == track]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "artifact_registry_v1",
            "artifacts": [
                artifact.to_dict()
                for artifact in sorted(self._artifacts.values(), key=lambda item: item.artifact_id)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRegistry":
        if not isinstance(data, dict):
            raise ArtifactNamespaceError("artifact registry must be a JSON object")
        unknown = set(data) - {"schema", "artifacts"}
        if unknown:
            raise ArtifactNamespaceError(
                f"ArtifactRegistry: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "artifact_registry_v1":
            raise ArtifactNamespaceError("wrong schema: expected 'artifact_registry_v1'")
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, list):
            raise ArtifactNamespaceError("artifacts must be a list")
        registry = cls()
        for item in artifacts:
            registry.register(ArtifactBindingV1.from_dict(item))
        return registry

    @classmethod
    def from_json(cls, path: Path) -> "ArtifactRegistry":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactNamespaceError(f"cannot load artifact registry {path}: {exc}") from exc
        return cls.from_dict(data)
