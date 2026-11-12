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
DEFAULT_AVALCD_BENCHMARK = Path(
    'backend/artifacts/european-shadow-real-benchmarks/'
    'european-shadow-real-avalcd-scene-blended-v5-2026-05-18/'
    'european_shadow_benchmark_report.json',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required candidate-design input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'required candidate-design input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _avalcd_metrics(report: dict[str, Any]) -> dict[str, Any]:
    for source_report in report.get('source_reports') or []:
        if isinstance(source_report, dict) and source_report.get('source_key') == 'avalcd_zenodo_v1':
            metrics = source_report.get('sar_prediction_metrics')
            return metrics if isinstance(metrics, dict) else {}
    return {}


def _decision(
    *,
    manual_outcome: dict[str, Any],
    acceptance_report: dict[str, Any],
    eval_only_recovery: dict[str, Any],
) -> tuple[str, str]:
    manual_decision = str(manual_outcome.get('decision') or '')
    if manual_decision == 'review_incomplete':
        return 'blocked_pending_manual_review', 'Complete manual scene/label review before candidate design.'
    if manual_decision in {'label_remediation_required', 'terrain_context_required'}:
        return manual_decision, 'Resolve source-label or terrain/SAR context issues before model work.'
    if int(eval_only_recovery.get('passing_candidate_count') or 0) > 0:
        return 'eval_only_change_recommended', 'A non-GPU threshold/postprocess candidate exists and should be rechecked before training.'
    if (
        manual_decision == 'labels_valid_model_gap'
        and acceptance_report.get('decision') == 'blocked_research_grade'
        and manual_outcome.get('future_candidate_design_warranted') is True
    ):
        return 'bounded_candidate_design_recommended', (
            'Manual artifact-only review confirms a model-side gap under current truth masks, '
            'and evaluation-only recovery did not meet SnowSlide floors.'
        )
    return 'no_further_model_work', 'Evidence does not justify another model candidate.'


def _candidate_design(decision: str) -> dict[str, Any] | None:
    if decision != 'bounded_candidate_design_recommended':
        return None
    return {
        'version': 'candidate_authorization_request_v1',
        'status': 'design_only_not_authorized',
        'candidate_model_version': 'avalcd_swinunet_tiny_diff_research_gate_shadow_v6_design_only',
        'hypothesis': (
            'Recover SnowSlide recall and F1 while preserving precision by addressing model-side '
            'false-negative misses and false-positive terrain texture errors identified in Nuuk and Pish scenes.'
        ),
        'proposed_changes': [
            'Use hard-negative sampling from pish_20230221 and nuuk_20210411 false-positive components.',
            'Use false-negative-focused sampling from nuuk_20160413 and nuuk_20210411 labeled truth components.',
            'Keep scene_blended evaluation and the existing SnowSlide research-grade floors unchanged.',
            'Do not alter public scoring, label truth, or promotion rules.',
        ],
        'suggested_budget_cap': {
            'max_gpu_runs': 1,
            'max_wait_seconds': 3600,
            'cancel_on_timeout': True,
            'modal_profile': 'sanjabh1103_limit30',
            'zero_warm_containers_required': True,
        },
        'stop_criteria': [
            'Stop if AvalCD scene_blended precision < 0.60 or recall < 0.50.',
            'Stop if SnowSlide precision < 0.70, recall < 0.50, F1 < 0.60, or FPR > 0.002.',
            'Stop after one bounded run even if metrics improve but remain below floors.',
            'Require a fresh final holdout before any production discussion if SnowSlide influenced candidate selection.',
        ],
        'gpu_run_authorized': False,
        'requires_explicit_operator_approval': True,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    snowslide = report['evidence']['snowslide_metrics']
    avalcd = report['evidence']['avalcd_metrics']
    lines = [
        '# SnowSlide Candidate Design Report',
        '',
        f"- Decision: `{report['decision']}`",
        f"- GPU run authorized: `{str(report['gpu_run_authorized']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Promotion allowed: `{str(report['promotion_allowed']).lower()}`",
        f"- Rationale: {report['rationale']}",
        '',
        '## Evidence',
        '',
        '| Surface | Precision | Recall | F1 | FPR | Decision |',
        '|---|---:|---:|---:|---:|---|',
        (
            f"| AvalCD scene-blended v5 | {avalcd.get('precision')} | {avalcd.get('recall')} | "
            f"{avalcd.get('f1')} | {avalcd.get('false_positive_rate')} | {report['evidence']['avalcd_quality_gate'].get('passed')} |"
        ),
        (
            f"| SnowSlide v5 | {snowslide.get('precision')} | {snowslide.get('recall')} | "
            f"{snowslide.get('f1')} | {snowslide.get('false_positive_rate')} | "
            f"{report['evidence']['snowslide_acceptance_decision']} |"
        ),
        '',
        '## Next Checkpoint',
        '',
        report['next_checkpoint'],
        '',
    ]
    if report.get('candidate_design'):
        lines.extend([
            '## Candidate Design',
            '',
            f"- Candidate: `{report['candidate_design']['candidate_model_version']}`",
            f"- Status: `{report['candidate_design']['status']}`",
            f"- Hypothesis: {report['candidate_design']['hypothesis']}",
            '',
            'No GPU run is authorized by this report.',
            '',
        ])
    return '\n'.join(lines)


def build_candidate_design_report(
    *,
    manual_label_review_outcome: Path,
    next_candidate_decision: Path,
    acceptance_report: Path,
    eval_only_recovery_report: Path,
    avalcd_benchmark_report: Path,
    output_root: Path,
) -> dict[str, Any]:
    manual_outcome = _load_json(manual_label_review_outcome, label='manual_label_review_outcome')
    next_decision = _load_json(next_candidate_decision, label='next_candidate_decision')
    acceptance = _load_json(acceptance_report, label='acceptance_report')
    eval_only = _load_json(eval_only_recovery_report, label='snowslide_eval_only_recovery_report')
    avalcd_report = _load_json(avalcd_benchmark_report, label='avalcd_benchmark_report')
    avalcd = _avalcd_metrics(avalcd_report)
    avalcd_values = avalcd.get('metrics') if isinstance(avalcd.get('metrics'), dict) else {}
    avalcd_gate = avalcd.get('quality_gate') if isinstance(avalcd.get('quality_gate'), dict) else {}

    decision, rationale = _decision(
        manual_outcome=manual_outcome,
        acceptance_report=acceptance,
        eval_only_recovery=eval_only,
    )
    report = {
        'version': 'candidate_design_report_v1',
        'generated_at': _now_iso(),
        'source_inputs': {
            'manual_label_review_outcome': str(manual_label_review_outcome),
            'next_candidate_decision': str(next_candidate_decision),
            'acceptance_report': str(acceptance_report),
            'snowslide_eval_only_recovery_report': str(eval_only_recovery_report),
            'avalcd_benchmark_report': str(avalcd_benchmark_report),
        },
        'decision': decision,
        'rationale': rationale,
        'gpu_run_authorized': False,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'candidate_design': _candidate_design(decision),
        'evidence': {
            'manual_review_decision': manual_outcome.get('decision'),
            'manual_review_component_counts': manual_outcome.get('component_decision_counts'),
            'manual_review_future_candidate_design_warranted': manual_outcome.get('future_candidate_design_warranted'),
            'previous_candidate_recommendation': next_decision.get('recommendation'),
            'snowslide_acceptance_decision': acceptance.get('decision'),
            'snowslide_acceptance_blockers': acceptance.get('blockers'),
            'snowslide_metrics': acceptance.get('metrics'),
            'eval_only_decision': eval_only.get('decision'),
            'eval_only_passing_candidate_count': eval_only.get('passing_candidate_count'),
            'avalcd_evaluation_mode': avalcd.get('evaluation_mode'),
            'avalcd_quality_gate': avalcd_gate,
            'avalcd_metrics': {
                'precision': avalcd_values.get('precision'),
                'recall': avalcd_values.get('recall'),
                'f1': avalcd_values.get('f1'),
                'false_positive_rate': avalcd_values.get('false_positive_rate'),
                'threshold': avalcd_values.get('threshold'),
                'postprocess_min_component_area_px': avalcd_values.get('postprocess_min_component_area_px'),
            },
        },
        'next_checkpoint': {
            'blocked_pending_manual_review': 'Complete manual review before any candidate design.',
            'label_remediation_required': 'Prepare a label/source remediation checkpoint.',
            'terrain_context_required': 'Prepare terrain/SAR context review before candidate design.',
            'eval_only_change_recommended': 'Rebuild SnowSlide and AvalCD reports with the passing non-GPU decision rule.',
            'bounded_candidate_design_recommended': 'Prepare a separate candidate authorization request; do not launch GPU work from this report.',
            'no_further_model_work': 'Stop SAR candidate work and report blocked state.',
        }[decision],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'candidate_design_report.json', report)
    (output_root / 'candidate_design_report.md').write_text(_render_markdown(report), encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a no-GPU SnowSlide SAR candidate design dossier.')
    parser.add_argument('--manual-label-review-outcome', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'manual_label_review_outcome.json')
    parser.add_argument('--next-candidate-decision', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'next_candidate_decision.json')
    parser.add_argument('--acceptance-report', type=Path, default=DEFAULT_QUALIFICATION_ROOT / 'acceptance_report.json')
    parser.add_argument('--eval-only-recovery-report', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'snowslide_eval_only_recovery_report.json')
    parser.add_argument('--avalcd-benchmark-report', type=Path, default=DEFAULT_AVALCD_BENCHMARK)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_QUALIFICATION_ROOT / 'candidate-design')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_candidate_design_report(
        manual_label_review_outcome=args.manual_label_review_outcome,
        next_candidate_decision=args.next_candidate_decision,
        acceptance_report=args.acceptance_report,
        eval_only_recovery_report=args.eval_only_recovery_report,
        avalcd_benchmark_report=args.avalcd_benchmark_report,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'gpu_run_authorized': report['gpu_run_authorized'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
