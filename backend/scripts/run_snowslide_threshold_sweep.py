from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.sar_acceptance_policy import evaluate_snowslide_research_grade
from backend.sar_release_manifest import ReleaseManifestOptions, build_release_manifest_from_reference_set
from backend.sar_unet_training import _postprocess_binary_mask
from backend.sar_unet_worker import _load_mask_array, compute_mask_metrics
from backend.scripts.bootstrap_release_gate import load_rollout_env


DEFAULT_THRESHOLDS = (0.985, 0.988, 0.990, 0.992, 0.994, 0.996, 0.998, 0.999)
DEFAULT_COMPONENT_AREAS = (0, 16, 32, 64, 96, 128)
DEFAULT_OPENING_SIZES = (0,)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'JSON artifact must contain an object: {path}')
    return payload


def _parse_float_list(raw: str | None, default: tuple[float, ...]) -> list[float]:
    if not raw:
        return list(default)
    return [float(item.strip()) for item in raw.split(',') if item.strip()]


def _parse_int_list(raw: str | None, default: tuple[int, ...]) -> list[int]:
    if not raw:
        return list(default)
    return [int(item.strip()) for item in raw.split(',') if item.strip()]


def _apply_env_file(env_file: Path | None) -> None:
    if env_file is None:
        return
    env = load_rollout_env(env_file)
    if env.supabase_url:
        os.environ['SUPABASE_URL'] = env.supabase_url
    if env.supabase_service_role_key:
        os.environ['SUPABASE_SERVICE_ROLE_KEY'] = env.supabase_service_role_key


def _manifest_from_request(request: dict[str, Any], *, env_file: Path | None) -> dict[str, Any]:
    scenes = request.get('scenes')
    if isinstance(scenes, list) and scenes:
        return {
            **request,
            'scenes': scenes,
            'baseline_margin': float(request.get('baseline_margin') or 0.05),
        }
    reference_set_key = str(request.get('reference_set_key') or '').strip()
    if not reference_set_key:
        raise ValueError('request must include scenes[] or reference_set_key')
    _apply_env_file(env_file)
    manifest = build_release_manifest_from_reference_set(
        reference_set_key=reference_set_key,
        options=ReleaseManifestOptions(
            baseline_margin=float(request.get('baseline_margin') or 0.05),
            validate_refs=False,
            authoritative_only=bool(request.get('authoritative_only', True)),
            prediction_model_version=str(
                request.get('prediction_model_version') or 'sar_unet_resnet34_shadow_v1'
            ),
            reference_set_key=reference_set_key,
        ),
    )
    return {**manifest, **{key: value for key, value in request.items() if key != 'scenes'}, 'scenes': manifest['scenes']}


def _load_scene_arrays(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    scenes = [scene for scene in manifest.get('scenes', []) if isinstance(scene, dict)]
    if not scenes:
        raise ValueError('manifest must contain scenes[]')
    predictions: list[np.ndarray] = []
    truths: list[np.ndarray] = []
    baselines: list[np.ndarray] = []
    for scene in scenes:
        if not scene.get('prediction_mask') or not scene.get('truth_mask'):
            raise ValueError(f'scene "{scene.get("scene_id")}" is missing prediction_mask or truth_mask')
        predictions.append(_load_mask_array(scene['prediction_mask']))
        truths.append(_load_mask_array(scene['truth_mask']) >= float(manifest.get('truth_threshold') or 0.5))
        if scene.get('baseline_mask'):
            baselines.append(_load_mask_array(scene['baseline_mask']) >= float(manifest.get('truth_threshold') or 0.5))
    return scenes, predictions, truths, baselines


def _prediction_value_summary(predictions: list[np.ndarray]) -> dict[str, Any]:
    minimum = min(float(np.nanmin(mask)) for mask in predictions)
    maximum = max(float(np.nanmax(mask)) for mask in predictions)
    sample_values: set[float] = set()
    for mask in predictions:
        unique = np.unique(mask)
        for value in unique[:32]:
            sample_values.add(float(value))
        if len(sample_values) > 64:
            break
    return {
        'min': minimum,
        'max': maximum,
        'sample_unique_value_count': len(sample_values),
        'sample_unique_values': sorted(sample_values)[:20],
        'appears_binary': len(sample_values) <= 2 and set(round(value, 6) for value in sample_values).issubset({0.0, 1.0}),
    }


def _baseline_floor(manifest: dict[str, Any], baselines: list[np.ndarray], truths: list[np.ndarray]) -> tuple[float, dict[str, Any] | None]:
    raw_floor = manifest.get('baseline_f1_floor')
    if raw_floor not in (None, ''):
        return float(raw_floor), None
    baseline_metrics = manifest.get('baseline_metrics') if isinstance(manifest.get('baseline_metrics'), dict) else None
    baseline_margin = float(manifest.get('baseline_margin') or 0.05)
    if baseline_metrics and float(baseline_metrics.get('f1') or 0.0) > 0.0:
        return float(baseline_metrics['f1']) + baseline_margin, {'source': 'manifest.baseline_metrics', **baseline_metrics}
    if baselines and len(baselines) == len(truths):
        computed = compute_mask_metrics(baselines, truths)
        return float(computed.get('f1') or 0.0) + baseline_margin, computed
    raise ValueError('threshold sweep requires baseline_f1_floor, baseline_metrics.f1, or per-scene baseline_mask values')


def _candidate_report(
    *,
    scenes: list[dict[str, Any]],
    predictions: list[np.ndarray],
    truths: list[np.ndarray],
    threshold: float,
    component_area: int,
    opening_size: int,
    baseline_f1_floor: float,
    baseline_metrics: dict[str, Any] | None,
    request: dict[str, Any],
) -> dict[str, Any]:
    binary_predictions = [
        _postprocess_binary_mask(
            prediction >= threshold,
            min_component_area_px=component_area,
            opening_size_px=opening_size,
        )
        for prediction in predictions
    ]
    metrics = compute_mask_metrics(binary_predictions, truths)
    metrics['status'] = 'ok'
    metrics['dry_run'] = True
    metrics['evaluated_at'] = _now_iso()
    metrics['prediction_threshold'] = threshold
    metrics['truth_threshold'] = float(request.get('truth_threshold') or 0.5)
    metrics['postprocess_min_component_area_px'] = component_area
    metrics['postprocess_opening_size_px'] = opening_size
    metrics['baseline_f1_floor_used'] = baseline_f1_floor
    metrics['baseline_margin'] = float(request.get('baseline_margin') or 0.05)
    if baseline_metrics is not None:
        metrics['baseline_metrics'] = baseline_metrics
    metrics['beats_baseline'] = bool(float(metrics.get('f1') or 0.0) > baseline_f1_floor)
    metrics['model_version'] = request.get('prediction_model_version') or request.get('model_version')
    metrics['region_coverage'] = sorted(str(scene.get('scene_id') or scene.get('region_key')) for scene in scenes)
    return metrics


def _ranking_key(row: dict[str, Any]) -> tuple[int, float, float, float]:
    policy = row.get('policy') if isinstance(row.get('policy'), dict) else {}
    floors = policy.get('metric_floors_met')
    metrics = row.get('metrics') if isinstance(row.get('metrics'), dict) else {}
    met_count = sum(
        1
        for key in ('precision_floor_met', 'recall_floor_met', 'f1_floor_met', 'false_positive_rate_ceiling_met')
        if row.get(key) is True
    )
    return (
        100 if floors is True else met_count,
        float(metrics.get('f1') or 0.0),
        float(metrics.get('precision') or 0.0),
        float(metrics.get('recall') or 0.0),
    )


def run_sweep(
    *,
    request_path: Path,
    output_path: Path,
    env_file: Path | None = None,
    threshold_grid: list[float] | None = None,
    component_areas: list[int] | None = None,
    opening_sizes: list[int] | None = None,
) -> dict[str, Any]:
    request = _load_json(request_path)
    manifest = _manifest_from_request(request, env_file=env_file)
    scenes, raw_predictions, truths, baselines = _load_scene_arrays(manifest)
    baseline_f1_floor, baseline_metrics = _baseline_floor(manifest, baselines, truths)
    thresholds = threshold_grid or list(DEFAULT_THRESHOLDS)
    areas = component_areas or list(DEFAULT_COMPONENT_AREAS)
    openings = opening_sizes or list(DEFAULT_OPENING_SIZES)
    candidates: list[dict[str, Any]] = []
    for threshold in thresholds:
        for area in areas:
            for opening in openings:
                metrics = _candidate_report(
                    scenes=scenes,
                    predictions=raw_predictions,
                    truths=truths,
                    threshold=threshold,
                    component_area=area,
                    opening_size=opening,
                    baseline_f1_floor=baseline_f1_floor,
                    baseline_metrics=baseline_metrics,
                    request=request,
                )
                policy = evaluate_snowslide_research_grade(
                    metrics,
                    qualification_set_used_for_model_selection=True,
                    require_avalcd_provenance=False,
                    require_materialization_summary=False,
                    expected_scene_ids=tuple(sorted(str(scene.get('scene_id')) for scene in scenes)),
                )
                candidates.append({
                    'threshold': threshold,
                    'postprocess_min_component_area_px': area,
                    'postprocess_opening_size_px': opening,
                    'metrics': {
                        key: metrics.get(key)
                        for key in ('precision', 'recall', 'f1', 'iou', 'false_positive_rate', 'tp', 'fp', 'fn', 'tn')
                    },
                    'beats_baseline': metrics.get('beats_baseline'),
                    'precision_floor_met': float(metrics.get('precision') or 0.0) >= 0.70,
                    'recall_floor_met': float(metrics.get('recall') or 0.0) >= 0.50,
                    'f1_floor_met': float(metrics.get('f1') or 0.0) >= 0.60,
                    'false_positive_rate_ceiling_met': float(metrics.get('false_positive_rate') or 0.0) <= 0.002,
                    'policy': {
                        'decision': policy.get('decision'),
                        'metric_floors_met': policy.get('metric_floors_met'),
                        'requires_fresh_final_holdout': policy.get('requires_fresh_final_holdout'),
                        'blockers': policy.get('blockers'),
                    },
                })
    candidates.sort(key=_ranking_key, reverse=True)
    passing = [row for row in candidates if row.get('policy', {}).get('decision') == 'requires_fresh_final_holdout']
    selected = passing[0] if passing else candidates[0]
    report = {
        'version': 'snowslide_threshold_sweep_report_v1',
        'generated_at': _now_iso(),
        'request_path': str(request_path),
        'decision': 'requires_fresh_final_holdout' if passing else 'blocked_research_grade',
        'bounded_candidate_warranted': not bool(passing),
        'avalcd_recheck_required': bool(passing),
        'fresh_final_holdout_required': bool(passing),
        'candidate_count': len(candidates),
        'passing_candidate_count': len(passing),
        'selected_candidate': selected,
        'prediction_value_summary': _prediction_value_summary(raw_predictions),
        'baseline_f1_floor_used': baseline_f1_floor,
        'scene_ids': sorted(str(scene.get('scene_id')) for scene in scenes),
        'candidates': candidates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run an evaluation-only SnowSlide threshold/postprocess sweep')
    parser.add_argument('--request', type=Path, required=True, help='Existing evaluate-release request JSON')
    parser.add_argument('--env-file', type=Path, help='Env file used only when request resolves a Supabase reference_set_key')
    parser.add_argument('--threshold-grid', help='Comma-delimited threshold grid')
    parser.add_argument('--component-areas', help='Comma-delimited component area grid')
    parser.add_argument('--opening-sizes', help='Comma-delimited opening-size grid')
    parser.add_argument('--output', type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_sweep(
        request_path=args.request,
        output_path=args.output,
        env_file=args.env_file,
        threshold_grid=_parse_float_list(args.threshold_grid, DEFAULT_THRESHOLDS),
        component_areas=_parse_int_list(args.component_areas, DEFAULT_COMPONENT_AREAS),
        opening_sizes=_parse_int_list(args.opening_sizes, DEFAULT_OPENING_SIZES),
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'bounded_candidate_warranted': report['bounded_candidate_warranted'],
        'avalcd_recheck_required': report['avalcd_recheck_required'],
        'passing_candidate_count': report['passing_candidate_count'],
        'output': str(args.output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
