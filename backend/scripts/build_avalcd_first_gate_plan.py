from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TRAINING_ROOT = Path(
    'backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required AvalCD first-gate input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'AvalCD first-gate input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _training_result_checkpoint(training_result: dict[str, Any]) -> str | None:
    for key in ('model_checkpoint_path', 'checkpoint_path'):
        value = training_result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sar_metrics(evaluation_report: dict[str, Any]) -> dict[str, Any]:
    if isinstance(evaluation_report.get('metrics'), dict):
        return evaluation_report['metrics']
    if isinstance(evaluation_report.get('validation_metrics'), dict):
        return evaluation_report['validation_metrics']
    return {}


def _quality_gate(evaluation_report: dict[str, Any]) -> dict[str, Any]:
    gate = evaluation_report.get('quality_gate')
    if isinstance(gate, dict):
        return gate
    if 'quality_gate_passed' in evaluation_report:
        return {
            'passed': bool(evaluation_report.get('quality_gate_passed')),
            'source': 'quality_gate_passed',
        }
    return {}


def _build_evaluation_request(
    *,
    training_result: dict[str, Any],
    template_training_request: dict[str, Any],
    checkpoint_path: str,
) -> dict[str, Any]:
    return {
        'training_manifest_path': template_training_request.get('training_manifest_path'),
        'checkpoint_path': checkpoint_path,
        'source_key': template_training_request.get('source_key') or 'avalcd_zenodo_v1',
        'license_review_id': template_training_request.get('license_review_id'),
        'candidate_model_version': training_result.get('candidate_model_version') or template_training_request.get('candidate_model_version'),
        'model_family': training_result.get('model_family') or template_training_request.get('model_family') or 'swinunet_tiny_diff',
        'patch_size': int(template_training_request.get('patch_size') or 128),
        'stride': int(template_training_request.get('stride') or 64),
        'batch_size': int(template_training_request.get('batch_size') or 8),
        'loss': template_training_request.get('loss') or 'focal_tversky',
        'f_beta': float(template_training_request.get('f_beta') or 0.75),
        'precision_floor': 0.6,
        'postprocess_recall_floor': 0.5,
        'threshold_grid': template_training_request.get('threshold_grid') or [0.985, 0.988, 0.99, 0.992, 0.994, 0.996, 0.998, 0.999],
        'postprocess_min_component_area_px': int(template_training_request.get('postprocess_min_component_area_px') or 64),
        'postprocess_opening_size_px': int(template_training_request.get('postprocess_opening_size_px') or 0),
        'postprocess_apply_to_threshold_selection': True,
        'export_validation_prediction_artifact': True,
        'evaluation_mode': 'scene_blended',
    }


def _render_markdown(report: dict[str, Any]) -> str:
    metrics = report.get('metrics') if isinstance(report.get('metrics'), dict) else {}
    return '\n'.join([
        '# AvalCD First Gate',
        '',
        f"- Status: `{report['status']}`",
        f"- Candidate: `{report.get('candidate_model_version')}`",
        f"- Evaluation mode required: `scene_blended`",
        f"- Gate passed: `{str(report['avalcd_first_gate_passed']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        '',
        '| Precision | Recall | F1 | FPR |',
        '|---:|---:|---:|---:|',
        f"| {metrics.get('precision')} | {metrics.get('recall')} | {metrics.get('f1')} | {metrics.get('false_positive_rate')} |",
        '',
        report['next_checkpoint'],
        '',
    ])


def build_avalcd_first_gate_plan(
    *,
    candidate_authorization_request: Path,
    template_training_request: Path,
    output_root: Path,
    training_result: Path | None = None,
    evaluation_report: Path | None = None,
) -> dict[str, Any]:
    auth = _load_json(candidate_authorization_request, label='candidate_authorization_request')
    template_request = _load_json(template_training_request, label='template_training_request')
    training_payload = _load_json(training_result, label='training_result') if training_result is not None and training_result.exists() else {}
    evaluation_payload = _load_json(evaluation_report, label='evaluation_report') if evaluation_report is not None and evaluation_report.exists() else {}

    checkpoint_path = _training_result_checkpoint(training_payload)
    metrics = _sar_metrics(evaluation_payload)
    gate = _quality_gate(evaluation_payload)
    evaluation_mode = evaluation_payload.get('evaluation_mode')
    if not checkpoint_path:
        status = 'blocked_pending_candidate_artifact'
        passed = False
        next_checkpoint = 'Run the authorized bounded candidate before AvalCD scene-blended evaluation.'
        evaluation_request = None
    elif not evaluation_payload:
        status = 'ready_for_scene_blended_evaluation'
        passed = False
        next_checkpoint = 'Run the generated evaluate_sar_checkpoint_request.json through the scene-blended evaluator.'
        evaluation_request = _build_evaluation_request(
            training_result=training_payload,
            template_training_request=template_request,
            checkpoint_path=checkpoint_path,
        )
    else:
        precision = float(metrics.get('precision') or 0.0)
        recall = float(metrics.get('recall') or 0.0)
        mode_ok = evaluation_mode == 'scene_blended'
        gate_ok = bool(gate.get('passed', precision >= 0.6 and recall >= 0.5))
        passed = mode_ok and gate_ok and precision >= 0.6 and recall >= 0.5
        status = 'passed_avalcd_first_gate' if passed else 'failed_avalcd_first_gate'
        next_checkpoint = (
            'Proceed to Phase 5 SnowSlide qualification with the same selected rule.'
            if passed
            else 'Stop before SnowSlide; candidate failed the AvalCD scene-blended first gate.'
        )
        evaluation_request = None

    report = {
        'version': 'avalcd_first_gate_plan_v1',
        'generated_at': _now_iso(),
        'source_inputs': {
            'candidate_authorization_request': str(candidate_authorization_request),
            'template_training_request': str(template_training_request),
            'training_result': str(training_result) if training_result else None,
            'evaluation_report': str(evaluation_report) if evaluation_report else None,
        },
        'status': status,
        'candidate_model_version': auth.get('candidate_model_version') or training_payload.get('candidate_model_version'),
        'checkpoint_path': checkpoint_path,
        'evaluation_mode': evaluation_mode,
        'required_evaluation_mode': 'scene_blended',
        'precision_floor': 0.6,
        'recall_floor': 0.5,
        'metrics': metrics,
        'quality_gate': gate,
        'avalcd_first_gate_passed': passed,
        'snow_slide_materialization_allowed': passed,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'next_checkpoint': next_checkpoint,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'avalcd_first_gate_plan.json', report)
    (output_root / 'avalcd_first_gate_plan.md').write_text(_render_markdown(report), encoding='utf-8')
    if evaluation_request is not None:
        _write_json(output_root / 'evaluate_sar_checkpoint_request.json', evaluation_request)
        report['evaluation_request_path'] = str(output_root / 'evaluate_sar_checkpoint_request.json')
        _write_json(output_root / 'avalcd_first_gate_plan.json', report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build or check the AvalCD scene-blended first gate for a SAR candidate.')
    parser.add_argument('--candidate-authorization-request', type=Path, default=DEFAULT_TRAINING_ROOT / 'research-v6' / 'candidate_authorization_request.json')
    parser.add_argument('--template-training-request', type=Path, default=DEFAULT_TRAINING_ROOT / 'research-v6' / 'train_sar_unet_request.json')
    parser.add_argument('--training-result', type=Path)
    parser.add_argument('--evaluation-report', type=Path)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_TRAINING_ROOT / 'research-v6' / 'avalcd-first-gate')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_avalcd_first_gate_plan(
        candidate_authorization_request=args.candidate_authorization_request,
        template_training_request=args.template_training_request,
        training_result=args.training_result,
        evaluation_report=args.evaluation_report,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'gate_status': report['status'],
        'avalcd_first_gate_passed': report['avalcd_first_gate_passed'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0 if report['status'] != 'failed_avalcd_first_gate' else 1


if __name__ == '__main__':
    raise SystemExit(main())
