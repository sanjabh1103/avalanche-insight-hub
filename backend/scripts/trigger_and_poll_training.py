from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from backend.scripts.bootstrap_release_gate import load_rollout_env


DEFAULT_DATASET_SNAPSHOT_ID = 'latest'
DEFAULT_EPOCHS = 1
DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 14400


def apply_rollout_env(env_file: Path) -> dict[str, str]:
    env = load_rollout_env(env_file)
    missing: list[str] = []
    if not env.modal_worker_url:
        missing.append('MODAL_WORKER_URL')
    if not env.modal_worker_token:
        missing.append('MODAL_WORKER_TOKEN')
    if missing:
        raise ValueError(f'remote MTS-LSTM trigger is blocked until required settings are present: {", ".join(missing)}')
    return {
        'modal_worker_url': env.modal_worker_url,
        'modal_worker_token': env.modal_worker_token,
    }


def build_training_payload(
    *,
    dataset_snapshot_id: str = DEFAULT_DATASET_SNAPSHOT_ID,
    epochs: int = DEFAULT_EPOCHS,
) -> dict[str, Any]:
    return {
        'request_type': 'train_mtslstm',
        'dataset_snapshot_id': dataset_snapshot_id,
        'epochs': int(epochs),
        'early_stopping': True,
        'shadow_mode': True,
        'allow_publish': False,
        'sar_release_gate_passed': False,
        'pss_floor': 0.0,
    }


def _response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f'worker returned non-JSON response ({response.status_code}): {response.text}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'worker returned non-object JSON response ({response.status_code})')
    return payload


def submit_training_job(
    *,
    worker_url: str,
    worker_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = requests.post(
        worker_url.rstrip('/') + '/train-mtslstm',
        headers={'Authorization': f'Bearer {worker_token}'},
        json=payload,
        timeout=300,
    )
    body = _response_payload(response)
    if response.status_code != 200:
        raise RuntimeError(f'train-mtslstm submission failed ({response.status_code}): {json.dumps(body, sort_keys=True)}')
    call_id = str(body.get('call_id') or '').strip()
    if not call_id:
        raise RuntimeError('train-mtslstm submission succeeded without a call_id')
    return body


def poll_training_job(
    *,
    worker_url: str,
    worker_token: str,
    call_id: str,
) -> tuple[int, dict[str, Any]]:
    response = requests.get(
        worker_url.rstrip('/') + f'/train-mtslstm/result/{call_id}',
        headers={'Authorization': f'Bearer {worker_token}'},
        timeout=60,
    )
    body = _response_payload(response)
    return response.status_code, body


def trigger_and_poll_training(
    *,
    env_file: Path,
    dataset_snapshot_id: str = DEFAULT_DATASET_SNAPSHOT_ID,
    epochs: int = DEFAULT_EPOCHS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    env_values = apply_rollout_env(env_file)
    submission = submit_training_job(
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        payload=build_training_payload(dataset_snapshot_id=dataset_snapshot_id, epochs=epochs),
    )
    print(json.dumps(submission, indent=2, sort_keys=True))

    call_id = str(submission['call_id'])
    deadline = time.monotonic() + max(int(timeout_seconds), 1)

    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f'train-mtslstm polling timed out after {timeout_seconds} seconds for call_id={call_id}')

        status_code, body = poll_training_job(
            worker_url=env_values['modal_worker_url'],
            worker_token=env_values['modal_worker_token'],
            call_id=call_id,
        )
        if status_code == 202:
            print(json.dumps(body, indent=2, sort_keys=True))
            time.sleep(max(int(poll_interval_seconds), 1))
            continue
        if status_code != 200:
            raise RuntimeError(f'train-mtslstm polling failed ({status_code}): {json.dumps(body, sort_keys=True)}')
        return body


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trigger remote shadow-only MTS-LSTM training and poll until completion')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--dataset-snapshot-id', default=DEFAULT_DATASET_SNAPSHOT_ID)
    parser.add_argument('--epochs', type=int, default=DEFAULT_EPOCHS)
    parser.add_argument('--poll-interval-seconds', type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = trigger_and_poll_training(
            env_file=args.env_file,
            dataset_snapshot_id=args.dataset_snapshot_id,
            epochs=args.epochs,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
