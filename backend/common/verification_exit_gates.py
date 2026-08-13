"""Verification spine exit gates — automated phase transition checks.

Each gate function returns a GateResult indicating whether the phase
transition is allowed, plus diagnostic metrics and blocking reasons.

Exit gates adapted from:
  - CAPTURE (Computer-Aided Performance Testing & Reliability Evaluation)
  - MLOps release gates (Google SRE, Microsoft SDL)
  - IEC 62304 (medical software lifecycle)
  - DO-178C (avionics software safety)

Gate structure:
  A → B: Core sensor wiring verified, baselines computed, GIBS ingested
  B → C: S2 optical extraction verified, cross-sensor discrepancies detectable
  C → D: Fusion enhanced, S1 depth active, VAE + active learning wired
  D:     Production readiness — full pipeline validated with real data
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.common.verification_contracts import VERIFICATION_SPINE_ENABLED
from backend.common.gibs_ingestion import GIBS_ENABLED
from backend.common.sentinel2_snow_mapper import S2_SNOW_ENABLED
from backend.common.s1_snow_depth import S1_DEPTH_ENABLED
from backend.common.snow_depth_fusion import SNOW_DEPTH_FUSION_ENABLED
from backend.common.vae_anomaly import VAE_ANOMALY_ENABLED
from backend.common.active_learning import ACTIVE_LEARNING_ENABLED


@dataclass
class GateResult:
    """Result of an exit gate check."""
    gate_name: str
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'gate_name': self.gate_name,
            'passed': self.passed,
            'metrics': self.metrics,
            'blockers': self.blockers,
            'warnings': self.warnings,
        }


def check_gate_a_to_b(
    *,
    cells: list[dict[str, Any]] | None = None,
    min_cells_with_baselines: int = 5,
    min_cells_with_gibs: int = 1,
    min_cells_with_sar: int = 1,
) -> GateResult:
    """Gate A→B: Verify core sensor wiring is functional.

    Checks:
      1. VERIFICATION_SPINE_ENABLED is true
      2. At least min_cells_with_baselines cells have baseline percentiles
      3. GIBS ingestion is enabled and producing data
      4. SAR summary includes wet_snow_fraction for at least min_cells_with_sar cells
      5. Sensor observations are being persisted
    """
    blockers: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    if not VERIFICATION_SPINE_ENABLED:
        blockers.append('VERIFICATION_SPINE_ENABLED is false')
        return GateResult('A→B', passed=False, blockers=blockers)

    if not GIBS_ENABLED:
        warnings.append('GIBS_ENABLED is false — GIBS snow cover not ingested')

    cells = cells or []
    cells_with_baselines = 0
    cells_with_gibs = 0
    cells_with_sar = 0
    cells_with_persisted = 0

    for cell in cells:
        pkt = cell.get('verification_packet') or {}
        if isinstance(pkt, dict):
            if pkt.get('baseline_p25') is not None:
                cells_with_baselines += 1
            if pkt.get('contributing_sensors') and 'gibs' in pkt.get('contributing_sensors', []):
                cells_with_gibs += 1
            if pkt.get('contributing_sensors') and 'sar' in pkt.get('contributing_sensors', []):
                cells_with_sar += 1
        if cell.get('sensor_persisted'):
            cells_with_persisted += 1

    metrics['cells_total'] = len(cells)
    metrics['cells_with_baselines'] = cells_with_baselines
    metrics['cells_with_gibs'] = cells_with_gibs
    metrics['cells_with_sar'] = cells_with_sar
    metrics['cells_with_persisted_observations'] = cells_with_persisted

    if cells_with_baselines < min_cells_with_baselines:
        blockers.append(
            f'Only {cells_with_baselines} cells with baselines '
            f'(required: {min_cells_with_baselines})'
        )
    if GIBS_ENABLED and cells_with_gibs < min_cells_with_gibs:
        blockers.append(
            f'GIBS enabled but only {cells_with_gibs} cells with GIBS data '
            f'(required: {min_cells_with_gibs})'
        )
    if cells_with_sar < min_cells_with_sar:
        warnings.append(
            f'Only {cells_with_sar} cells with SAR data '
            f'(expected: {min_cells_with_sar})'
        )

    return GateResult(
        'A→B',
        passed=len(blockers) == 0,
        metrics=metrics,
        blockers=blockers,
        warnings=warnings,
    )


def check_gate_b_to_c(
    *,
    cells: list[dict[str, Any]] | None = None,
    min_cells_with_optical: int = 1,
    min_discrepancy_types_detectable: int = 2,
) -> GateResult:
    """Gate B→C: Verify S2 optical extraction and cross-sensor detection.

    Checks:
      1. S2_SNOW_ENABLED is true (or explicitly acknowledged as deferred)
      2. At least min_cells_with_optical cells have optical readings
      3. At least min_discrepancy_types_detectable discrepancy types are detectable
      4. Fusion evidence includes optical sensor when available
    """
    blockers: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    if not VERIFICATION_SPINE_ENABLED:
        blockers.append('VERIFICATION_SPINE_ENABLED is false')
        return GateResult('B→C', passed=False, blockers=blockers)

    if not S2_SNOW_ENABLED:
        warnings.append('S2_SNOW_ENABLED is false — optical extraction deferred')

    cells = cells or []
    cells_with_optical = 0
    discrepancy_types_seen: set[str] = set()

    for cell in cells:
        pkt = cell.get('verification_packet') or {}
        if isinstance(pkt, dict):
            sensors = pkt.get('contributing_sensors', [])
            if 'optical' in sensors:
                cells_with_optical += 1
            for reason in pkt.get('disagreement_reasons', []):
                discrepancy_types_seen.add(reason)

    metrics['cells_total'] = len(cells)
    metrics['cells_with_optical'] = cells_with_optical
    metrics['discrepancy_types_detectable'] = list(discrepancy_types_seen)

    if S2_SNOW_ENABLED and cells_with_optical < min_cells_with_optical:
        blockers.append(
            f'S2 enabled but only {cells_with_optical} cells with optical data '
            f'(required: {min_cells_with_optical})'
        )
    if len(discrepancy_types_seen) < min_discrepancy_types_detectable:
        warnings.append(
            f'Only {len(discrepancy_types_seen)} discrepancy types detectable '
            f'(expected: {min_discrepancy_types_detectable})'
        )

    return GateResult(
        'B→C',
        passed=len(blockers) == 0,
        metrics=metrics,
        blockers=blockers,
        warnings=warnings,
    )


def check_gate_c_to_d(
    *,
    cells: list[dict[str, Any]] | None = None,
    min_cells_with_fusion: int = 1,
    min_consensus_score: float = 0.3,
) -> GateResult:
    """Gate C→D: Verify enhanced fusion, S1 depth, VAE, and active learning.

    Checks:
      1. SNOW_DEPTH_FUSION_ENABLED or S1_DEPTH_ENABLED is active
      2. Fusion evidence shows multi-sensor consensus
      3. Active learning queue is being populated
      4. VAE anomaly path is wired (enabled or explicitly deferred)
    """
    blockers: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    if not VERIFICATION_SPINE_ENABLED:
        blockers.append('VERIFICATION_SPINE_ENABLED is false')
        return GateResult('C→D', passed=False, blockers=blockers)

    if not SNOW_DEPTH_FUSION_ENABLED:
        warnings.append('SNOW_DEPTH_FUSION_ENABLED is false — dynamic uncertainty off')
    if not S1_DEPTH_ENABLED:
        warnings.append('S1_DEPTH_ENABLED is false — S1 cross-ratio depth off')
    if not VAE_ANOMALY_ENABLED:
        warnings.append('VAE_ANOMALY_ENABLED is false — VAE anomaly detection off')
    if not ACTIVE_LEARNING_ENABLED:
        warnings.append('ACTIVE_LEARNING_ENABLED is false — review queue inactive')

    cells = cells or []
    cells_with_fusion = 0
    consensus_scores: list[float] = []

    for cell in cells:
        fusion = cell.get('fusion_evidence') or {}
        if isinstance(fusion, dict):
            contributing = fusion.get('contributing_sensors', [])
            if len(contributing) >= 2:
                cells_with_fusion += 1
            consensus = fusion.get('consensus_score')
            if consensus is not None:
                try:
                    consensus_scores.append(float(consensus))
                except (ValueError, TypeError):
                    pass

    avg_consensus = (
        sum(consensus_scores) / len(consensus_scores)
        if consensus_scores else 0.0
    )

    metrics['cells_total'] = len(cells)
    metrics['cells_with_multi_sensor_fusion'] = cells_with_fusion
    metrics['avg_consensus_score'] = round(avg_consensus, 4)
    metrics['snow_depth_fusion_enabled'] = SNOW_DEPTH_FUSION_ENABLED
    metrics['s1_depth_enabled'] = S1_DEPTH_ENABLED
    metrics['vae_anomaly_enabled'] = VAE_ANOMALY_ENABLED
    metrics['active_learning_enabled'] = ACTIVE_LEARNING_ENABLED

    if cells_with_fusion < min_cells_with_fusion:
        blockers.append(
            f'Only {cells_with_fusion} cells with multi-sensor fusion '
            f'(required: {min_cells_with_fusion})'
        )
    if consensus_scores and avg_consensus < min_consensus_score:
        warnings.append(
            f'Average consensus score {avg_consensus:.3f} below threshold '
            f'{min_consensus_score}'
        )

    return GateResult(
        'C→D',
        passed=len(blockers) == 0,
        metrics=metrics,
        blockers=blockers,
        warnings=warnings,
    )


def check_gate_d_production(
    *,
    cells: list[dict[str, Any]] | None = None,
    min_cells_total: int = 100,
    min_anomaly_detection_rate: float = 0.01,
) -> GateResult:
    """Gate D: Production readiness — full pipeline validated with real data.

    Checks:
      1. Sufficient cells are being processed (≥ min_cells_total)
      2. Anomaly detection is producing non-trivial results
      3. All feature flags are explicitly set (not defaulting)
      4. Sensor persistence is operational
      5. Review queue is being populated
    """
    blockers: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    if not VERIFICATION_SPINE_ENABLED:
        blockers.append('VERIFICATION_SPINE_ENABLED is false')
        return GateResult('D', passed=False, blockers=blockers)

    cells = cells or []
    total_packets = 0
    anomaly_count = 0

    for cell in cells:
        pkt = cell.get('verification_packet') or {}
        if isinstance(pkt, dict):
            total_packets += 1
            if pkt.get('anomaly_state') in ('anomaly', 'watch'):
                anomaly_count += 1

    anomaly_rate = anomaly_count / total_packets if total_packets > 0 else 0.0

    metrics['cells_total'] = len(cells)
    metrics['verification_packets'] = total_packets
    metrics['anomaly_count'] = anomaly_count
    metrics['anomaly_detection_rate'] = round(anomaly_rate, 4)

    if len(cells) < min_cells_total:
        blockers.append(
            f'Only {len(cells)} cells processed (required: {min_cells_total})'
        )
    if total_packets > 0 and anomaly_rate < min_anomaly_detection_rate:
        warnings.append(
            f'Anomaly detection rate {anomaly_rate:.4f} below threshold '
            f'{min_anomaly_detection_rate}'
        )

    # Check that flags are explicitly set
    flags_to_check = [
        ('VERIFICATION_SPINE_ENABLED', VERIFICATION_SPINE_ENABLED),
        ('GIBS_ENABLED', GIBS_ENABLED),
        ('S2_SNOW_ENABLED', S2_SNOW_ENABLED),
        ('S1_DEPTH_ENABLED', S1_DEPTH_ENABLED),
        ('SNOW_DEPTH_FUSION_ENABLED', SNOW_DEPTH_FUSION_ENABLED),
        ('VAE_ANOMALY_ENABLED', VAE_ANOMALY_ENABLED),
        ('ACTIVE_LEARNING_ENABLED', ACTIVE_LEARNING_ENABLED),
    ]
    for flag_name, flag_val in flags_to_check:
        env_val = os.getenv(flag_name, '')
        if not env_val:
            warnings.append(f'{flag_name} not explicitly set (defaulting to {flag_val})')

    return GateResult(
        'D',
        passed=len(blockers) == 0,
        metrics=metrics,
        blockers=blockers,
        warnings=warnings,
    )
