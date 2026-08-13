"""Tier-A continuous physical comparison, without danger labels.

The harness joins candidate and direct-science observations by pixel, valid
time, and variable. It never imputes missing observations and never computes
PSS/Brier/ROC or five-level danger metrics. A report is a review artifact only.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from .contracts import OpenForcingContractError, ensure_utc
from .replay import PhysicalValidationReport, SourceReplay


@dataclass(frozen=True)
class PhysicalObservation:
    source_id: str
    pixel_id: str
    valid_time: datetime
    variable: str
    value: float
    unit: str
    source_snapshot_id: str
    synthetic: bool = False

    def validate(self) -> None:
        if not self.source_id.strip() or not self.pixel_id.strip() or not self.variable.strip():
            raise OpenForcingContractError("physical observations require source, pixel, and variable")
        if not self.unit.strip() or not self.source_snapshot_id.strip():
            raise OpenForcingContractError("physical observations require unit and snapshot identity")
        ensure_utc(self.valid_time)
        value = float(self.value)
        if not math.isfinite(value):
            raise OpenForcingContractError("physical observations must contain finite values")
        if self.synthetic:
            raise OpenForcingContractError("synthetic observations cannot enter Tier-A comparison")

    @property
    def join_key(self) -> tuple[str, str, str, str]:
        self.validate()
        return (self.pixel_id, ensure_utc(self.valid_time).isoformat(), self.variable, self.unit)


def _report_id(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compare_continuous_observations(
    *,
    replay: SourceReplay,
    reference: Sequence[PhysicalObservation],
    candidate: Sequence[PhysicalObservation],
    reference_source_id: str,
    candidate_source_id: str,
    variable: str,
    holdout_strategy: str = "forward_time",
    independent_holdout: bool = False,
    provenance_complete: bool = True,
) -> PhysicalValidationReport:
    """Build a pending physical report from exact, non-imputed pairs."""

    replay.validate()
    if not reference_source_id.strip() or not candidate_source_id.strip() or not variable.strip():
        raise OpenForcingContractError("comparison source IDs and variable are required")
    reference_rows = tuple(reference)
    candidate_rows = tuple(candidate)
    for observation in reference_rows + candidate_rows:
        observation.validate()
        if observation.variable != variable:
            raise OpenForcingContractError("all observations must use the requested variable")
    reference_map = {observation.join_key: observation for observation in reference_rows}
    candidate_map = {observation.join_key: observation for observation in candidate_rows}
    pairs = [
        (reference_map[key], candidate_map[key])
        for key in sorted(reference_map.keys() & candidate_map.keys())
        if reference_map[key].source_id == reference_source_id
        and candidate_map[key].source_id == candidate_source_id
    ]
    errors = [candidate_row.value - reference_row.value for reference_row, candidate_row in pairs]
    if errors:
        absolute = [abs(error) for error in errors]
        metrics = (
            ("mae", sum(absolute) / len(absolute)),
            ("rmse", math.sqrt(sum(error * error for error in errors) / len(errors))),
            ("bias", sum(errors) / len(errors)),
            ("max_abs_error", max(absolute)),
            ("paired_coverage", len(pairs) / max(len(reference_rows), 1)),
        )
    else:
        metrics = (("paired_coverage", 0.0),)
    identity = {
        "replay_id": replay.replay_id,
        "reference_source_id": reference_source_id,
        "candidate_source_id": candidate_source_id,
        "variable": variable,
        "reference_keys": sorted(reference_map),
        "candidate_keys": sorted(candidate_map),
        "metrics": metrics,
        "holdout_strategy": holdout_strategy,
    }
    report = PhysicalValidationReport(
        report_id=_report_id(identity),
        replay_id=replay.replay_id,
        reference_source_id=reference_source_id,
        candidate_source_id=candidate_source_id,
        variables=(variable,),
        sample_count=len(reference_rows),
        paired_count=len(pairs),
        holdout_strategy=holdout_strategy,
        independent_holdout=independent_holdout,
        provenance_complete=provenance_complete,
        metrics=metrics,
        decision="pending",
        synthetic_inputs_present=False,
        label_eligible=False,
        label_contract_approved=False,
    )
    report.validate()
    return report
