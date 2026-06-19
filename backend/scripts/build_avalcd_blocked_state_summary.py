from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SUMMARY_VERSION = 'avalcd_blocked_state_summary_v1'
DEFAULT_MODAL_CLI = '.venv/bin/modal'


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'expected JSON object at {path}')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidates = summary['candidates']
    lines = [
        '# AvalCD Blocked-State Qualification Summary',
        '',
        f'- Generated: `{summary["generated_at"]}`',
        f'- Final decision: `{summary["final_decision"]}`',
        f'- SnowSlide materialization allowed: `{str(summary["snow_slide_materialization_allowed"]).lower()}`',
        f'- Production scoring allowed: `{str(summary["production_scoring_allowed"]).lower()}`',
        f'- Modal containers: `{summary["modal_containers"]["status"]}`',
        '',
        '| Candidate | Evaluation mode | Precision | Recall | F1 | Gate | Result |',
        '|---|---|---:|---:|---:|---|---|',
    ]
    for candidate in candidates:
        metrics = candidate['metrics']
        lines.append(
            '| {label} | `{mode}` | `{precision:.4f}` | `{recall:.4f}` | `{f1:.4f}` | `{gate}` | {summary} |'.format(
                label=candidate['label'],
                mode=candidate['evaluation_mode'],
                precision=float(metrics['precision']),
                recall=float(metrics['recall']),
                f1=float(metrics['f1']),
                gate=candidate['blocked_gate'],
                summary=candidate['gate_summary'],
            )
        )
    lines.extend([
        '',
        '## SnowSlide',
        '',
        f'- Materialization result: `{summary["snow_slide_materialization"]["status"]}`',
        f'- Materialization reason: `{summary["snow_slide_materialization"].get("reason") or ""}`',
        '',
        '## Violations',
        '',
    ])
    if summary['violations']:
        lines.extend(f'- {item}' for item in summary['violations'])
    else:
        lines.append('- None')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _avalcd_source_report(report: dict[str, Any]) -> dict[str, Any]:
    source_reports = report.get('source_reports')
    if not isinstance(source_reports, list):
        raise ValueError('benchmark report is missing source_reports[]')
    for item in source_reports:
        if isinstance(item, dict) and item.get('source_key') == 'avalcd_zenodo_v1':
            return item
    raise ValueError('benchmark report does not contain source_key=avalcd_zenodo_v1')


def _classify_gate(precision_met: bool, recall_met: bool, passed: bool) -> str:
    if passed and precision_met and recall_met:
        return 'passed_both_floors'
    if precision_met and not recall_met:
        return 'precision_passed_recall_failed'
    if recall_met and not precision_met:
        return 'recall_passed_precision_failed'
    return 'precision_and_recall_failed'


def _candidate_from_report(label: str, path: Path, report: dict[str, Any], violations: list[str]) -> dict[str, Any]:
    if report.get('production_scoring_allowed') is not False:
        violations.append(f'{label}: production_scoring_allowed must be false')
    promotion = report.get('promotion_gate_report') if isinstance(report.get('promotion_gate_report'), dict) else {}
    if promotion.get('decision') != 'blocked_shadow_only':
        violations.append(f'{label}: promotion decision must remain blocked_shadow_only')

    source_report = _avalcd_source_report(report)
    metrics_report = source_report.get('sar_prediction_metrics') if isinstance(source_report.get('sar_prediction_metrics'), dict) else {}
    evaluation_mode = str(metrics_report.get('evaluation_mode') or '').strip()
    if evaluation_mode != 'scene_blended':
        violations.append(f'{label}: evaluation_mode must be scene_blended')

    metrics = metrics_report.get('metrics') if isinstance(metrics_report.get('metrics'), dict) else {}
    quality_gate = metrics_report.get('quality_gate') if isinstance(metrics_report.get('quality_gate'), dict) else {}
    precision_met = quality_gate.get('precision_floor_met') is True
    recall_met = quality_gate.get('recall_floor_met') is True
    passed = quality_gate.get('passed') is True
    gate_summary = _classify_gate(precision_met, recall_met, passed)
    allowed = evaluation_mode == 'scene_blended' and passed and precision_met and recall_met
    return {
        'label': label,
        'benchmark_report_path': str(path),
        'model_version': metrics_report.get('model_version'),
        'evaluation_mode': evaluation_mode,
        'threshold': metrics_report.get('threshold'),
        'metrics': {
            'precision': float(metrics.get('precision') or 0.0),
            'recall': float(metrics.get('recall') or 0.0),
            'f1': float(metrics.get('f1') or 0.0),
            'iou': float(metrics.get('iou') or 0.0),
            'false_positive_rate': float(metrics.get('false_positive_rate') or 0.0),
        },
        'quality_gate_passed': passed,
        'precision_floor_met': precision_met,
        'recall_floor_met': recall_met,
        'blocked_gate': quality_gate.get('blocked_gate'),
        'gate_summary': gate_summary,
        'snow_slide_materialization_allowed': allowed,
    }


def _modal_container_status_from_output(output: str) -> dict[str, Any]:
    empty = 'Active Containers in environment: None' in output
    return {
        'status': 'empty' if empty else 'active_or_unknown',
        'active_containers_empty': empty,
        'raw_output': output,
    }


def _run_modal_container_list(*, modal_profile: str, modal_cli: str) -> dict[str, Any]:
    env = {**os.environ, 'MODAL_PROFILE': modal_profile}
    completed = subprocess.run(
        [modal_cli, 'container', 'list'],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    output = '\n'.join(part for part in (completed.stdout, completed.stderr) if part)
    status = _modal_container_status_from_output(output)
    status.update({
        'command': f'MODAL_PROFILE={modal_profile} {modal_cli} container list',
        'returncode': completed.returncode,
    })
    if completed.returncode != 0:
        status['status'] = 'check_failed'
        status['active_containers_empty'] = False
    return status


def build_avalcd_blocked_state_summary(
    *,
    v3_benchmark_report: Path,
    v4_benchmark_report: Path,
    snow_materialization_result: Path,
    modal_profile: str | None = None,
    modal_cli: str = DEFAULT_MODAL_CLI,
    modal_container_list_output: Path | None = None,
) -> dict[str, Any]:
    violations: list[str] = []
    candidates = [
        _candidate_from_report('v3', v3_benchmark_report, _load_json(v3_benchmark_report), violations),
        _candidate_from_report('v4', v4_benchmark_report, _load_json(v4_benchmark_report), violations),
    ]
    any_allowed = any(candidate['snow_slide_materialization_allowed'] for candidate in candidates)
    if any_allowed:
        violations.append('blocked-state closure expected no current AvalCD candidate to pass both floors')

    snow_result = _load_json(snow_materialization_result)
    snow_status = str(snow_result.get('status') or '').strip()
    snow_blocked = snow_status == 'blocked_prediction_materialization'
    if not snow_blocked:
        violations.append('SnowSlide materialization result must remain blocked_prediction_materialization')

    if modal_container_list_output is not None:
        modal_status = _modal_container_status_from_output(modal_container_list_output.expanduser().read_text(encoding='utf-8'))
    elif modal_profile:
        modal_status = _run_modal_container_list(modal_profile=modal_profile, modal_cli=modal_cli)
    else:
        modal_status = {
            'status': 'not_checked',
            'active_containers_empty': None,
        }
        violations.append('Modal active container check must be provided at closeout')
    if modal_status.get('active_containers_empty') is False:
        violations.append('Modal active containers must be empty at closeout')

    return {
        'version': SUMMARY_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'final_decision': 'blocked_shadow_only',
        'production_scoring_allowed': False,
        'avalcd_first_gate_required': True,
        'training_freeze': True,
        'snow_slide_materialization_allowed': False,
        'snow_slide_dry_run_rerun_allowed': False,
        'candidates': candidates,
        'snow_slide_materialization': {
            'path': str(snow_materialization_result),
            'status': snow_status,
            'blocked': snow_blocked,
            'reason': snow_result.get('reason') or snow_result.get('error'),
        },
        'modal_containers': modal_status,
        'violations': violations,
        'status': 'ok' if not violations else 'failed',
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build the AvalCD/SnowSlide blocked-state qualification summary.')
    parser.add_argument('--v3-benchmark-report', type=Path, required=True)
    parser.add_argument('--v4-benchmark-report', type=Path, required=True)
    parser.add_argument('--snow-materialization-result', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-markdown', type=Path, required=True)
    parser.add_argument('--modal-profile')
    parser.add_argument('--modal-cli', default=DEFAULT_MODAL_CLI)
    parser.add_argument('--modal-container-list-output', type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = build_avalcd_blocked_state_summary(
        v3_benchmark_report=args.v3_benchmark_report,
        v4_benchmark_report=args.v4_benchmark_report,
        snow_materialization_result=args.snow_materialization_result,
        modal_profile=args.modal_profile,
        modal_cli=args.modal_cli,
        modal_container_list_output=args.modal_container_list_output,
    )
    _write_json(args.output_json, summary)
    _write_markdown(args.output_markdown, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary['violations']:
        for violation in summary['violations']:
            print(violation, file=sys.stderr)
    return 0 if summary['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
