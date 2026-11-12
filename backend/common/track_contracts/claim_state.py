"""Claim state and claim record for evidence-bound assertions.

Every claim made about Track 1, T2A, or T2B must have a controlled source,
proof level, and permitted audience. This prevents the overstatement that
the Codex audit identified in the GLM 5.2 assessment.

Claim states follow the progression from unapproved to promotion_eligible.
No claim can skip states — each transition requires evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class ClaimValidationError(ValueError):
    """Raised when a claim record fails validation."""


VALID_PROOF_LEVELS = (
    "none",
    "local_artifact",
    "swiss_reproduction",
    "himalayan_shadow",
    "himalayan_validated",
    "operational",
)

VALID_AUDIENCES = (
    "internal_only",
    "Partner_review",
    "Partner_signed",
    "scientific_publication",
    "public",
)

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

# Claims that are PERMANENTLY PROHIBITED per PlanB.md STOP list
PROHIBITED_CLAIM_PATTERNS: tuple[str, ...] = (
    "unprecedented",
    "first ever",
    "state of the art",
    "sota",
    "scientifically superior",
    "station-free means observation-free",
    "avalanche prediction from snowpack execution",
    "independent validation from t2a/t2b agreement",
    "3 km meteorological skill",
    "operational readiness",
    "validated himalayan accuracy",
    "95% code-ready",
    "95% ready",
    "code-ready",
)


@dataclass(frozen=True)
class ClaimRecord:
    """A single evidence-bound claim with source, proof level, and audience.

    This prevents the overstatement patterns identified in the Codex audit:
    - "Swiss metrics are Partner reference metrics" → rejected
    - "95% code-ready" → rejected
    - "Complete Swiss reproduction" → downgraded to research rehearsal
    """

    claim_id: str
    statement: str
    track: str  # track1, t2a, t2b, or shared
    claim_state: str
    proof_level: str
    permitted_audience: str
    controlling_source: str  # document/file/hash that controls this claim
    created_at: datetime
    approved_by: str = ""
    notes: str = ""

    def validate(self) -> None:
        if not self.claim_id.strip():
            raise ClaimValidationError("claim_id is required")
        if not self.statement.strip():
            raise ClaimValidationError("statement is required")
        if self.track not in ("track1", "t2a", "t2b", "shared"):
            raise ClaimValidationError(
                f"track must be track1/t2a/t2b/shared; got {self.track}"
            )
        if self.claim_state not in VALID_CLAIM_STATES:
            raise ClaimValidationError(
                f"claim_state must be one of {VALID_CLAIM_STATES}; got {self.claim_state}"
            )
        if self.proof_level not in VALID_PROOF_LEVELS:
            raise ClaimValidationError(
                f"proof_level must be one of {VALID_PROOF_LEVELS}; got {self.proof_level}"
            )
        if self.permitted_audience not in VALID_AUDIENCES:
            raise ClaimValidationError(
                f"permitted_audience must be one of {VALID_AUDIENCES}; "
                f"got {self.permitted_audience}"
            )
        if not self.controlling_source.strip():
            raise ClaimValidationError("controlling_source is required")
        self._validate_utc(self.created_at, "created_at")
        # Check for prohibited language
        statement_lower = self.statement.lower()
        for pattern in PROHIBITED_CLAIM_PATTERNS:
            if pattern in statement_lower:
                raise ClaimValidationError(
                    f"statement contains prohibited language: '{pattern}'"
                )
        # State/proof level matrix: claim state must be backed by sufficient proof
        STATE_MIN_PROOF: dict[str, str] = {
            "unapproved": "none",
            "framework_ready": "local_artifact",
            "gates_passed": "swiss_reproduction",  # requires at least reproduction evidence
            "training_eligible": "himalayan_shadow",
            "trained": "himalayan_shadow",
            "evaluated": "himalayan_shadow",
            "promotion_eligible": "himalayan_validated",
        }
        min_proof = STATE_MIN_PROOF.get(self.claim_state, "none")
        proof_order = list(VALID_PROOF_LEVELS)
        if proof_order.index(self.proof_level) < proof_order.index(min_proof):
            raise ClaimValidationError(
                f"claim_state '{self.claim_state}' requires proof_level >= '{min_proof}'; "
                f"got '{self.proof_level}'"
            )
        # Promotion claims require Partner-signed audience
        if self.claim_state == "promotion_eligible" and self.permitted_audience != "Partner_signed":
            raise ClaimValidationError(
                f"promotion_eligible claims require Partner_signed audience; "
                f"got {self.permitted_audience}"
            )

    @staticmethod
    def _validate_utc(value: datetime, field_name: str) -> None:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ClaimValidationError(f"{field_name} must be timezone-aware UTC")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "claim_record_v1",
            "claim_id": self.claim_id,
            "statement": self.statement,
            "track": self.track,
            "claim_state": self.claim_state,
            "proof_level": self.proof_level,
            "permitted_audience": self.permitted_audience,
            "controlling_source": self.controlling_source,
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "notes": self.notes,
        }


class ClaimState:
    """Helper for managing claim state transitions."""

    @staticmethod
    def can_transition(from_state: str, to_state: str) -> bool:
        """Check if a state transition is valid (no skipping).

        Rejected is TERMINAL — a rejected claim cannot transition to any
        other state. A new claim must receive a new claim ID.
        """
        order = list(VALID_CLAIM_STATES)
        # Rejected is terminal: cannot leave rejected state
        if from_state == "rejected" and to_state != "rejected":
            return False
        # Can always transition TO rejected
        if to_state == "rejected":
            return True
        try:
            from_idx = order.index(from_state)
            to_idx = order.index(to_state)
        except ValueError:
            return False
        # Can only advance by 1 step at a time (or stay)
        return to_idx == from_idx + 1 or to_idx == from_idx

    @staticmethod
    def requires_approval_for(state: str) -> bool:
        """Check if a claim state requires Partner approval."""
        return state in ("gates_passed", "training_eligible", "promotion_eligible")
