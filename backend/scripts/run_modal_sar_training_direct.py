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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run shadow-only SAR training by invoking the Modal function directly.',
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
        request_payload = load_training_request(args.request)
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
            'request_type': 'train_sar_unet_direct',
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

    _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') in SUCCESS_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
