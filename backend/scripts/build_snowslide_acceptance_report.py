from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.common.sar_acceptance_policy import (
    evaluate_snowslide_research_grade,
    summarize_materialization_results,
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'JSON artifact must contain an object: {path}')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _gate_names(report: dict[str, Any], key: str) -> str:
    values = [str(item.get('gate')) for item in report.get(key, []) if isinstance(item, dict)]
    return ', '.join(values) if values else 'none'


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = report.get('metrics') if isinstance(report.get('metrics'), dict) else {}
    floors = report.get('floors') if isinstance(report.get('floors'), dict) else {}
    coverage = report.get('coverage') if isinstance(report.get('coverage'), dict) else {}
    materialization = report.get('materialization_summary') if isinstance(report.get('materialization_summary'), dict) else {}
    lines = [
        '# SnowSlide Research-Grade Acceptance Report',
        '',
        f"- Policy version: `{report.get('policy_version')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Accepted research grade: `{report.get('accepted_research_grade')}`",
        f"- Requires fresh final hold-out: `{report.get('requires_fresh_final_holdout')}`",
        f"- Bounded candidate warranted: `{report.get('bounded_candidate_warranted')}`",
        f"- Production scoring allowed: `{report.get('production_scoring_allowed')}`",
        '',
        '## Metrics',
        '',
        '| Metric | Actual | Required |',
        '|---|---:|---:|',
        f"| Precision | {metrics.get('precision')} | >= {floors.get('precision')} |",
        f"| Recall | {metrics.get('recall')} | >= {floors.get('recall')} |",
        f"| F1 | {metrics.get('f1')} | >= {floors.get('f1')} |",
        f"| False-positive rate | {metrics.get('false_positive_rate')} | <= {floors.get('false_positive_rate')} |",
        '',
        '## Coverage',
        '',
        f"- Scene count: `{coverage.get('scene_count')}`",
        f"- Missing scene IDs: `{coverage.get('missing_scene_ids')}`",
        f"- Materialized masks: `{materialization.get('mask_asset_ref_count')}`",
        f"- Materialization missing scene IDs: `{materialization.get('missing_scene_ids')}`",
        '',
        '## Blockers',
        '',
        f"- Gates: `{_gate_names(report, 'blockers')}`",
        '',
        '## Warnings',
        '',
        f"- Gates: `{_gate_names(report, 'warnings')}`",
        '',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')


def build_report(
    *,
    snow_report_path: Path,
    avalcd_benchmark_report_path: Path,
    materialization_result_dir: Path,
    qualification_set_used_for_model_selection: bool = False,
) -> dict[str, Any]:
    snow_report = _load_json(snow_report_path)
    avalcd_report = _load_json(avalcd_benchmark_report_path)
    materialization_summary = summarize_materialization_results(materialization_result_dir)
    return evaluate_snowslide_research_grade(
        snow_report,
        avalcd_benchmark_report=avalcd_report,
        materialization_summary=materialization_summary,
        qualification_set_used_for_model_selection=qualification_set_used_for_model_selection,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a SnowSlide research-grade SAR acceptance report')
    parser.add_argument('--snow-report', type=Path, required=True, help='SnowSlide evaluate-release dry-run result JSON')
    parser.add_argument('--avalcd-benchmark-report', type=Path, required=True, help='AvalCD scene-blended benchmark report JSON')
    parser.add_argument('--materialization-result-dir', type=Path, required=True, help='Directory containing per-scene sar_segment_result.json files')
    parser.add_argument('--qualification-set-used-for-model-selection', action='store_true')
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-markdown', type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        snow_report_path=args.snow_report,
        avalcd_benchmark_report_path=args.avalcd_benchmark_report,
        materialization_result_dir=args.materialization_result_dir,
        qualification_set_used_for_model_selection=args.qualification_set_used_for_model_selection,
    )
    _write_json(args.output_json, report)
    if args.output_markdown:
        _write_markdown(args.output_markdown, report)
    print(json.dumps({
        'status': 'ok',
        'decision': report.get('decision'),
        'accepted_research_grade': report.get('accepted_research_grade'),
        'bounded_candidate_warranted': report.get('bounded_candidate_warranted'),
        'output_json': str(args.output_json),
        'output_markdown': str(args.output_markdown) if args.output_markdown else None,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
