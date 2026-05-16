from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import requests

from backend.scripts.bootstrap_release_gate import load_rollout_env
from backend.scripts.trigger_and_poll_training import cancel_modal_function_call


DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_TIMEOUT_SECONDS = 14400
EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION = 'european_sar_prediction_artifact_v1'


def apply_rollout_env(env_file: Path) -> dict[str, str]:
    env = load_rollout_env(env_file)
    if env.modal_token_id:
        os.environ['MODAL_TOKEN_ID'] = env.modal_token_id
    if env.modal_token_secret:
        os.environ['MODAL_TOKEN_SECRET'] = env.modal_token_secret
    missing: list[str] = []
    if not env.modal_worker_url:
        missing.append('MODAL_WORKER_URL')
    if not env.modal_worker_token:
        missing.append('MODAL_WORKER_TOKEN')
    if missing:
        raise ValueError(f'remote SAR training trigger is blocked until required settings are present: {", ".join(missing)}')
    return {
        'modal_worker_url': env.modal_worker_url,
        'modal_worker_token': env.modal_worker_token,
    }


def load_training_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR training request must be a JSON object: {path}')
    if not str(payload.get('training_manifest_path') or '').strip():
        raise ValueError('SAR training request requires training_manifest_path')
    return payload


def _response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f'worker returned non-JSON response ({response.status_code}): {response.text}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'worker returned non-object JSON response ({response.status_code})')
    return payload


def submit_sar_training_job(
    *,
    worker_url: str,
    worker_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = requests.post(
        worker_url.rstrip('/') + '/train-sar-unet',
        headers={'Authorization': f'Bearer {worker_token}'},
        json=payload,
        timeout=300,
    )
    body = _response_payload(response)
    if response.status_code != 200:
        raise RuntimeError(f'train-sar-unet submission failed ({response.status_code}): {json.dumps(body, sort_keys=True)}')
    call_id = str(body.get('call_id') or '').strip()
    if not call_id:
        raise RuntimeError('train-sar-unet submission succeeded without a call_id')
    return body


def poll_sar_training_job(
    *,
    worker_url: str,
    worker_token: str,
    call_id: str,
) -> tuple[int, dict[str, Any]]:
    response = requests.get(
        worker_url.rstrip('/') + f'/train-sar-unet/result/{call_id}',
        headers={'Authorization': f'Bearer {worker_token}'},
        timeout=60,
    )
    return response.status_code, _response_payload(response)


def _poll_until_terminal(
    *,
    poller: Callable[..., tuple[int, dict[str, Any]]],
    worker_url: str,
    worker_token: str,
    call_id: str,
    poll_interval_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(int(timeout_seconds), 1)
    while True:
        if time.monotonic() > deadline:
            cancel_modal_function_call(call_id, terminate_containers=True)
            raise TimeoutError(f'train-sar-unet polling timed out after {timeout_seconds} seconds for call_id={call_id}')
        status_code, body = poller(
            worker_url=worker_url,
            worker_token=worker_token,
            call_id=call_id,
        )
        if status_code == 202:
            print(json.dumps(body, indent=2, sort_keys=True))
            time.sleep(max(int(poll_interval_seconds), 1))
            continue
        if status_code != 200:
            raise RuntimeError(f'train-sar-unet polling failed ({status_code}): {json.dumps(body, sort_keys=True)}')
        return body


def _request_context(path: Path) -> dict[str, Any]:
    try:
        request = load_training_request(path)
    except Exception:
        return {}
    return {
        'version': EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION,
        'source_key': request.get('source_key'),
        'dataset_version': request.get('dataset_version'),
        'model_family': request.get('model_family'),
        'model_version': request.get('model_version') or request.get('candidate_model_version'),
        'candidate_model_version': request.get('candidate_model_version'),
        'split': 'val',
        'threshold': request.get('threshold'),
        'license_review_id': request.get('license_review_id'),
        'train_events': request.get('train_scene_ids') or request.get('train_events') or [],
        'val_events': request.get('validation_scene_ids') or request.get('val_events') or [],
        'evaluated_scene_ids': request.get('validation_scene_ids') or request.get('val_events') or [],
    }


def trigger_and_poll_sar_training(
    *,
    env_file: Path,
    request_path: Path,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    env_values = apply_rollout_env(env_file)
    request_payload = load_training_request(request_path)
    submission = submit_sar_training_job(
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        payload=request_payload,
    )
    print(json.dumps(submission, indent=2, sort_keys=True))
    return _poll_until_terminal(
        poller=poll_sar_training_job,
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        call_id=str(submission['call_id']),
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trigger remote shadow-only SAR training and poll until completion.')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--poll-interval-seconds', type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = trigger_and_poll_sar_training(
            env_file=args.env_file,
            request_path=args.request,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        error_payload = {
            **_request_context(args.request),
            'status': 'blocked_remote_training',
            'request_type': 'train_sar_unet',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'request_path': str(args.request),
            'error': str(exc),
            'reason': str(exc),
        }
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(error_payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(str(exc), file=sys.stderr)
        return 1

    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    return 0 if result.get('status') in {'ok', 'completed_with_validation_gate_failure'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
