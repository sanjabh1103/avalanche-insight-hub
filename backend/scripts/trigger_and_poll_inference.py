from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from backend.scripts.bootstrap_release_gate import load_rollout_env
from backend.scripts.trigger_and_poll_training import DEFAULT_POLL_INTERVAL_SECONDS, DEFAULT_TIMEOUT_SECONDS
from backend.scripts.trigger_and_verify_shadow_regression import (
    DEFAULT_FORECAST_HOURS,
    DEFAULT_GRID_SIZE,
    _poll_until_terminal,
    build_inference_payload,
    poll_inference_job as poll_inference_job_http,
    submit_inference_job as submit_inference_job_http,
)


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
    return (
        result.get('status') == 'ok'
        and int(result.get('regions_written') or 0) > 0
        and int(result.get('total_cells_written') or 0) > 0
        and int(result.get('cells_with_shap') or 0) > 0
        and bool(str(result.get('surrogate_model_version') or '').strip())
    )


def trigger_and_poll_inference(
    *,
    env_file: Path,
    artifact_dir: str,
    transport: str,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
    grid_size: int = DEFAULT_GRID_SIZE,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    env_values = apply_inference_env(env_file, transport=transport)
    payload = build_inference_payload(
        forecast_hours=forecast_hours,
        grid_size=grid_size,
        artifact_dir=artifact_dir,
    )

    if transport == 'http':
        submission = submit_inference_job_http(
            worker_url=env_values['modal_worker_url'],
            worker_token=env_values['modal_worker_token'],
            payload=payload,
        )
        poller = poll_inference_job_http
    else:
        submission = submit_inference_job_modal(payload=payload)
        poller = poll_inference_job_modal

    print(json.dumps(submission, indent=2, sort_keys=True))
    inference_result = _poll_until_terminal(
        job_name=f'infer-mtslstm[{transport}]',
        poller=poller,
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        call_id=str(submission['call_id']),
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    return {
        'transport': transport,
        'inference': inference_result,
        'inference_passed': inference_passed(inference_result),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trigger remote shadow-only MTS-LSTM inference and poll until completion')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--artifact-dir', required=True)
    parser.add_argument('--transport', choices=('modal', 'http'), default='modal')
    parser.add_argument('--forecast-hours', type=int, default=DEFAULT_FORECAST_HOURS)
    parser.add_argument('--grid-size', type=int, default=DEFAULT_GRID_SIZE)
    parser.add_argument('--poll-interval-seconds', type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = trigger_and_poll_inference(
            env_file=args.env_file,
            artifact_dir=args.artifact_dir,
            transport=args.transport,
            forecast_hours=args.forecast_hours,
            grid_size=args.grid_size,
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
