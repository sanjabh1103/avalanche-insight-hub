from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MODAL_APP_NAME = 'avalanche-modal-worker'
DEFAULT_MODAL_FUNCTION_NAME = 'evaluate_sar_checkpoint_remote'
SUCCESS_STATUSES = {'ok', 'completed_with_validation_gate_failure'}


def load_checkpoint_evaluation_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR checkpoint evaluation request must be a JSON object: {path}')
    if not str(payload.get('training_manifest_path') or payload.get('training_manifest') or '').strip():
        raise ValueError('SAR checkpoint evaluation request requires training_manifest_path')
    if not str(
        payload.get('checkpoint_path')
        or payload.get('model_checkpoint_path')
        or payload.get('initial_checkpoint_path')
        or '',
    ).strip():
        raise ValueError('SAR checkpoint evaluation request requires checkpoint_path')
    return payload


def _load_modal_module() -> Any:
    try:
        import modal
    except ImportError as exc:  # pragma: no cover - depends on operator machine setup
        raise RuntimeError('modal must be installed to run direct Modal SAR checkpoint evaluation') from exc
    return modal


def run_modal_sar_checkpoint_evaluation_direct(
    *,
    modal_profile: str,
    request_payload: dict[str, Any],
    app_name: str = DEFAULT_MODAL_APP_NAME,
    function_name: str = DEFAULT_MODAL_FUNCTION_NAME,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('direct Modal SAR checkpoint evaluation requires --modal-profile')
    os.environ['MODAL_PROFILE'] = profile

    modal_module = _load_modal_module()
    remote_function = modal_module.Function.from_name(app_name, function_name)
    result = remote_function.remote(request_payload)
    if not isinstance(result, dict):
        raise RuntimeError(f'Modal function returned non-object result: {type(result).__name__}')
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run shadow-only SAR checkpoint evaluation by invoking the Modal function directly.',
    )
    parser.add_argument('--modal-profile', required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app-name', default=DEFAULT_MODAL_APP_NAME)
    parser.add_argument('--function-name', default=DEFAULT_MODAL_FUNCTION_NAME)
    return parser.parse_args(argv)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _failure_payload(args: argparse.Namespace, exc: Exception) -> dict[str, Any]:
    return {
        'status': 'blocked_remote_checkpoint_evaluation',
        'request_type': 'evaluate_sar_checkpoint_direct',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'modal_profile': str(args.modal_profile),
        'app_name': str(args.app_name),
        'function_name': str(args.function_name),
        'request_path': str(args.request),
        'error': str(exc),
        'reason': str(exc),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        request_payload = load_checkpoint_evaluation_request(args.request)
        result = run_modal_sar_checkpoint_evaluation_direct(
            modal_profile=args.modal_profile,
            request_payload=request_payload,
            app_name=args.app_name,
            function_name=args.function_name,
        )
    except Exception as exc:
        error_payload = _failure_payload(args, exc)
        _write_json(args.output, error_payload)
        print(str(exc), file=sys.stderr)
        return 1

    _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') in SUCCESS_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
