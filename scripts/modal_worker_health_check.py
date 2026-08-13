from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXPECTED_ROUTES = {
    '/sar-segment',
    '/train-sar-unet',
    '/train-mtslstm',
    '/infer-mtslstm',
    '/evaluate-release',
}

EXPECTED_GPU_FUNCTIONS = {
    'sar_segment_remote',
    'train_sar_unet_remote',
    'evaluate_sar_checkpoint_remote',
    'train_mts_lstm_remote',
}


def _base_url() -> str:
    raw = os.environ.get('MODAL_WORKER_URL', '').strip()
    if not raw:
        raise RuntimeError('MODAL_WORKER_URL is required')
    return raw.rstrip('/')


def _fetch_json(url: str, timeout: float = 15.0) -> tuple[int, dict[str, Any]]:
    request = Request(url, headers={'Accept': 'application/json'})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            body = response.read().decode('utf-8')
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'{url} returned HTTP {exc.code}: {detail[:300]}') from exc
    except URLError as exc:
        raise RuntimeError(f'{url} failed: {exc.reason}') from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'{url} did not return JSON: {body[:300]}') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'{url} returned non-object JSON')
    return status, payload


def run_check() -> dict[str, Any]:
    status, payload = _fetch_json(f'{_base_url()}/health')
    routes = set(payload.get('routes') or [])
    gpu_functions = set(payload.get('gpu_functions') or [])
    missing_routes = sorted(EXPECTED_ROUTES - routes)
    missing_gpu_functions = sorted(EXPECTED_GPU_FUNCTIONS - gpu_functions)
    ok = (
        status == 200
        and payload.get('status') == 'ok'
        and payload.get('runtime_provider') == 'modal'
        and not missing_routes
        and not missing_gpu_functions
    )
    return {
        'ok': ok,
        'status_code': status,
        'worker_status': payload.get('status'),
        'runtime_provider': payload.get('runtime_provider'),
        'missing_routes': missing_routes,
        'missing_gpu_functions': missing_gpu_functions,
    }


def main() -> int:
    result = run_check()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
