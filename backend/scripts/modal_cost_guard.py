from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Sequence


DEFAULT_MODAL_APP_NAME = 'avalanche-modal-worker'
DEFAULT_GPU_FUNCTIONS = (
    'sar_segment_remote',
    'train_sar_unet_remote',
    'evaluate_sar_checkpoint_remote',
    'train_mts_lstm_remote',
    'infer_mts_lstm_remote',
)


def _load_modal_module() -> Any:
    try:
        import modal
    except ImportError as exc:  # pragma: no cover - depends on operator machine setup
        raise RuntimeError('modal must be installed to reassert Modal autoscaler cost guard') from exc
    return modal


def reassert_modal_zero_warm_autoscaler(
    *,
    modal_profile: str,
    app_name: str = DEFAULT_MODAL_APP_NAME,
    function_names: Sequence[str] = DEFAULT_GPU_FUNCTIONS,
    scaledown_window: int = 30,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('Modal cost guard requires --modal-profile')
    os.environ['MODAL_PROFILE'] = profile
    modal_module = _load_modal_module()
    updates: list[dict[str, Any]] = []
    for function_name in function_names:
        function = modal_module.Function.from_name(app_name, function_name)
        function.update_autoscaler(
            min_containers=0,
            buffer_containers=0,
            scaledown_window=int(scaledown_window),
        )
        updates.append({
            'function_name': function_name,
            'min_containers': 0,
            'buffer_containers': 0,
            'scaledown_window': int(scaledown_window),
        })
    return {
        'status': 'ok',
        'request_type': 'modal_cost_guard',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'modal_profile': profile,
        'app_name': app_name,
        'updates': updates,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Reassert Modal scale-to-zero settings for GPU functions.')
    parser.add_argument('--modal-profile', required=True)
    parser.add_argument('--app-name', default=DEFAULT_MODAL_APP_NAME)
    parser.add_argument('--function', dest='functions', action='append', help='Function to guard; repeatable')
    parser.add_argument('--scaledown-window', type=int, default=30)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = reassert_modal_zero_warm_autoscaler(
        modal_profile=args.modal_profile,
        app_name=args.app_name,
        function_names=tuple(args.functions or DEFAULT_GPU_FUNCTIONS),
        scaledown_window=args.scaledown_window,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
