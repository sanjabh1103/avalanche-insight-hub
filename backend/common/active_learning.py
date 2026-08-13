"""Active learning queue — ranks cells by uncertainty × anomaly × sparsity.

Ranks cells for observation requests using:
- Prediction uncertainty (from conformal/confidence intervals)
- Anomaly severity (from verification spine anomaly_score)
- Data sparsity (SAR coverage state, sensor count, freshness)

Queue rows carry SAM pre-annotation refs via existing sam_lora_adapter.py
and VAE reconstruction-error scores when VAE_ANOMALY_ENABLED.

Env flags:
  ACTIVE_LEARNING_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

ACTIVE_LEARNING_ENABLED = os.getenv(
    'ACTIVE_LEARNING_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}

ACTIVE_LEARNING_MAX_QUEUE = int(os.getenv('ACTIVE_LEARNING_MAX_QUEUE', '50'))
ACTIVE_LEARNING_UNCERTAINTY_WEIGHT = float(os.getenv('ACTIVE_LEARNING_UNCERTAINTY_WEIGHT', '0.4'))
ACTIVE_LEARNING_ANOMALY_WEIGHT = float(os.getenv('ACTIVE_LEARNING_ANOMALY_WEIGHT', '0.4'))
ACTIVE_LEARNING_SPARSITY_WEIGHT = float(os.getenv('ACTIVE_LEARNING_SPARSITY_WEIGHT', '0.2'))


@dataclass
class ActiveLearningQueueRow:
    """A single cell in the active learning observation-request queue."""

    region_key: str
    cell_id: str
    lat: float
    lng: float
    priority_score: float
    uncertainty_score: float
    anomaly_score: float
    sparsity_score: float
    review_state: str = 'pending'  # pending | assigned | completed | skipped
    verification_basis: str | None = None
    sam_preannotation_ref: str | None = None
    vae_reconstruction_error: float | None = None
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'region_key': self.region_key,
            'cell_id': self.cell_id,
            'lat': self.lat,
            'lng': self.lng,
            # ``priority`` is the legacy queue column; keep it aligned with
            # the explicit score while the additive migration rolls out.
            'priority': self.priority_score,
            'priority_score': self.priority_score,
            'uncertainty_score': self.uncertainty_score,
            'anomaly_score': self.anomaly_score,
            'sparsity_score': self.sparsity_score,
            'review_state': self.review_state,
            'verification_basis': self.verification_basis,
            'sam_preannotation_ref': self.sam_preannotation_ref,
            'vae_reconstruction_error': self.vae_reconstruction_error,
            'sources': self.sources,
            'metadata': self.metadata,
        }


def compute_uncertainty_score(cell: dict[str, Any]) -> float:
    """Compute uncertainty score from cell prediction data.

    Uses conformal interval span or uncertainty class.
    Returns 0.0–1.0.
    """
    conformal_lower = cell.get('conformalLower')
    conformal_upper = cell.get('conformalUpper')
    if conformal_lower is not None and conformal_upper is not None:
        span = abs(conformal_upper - conformal_lower)
        return min(span, 1.0)

    uncertainty_span = cell.get('uncertaintySpan')
    if uncertainty_span is not None:
        return min(float(uncertainty_span), 1.0)

    uncertainty_class = cell.get('uncertaintyClass', 'unknown')
    if uncertainty_class == 'high':
        return 0.8
    elif uncertainty_class == 'medium':
        return 0.5
    elif uncertainty_class == 'low':
        return 0.2

    return 0.0


def compute_anomaly_score(cell: dict[str, Any]) -> float:
    """Compute anomaly score from verification packet data.

    Uses anomaly_score from verification spine, or 0.0 if absent.
    Returns 0.0–1.0 (clamped).
    """
    score = cell.get('anomaly_score')
    if score is not None:
        return min(abs(float(score)), 1.0)

    discrepancy_reasons = cell.get('discrepancy_reasons', [])
    if discrepancy_reasons:
        return min(len(discrepancy_reasons) * 0.2, 1.0)

    return 0.0


def compute_sparsity_score(cell: dict[str, Any]) -> float:
    """Compute data sparsity score.

    Higher = more data-sparse (more observation needed).
    Uses SAR coverage state, sensor count, and freshness.
    Returns 0.0–1.0.
    """
    score = 0.0

    coverage_flags = cell.get('coverageFlags', {})
    sar_state = coverage_flags.get('sar_coverage_state', 'not_applicable')
    if sar_state in ('low_coverage', 'no_coverage', 'not_applicable'):
        score += 0.4
    elif sar_state == 'audit_only':
        score += 0.3

    data_gaps = coverage_flags.get('data_gaps', [])
    score += min(len(data_gaps) * 0.1, 0.3)

    # Check for verification packet contributing sensors
    verification_packet = cell.get('verification_packet', {})
    contributing = verification_packet.get('contributing_sensors', [])
    if contributing:
        score += max(0.0, 0.3 - len(contributing) * 0.1)

    return min(score, 1.0)


def _get_sam_preannotation_ref(cell: dict[str, Any]) -> str | None:
    """Get SAM pre-annotation reference for the cell.

    Uses existing sam_lora_adapter.py if available.
    Returns a reference string or None.
    """
    try:
        from backend.common.sam_lora_adapter import sam_lora_available
        if not sam_lora_available():
            return None
        lat = cell.get('lat', 0.0)
        lng = cell.get('lng', 0.0)
        return f'sam_preannotation:cell_{lat:.4f}_{lng:.4f}'
    except Exception:
        return None


def _get_vae_reconstruction_error(cell: dict[str, Any]) -> float | None:
    """Get VAE reconstruction error score if available.

    Checks for VAE anomaly result in cell data.
    Returns error value or None.
    """
    vae_result = cell.get('vae_anomaly_result')
    if vae_result is not None and isinstance(vae_result, dict):
        return vae_result.get('reconstruction_error')
    return None


def rank_cells_for_observation(
    cells: list[dict[str, Any]],
    *,
    region_key: str,
    max_queue: int = ACTIVE_LEARNING_MAX_QUEUE,
) -> list[ActiveLearningQueueRow]:
    """Rank cells by uncertainty × anomaly severity × data sparsity.

    Args:
        cells: List of cell dicts with prediction and verification data.
        region_key: Region key for all cells.
        max_queue: Maximum queue rows to return.

    Returns:
        Sorted list of ActiveLearningQueueRow (highest priority first).
    """
    if not ACTIVE_LEARNING_ENABLED:
        return []

    rows: list[ActiveLearningQueueRow] = []

    for idx, cell in enumerate(cells):
        lat = float(cell.get('lat', 0.0))
        lng = float(cell.get('lng', 0.0))
        cell_id = cell.get('cell_id', f'cell_{idx}')

        uncertainty = compute_uncertainty_score(cell)
        anomaly = compute_anomaly_score(cell)
        sparsity = compute_sparsity_score(cell)

        priority = (
            ACTIVE_LEARNING_UNCERTAINTY_WEIGHT * uncertainty
            + ACTIVE_LEARNING_ANOMALY_WEIGHT * anomaly
            + ACTIVE_LEARNING_SPARSITY_WEIGHT * sparsity
        )

        sam_ref = _get_sam_preannotation_ref(cell)
        vae_error = _get_vae_reconstruction_error(cell)

        verification_packet = cell.get('verification_packet', {})
        if not isinstance(verification_packet, dict):
            verification_packet = {}
        sources = verification_packet.get('contributing_sensors', [])
        verification_basis = 'verification_packet' if verification_packet else 'forecast_only'

        row = ActiveLearningQueueRow(
            region_key=region_key,
            cell_id=cell_id,
            lat=lat,
            lng=lng,
            priority_score=round(priority, 4),
            uncertainty_score=round(uncertainty, 4),
            anomaly_score=round(anomaly, 4),
            sparsity_score=round(sparsity, 4),
            verification_basis=verification_basis,
            sam_preannotation_ref=sam_ref,
            vae_reconstruction_error=vae_error,
            sources=list(sources) if sources else [],
            metadata={
                'risk_score': cell.get('riskScore'),
                'problem_type': cell.get('problemType'),
                'evidence_refs': verification_packet.get('evidence_refs', []),
                'baseline_ids': verification_packet.get('baseline_ids', []),
                'packet_version': verification_packet.get('packet_version'),
            },
        )
        rows.append(row)

    rows.sort(key=lambda r: r.priority_score, reverse=True)
    return rows[:max_queue]


def emit_review_queue_rows(
    ranked_rows: list[ActiveLearningQueueRow],
) -> list[dict[str, Any]]:
    """Convert ranked rows into review queue table insert dicts.

    Returns list of dicts suitable for Supabase insert into
    verification_review_queue table.
    """
    if not ACTIVE_LEARNING_ENABLED:
        return []

    queue_rows: list[dict[str, Any]] = []
    for row in ranked_rows:
        queue_rows.append({
            'region_key': row.region_key,
            'cell_id': row.cell_id,
            'lat': row.lat,
            'lng': row.lng,
            'priority': row.priority_score,
            'priority_score': row.priority_score,
            'uncertainty_score': row.uncertainty_score,
            'anomaly_score': row.anomaly_score,
            'sparsity_score': row.sparsity_score,
            'review_state': row.review_state,
            'verification_basis': row.verification_basis,
            'sam_preannotation_ref': row.sam_preannotation_ref,
            'vae_reconstruction_error': row.vae_reconstruction_error,
            'sources': row.sources,
            'metadata': row.metadata,
        })
    return queue_rows
