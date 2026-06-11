"""Generate a concise random-forest methodology baseline report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _fmt(value: Any, fallback: str = 'n/a') -> str:
    if value is None:
        return fallback
    if isinstance(value, float):
        return f'{value:.3f}'
    return str(value)


def build_rf_methodology_report(metadata: dict[str, Any]) -> str:
    resampling = metadata.get('resampling') if isinstance(metadata.get('resampling'), dict) else {}
    cv = metadata.get('time_series_cv') if isinstance(metadata.get('time_series_cv'), dict) else {}
    calibration = metadata.get('calibration') if isinstance(metadata.get('calibration'), dict) else {}
    selected_features = metadata.get('selected_features') if isinstance(metadata.get('selected_features'), list) else []
    metrics = metadata.get('metrics') if isinstance(metadata.get('metrics'), dict) else {}

    lines = [
        '# Random-Forest Methodology Baseline',
        '',
        f'Generated: {datetime.now(timezone.utc).isoformat()}',
        '',
        '## Claim Boundary',
        '',
        'This report documents the active explainable RF baseline. It is not a promoted MTS-LSTM, SAR FCN, or authority-grade warning claim.',
        '',
        '## Training And Imbalance Handling',
        '',
        f"- Model family: {_fmt(metadata.get('model_family'), 'RandomForestClassifier')}",
        f"- Resampling strategy: {_fmt(resampling.get('strategy'))}",
        f"- Class weighting: {_fmt(metadata.get('class_weight'))}",
        f"- Time-series CV mean PSS: {_fmt(cv.get('mean_pss'))}",
        f"- PSS threshold: {_fmt(metrics.get('pss_threshold'))}",
        '',
        '## Feature And Calibration Controls',
        '',
        f"- Selected feature count: {len(selected_features)}",
        f"- Selected features: {', '.join(map(str, selected_features[:15])) if selected_features else 'n/a'}",
        f"- Calibration method: {_fmt(calibration.get('method'))}",
        f"- Brier score: {_fmt(metrics.get('brier_score'))}",
        f"- ROC AUC: {_fmt(metrics.get('roc_auc'))}",
        '',
        '## Promotion Boundary',
        '',
        '- Synthetic demo rows are excluded from training and methodology claims.',
        '- Scientist reviews can create remediation actions; they do not automatically retrain or promote this baseline.',
    ]
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate RF methodology baseline report.')
    parser.add_argument('--metadata-json', required=True)
    parser.add_argument('--output', default='docs/RF_Methodology_Baseline.md')
    args = parser.parse_args(argv)

    metadata = json.loads(Path(args.metadata_json).read_text(encoding='utf-8'))
    output = Path(args.output)
    output.write_text(build_rf_methodology_report(metadata), encoding='utf-8')
    print(json.dumps({'output': str(output), 'claim_boundary': 'rf_baseline_not_promoted_authority_model'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
