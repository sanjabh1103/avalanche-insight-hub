"""Verification contracts for the Pachama-equivalent continuous verification spine.

Defines dataclasses for per-cell verification packets, evidence entries,
fused snow state, and discrepancy attribution. These contracts are the
interchange format between the verification spine modules (snow_baselines,
anomaly_detector, fusion_engine) and the inference pipeline.

Env flags:
  VERIFICATION_SPINE_ENABLED — master switch (default: false)

Safety: every payload carries SAFETY_DISCLAIMER. Unverified or synthetic
evidence may raise review priority but NEVER independently raises public risk.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

VERIFICATION_SPINE_ENABLED = os.getenv('VERIFICATION_SPINE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)

PACKET_VERSION = 'v1'

# Discrepancy attribution buckets
ATTRIBUTION_FORCING_ERROR = 'forcing_error'
ATTRIBUTION_SENSING_GAP = 'sensing_gap'
ATTRIBUTION_PHYSICS_MODEL_BIAS = 'physics_model_bias'
ATTRIBUTION_TERRAIN_TRANSFER_ERROR = 'terrain_transfer_error'
ATTRIBUTION_THRESHOLD_MISCALIBRATION = 'threshold_miscalibration'
ATTRIBUTION_UNATTRIBUTED = 'unattributed'

VALID_ATTRIBUTION_BUCKETS = frozenset({
    ATTRIBUTION_FORCING_ERROR,
    ATTRIBUTION_SENSING_GAP,
    ATTRIBUTION_PHYSICS_MODEL_BIAS,
    ATTRIBUTION_TERRAIN_TRANSFER_ERROR,
    ATTRIBUTION_THRESHOLD_MISCALIBRATION,
    ATTRIBUTION_UNATTRIBUTED,
})

# Anomaly states
ANOMALY_NORMAL = 'normal'
ANOMALY_WATCH = 'watch'
ANOMALY_ANOMALY = 'anomaly'
ANOMALY_UNVERIFIED = 'unverified'

VALID_ANOMALY_STATES = frozenset({
    ANOMALY_NORMAL,
    ANOMALY_WATCH,
    ANOMALY_ANOMALY,
    ANOMALY_UNVERIFIED,
})

# Evidence types
EVIDENCE_WEATHER = 'weather'
EVIDENCE_DEM = 'dem'
EVIDENCE_SAR = 'sar'
EVIDENCE_OPTICAL = 'optical'
EVIDENCE_PHYSICS = 'physics'
EVIDENCE_STATION = 'station'
EVIDENCE_FIELD = 'field'
EVIDENCE_SEISMIC = 'seismic'

VALID_EVIDENCE_TYPES = frozenset({
    EVIDENCE_WEATHER,
    EVIDENCE_DEM,
    EVIDENCE_SAR,
    EVIDENCE_OPTICAL,
    EVIDENCE_PHYSICS,
    EVIDENCE_STATION,
    EVIDENCE_FIELD,
    EVIDENCE_SEISMIC,
})


@dataclass
class EvidenceEntry:
    """A single typed evidence entry for a cell."""

    source: str
    evidence_type: str
    value: float | None = None
    uncertainty: float | None = None
    freshness_hours: float | None = None
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'source': self.source,
            'evidence_type': self.evidence_type,
            'value': self.value,
            'uncertainty': self.uncertainty,
            'freshness_hours': self.freshness_hours,
            'verified': self.verified,
            'metadata': self.metadata,
        }


@dataclass
class EvidencePacket:
    """Collection of evidence entries for a single cell."""

    cell_id: str
    entries: list[EvidenceEntry] = field(default_factory=list)
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def add(self, entry: EvidenceEntry) -> None:
        self.entries.append(entry)

    @property
    def verified_entries(self) -> list[EvidenceEntry]:
        return [e for e in self.entries if e.verified]

    @property
    def has_synthetic(self) -> bool:
        return any(
            e.metadata.get('synthetic', False) or e.metadata.get('method', '').startswith('synthetic')
            for e in self.entries
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'entries': [e.to_dict() for e in self.entries],
            'has_synthetic': self.has_synthetic,
            'disclaimer': self.disclaimer,
        }


@dataclass
class VerificationPacket:
    """Per-cell verification result from the continuous verification spine."""

    cell_id: str
    region_key: str
    baseline_p25: float | None = None
    baseline_p50: float | None = None
    baseline_p75: float | None = None
    observed: float | None = None
    residual_zscore: float | None = None
    anomaly_state: str = ANOMALY_UNVERIFIED
    source_freshness_hours: dict[str, float] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    contributing_sensors: list[str] = field(default_factory=list)
    baseline_ids: list[str] = field(default_factory=list)
    lineage: dict[str, Any] = field(default_factory=dict)
    disagreement_reasons: list[str] = field(default_factory=list)
    attribution_bucket: str = ATTRIBUTION_UNATTRIBUTED
    attribution: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    has_synthetic_evidence: bool = False
    data_quality: dict[str, Any] = field(default_factory=dict)
    packet_version: str = PACKET_VERSION
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def __post_init__(self) -> None:
        if self.anomaly_state not in VALID_ANOMALY_STATES:
            raise ValueError(f'Invalid anomaly_state: {self.anomaly_state}')
        if self.attribution_bucket not in VALID_ATTRIBUTION_BUCKETS:
            raise ValueError(f'Invalid attribution_bucket: {self.attribution_bucket}')
        if not math.isfinite(float(self.confidence)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError('confidence must be between 0 and 1')
        for source, freshness in self.source_freshness_hours.items():
            if freshness is None:
                continue
            if not math.isfinite(float(freshness)) or float(freshness) < 0:
                raise ValueError(f'Invalid freshness for source {source}')

    def to_dict(self) -> dict[str, Any]:
        return {
            'cell_id': self.cell_id,
            'region_key': self.region_key,
            'baseline_p25': self.baseline_p25,
            'baseline_p50': self.baseline_p50,
            'baseline_p75': self.baseline_p75,
            'observed': self.observed,
            'residual_zscore': self.residual_zscore,
            'anomaly_state': self.anomaly_state,
            'source_freshness_hours': self.source_freshness_hours,
            'evidence_refs': self.evidence_refs,
            'contributing_sensors': self.contributing_sensors,
            'baseline_ids': self.baseline_ids,
            'lineage': self.lineage,
            'disagreement_reasons': self.disagreement_reasons,
            'attribution_bucket': self.attribution_bucket,
            'attribution': self.attribution,
            'confidence': self.confidence,
            'has_synthetic_evidence': self.has_synthetic_evidence,
            'data_quality': self.data_quality,
            'packet_version': self.packet_version,
            'disclaimer': self.disclaimer,
        }


@dataclass
class FusedSnowState:
    """Fused multi-sensor snow state for a cell."""

    snow_depth_m: float | None = None
    snow_cover_fraction: float | None = None
    wet_snow_fraction: float | None = None
    loading_rate_24h: float | None = None
    uncertainty: float | None = None
    consensus_score: float = 0.0
    contributing_sensors: list[str] = field(default_factory=list)
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def to_dict(self) -> dict[str, Any]:
        return {
            'snow_depth_m': self.snow_depth_m,
            'snow_cover_fraction': self.snow_cover_fraction,
            'wet_snow_fraction': self.wet_snow_fraction,
            'loading_rate_24h': self.loading_rate_24h,
            'uncertainty': self.uncertainty,
            'consensus_score': self.consensus_score,
            'contributing_sensors': self.contributing_sensors,
            'disclaimer': self.disclaimer,
        }


@dataclass
class DiscrepancyAttribution:
    """Attribution of a discrepancy to a specific error source."""

    bucket: str
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    recommended_action: str = ''

    def __post_init__(self) -> None:
        if self.bucket not in VALID_ATTRIBUTION_BUCKETS:
            raise ValueError(f'Invalid attribution bucket: {self.bucket}')

    def to_dict(self) -> dict[str, Any]:
        return {
            'bucket': self.bucket,
            'confidence': self.confidence,
            'evidence': self.evidence,
            'recommended_action': self.recommended_action,
        }


def now_utc() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Workflow contract map — defines the contract each pipeline stage must
# satisfy, including required evidence types and gate policy.
# ---------------------------------------------------------------------------

WORKFLOW_CONTRACT_MAP: dict[str, dict[str, Any]] = {
    'weather_ingest': {
        'contract_type': 'EvidencePacket',
        'required_evidence_types': [EVIDENCE_WEATHER],
        'gate_policy': 'soft',
        'description': 'Open-Meteo forecast + historical window fetch',
    },
    'terrain_extract': {
        'contract_type': 'EvidencePacket',
        'required_evidence_types': [EVIDENCE_DEM],
        'gate_policy': 'hard',
        'description': 'DEM-derived slope/aspect/elevation extraction',
    },
    'sar_extract': {
        'contract_type': 'EvidencePacket',
        'required_evidence_types': [EVIDENCE_SAR],
        'gate_policy': 'soft',
        'description': 'Sentinel-1 SAR change detection / mask extraction',
    },
    'snowpack_physics': {
        'contract_type': 'EvidencePacket',
        'required_evidence_types': [EVIDENCE_PHYSICS, EVIDENCE_WEATHER],
        'gate_policy': 'soft',
        'description': 'Snowpack physics proxy computation',
    },
    'risk_fusion': {
        'contract_type': 'VerificationPacket',
        'required_evidence_types': [EVIDENCE_WEATHER, EVIDENCE_DEM],
        'gate_policy': 'hard',
        'description': 'IPA-weighted risk score fusion with UQ gating',
    },
    'publication': {
        'contract_type': 'EvidencePacket',
        'required_evidence_types': [],
        'gate_policy': 'scientist_review',
        'description': 'Forecast grid publication with lineage metadata',
    },
    'drift_check': {
        'contract_type': 'VerificationPacket',
        'required_evidence_types': [EVIDENCE_FIELD],
        'gate_policy': 'scientist_review',
        'description': 'Model drift detection and retrain gating',
    },
    'model_activation': {
        'contract_type': 'VerificationPacket',
        'required_evidence_types': [],
        'gate_policy': 'scientist_review',
        'description': 'Dynamic model candidate activation after automated gates',
    },
}


def validate_workflow_contract(stage: str, packet: EvidencePacket | VerificationPacket) -> list[str]:
    """Validate that a packet satisfies the workflow contract for a stage.

    Returns a list of violation messages (empty if valid).
    """
    violations: list[str] = []
    contract = WORKFLOW_CONTRACT_MAP.get(stage)
    if contract is None:
        violations.append(f'Unknown workflow stage: {stage}')
        return violations

    required_types = contract.get('required_evidence_types', [])
    if not required_types:
        return violations

    if isinstance(packet, EvidencePacket):
        present_types = {e.evidence_type for e in packet.entries}
    else:
        present_types = set(packet.lineage.get('evidence_types', []))

    for rtype in required_types:
        if rtype not in present_types:
            violations.append(
                f'Stage {stage} requires evidence type {rtype} but it is missing'
            )

    return violations


# ---------------------------------------------------------------------------
# Typed WorkflowContract — enforces gate policy at each pipeline stage
# ---------------------------------------------------------------------------

@dataclass
class WorkflowContract:
    """Typed contract for a pipeline stage gate.

    Encodes the gate policy, required evidence types, and the scientist
    validation case type to create when the gate blocks.
    """

    stage: str
    contract_type: str  # 'EvidencePacket' or 'VerificationPacket'
    required_evidence_types: list[str]
    gate_policy: str  # 'soft', 'hard', 'scientist_review'
    description: str = ''
    scientist_case_type: str | None = None  # maps to scientist_validation_cases.case_type
    require_verified: bool = False  # if True, required evidence entries must have verified=True

    def __post_init__(self) -> None:
        if self.gate_policy not in {'soft', 'hard', 'scientist_review'}:
            raise ValueError(f'Invalid gate_policy: {self.gate_policy}')
        if self.contract_type not in {'EvidencePacket', 'VerificationPacket'}:
            raise ValueError(f'Invalid contract_type: {self.contract_type}')

    def evaluate(
        self,
        packet: EvidencePacket | VerificationPacket,
    ) -> tuple[bool, list[str]]:
        """Evaluate the contract against a packet.

        Returns (passed, violations).
        - 'soft' gate: passes with warnings even if evidence is missing.
        - 'hard' gate: fails if any required evidence type is missing.
        - 'scientist_review' gate: fails if packet type mismatch or unverified
          required evidence; passes if no required evidence types and packet
          type matches (routine publication).
        """
        violations = validate_workflow_contract(self.stage, packet)

        # Enforce packet type check
        expected_class = EvidencePacket if self.contract_type == 'EvidencePacket' else VerificationPacket
        if not isinstance(packet, expected_class):
            violations.append(
                f'Stage {self.stage} expects {self.contract_type} but got {type(packet).__name__}'
            )

        # Enforce verified=True on required evidence entries
        if self.require_verified and isinstance(packet, EvidencePacket):
            for entry in packet.entries:
                if entry.evidence_type in self.required_evidence_types and not getattr(entry, 'verified', False):
                    violations.append(
                        f'Stage {self.stage} requires verified=True for evidence type {entry.evidence_type}'
                    )

        type_mismatch = any('expects ' in violation for violation in violations)
        if type_mismatch:
            return False, violations
        if self.gate_policy == 'soft':
            return True, violations
        if self.gate_policy == 'hard':
            return len(violations) == 0, violations
        if self.gate_policy == 'scientist_review':
            if violations:
                return False, violations
            return True, violations
        return True, violations


# Build typed contracts from the existing map
TYPED_WORKFLOW_CONTRACTS: dict[str, WorkflowContract] = {
    stage: WorkflowContract(
        stage=stage,
        contract_type=spec['contract_type'],
        required_evidence_types=spec.get('required_evidence_types', []),
        gate_policy=spec['gate_policy'],
        description=spec.get('description', ''),
        scientist_case_type='model_gate' if spec['gate_policy'] == 'scientist_review' else None,
        require_verified=stage in ('publication', 'drift_check'),
    )
    for stage, spec in WORKFLOW_CONTRACT_MAP.items()
}


def evaluate_publication_gate(
    packet: EvidencePacket | VerificationPacket,
    *,
    publish_eligible: bool = True,
    is_exception: bool = False,
) -> tuple[bool, list[str], str | None]:
    """Evaluate the publication gate for a forecast run.

    Returns (can_publish, violations, scientist_case_type).
    If the gate blocks, scientist_case_type indicates which case to create
    in scientist_validation_cases (or None if no case needed).

    - Routine publication (is_exception=False, publish_eligible=True): passes.
    - Exception release (is_exception=True): blocks until scientist approves.
    - Synthetic/mixed lineage (publish_eligible=False): blocks.
    """
    contract = TYPED_WORKFLOW_CONTRACTS.get('publication')
    if contract is None:
        return True, [], None

    passed, violations = contract.evaluate(packet)

    if not publish_eligible:
        violations.append('publish_eligible is False — synthetic or mixed lineage')
        passed = False

    if is_exception:
        violations.append('Exception release requires scientist review')
        passed = False

    if not passed:
        return False, violations, contract.scientist_case_type

    return True, violations, None
