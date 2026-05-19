from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.sar_acceptance_policy import SNOWSLIDE_EXPECTED_SCENE_IDS, summarize_materialization_results
from backend.scripts.run_snowslide_threshold_sweep import _load_scene_arrays, _manifest_from_request


DEFAULT_REQUEST = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v6/evaluate_release_request.json',
)
DEFAULT_ACCEPTANCE_REPORT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v6-2026-05-18/acceptance_report.json',
)
DEFAULT_MATERIALIZATION_DIR = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v6/by-scene',
)
DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v6-2026-05-18/integrity-audit',
)
DEFAULT_THRESHOLDS = (0.50, 0.70, 0.90, 0.95, 0.98, 0.99, 0.995, 0.9980000257492065)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required SnowSlide v6 integrity input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'SnowSlide v6 integrity input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _parse_float_list(raw: str | None, default: tuple[float, ...]) -> list[float]:
    if not raw:
        return list(default)
    values = [float(item.strip()) for item in raw.split(',') if item.strip()]
    if not values:
        raise ValueError('at least one audit threshold is required')
    return values


def _finite_values(array: np.ndarray) -> np.ndarray:
    values = np.asarray(array, dtype=np.float32)
    return values[np.isfinite(values)]


def _probability_summary(array: np.ndarray) -> dict[str, Any]:
    values = _finite_values(array)
    if values.size == 0:
        return {
            'finite_pixel_count': 0,
            'min': None,
            'max': None,
            'mean': None,
            'percentiles': {},
            'all_zero': False,
            'all_nan': True,
            'outside_probability_range_count': int(array.size),
        }
    return {
        'finite_pixel_count': int(values.size),
        'min': float(np.min(values)),
        'max': float(np.max(values)),
        'mean': float(np.mean(values)),
        'percentiles': {
            'p50': float(np.percentile(values, 50)),
            'p90': float(np.percentile(values, 90)),
            'p95': float(np.percentile(values, 95)),
            'p99': float(np.percentile(values, 99)),
            'p999': float(np.percentile(values, 99.9)),
        },
        'all_zero': bool(np.max(np.abs(values)) == 0.0),
        'all_nan': False,
        'outside_probability_range_count': int(np.sum((values < 0.0) | (values > 1.0))),
    }


def _shape(array: np.ndarray) -> list[int]:
    return [int(item) for item in array.shape]


def _positive_counts(array: np.ndarray, thresholds: list[float]) -> dict[str, int]:
    return {str(threshold): int(np.sum(array >= threshold)) for threshold in thresholds}


def _quantization_signature(array: np.ndarray, *, selected_threshold: float) -> dict[str, Any]:
    values = _finite_values(array)
    if values.size == 0:
        return {
            'storage_dtype_signature': 'empty_or_nan',
            'value_step_signature': None,
            'selected_threshold_reachable': False,
            'quantized_threshold_mismatch': False,
        }
    stride = max(1, values.size // 200000)
    sample = values[::stride]
    if len(np.unique(sample)) < 8:
        return {
            'storage_dtype_signature': 'float_probability_or_unquantized',
            'value_step_signature': None,
            'selected_threshold_reachable': bool(float(np.max(values)) >= selected_threshold),
            'quantized_threshold_mismatch': False,
        }

    def _matches_step(scale: float) -> bool:
        scaled = sample * np.float32(scale)
        return bool(np.all(np.abs(scaled - np.round(scaled)) <= 1e-5))

    if _matches_step(255.0):
        storage_dtype_signature = 'uint8_quantized_probability'
        step = 1.0 / 255.0
    elif _matches_step(65535.0):
        storage_dtype_signature = 'uint16_quantized_probability'
        step = 1.0 / 65535.0
    else:
        storage_dtype_signature = 'float_probability_or_unquantized'
        step = None

    max_value = float(np.max(values))
    selected_reachable = bool(max_value >= selected_threshold)
    lower_positive = bool(np.sum(values >= min(0.995, selected_threshold)) > 0)
    quantized_mismatch = (
        storage_dtype_signature in {'uint8_quantized_probability', 'uint16_quantized_probability'}
        and not selected_reachable
        and lower_positive
    )
    return {
        'storage_dtype_signature': storage_dtype_signature,
        'value_step_signature': step,
        'selected_threshold_reachable': selected_reachable,
        'quantized_threshold_mismatch': quantized_mismatch,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        '# SnowSlide V6 Integrity Audit',
        '',
        f"- Decision: `{report['decision']}`",
        f"- Failure classification: `{report['failure_classification']}`",
        f"- Quantized threshold mismatch: `{str(report.get('quantized_threshold_mismatch')).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Next GPU run authorized: `{str(report['next_gpu_run_authorized']).lower()}`",
        '',
        '## Findings',
        '',
    ]
    for finding in report['findings']:
        lines.append(f"- `{finding['gate']}`: {finding['summary']}")
    lines.extend([
        '',
        '## Scene Probability Summary',
        '',
        '| Scene | Dtype signature | Max | P99 | Selected threshold reachable | Positives at selected threshold | Truth positives |',
        '|---|---|---:|---:|---|---:|---:|',
    ])
    selected_threshold = str(report['selected_threshold'])
    for scene in report['scene_reports']:
        prob = scene['prediction_probability_summary']
        lines.append(
            f"| {scene['scene_id']} | {scene.get('storage_dtype_signature')} | "
            f"{prob.get('max')} | "
            f"{prob.get('percentiles', {}).get('p99')} | "
            f"{scene.get('selected_threshold_reachable')} | "
            f"{scene['positive_pixel_counts_by_threshold'].get(selected_threshold, 0)} | "
            f"{scene['truth_positive_pixels']} |"
        )
    lines.extend(['', report['next_checkpoint'], ''])
    return '\n'.join(lines)


def _decision_from_findings(findings: list[dict[str, Any]], *, selected_positive_pixels: int, lower_threshold_positive_pixels: int) -> tuple[str, str, str]:
    blocking = {finding['gate'] for finding in findings if finding.get('severity') == 'blocker'}
    if blocking:
        return (
            'blocked_pipeline_integrity_failure',
            'pipeline_integrity_failure',
            'Fix mask/reference/model-path integrity issues before rerunning Phase 5.',
        )
    if any(finding.get('gate') == 'quantized_threshold_mismatch' for finding in findings):
        return (
            'blocked_quantized_threshold_mismatch',
            'probability_storage_quantization_mismatch',
            'Re-materialize SnowSlide prediction masks as float32 probabilities before judging Phase 5.',
        )
    if selected_positive_pixels == 0 and lower_threshold_positive_pixels > 0:
        return (
            'blocked_threshold_calibration_failure',
            'high_threshold_calibration_failure',
            'Run non-GPU threshold/ensemble recovery before considering another GPU candidate.',
        )
    if selected_positive_pixels == 0:
        return (
            'blocked_blank_or_low_probability_predictions',
            'blank_or_low_probability_predictions',
            'Inspect checkpoint/domain-transfer behavior; do not proceed to fresh-final evaluation.',
        )
    return (
        'integrity_passed_recovery_needed',
        'metrics_failure_after_valid_materialization',
        'Use threshold recovery or candidate design; do not promote.',
    )


def build_snowslide_v6_integrity_audit(
    *,
    request_path: Path,
    acceptance_report_path: Path,
    materialization_result_dir: Path,
    output_root: Path,
    env_file: Path | None = None,
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or list(DEFAULT_THRESHOLDS)
    request = _load_json(request_path, label='request')
    acceptance = _load_json(acceptance_report_path, label='acceptance_report')
    manifest = _manifest_from_request(request, env_file=env_file)
    scenes, predictions, truths, baselines = _load_scene_arrays(manifest)
    materialization = summarize_materialization_results(materialization_result_dir)
    selected_threshold = float(request.get('prediction_threshold') or request.get('threshold') or thresholds[-1])

    scene_reports: list[dict[str, Any]] = []
    selected_positive_pixels = 0
    lower_threshold_positive_pixels = 0
    for index, scene in enumerate(scenes):
        prediction = predictions[index]
        truth = truths[index]
        positive_counts = _positive_counts(prediction, thresholds)
        selected_count = int(np.sum(prediction >= selected_threshold))
        lower_count = int(np.sum(prediction >= min(thresholds)))
        quantization = _quantization_signature(prediction, selected_threshold=selected_threshold)
        selected_positive_pixels += selected_count
        lower_threshold_positive_pixels += lower_count
        scene_reports.append({
            'scene_id': str(scene.get('scene_id') or f'scene-{index}'),
            'prediction_mask_ref': scene.get('prediction_mask'),
            'truth_mask_ref': scene.get('truth_mask'),
            'baseline_mask_ref': scene.get('baseline_mask'),
            'prediction_shape': _shape(prediction),
            'truth_shape': _shape(truth),
            'shape_aligned': tuple(prediction.shape) == tuple(truth.shape),
            'truth_positive_pixels': int(np.sum(truth)),
            'prediction_probability_summary': _probability_summary(prediction),
            **quantization,
            'positive_pixel_counts_by_threshold': positive_counts | {str(selected_threshold): selected_count},
        })

    expected = set(SNOWSLIDE_EXPECTED_SCENE_IDS)
    actual = {scene['scene_id'] for scene in scene_reports}
    findings: list[dict[str, Any]] = []
    if len(scene_reports) != len(SNOWSLIDE_EXPECTED_SCENE_IDS) or actual != expected:
        findings.append({
            'gate': 'scene_coverage',
            'severity': 'blocker',
            'summary': f'expected {len(expected)} SnowSlide scenes and found {len(scene_reports)}',
            'missing_scene_ids': sorted(expected - actual),
            'extra_scene_ids': sorted(actual - expected),
        })
    if materialization.get('missing_scene_ids'):
        findings.append({
            'gate': 'materialization_coverage',
            'severity': 'blocker',
            'summary': 'materialization results are missing one or more scenes',
            'missing_scene_ids': materialization.get('missing_scene_ids'),
        })
    if any(not scene['shape_aligned'] for scene in scene_reports):
        findings.append({
            'gate': 'mask_shape_alignment',
            'severity': 'blocker',
            'summary': 'one or more prediction/truth masks have different shapes',
        })
    if any(scene['truth_positive_pixels'] == 0 for scene in scene_reports):
        findings.append({
            'gate': 'truth_positive_pixels',
            'severity': 'blocker',
            'summary': 'one or more truth masks contain zero positive pixels',
        })
    if any(scene['prediction_probability_summary']['outside_probability_range_count'] for scene in scene_reports):
        findings.append({
            'gate': 'prediction_probability_range',
            'severity': 'blocker',
            'summary': 'one or more prediction masks contain values outside [0, 1]',
        })
    if all(scene['prediction_probability_summary']['all_zero'] for scene in scene_reports):
        findings.append({
            'gate': 'blank_prediction_masks',
            'severity': 'blocker',
            'summary': 'all prediction masks are all-zero arrays',
        })
    if selected_positive_pixels == 0:
        findings.append({
            'gate': 'selected_threshold_positive_pixels',
            'severity': 'warning',
            'summary': f'no pixels meet selected threshold {selected_threshold}',
        })
    if any(scene.get('quantized_threshold_mismatch') for scene in scene_reports):
        findings.append({
            'gate': 'quantized_threshold_mismatch',
            'severity': 'warning',
            'summary': 'selected threshold is unreachable after probability-mask quantization, but lower thresholds have positives',
            'affected_scene_ids': [
                scene['scene_id']
                for scene in scene_reports
                if scene.get('quantized_threshold_mismatch')
            ],
        })

    decision, failure_classification, next_checkpoint = _decision_from_findings(
        findings,
        selected_positive_pixels=selected_positive_pixels,
        lower_threshold_positive_pixels=lower_threshold_positive_pixels,
    )
    report = {
        'version': 'snowslide_v6_integrity_audit_v1',
        'generated_at': _now_iso(),
        'decision': decision,
        'failure_classification': failure_classification,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'next_gpu_run_authorized': False,
        'selected_threshold': selected_threshold,
        'thresholds_checked': thresholds,
        'selected_threshold_positive_pixels': selected_positive_pixels,
        'lowest_threshold_positive_pixels': lower_threshold_positive_pixels,
        'storage_dtype_signature': sorted({
            str(scene.get('storage_dtype_signature'))
            for scene in scene_reports
            if scene.get('storage_dtype_signature')
        }),
        'value_step_signature': sorted({
            float(scene.get('value_step_signature'))
            for scene in scene_reports
            if scene.get('value_step_signature') is not None
        }),
        'selected_threshold_reachable': bool(selected_positive_pixels > 0),
        'quantized_threshold_mismatch': any(
            scene.get('quantized_threshold_mismatch') for scene in scene_reports
        ),
        'request_model_version': request.get('prediction_model_version') or request.get('model_version'),
        'request_reference_set_key': request.get('reference_set_key'),
        'acceptance_decision': acceptance.get('decision'),
        'acceptance_metrics': acceptance.get('metrics'),
        'scene_count': len(scene_reports),
        'materialization_summary': materialization,
        'findings': findings,
        'scene_reports': scene_reports,
        'next_checkpoint': next_checkpoint,
        'source_inputs': {
            'request': str(request_path),
            'acceptance_report': str(acceptance_report_path),
            'materialization_result_dir': str(materialization_result_dir),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'snowslide_v6_integrity_audit.json', report)
    (output_root / 'snowslide_v6_integrity_audit.md').write_text(_render_markdown(report), encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Audit SnowSlide v6 prediction-mask integrity without GPU work.')
    parser.add_argument('--request', type=Path, default=DEFAULT_REQUEST)
    parser.add_argument('--acceptance-report', type=Path, default=DEFAULT_ACCEPTANCE_REPORT)
    parser.add_argument('--materialization-result-dir', type=Path, default=DEFAULT_MATERIALIZATION_DIR)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--thresholds')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_snowslide_v6_integrity_audit(
        request_path=args.request,
        acceptance_report_path=args.acceptance_report,
        materialization_result_dir=args.materialization_result_dir,
        output_root=args.output_root,
        env_file=args.env_file,
        thresholds=_parse_float_list(args.thresholds, DEFAULT_THRESHOLDS),
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'failure_classification': report['failure_classification'],
        'selected_threshold_positive_pixels': report['selected_threshold_positive_pixels'],
        'lowest_threshold_positive_pixels': report['lowest_threshold_positive_pixels'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'next_gpu_run_authorized': report['next_gpu_run_authorized'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
