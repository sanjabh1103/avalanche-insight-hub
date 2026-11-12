"""Authority registry for signer verification.

This module provides the trust anchor for Partner approval verification.
It replaces format-only hash checks with evidence-bound verification.

The registry is intentionally simple and extensible:
- Each authority has an ID, name, role, and active status
- Approvals can be checked against the registry
- Revocation and expiry are supported

This does NOT implement cryptographic signature verification (which
requires a PKI infrastructure that Partner must provide). Instead, it
provides:
1. Signer authority verification (is this person authorized?)
2. Approval expiry checking (is the approval still valid?)
3. Revocation support (can an approval be revoked?)
4. A clear interface for future cryptographic verification

Until a PKI is available, the registry serves as the trust anchor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable


class AuthorityValidationError(ValueError):
    """Raised when authority verification fails."""


@dataclass(frozen=True)
class AuthorityRecord:
    """A registered authority who can sign Partner approvals.

    The authority must be registered BEFORE any approval can be verified.
    This prevents fake signers from creating valid approvals.
    """

    authority_id: str  # unique identifier (e.g., "Partner_scientist_001")
    name: str  # human-readable name
    role: str  # e.g., "Lead Scientist", "Director"
    active: bool  # whether this authority is currently active
    registered_at: datetime  # when this authority was registered
    deactivated_at: datetime | None = None  # when deactivated (if applicable)
    approved_tracks: tuple[str, ...] = ()  # tracks this authority can approve

    def validate(self) -> None:
        if not self.authority_id.strip():
            raise AuthorityValidationError("authority_id is required")
        if not self.name.strip():
            raise AuthorityValidationError("name is required")
        if not self.role.strip():
            raise AuthorityValidationError("role is required")
        if self.registered_at.tzinfo is None:
            raise AuthorityValidationError("registered_at must be timezone-aware")
        if self.deactivated_at is not None and self.deactivated_at.tzinfo is None:
            raise AuthorityValidationError("deactivated_at must be timezone-aware")
        for track in self.approved_tracks:
            if track not in ("track1", "t2a", "t2b"):
                raise AuthorityValidationError(
                    f"approved track must be track1/t2a/t2b; got {track}"
                )

    def is_active_at(self, when: datetime) -> bool:
        """Check if this authority was active at a given time."""
        if not self.active:
            return False
        if self.deactivated_at is not None and when >= self.deactivated_at:
            return False
        return when >= self.registered_at

    def can_approve_track(self, track: str) -> bool:
        """Check if this authority can approve the given track."""
        # An omitted/empty scope is fail-closed. A registry entry must never
        # become an allow-all signer merely because track rights were omitted.
        return bool(self.approved_tracks) and track in self.approved_tracks

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "authority_record_v1",
            "authority_id": self.authority_id,
            "name": self.name,
            "role": self.role,
            "active": self.active,
            "registered_at": self.registered_at.isoformat(),
            "deactivated_at": self.deactivated_at.isoformat() if self.deactivated_at else None,
            "approved_tracks": list(self.approved_tracks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthorityRecord":
        if not isinstance(data, dict):
            raise AuthorityValidationError("authority record must be a JSON object")
        known = {
            "schema", "authority_id", "name", "role", "active", "registered_at",
            "deactivated_at", "approved_tracks",
        }
        unknown = set(data) - known
        if unknown:
            raise AuthorityValidationError(
                f"AuthorityRecord: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "authority_record_v1":
            raise AuthorityValidationError("wrong schema: expected 'authority_record_v1'")
        required = ("authority_id", "name", "role", "active", "registered_at")
        missing = [field_name for field_name in required if field_name not in data]
        if missing:
            raise AuthorityValidationError(f"missing required fields: {missing}")
        if not isinstance(data["active"], bool):
            raise AuthorityValidationError("active must be a boolean")
        if "approved_tracks" in data and (
            not isinstance(data["approved_tracks"], list)
            or not all(isinstance(track, str) for track in data["approved_tracks"])
        ):
            raise AuthorityValidationError("approved_tracks must be a list of strings")
        record = cls(
            authority_id=str(data["authority_id"]),
            name=str(data["name"]),
            role=str(data["role"]),
            active=bool(data["active"]),
            registered_at=datetime.fromisoformat(str(data["registered_at"])),
            deactivated_at=(
                datetime.fromisoformat(str(data["deactivated_at"]))
                if data.get("deactivated_at") else None
            ),
            approved_tracks=tuple(str(track) for track in data.get("approved_tracks", [])),
        )
        record.validate()
        return record


@dataclass(frozen=True)
class ApprovalRecordV1:
    """Registry entry for a promotion/publication approval.

    ``cryptographic_verified`` is deliberately false by default. It can only
    be set by the Partner PKI/equivalent verifier, never inferred from a hash.
    """

    approval_id: str
    authority_id: str
    approved_tracks: tuple[str, ...]
    approved_at: datetime
    signature_hash: str
    cryptographic_verified: bool = False

    def validate(self) -> None:
        if not self.approval_id.strip() or not self.authority_id.strip():
            raise AuthorityValidationError("approval_id and authority_id are required")
        if not self.approved_tracks:
            raise AuthorityValidationError("approval must cover at least one track")
        if any(track not in ("track1", "t2a", "t2b") for track in self.approved_tracks):
            raise AuthorityValidationError("approval contains an unknown track")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() != timezone.utc.utcoffset(self.approved_at):
            raise AuthorityValidationError("approved_at must be timezone-aware UTC")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.signature_hash):
            raise AuthorityValidationError("signature_hash must be a 64-character hexadecimal hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "approval_record_v1",
            "approval_id": self.approval_id,
            "authority_id": self.authority_id,
            "approved_tracks": list(self.approved_tracks),
            "approved_at": self.approved_at.isoformat(),
            "signature_hash": self.signature_hash,
            "cryptographic_verified": self.cryptographic_verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRecordV1":
        if not isinstance(data, dict):
            raise AuthorityValidationError("approval record must be a JSON object")
        known = {
            "schema", "approval_id", "authority_id", "approved_tracks", "approved_at",
            "signature_hash", "cryptographic_verified",
        }
        unknown = set(data) - known
        if unknown:
            raise AuthorityValidationError(
                f"ApprovalRecordV1: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "approval_record_v1":
            raise AuthorityValidationError("wrong schema: expected 'approval_record_v1'")
        required = (
            "approval_id", "authority_id", "approved_tracks", "approved_at", "signature_hash",
        )
        missing = [field_name for field_name in required if field_name not in data]
        if missing:
            raise AuthorityValidationError(f"missing required fields: {missing}")
        if not isinstance(data["approved_tracks"], list) or not all(
            isinstance(track, str) for track in data["approved_tracks"]
        ):
            raise AuthorityValidationError("approved_tracks must be a list of strings")
        if "cryptographic_verified" in data and not isinstance(data["cryptographic_verified"], bool):
            raise AuthorityValidationError("cryptographic_verified must be a boolean")
        record = cls(
            approval_id=str(data["approval_id"]),
            authority_id=str(data["authority_id"]),
            approved_tracks=tuple(str(track) for track in data["approved_tracks"]),
            approved_at=datetime.fromisoformat(str(data["approved_at"])),
            signature_hash=str(data["signature_hash"]),
            cryptographic_verified=bool(data.get("cryptographic_verified", False)),
        )
        record.validate()
        return record


@dataclass
class AuthorityRegistry:
    """Registry of authorized signers.

    This is the trust anchor. An approval is NOT valid unless the signer
    is registered here and active at the time of approval.
    """

    authorities: dict[str, AuthorityRecord] = field(default_factory=dict)
    revoked_approvals: set[str] = field(default_factory=set)
    approval_records: dict[str, ApprovalRecordV1] = field(default_factory=dict)
    approval_expiry_days: int = 365  # approvals expire after 1 year by default
    # This callback is injected only by a verified Partner PKI/equivalent
    # integration. A JSON field claiming cryptographic_verified=True is not a
    # trust anchor and is deliberately ignored by promotion checks.
    cryptographic_verifier: Callable[[ApprovalRecordV1], bool] | None = field(
        default=None, repr=False, compare=False
    )

    def register(self, authority: AuthorityRecord) -> None:
        """Register a new authority."""
        authority.validate()
        if authority.authority_id in self.authorities:
            raise AuthorityValidationError(
                f"duplicate authority_id is rejected: '{authority.authority_id}'"
            )
        self.authorities[authority.authority_id] = authority

    def revoke_approval(self, approval_id: str) -> None:
        """Revoke an approval by ID."""
        self.revoked_approvals.add(approval_id)

    def register_approval(self, approval: ApprovalRecordV1) -> None:
        approval.validate()
        authority = self.authorities.get(approval.authority_id)
        if authority is None:
            raise AuthorityValidationError(
                f"approval authority '{approval.authority_id}' is not registered"
            )
        for track in approval.approved_tracks:
            if not authority.can_approve_track(track):
                raise AuthorityValidationError(
                    f"authority '{approval.authority_id}' cannot approve track '{track}'"
                )
        if approval.approval_id in self.approval_records:
            raise AuthorityValidationError(
                f"duplicate approval_id is rejected: '{approval.approval_id}'"
            )
        self.approval_records[approval.approval_id] = approval

    def is_approval_revoked(self, approval_id: str) -> bool:
        """Check if an approval has been revoked."""
        return approval_id in self.revoked_approvals

    def verify_authority(
        self,
        signer_name: str,
        signer_role: str,
        approved_tracks: tuple[str, ...],
        approved_at: datetime,
    ) -> AuthorityRecord:
        """Verify that a signer is a registered, active authority.

        Returns the AuthorityRecord if valid, raises AuthorityValidationError if not.
        """
        # Find authority by name and role
        matching = [
            a for a in self.authorities.values()
            if a.name == signer_name and a.role == signer_role
        ]
        if not matching:
            raise AuthorityValidationError(
                f"signer '{signer_name}' with role '{signer_role}' is not "
                f"a registered authority"
            )
        authority = matching[0]
        # Check authority was active at approval time
        if not authority.is_active_at(approved_at):
            raise AuthorityValidationError(
                f"authority '{signer_name}' was not active at {approved_at}"
            )
        # Check authority can approve all requested tracks
        for track in approved_tracks:
            if not authority.can_approve_track(track):
                raise AuthorityValidationError(
                    f"authority '{signer_name}' cannot approve track '{track}'"
                )
        return authority

    def verify_approval_validity(
        self,
        approval_id: str,
        approved_at: datetime,
        check_time: datetime | None = None,
    ) -> None:
        """Verify that an approval is not revoked or expired.

        Raises AuthorityValidationError if revoked or expired.
        """
        if self.is_approval_revoked(approval_id):
            raise AuthorityValidationError(
                f"approval '{approval_id}' has been revoked"
            )
        check_time = check_time or datetime.now(timezone.utc)
        expiry = approved_at + timedelta(days=self.approval_expiry_days)
        if check_time > expiry:
            raise AuthorityValidationError(
                f"approval '{approval_id}' expired at {expiry.isoformat()}"
            )

    def verify_approval(
        self,
        approval_id: str,
        signer_name: str,
        signer_role: str,
        signature_hash: str,
        approved_tracks: tuple[str, ...],
        approved_at: datetime,
        check_time: datetime | None = None,
        authority_id: str | None = None,
    ) -> AuthorityRecord:
        """Full approval verification: authority + revocation + expiry.

        This is the comprehensive check that should be called before
        accepting any approval as valid.

        Returns the AuthorityRecord if valid, raises if not.
        """
        # 1. Verify signer is a registered, active authority
        authority = self.verify_authority(
            signer_name, signer_role, approved_tracks, approved_at
        )
        if authority_id and authority.authority_id != authority_id:
            raise AuthorityValidationError(
                f"approval authority mismatch: packet='{authority_id}', "
                f"registry='{authority.authority_id}'"
            )
        # 2. Verify approval is not revoked or expired
        self.verify_approval_validity(approval_id, approved_at, check_time)
        # 3. Note: cryptographic signature verification would go here
        #    once a PKI is available. Until then, the hash is format-validated
        #    by the packet loader, and the authority registry provides the
        #    trust anchor.
        return authority

    def verify_registered_approval(
        self,
        approval_id: str,
        track: str,
        *,
        check_time: datetime | None = None,
        require_cryptographic: bool = True,
    ) -> ApprovalRecordV1:
        """Resolve a named approval from the registry for promotion/serving."""
        approval = self.approval_records.get(approval_id)
        if approval is None:
            raise AuthorityValidationError(
                f"approval '{approval_id}' is not registered"
            )
        if track not in approval.approved_tracks:
            raise AuthorityValidationError(
                f"approval '{approval_id}' does not cover track '{track}'"
            )
        authority = self.authorities.get(approval.authority_id)
        if authority is None or not authority.is_active_at(approval.approved_at):
            raise AuthorityValidationError(
                f"approval '{approval_id}' has no active registered authority"
            )
        if not authority.can_approve_track(track):
            raise AuthorityValidationError(
                f"authority '{authority.authority_id}' cannot approve track '{track}'"
            )
        self.verify_approval_validity(
            approval.approval_id,
            approval.approved_at,
            check_time=check_time,
        )
        cryptographically_verified = False
        if self.cryptographic_verifier is not None:
            try:
                cryptographically_verified = bool(self.cryptographic_verifier(approval))
            except Exception as exc:
                raise AuthorityValidationError(
                    f"cryptographic approval verifier failed: {exc}"
                ) from exc
        if require_cryptographic and not cryptographically_verified:
            raise AuthorityValidationError(
                f"approval '{approval_id}' lacks Partner cryptographic verification"
            )
        return approval

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "authority_registry_v1",
            "authorities": [
                authority.to_dict()
                for authority in sorted(self.authorities.values(), key=lambda item: item.authority_id)
            ],
            "approval_records": [
                approval.to_dict()
                for approval in sorted(self.approval_records.values(), key=lambda item: item.approval_id)
            ],
            "revoked_approvals": sorted(self.revoked_approvals),
            "approval_expiry_days": self.approval_expiry_days,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthorityRegistry":
        if not isinstance(data, dict):
            raise AuthorityValidationError("authority registry must be a JSON object")
        known = {"schema", "authorities", "approval_records", "revoked_approvals", "approval_expiry_days"}
        unknown = set(data) - known
        if unknown:
            raise AuthorityValidationError(
                f"AuthorityRegistry: unknown fields rejected: {sorted(unknown)}"
            )
        if data.get("schema") != "authority_registry_v1":
            raise AuthorityValidationError("wrong schema: expected 'authority_registry_v1'")
        authorities = data.get("authorities", [])
        approvals = data.get("approval_records", [])
        revoked = data.get("revoked_approvals", [])
        expiry_days = data.get("approval_expiry_days", 365)
        if not isinstance(authorities, list) or not isinstance(approvals, list):
            raise AuthorityValidationError("authorities and approval_records must be lists")
        if not isinstance(revoked, list) or not all(isinstance(value, str) for value in revoked):
            raise AuthorityValidationError("revoked_approvals must be a list of strings")
        if isinstance(expiry_days, bool) or not isinstance(expiry_days, int) or expiry_days <= 0:
            raise AuthorityValidationError("approval_expiry_days must be a positive integer")
        registry = cls(approval_expiry_days=expiry_days)
        for item in authorities:
            registry.register(AuthorityRecord.from_dict(item))
        for item in approvals:
            registry.register_approval(ApprovalRecordV1.from_dict(item))
        registry.revoked_approvals = set(revoked)
        return registry

    @classmethod
    def from_json(cls, path: Path) -> "AuthorityRegistry":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthorityValidationError(f"cannot load authority registry {path}: {exc}") from exc
        return cls.from_dict(data)
