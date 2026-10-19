"""Centralized model-aware release policy.

Provides a single decision function used by model activation, active-model
resolution, and forecast promotion to enforce consistent release semantics
across the inference pipeline.

When the research gate is enabled:
- Non-baseline models are blocked from activation and authoritative release.
- The baseline surrogate (surrogate_rf_v1) may publish a labelled technical
  artifact only when its existing publication gates pass.
- No model receives warning authority or movement-advice authority.

When the research gate is disabled:
- Normal production semantics apply (authoritative release).
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PublicationEvidence:
    """G-01: Immutable composite evidence object for publication decisions.

    Every caller (daily_inference, promote_forecast_run) must construct this
    object and pass it to evaluate_publication_evidence() for a consistent
    release decision. Missing evidence defaults to False.

    Attributes:
        model_type: Active model type (e.g. 'surrogate_rf_v1').
        model_version: Active model version string.
        uq_passed: Whether UQ calibration gates passed.
        provenance_verified: Whether data provenance was verified.
        validation_spine_passed: Whether validation spine gates passed.
        eaws_reviewed: Whether EAWS factor review was completed.
        release_mode: 'research' or 'production'.
    """
    model_type: str
    model_version: str
    uq_passed: bool = False
    provenance_verified: bool = False
    validation_spine_passed: bool = False
    eaws_reviewed: bool = False
    release_mode: str = 'research'

    def all_gates_passed(self) -> bool:
        """Return True only if every evidence field is True."""
        return (
            self.uq_passed
            and self.provenance_verified
            and self.validation_spine_passed
            and self.eaws_reviewed
        )

    def missing_gates(self) -> list[str]:
        """Return list of gate names that are not satisfied."""
        missing = []
        if not self.uq_passed:
            missing.append('uq')
        if not self.provenance_verified:
            missing.append('provenance')
        if not self.validation_spine_passed:
            missing.append('validation_spine')
        if not self.eaws_reviewed:
            missing.append('eaws_review')
        return missing


def evaluate_publication_evidence(evidence: PublicationEvidence) -> ReleaseDecision:
    """G-01: Evaluate a composite PublicationEvidence and return a ReleaseDecision.

    This is the single canonical entry point for publication decisions.
    All callers must use this function instead of passing individual booleans.
    """
    gate_enabled = is_research_gate_enabled()
    is_baseline = evidence.model_type == BASELINE_MODEL_TYPE

    if not gate_enabled:
        return ReleaseDecision(
            allowed=True,
            artifact_mode='authoritative',
            blocking_reason=None,
            model_type=evidence.model_type,
            model_version=evidence.model_version,
            is_baseline=is_baseline,
            gate_enabled=False,
            warning_authority='full',
            movement_advice='full',
        )

    if not is_baseline:
        return ReleaseDecision(
            allowed=False,
            artifact_mode='blocked',
            blocking_reason='research_gate_non_baseline',
            model_type=evidence.model_type,
            model_version=evidence.model_version,
            is_baseline=False,
            gate_enabled=True,
            warning_authority='none',
            movement_advice='none',
        )

    if not evidence.all_gates_passed():
        missing = ', '.join(evidence.missing_gates())
        return ReleaseDecision(
            allowed=False,
            artifact_mode='blocked',
            blocking_reason=f'publication_gates_not_passed: {missing}',
            model_type=evidence.model_type,
            model_version=evidence.model_version,
            is_baseline=True,
            gate_enabled=True,
            warning_authority='none',
            movement_advice='none',
        )

    return ReleaseDecision(
        allowed=True,
        artifact_mode='technical_artifact',
        blocking_reason=None,
        model_type=evidence.model_type,
        model_version=evidence.model_version,
        is_baseline=True,
        gate_enabled=True,
        warning_authority='none',
        movement_advice='none',
    )


@dataclass(frozen=True)
class ReleaseDecision:
    """Result of evaluating the release policy for a model.

    Attributes:
        allowed: Whether this model can activate/publish.
        artifact_mode: 'technical_artifact' | 'authoritative' | 'blocked'.
        blocking_reason: Human-readable reason when blocked, else None.
        model_type: The model type evaluated.
        model_version: The model version evaluated.
        is_baseline: True if the model is the baseline surrogate.
        gate_enabled: Whether the research gate was enabled at decision time.
        warning_authority: Always 'none' when gate is enabled.
        movement_advice: Always 'none' when gate is enabled.
    """
    allowed: bool
    artifact_mode: str
    blocking_reason: str | None
    model_type: str
    model_version: str
    is_baseline: bool
    gate_enabled: bool
    warning_authority: str
    movement_advice: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


BASELINE_MODEL_TYPE = 'surrogate_rf_v1'


def is_research_gate_enabled() -> bool:
    """Check whether the research model gate is enabled.

    Defaults to True (gate enabled) for safety.
    """
    raw = os.environ.get('RESEARCH_MODEL_GATE_ENABLED', 'true')
    return raw.strip().lower() not in {'0', 'false', 'off', 'no'}


def evaluate_release_decision(
    model_type: str,
    model_version: str,
    *,
    gate_enabled: bool | None = None,
    publication_gates_passed: bool = False,
) -> ReleaseDecision:
    """Evaluate the release policy for a given model.

    Args:
        model_type: The model type (e.g. 'surrogate_rf_v1', 'mts_lstm_v1').
        model_version: The model version string.
        gate_enabled: Override for gate state. If None, reads from env.
        publication_gates_passed: Whether existing publication gates passed.

    Returns:
        ReleaseDecision with allowed, artifact_mode, and blocking reason.
    """
    if gate_enabled is None:
        gate_enabled = is_research_gate_enabled()

    is_baseline = model_type == BASELINE_MODEL_TYPE

    if not gate_enabled:
        return ReleaseDecision(
            allowed=True,
            artifact_mode='authoritative',
            blocking_reason=None,
            model_type=model_type,
            model_version=model_version,
            is_baseline=is_baseline,
            gate_enabled=False,
            warning_authority='full',
            movement_advice='full',
        )

    # Gate is enabled — only baseline can proceed, and only as technical artifact
    if not is_baseline:
        return ReleaseDecision(
            allowed=False,
            artifact_mode='blocked',
            blocking_reason='research_gate_non_baseline',
            model_type=model_type,
            model_version=model_version,
            is_baseline=False,
            gate_enabled=True,
            warning_authority='none',
            movement_advice='none',
        )

    # Baseline model under gate
    if not publication_gates_passed:
        return ReleaseDecision(
            allowed=False,
            artifact_mode='blocked',
            blocking_reason='publication_gates_not_passed',
            model_type=model_type,
            model_version=model_version,
            is_baseline=True,
            gate_enabled=True,
            warning_authority='none',
            movement_advice='none',
        )

    return ReleaseDecision(
        allowed=True,
        artifact_mode='technical_artifact',
        blocking_reason=None,
        model_type=model_type,
        model_version=model_version,
        is_baseline=True,
        gate_enabled=True,
        warning_authority='none',
        movement_advice='none',
    )
