from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUALIFICATION_ROOT = Path(
    'backend/artifacts/european-shadow-qualification',
)
DEFAULT_PHASE7_ROOT = DEFAULT_QUALIFICATION_ROOT / 'phase7-unblock-reattempt-2026-05-18'
DEFAULT_FLOAT32_ROOT = DEFAULT_QUALIFICATION_ROOT / 'snowslide-research-grade-v7-float32-2026-05-18'
DEFAULT_TRAINING_ROOT = Path(
    'backend/artifacts/european-shadow-sar-training/avalcd-shadow-train5-val2-2026-05-16',
)
DEFAULT_OUTPUT_ROOT = DEFAULT_TRAINING_ROOT / 'research-v8'

DEFAULT_CANDIDATE_MODEL_VERSION = 'avalcd_swinunet_tiny_diff_calibrated_transfer_shadow_20260518_v8'
DEFAULT_MAX_WAIT_SECONDS = 3600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required v8 authorization input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'v8 authorization input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _has_production_scoring_allowed(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'production_scoring_allowed' and item is True:
                return True
            if _has_production_scoring_allowed(item):
                return True
    elif isinstance(value, list):
        return any(_has_production_scoring_allowed(item) for item in value)
    return False


def _best_sweep_candidate(sweep: dict[str, Any]) -> dict[str, Any]:
    selected = sweep.get('selected_candidate')
    if isinstance(selected, dict):
        return selected
    candidates = [item for item in sweep.get('candidates') or [] if isinstance(item, dict)]
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda item: (
            float((item.get('metrics') or {}).get('f1') or 0.0),
            float((item.get('metrics') or {}).get('precision') or 0.0),
        ),
    )


def _training_request_from_design(
    *,
    template: dict[str, Any],
    design: dict[str, Any],
    candidate_model_version: str,
    max_wait_seconds: int,
) -> dict[str, Any]:
    overrides = design.get('proposed_training_request_overrides')
    if not isinstance(overrides, dict):
        overrides = {}

    request = deepcopy(template)
    request['candidate_model_version'] = candidate_model_version
    request['model_family'] = request.get('model_family') or 'swinunet_tiny_diff'
    request['initial_checkpoint_path'] = str(
        design.get('initial_checkpoint_path')
        or request.get('initial_checkpoint_path')
        or '/artifacts/20260518T124829Z/sar_model.pt',
    )
    request['epochs'] = int(overrides.get('epochs') or 4)
    request['patience'] = int(overrides.get('patience') or 2)
    request['batch_size'] = int(overrides.get('batch_size') or request.get('batch_size') or 8)
    request['learning_rate'] = float(overrides.get('learning_rate') or 0.000005)
    request['loss'] = str(overrides.get('loss') or request.get('loss') or 'focal_tversky')
    request['negative_ratio'] = int(overrides.get('negative_ratio') or 6)
    request['focal_tversky_alpha'] = float(overrides.get('focal_tversky_alpha') or 0.35)
    request['focal_tversky_beta'] = float(overrides.get('focal_tversky_beta') or 0.65)
    request['focal_tversky_gamma'] = float(overrides.get('focal_tversky_gamma') or 1.33)
    request['f_beta'] = float(overrides.get('f_beta') or 0.75)
    request['threshold_grid'] = [
        float(item)
        for item in (
            overrides.get('threshold_grid')
            or [0.90, 0.95, 0.97, 0.98, 0.985, 0.99, 0.995, 0.998]
        )
    ]
    request['postprocess_min_component_area_px'] = int(
        overrides.get('postprocess_min_component_area_px') or 128,
    )
    request['postprocess_opening_size_px'] = int(overrides.get('postprocess_opening_size_px') or 0)
    request['materialized_dataset_root'] = str(
        overrides.get('materialized_dataset_root') or '/tmp/avalcd-shadow-train5-val2-v8',
    )
    request['precision_floor'] = 0.6
    request['postprocess_recall_floor'] = 0.5
    request['postprocess_apply_to_threshold_selection'] = True
    request['export_validation_prediction_artifact'] = True
    request['max_wait_seconds'] = int(max_wait_seconds)
    request['cancel_on_timeout'] = True
    request['production_scoring_allowed'] = False
    return request


def _status_and_reason(
    *,
    phase7_report: dict[str, Any],
    design: dict[str, Any],
    acceptance: dict[str, Any],
    sweep: dict[str, Any],
    integrity: dict[str, Any],
    authorize_gpu: bool,
) -> tuple[str, str, bool]:
    inputs = [phase7_report, design, acceptance, sweep, integrity]
    if any(_has_production_scoring_allowed(item) for item in inputs):
        return 'blocked_production_scoring_flag', 'At least one source artifact allows production scoring.', False
    if phase7_report.get('decision') != 'one_bounded_v8_candidate_warranted':
        return (
            'blocked_phase7_not_warranted',
            f"Phase 7 decision is not one_bounded_v8_candidate_warranted: {phase7_report.get('decision')}",
            False,
        )
    if design.get('decision') != 'bounded_v8_candidate_design_recommended':
        return (
            'blocked_candidate_design_not_recommended',
            f"Candidate design is not bounded_v8_candidate_design_recommended: {design.get('decision')}",
            False,
        )
    if integrity.get('decision') != 'integrity_passed_recovery_needed':
        return (
            'blocked_float32_integrity_not_passed',
            f"Float32 integrity decision is not integrity_passed_recovery_needed: {integrity.get('decision')}",
            False,
        )
    if integrity.get('quantized_threshold_mismatch') is True:
        return 'blocked_quantized_threshold_mismatch', 'Float32 integrity still reports quantized threshold mismatch.', False
    if int(sweep.get('passing_candidate_count') or 0) > 0:
        return 'blocked_non_gpu_candidate_available', 'A non-GPU passing candidate exists; recheck AvalCD before training.', False
    if acceptance.get('decision') != 'blocked_research_grade':
        return (
            'blocked_unexpected_snowslide_decision',
            f"SnowSlide acceptance decision is not blocked_research_grade: {acceptance.get('decision')}",
            False,
        )
    if not authorize_gpu:
        return 'awaiting_explicit_operator_approval', 'Prerequisites pass, but --authorize-gpu was not supplied.', False
    return 'authorized_for_single_bounded_gpu_run', 'User explicitly authorized one bounded v8 GPU run.', True


def _render_markdown(report: dict[str, Any]) -> str:
    best = report.get('best_non_gpu_candidate') if isinstance(report.get('best_non_gpu_candidate'), dict) else {}
    metrics = best.get('metrics') if isinstance(best.get('metrics'), dict) else {}
    return '\n'.join([
        '# Phase 7 V8 Candidate Authorization Review',
        '',
        f"- Status: `{report['status']}`",
        f"- Candidate: `{report['candidate_model_version']}`",
        f"- GPU run authorized: `{str(report['gpu_run_authorized']).lower()}`",
        f"- Max GPU runs: `{report['max_gpu_runs']}`",
        f"- Max wait seconds: `{report['max_wait_seconds']}`",
        f"- Cancel on timeout: `{str(report['cancel_on_timeout']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Reason: {report['reason']}",
        '',
        '## Corrected Float32 Evidence',
        '',
        f"- Phase 7 decision: `{report['phase7_decision']}`",
        f"- Float32 integrity: `{report['float32_integrity_decision']}`",
        f"- SnowSlide acceptance: `{report['snowslide_acceptance_decision']}`",
        f"- Float32 sweep passing candidates: `{report['float32_sweep_passing_candidate_count']}`",
        (
            f"- Best non-GPU candidate: threshold `{best.get('threshold')}`, area "
            f"`{best.get('postprocess_min_component_area_px')}`, precision "
            f"`{metrics.get('precision')}`, recall `{metrics.get('recall')}`, F1 `{metrics.get('f1')}`"
        ),
        '',
        'This artifact may authorize at most one Modal GPU run. It never authorizes production scoring or promotion.',
        '',
    ])


def build_phase7_v8_candidate_authorization_review(
    *,
    phase7_report_path: Path,
    candidate_design_path: Path,
    acceptance_report_path: Path,
    sweep_report_path: Path,
    integrity_audit_path: Path,
    template_training_request_path: Path,
    output_root: Path,
    authorize_gpu: bool = False,
    modal_profile: str = 'sanjabh1103_limit30',
    candidate_model_version: str = DEFAULT_CANDIDATE_MODEL_VERSION,
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS,
) -> dict[str, Any]:
    phase7_report = _load_json(phase7_report_path, label='phase7_report')
    design = _load_json(candidate_design_path, label='candidate_design_report_v8')
    acceptance = _load_json(acceptance_report_path, label='float32_acceptance_report')
    sweep = _load_json(sweep_report_path, label='float32_threshold_sweep')
    integrity = _load_json(integrity_audit_path, label='float32_integrity_audit')
    template_request = _load_json(template_training_request_path, label='template_training_request')

    status, reason, gpu_allowed = _status_and_reason(
        phase7_report=phase7_report,
        design=design,
        acceptance=acceptance,
        sweep=sweep,
        integrity=integrity,
        authorize_gpu=authorize_gpu,
    )
    train_request = (
        _training_request_from_design(
            template=template_request,
            design=design,
            candidate_model_version=candidate_model_version,
            max_wait_seconds=max_wait_seconds,
        )
        if gpu_allowed
        else None
    )
    best = _best_sweep_candidate(sweep)
    report = {
        'version': 'phase7_v8_candidate_authorization_review_v1',
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
        'phase7_ready': False,
        'phase7_decision': phase7_report.get('decision'),
        'candidate_design_decision': design.get('decision'),
        'float32_integrity_decision': integrity.get('decision'),
        'float32_sweep_decision': sweep.get('decision'),
        'float32_sweep_passing_candidate_count': int(sweep.get('passing_candidate_count') or 0),
        'snowslide_acceptance_decision': acceptance.get('decision'),
        'best_non_gpu_candidate': best,
        'train_request_path': str(output_root / 'train_sar_unet_request.json') if train_request else None,
        'source_inputs': {
            'phase7_report': str(phase7_report_path),
            'candidate_design_report_v8': str(candidate_design_path),
            'float32_acceptance_report': str(acceptance_report_path),
            'float32_threshold_sweep': str(sweep_report_path),
            'float32_integrity_audit': str(integrity_audit_path),
            'template_training_request': str(template_training_request_path),
        },
        'next_checkpoint': (
            'Run the generated train_sar_unet_request.json through the bounded async Modal training path.'
            if gpu_allowed
            else 'Do not launch GPU work until this review is authorized and guard checks pass.'
        ),
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'candidate_authorization_review.json', report)
    (output_root / 'candidate_authorization_review.md').write_text(_render_markdown(report), encoding='utf-8')
    if train_request is not None:
        _write_json(output_root / 'train_sar_unet_request.json', train_request)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build Phase 7 v8 SAR candidate authorization review artifacts.')
    parser.add_argument('--phase7-report', type=Path, default=DEFAULT_PHASE7_ROOT / 'phase7_unblock_reattempt_report.json')
    parser.add_argument('--candidate-design-report', type=Path, default=DEFAULT_PHASE7_ROOT / 'candidate_design_report_v8.json')
    parser.add_argument('--acceptance-report', type=Path, default=DEFAULT_FLOAT32_ROOT / 'acceptance_report.json')
    parser.add_argument('--sweep-report', type=Path, default=DEFAULT_FLOAT32_ROOT / 'snowslide_v7_float32_threshold_sweep_report.json')
    parser.add_argument('--integrity-audit', type=Path, default=DEFAULT_FLOAT32_ROOT / 'integrity-audit' / 'snowslide_v6_integrity_audit.json')
    parser.add_argument('--template-training-request', type=Path, default=DEFAULT_TRAINING_ROOT / 'research-v7' / 'train_sar_unet_request.json')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--authorize-gpu', action='store_true')
    parser.add_argument('--modal-profile', default='sanjabh1103_limit30')
    parser.add_argument('--candidate-model-version', default=DEFAULT_CANDIDATE_MODEL_VERSION)
    parser.add_argument('--max-wait-seconds', type=int, default=DEFAULT_MAX_WAIT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_phase7_v8_candidate_authorization_review(
        phase7_report_path=args.phase7_report,
        candidate_design_path=args.candidate_design_report,
        acceptance_report_path=args.acceptance_report,
        sweep_report_path=args.sweep_report,
        integrity_audit_path=args.integrity_audit,
        template_training_request_path=args.template_training_request,
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
        'blocked_production_scoring_flag',
        'blocked_phase7_not_warranted',
        'blocked_candidate_design_not_recommended',
        'blocked_float32_integrity_not_passed',
        'blocked_quantized_threshold_mismatch',
        'blocked_non_gpu_candidate_available',
        'blocked_unexpected_snowslide_decision',
    } else 1


if __name__ == '__main__':
    raise SystemExit(main())
