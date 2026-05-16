from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MODAL_APP_NAME = 'avalanche-modal-worker'
DEFAULT_MODAL_FUNCTION_NAME = 'evaluate_release_remote'
SUCCESS_STATUSES = {'ok'}


def load_evaluation_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR release evaluation request must be a JSON object: {path}')
    has_reference_set = bool(str(payload.get('reference_set_key') or '').strip())
    has_scenes = isinstance(payload.get('scenes'), list) and bool(payload.get('scenes'))
    if not has_reference_set and not has_scenes:
        raise ValueError('SAR release evaluation request requires reference_set_key or non-empty scenes[]')
    payload['dry_run'] = True
    return payload


def _request_context(path: Path) -> dict[str, Any]:
    try:
        request = load_evaluation_request(path)
    except Exception:
        return {}
    return {
        'reference_set_key': request.get('reference_set_key'),
        'prediction_model_version': request.get('prediction_model_version'),
        'scene_count': len(request.get('scenes') or []),
        'dry_run': True,
    }


def _load_modal_module() -> Any:
    try:
        import modal
    except ImportError as exc:  # pragma: no cover - depends on operator machine setup
        raise RuntimeError('modal must be installed to run direct Modal SAR held-out evaluation') from exc
    return modal


def run_modal_sar_release_evaluation_direct(
    *,
    modal_profile: str,
    request_payload: dict[str, Any],
    app_name: str = DEFAULT_MODAL_APP_NAME,
    function_name: str = DEFAULT_MODAL_FUNCTION_NAME,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('direct Modal SAR release evaluation requires --modal-profile')
    os.environ['MODAL_PROFILE'] = profile
    request_payload = {**request_payload, 'dry_run': True}

    modal_module = _load_modal_module()
    remote_function = modal_module.Function.from_name(app_name, function_name)
    result = remote_function.remote(request_payload)
    if not isinstance(result, dict):
        raise RuntimeError(f'Modal function returned non-object result: {type(result).__name__}')
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run shadow-only SAR held-out release evaluation by invoking the Modal function directly.',
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


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        request_payload = load_evaluation_request(args.request)
        result = run_modal_sar_release_evaluation_direct(
            modal_profile=args.modal_profile,
            request_payload=request_payload,
            app_name=args.app_name,
            function_name=args.function_name,
        )
    except Exception as exc:
        error_payload = {
            **_request_context(args.request),
            'status': 'blocked_remote_evaluation',
            'request_type': 'evaluate_release_direct',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'modal_profile': str(args.modal_profile),
            'app_name': str(args.app_name),
            'function_name': str(args.function_name),
            'request_path': str(args.request),
            'error': str(exc),
            'reason': str(exc),
            'dry_run': True,
        }
        _write_json(args.output, error_payload)
        print(str(exc), file=sys.stderr)
        return 1

    result = {**result, 'dry_run': True}
    _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') in SUCCESS_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
