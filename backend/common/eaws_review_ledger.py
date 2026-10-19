"""EAWS review ledger for validation spine.

Stores per-cell EAWS factor review records as JSONL.
Path via env EAWS_REVIEW_LEDGER_PATH, default artifact-dir relative.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

VALID_STABILITY_CLASSES = {'very_poor', 'poor', 'fair', 'good'}
VALID_SIZE_CLASSES = {1, 2, 3, 4, 5}
VALID_FREQUENCY_CLASSES = {'frequent', 'occasional', 'rare', 'none'}


def _default_ledger_path() -> str:
    return os.getenv('EAWS_REVIEW_LEDGER_PATH', 'artifacts-review/eaws_review_ledger.jsonl')


@dataclass(frozen=True)
class EAWSReviewRecord:
    """A single EAWS factor review record for a forecast cell.

    Attributes:
        record_id: Unique record identifier.
        forecast_run_id: Associated forecast run ID.
        cell_id: Cell identifier within the forecast grid.
        stability_class: EAWS stability class (very_poor, poor, fair, good).
        frequency_class: EAWS frequency class (frequent, occasional, rare, none).
        expected_size_class: Expected avalanche size class (1-5).
        evidence_source: Source of evidence for the review.
        reviewer: Reviewer identifier.
        confidence: Reviewer confidence (0.0-1.0).
        reviewed_at: ISO 8601 timestamp of review.
        notes: Free-text review notes.
    """
    record_id: str
    forecast_run_id: str
    cell_id: str
    stability_class: str
    frequency_class: str
    expected_size_class: int
    evidence_source: str
    reviewer: str
    confidence: float
    reviewed_at: str
    notes: str = ''

    def validate(self) -> list[str]:
        """Return list of validation errors (empty if valid)."""
        errors: list[str] = []
        if self.stability_class not in VALID_STABILITY_CLASSES:
            errors.append(f'Invalid stability_class: {self.stability_class}')
        if self.expected_size_class not in VALID_SIZE_CLASSES:
            errors.append(f'Invalid expected_size_class: {self.expected_size_class}')
        if self.frequency_class not in VALID_FREQUENCY_CLASSES:
            errors.append(f'Invalid frequency_class: {self.frequency_class}')
        if not 0.0 <= self.confidence <= 1.0:
            errors.append(f'confidence must be 0.0-1.0, got {self.confidence}')
        return errors


def append_review_record(
    path: str | None = None,
    record: EAWSReviewRecord | None = None,
) -> str:
    """Append a review record to the JSONL ledger.

    Returns the record_id. Raises ValueError if record is invalid.
    """
    if record is None:
        raise ValueError('record is required')

    errors = record.validate()
    if errors:
        raise ValueError('; '.join(errors))

    ledger_path = Path(path or _default_ledger_path())
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    with ledger_path.open('a') as f:
        f.write(json.dumps(asdict(record)) + '\n')

    return record.record_id


def load_review_ledger(path: str | None = None) -> list[EAWSReviewRecord]:
    """Load all review records from the JSONL ledger."""
    ledger_path = Path(path or _default_ledger_path())
    if not ledger_path.exists():
        return []

    records: list[EAWSReviewRecord] = []
    for line in ledger_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        records.append(EAWSReviewRecord(**data))
    return records


def make_record(
    forecast_run_id: str,
    cell_id: str,
    stability_class: str,
    frequency_class: str,
    expected_size_class: int,
    evidence_source: str,
    reviewer: str,
    confidence: float,
    notes: str = '',
) -> EAWSReviewRecord:
    """Create a new EAWSReviewRecord with auto-generated ID and timestamp."""
    return EAWSReviewRecord(
        record_id=str(uuid.uuid4()),
        forecast_run_id=forecast_run_id,
        cell_id=cell_id,
        stability_class=stability_class,
        frequency_class=frequency_class,
        expected_size_class=expected_size_class,
        evidence_source=evidence_source,
        reviewer=reviewer,
        confidence=confidence,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )
