"""RAvaFcast runtime gate — disabled-by-default seam for candidate modules.

This module provides a metadata-only runtime gate that can be imported by the
inference orchestrator. It does NOT modify risk_score, danger, CAP, SACHET,
or any active-path output. It is controlled by the environment variable
RAVAFCAST_PIPELINE_ENABLED (default: false).

When disabled (default):
    - status = "disabled"
    - active RF output unchanged
    - no candidate computation

When enabled but contracts are missing/invalid:
    - status = "blocked_missing_contract"
    - no candidate output

When enabled with valid contracts but no Partner-selected hypothesis:
    - status = "shadow_not_selected"
    - no publication or alert output

This module is additive and does NOT modify any denylisted file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.common.ravafcast_contracts import (
    ContractViolationError,
    LabelContract,
    StationContract,
    SnowpackContract,
    GridCRSContract,
    RegionElevationContract,
    EvidenceCaseContract,
)


@dataclass(frozen=True)
class GateStatus:
    """Result of a runtime gate check."""
    status: str  # 'disabled' | 'blocked_missing_contract' | 'shadow_not_selected' | 'active'
    reason: str
    contracts_provided: bool
    contracts_valid: bool
    hypothesis_selected: bool
    metadata: dict[str, Any] = field(default_factory=dict)


def _is_enabled() -> bool:
    return os.getenv("RAVAFCAST_PIPELINE_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )


def check_pipeline_status(
    label_contract: LabelContract | None = None,
    station_contract: StationContract | None = None,
    snowpack_contract: SnowpackContract | None = None,
    grid_crs_contract: GridCRSContract | None = None,
    region_elevation_contract: RegionElevationContract | None = None,
    evidence_case_contract: EvidenceCaseContract | None = None,
    hypothesis_selected: bool = False,
) -> GateStatus:
    """Check the RAvaFcast candidate pipeline status.

    Returns a GateStatus describing whether the pipeline is disabled,
    blocked, shadow, or active. Never raises — always returns a status.

    This function does NOT compute any candidate output. It only reports
    what state the gate is in, for metadata emission by the orchestrator.
    """
    if not _is_enabled():
        return GateStatus(
            status="disabled",
            reason="RAVAFCAST_PIPELINE_ENABLED is false (default)",
            contracts_provided=False,
            contracts_valid=False,
            hypothesis_selected=False,
        )

    contracts = [
        label_contract,
        station_contract,
        snowpack_contract,
        grid_crs_contract,
        region_elevation_contract,
        evidence_case_contract,
    ]
    contracts_provided = any(c is not None for c in contracts)

    if not contracts_provided:
        return GateStatus(
            status="blocked_missing_contract",
            reason="No contracts provided — candidate pipeline cannot proceed",
            contracts_provided=False,
            contracts_valid=False,
            hypothesis_selected=hypothesis_selected,
        )

    contracts_valid = True
    validation_errors: list[str] = []
    for c in contracts:
        if c is None:
            continue
        if not hasattr(c, "validate") or not callable(getattr(c, "validate", None)):
            contracts_valid = False
            validation_errors.append(f"{type(c).__name__} has no validate() method")
            continue
        try:
            c.validate()
        except ContractViolationError as exc:
            contracts_valid = False
            validation_errors.append(str(exc))

    if not contracts_valid:
        return GateStatus(
            status="blocked_missing_contract",
            reason=f"Contract validation failed: {'; '.join(validation_errors[:3])}",
            contracts_provided=True,
            contracts_valid=False,
            hypothesis_selected=hypothesis_selected,
        )

    if not hypothesis_selected:
        return GateStatus(
            status="shadow_not_selected",
            reason="Contracts valid but no Partner-selected hypothesis — shadow mode only",
            contracts_provided=True,
            contracts_valid=True,
            hypothesis_selected=False,
        )

    return GateStatus(
        status="active",
        reason="Contracts valid and hypothesis selected — candidate pipeline active",
        contracts_provided=True,
        contracts_valid=True,
        hypothesis_selected=True,
    )


def emit_gate_metadata(status: GateStatus) -> dict[str, Any]:
    """Convert a GateStatus into a metadata dict for the orchestrator.

    This is metadata-only. It does NOT alter any active-path output.
    """
    return {
        "ravafcast_gate": {
            "status": status.status,
            "reason": status.reason,
            "contracts_provided": status.contracts_provided,
            "contracts_valid": status.contracts_valid,
            "hypothesis_selected": status.hypothesis_selected,
            "active_path_unchanged": True,
        }
    }
