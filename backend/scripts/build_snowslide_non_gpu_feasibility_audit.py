from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUALIFICATION_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v5-2026-05-18',
)
DEFAULT_DIAGNOSTICS_ROOT = DEFAULT_QUALIFICATION_ROOT / 'diagnostics'
DEFAULT_CANDIDATE_DESIGN_ROOT = DEFAULT_QUALIFICATION_ROOT / 'candidate-design'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required non-GPU feasibility input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'non-GPU feasibility input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _best_candidate(eval_only: dict[str, Any]) -> dict[str, Any]:
    selected = eval_only.get('selected_candidate')
    if isinstance(selected, dict):
        return selected
    candidates = eval_only.get('candidates')
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        return candidates[0]
    return {}


def _decision(
    *,
    manual_outcome: dict[str, Any],
    eval_only: dict[str, Any],
    candidate_design: dict[str, Any],
) -> tuple[str, str]:
    manual_decision = str(manual_outcome.get('decision') or '')
    passing_count = int(eval_only.get('passing_candidate_count') or 0)
    if manual_decision == 'review_incomplete':
        return 'blocked_pending_manual_review', 'Manual scene/label review is incomplete.'
    if manual_decision in {'label_remediation_required', 'terrain_context_required'}:
        return manual_decision, 'Source-label or terrain/SAR context remediation is required before model work.'
    if passing_count > 0:
        return 'non_gpu_pass_found', 'Threshold/postprocess-only recovery found an all-scene candidate.'
    if candidate_design.get('decision') == 'bounded_candidate_design_recommended':
        return (
            'blocked_research_grade_candidate_needed',
            'No all-seven-scene non-GPU recovery met SnowSlide floors; bounded candidate design remains the next step.',
        )
    return 'blocked_research_grade_no_candidate', 'No all-seven-scene non-GPU recovery passed and candidate design is not warranted.'


def _render_markdown(report: dict[str, Any]) -> str:
    best = report.get('best_non_gpu_candidate') if isinstance(report.get('best_non_gpu_candidate'), dict) else {}
    metrics = best.get('metrics') if isinstance(best.get('metrics'), dict) else {}
    return '\n'.join([
        '# SnowSlide Non-GPU Feasibility Audit',
        '',
        f"- Decision: `{report['decision']}`",
        f"- Non-GPU pass found: `{str(report['non_gpu_pass_found']).lower()}`",
        f"- Passing candidate count: `{report['passing_candidate_count']}`",
        f"- GPU run authorized: `{str(report['gpu_run_authorized']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Rationale: {report['rationale']}",
        '',
        '## Best Non-GPU Candidate',
        '',
        '| Threshold | Area | Opening | Precision | Recall | F1 | FPR |',
        '|---:|---:|---:|---:|---:|---:|---:|',
        (
            f"| {best.get('threshold')} | {best.get('postprocess_min_component_area_px')} | "
            f"{best.get('postprocess_opening_size_px')} | {metrics.get('precision')} | "
            f"{metrics.get('recall')} | {metrics.get('f1')} | {metrics.get('false_positive_rate')} |"
        ),
        '',
        'This audit does not change labels, train a model, authorize GPU work, or alter production scoring.',
        '',
    ])


def build_non_gpu_feasibility_audit(
    *,
    acceptance_report: Path,
    eval_only_recovery_report: Path,
    manual_label_review_outcome: Path,
    candidate_design_report: Path,
    output_root: Path,
) -> dict[str, Any]:
    acceptance = _load_json(acceptance_report, label='acceptance_report')
    eval_only = _load_json(eval_only_recovery_report, label='snowslide_eval_only_recovery_report')
    manual_outcome = _load_json(manual_label_review_outcome, label='manual_label_review_outcome')
    candidate_design = _load_json(candidate_design_report, label='candidate_design_report')

    decision, rationale = _decision(
        manual_outcome=manual_outcome,
        eval_only=eval_only,
        candidate_design=candidate_design,
    )
    passing_count = int(eval_only.get('passing_candidate_count') or 0)
    report = {
        'version': 'non_gpu_feasibility_audit_v1',
        'generated_at': _now_iso(),
        'source_inputs': {
            'acceptance_report': str(acceptance_report),
            'snowslide_eval_only_recovery_report': str(eval_only_recovery_report),
            'manual_label_review_outcome': str(manual_label_review_outcome),
            'candidate_design_report': str(candidate_design_report),
        },
        'decision': decision,
        'rationale': rationale,
        'non_gpu_pass_found': decision == 'non_gpu_pass_found',
        'passing_candidate_count': passing_count,
        'bounded_candidate_warranted': decision == 'blocked_research_grade_candidate_needed',
        'avalcd_recheck_required': decision == 'non_gpu_pass_found',
        'fresh_final_holdout_required': decision == 'non_gpu_pass_found',
        'gpu_run_authorized': False,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'best_non_gpu_candidate': _best_candidate(eval_only),
        'snow_slide_acceptance_decision': acceptance.get('decision'),
        'manual_review_decision': manual_outcome.get('decision'),
        'candidate_design_decision': candidate_design.get('decision'),
        'next_checkpoint': (
            'Prepare bounded candidate authorization request.'
            if decision == 'blocked_research_grade_candidate_needed'
            else 'Recheck non-GPU decision rule on AvalCD before any SnowSlide acceptance claim.'
            if decision == 'non_gpu_pass_found'
            else 'Stop before GPU work and resolve blocker.'
        ),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'non_gpu_feasibility_audit.json', report)
    (output_root / 'non_gpu_feasibility_audit.md').write_text(_render_markdown(report), encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build SnowSlide non-GPU feasibility audit from existing diagnostics.')
    parser.add_argument('--acceptance-report', type=Path, default=DEFAULT_QUALIFICATION_ROOT / 'acceptance_report.json')
    parser.add_argument('--eval-only-recovery-report', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'snowslide_eval_only_recovery_report.json')
    parser.add_argument('--manual-label-review-outcome', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'manual_label_review_outcome.json')
    parser.add_argument('--candidate-design-report', type=Path, default=DEFAULT_CANDIDATE_DESIGN_ROOT / 'candidate_design_report.json')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_QUALIFICATION_ROOT / 'phase2-non-gpu-feasibility')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_non_gpu_feasibility_audit(
        acceptance_report=args.acceptance_report,
        eval_only_recovery_report=args.eval_only_recovery_report,
        manual_label_review_outcome=args.manual_label_review_outcome,
        candidate_design_report=args.candidate_design_report,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'non_gpu_pass_found': report['non_gpu_pass_found'],
        'bounded_candidate_warranted': report['bounded_candidate_warranted'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
