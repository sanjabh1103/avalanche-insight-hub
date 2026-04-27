from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

from backend.scripts.trigger_and_poll_training import (
    DEFAULT_DATASET_SNAPSHOT_ID,
    DEFAULT_EPOCHS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    apply_rollout_env,
    build_training_payload,
    poll_training_job,
    submit_training_job,
)


DEFAULT_FORECAST_HOURS = 72
DEFAULT_GRID_SIZE = 20


def build_inference_payload(
    *,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
    grid_size: int = DEFAULT_GRID_SIZE,
) -> dict[str, Any]:
    return {
        'request_type': 'infer_mtslstm',
        'forecast_hours': int(forecast_hours),
        'grid_size': int(grid_size),
        'shadow_mode': True,
        'dry_run': True,
        'allow_publish': False,
    }


def _response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f'worker returned non-JSON response ({response.status_code}): {response.text}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'worker returned non-object JSON response ({response.status_code})')
    return payload


def submit_inference_job(
    *,
    worker_url: str,
    worker_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = requests.post(
        worker_url.rstrip('/') + '/infer-mtslstm',
        headers={'Authorization': f'Bearer {worker_token}'},
        json=payload,
        timeout=300,
    )
    body = _response_payload(response)
    if response.status_code != 200:
        raise RuntimeError(f'infer-mtslstm submission failed ({response.status_code}): {json.dumps(body, sort_keys=True)}')
    call_id = str(body.get('call_id') or '').strip()
    if not call_id:
        raise RuntimeError('infer-mtslstm submission succeeded without a call_id')
    return body


def poll_inference_job(
    *,
    worker_url: str,
    worker_token: str,
    call_id: str,
) -> tuple[int, dict[str, Any]]:
    response = requests.get(
        worker_url.rstrip('/') + f'/infer-mtslstm/result/{call_id}',
        headers={'Authorization': f'Bearer {worker_token}'},
        timeout=60,
    )
    body = _response_payload(response)
    return response.status_code, body


def _poll_until_terminal(
    *,
    job_name: str,
    poller,
    worker_url: str,
    worker_token: str,
    call_id: str,
    poll_interval_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(int(timeout_seconds), 1)
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f'{job_name} polling timed out after {timeout_seconds} seconds for call_id={call_id}')
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
            raise RuntimeError(f'{job_name} polling failed ({status_code}): {json.dumps(body, sort_keys=True)}')
        return body


def shadow_regression_passed(training_result: dict[str, Any], inference_result: dict[str, Any]) -> bool:
    if training_result.get('status') != 'ok':
        return False
    if inference_result.get('status') != 'ok':
        return False
    if int(inference_result.get('regions_written') or 0) <= 0:
        return False
    if int(inference_result.get('total_cells_written') or 0) <= 0:
        return False
    if int(inference_result.get('cells_with_shap') or 0) <= 0:
        return False
    return True


def trigger_and_verify_shadow_regression(
    *,
    env_file: Path,
    dataset_snapshot_id: str = DEFAULT_DATASET_SNAPSHOT_ID,
    epochs: int = DEFAULT_EPOCHS,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
    grid_size: int = DEFAULT_GRID_SIZE,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    env_values = apply_rollout_env(env_file)
    worker_url = env_values['modal_worker_url']
    worker_token = env_values['modal_worker_token']

    training_submission = submit_training_job(
        worker_url=worker_url,
        worker_token=worker_token,
        payload=build_training_payload(dataset_snapshot_id=dataset_snapshot_id, epochs=epochs),
    )
    print(json.dumps(training_submission, indent=2, sort_keys=True))
    training_result = _poll_until_terminal(
        job_name='train-mtslstm',
        poller=poll_training_job,
        worker_url=worker_url,
        worker_token=worker_token,
        call_id=str(training_submission['call_id']),
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    if training_result.get('status') != 'ok':
        return {
            'training': training_result,
            'inference': None,
            'shadow_regression_passed': False,
        }

    inference_submission = submit_inference_job(
        worker_url=worker_url,
        worker_token=worker_token,
        payload=build_inference_payload(forecast_hours=forecast_hours, grid_size=grid_size),
    )
    print(json.dumps(inference_submission, indent=2, sort_keys=True))
    inference_result = _poll_until_terminal(
        job_name='infer-mtslstm',
        poller=poll_inference_job,
        worker_url=worker_url,
        worker_token=worker_token,
        call_id=str(inference_submission['call_id']),
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    return {
        'training': training_result,
        'inference': inference_result,
        'shadow_regression_passed': shadow_regression_passed(training_result, inference_result),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Trigger remote shadow-only MTS-LSTM train->infer regression and poll until completion')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--dataset-snapshot-id', default=DEFAULT_DATASET_SNAPSHOT_ID)
    parser.add_argument('--epochs', type=int, default=DEFAULT_EPOCHS)
    parser.add_argument('--forecast-hours', type=int, default=DEFAULT_FORECAST_HOURS)
    parser.add_argument('--grid-size', type=int, default=DEFAULT_GRID_SIZE)
    parser.add_argument('--poll-interval-seconds', type=int, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = trigger_and_verify_shadow_regression(
            env_file=args.env_file,
            dataset_snapshot_id=args.dataset_snapshot_id,
            epochs=args.epochs,
            forecast_hours=args.forecast_hours,
            grid_size=args.grid_size,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('shadow_regression_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
