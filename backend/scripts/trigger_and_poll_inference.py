from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from backend.scripts.bootstrap_release_gate import load_rollout_env
from backend.scripts.trigger_and_poll_training import DEFAULT_POLL_INTERVAL_SECONDS, _poll_until_terminal
from backend.scripts.trigger_and_verify_shadow_regression import (
    DEFAULT_FORECAST_HOURS,
    DEFAULT_GRID_SIZE,
    DEFAULT_INFERENCE_TIMEOUT_SECONDS,
    build_inference_payload,
    poll_inference_job as poll_inference_job_http,
    submit_inference_job as submit_inference_job_http,
)

DEFAULT_REATTACH_TIMEOUT_SECONDS = 3600


def apply_inference_env(env_file: Path, *, transport: str) -> dict[str, str]:
    env = load_rollout_env(env_file)
    if env.modal_token_id:
        os.environ['MODAL_TOKEN_ID'] = env.modal_token_id
    if env.modal_token_secret:
        os.environ['MODAL_TOKEN_SECRET'] = env.modal_token_secret

    if transport == 'http':
        missing: list[str] = []
        if not env.modal_worker_url:
            missing.append('MODAL_WORKER_URL')
        if not env.modal_worker_token:
            missing.append('MODAL_WORKER_TOKEN')
        if missing:
            raise ValueError(f'remote HTTP inference trigger is blocked until required settings are present: {", ".join(missing)}')
        return {
            'modal_worker_url': env.modal_worker_url,
            'modal_worker_token': env.modal_worker_token,
        }

    token_id = os.environ.get('MODAL_TOKEN_ID') or env.modal_token_id
    token_secret = os.environ.get('MODAL_TOKEN_SECRET') or env.modal_token_secret
    missing = []
    if not token_id:
        missing.append('MODAL_TOKEN_ID')
    if not token_secret:
        missing.append('MODAL_TOKEN_SECRET')
    if missing:
        raise ValueError(f'remote Modal inference trigger is blocked until required settings are present: {", ".join(missing)}')
    return {
        'modal_worker_url': '',
        'modal_worker_token': '',
    }


def submit_inference_job_modal(*, payload: dict[str, Any]) -> dict[str, Any]:
    from backend.modal_worker_app import submit_infer_mtslstm_job

    return submit_infer_mtslstm_job(payload)


def poll_inference_job_modal(
    *,
    worker_url: str,
    worker_token: str,
    call_id: str,
) -> tuple[int, dict[str, Any]]:
    del worker_url
    del worker_token
    from backend.modal_worker_app import poll_infer_mtslstm_job

    return poll_infer_mtslstm_job(call_id)


def inference_passed(result: dict[str, Any]) -> bool:
    lifeboat_mode = bool(result.get('lifeboat_mode'))
    return (
        result.get('status') == 'ok'
        and int(result.get('regions_written') or 0) > 0
        and int(result.get('total_cells_written') or 0) > 0
        and (lifeboat_mode or int(result.get('cells_with_shap') or 0) > 0)
        and bool(str(result.get('surrogate_model_version') or '').strip())
    )


def trigger_and_poll_inference(
    *,
    env_file: Path,
    artifact_dir: str | None = None,
    call_id: str | None = None,
    transport: str,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
    grid_size: int = DEFAULT_GRID_SIZE,
    region_keys: list[str] | None = None,
    lifeboat_mode: bool = False,
    lifeboat_profile: str = 'proof72',
    skip_tree_shap: bool = False,
    skip_shap_cache: bool = False,
    skip_runout_generation: bool = False,
    skip_compatibility_write: bool = False,
    emit_stage_metrics: bool = False,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    if bool(str(artifact_dir or '').strip()) == bool(str(call_id or '').strip()):
        raise ValueError('exactly one of --artifact-dir or --call-id is required')

    env_values = apply_inference_env(env_file, transport=transport)
    resolved_timeout_seconds = (
        int(timeout_seconds)
        if timeout_seconds is not None
        else (DEFAULT_REATTACH_TIMEOUT_SECONDS if call_id else DEFAULT_INFERENCE_TIMEOUT_SECONDS)
    )

    if transport == 'http':
        poller = poll_inference_job_http
    else:
        poller = poll_inference_job_modal

    resolved_call_id = str(call_id or '').strip()
    if not resolved_call_id:
        payload = build_inference_payload(
            forecast_hours=forecast_hours,
            grid_size=grid_size,
            artifact_dir=artifact_dir,
            region_keys=region_keys,
            lifeboat_mode=lifeboat_mode,
            lifeboat_profile=lifeboat_profile,
            skip_tree_shap=skip_tree_shap,
            skip_shap_cache=skip_shap_cache,
            skip_runout_generation=skip_runout_generation,
            skip_compatibility_write=skip_compatibility_write,
            emit_stage_metrics=emit_stage_metrics,
        )
        if transport == 'http':
            submission = submit_inference_job_http(
                worker_url=env_values['modal_worker_url'],
                worker_token=env_values['modal_worker_token'],
                payload=payload,
            )
        else:
            submission = submit_inference_job_modal(payload=payload)
        print(json.dumps(submission, indent=2, sort_keys=True))
        resolved_call_id = str(submission['call_id'])

    inference_result = _poll_until_terminal(
        job_name=f'infer-mtslstm[{transport}]',
        poller=poller,
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        call_id=resolved_call_id,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=resolved_timeout_seconds,
    )
    return {
        'transport': transport,
        'inference': inference_result,
        'inference_passed': inference_passed(inference_result),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trigger remote shadow-only MTS-LSTM inference and poll until completion')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--artifact-dir')
    source_group.add_argument('--call-id')
    parser.add_argument('--transport', choices=('modal', 'http'), default='modal')
    parser.add_argument('--forecast-hours', type=int, default=DEFAULT_FORECAST_HOURS)
    parser.add_argument('--grid-size', type=int, default=DEFAULT_GRID_SIZE)
    parser.add_argument('--region-key', action='append', default=[])
    parser.add_argument('--lifeboat-mode', action='store_true')
    parser.add_argument('--lifeboat-profile', choices=('proof72', 'smoke24'), default='proof72')
    parser.add_argument('--skip-tree-shap', action='store_true')
    parser.add_argument('--skip-shap-cache', action='store_true')
    parser.add_argument('--skip-runout-generation', action='store_true')
    parser.add_argument('--skip-compatibility-write', action='store_true')
    parser.add_argument('--emit-stage-metrics', action='store_true')
    parser.add_argument('--poll-interval-seconds', type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument('--timeout-seconds', type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = trigger_and_poll_inference(
            env_file=args.env_file,
            artifact_dir=args.artifact_dir,
            call_id=args.call_id,
            transport=args.transport,
            forecast_hours=args.forecast_hours,
            grid_size=args.grid_size,
            region_keys=args.region_key,
            lifeboat_mode=args.lifeboat_mode,
            lifeboat_profile=args.lifeboat_profile,
            skip_tree_shap=args.skip_tree_shap,
            skip_shap_cache=args.skip_shap_cache,
            skip_runout_generation=args.skip_runout_generation,
            skip_compatibility_write=args.skip_compatibility_write,
            emit_stage_metrics=args.emit_stage_metrics,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('inference_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
