"""Immutable replay and physical-review artifacts for the open-forcing lane.

The artifacts in this module describe what was compared and how complete the
source coverage was. They do not manufacture labels, promote a model, or turn
an open-source proxy into an operational warning. A later candidate pipeline
must supply an approved label contract separately.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .contracts import OpenForcingContractError, ensure_utc
from .source_registry import ForcingSnapshotManifest


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVIEW_STATUSES = {"pending", "select", "refine", "decline"}
_HOLDOUT_STRATEGIES = {"forward_time", "leave_one_source_out", "leave_one_region_out"}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(value: float, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise OpenForcingContractError(f"{name} must be finite")
    return converted


@dataclass(frozen=True)
class SourceReplay:
    """Content-addressed source replay identity with research-only locks."""

    replay_id: str
    manifest_hash: str
    payload_sha256: str
    source_ids: tuple[str, ...]
    created_at: datetime
    synthetic_inputs_present: bool = False
    training_eligible: bool = False
    production_eligible: bool = False

    @classmethod
    def from_payload(
        cls,
        manifest: ForcingSnapshotManifest,
        payload: bytes | bytearray | memoryview | Mapping[str, Any] | Sequence[Any],
        *,
        created_at: datetime,
    ) -> "SourceReplay":
        manifest.validate()
        if isinstance(payload, (bytes, bytearray, memoryview)):
            payload_sha256 = hashlib.sha256(bytes(payload)).hexdigest()
        else:
            payload_sha256 = _canonical_hash(payload)
        source_ids = tuple(sorted({snapshot.source_id for snapshot in manifest.snapshots}))
        replay_id = _canonical_hash(
            {
                "manifest_hash": manifest.manifest_hash,
                "payload_sha256": payload_sha256,
                "source_ids": source_ids,
            }
        )
        replay = cls(
            replay_id=replay_id,
            manifest_hash=manifest.manifest_hash,
            payload_sha256=payload_sha256,
            source_ids=source_ids,
            created_at=ensure_utc(created_at),
        )
        replay.validate()
        return replay

    def validate(self) -> None:
        for name, value in (
            ("replay_id", self.replay_id),
            ("manifest_hash", self.manifest_hash),
            ("payload_sha256", self.payload_sha256),
        ):
            if not isinstance(value, str) or not _SHA256_RE.fullmatch(value.lower()):
                raise OpenForcingContractError(f"{name} must be a SHA-256 hex digest")
        if not self.source_ids or any(not source.strip() for source in self.source_ids):
            raise OpenForcingContractError("source_ids must contain non-empty source identifiers")
        if tuple(sorted(set(self.source_ids))) != self.source_ids:
            raise OpenForcingContractError("source_ids must be sorted and unique")
        ensure_utc(self.created_at)
        if self.synthetic_inputs_present or self.training_eligible or self.production_eligible:
            raise OpenForcingContractError(
                "open-forcing replay must remain non-synthetic, non-training, and non-production"
            )


@dataclass(frozen=True)
class CoverageMask:
    """Per-pixel availability and freshness mask for a replay window."""

    grid_manifest_hash: str
    source_snapshot_id: str
    pixel_ids: tuple[str, ...]
    available: tuple[bool, ...]
    freshness_hours: tuple[float | None, ...]
    max_freshness_hours: float
    missingness_policy: str = "fail_or_hold"

    def validate(self) -> None:
        if not _SHA256_RE.fullmatch(self.grid_manifest_hash.lower()):
            raise OpenForcingContractError("grid_manifest_hash must be a SHA-256 hex digest")
        if not self.source_snapshot_id.strip():
            raise OpenForcingContractError("source_snapshot_id is required")
        if not self.pixel_ids or len(set(self.pixel_ids)) != len(self.pixel_ids):
            raise OpenForcingContractError("pixel_ids must be non-empty and unique")
        if len(self.available) != len(self.pixel_ids) or len(self.freshness_hours) != len(self.pixel_ids):
            raise OpenForcingContractError("coverage arrays must match pixel_ids length")
        if self.missingness_policy not in {"fail", "hold", "fail_or_hold"}:
            raise OpenForcingContractError("unsupported missingness policy")
        max_freshness = _finite(self.max_freshness_hours, "max_freshness_hours")
        if max_freshness < 0.0:
            raise OpenForcingContractError("max_freshness_hours cannot be negative")
        for available, freshness in zip(self.available, self.freshness_hours):
            if not isinstance(available, bool):
                raise OpenForcingContractError("available values must be booleans")
            if available and freshness is None:
                raise OpenForcingContractError("available pixels require freshness metadata")
            if freshness is not None and _finite(freshness, "freshness_hours") < 0.0:
                raise OpenForcingContractError("freshness_hours cannot be negative")

    @property
    def coverage_fraction(self) -> float:
        self.validate()
        return sum(self.available) / len(self.available)

    @property
    def missing_pixel_ids(self) -> tuple[str, ...]:
        self.validate()
        return tuple(pixel_id for pixel_id, present in zip(self.pixel_ids, self.available) if not present)

    @property
    def mask_hash(self) -> str:
        self.validate()
        return _canonical_hash(
            {
                "grid_manifest_hash": self.grid_manifest_hash.lower(),
                "source_snapshot_id": self.source_snapshot_id,
                "pixel_ids": self.pixel_ids,
                "available": self.available,
                "freshness_hours": self.freshness_hours,
                "max_freshness_hours": self.max_freshness_hours,
                "missingness_policy": self.missingness_policy,
            }
        )


@dataclass(frozen=True)
class PhysicalValidationReport:
    """Paired physical/reference comparison awaiting scientific interpretation."""

    report_id: str
    replay_id: str
    reference_source_id: str
    candidate_source_id: str
    variables: tuple[str, ...]
    sample_count: int
    paired_count: int
    holdout_strategy: str
    independent_holdout: bool
    provenance_complete: bool
    metrics: tuple[tuple[str, float], ...]
    reviewer_id: str | None = None
    decision: str = "pending"
    synthetic_inputs_present: bool = False
    label_eligible: bool = False
    label_contract_approved: bool = False

    def validate(self) -> None:
        if not _SHA256_RE.fullmatch(self.report_id.lower()) or not _SHA256_RE.fullmatch(self.replay_id.lower()):
            raise OpenForcingContractError("report_id and replay_id must be SHA-256 hex digests")
        if not self.reference_source_id.strip() or not self.candidate_source_id.strip():
            raise OpenForcingContractError("comparison source identifiers are required")
        if not self.variables or any(not variable.strip() for variable in self.variables):
            raise OpenForcingContractError("at least one comparison variable is required")
        if len(set(self.variables)) != len(self.variables):
            raise OpenForcingContractError("comparison variables must be unique")
        if self.sample_count < 0 or self.paired_count < 0 or self.paired_count > self.sample_count:
            raise OpenForcingContractError("sample counts are inconsistent")
        if self.holdout_strategy not in _HOLDOUT_STRATEGIES:
            raise OpenForcingContractError("unsupported holdout strategy")
        if self.decision not in _REVIEW_STATUSES:
            raise OpenForcingContractError("unsupported review decision")
        if self.reviewer_id is not None and not self.reviewer_id.strip():
            raise OpenForcingContractError("reviewer_id cannot be blank")
        if self.decision != "pending" and not self.reviewer_id:
            raise OpenForcingContractError("non-pending decisions require a named reviewer")
        for name, value in self.metrics:
            if not name.strip() or not math.isfinite(float(value)):
                raise OpenForcingContractError("metrics must have finite named values")
        if self.synthetic_inputs_present or self.label_eligible:
            raise OpenForcingContractError(
                "synthetic or label-eligible inputs cannot enter a Tier-A physical report"
            )
        if self.decision == "select" and (not self.independent_holdout or not self.provenance_complete):
            raise OpenForcingContractError(
                "select requires an independent holdout and complete provenance"
            )

    @property
    def candidate_pipeline_allowed(self) -> bool:
        """Remain locked until a separate approved label contract exists."""

        self.validate()
        return bool(
            self.decision == "select"
            and self.independent_holdout
            and self.provenance_complete
            and self.label_contract_approved
            and not self.synthetic_inputs_present
            and not self.label_eligible
        )
