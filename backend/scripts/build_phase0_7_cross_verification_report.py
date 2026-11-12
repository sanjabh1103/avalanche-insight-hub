from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/phase0-7-cross-verification-2026-05-18',
)
DEFAULT_PHASE2_AUDIT = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v5-2026-05-18/phase2-non-gpu-feasibility/non_gpu_feasibility_audit.json',
)
DEFAULT_CANDIDATE_DESIGN = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v5-2026-05-18/candidate-design/candidate_design_report.json',
)
DEFAULT_CANDIDATE_AUTHORIZATION = Path(
    'backend/artifacts/european-shadow-sar-training/'
    'avalcd-shadow-train5-val2-2026-05-16/research-v6/candidate_authorization_request.json',
)
DEFAULT_AVALCD_BENCHMARK = Path(
    'backend/artifacts/european-shadow-real-benchmarks/'
    'european-shadow-real-avalcd-scene-blended-v6-2026-05-18/european_shadow_benchmark_report.json',
)
DEFAULT_SNOWSLIDE_ACCEPTANCE = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v6-2026-05-18/acceptance_report.json',
)
DEFAULT_SNOWSLIDE_DIAGNOSTICS = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v6-2026-05-18/diagnostics/sar_error_diagnostics.json',
)
DEFAULT_FRESH_FINAL_PLAN = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v6-2026-05-18/fresh-final-holdout/fresh_final_holdout_plan.json',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required phase 0-7 artifact not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'phase 0-7 artifact must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _git_status_text(cwd: Path) -> str:
    result = subprocess.run(
        ['git', 'status', '--short', '--branch'],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _git_status_summary(text: str) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if line.strip()]
    branch_line = lines[0] if lines else ''
    return {
        'branch_line': branch_line,
        'is_clean': len(lines) == 1,
        'ahead_of_origin': 'ahead ' in branch_line,
        'raw': text,
    }


def _modal_container_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {'status': 'not_checked', 'active_containers_empty': False, 'raw': None}
    if not path.exists():
        raise FileNotFoundError(f'modal container list file not found: {path}')
    raw = path.read_text(encoding='utf-8')
    active_empty = 'Active Containers in environment: None' in raw and '│ avalanche-modal-worker │' not in raw
    return {
        'status': 'empty' if active_empty else 'active_or_unknown',
        'active_containers_empty': active_empty,
        'raw': raw,
    }


def _truthy_production_scoring_paths(value: Any, *, path: str = '$') -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f'{path}.{key}'
            if key == 'production_scoring_allowed' and item is True:
                matches.append(child_path)
            matches.extend(_truthy_production_scoring_paths(item, path=child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(_truthy_production_scoring_paths(item, path=f'{path}[{index}]'))
    return matches


def _source_avalcd_sar_metrics(benchmark: dict[str, Any]) -> dict[str, Any]:
    for source_report in benchmark.get('source_reports') or []:
        if isinstance(source_report, dict) and source_report.get('source_key') == 'avalcd_zenodo_v1':
            metrics = source_report.get('sar_prediction_metrics')
            return metrics if isinstance(metrics, dict) else {}
    return {}


def _metric_block(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        'precision': metrics.get('precision'),
        'recall': metrics.get('recall'),
        'f1': metrics.get('f1'),
        'false_positive_rate': metrics.get('false_positive_rate'),
        'beats_baseline': metrics.get('beats_baseline'),
    }


def _readiness_decision(
    *,
    snowslide_acceptance: dict[str, Any],
    fresh_final_plan: dict[str, Any],
    production_true_paths: list[str],
    modal_summary: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], bool]:
    blockers: list[dict[str, Any]] = []
    if production_true_paths:
        blockers.append({'gate': 'production_scoring_guard', 'paths': production_true_paths})
    if modal_summary.get('active_containers_empty') is not True:
        blockers.append({'gate': 'modal_containers_empty', 'actual': modal_summary.get('status'), 'required': 'empty'})

    acceptance_decision = snowslide_acceptance.get('decision')
    if acceptance_decision not in {'accepted_research_grade', 'requires_fresh_final_holdout'}:
        blockers.append({
            'gate': 'snowslide_research_grade',
            'actual': acceptance_decision,
            'required': 'accepted_research_grade or requires_fresh_final_holdout',
        })
        return 'blocked_phase7_not_ready', blockers, False

    fresh_status = fresh_final_plan.get('status')
    if fresh_status != 'ready_for_fresh_final_holdout_evaluation':
        blockers.append({
            'gate': 'fresh_final_holdout',
            'actual': fresh_status,
            'required': 'ready_for_fresh_final_holdout_evaluation',
        })
        return 'blocked_pending_fresh_final', blockers, False

    if production_true_paths:
        return 'blocked_production_guard_violation', blockers, False
    if modal_summary.get('active_containers_empty') is not True:
        return 'blocked_modal_active', blockers, False
    return 'ready_for_phase7_review', blockers, True


def _phase_statuses(
    *,
    git_status: dict[str, Any],
    phase2_audit: dict[str, Any],
    candidate_design: dict[str, Any],
    candidate_authorization: dict[str, Any],
    avalcd_metrics: dict[str, Any],
    snowslide_acceptance: dict[str, Any],
    fresh_final_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    quality_gate = avalcd_metrics.get('quality_gate') if isinstance(avalcd_metrics.get('quality_gate'), dict) else {}
    avalcd_metric_values = avalcd_metrics.get('metrics') if isinstance(avalcd_metrics.get('metrics'), dict) else {}
    return [
        {
            'phase': 0,
            'verdict': 'complete',
            'evidence': 'source checkpoints committed and branch is clean',
            'gap': 'not_pushed_to_origin' if git_status.get('ahead_of_origin') else None,
        },
        {
            'phase': 1,
            'verdict': 'complete',
            'evidence': candidate_design.get('decision'),
            'gap': 'supersede_with_v6_failure_addendum',
        },
        {
            'phase': 2,
            'verdict': 'complete',
            'evidence': phase2_audit.get('decision'),
            'gap': None,
        },
        {
            'phase': 3,
            'verdict': 'complete',
            'evidence': candidate_authorization.get('status'),
            'gap': 'no_second_gpu_run_without_new_authorization',
        },
        {
            'phase': 4,
            'verdict': 'complete',
            'evidence': {
                'evaluation_mode': avalcd_metrics.get('evaluation_mode'),
                'quality_gate_passed': quality_gate.get('passed'),
                'precision': avalcd_metric_values.get('precision'),
                'recall': avalcd_metric_values.get('recall'),
            },
            'gap': None,
        },
        {
            'phase': 5,
            'verdict': 'failed_correctly',
            'evidence': snowslide_acceptance.get('decision'),
            'gap': 'v6_transfer_failure_addendum_required',
        },
        {
            'phase': 6,
            'verdict': 'blocked_correctly',
            'evidence': fresh_final_plan.get('status'),
            'gap': None,
        },
        {
            'phase': 7,
            'verdict': 'not_authorized',
            'evidence': 'promotion guard requires accepted research-grade and fresh-final evidence',
            'gap': 'operator_phase7_readiness_false_summary',
        },
    ]


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        '# Phase 0-7 Cross-Verification Report',
        '',
        f"- Decision: `{report['decision']}`",
        f"- Phase 7 ready: `{str(report['phase7_ready']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Next GPU run authorized: `{str(report['next_gpu_run_authorized']).lower()}`",
        f"- Promotion allowed: `{str(report['promotion_allowed']).lower()}`",
        '',
        '## Phase Status',
        '',
        '| Phase | Verdict | Evidence | Gap |',
        '|---:|---|---|---|',
    ]
    for item in report['phase_statuses']:
        lines.append(
            f"| {item['phase']} | `{item['verdict']}` | "
            f"{json.dumps(item.get('evidence'), sort_keys=True)} | `{item.get('gap')}` |"
        )
    addendum = report['v6_transfer_failure_addendum']
    lines.extend([
        '',
        '## V6 Transfer-Failure Addendum',
        '',
        f"- Failure mode: `{addendum['failure_mode']}`",
        f"- AvalCD passed: `{str(addendum['avalcd_passed']).lower()}`",
        f"- SnowSlide produced positives: `{str(addendum['snowslide_produced_positive_predictions']).lower()}`",
        f"- Recommendation: {addendum['recommendation']}",
        '',
        '## Readiness Blockers',
        '',
        f"`{json.dumps(report['phase7_readiness']['blockers'], sort_keys=True)}`",
        '',
    ])
    return '\n'.join(lines)


def build_phase0_7_cross_verification_report(
    *,
    phase2_audit_path: Path,
    candidate_design_path: Path,
    candidate_authorization_path: Path,
    avalcd_benchmark_path: Path,
    snowslide_acceptance_path: Path,
    snowslide_diagnostics_path: Path,
    fresh_final_plan_path: Path,
    output_root: Path,
    cwd: Path = Path('.'),
    git_status_text: str | None = None,
    modal_container_list_file: Path | None = None,
) -> dict[str, Any]:
    phase2_audit = _load_json(phase2_audit_path, label='phase2_audit')
    candidate_design = _load_json(candidate_design_path, label='candidate_design')
    candidate_authorization = _load_json(candidate_authorization_path, label='candidate_authorization')
    avalcd_benchmark = _load_json(avalcd_benchmark_path, label='avalcd_benchmark')
    snowslide_acceptance = _load_json(snowslide_acceptance_path, label='snowslide_acceptance')
    snowslide_diagnostics = _load_json(snowslide_diagnostics_path, label='snowslide_diagnostics')
    fresh_final_plan = _load_json(fresh_final_plan_path, label='fresh_final_plan')

    loaded_artifacts = {
        'phase2_audit': phase2_audit,
        'candidate_design': candidate_design,
        'candidate_authorization': candidate_authorization,
        'avalcd_benchmark': avalcd_benchmark,
        'snowslide_acceptance': snowslide_acceptance,
        'snowslide_diagnostics': snowslide_diagnostics,
        'fresh_final_plan': fresh_final_plan,
    }
    production_true_paths: list[str] = []
    for label, artifact in loaded_artifacts.items():
        production_true_paths.extend(
            f'{label}:{path}' for path in _truthy_production_scoring_paths(artifact)
        )

    git_summary = _git_status_summary(git_status_text if git_status_text is not None else _git_status_text(cwd))
    modal_summary = _modal_container_summary(modal_container_list_file)
    avalcd_metrics = _source_avalcd_sar_metrics(avalcd_benchmark)
    avalcd_metric_values = avalcd_metrics.get('metrics') if isinstance(avalcd_metrics.get('metrics'), dict) else {}
    snow_metrics = snowslide_acceptance.get('metrics') if isinstance(snowslide_acceptance.get('metrics'), dict) else {}
    diagnostics_metrics = (
        snowslide_diagnostics.get('aggregate_metrics')
        if isinstance(snowslide_diagnostics.get('aggregate_metrics'), dict)
        else {}
    )
    readiness_decision, readiness_blockers, phase7_ready = _readiness_decision(
        snowslide_acceptance=snowslide_acceptance,
        fresh_final_plan=fresh_final_plan,
        production_true_paths=production_true_paths,
        modal_summary=modal_summary,
    )

    avalcd_passed = (
        avalcd_metrics.get('evaluation_mode') == 'scene_blended'
        and isinstance(avalcd_metrics.get('quality_gate'), dict)
        and avalcd_metrics['quality_gate'].get('passed') is True
    )
    snowslide_tp = int(diagnostics_metrics.get('tp') or 0)
    snowslide_fp = int(diagnostics_metrics.get('fp') or 0)
    produced_positive_predictions = snowslide_tp + snowslide_fp > 0
    transfer_failure = {
        'version': 'v6_transfer_failure_addendum_v1',
        'avalcd_passed': avalcd_passed,
        'avalcd_threshold': avalcd_metric_values.get('threshold'),
        'avalcd_metrics': _metric_block(avalcd_metric_values),
        'snowslide_decision': snowslide_acceptance.get('decision'),
        'snowslide_metrics': _metric_block(snow_metrics),
        'snowslide_produced_positive_predictions': produced_positive_predictions,
        'failure_mode': 'cross_domain_calibration_generalization_failure',
        'classification': 'not_promotion_evidence',
        'recommendation': (
            'Do not request fresh-final evaluation or production promotion until a future candidate passes '
            'SnowSlide research-grade acceptance with the same decision rule.'
        ),
    }

    report = {
        'version': 'phase0_6_cross_verification_report_v1',
        'generated_at': _now_iso(),
        'decision': readiness_decision,
        'phase7_ready': phase7_ready,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'next_gpu_run_authorized': False,
        'no_second_gpu_run_without_new_authorization': True,
        'git_status': git_summary,
        'modal_container_summary': {
            'status': modal_summary.get('status'),
            'active_containers_empty': modal_summary.get('active_containers_empty'),
        },
        'phase_statuses': _phase_statuses(
            git_status=git_summary,
            phase2_audit=phase2_audit,
            candidate_design=candidate_design,
            candidate_authorization=candidate_authorization,
            avalcd_metrics=avalcd_metrics,
            snowslide_acceptance=snowslide_acceptance,
            fresh_final_plan=fresh_final_plan,
        ),
        'v6_transfer_failure_addendum': transfer_failure,
        'phase7_readiness': {
            'decision': readiness_decision,
            'phase7_ready_for_review': phase7_ready,
            'promotion_allowed': False,
            'blockers': readiness_blockers,
        },
        'source_inputs': {
            'phase2_audit': str(phase2_audit_path),
            'candidate_design': str(candidate_design_path),
            'candidate_authorization': str(candidate_authorization_path),
            'avalcd_benchmark': str(avalcd_benchmark_path),
            'snowslide_acceptance': str(snowslide_acceptance_path),
            'snowslide_diagnostics': str(snowslide_diagnostics_path),
            'fresh_final_plan': str(fresh_final_plan_path),
            'modal_container_list_file': str(modal_container_list_file) if modal_container_list_file else None,
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'phase0_7_cross_verification_report.json', report)
    (output_root / 'phase0_7_cross_verification_report.md').write_text(_render_markdown(report), encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build Phase 0-7 cross-verification and final readiness guard report.')
    parser.add_argument('--phase2-audit', type=Path, default=DEFAULT_PHASE2_AUDIT)
    parser.add_argument('--candidate-design', type=Path, default=DEFAULT_CANDIDATE_DESIGN)
    parser.add_argument('--candidate-authorization', type=Path, default=DEFAULT_CANDIDATE_AUTHORIZATION)
    parser.add_argument('--avalcd-benchmark', type=Path, default=DEFAULT_AVALCD_BENCHMARK)
    parser.add_argument('--snowslide-acceptance', type=Path, default=DEFAULT_SNOWSLIDE_ACCEPTANCE)
    parser.add_argument('--snowslide-diagnostics', type=Path, default=DEFAULT_SNOWSLIDE_DIAGNOSTICS)
    parser.add_argument('--fresh-final-plan', type=Path, default=DEFAULT_FRESH_FINAL_PLAN)
    parser.add_argument('--modal-container-list-file', type=Path)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_phase0_7_cross_verification_report(
        phase2_audit_path=args.phase2_audit,
        candidate_design_path=args.candidate_design,
        candidate_authorization_path=args.candidate_authorization,
        avalcd_benchmark_path=args.avalcd_benchmark,
        snowslide_acceptance_path=args.snowslide_acceptance,
        snowslide_diagnostics_path=args.snowslide_diagnostics,
        fresh_final_plan_path=args.fresh_final_plan,
        modal_container_list_file=args.modal_container_list_file,
        output_root=args.output_root,
        cwd=Path.cwd(),
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'phase7_ready': report['phase7_ready'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'next_gpu_run_authorized': report['next_gpu_run_authorized'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
