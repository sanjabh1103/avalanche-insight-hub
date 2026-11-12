"""Validation spine gates — non-denylisted wrapper for verification exit gates.

This module composes the core verification exit gates (from verification_exit_gates.py)
with additional validation-spine checks (EAWS review ledger, calibration drift)
without modifying the denylisted core file.

G-20/G-15: EAWS and drift checks were relocated here from verification_exit_gates.py
to respect the denylist governance boundary.
"""
from __future__ import annotations

from typing import Any

from backend.common.verification_exit_gates import (
    GateResult,
    check_gate_d_production,
)


def check_gate_d_production_with_validation_spine(
    *,
    cells: list[dict[str, Any]] | None = None,
    min_cells_total: int = 100,
    min_anomaly_detection_rate: float = 0.01,
) -> GateResult:
    """Gate D with validation spine: production readiness + EAWS/drift checks.

    Calls the original check_gate_d_production() and then composes
    EAWS review-ledger and calibration-drift results on top.

    - Preserves all core metrics, blockers, warnings, and thresholds.
    - Adds EAWS review-ledger metrics and warnings.
    - Adds calibration-drift metrics; adds a blocker only for critical drift.
    - Returns a new GateResult; never mutates the core result in place.
    - Preserves core early-return behavior when VERIFICATION_SPINE_ENABLED is false.
    """
    core_result = check_gate_d_production(
        cells=cells,
        min_cells_total=min_cells_total,
        min_anomaly_detection_rate=min_anomaly_detection_rate,
    )

    # If the core gate returned early (e.g. VERIFICATION_SPINE_ENABLED is false),
    # return the core result as-is without adding validation-spine checks.
    if not core_result.passed and core_result.blockers and 'VERIFICATION_SPINE_ENABLED is false' in core_result.blockers:
        return core_result

    # Compose a new result with all core fields plus validation-spine additions
    combined_metrics = dict(core_result.metrics)
    combined_blockers = list(core_result.blockers)
    combined_warnings = list(core_result.warnings)

    # EAWS review ledger check
    try:
        from backend.common.eaws_review_ledger import load_review_ledger
        review_records = load_review_ledger()
        combined_metrics['eaws_review_records'] = len(review_records)
        if len(review_records) == 0:
            combined_warnings.append('EAWS review ledger is empty — no factor review records found')
    except Exception as eaws_exc:
        combined_warnings.append(f'EAWS review ledger check failed: {eaws_exc}')
        combined_metrics['eaws_review_records'] = -1

    # Calibration drift gate check
    try:
        from backend.common.calibration_drift import generate_scheduled_drift_report
        drift_report = generate_scheduled_drift_report()
        combined_metrics['drift_report'] = drift_report
        drift_gate = drift_report.get('gate', {})
        if not drift_gate.get('gate_passed', True):
            combined_blockers.append(f'Calibration drift gate failed: {drift_gate.get("gate_reason", "unknown")}')
        elif drift_gate.get('gate_reason') == 'warning_allowed':
            combined_warnings.append(f'Calibration drift warning: {drift_report.get("alert", {}).get("message", "")}')
    except Exception as drift_exc:
        combined_warnings.append(f'Calibration drift check failed: {drift_exc}')
        combined_metrics['drift_report'] = None

    return GateResult(
        'D',
        passed=len(combined_blockers) == 0,
        metrics=combined_metrics,
        blockers=combined_blockers,
        warnings=combined_warnings,
    )
