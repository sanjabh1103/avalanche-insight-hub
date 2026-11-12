"""Calibration drift reporting for validation spine.

Computes drift reports from per-run calibration history records.
Path via env CALIBRATION_HISTORY_PATH, skip silently when unset.

G-09: Extended with threshold evaluation, alert status, drift gate,
and scheduled report generator to make the scaffold operational.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Drift thresholds (configurable via env)
DRIFT_ALERT_THRESHOLD = float(os.getenv('CALIBRATION_DRIFT_ALERT_THRESHOLD', '0.1'))
DRIFT_BLOCK_THRESHOLD = float(os.getenv('CALIBRATION_DRIFT_BLOCK_THRESHOLD', '0.2'))
DRIFT_RETENTION_RUNS = int(os.getenv('CALIBRATION_DRIFT_RETENTION_RUNS', '30'))


@dataclass(frozen=True)
class DriftAlert:
    """Calibration drift alert status."""
    alert_status: str  # 'none', 'warning', 'critical'
    message: str
    drift_gap: float | None
    threshold_used: float
    timestamp: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DriftGateResult:
    """Drift gate result for publication decision."""
    gate_passed: bool
    gate_reason: str  # 'no_drift', 'warning_allowed', 'drift_blocks_publication', 'insufficient_data'
    drift_report: dict
    alert: DriftAlert | None

    def as_dict(self) -> dict:
        return {
            'gate_passed': self.gate_passed,
            'gate_reason': self.gate_reason,
            'drift_report': self.drift_report,
            'alert': self.alert.as_dict() if self.alert else None,
        }


def _default_history_path() -> str:
    from pathlib import Path
    return os.getenv(
        'CALIBRATION_HISTORY_PATH',
        str(Path(__file__).resolve().parent.parent / 'config' / 'calibration_history.jsonl')
    )


def compute_drift_report(history: list[dict]) -> dict:
    """Compute a calibration drift report from history records.

    Each record should have: run_id, generated_at, empirical_coverage,
    held_out_coverage, alpha.

    Returns:
        {trend, latest_gap, mean_gap, breach: bool}
    """
    if not history or len(history) < 3:
        return {
            'trend': 'insufficient_data',
            'latest_gap': None,
            'mean_gap': None,
            'breach': False,
        }

    # Use the latest >=3 runs
    recent = history[-3:]

    gaps: list[float] = []
    for rec in recent:
        coverage = rec.get('held_out_coverage')
        if coverage is None:
            coverage = rec.get('empirical_coverage')
        if coverage is None:
            continue
        alpha = rec.get('alpha', 0.1)
        target = 1.0 - alpha
        gap = abs(coverage - target)
        gaps.append(gap)

    if not gaps:
        return {
            'trend': 'insufficient_data',
            'latest_gap': None,
            'mean_gap': None,
            'breach': False,
        }

    latest_gap = gaps[-1]
    mean_gap = round(sum(gaps) / len(gaps), 4)

    # Determine trend
    if len(gaps) >= 2:
        if gaps[-1] > gaps[0]:
            trend = 'worsening'
        elif gaps[-1] < gaps[0]:
            trend = 'improving'
        else:
            trend = 'stable'
    else:
        trend = 'stable'

    breach = latest_gap > DRIFT_ALERT_THRESHOLD

    return {
        'trend': trend,
        'latest_gap': round(latest_gap, 4),
        'mean_gap': mean_gap,
        'breach': breach,
    }


def evaluate_drift_alert(drift_report: dict) -> DriftAlert:
    """G-09: Evaluate drift report and produce an alert status.

    Alert levels:
    - 'none': drift gap within acceptable range
    - 'warning': drift gap exceeds alert threshold but below block threshold
    - 'critical': drift gap exceeds block threshold
    """
    latest_gap = drift_report.get('latest_gap')
    timestamp = datetime.now(timezone.utc).isoformat()

    if latest_gap is None:
        return DriftAlert(
            alert_status='none',
            message='No drift data available',
            drift_gap=None,
            threshold_used=DRIFT_ALERT_THRESHOLD,
            timestamp=timestamp,
        )

    if latest_gap >= DRIFT_BLOCK_THRESHOLD:
        return DriftAlert(
            alert_status='critical',
            message=f'Drift gap {latest_gap:.4f} exceeds block threshold {DRIFT_BLOCK_THRESHOLD}',
            drift_gap=latest_gap,
            threshold_used=DRIFT_BLOCK_THRESHOLD,
            timestamp=timestamp,
        )

    if latest_gap >= DRIFT_ALERT_THRESHOLD:
        return DriftAlert(
            alert_status='warning',
            message=f'Drift gap {latest_gap:.4f} exceeds alert threshold {DRIFT_ALERT_THRESHOLD}',
            drift_gap=latest_gap,
            threshold_used=DRIFT_ALERT_THRESHOLD,
            timestamp=timestamp,
        )

    return DriftAlert(
        alert_status='none',
        message=f'Drift gap {latest_gap:.4f} within acceptable range',
        drift_gap=latest_gap,
        threshold_used=DRIFT_ALERT_THRESHOLD,
        timestamp=timestamp,
    )


def evaluate_drift_gate(
    drift_report: dict,
    alert: DriftAlert | None = None,
) -> DriftGateResult:
    """G-09: Evaluate whether drift blocks publication or produces a labelled warning.

    Gate logic:
    - 'critical' alert: gate fails (blocks publication)
    - 'warning' alert: gate passes with labelled warning
    - 'none' alert: gate passes
    - insufficient_data: gate passes (cannot block without data)
    """
    if alert is None:
        alert = evaluate_drift_alert(drift_report)

    if drift_report.get('trend') == 'insufficient_data':
        return DriftGateResult(
            gate_passed=True,
            gate_reason='insufficient_data',
            drift_report=drift_report,
            alert=alert,
        )

    if alert.alert_status == 'critical':
        return DriftGateResult(
            gate_passed=False,
            gate_reason='drift_blocks_publication',
            drift_report=drift_report,
            alert=alert,
        )

    if alert.alert_status == 'warning':
        return DriftGateResult(
            gate_passed=True,
            gate_reason='warning_allowed',
            drift_report=drift_report,
            alert=alert,
        )

    return DriftGateResult(
        gate_passed=True,
        gate_reason='no_drift',
        drift_report=drift_report,
        alert=alert,
    )


def generate_scheduled_drift_report(path: str | None = None) -> dict:
    """G-09: Generate a complete scheduled drift report with alert and gate evaluation.

    Combines: load history -> compute drift -> evaluate alert -> evaluate gate.
    Returns a dict suitable for inclusion in technical artifact and validation ledger.
    """
    history = load_calibration_history(path)
    drift_report = compute_drift_report(history)
    alert = evaluate_drift_alert(drift_report)
    gate = evaluate_drift_gate(drift_report, alert)

    return {
        'drift_report': drift_report,
        'alert': alert.as_dict(),
        'gate': gate.as_dict(),
        'history_length': len(history),
        'retention_limit': DRIFT_RETENTION_RUNS,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }


def append_calibration_history(
    path: str | None = None,
    record: dict | None = None,
) -> None:
    """Append a calibration record to the JSONL history file.

    Silently skips when no path is configured (shadow-lane instrumentation).
    """
    if record is None:
        raise ValueError('record is required')

    history_path = path or _default_history_path()
    if not history_path:
        return  # Shadow lane — skip silently when unset

    p = Path(history_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open('a') as f:
        f.write(json.dumps(record) + '\n')


def load_calibration_history(path: str | None = None) -> list[dict]:
    """Load all calibration history records from the JSONL file.

    G-09: Applies retention limit to prevent unbounded growth.
    """
    history_path = path or _default_history_path()
    if not history_path:
        return []

    p = Path(history_path)
    if not p.exists():
        return []

    records: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))

    # Apply retention limit — keep only the most recent N records
    if len(records) > DRIFT_RETENTION_RUNS:
        records = records[-DRIFT_RETENTION_RUNS:]

    return records
