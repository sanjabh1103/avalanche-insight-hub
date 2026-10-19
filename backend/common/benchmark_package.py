"""Held-out benchmark package — reproducible reports with Brier, calibration, recall, false-alarm rate, lead time.

Computes standard verification metrics for avalanche forecast models on held-out
splits, exports JSON and Markdown reports, and supports baseline vs candidate
comparison.

Env flags:
  BENCHMARK_PACKAGE_ENABLED — enable benchmark computation (default: false)
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BENCHMARK_PACKAGE_ENABLED = os.getenv('BENCHMARK_PACKAGE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)


@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for a benchmark run."""
    name: str
    region: str
    held_out_split: str = 'held_out'
    metrics: list[str] = field(default_factory=lambda: ['brier', 'calibration', 'recall', 'false_alarm_rate', 'lead_time_hours'])


@dataclass
class BenchmarkReport:
    """Complete benchmark report with all computed metrics."""
    name: str
    region: str
    timestamp: str
    count: int = 0
    brier_score: float = 0.0
    calibration_error: float = 0.0
    recall: float = 0.0
    false_alarm_rate: float = 0.0
    lead_time_hours: float = 0.0
    per_cell_results: list[dict[str, Any]] = field(default_factory=list)
    disclaimer: str = field(default=SAFETY_DISCLAIMER)

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'region': self.region,
            'timestamp': self.timestamp,
            'count': self.count,
            'brier_score': self.brier_score,
            'calibration_error': self.calibration_error,
            'recall': self.recall,
            'false_alarm_rate': self.false_alarm_rate,
            'lead_time_hours': self.lead_time_hours,
            'per_cell_results': self.per_cell_results,
            'disclaimer': self.disclaimer,
        }


def compute_brier_score(predictions: list[float], labels: list[int]) -> float:
    """Compute Brier score (mean squared error of probabilistic predictions).

    Args:
        predictions: List of predicted probabilities [0, 1].
        labels: List of binary labels (0 or 1).

    Returns:
        Brier score (lower is better, 0 = perfect).
    """
    if not predictions or len(predictions) != len(labels):
        return 0.0
    return sum((p - l) ** 2 for p, l in zip(predictions, labels)) / len(predictions)


def compute_calibration_error(predictions: list[float], labels: list[int], n_bins: int = 10) -> float:
    """Compute calibration error (reliability) using equal-width bins.

    Returns mean absolute difference between predicted and observed frequencies
    across bins.
    """
    if not predictions or len(predictions) != len(labels):
        return 0.0

    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    total_error = 0.0
    used_bins = 0

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        in_bin = [(p, l) for p, l in zip(predictions, labels) if lo <= p < hi or (i == n_bins - 1 and p == hi)]
        if not in_bin:
            continue
        mean_pred = sum(p for p, _ in in_bin) / len(in_bin)
        mean_label = sum(l for _, l in in_bin) / len(in_bin)
        total_error += abs(mean_pred - mean_label)
        used_bins += 1

    return total_error / used_bins if used_bins > 0 else 0.0


def compute_recall(predictions: list[float], labels: list[int], threshold: float = 0.5) -> float:
    """Compute recall (true positive rate).

    Args:
        predictions: Predicted probabilities.
        labels: Binary labels.
        threshold: Decision threshold for binary prediction.

    Returns:
        Recall = TP / (TP + FN), 0.0 if no positives.
    """
    if not predictions or len(predictions) != len(labels):
        return 0.0

    tp = sum(1 for p, l in zip(predictions, labels) if p >= threshold and l == 1)
    fn = sum(1 for p, l in zip(predictions, labels) if p < threshold and l == 1)

    return tp / (tp + fn) if (tp + fn) > 0 else 0.0


def compute_false_alarm_rate(predictions: list[float], labels: list[int], threshold: float = 0.5) -> float:
    """Compute false alarm rate (false positive rate).

    Returns:
        FAR = FP / (FP + TN), 0.0 if no negatives.
    """
    if not predictions or len(predictions) != len(labels):
        return 0.0

    fp = sum(1 for p, l in zip(predictions, labels) if p >= threshold and l == 0)
    tn = sum(1 for p, l in zip(predictions, labels) if p < threshold and l == 0)

    return fp / (fp + tn) if (fp + tn) > 0 else 0.0


def compute_lead_time_hours(
    prediction_times: list[str],
    event_times: list[str],
) -> float:
    """Compute mean lead time in hours between predictions and events.

    Args:
        prediction_times: ISO timestamps of predictions.
        event_times: ISO timestamps of actual events.

    Returns:
        Mean lead time in hours (positive = prediction before event).
    """
    if not prediction_times or len(prediction_times) != len(event_times):
        return 0.0

    lead_times = []
    for pred_ts, event_ts in zip(prediction_times, event_times):
        try:
            pred_dt = datetime.fromisoformat(str(pred_ts).replace('Z', '+00:00'))
            event_dt = datetime.fromisoformat(str(event_ts).replace('Z', '+00:00'))
            delta = (event_dt - pred_dt).total_seconds() / 3600.0
            lead_times.append(delta)
        except (ValueError, TypeError):
            continue

    return sum(lead_times) / len(lead_times) if lead_times else 0.0


def run_benchmark(
    config: BenchmarkConfig,
    predictions: list[float],
    labels: list[int],
    *,
    prediction_times: list[str] | None = None,
    event_times: list[str] | None = None,
    per_cell: list[dict[str, Any]] | None = None,
) -> BenchmarkReport:
    """Run a complete benchmark computation.

    Args:
        config: Benchmark configuration.
        predictions: Predicted probabilities.
        labels: Binary labels.
        prediction_times: Optional timestamps for lead time.
        event_times: Optional event timestamps for lead time.
        per_cell: Optional per-cell results for detailed report.

    Returns:
        BenchmarkReport with all computed metrics.
    """
    report = BenchmarkReport(
        name=config.name,
        region=config.region,
        timestamp=datetime.now(timezone.utc).isoformat(),
        count=len(predictions),
        per_cell_results=per_cell or [],
    )

    if not predictions:
        return report

    if 'brier' in config.metrics:
        report.brier_score = round(compute_brier_score(predictions, labels), 6)

    if 'calibration' in config.metrics:
        report.calibration_error = round(compute_calibration_error(predictions, labels), 6)

    if 'recall' in config.metrics:
        report.recall = round(compute_recall(predictions, labels), 6)

    if 'false_alarm_rate' in config.metrics:
        report.false_alarm_rate = round(compute_false_alarm_rate(predictions, labels), 6)

    if 'lead_time_hours' in config.metrics and prediction_times and event_times:
        report.lead_time_hours = round(compute_lead_time_hours(prediction_times, event_times), 2)

    return report


def export_report_json(report: BenchmarkReport, path: str) -> None:
    """Export benchmark report as JSON."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(report.to_dict(), f, indent=2)


def export_report_markdown(report: BenchmarkReport, path: str) -> None:
    """Export benchmark report as Markdown."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f'# Benchmark Report: {report.name}',
        '',
        f'**Region:** {report.region}',
        f'**Timestamp:** {report.timestamp}',
        f'**Samples:** {report.count}',
        '',
        '## Metrics',
        '',
        f'| Metric | Value |',
        f'|--------|-------|',
        f'| Brier Score | {report.brier_score:.4f} |',
        f'| Calibration Error | {report.calibration_error:.4f} |',
        f'| Recall | {report.recall:.4f} |',
        f'| False Alarm Rate | {report.false_alarm_rate:.4f} |',
        f'| Lead Time (hours) | {report.lead_time_hours:.2f} |',
        '',
        f'_{report.disclaimer}_',
    ]
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def compare_reports(baseline: BenchmarkReport, candidate: BenchmarkReport) -> dict[str, Any]:
    """Compare two benchmark reports and return delta table.

    Returns dict with per-metric deltas (candidate - baseline).
    Positive delta = candidate is better for recall/lead_time, worse for brier/far/calibration.
    """
    return {
        'brier_score_delta': round(candidate.brier_score - baseline.brier_score, 6),
        'calibration_error_delta': round(candidate.calibration_error - baseline.calibration_error, 6),
        'recall_delta': round(candidate.recall - baseline.recall, 6),
        'false_alarm_rate_delta': round(candidate.false_alarm_rate - baseline.false_alarm_rate, 6),
        'lead_time_delta': round(candidate.lead_time_hours - baseline.lead_time_hours, 2),
        'count_delta': candidate.count - baseline.count,
    }
