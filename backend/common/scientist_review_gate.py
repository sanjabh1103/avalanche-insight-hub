"""Scientist review gate for forecast publication and model promotion.

Enforces a human-in-the-loop checkpoint for stages that require scientist
approval before proceeding. This gate is separate from the automated UQ/brier
gate and the synthetic-input gate — it provides an additional layer of
oversight for publication and drift-check decisions.

Dry-run behavior:
  ``dry_run=True`` is the only non-production bypass; production cannot
  disable this gate through an environment variable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.common.verification_contracts import (
    EvidencePacket,
    TYPED_WORKFLOW_CONTRACTS,
    VerificationPacket,
    WORKFLOW_CONTRACT_MAP,
)

@dataclass
class ReviewDecision:
    """Result of a scientist review gate evaluation."""
    stage: str
    approved: bool
    blocked: bool
    needs_review: bool
    reason: str
    contract_violations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'stage': self.stage,
            'approved': self.approved,
            'blocked': self.blocked,
            'needs_review': self.needs_review,
            'reason': self.reason,
            'contract_violations': self.contract_violations,
            'metadata': self.metadata,
        }


def evaluate_scientist_review_gate(
    stage: str,
    packet: EvidencePacket | VerificationPacket,
    *,
    dry_run: bool = False,
    override: bool = False,
    region_key: str = '',
    gate_key: str = '',
) -> ReviewDecision:
    """Evaluate whether a stage requires scientist review.

    Gate logic:
    1. If dry_run → auto-approve (CI/dry-run mode, no Supabase query)
    2. If stage not in WORKFLOW_CONTRACT_MAP → block (unknown stage)
    3. Validate workflow contract → violations trigger needs_review
    4. If gate_policy is 'hard' or 'soft' and no violations → approve
    5. If gate_policy is 'scientist_review' → check Supabase for approved case
       - If approved case exists → approve
       - If no approved case → block with needs_review
    6. If violations → needs_review with violation details

    Args:
        stage: Pipeline stage name from WORKFLOW_CONTRACT_MAP
        packet: EvidencePacket or VerificationPacket for the stage
        dry_run: If True, auto-approve (CI/dry-run mode)
        override: Deprecated, ignored. Use dry_run for CI.
        region_key: Region key for Supabase case lookup
        gate_key: Gate key for Supabase case lookup

    Returns:
        ReviewDecision with approved/blocked/needs_review flags
    """
    if dry_run:
        return ReviewDecision(
            stage=stage,
            approved=True,
            blocked=False,
            needs_review=False,
            reason='Gate bypassed (dry_run)',
        )

    contract = WORKFLOW_CONTRACT_MAP.get(stage)
    if contract is None:
        return ReviewDecision(
            stage=stage,
            approved=False,
            blocked=True,
            needs_review=False,
            reason=f'Unknown workflow stage: {stage}',
        )

    typed_contract = TYPED_WORKFLOW_CONTRACTS.get(stage)
    if typed_contract is None:
        return ReviewDecision(
            stage=stage,
            approved=False,
            blocked=True,
            needs_review=False,
            reason=f'No typed contract exists for stage {stage}',
        )
    passed, violations = typed_contract.evaluate(packet)
    gate_policy = typed_contract.gate_policy

    if not passed:
        return ReviewDecision(
            stage=stage,
            approved=False,
            blocked=True,
            needs_review=True,
            reason=f'Contract violations require scientist review: {len(violations)} issue(s)',
            contract_violations=violations,
        )

    if gate_policy == 'scientist_review':
        approved_case = _check_scientist_validation_case(region_key, gate_key)
        if approved_case:
            return ReviewDecision(
                stage=stage,
                approved=True,
                blocked=False,
                needs_review=False,
                reason=f'Stage {stage} approved by scientist review case {approved_case}',
                metadata={'case_id': approved_case},
            )
        return ReviewDecision(
            stage=stage,
            approved=False,
            blocked=True,
            needs_review=True,
            reason=f'Stage {stage} requires scientist review — no accepted case found for gate_key={gate_key}',
        )

    return ReviewDecision(
        stage=stage,
        approved=True,
        blocked=False,
        needs_review=False,
        reason=f'Stage {stage} passed {gate_policy} gate with no violations',
    )


def _check_scientist_validation_case(region_key: str, gate_key: str) -> str | None:
    """Check Supabase for a reviewed case with an accepted review.

    The workbench schema represents approval as a reviewed case plus an
    accepted review verdict; ``approved`` is not a valid case status.
    """
    if not region_key and not gate_key:
        return None
    try:
        from backend.common.supabase_io import has_supabase_credentials, rest_get
        if not has_supabase_credentials():
            return None
        params = {
            'status': 'in.(reviewed,accepted_limitation)',
            'order': 'reviewed_at.desc,created_at.desc',
            'limit': '20',
        }
        if region_key:
            params['region_key'] = f'eq.{region_key}'
        if gate_key:
            params['gate_key'] = f'eq.{gate_key}'
        rows = rest_get('scientist_validation_cases', params=params)
        for case in rows if isinstance(rows, list) else []:
            case_id = str(case.get('id') or '')
            if not case_id:
                continue
            review_rows = rest_get(
                'scientist_validation_reviews',
                params={
                    'case_id': f'eq.{case_id}',
                    'verdict': 'in.(accepted,accepted_limitation)',
                    'claim_impact': 'neq.block',
                    'order': 'created_at.desc',
                    'limit': '20',
                },
            )
            accepted_reviews = review_rows if isinstance(review_rows, list) else []
            reviewer_ids = {
                str(review.get('reviewer_id'))
                for review in accepted_reviews
                if review.get('reviewer_id')
            }
            required_reviewers = 2 if case.get('requires_two_reviewers') else 1
            if len(reviewer_ids) >= required_reviewers:
                return case_id
    except Exception:
        pass
    return None
