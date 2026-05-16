from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MODAL_APP_NAME = 'avalanche-modal-worker'
DEFAULT_MODAL_FUNCTION_NAME = 'sar_segment_remote'
SUCCESS_STATUSES = {'ok'}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load_materialization_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SAR prediction materialization request must be a JSON object: {path}')
    if not str(payload.get('reference_set_key') or '').strip():
        raise ValueError('SAR prediction materialization request requires reference_set_key')
    if not str(payload.get('prediction_model_version') or '').strip():
        raise ValueError('SAR prediction materialization request requires prediction_model_version')
    model_path = str(payload.get('model_path') or '').strip()
    if not model_path.startswith('/artifacts/'):
        raise ValueError('SAR prediction materialization model_path must be under /artifacts/')
    return {
        **payload,
        'persist_events': False,
        'shadow_mode': True,
    }


def load_avalcd_gate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'AvalCD benchmark report must be a JSON object: {path}')
    return payload


def assert_avalcd_gate_allows_materialization(report: dict[str, Any]) -> dict[str, Any]:
    if report.get('production_scoring_allowed') is not False:
        raise ValueError('AvalCD benchmark must remain shadow-only before SnowSlide materialization')
    promotion = report.get('promotion_gate_report') if isinstance(report.get('promotion_gate_report'), dict) else {}
    if promotion.get('decision') != 'blocked_shadow_only':
        raise ValueError('AvalCD benchmark must retain decision=blocked_shadow_only before SnowSlide materialization')
    source_reports = report.get('source_reports')
    if not isinstance(source_reports, list) or not source_reports:
        raise ValueError('AvalCD benchmark report has no source_reports')
    avalcd_report = next(
        (
            item for item in source_reports
            if isinstance(item, dict) and item.get('source_key') == 'avalcd_zenodo_v1'
        ),
        None,
    )
    if avalcd_report is None:
        raise ValueError('AvalCD benchmark report does not contain source_key=avalcd_zenodo_v1')
    prediction_metrics = avalcd_report.get('sar_prediction_metrics') if isinstance(avalcd_report.get('sar_prediction_metrics'), dict) else {}
    quality_gate = prediction_metrics.get('quality_gate') if isinstance(prediction_metrics.get('quality_gate'), dict) else {}
    if not (
        quality_gate.get('passed') is True
        and quality_gate.get('precision_floor_met') is True
        and quality_gate.get('recall_floor_met') is True
    ):
        raise ValueError(
            'SnowSlide prediction materialization blocked until AvalCD SAR quality gate passes '
            'with precision_floor_met=true and recall_floor_met=true'
        )
    return quality_gate


def _load_modal_module() -> Any:
    try:
        import modal
    except ImportError as exc:  # pragma: no cover - depends on operator machine setup
        raise RuntimeError('modal must be installed to run direct Modal SAR prediction materialization') from exc
    return modal


def run_modal_sar_prediction_materialization_direct(
    *,
    modal_profile: str,
    request_payload: dict[str, Any],
    app_name: str = DEFAULT_MODAL_APP_NAME,
    function_name: str = DEFAULT_MODAL_FUNCTION_NAME,
) -> dict[str, Any]:
    profile = str(modal_profile or '').strip()
    if not profile:
        raise ValueError('direct Modal SAR prediction materialization requires --modal-profile')
    os.environ['MODAL_PROFILE'] = profile
    modal_module = _load_modal_module()
    remote_function = modal_module.Function.from_name(app_name, function_name)
    result = remote_function.remote(request_payload)
    if not isinstance(result, dict):
        raise RuntimeError(f'Modal function returned non-object result: {type(result).__name__}')
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Materialize SnowSlide held-out prediction masks by invoking sar_segment_remote directly.',
    )
    parser.add_argument('--modal-profile', required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--avalcd-benchmark-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--app-name', default=DEFAULT_MODAL_APP_NAME)
    parser.add_argument('--function-name', default=DEFAULT_MODAL_FUNCTION_NAME)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        request_payload = load_materialization_request(args.request)
        gate = assert_avalcd_gate_allows_materialization(load_avalcd_gate(args.avalcd_benchmark_report))
        result = run_modal_sar_prediction_materialization_direct(
            modal_profile=args.modal_profile,
            request_payload=request_payload,
            app_name=args.app_name,
            function_name=args.function_name,
        )
        result = {
            **result,
            'request_type': 'sar_prediction_materialization_direct',
            'avalcd_quality_gate': gate,
            'modal_profile': str(args.modal_profile),
            'app_name': str(args.app_name),
            'function_name': str(args.function_name),
            'dry_run': False,
        }
    except Exception as exc:
        result = {
            'status': 'blocked_prediction_materialization',
            'request_type': 'sar_prediction_materialization_direct',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'modal_profile': str(args.modal_profile),
            'app_name': str(args.app_name),
            'function_name': str(args.function_name),
            'request_path': str(args.request),
            'avalcd_benchmark_report_path': str(args.avalcd_benchmark_report),
            'error': str(exc),
            'reason': str(exc),
        }
        _write_json(args.output, result)
        print(str(exc), file=sys.stderr)
        return 1
    _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('status') in SUCCESS_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
