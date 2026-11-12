"""Partner reviewed label conversion interface — G5.

Defines the BLOCKED interface for converting PublicBulletinCandidateV1
to PartnerLabelRecordV1. This is NOT an implementation — it is a contract
that documents the required Partner approval inputs.

BLOCKED UNTIL: Partner provides all of:
- Five-level label inventory (approved historical labels)
- Reviewer identity and quality status
- Rights status (approved, not pending)
- Cryptographic signature/approval mechanism
- Support thresholds and seasonal/regional policy
- Reference unit binding (Pir Panjal sector or warning unit)
- Station/anchor evidence (for Track 1)

No automatic conversion is permitted. The interface exists to document
the gap and prevent silent reintroduction of a conversion path.

G5 exit gate: The interface is defined but BLOCKED. No code path converts
a public candidate to a training-eligible label without all required
Partner approval inputs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PartnerApprovalInputsV1:
    """Required Partner approval inputs for label conversion — G5.

    ALL fields must be provided and validated before any conversion
    from PublicBulletinCandidateV1 to PartnerLabelRecordV1 can proceed.
    Any missing field blocks the conversion.
    """

    # Partner-approved five-level label inventory
    approved_label_inventory: str | None = None  # Reference to approved labels
    # Reviewer identity (Partner scientist who approved)
    approved_by: str | None = None
    # Approval timestamp (UTC)
    approved_at: str | None = None
    # Rights status — must be 'approved' (not 'pending')
    rights_status: str = 'pending'
    # Quality status — must be 'reviewed' (not 'unreviewed')
    quality_status: str = 'unreviewed'
    # Cryptographic signature
    signature: str | None = None
    # Signer identity
    signer_identity: str | None = None
    # Trust anchor (e.g., Partner root certificate)
    trust_anchor: str | None = None
    # Signature expiry
    signature_expiry: str | None = None
    # Support thresholds (minimum sample count per level)
    support_thresholds: dict[int, int] = field(default_factory=dict)
    # Seasonal policy version
    seasonal_policy_version: str | None = None
    # Regional policy version
    regional_policy_version: str | None = None
    # Reference unit binding
    reference_unit: str | None = None

    @property
    def is_complete(self) -> bool:
        """Check if ALL required Partner approval inputs are provided."""
        return all([
            self.approved_label_inventory is not None,
            self.approved_by is not None,
            self.approved_at is not None,
            self.rights_status == 'approved',
            self.quality_status == 'reviewed',
            self.signature is not None,
            self.signer_identity is not None,
            self.trust_anchor is not None,
            self.signature_expiry is not None,
            len(self.support_thresholds) > 0,
            self.seasonal_policy_version is not None,
            self.regional_policy_version is not None,
            self.reference_unit is not None,
        ])

    @property
    def missing_inputs(self) -> list[str]:
        """List the missing required inputs."""
        missing = []
        if self.approved_label_inventory is None:
            missing.append('approved_label_inventory')
        if self.approved_by is None:
            missing.append('approved_by')
        if self.approved_at is None:
            missing.append('approved_at')
        if self.rights_status != 'approved':
            missing.append(f'rights_status (must be "approved", got "{self.rights_status}")')
        if self.quality_status != 'reviewed':
            missing.append(f'quality_status (must be "reviewed", got "{self.quality_status}")')
        if self.signature is None:
            missing.append('signature')
        if self.signer_identity is None:
            missing.append('signer_identity')
        if self.trust_anchor is None:
            missing.append('trust_anchor')
        if self.signature_expiry is None:
            missing.append('signature_expiry')
        if not self.support_thresholds:
            missing.append('support_thresholds')
        if self.seasonal_policy_version is None:
            missing.append('seasonal_policy_version')
        if self.regional_policy_version is None:
            missing.append('regional_policy_version')
        if self.reference_unit is None:
            missing.append('reference_unit')
        return missing


class ReviewedLabelConversionV1(ABC):
    """BLOCKED interface for converting public candidates to approved labels — G5.

    This interface defines the contract for converting a PublicBulletinCandidateV1
    to a PartnerLabelRecordV1. It is BLOCKED — no implementation exists.

    The conversion requires ALL Partner approval inputs to be provided and validated.
    No automatic conversion is permitted.

    BLOCKED UNTIL: Partner provides all required approval inputs.

    P1 (proactive): 4-level to 5-level scale conversion policy.
    If Partner provides labels on a 4-level scale (1-4) instead of the required
    5-level scale (1-5), the conversion implementer must:
    1. Document the mapping policy (e.g., Level 4→4, Level 3→3, etc.)
    2. Decide whether to merge Level 5 into Level 4 (as Swiss RAvaFcast does)
       or to split Level 4 into Levels 4 and 5 based on additional criteria
    3. Record the conversion policy in PartnerApprovalInputsV1.seasonal_policy_version
    4. Validate that the resulting labels satisfy PartnerLabelRecordV1.validate()
       (which enforces MIN_LEVEL=1, MAX_LEVEL=5)
    5. Report the conversion as a known limitation in the decision packet

    Per Partner_APPROVAL_TABLE_EXPLAINER Page 8: "If Level 5 is not learnable,
    return to Partner." The system must NOT silently merge levels without
    explicit Partner approval and documented policy.
    """

    @abstractmethod
    def can_convert(self, approval_inputs: PartnerApprovalInputsV1) -> bool:
        """Check if conversion can proceed with the given approval inputs.

        Returns False if any required input is missing.
        """
        ...

    @abstractmethod
    def get_blocking_reasons(self, approval_inputs: PartnerApprovalInputsV1) -> list[str]:
        """Return the list of missing/blocked inputs that prevent conversion.

        Returns an empty list if conversion can proceed.
        """
        ...

    @abstractmethod
    def convert(self, candidate: Any, approval_inputs: PartnerApprovalInputsV1) -> Any:
        """Convert a PublicBulletinCandidateV1 to a PartnerLabelRecordV1.

        BLOCKED: This method must raise NotImplementedError until all Partner
        approval inputs are available and validated.

        Raises:
            NotImplementedError: Always — no implementation exists.
            ValueError: If approval inputs are incomplete.
        """
        ...


# G5: The conversion is BLOCKED — this is documented, not implemented
CONVERSION_STATUS = 'BLOCKED'
CONVERSION_BLOCKED_REASON = (
    'No Partner-approved five-level labels, reviewer identity, rights status, '
    'cryptographic signature, support thresholds, or policy versions are available. '
    'The conversion from PublicBulletinCandidateV1 to PartnerLabelRecordV1 cannot proceed.'
)


def get_conversion_status() -> dict[str, Any]:
    """Return the current conversion status — always BLOCKED.

    G5 exit gate: The conversion is explicitly documented as BLOCKED.
    No code path converts a public candidate to a training-eligible label.
    """
    return {
        'schema_version': 'Partner_reviewed_label_conversion_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': CONVERSION_STATUS,
        'blocked_reason': CONVERSION_BLOCKED_REASON,
        'required_inputs': [
            'approved_label_inventory',
            'approved_by',
            'approved_at',
            'rights_status (must be "approved")',
            'quality_status (must be "reviewed")',
            'signature',
            'signer_identity',
            'trust_anchor',
            'signature_expiry',
            'support_thresholds',
            'seasonal_policy_version',
            'regional_policy_version',
            'reference_unit',
        ],
        'interface_defined': True,
        'implementation_exists': False,
        'note': (
            'The interface is defined to document the gap. '
            'No automatic conversion is permitted. '
            'P11 conditional training remains blocked until Partner provides all required inputs.'
        ),
    }
