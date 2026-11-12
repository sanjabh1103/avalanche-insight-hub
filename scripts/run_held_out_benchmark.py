#!/usr/bin/env python3
"""Run held-out benchmark package.

Usage:
  python scripts/run_held_out_benchmark.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.common.benchmark_package import (
    BenchmarkConfig,
    run_benchmark,
    export_report_json,
    export_report_markdown,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run held-out benchmark package')
    parser.add_argument('--dry-run', action='store_true', help='Run with synthetic data, no DB access')
    parser.add_argument('--split-file', default='config/held_out_split.csv', help='Path to held-out split CSV')
    parser.add_argument('--output-dir', default='artifacts/benchmarks', help='Output directory for reports')
    args = parser.parse_args(argv)

    if args.dry_run:
        print('Running in dry-run mode with synthetic data...')
        predictions = [0.8, 0.3, 0.6, 0.9, 0.2, 0.7, 0.4, 0.85, 0.15, 0.55]
        labels = [1, 0, 1, 1, 0, 1, 0, 1, 0, 0]
        prediction_times = ['2026-01-10T06:00:00Z'] * 10
        event_times = ['2026-01-10T12:00:00Z'] * 10
    else:
        print('Full benchmark requires inference pipeline + held-out labels.')
        print('Use --dry-run for synthetic benchmark validation.')
        return 1

    config = BenchmarkConfig(
        name='colorado_himalaya_held_out',
        region='colorado_rockies+great_himalaya',
    )

    report = run_benchmark(
        config,
        predictions,
        labels,
        prediction_times=prediction_times,
        event_times=event_times,
    )

    output_dir = Path(args.output_dir)
    json_path = output_dir / f'{config.name}.json'
    md_path = output_dir / f'{config.name}.md'

    export_report_json(report, str(json_path))
    export_report_markdown(report, str(md_path))

    print(f'Benchmark report exported:')
    print(f'  JSON: {json_path}')
    print(f'  Markdown: {md_path}')
    print(f'  Brier: {report.brier_score:.4f}')
    print(f'  Recall: {report.recall:.4f}')
    print(f'  FAR: {report.false_alarm_rate:.4f}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
