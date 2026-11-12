"""Cross-sensor calibration for S1/GIBS/S2/weather against SnowEx and Himalayan observations.

Builds calibration pairs from reference datasets, computes bias/RMSE/correlation
per sensor pair, and applies linear corrections to sensor values before fusion.

Env flags:
  CROSS_SENSOR_CALIBRATION_ENABLED — apply corrections in fusion (default: false)
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CROSS_SENSOR_CALIBRATION_ENABLED = os.getenv('CROSS_SENSOR_CALIBRATION_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

SAFETY_DISCLAIMER = (
    'Decision-support tool only. Not an official avalanche warning. '
    'Always consult local avalanche forecasting services for operational decisions.'
)


@dataclass(frozen=True)
class CalibrationPair:
    """A single calibration pair between two sensors or sensor vs reference."""
    sensor_a: str
    sensor_b: str
    variable: str
    cell_id: str
    timestamp: str
    value_a: float
    value_b: float
    reference_source: str = ''


@dataclass(frozen=True)
class CalibrationMetrics:
    """Calibration metrics for a sensor pair."""
    sensor_a: str
    sensor_b: str
    variable: str
    count: int = 0
    bias: float = 0.0
    rmse: float = 0.0
    correlation: float = 0.0
    slope: float = 1.0
    intercept: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'sensor_a': self.sensor_a,
            'sensor_b': self.sensor_b,
            'variable': self.variable,
            'count': self.count,
            'bias': self.bias,
            'rmse': self.rmse,
            'correlation': self.correlation,
            'slope': self.slope,
            'intercept': self.intercept,
        }


def load_calibration_pairs(path: str) -> list[CalibrationPair]:
    """Load calibration pairs from a CSV file.

    Expected columns: sensor_a, sensor_b, variable, cell_id, timestamp, value_a, value_b, reference_source
    Returns empty list if file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return []

    pairs: list[CalibrationPair] = []
    with open(p, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pairs.append(CalibrationPair(
                    sensor_a=row['sensor_a'],
                    sensor_b=row['sensor_b'],
                    variable=row['variable'],
                    cell_id=row.get('cell_id', ''),
                    timestamp=row.get('timestamp', ''),
                    value_a=float(row['value_a']),
                    value_b=float(row['value_b']),
                    reference_source=row.get('reference_source', ''),
                ))
            except (KeyError, ValueError):
                continue
    return pairs


def load_snowex_pairs(path: str | None = None) -> list[CalibrationPair]:
    """Load SnowEx calibration pairs."""
    default_path = os.getenv(
        'SNOWEX_CALIBRATION_PATH',
        str(Path(__file__).resolve().parent.parent.parent / 'config' / 'snowex_calibration_data.csv'),
    )
    return load_calibration_pairs(path or default_path)


def load_himalayan_pairs(path: str | None = None) -> list[CalibrationPair]:
    """Load Himalayan observation calibration pairs."""
    default_path = os.getenv(
        'HIMALAYAN_CALIBRATION_PATH',
        str(Path(__file__).resolve().parent.parent.parent / 'config' / 'himalayan_calibration_data.csv'),
    )
    return load_calibration_pairs(path or default_path)


def compute_calibration_metrics(pairs: list[CalibrationPair]) -> list[CalibrationMetrics]:
    """Compute calibration metrics for each sensor pair + variable combination.

    Returns one CalibrationMetrics per unique (sensor_a, sensor_b, variable) group.
    """
    if not pairs:
        return []

    groups: dict[tuple[str, str, str], list[CalibrationPair]] = {}
    for p in pairs:
        key = (p.sensor_a, p.sensor_b, p.variable)
        groups.setdefault(key, []).append(p)

    metrics: list[CalibrationMetrics] = []
    for (sensor_a, sensor_b, variable), group_pairs in groups.items():
        n = len(group_pairs)
        if n < 2:
            metrics.append(CalibrationMetrics(
                sensor_a=sensor_a, sensor_b=sensor_b, variable=variable, count=n,
            ))
            continue

        values_a = [p.value_a for p in group_pairs]
        values_b = [p.value_b for p in group_pairs]

        mean_a = sum(values_a) / n
        mean_b = sum(values_b) / n

        bias = mean_a - mean_b

        squared_errors = [(a - b) ** 2 for a, b in zip(values_a, values_b)]
        rmse = math.sqrt(sum(squared_errors) / n)

        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b)) / n
        var_a = sum((a - mean_a) ** 2 for a in values_a) / n
        var_b = sum((b - mean_b) ** 2 for b in values_b) / n

        correlation = 0.0
        if var_a > 1e-12 and var_b > 1e-12:
            correlation = cov / (math.sqrt(var_a) * math.sqrt(var_b))
            correlation = max(-1.0, min(1.0, correlation))

        slope = 1.0
        intercept = 0.0
        if var_b > 1e-12:
            slope = cov / var_b
            intercept = mean_a - slope * mean_b

        metrics.append(CalibrationMetrics(
            sensor_a=sensor_a,
            sensor_b=sensor_b,
            variable=variable,
            count=n,
            bias=round(bias, 6),
            rmse=round(rmse, 6),
            correlation=round(correlation, 6),
            slope=round(slope, 6),
            intercept=round(intercept, 6),
        ))

    return metrics


def apply_calibration_correction(
    value: float,
    sensor: str,
    calibration_metrics: list[CalibrationMetrics],
    reference_sensor: str = 'reference',
) -> float:
    """Apply linear calibration correction to a sensor value.

    Finds the calibration metrics for (sensor, reference_sensor) and applies:
      corrected = slope * value + intercept

    Returns the original value if no calibration is found or if disabled.
    """
    if not CROSS_SENSOR_CALIBRATION_ENABLED:
        return value

    for m in calibration_metrics:
        if m.sensor_a == sensor and m.sensor_b == reference_sensor:
            return m.slope * value + m.intercept

    return value


def load_all_calibration_metrics() -> list[CalibrationMetrics]:
    """Load and compute all available calibration metrics.

    Combines SnowEx and Himalayan pairs, computes metrics.
    Returns empty list when no data files exist.
    """
    pairs = load_snowex_pairs() + load_himalayan_pairs()
    if not pairs:
        return []
    return compute_calibration_metrics(pairs)
