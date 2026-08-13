"""Active-learning feedback loop — scientist decisions become versioned labels, drift signals, and retraining candidates.

Records scientist validation feedback as versioned, append-only entries.
Computes drift signals by comparing recent feedback decisions vs model predictions.
Generates retraining candidates for cells with high drift.

Env flags:
  ACTIVE_LEARNING_FEEDBACK_ENABLED — enable feedback loop (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

ACTIVE_LEARNING_FEEDBACK_ENABLED = os.getenv('ACTIVE_LEARNING_FEEDBACK_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)

VALID_DECISIONS = {'confirmed', 'anomaly', 'false_positive', 'needs_observation'}


@dataclass(frozen=True)
class ScientistFeedback:
    """A single scientist validation feedback entry."""
    queue_row_id: str = ''
    cell_id: str = ''
    region_key: str = ''
    scientist_id: str = ''
    decision: str = 'confirmed'
    label_value: float | None = None
    notes: str = ''
    version: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'queue_row_id': self.queue_row_id,
            'cell_id': self.cell_id,
            'region_key': self.region_key,
            'scientist_id': self.scientist_id,
            'decision': self.decision,
            'label_value': self.label_value,
            'notes': self.notes,
            'version': self.version,
            'created_at': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass(frozen=True)
class DriftSignal:
    """Drift signal for a cell — discrepancy between model and scientist decisions."""
    cell_id: str
    region_key: str
    drift_score: float
    scientist_decisions: list[str] = field(default_factory=list)
    model_predictions: list[float] = field(default_factory=list)
    disagreement_count: int = 0
    total_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'region_key': self.region_key,
            'drift_score': self.drift_score,
            'scientist_decisions': self.scientist_decisions,
            'model_predictions': self.model_predictions,
            'disagreement_count': self.disagreement_count,
            'total_count': self.total_count,
        }


@dataclass(frozen=True)
class RetrainingCandidate:
    """A cell identified as a retraining candidate due to high drift."""
    cell_id: str
    region_key: str
    drift_score: float
    reason: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'region_key': self.region_key,
            'drift_score': self.drift_score,
            'reason': self.reason,
        }


def record_feedback(feedback: ScientistFeedback) -> dict[str, Any]:
    """Record scientist feedback as a versioned entry.

    In production, this inserts into the active_learning_feedback table.
    Returns the feedback dict with version assigned.

    Args:
        feedback: ScientistFeedback to record.

    Returns:
        Dict representation of the recorded feedback.
    """
    if feedback.decision not in VALID_DECISIONS:
        raise ValueError(f'Invalid decision: {feedback.decision}. Must be one of {VALID_DECISIONS}')

    return feedback.to_dict()


def compute_drift_signals(
    region_key: str,
    feedback_entries: list[dict[str, Any]],
    model_predictions: dict[str, list[float]],
) -> list[DriftSignal]:
    """Compute drift signals for cells in a region.

    Compares scientist decisions against model predictions to identify
    cells where the model consistently disagrees with scientist assessment.

    Args:
        region_key: Region identifier.
        feedback_entries: List of feedback dicts (from DB or fixtures).
        model_predictions: Dict mapping cell_id to list of model prediction probabilities.

    Returns:
        List of DriftSignal per cell with feedback.
    """
    cell_feedback: dict[str, list[dict[str, Any]]] = {}
    for entry in feedback_entries:
        if entry.get('region_key') != region_key:
            continue
        cell_id = entry.get('cell_id', '')
        if cell_id:
            cell_feedback.setdefault(cell_id, []).append(entry)

    signals: list[DriftSignal] = []
    for cell_id, entries in cell_feedback.items():
        decisions = [e.get('decision', 'confirmed') for e in entries]
        preds = model_predictions.get(cell_id, [])

        disagreement_count = 0
        total = len(entries)

        for i, entry in enumerate(entries):
            decision = entry.get('decision', 'confirmed')
            pred = preds[i] if i < len(preds) else None

            if pred is not None:
                pred_binary = 1 if pred >= 0.5 else 0
                decision_binary = 0 if decision in ('confirmed', 'false_positive') else 1
                if pred_binary != decision_binary:
                    disagreement_count += 1
            elif decision in ('anomaly', 'false_positive'):
                disagreement_count += 1

        drift_score = disagreement_count / total if total > 0 else 0.0

        signals.append(DriftSignal(
            cell_id=cell_id,
            region_key=region_key,
            drift_score=round(drift_score, 4),
            scientist_decisions=decisions,
            model_predictions=preds,
            disagreement_count=disagreement_count,
            total_count=total,
        ))

    return signals


def generate_retraining_candidates(
    region_key: str,
    drift_signals: list[DriftSignal],
    drift_threshold: float = 0.3,
) -> list[RetrainingCandidate]:
    """Generate retraining candidates from drift signals.

    Args:
        region_key: Region identifier.
        drift_signals: List of drift signals from compute_drift_signals.
        drift_threshold: Minimum drift score to qualify as retraining candidate.

    Returns:
        List of RetrainingCandidate for cells exceeding the threshold.
    """
    candidates: list[RetrainingCandidate] = []
    for signal in drift_signals:
        if signal.drift_score >= drift_threshold:
            candidates.append(RetrainingCandidate(
                cell_id=signal.cell_id,
                region_key=region_key,
                drift_score=signal.drift_score,
                reason=f'Drift score {signal.drift_score:.2f} exceeds threshold {drift_threshold} '
                       f'({signal.disagreement_count}/{signal.total_count} disagreements)',
            ))

    candidates.sort(key=lambda c: c.drift_score, reverse=True)
    return candidates
