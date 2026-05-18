from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.sar_acceptance_policy import (
    SNOWSLIDE_F1_FLOOR,
    SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING,
    SNOWSLIDE_PRECISION_FLOOR,
    SNOWSLIDE_RECALL_FLOOR,
    SNOWSLIDE_RESEARCH_GRADE_POLICY_VERSION,
    summarize_materialization_results,
)
from backend.sar_unet_training import _component_summaries, _postprocess_binary_mask
from backend.sar_unet_worker import compute_mask_metrics
from backend.scripts.run_snowslide_threshold_sweep import _load_scene_arrays, _manifest_from_request


DEFAULT_REQUEST = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-dry-run/scene-blended-v5/evaluate_release_request.json',
)
DEFAULT_ACCEPTANCE_REPORT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v5-2026-05-18/acceptance_report.json',
)
DEFAULT_MATERIALIZATION_DIR = Path(
    'backend/artifacts/european-shadow-heldout/snowslide-materialization/scene-blended-v5/by-scene',
)
DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v5-2026-05-18/diagnostics',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'JSON artifact must contain an object: {path}')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _acceptance_floor_failures(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    precision = _as_float(metrics.get('precision'))
    recall = _as_float(metrics.get('recall'))
    f1 = _as_float(metrics.get('f1'))
    fpr = _as_float(metrics.get('false_positive_rate'))
    if precision < SNOWSLIDE_PRECISION_FLOOR:
        failures.append({'gate': 'precision_floor', 'actual': precision, 'required': SNOWSLIDE_PRECISION_FLOOR})
    if recall < SNOWSLIDE_RECALL_FLOOR:
        failures.append({'gate': 'recall_floor', 'actual': recall, 'required': SNOWSLIDE_RECALL_FLOOR})
    if f1 < SNOWSLIDE_F1_FLOOR:
        failures.append({'gate': 'f1_floor', 'actual': f1, 'required': SNOWSLIDE_F1_FLOOR})
    if fpr > SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING:
        failures.append({
            'gate': 'false_positive_rate_ceiling',
            'actual': fpr,
            'required_max': SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING,
        })
    return failures


def classify_dominant_blocker(metrics: dict[str, Any]) -> str:
    precision_failed = _as_float(metrics.get('precision')) < SNOWSLIDE_PRECISION_FLOOR
    recall_failed = _as_float(metrics.get('recall')) < SNOWSLIDE_RECALL_FLOOR
    if precision_failed and recall_failed:
        return 'both'
    if precision_failed:
        return 'precision_burden'
    if recall_failed:
        return 'recall_burden'
    if _as_float(metrics.get('f1')) < SNOWSLIDE_F1_FLOOR:
        return 'f1_burden'
    if _as_float(metrics.get('false_positive_rate')) > SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING:
        return 'false_positive_rate_burden'
    return 'none'


def classify_recommendation(
    *,
    aggregate_metrics: dict[str, Any],
    per_scene: list[dict[str, Any]],
) -> dict[str, Any]:
    fp_ranked = sorted(per_scene, key=lambda row: (_as_float(row.get('fp_share')), int(row.get('fp', 0))), reverse=True)
    fn_ranked = sorted(per_scene, key=lambda row: (_as_float(row.get('fn_share')), int(row.get('fn', 0))), reverse=True)
    top_two_fp_share = sum(_as_float(row.get('fp_share')) for row in fp_ranked[:2])
    top_two_fn_share = sum(_as_float(row.get('fn_share')) for row in fn_ranked[:2])

    if top_two_fp_share >= 0.60 or top_two_fn_share >= 0.60:
        return {
            'recommendation': 'targeted_scene_label_data_review_no_training',
            'reason': 'one or two scenes account for most false-positive or false-negative burden',
            'top_two_fp_share': top_two_fp_share,
            'top_two_fn_share': top_two_fn_share,
            'future_gpu_training_allowed': False,
        }

    precision = _as_float(aggregate_metrics.get('precision'))
    recall = _as_float(aggregate_metrics.get('recall'))
    f1 = _as_float(aggregate_metrics.get('f1'))
    fpr = _as_float(aggregate_metrics.get('false_positive_rate'))
    close_to_floors = (
        precision >= SNOWSLIDE_PRECISION_FLOOR - 0.12
        and recall >= SNOWSLIDE_RECALL_FLOOR - 0.04
        and f1 >= SNOWSLIDE_F1_FLOOR - 0.07
        and fpr <= SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING
    )
    if close_to_floors:
        return {
            'recommendation': 'threshold_postprocess_only_retry',
            'reason': 'metrics are close enough to floors that evaluation-only threshold/component filtering should be tried before training',
            'future_gpu_training_allowed': False,
        }

    return {
        'recommendation': 'one_future_candidate_design',
        'reason': 'errors are broad enough that a future candidate may be scientifically warranted after this diagnostic is reviewed',
        'future_gpu_training_allowed': False,
    }


def _scene_id(scene: dict[str, Any], index: int) -> str:
    return str(scene.get('scene_id') or scene.get('id') or scene.get('region_key') or f'scene-{index}')


def _scene_region(scene: dict[str, Any]) -> str:
    return str(scene.get('region_key') or scene.get('region') or 'unknown')


def _shape(value: np.ndarray) -> list[int]:
    return [int(item) for item in value.shape]


def _per_scene_rows(
    *,
    scenes: list[dict[str, Any]],
    prediction_probabilities: list[np.ndarray],
    truths: list[np.ndarray],
    baselines: list[np.ndarray],
    threshold: float,
    truth_threshold: float,
    component_area: int,
    opening_size: int,
    top_components: int,
) -> tuple[list[dict[str, Any]], list[np.ndarray], list[np.ndarray]]:
    rows: list[dict[str, Any]] = []
    binary_predictions: list[np.ndarray] = []
    binary_truths: list[np.ndarray] = []
    for index, (scene, probability, truth) in enumerate(zip(scenes, prediction_probabilities, truths, strict=True), start=1):
        scene_name = _scene_id(scene, index)
        prediction = _postprocess_binary_mask(
            np.asarray(probability, dtype=np.float32) >= threshold,
            min_component_area_px=component_area,
            opening_size_px=opening_size,
        )
        binary_truth = np.asarray(truth, dtype=bool)
        metrics = compute_mask_metrics([prediction], [binary_truth])
        fp_mask = prediction & ~binary_truth
        fn_mask = ~prediction & binary_truth
        row: dict[str, Any] = {
            'scene_id': scene_name,
            'region_key': _scene_region(scene),
            'mask_shape': _shape(probability),
            'truth_shape': _shape(binary_truth),
            'prediction_threshold': threshold,
            'truth_threshold': truth_threshold,
            'postprocess_min_component_area_px': component_area,
            'postprocess_opening_size_px': opening_size,
            **{key: metrics[key] for key in ('tp', 'fp', 'fn', 'tn', 'precision', 'recall', 'f1', 'iou', 'false_positive_rate')},
            'top_false_positive_components': _component_summaries(
                fp_mask,
                scene_id=scene_name,
                patch_id=scene_name,
                component_type='false_positive',
                limit=top_components,
            ),
            'top_false_negative_components': _component_summaries(
                fn_mask,
                scene_id=scene_name,
                patch_id=scene_name,
                component_type='false_negative',
                limit=top_components,
            ),
        }
        if index <= len(baselines):
            baseline = np.asarray(baselines[index - 1], dtype=bool)
            if baseline.shape == binary_truth.shape:
                row['baseline_metrics'] = compute_mask_metrics([baseline], [binary_truth])
        rows.append(row)
        binary_predictions.append(prediction)
        binary_truths.append(binary_truth)
    return rows, binary_predictions, binary_truths


def _add_error_shares(per_scene: list[dict[str, Any]]) -> None:
    total_fp = sum(int(row.get('fp', 0)) for row in per_scene)
    total_fn = sum(int(row.get('fn', 0)) for row in per_scene)
    for row in per_scene:
        fp = int(row.get('fp', 0))
        fn = int(row.get('fn', 0))
        row['fp_share'] = fp / max(total_fp, 1)
        row['fn_share'] = fn / max(total_fn, 1)
        row['acceptance_impact_score'] = row['fp_share'] + row['fn_share']


def _rankings(per_scene: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    keys = ('scene_id', 'region_key', 'tp', 'fp', 'fn', 'tn', 'precision', 'recall', 'f1', 'iou', 'false_positive_rate', 'fp_share', 'fn_share', 'acceptance_impact_score')

    def compact(row: dict[str, Any]) -> dict[str, Any]:
        return {key: row[key] for key in keys if key in row}

    return {
        'false_positive_burden': [
            compact(row)
            for row in sorted(per_scene, key=lambda item: (_as_float(item.get('fp_share')), int(item.get('fp', 0))), reverse=True)
        ],
        'false_negative_burden': [
            compact(row)
            for row in sorted(per_scene, key=lambda item: (_as_float(item.get('fn_share')), int(item.get('fn', 0))), reverse=True)
        ],
        'acceptance_impact': [
            compact(row)
            for row in sorted(per_scene, key=lambda item: _as_float(item.get('acceptance_impact_score')), reverse=True)
        ],
    }


def _render_markdown(report: dict[str, Any], decision: dict[str, Any]) -> str:
    metrics = report['aggregate_metrics']
    rankings = report['scene_rankings']
    blockers = ', '.join(item['gate'] for item in report['acceptance_floor_failures']) or 'none'
    lines = [
        '# SnowSlide v5 Error Diagnostics',
        '',
        f"- Decision: `{decision['decision']}`",
        f"- Dominant blocker: `{report['dominant_blocker']}`",
        f"- Recommendation: `{decision['recommendation']}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Failed research-grade floors: {blockers}",
        '',
        '## Aggregate Metrics',
        '',
        '| Metric | Value | Floor |',
        '|---|---:|---:|',
        f"| Precision | {metrics['precision']:.6f} | {SNOWSLIDE_PRECISION_FLOOR:.2f} |",
        f"| Recall | {metrics['recall']:.6f} | {SNOWSLIDE_RECALL_FLOOR:.2f} |",
        f"| F1 | {metrics['f1']:.6f} | {SNOWSLIDE_F1_FLOOR:.2f} |",
        f"| IoU | {metrics['iou']:.6f} | n/a |",
        f"| False-positive rate | {metrics['false_positive_rate']:.6f} | <= {SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING:.3f} |",
        '',
        '## Top False-Positive Burden',
        '',
        '| Scene | FP | FP share | Precision | F1 |',
        '|---|---:|---:|---:|---:|',
    ]
    for row in rankings['false_positive_burden'][:5]:
        lines.append(
            f"| {row['scene_id']} | {row['fp']} | {row['fp_share']:.3f} | "
            f"{row['precision']:.3f} | {row['f1']:.3f} |",
        )
    lines.extend([
        '',
        '## Top False-Negative Burden',
        '',
        '| Scene | FN | FN share | Recall | F1 |',
        '|---|---:|---:|---:|---:|',
    ])
    for row in rankings['false_negative_burden'][:5]:
        lines.append(
            f"| {row['scene_id']} | {row['fn']} | {row['fn_share']:.3f} | "
            f"{row['recall']:.3f} | {row['f1']:.3f} |",
        )
    lines.extend([
        '',
        '## Scientific Recommendation',
        '',
        decision['reason'],
        '',
        'No additional GPU training is authorized by this diagnostic artifact.',
        '',
    ])
    return '\n'.join(lines)


def build_diagnostics(
    *,
    request_path: Path,
    acceptance_report_path: Path,
    materialization_result_dir: Path,
    output_root: Path,
    env_file: Path | None = None,
    top_components: int = 5,
) -> dict[str, Any]:
    request = _load_json(request_path)
    acceptance_report = _load_json(acceptance_report_path)
    manifest = _manifest_from_request(request, env_file=env_file)
    scenes, prediction_probabilities, truths, baselines = _load_scene_arrays(manifest)
    threshold = float(request.get('prediction_threshold') or request.get('threshold') or manifest.get('prediction_threshold') or 0.5)
    truth_threshold = float(request.get('truth_threshold') or manifest.get('truth_threshold') or 0.5)
    component_area = int(request.get('postprocess_min_component_area_px') or manifest.get('postprocess_min_component_area_px') or 0)
    opening_size = int(request.get('postprocess_opening_size_px') or manifest.get('postprocess_opening_size_px') or 0)

    per_scene, binary_predictions, binary_truths = _per_scene_rows(
        scenes=scenes,
        prediction_probabilities=prediction_probabilities,
        truths=truths,
        baselines=baselines,
        threshold=threshold,
        truth_threshold=truth_threshold,
        component_area=component_area,
        opening_size=opening_size,
        top_components=top_components,
    )
    _add_error_shares(per_scene)
    aggregate_metrics = compute_mask_metrics(binary_predictions, binary_truths)
    aggregate_metrics.update({
        'dry_run': True,
        'prediction_threshold': threshold,
        'truth_threshold': truth_threshold,
        'postprocess_min_component_area_px': component_area,
        'postprocess_opening_size_px': opening_size,
        'scene_count': len(per_scene),
    })
    if 'beats_baseline' in acceptance_report:
        aggregate_metrics['beats_baseline'] = bool(acceptance_report.get('beats_baseline'))
    elif isinstance(acceptance_report.get('metrics'), dict):
        aggregate_metrics['beats_baseline'] = bool(acceptance_report['metrics'].get('beats_baseline'))

    rankings = _rankings(per_scene)
    recommendation = classify_recommendation(
        aggregate_metrics=aggregate_metrics,
        per_scene=per_scene,
    )
    materialization_summary = summarize_materialization_results(materialization_result_dir)
    floor_failures = _acceptance_floor_failures(aggregate_metrics)
    dominant_blocker = classify_dominant_blocker(aggregate_metrics)
    scene_ids = [row['scene_id'] for row in per_scene]
    missing_materialized = list(materialization_summary.get('missing_scene_ids') or [])

    report = {
        'version': 'snowslide_sar_error_diagnostics_v1',
        'generated_at': _now_iso(),
        'policy_version': SNOWSLIDE_RESEARCH_GRADE_POLICY_VERSION,
        'source_request': str(request_path),
        'acceptance_report': str(acceptance_report_path),
        'materialization_result_dir': str(materialization_result_dir),
        'production_scoring_allowed': False,
        'decision': 'blocked_shadow_only',
        'promotion_allowed': False,
        'gpu_training_launched': False,
        'modal_gpu_call_launched': False,
        'aggregate_metrics': aggregate_metrics,
        'acceptance_floors': {
            'precision': SNOWSLIDE_PRECISION_FLOOR,
            'recall': SNOWSLIDE_RECALL_FLOOR,
            'f1': SNOWSLIDE_F1_FLOOR,
            'false_positive_rate': SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING,
        },
        'acceptance_floor_failures': floor_failures,
        'dominant_blocker': dominant_blocker,
        'scene_count': len(scene_ids),
        'scene_ids': scene_ids,
        'materialization_summary': materialization_summary,
        'materialization_missing_scene_ids': missing_materialized,
        'per_scene': per_scene,
        'scene_rankings': rankings,
        'recommendation': recommendation,
    }
    decision = {
        'version': 'snowslide_next_candidate_decision_v1',
        'generated_at': report['generated_at'],
        'decision': 'blocked_shadow_only',
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'dominant_blocker': dominant_blocker,
        'recommendation': recommendation['recommendation'],
        'reason': recommendation['reason'],
        'future_gpu_training_allowed': False,
        'next_gpu_run_authorized': False,
        'requires_human_review': True,
        'acceptance_floor_failures': floor_failures,
        'top_false_positive_scenes': rankings['false_positive_burden'][:3],
        'top_false_negative_scenes': rankings['false_negative_burden'][:3],
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'sar_error_diagnostics.json', report)
    _write_json(output_root / 'next_candidate_decision.json', decision)
    (output_root / 'sar_error_diagnostics.md').write_text(_render_markdown(report, decision), encoding='utf-8')
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build diagnostic-only SnowSlide SAR error report from existing masks.')
    parser.add_argument('--request', type=Path, default=DEFAULT_REQUEST)
    parser.add_argument('--acceptance-report', type=Path, default=DEFAULT_ACCEPTANCE_REPORT)
    parser.add_argument('--materialization-result-dir', type=Path, default=DEFAULT_MATERIALIZATION_DIR)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--env-file', type=Path, default=None)
    parser.add_argument('--top-components', type=int, default=5)
    args = parser.parse_args(argv)
    report = build_diagnostics(
        request_path=args.request,
        acceptance_report_path=args.acceptance_report,
        materialization_result_dir=args.materialization_result_dir,
        output_root=args.output_root,
        env_file=args.env_file,
        top_components=args.top_components,
    )
    print(json.dumps({
        'status': 'ok',
        'output_root': str(args.output_root),
        'decision': report['decision'],
        'dominant_blocker': report['dominant_blocker'],
        'recommendation': report['recommendation']['recommendation'],
        'production_scoring_allowed': report['production_scoring_allowed'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
