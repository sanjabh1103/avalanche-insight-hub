"""Fail-closed contracts for the open-forcing research lane."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone


OPEN_FORCING_LANE = "open_forcing_distributed_candidate"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LICENSE_REVIEW_STATUSES = {"pending", "approved", "rejected"}
_UNRESOLVED_METADATA = {"unknown", "unresolved", "best_match"}
ASSIMILATION_DISCLOSURE = (
    "No Partner or customer station feed is required. Public forecast and reanalysis "
    "products may assimilate observations; this is not an observation-free system."
)


class OpenForcingContractError(ValueError):
    """Raised when open-forcing provenance or safety metadata is invalid."""


def _validate_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise OpenForcingContractError(f"{field_name} must be timezone-aware UTC")


@dataclass(frozen=True)
class SourceSnapshot:
    """Immutable identity for one public forcing or validation source snapshot."""

    source_id: str
    product: str
    issue_time: datetime
    valid_time: datetime
    retrieved_at: datetime
    source_as_of: datetime
    native_resolution_m: float
    content_sha256: str
    license_id: str
    provider: str = ""
    model_id: str = ""
    run_id: str = ""
    lead_time_hours: float | None = None
    assimilation_disclosure: str = ""
    license_review_status: str = "pending"
    research_only: bool = True

    def validate(self) -> None:
        for name, value in (
            ("issue_time", self.issue_time),
            ("valid_time", self.valid_time),
            ("retrieved_at", self.retrieved_at),
            ("source_as_of", self.source_as_of),
        ):
            _validate_utc(value, name)
        if not self.source_id.strip() or not self.product.strip() or not self.provider.strip():
            raise OpenForcingContractError("source_id, product and provider are required")
        if (
            not self.model_id.strip()
            or not self.run_id.strip()
            or self.model_id.strip().lower() in _UNRESOLVED_METADATA
            or self.run_id.strip().lower() in _UNRESOLVED_METADATA
        ):
            raise OpenForcingContractError("exact model_id and run_id are required")
        if not self.assimilation_disclosure.strip():
            raise OpenForcingContractError("assimilation_disclosure is required")
        if self.license_review_status not in _LICENSE_REVIEW_STATUSES:
            raise OpenForcingContractError("unsupported license_review_status")
        if not self.research_only:
            raise OpenForcingContractError("source snapshots must remain research_only")
        if self.lead_time_hours is not None and self.lead_time_hours < 0:
            raise OpenForcingContractError("lead_time_hours cannot be negative")
        if self.native_resolution_m <= 0:
            raise OpenForcingContractError("native_resolution_m must be positive")
        if not _SHA256_RE.fullmatch(self.content_sha256.lower()):
            raise OpenForcingContractError("content_sha256 must be a 64-character SHA-256 hex digest")
        if not self.license_id.strip():
            raise OpenForcingContractError("license_id is required")
        if self.retrieved_at < self.issue_time:
            raise OpenForcingContractError("retrieved_at cannot precede issue_time")

    @property
    def snapshot_id(self) -> str:
        """Stable identifier for manifests and replay records."""

        self.validate()
        material = "|".join(
            (
                self.source_id,
                self.product,
                self.issue_time.isoformat(),
                self.valid_time.isoformat(),
                self.content_sha256.lower(),
                self.provider,
                self.model_id,
                self.run_id,
                self.license_review_status,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OpenForcingPolicy:
    """Safety boundary for candidate outputs.

    The lane may be enabled for research execution, but it is never eligible
    for production scoring, training, official warnings, or customer authority
    without a separate approved governance decision.
    """

    enabled: bool = False
    production_eligible: bool = False
    training_eligible: bool = False
    warning_authority: bool = False
    label_provenance: str = "unreviewed"

    def validate(self) -> None:
        if self.production_eligible or self.training_eligible or self.warning_authority:
            raise OpenForcingContractError(
                "open-forcing candidate cannot be production-eligible, training-eligible, "
                "or warning-authoritative"
            )
        if not self.label_provenance.strip():
            raise OpenForcingContractError("label_provenance is required")


def ensure_utc(value: datetime) -> datetime:
    """Return a UTC datetime or fail closed for naive timestamps."""

    _validate_utc(value, "timestamp")
    return value.astimezone(timezone.utc)
