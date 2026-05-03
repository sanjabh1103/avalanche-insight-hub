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
    artifact_dir: str | None = None,
    region_keys: list[str] | None = None,
    lifeboat_mode: bool = False,
    lifeboat_profile: str = 'proof72',
    skip_tree_shap: bool = False,
    skip_shap_cache: bool = False,
    skip_runout_generation: bool = False,
    skip_compatibility_write: bool = False,
    emit_stage_metrics: bool = False,
) -> dict[str, Any]:
    payload = {
        'request_type': 'infer_mtslstm',
        'forecast_hours': int(forecast_hours),
        'grid_size': int(grid_size),
        'shadow_mode': True,
        'dry_run': True,
        'allow_publish': False,
    }
    if artifact_dir:
        payload['artifact_dir'] = str(artifact_dir)
    cleaned_region_keys = [
        str(region_key).strip()
        for region_key in (region_keys or [])
        if str(region_key).strip()
    ]
    if cleaned_region_keys:
        payload['region_keys'] = cleaned_region_keys
    if lifeboat_mode:
        payload['lifeboat_mode'] = True
        payload['lifeboat_profile'] = str(lifeboat_profile or 'proof72').strip() or 'proof72'
    if skip_tree_shap:
        payload['skip_tree_shap'] = True
    if skip_shap_cache:
        payload['skip_shap_cache'] = True
    if skip_runout_generation:
        payload['skip_runout_generation'] = True
    if skip_compatibility_write:
        payload['skip_compatibility_write'] = True
    if emit_stage_metrics:
        payload['emit_stage_metrics'] = True
    return payload


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
    if not _training_result_allows_shadow_inference(training_result):
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


def _training_result_supports_shadow_proof(training_result: dict[str, Any]) -> bool:
    status = str(training_result.get('status') or '').strip()
    if status == 'ok':
        return True
    if status != 'completed_with_gate_failure':
        return False
    return bool(
        str(training_result.get('model_artifact_ref') or '').strip()
        and bool(training_result.get('shadow_mode'))
        and not bool(training_result.get('allow_publish'))
    )


def _training_result_allows_shadow_inference(training_result: dict[str, Any]) -> bool:
    status = str(training_result.get('status') or '').strip()
    artifact_dir = str(training_result.get('artifact_dir') or '').strip()
    if status == 'ok':
        return bool(artifact_dir)
    if status != 'completed_with_gate_failure':
        return False
    return bool(
        artifact_dir
        and str(training_result.get('model_artifact_ref') or '').strip()
        and bool(training_result.get('shadow_mode'))
        and not bool(training_result.get('allow_publish'))
    )


def calibration_expectation_passed(
    training_result: dict[str, Any],
    *,
    require_improvement: bool = False,
) -> dict[str, Any]:
    calibration_applied = bool(training_result.get('calibration_applied'))
    calibration_reason = str(training_result.get('calibration_reason') or '').strip()
    calibration_method = str(training_result.get('calibration_method') or '').strip()
    try:
        raw_brier = float(training_result.get('lstm_brier_uncalibrated'))
        calibrated_brier = float(training_result.get('lstm_brier_calibrated'))
        float(training_result.get('lstm_pss_uncalibrated'))
        float(training_result.get('lstm_pss_calibrated'))
        calibration_metrics_present = True
    except (TypeError, ValueError):
        calibration_metrics_present = False
        raw_brier = 0.0
        calibrated_brier = 0.0

    calibration_improved = bool(calibration_metrics_present and calibrated_brier < raw_brier)
    calibration_status_present = bool(calibration_method) if calibration_applied else bool(calibration_reason)

    if not calibration_metrics_present:
        return {
            'passed': False,
            'reason': 'missing_calibration_metrics',
            'calibration_metrics_present': False,
            'calibration_applied': calibration_applied,
            'calibration_improved': calibration_improved,
        }
    if not calibration_status_present:
        return {
            'passed': False,
            'reason': 'missing_calibration_status',
            'calibration_metrics_present': True,
            'calibration_applied': calibration_applied,
            'calibration_improved': calibration_improved,
        }
    if require_improvement and not calibration_improved:
        return {
            'passed': False,
            'reason': 'calibrated_brier_not_improved',
            'calibration_metrics_present': True,
            'calibration_applied': calibration_applied,
            'calibration_improved': calibration_improved,
        }
    return {
        'passed': True,
        'reason': 'calibrated_brier_improved' if calibration_improved else 'calibration_metrics_present',
        'calibration_metrics_present': True,
        'calibration_applied': calibration_applied,
        'calibration_improved': calibration_improved,
    }


def trigger_and_verify_shadow_regression(
    *,
    env_file: Path,
    dataset_snapshot_id: str = DEFAULT_DATASET_SNAPSHOT_ID,
    epochs: int = DEFAULT_EPOCHS,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
    grid_size: int = DEFAULT_GRID_SIZE,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    require_calibration_improvement: bool = False,
) -> dict[str, Any]:
    env_values = apply_rollout_env(env_file)
    worker_url = env_values['modal_worker_url']
    worker_token = env_values['modal_worker_token']
    training_payload = build_training_payload(dataset_snapshot_id=dataset_snapshot_id, epochs=epochs)

    training_submission = submit_training_job(
        worker_url=worker_url,
        worker_token=worker_token,
        payload=training_payload,
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
    calibration_expectation = calibration_expectation_passed(
        training_result,
        require_improvement=require_calibration_improvement,
    )
    if not _training_result_supports_shadow_proof(training_result):
        return {
            'training': training_result,
            'inference': None,
            'shadow_regression_passed': False,
            'calibration_expectation_passed': calibration_expectation['passed'],
            'calibration_expectation_reason': calibration_expectation['reason'],
            'calibration_metrics_present': calibration_expectation['calibration_metrics_present'],
            'calibration_applied': calibration_expectation['calibration_applied'],
            'calibration_improved': calibration_expectation['calibration_improved'],
        }
    training_artifact_dir = str(training_result.get('artifact_dir') or '').strip()
    if not training_artifact_dir:
        raise RuntimeError('training artifact_dir is required for shadow inference')

    inference_submission = submit_inference_job(
        worker_url=worker_url,
        worker_token=worker_token,
        payload=build_inference_payload(
            forecast_hours=forecast_hours,
            grid_size=grid_size,
            artifact_dir=training_artifact_dir,
        ),
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
        'calibration_expectation_passed': calibration_expectation['passed'],
        'calibration_expectation_reason': calibration_expectation['reason'],
        'calibration_metrics_present': calibration_expectation['calibration_metrics_present'],
        'calibration_applied': calibration_expectation['calibration_applied'],
        'calibration_improved': calibration_expectation['calibration_improved'],
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
    parser.add_argument('--require-calibration-improvement', action='store_true')
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
            require_calibration_improvement=args.require_calibration_improvement,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('shadow_regression_passed') and result.get('calibration_expectation_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
