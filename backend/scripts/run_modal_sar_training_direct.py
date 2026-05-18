from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MODAL_APP_NAME = 'avalanche-modal-worker'
DEFAULT_MODAL_FUNCTION_NAME = 'train_sar_unet_remote'
EUROPEAN_SAR_PREDICTION_ARTIFACT_VERSION = 'european_sar_prediction_artifact_v1'
SUCCESS_STATUSES = {'ok', 'completed_with_validation_gate_failure'}
DEFAULT_ASYNC_MAX_WAIT_SECONDS = 3600


def load_training_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR training request must be a JSON object: {path}')
    if not str(payload.get('training_manifest_path') or '').strip():
        raise ValueError('SAR training request requires training_manifest_path')
    return payload


def _request_context(path: Path) -> dict[str, Any]:
    try:
        request = load_training_request(path)
    except Exception:
        return {}
    return _request_payload_context(request)


def _request_payload_context(request: dict[str, Any]) -> dict[str, Any]:
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


def _load_modal_module() -> Any:
    try:
        import modal
    except ImportError as exc:  # pragma: no cover - depends on operator machine setup
        raise RuntimeError('modal must be installed to run direct Modal SAR training') from exc
    return modal


def run_modal_sar_training_direct(
    *,
    modal_profile: str,
    request_payload: dict[str, Any],
    app_name: str = DEFAULT_MODAL_APP_NAME,
    function_name: str = DEFAULT_MODAL_FUNCTION_NAME,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('direct Modal SAR training requires --modal-profile')
    os.environ['MODAL_PROFILE'] = profile

    modal_module = _load_modal_module()
    remote_function = modal_module.Function.from_name(app_name, function_name)
    result = remote_function.remote(request_payload)
    if not isinstance(result, dict):
        raise RuntimeError(f'Modal function returned non-object result: {type(result).__name__}')
    return result


def _function_call_id(function_call: Any) -> str:
    for attribute in ('object_id', 'function_call_id', 'call_id'):
        value = getattr(function_call, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(function_call)


def _is_timeout_exception(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or type(exc).__name__ in {
        'TimeoutError',
        'FunctionTimeoutError',
        'OutputExpiredError',
    }


def run_modal_sar_training_async(
    *,
    modal_profile: str,
    request_payload: dict[str, Any],
    app_name: str = DEFAULT_MODAL_APP_NAME,
    function_name: str = DEFAULT_MODAL_FUNCTION_NAME,
    max_wait_seconds: int = DEFAULT_ASYNC_MAX_WAIT_SECONDS,
    cancel_on_timeout: bool = False,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('direct Modal SAR training requires --modal-profile')
    os.environ['MODAL_PROFILE'] = profile

    modal_module = _load_modal_module()
    remote_function = modal_module.Function.from_name(app_name, function_name)
    function_call = remote_function.spawn(request_payload)
    function_call_id = _function_call_id(function_call)
    try:
        result = function_call.get(timeout=int(max_wait_seconds))
    except Exception as exc:
        if not _is_timeout_exception(exc):
            raise
        cancelled = False
        cancel_error: str | None = None
        if cancel_on_timeout:
            try:
                function_call.cancel(terminate_containers=True)
                cancelled = True
            except Exception as cancel_exc:  # pragma: no cover - depends on Modal transport failure modes
                cancel_error = str(cancel_exc)
        payload = {
            **_request_payload_context(request_payload),
            'status': 'blocked_remote_training_timeout',
            'request_type': 'train_sar_unet_direct_async',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'modal_profile': profile,
            'app_name': str(app_name),
            'function_name': str(function_name),
            'function_call_id': function_call_id,
            'max_wait_seconds': int(max_wait_seconds),
            'cancel_on_timeout': bool(cancel_on_timeout),
            'cancelled': cancelled,
            'cancel_error': cancel_error,
            'reason': f'Modal function call exceeded {int(max_wait_seconds)} seconds',
            'error': str(exc),
        }
        return payload
    if not isinstance(result, dict):
        raise RuntimeError(f'Modal function returned non-object result: {type(result).__name__}')
    result.setdefault('function_call_id', function_call_id)
    result.setdefault('request_type', 'train_sar_unet_direct_async')
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run shadow-only SAR training by invoking the Modal function directly.',
    )
    parser.add_argument('--modal-profile', required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app-name', default=DEFAULT_MODAL_APP_NAME)
    parser.add_argument('--function-name', default=DEFAULT_MODAL_FUNCTION_NAME)
    parser.add_argument('--async', dest='async_mode', action='store_true', help='Spawn the Modal call and poll with a bounded timeout.')
    parser.add_argument('--max-wait-seconds', type=int, default=DEFAULT_ASYNC_MAX_WAIT_SECONDS)
    parser.add_argument('--cancel-on-timeout', action='store_true')
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        request_payload = load_training_request(args.request)
        if args.async_mode:
            result = run_modal_sar_training_async(
                modal_profile=args.modal_profile,
                request_payload=request_payload,
                app_name=args.app_name,
                function_name=args.function_name,
                max_wait_seconds=args.max_wait_seconds,
                cancel_on_timeout=args.cancel_on_timeout,
            )
        else:
            result = run_modal_sar_training_direct(
                modal_profile=args.modal_profile,
                request_payload=request_payload,
                app_name=args.app_name,
                function_name=args.function_name,
            )
    except Exception as exc:
        error_payload = {
            **_request_context(args.request),
            'status': 'blocked_remote_training',
            'request_type': 'train_sar_unet_direct_async' if getattr(args, 'async_mode', False) else 'train_sar_unet_direct',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'modal_profile': str(args.modal_profile),
            'app_name': str(args.app_name),
            'function_name': str(args.function_name),
            'request_path': str(args.request),
            'error': str(exc),
            'reason': str(exc),
        }
        _write_json(args.output, error_payload)
        print(str(exc), file=sys.stderr)
        return 1

    result.setdefault('request_path', str(args.request))
    result.setdefault('modal_profile', str(args.modal_profile))
    result.setdefault('app_name', str(args.app_name))
    result.setdefault('function_name', str(args.function_name))
    _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') in SUCCESS_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
