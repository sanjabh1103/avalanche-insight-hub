from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUALIFICATION_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v5-2026-05-18',
)
DEFAULT_TRAINING_ROOT = Path(
    'backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required candidate authorization input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'candidate authorization input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _candidate_request_from_template(template: dict[str, Any], *, candidate_model_version: str) -> dict[str, Any]:
    request = deepcopy(template)
    request['candidate_model_version'] = candidate_model_version
    request['model_family'] = request.get('model_family') or 'swinunet_tiny_diff'
    request['materialized_dataset_root'] = '/tmp/avalcd-shadow-train5-val2-v6'
    request['initial_checkpoint_path'] = request.get('model_checkpoint_path') or '/artifacts/20260518T053032Z/sar_model.pt'
    request['epochs'] = 4
    request['patience'] = 2
    request['learning_rate'] = 0.00001
    request['negative_ratio'] = int(request.get('negative_ratio') or 5)
    request['focal_tversky_alpha'] = 0.45
    request['focal_tversky_beta'] = 0.55
    request['focal_tversky_gamma'] = 1.33
    request['f_beta'] = 0.75
    request['precision_floor'] = 0.6
    request['postprocess_recall_floor'] = 0.5
    request['postprocess_apply_to_threshold_selection'] = True
    request['postprocess_min_component_area_px'] = 64
    request['postprocess_opening_size_px'] = 0
    request['threshold_grid'] = [0.985, 0.988, 0.99, 0.992, 0.994, 0.996, 0.998, 0.999]
    request['export_validation_prediction_artifact'] = True
    return request


def _render_markdown(report: dict[str, Any]) -> str:
    return '\n'.join([
        '# SAR Candidate Authorization Request',
        '',
        f"- Status: `{report['status']}`",
        f"- Candidate: `{report['candidate_model_version']}`",
        f"- GPU run authorized: `{str(report['gpu_run_authorized']).lower()}`",
        f"- Modal profile: `{report['modal_profile']}`",
        f"- Max wait seconds: `{report['max_wait_seconds']}`",
        f"- Cancel on timeout: `{str(report['cancel_on_timeout']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        '',
        'This request authorizes at most one bounded Modal GPU run and does not authorize promotion.',
        '',
    ])


def build_candidate_authorization_request(
    *,
    non_gpu_feasibility_audit: Path,
    candidate_design_report: Path,
    template_training_request: Path,
    output_root: Path,
    authorize_gpu: bool = False,
    modal_profile: str = 'sanjabh1103_limit30',
    candidate_model_version: str = 'avalcd_swinunet_tiny_diff_research_gate_shadow_20260518_v6',
    max_wait_seconds: int = 3600,
) -> dict[str, Any]:
    audit = _load_json(non_gpu_feasibility_audit, label='non_gpu_feasibility_audit')
    design = _load_json(candidate_design_report, label='candidate_design_report')
    template_request = _load_json(template_training_request, label='template_training_request')

    if audit.get('decision') == 'non_gpu_pass_found':
        status = 'blocked_non_gpu_candidate_available'
        gpu_allowed = False
        reason = 'A non-GPU passing candidate exists; recheck AvalCD before training.'
        train_request = None
    elif audit.get('decision') != 'blocked_research_grade_candidate_needed':
        status = 'blocked_missing_candidate_prerequisite'
        gpu_allowed = False
        reason = f"Phase 2 decision does not authorize candidate preparation: {audit.get('decision')}"
        train_request = None
    elif design.get('decision') != 'bounded_candidate_design_recommended':
        status = 'blocked_candidate_design_not_recommended'
        gpu_allowed = False
        reason = f"Candidate design decision is not bounded_candidate_design_recommended: {design.get('decision')}"
        train_request = None
    else:
        status = 'authorized_for_single_bounded_gpu_run' if authorize_gpu else 'awaiting_explicit_operator_approval'
        gpu_allowed = bool(authorize_gpu)
        reason = 'User explicitly authorized one bounded GPU run.' if authorize_gpu else 'Awaiting explicit operator approval.'
        train_request = _candidate_request_from_template(
            template_request,
            candidate_model_version=candidate_model_version,
        )

    report = {
        'version': 'candidate_authorization_request_v1',
        'generated_at': _now_iso(),
        'status': status,
        'reason': reason,
        'candidate_model_version': candidate_model_version,
        'gpu_run_authorized': gpu_allowed,
        'requires_explicit_operator_approval': not gpu_allowed,
        'max_gpu_runs': 1,
        'max_wait_seconds': int(max_wait_seconds),
        'cancel_on_timeout': True,
        'modal_profile': modal_profile,
        'zero_warm_containers_required': True,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'source_inputs': {
            'non_gpu_feasibility_audit': str(non_gpu_feasibility_audit),
            'candidate_design_report': str(candidate_design_report),
            'template_training_request': str(template_training_request),
        },
        'phase2_decision': audit.get('decision'),
        'candidate_design_decision': design.get('decision'),
        'train_request_path': str(output_root / 'train_sar_unet_request.json') if train_request is not None else None,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'candidate_authorization_request.json', report)
    (output_root / 'candidate_authorization_request.md').write_text(_render_markdown(report), encoding='utf-8')
    if train_request is not None:
        _write_json(output_root / 'train_sar_unet_request.json', train_request)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build bounded SAR candidate authorization and training request artifacts.')
    parser.add_argument('--non-gpu-feasibility-audit', type=Path, default=DEFAULT_QUALIFICATION_ROOT / 'phase2-non-gpu-feasibility' / 'non_gpu_feasibility_audit.json')
    parser.add_argument('--candidate-design-report', type=Path, default=DEFAULT_QUALIFICATION_ROOT / 'candidate-design' / 'candidate_design_report.json')
    parser.add_argument('--template-training-request', type=Path, default=DEFAULT_TRAINING_ROOT / 'research-v5' / 'train_sar_unet_request.json')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_TRAINING_ROOT / 'research-v6')
    parser.add_argument('--authorize-gpu', action='store_true')
    parser.add_argument('--modal-profile', default='sanjabh1103_limit30')
    parser.add_argument('--candidate-model-version', default='avalcd_swinunet_tiny_diff_research_gate_shadow_20260518_v6')
    parser.add_argument('--max-wait-seconds', type=int, default=3600)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_candidate_authorization_request(
        non_gpu_feasibility_audit=args.non_gpu_feasibility_audit,
        candidate_design_report=args.candidate_design_report,
        template_training_request=args.template_training_request,
        output_root=args.output_root,
        authorize_gpu=args.authorize_gpu,
        modal_profile=args.modal_profile,
        candidate_model_version=args.candidate_model_version,
        max_wait_seconds=args.max_wait_seconds,
    )
    print(json.dumps({
        'status': 'ok',
        'authorization_status': report['status'],
        'gpu_run_authorized': report['gpu_run_authorized'],
        'train_request_path': report['train_request_path'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0 if report['status'] not in {
        'blocked_non_gpu_candidate_available',
        'blocked_missing_candidate_prerequisite',
        'blocked_candidate_design_not_recommended',
    } else 1


if __name__ == '__main__':
    raise SystemExit(main())
