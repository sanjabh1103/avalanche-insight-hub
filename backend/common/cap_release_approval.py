"""CAP release approval — signed human approval, authority identity, release artifact, and audit event before outbound alerts.

Adds a mandatory human approval step to the CAP publication pipeline.
When CAP_RELEASE_APPROVAL_ENABLED is true, CAP alerts cannot be published
until an authorized approver signs the release.

Env flags:
  CAP_RELEASE_APPROVAL_ENABLED — require signed approval (default: false)
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

CAP_RELEASE_APPROVAL_ENABLED = os.getenv('CAP_RELEASE_APPROVAL_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)


@dataclass
class ReleaseApproval:
    """CAP release approval record."""
    cap_alert_id: str = ''
    approver_id: str = ''
    approver_name: str = ''
    authority_org: str = ''
    approval_timestamp: str | None = None
    signature: str | None = None
    release_artifact_ref: str | None = None
    audit_event_id: str | None = None
    status: str = 'pending'
    rejection_reason: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'cap_alert_id': self.cap_alert_id,
            'approver_id': self.approver_id,
            'approver_name': self.approver_name,
            'authority_org': self.authority_org,
            'approval_timestamp': self.approval_timestamp,
            'signature': self.signature,
            'release_artifact_ref': self.release_artifact_ref,
            'audit_event_id': self.audit_event_id,
            'status': self.status,
            'rejection_reason': self.rejection_reason,
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


def _generate_signature(cap_alert_id: str, approver_id: str, authority_org: str, timestamp: str) -> str:
    """Generate a deterministic signature for the approval."""
    payload = f'{cap_alert_id}:{approver_id}:{authority_org}:{timestamp}'
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


def request_approval(cap_alert_id: str, cap_alert_xml: str = '') -> ReleaseApproval:
    """Create a pending approval request for a CAP alert.

    Args:
        cap_alert_id: CAP alert identifier.
        cap_alert_xml: CAP alert XML content (stored as artifact reference).

    Returns:
        ReleaseApproval with status='pending'.
    """
    return ReleaseApproval(
        cap_alert_id=cap_alert_id,
        status='pending',
        metadata={'cap_alert_xml_hash': hashlib.sha256(cap_alert_xml.encode()).hexdigest()[:16]} if cap_alert_xml else {},
    )


def approve_release(
    approval: ReleaseApproval,
    approver_id: str,
    approver_name: str,
    authority_org: str,
) -> ReleaseApproval:
    """Sign and approve a CAP release.

    Generates signature, sets approval timestamp, creates release artifact
    reference and audit event ID.

    Args:
        approval: Pending ReleaseApproval to approve.
        approver_id: Approver's user ID.
        approver_name: Approver's full name.
        authority_org: Authority organization (e.g. 'SLF', 'IMD').

    Returns:
        Updated ReleaseApproval with status='approved'.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    signature = _generate_signature(approval.cap_alert_id, approver_id, authority_org, timestamp)
    artifact_ref = f'cap_release:{approval.cap_alert_id}:{timestamp}'
    audit_id = f'audit:{approval.cap_alert_id}:{approver_id}'

    approval.approver_id = approver_id
    approval.approver_name = approver_name
    approval.authority_org = authority_org
    approval.approval_timestamp = timestamp
    approval.signature = signature
    approval.release_artifact_ref = artifact_ref
    approval.audit_event_id = audit_id
    approval.status = 'approved'

    return approval


def reject_release(
    approval: ReleaseApproval,
    approver_id: str,
    approver_name: str,
    authority_org: str,
    reason: str,
) -> ReleaseApproval:
    """Reject a CAP release.

    Args:
        approval: Pending ReleaseApproval to reject.
        approver_id: Approver's user ID.
        approver_name: Approver's full name.
        authority_org: Authority organization.
        reason: Rejection reason.

    Returns:
        Updated ReleaseApproval with status='rejected'.
    """
    approval.approver_id = approver_id
    approval.approver_name = approver_name
    approval.authority_org = authority_org
    approval.status = 'rejected'
    approval.rejection_reason = reason

    return approval


def check_release_approved(approval: ReleaseApproval | None) -> tuple[bool, str | None]:
    """Check if a CAP release is approved and signature is valid.

    Args:
        approval: ReleaseApproval to check (None = no approval record).

    Returns:
        Tuple of (is_approved, reason_if_not).
    """
    if not CAP_RELEASE_APPROVAL_ENABLED:
        return True, None

    if approval is None:
        return False, 'release approval pending: no approval record'

    if approval.status != 'approved':
        return False, f'release approval {approval.status}: {approval.rejection_reason or "pending"}'

    if not approval.signature:
        return False, 'release approval: missing signature'

    if not approval.approval_timestamp:
        return False, 'release approval: missing timestamp'

    expected_sig = _generate_signature(
        approval.cap_alert_id,
        approval.approver_id,
        approval.authority_org,
        approval.approval_timestamp,
    )
    if approval.signature != expected_sig:
        return False, 'release approval: invalid signature'

    return True, None
