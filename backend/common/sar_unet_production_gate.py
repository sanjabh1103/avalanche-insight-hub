"""SAR U-Net production gate evaluator.

Standalone module that evaluates whether the SAR U-Net model is ready
for production promotion. Wraps the existing assess_production_gates
logic from lstm_model.py with a CLI-callable interface and adds
SAR-specific quality gates (IoU, precision, recall thresholds).

Environment variables:
  SAR_UNET_GATE_MIN_IOU: Minimum IoU threshold (default: 0.4)
  SAR_UNET_GATE_MIN_PRECISION: Minimum precision (default: 0.6)
  SAR_UNET_GATE_MIN_RECALL: Minimum recall (default: 0.5)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

SAR_UNET_GATE_MIN_IOU = float(os.getenv('SAR_UNET_GATE_MIN_IOU', '0.4'))
SAR_UNET_GATE_MIN_PRECISION = float(os.getenv('SAR_UNET_GATE_MIN_PRECISION', '0.6'))
SAR_UNET_GATE_MIN_RECALL = float(os.getenv('SAR_UNET_GATE_MIN_RECALL', '0.5'))


@dataclass(frozen=True)
class SarUnetGateResult:
    """Result of SAR U-Net production gate evaluation."""
    passed: bool
    iou: float
    precision: float
    recall: float
    f1_score: float
    min_iou: float
    min_precision: float
    min_recall: float
    failure_reasons: list[str] = field(default_factory=list)
    recommendation: str = 'shadow'


def evaluate_sar_unet_quality_gate(
    metrics: dict[str, Any],
) -> SarUnetGateResult:
    """Evaluate SAR U-Net model quality against production thresholds.

    Args:
        metrics: Dict with keys 'iou', 'precision', 'recall' (floats 0-1)

    Returns:
        SarUnetGateResult with pass/fail and recommendation
    """
    iou = float(metrics.get('iou', 0.0) or 0.0)
    precision = float(metrics.get('precision', 0.0) or 0.0)
    recall = float(metrics.get('recall', 0.0) or 0.0)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-8) if (precision + recall) > 0 else 0.0

    failures: list[str] = []

    if iou < SAR_UNET_GATE_MIN_IOU:
        failures.append(f'iou_{iou:.3f}_below_{SAR_UNET_GATE_MIN_IOU}')
    if precision < SAR_UNET_GATE_MIN_PRECISION:
        failures.append(f'precision_{precision:.3f}_below_{SAR_UNET_GATE_MIN_PRECISION}')
    if recall < SAR_UNET_GATE_MIN_RECALL:
        failures.append(f'recall_{recall:.3f}_below_{SAR_UNET_GATE_MIN_RECALL}')

    passed = len(failures) == 0
    recommendation = 'promote' if passed else 'shadow'

    return SarUnetGateResult(
        passed=passed,
        iou=round(iou, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1_score=round(f1, 4),
        min_iou=SAR_UNET_GATE_MIN_IOU,
        min_precision=SAR_UNET_GATE_MIN_PRECISION,
        min_recall=SAR_UNET_GATE_MIN_RECALL,
        failure_reasons=failures,
        recommendation=recommendation,
    )


def evaluate_full_production_gate(
    sar_metrics: dict[str, Any],
    lstm_pss: float,
    lstm_brier: float,
    rf_pss: float,
    rf_brier: float,
    sar_release_gate_passed: bool,
    sar_unet_promoted_count: int,
    sar_unet_promoted_region_count: int,
    sar_unet_promoted_scene_date_count: int,
) -> dict[str, Any]:
    """Evaluate the full SAR U-Net + LSTM production gate.

    Combines SAR U-Net quality gates with the existing LSTM shadow
    quality and SAR volume gates from assess_production_gates.

    Args:
        sar_metrics: SAR U-Net evaluation metrics (iou, precision, recall)
        lstm_pss, lstm_brier, rf_pss, rf_brier: Model comparison metrics
        sar_release_gate_passed: Whether SAR release gate passed
        sar_unet_promoted_count: Number of promoted SAR U-Net events
        sar_unet_promoted_region_count: Number of regions with promoted events
        sar_unet_promoted_scene_date_count: Number of unique scene dates

    Returns:
        Dict with all gate results and overall production eligibility
    """
    from backend.lstm_model import assess_production_gates

    lstm_gates = assess_production_gates(
        lstm_pss=lstm_pss,
        lstm_brier=lstm_brier,
        rf_pss=rf_pss,
        rf_brier=rf_brier,
        sar_release_gate_passed=sar_release_gate_passed,
        sar_unet_promoted_count=sar_unet_promoted_count,
        sar_unet_promoted_region_count=sar_unet_promoted_region_count,
        sar_unet_promoted_scene_date_count=sar_unet_promoted_scene_date_count,
    )

    sar_quality = evaluate_sar_unet_quality_gate(sar_metrics)

    overall_passed = bool(
        lstm_gates['production_eligibility_gate_passed']
        and sar_quality.passed
    )

    return {
        'overall_passed': overall_passed,
        'recommendation': 'promote' if overall_passed else 'shadow',
        'sar_unet_quality_gate': {
            'passed': sar_quality.passed,
            'iou': sar_quality.iou,
            'precision': sar_quality.precision,
            'recall': sar_quality.recall,
            'f1_score': sar_quality.f1_score,
            'failure_reasons': sar_quality.failure_reasons,
            'thresholds': {
                'min_iou': sar_quality.min_iou,
                'min_precision': sar_quality.min_precision,
                'min_recall': sar_quality.min_recall,
            },
        },
        **lstm_gates,
    }


def main() -> int:
    """CLI entry point for SAR U-Net production gate evaluation."""
    if len(sys.argv) < 2:
        print('Usage: python -m backend.common.sar_unet_production_gate <metrics_json>')
        print('  metrics_json: JSON string with iou, precision, recall')
        return 1

    try:
        metrics = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(f'Error: invalid JSON: {exc}', file=sys.stderr)
        return 1

    result = evaluate_sar_unet_quality_gate(metrics)
    print(json.dumps({
        'passed': result.passed,
        'iou': result.iou,
        'precision': result.precision,
        'recall': result.recall,
        'f1_score': result.f1_score,
        'failure_reasons': result.failure_reasons,
        'recommendation': result.recommendation,
        'thresholds': {
            'min_iou': result.min_iou,
            'min_precision': result.min_precision,
            'min_recall': result.min_recall,
        },
    }, indent=2))
    return 0 if result.passed else 1


if __name__ == '__main__':
    sys.exit(main())
