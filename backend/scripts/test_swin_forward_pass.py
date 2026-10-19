from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from backend.scripts.bootstrap_release_gate import load_rollout_env


DEFAULT_MODEL_FAMILY = 'swinunet_tiny_diff'
DEFAULT_MODEL_VERSION = 'swin_transformer_v2_tiny_shadow_v1'
DEFAULT_BBOX = [9.7, 46.7, 9.8, 46.8]


def apply_rollout_env(env_file: Path) -> dict[str, str]:
    env = load_rollout_env(env_file)
    missing: list[str] = []
    if not env.modal_worker_url:
        missing.append('MODAL_WORKER_URL')
    if not env.modal_worker_token:
        missing.append('MODAL_WORKER_TOKEN')
    if missing:
        raise ValueError(f'swin forward-pass test is blocked until required settings are present: {", ".join(missing)}')
    return {
        'modal_worker_url': env.modal_worker_url,
        'modal_worker_token': env.modal_worker_token,
    }


def build_forward_pass_payload(
    *,
    model_family: str = DEFAULT_MODEL_FAMILY,
    prediction_model_version: str = DEFAULT_MODEL_VERSION,
) -> dict[str, Any]:
    pre_channels = [[[0.0 for _ in range(128)] for _ in range(128)] for _ in range(2)]
    post_channels = [[[1.0 for _ in range(128)] for _ in range(128)] for _ in range(2)]
    return {
        'hazard_type': 'avalanche',
        'dry_run': True,
        'shadow_mode': True,
        'model_family': model_family,
        'prediction_model_version': prediction_model_version,
        'scenes': [{
            'scene_id': 'swin-forward-pass-smoke',
            'region_key': 'davos',
            'scene_time': datetime.now(timezone.utc).isoformat(),
            'bbox': list(DEFAULT_BBOX),
            'pre_channels': pre_channels,
            'post_channels': post_channels,
        }],
    }


def post_forward_pass(
    *,
    worker_url: str,
    worker_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = requests.post(
        worker_url.rstrip('/') + '/sar-segment',
        headers={'Authorization': f'Bearer {worker_token}'},
        json=payload,
        timeout=300,
    )
    if not response.ok:
        raise RuntimeError(f'swin forward-pass failed ({response.status_code}): {response.text}')
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError('swin forward-pass returned a non-object JSON payload')
    return result


def run_forward_pass_smoke_test(
    *,
    env_file: Path,
    model_family: str = DEFAULT_MODEL_FAMILY,
    prediction_model_version: str = DEFAULT_MODEL_VERSION,
) -> dict[str, Any]:
    env_values = apply_rollout_env(env_file)
    payload = build_forward_pass_payload(
        model_family=model_family,
        prediction_model_version=prediction_model_version,
    )
    return post_forward_pass(
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        payload=payload,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run a dry-run Swin shadow forward-pass smoke test against the Modal worker')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--model-family', default=DEFAULT_MODEL_FAMILY)
    parser.add_argument('--prediction-model-version', default=DEFAULT_MODEL_VERSION)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_forward_pass_smoke_test(
        env_file=args.env_file,
        model_family=args.model_family,
        prediction_model_version=args.prediction_model_version,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
