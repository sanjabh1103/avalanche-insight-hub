from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from backend.common.config import load_settings
from backend.common.regions import repo_root
from backend.common.sar_acceptance_policy import assert_sar_acceptance_for_promotion
from backend.common.supabase_io import has_supabase_credentials, rest_insert
from backend.sar_release_manifest import ReleaseManifestOptions, build_release_manifest_from_reference_set
from backend.sar_release_promote import promote_from_report
from backend.scripts.bootstrap_release_gate import load_rollout_env
from backend.scripts.evaluate_canary_release import post_evaluate_release


def apply_authoritative_release_env(env_file: Path) -> dict[str, str]:
    env = load_rollout_env(env_file)
    missing: list[str] = []
    if not env.supabase_url:
        missing.append('SUPABASE_URL or VITE_SUPABASE_URL')
    if not env.supabase_service_role_key:
        missing.append('SUPABASE_SERVICE_ROLE_KEY')
    if not env.modal_worker_url:
        missing.append('MODAL_WORKER_URL')
    if not env.modal_worker_token:
        missing.append('MODAL_WORKER_TOKEN')
    if not env.sar_unet_model_path:
        missing.append('SAR_UNET_MODEL_PATH')
    if missing:
        raise ValueError(
            'authoritative release gate is blocked until required settings are present: '
            + ', '.join(missing)
        )
    os.environ['SUPABASE_URL'] = env.supabase_url
    os.environ['SUPABASE_SERVICE_ROLE_KEY'] = env.supabase_service_role_key
    os.environ['MODAL_WORKER_URL'] = env.modal_worker_url
    os.environ['MODAL_WORKER_TOKEN'] = env.modal_worker_token
    os.environ['SAR_UNET_MODEL_PATH'] = env.sar_unet_model_path
    os.environ['SAR_UNET_MODEL_VERSION'] = env.sar_unet_model_version
    os.environ['SAR_UNET_MODEL_FAMILY'] = env.sar_unet_model_family
    os.environ['SAR_UNET_DEVICE'] = env.sar_unet_device
    return {
        'supabase_url': env.supabase_url,
        'modal_worker_url': env.modal_worker_url,
        'modal_worker_token': env.modal_worker_token,
        'sar_unet_model_path': env.sar_unet_model_path,
        'sar_unet_model_version': env.sar_unet_model_version,
        'sar_unet_device': env.sar_unet_device,
    }


def build_authoritative_manifest(
    *,
    reference_set_key: str,
    prediction_model_version: str,
) -> dict[str, Any]:
    return build_release_manifest_from_reference_set(
        reference_set_key=reference_set_key,
        options=ReleaseManifestOptions(
            validate_refs=False,
            authoritative_only=True,
            prediction_model_version=prediction_model_version,
            reference_set_key=reference_set_key,
        ),
    )


def resolve_local_model_path(raw_model_path: str, override: Path | None = None) -> Path:
    if override is not None:
        return override.expanduser().resolve()

    candidate = Path(raw_model_path).expanduser()

    if candidate.is_absolute() and tuple(candidate.parts[:2]) == ('/', 'artifacts') and len(candidate.parts) >= 4:
        fallback = (repo_root() / 'backend' / 'data' / candidate.parts[2] / candidate.name).resolve()
        return fallback

    if candidate.exists():
        return candidate.resolve()

    return candidate


def _acceptance_blocker(acceptance_report: dict[str, Any] | None) -> str | None:
    try:
        assert_sar_acceptance_for_promotion(acceptance_report)
    except ValueError as exc:
        return str(exc)
    return None


def _decision_reason(report: dict[str, Any], *, acceptance_blocker: str | None = None) -> str:
    if str(report.get('status')) != 'ok':
        return f'evaluate-release returned status={report.get("status")}'
    baseline = report.get('baseline_f1_floor_used')
    f1 = report.get('f1')
    if not bool(report.get('beats_baseline')):
        if baseline is not None and f1 is not None:
            return f'evaluate-release did not beat baseline gate (f1={f1}, floor={baseline})'
        return 'evaluate-release did not beat baseline gate'
    if acceptance_blocker:
        return f'authoritative held-out evaluation beat baseline, but {acceptance_blocker}'
    return 'authoritative held-out evaluation beat baseline and SnowSlide research-grade acceptance gate'


def record_promotion_event(
    *,
    decision: str,
    decision_reason: str,
    prediction_model_version: str,
    hazard_type: str,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    if not has_supabase_credentials():
        return None
    rows = rest_insert('promotion_events', [{
        'event_type': 'model',
        'previous_version': None,
        'new_version': prediction_model_version,
        'hazard_type': hazard_type,
        'region_name': 'global',
        'evaluation_run_id': report.get('evaluation_run_id'),
        'triggering_metrics': report,
        'decision': decision,
        'decision_reason': decision_reason,
        'automatic': True,
    }])
    return rows[0] if rows else None


def run_authoritative_release_gate(
    *,
    env_file: Path,
    reference_set_key: str,
    prediction_model_version: str,
    artifact_root: Path,
    device: str,
    threshold: float,
    hazard_type: str,
    dry_run: bool = False,
    local_model_path: Path | None = None,
    acceptance_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env_values = apply_authoritative_release_env(env_file)
    manifest = build_authoritative_manifest(
        reference_set_key=reference_set_key,
        prediction_model_version=prediction_model_version,
    )
    report = post_evaluate_release(
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        manifest=manifest,
        request_type='authoritative_evaluate_release',
    )
    acceptance_blocker = _acceptance_blocker(acceptance_report)
    decision = (
        'promote'
        if bool(report.get('beats_baseline')) and str(report.get('status')) == 'ok' and acceptance_blocker is None
        else 'reject'
    )
    decision_reason = _decision_reason(report, acceptance_blocker=acceptance_blocker)
    promotion_event = None if dry_run else record_promotion_event(
        decision=decision,
        decision_reason=decision_reason,
        prediction_model_version=prediction_model_version,
        hazard_type=hazard_type,
        report=report,
    )
    if decision != 'promote':
        return {
            'status': 'ok',
            'reference_set_key': reference_set_key,
            'prediction_model_version': prediction_model_version,
            'decision': decision,
            'decision_reason': decision_reason,
            'evaluation_report': report,
            'promotion_result': None,
            'promotion_event': promotion_event,
        }
    promotion_model_path = resolve_local_model_path(
        env_values['sar_unet_model_path'],
        override=local_model_path,
    )
    promotion_result = promote_from_report(
        report,
        acceptance_report=acceptance_report,
        scenes_manifest=manifest,
        model_path=promotion_model_path,
        artifact_root=artifact_root,
        threshold=threshold,
        device=device,
        hazard_type=hazard_type,
        dry_run=dry_run,
    )
    return {
        'status': 'ok',
        'reference_set_key': reference_set_key,
        'prediction_model_version': prediction_model_version,
        'decision': decision,
        'decision_reason': decision_reason,
        'evaluation_report': report,
        'promotion_result': promotion_result,
        'promotion_event': promotion_event,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description='Evaluate the authoritative SAR held-out set and promote the checkpoint when it beats baseline',
    )
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--reference-set-key', required=True)
    parser.add_argument('--prediction-model-version', default=os.environ.get('SAR_UNET_MODEL_VERSION', 'sar_unet_resnet34_shadow_v1'))
    parser.add_argument('--artifact-root', type=Path, default=settings.artifact_root)
    parser.add_argument('--device', default=os.environ.get('SAR_UNET_DEVICE', 'cpu'))
    parser.add_argument('--threshold', type=float, default=float(os.environ.get('SAR_UNET_SEGMENTATION_THRESHOLD', '0.5')))
    parser.add_argument('--hazard-type', default=settings.hazard_type)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--local-model-path', type=Path)
    parser.add_argument('--acceptance-report', type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_authoritative_release_gate(
        env_file=args.env_file,
        reference_set_key=args.reference_set_key,
        prediction_model_version=args.prediction_model_version,
        artifact_root=args.artifact_root,
        device=args.device,
        threshold=args.threshold,
        hazard_type=args.hazard_type,
        dry_run=args.dry_run,
        local_model_path=args.local_model_path,
        acceptance_report=json.loads(args.acceptance_report.read_text(encoding='utf-8')),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
