"""Partner public bulletin candidate inventory module.

P4: PublicBulletinCandidateV1 — separate from PartnerLabelRecordV1.

Every fetched public bulletin is stored as a candidate with:
- Observed PDF hash (SHA-256 of downloaded bytes)
- Source URL
- Parse status (complete, partial, duplicate, failed)
- Raw applicability and revision evidence
- Forced authority_status=unreviewed, rights_status=pending, training_eligible=false

No public candidate can enter preflight as a training label.
No conversion path from candidate to approved label currently exists in the codebase.
This is a known gap that must be addressed before conditional training (P11) can proceed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Parse statuses
PARSE_COMPLETE = 'complete'
PARSE_PARTIAL = 'partial'
PARSE_DUPLICATE = 'duplicate'
PARSE_FAILED = 'failed'

# Authority/rights/training statuses (always forced for public candidates)
AUTHORITY_STATUS_UNREVIEWED = 'unreviewed'
RIGHTS_STATUS_PENDING = 'pending'
TRAINING_ELIGIBLE_FALSE = False


@dataclass(frozen=True)
class PublicBulletinCandidateV1:
    """A public Partner bulletin candidate — NOT a training label.

    P4 contract: source hash, parsed rows, exact validity, provenance locations,
    parsing status, rights/QC/authority status, and mandatory training_eligible=false.

    This is separate from PartnerLabelRecordV1. No public candidate can enter
    preflight as a training label. No conversion path from candidate to
    approved label currently exists in the codebase — this is a known gap
    that must be addressed before conditional training can proceed.

    INVARIANTS (enforced via __post_init__):
    - training_eligible must always be False
    - authority_status must always be 'unreviewed'
    - rights_status must always be 'pending'
    - observed_sha256 must be a valid 64-character hex string
    These CANNOT be overridden — __post_init__ raises ValueError if violated.
    """

    bulletin_id: str
    source_url: str
    observed_sha256: str  # SHA-256 of downloaded PDF bytes
    parse_status: str  # complete, partial, duplicate, failed
    issue_date: str | None  # ISO date string or None
    valid_from: str | None  # ISO date string or None
    valid_until: str | None  # ISO date string or None
    bulletin_number: str | None  # e.g., "2025-26 181"
    row_count: int  # Number of parsed district rows
    rows: list[dict[str, Any]] = field(default_factory=list)  # Serialized row data
    # Forced statuses — always these values for public candidates
    authority_status: str = AUTHORITY_STATUS_UNREVIEWED
    rights_status: str = RIGHTS_STATUS_PENDING
    training_eligible: bool = TRAINING_ELIGIBLE_FALSE
    # Metadata
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parse_error: str | None = None
    file_size_bytes: int | None = None
    provenance_locations: list[str] = field(default_factory=list)  # Where the hash was recorded
    notes: str | None = None

    def __post_init__(self) -> None:
        """Enforce the candidate schema and its fail-closed invariants."""
        if not isinstance(self.bulletin_id, str) or not self.bulletin_id.strip():
            raise ValueError('bulletin_id must be a non-empty string')
        if not isinstance(self.source_url, str) or not self.source_url.strip():
            raise ValueError('source_url must be a non-empty string')
        if self.parse_status not in {
            PARSE_COMPLETE, PARSE_PARTIAL, PARSE_DUPLICATE, PARSE_FAILED,
        }:
            raise ValueError(f'unsupported parse_status: {self.parse_status!r}')
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 0:
            raise ValueError('row_count must be a non-negative integer')
        if not isinstance(self.rows, list):
            raise ValueError('rows must be a list of objects')
        if self.row_count != len(self.rows):
            raise ValueError(
                f'row_count ({self.row_count}) must equal serialized rows length ({len(self.rows)})'
            )

        def _validate_date(value: str | None, field_name: str) -> date | None:
            if value is None:
                return None
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{field_name} must be an ISO date string or null')
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f'{field_name} must be a valid ISO date: {value!r}') from exc

        issue = _validate_date(self.issue_date, 'issue_date')
        valid_from = _validate_date(self.valid_from, 'valid_from')
        valid_until = _validate_date(self.valid_until, 'valid_until')
        if valid_from and valid_until and valid_from > valid_until:
            raise ValueError('valid_from must not be after valid_until')
        if self.file_size_bytes is not None and (
            isinstance(self.file_size_bytes, bool)
            or not isinstance(self.file_size_bytes, int)
            or self.file_size_bytes < 0
        ):
            raise ValueError('file_size_bytes must be a non-negative integer or null')
        if not isinstance(self.provenance_locations, list) or not all(
            isinstance(item, str) and item.strip() for item in self.provenance_locations
        ):
            raise ValueError('provenance_locations must be a list of non-empty strings')
        if not isinstance(self.discovered_at, str) or not self.discovered_at.strip():
            raise ValueError('discovered_at must be a non-empty ISO datetime string')
        try:
            datetime.fromisoformat(self.discovered_at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError(f'discovered_at must be a valid ISO datetime: {self.discovered_at!r}') from exc

        # G4: training_eligible must always be False
        if self.training_eligible is not False:
            raise ValueError(
                f'PublicBulletinCandidateV1 invariant violated: training_eligible must be False, '
                f'got {self.training_eligible!r}. Public candidates can NEVER be training eligible.'
            )
        # G4: authority_status must always be 'unreviewed'
        if self.authority_status != AUTHORITY_STATUS_UNREVIEWED:
            raise ValueError(
                f'PublicBulletinCandidateV1 invariant violated: authority_status must be '
                f'{AUTHORITY_STATUS_UNREVIEWED!r}, got {self.authority_status!r}. '
                f'Public candidates are always unreviewed.'
            )
        # G4: rights_status must always be 'pending'
        if self.rights_status != RIGHTS_STATUS_PENDING:
            raise ValueError(
                f'PublicBulletinCandidateV1 invariant violated: rights_status must be '
                f'{RIGHTS_STATUS_PENDING!r}, got {self.rights_status!r}. '
                f'Public candidates always have pending rights.'
            )
        # G4: observed_sha256 must be a valid 64-character hex string
        if not isinstance(self.observed_sha256, str) or len(self.observed_sha256) != 64:
            raise ValueError(
                f'PublicBulletinCandidateV1 invariant violated: observed_sha256 must be a '
                f'64-character hex string, got {self.observed_sha256!r} '
                f'(length={len(self.observed_sha256) if isinstance(self.observed_sha256, str) else "not a string"})'
            )
        try:
            int(self.observed_sha256, 16)  # Validate hex
        except ValueError:
            raise ValueError(
                f'PublicBulletinCandidateV1 invariant violated: observed_sha256 must be '
                f'valid hexadecimal, got {self.observed_sha256!r}'
            )
        # N10: Validate that all rows are dicts
        for i, row in enumerate(self.rows):
            if not isinstance(row, dict):
                raise ValueError(
                    f'PublicBulletinCandidateV1 invariant violated: rows[{i}] must be a '
                    f'dict, got {type(row).__name__}'
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublicBulletinCandidateV1:
        """Strictly deserialize an untrusted candidate payload.

        A payload that attempts to change the forced authority, rights, or
        eligibility fields is rejected. Silently normalizing those fields
        would hide a privilege-escalation attempt and make provenance
        auditing ambiguous.
        """
        if not isinstance(data, dict):
            raise ValueError('candidate payload must be a JSON object')
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f'unknown candidate fields: {unknown}')
        expected_invariants = {
            'authority_status': AUTHORITY_STATUS_UNREVIEWED,
            'rights_status': RIGHTS_STATUS_PENDING,
            'training_eligible': TRAINING_ELIGIBLE_FALSE,
        }
        for field_name, expected in expected_invariants.items():
            if field_name in data and data[field_name] != expected:
                raise ValueError(
                    f'{field_name} is immutable for public candidates; expected {expected!r}'
                )
        try:
            return cls(**dict(data))
        except TypeError as exc:
            raise ValueError(f'invalid candidate payload shape: {exc}') from exc

    @property
    def is_complete(self) -> bool:
        return self.parse_status == PARSE_COMPLETE

    @property
    def is_parseable(self) -> bool:
        return self.parse_status in (PARSE_COMPLETE, PARSE_PARTIAL)

    @property
    def can_enter_training(self) -> bool:
        """Always False for public candidates — P4 exit gate."""
        return False


def build_candidate_from_parse_result(
    bulletin_id: str,
    source_url: str,
    pdf_bytes: bytes,
    parse_status: str,
    issue_date: date | None = None,
    valid_from: date | None = None,
    valid_until: date | None = None,
    bulletin_number: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    parse_error: str | None = None,
    provenance_locations: list[str] | None = None,
    notes: str | None = None,
) -> PublicBulletinCandidateV1:
    """Build a PublicBulletinCandidateV1 from parsed bulletin data.

    Forces authority_status=unreviewed, rights_status=pending, training_eligible=false.
    These CANNOT be overridden — they are hardcoded in the dataclass defaults.
    """
    observed_hash = hashlib.sha256(pdf_bytes).hexdigest()
    return PublicBulletinCandidateV1(
        bulletin_id=bulletin_id,
        source_url=source_url,
        observed_sha256=observed_hash,
        parse_status=parse_status,
        issue_date=issue_date.isoformat() if issue_date else None,
        valid_from=valid_from.isoformat() if valid_from else None,
        valid_until=valid_until.isoformat() if valid_until else None,
        bulletin_number=bulletin_number,
        row_count=len(rows) if rows else 0,
        rows=rows or [],
        parse_error=parse_error,
        file_size_bytes=len(pdf_bytes),
        provenance_locations=provenance_locations or [],
        notes=notes,
    )


def detect_duplicate(
    candidate: PublicBulletinCandidateV1,
    existing_candidates: list[PublicBulletinCandidateV1],
) -> PublicBulletinCandidateV1 | None:
    """Check if a candidate is a duplicate of an existing one by hash.

    Returns the matching existing candidate if found, else None.
    """
    for existing in existing_candidates:
        if existing.observed_sha256 == candidate.observed_sha256:
            return existing
    return None


def verify_candidate_content(
    candidate: PublicBulletinCandidateV1,
    pdf_bytes: bytes,
) -> bool:
    """Verify candidate provenance against the exact downloaded bytes."""
    if not isinstance(pdf_bytes, bytes):
        raise ValueError('pdf_bytes must be bytes')
    return hashlib.sha256(pdf_bytes).hexdigest() == candidate.observed_sha256


def build_candidate_manifest(
    candidates: list[PublicBulletinCandidateV1],
) -> dict[str, Any]:
    """Build a summary manifest from collected public candidates.

    P4 exit gate: Every fetched candidate is complete, partial, duplicate, or failed;
    no public candidate can enter preflight as a training label.
    """
    complete = [c for c in candidates if c.parse_status == PARSE_COMPLETE]
    partial = [c for c in candidates if c.parse_status == PARSE_PARTIAL]
    duplicates = [c for c in candidates if c.parse_status == PARSE_DUPLICATE]
    failed = [c for c in candidates if c.parse_status == PARSE_FAILED]

    # Verify all candidates have training_eligible=False
    all_ineligible = all(not c.training_eligible for c in candidates)

    # Unique bulletins by hash
    seen_hashes: set[str] = set()
    unique_count = 0
    for c in candidates:
        if c.observed_sha256 not in seen_hashes:
            seen_hashes.add(c.observed_sha256)
            unique_count += 1

    return {
        'schema_version': 'Partner_public_candidate_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_candidates': len(candidates),
        'complete': len(complete),
        'partial': len(partial),
        'duplicates': len(duplicates),
        'failed': len(failed),
        'unique_by_hash': unique_count,
        'all_training_ineligible': all_ineligible,
        'authority_status_all_unreviewed': all(
            c.authority_status == AUTHORITY_STATUS_UNREVIEWED for c in candidates
        ),
        'rights_status_all_pending': all(
            c.rights_status == RIGHTS_STATUS_PENDING for c in candidates
        ),
        'candidates': [c.to_dict() for c in candidates],
    }


def save_candidate_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Save candidate manifest to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def load_candidate_manifest(path: Path) -> dict[str, Any] | None:
    """Load a previously saved candidate manifest fail-closed."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'candidate manifest load failed: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('candidate manifest must be a JSON object')
    return payload
