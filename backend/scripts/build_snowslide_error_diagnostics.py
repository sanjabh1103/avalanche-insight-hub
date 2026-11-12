from __future__ import annotations

import argparse
import csv
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
    evaluate_snowslide_research_grade,
    summarize_materialization_results,
)
from backend.sar_unet_training import _postprocess_binary_mask
from backend.sar_unet_worker import compute_mask_metrics
from backend.scripts.run_snowslide_threshold_sweep import _baseline_floor, _load_scene_arrays, _manifest_from_request


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
DEFAULT_RECOVERY_THRESHOLDS = (0.994, 0.995, 0.996, 0.997, 0.998, 0.999)
DEFAULT_RECOVERY_COMPONENT_AREAS = (0, 16, 32, 64, 96, 128)
DEFAULT_REVIEW_SCENE_IDS = ('nuuk_20160413', 'nuuk_20210411', 'pish_20230221')


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


def _parse_float_list(raw: str | None, default: tuple[float, ...]) -> list[float]:
    if not raw:
        return list(default)
    return [float(item.strip()) for item in raw.split(',') if item.strip()]


def _parse_int_list(raw: str | None, default: tuple[int, ...]) -> list[int]:
    if not raw:
        return list(default)
    return [int(item.strip()) for item in raw.split(',') if item.strip()]


def _parse_str_list(raw: str | None, default: tuple[str, ...]) -> list[str]:
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(',') if item.strip()]


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


def _scene_bbox(scene: dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = scene.get('bbox')
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        west, south, east, north = (float(item) for item in bbox)
    except (TypeError, ValueError):
        return None
    if east <= west or north <= south:
        return None
    return west, south, east, north


def _pixel_bbox_to_geo(
    *,
    pixel_bbox: dict[str, int],
    shape: tuple[int, int],
    scene_bbox: tuple[float, float, float, float] | None,
) -> dict[str, float] | None:
    if scene_bbox is None:
        return None
    height, width = int(shape[0]), int(shape[1])
    if height <= 0 or width <= 0:
        return None
    west, south, east, north = scene_bbox
    col_min = int(pixel_bbox['col_min'])
    col_max = int(pixel_bbox['col_max_exclusive'])
    row_min = int(pixel_bbox['row_min'])
    row_max = int(pixel_bbox['row_max_exclusive'])
    return {
        'west': west + (col_min / width) * (east - west),
        'east': west + (col_max / width) * (east - west),
        'north': north - (row_min / height) * (north - south),
        'south': north - (row_max / height) * (north - south),
    }


def _component_details(
    mask: np.ndarray,
    *,
    scene: dict[str, Any],
    scene_id: str,
    component_type: str,
    limit: int,
) -> list[dict[str, Any]]:
    binary = np.asarray(mask, dtype=bool)
    if not np.any(binary):
        return []
    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - scipy is part of backend requirements
        raise RuntimeError('scipy is required for SnowSlide component review packets') from exc

    labeled, component_count = ndimage.label(binary)
    if component_count <= 0:
        return []
    slices = ndimage.find_objects(labeled)
    scene_geo_bbox = _scene_bbox(scene)
    rows: list[dict[str, Any]] = []
    for component_index, component_slice in enumerate(slices, start=1):
        if component_slice is None:
            continue
        component_mask = labeled[component_slice] == component_index
        pixel_count = int(np.sum(component_mask))
        if pixel_count <= 0:
            continue
        row_slice, col_slice = component_slice
        absolute_rows, absolute_cols = np.where(labeled == component_index)
        centroid_row = float(np.mean(absolute_rows))
        centroid_col = float(np.mean(absolute_cols))
        pixel_bbox = {
            'row_min': int(row_slice.start),
            'row_max_exclusive': int(row_slice.stop),
            'col_min': int(col_slice.start),
            'col_max_exclusive': int(col_slice.stop),
        }
        rows.append({
            'scene_id': scene_id,
            'region_key': _scene_region(scene),
            'component_type': component_type,
            'component_index': int(component_index),
            'pixel_count': pixel_count,
            'pixel_bbox': pixel_bbox,
            'pixel_extent': {
                'height_px': int(row_slice.stop - row_slice.start),
                'width_px': int(col_slice.stop - col_slice.start),
            },
            'pixel_centroid': {
                'row': centroid_row,
                'col': centroid_col,
            },
            'geo_bbox': _pixel_bbox_to_geo(
                pixel_bbox=pixel_bbox,
                shape=binary.shape,
                scene_bbox=scene_geo_bbox,
            ),
        })
    return sorted(rows, key=lambda row: row['pixel_count'], reverse=True)[:limit]


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
            'top_false_positive_components': _component_details(
                fp_mask,
                scene=scene,
                scene_id=scene_name,
                component_type='false_positive',
                limit=top_components,
            ),
            'top_false_negative_components': _component_details(
                fn_mask,
                scene=scene,
                scene_id=scene_name,
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


def _review_priority_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _as_float(row.get('fn_share')) >= 0.10:
        reasons.append('high_false_negative_share')
    if _as_float(row.get('fp_share')) >= 0.10:
        reasons.append('high_false_positive_share')
    if _as_float(row.get('precision')) < SNOWSLIDE_PRECISION_FLOOR:
        reasons.append('precision_below_research_floor')
    if _as_float(row.get('recall')) < SNOWSLIDE_RECALL_FLOOR:
        reasons.append('recall_below_research_floor')
    if _as_float(row.get('false_positive_rate')) > SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING:
        reasons.append('false_positive_rate_above_research_ceiling')
    return reasons or ['included_for_context']


def _build_scene_review_packet(
    *,
    per_scene: list[dict[str, Any]],
    review_scene_ids: list[str],
    generated_at: str,
) -> dict[str, Any]:
    rows_by_id = {str(row.get('scene_id')): row for row in per_scene}
    selected_rows = [rows_by_id[scene_id] for scene_id in review_scene_ids if scene_id in rows_by_id]
    if not selected_rows:
        selected_rows = sorted(
            per_scene,
            key=lambda row: _as_float(row.get('acceptance_impact_score')),
            reverse=True,
        )[:3]

    review_scenes: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    for priority_rank, row in enumerate(
        sorted(selected_rows, key=lambda item: _as_float(item.get('acceptance_impact_score')), reverse=True),
        start=1,
    ):
        scene_id = str(row['scene_id'])
        components = []
        for component_type, source_key in (
            ('false_positive', 'top_false_positive_components'),
            ('false_negative', 'top_false_negative_components'),
        ):
            for component_rank, component in enumerate(row.get(source_key) or [], start=1):
                component_row = {
                    'scene_id': scene_id,
                    'review_priority_rank': priority_rank,
                    'component_rank': component_rank,
                    'component_type': component_type,
                    **component,
                }
                components.append(component_row)
                component_rows.append(component_row)
        review_scenes.append({
            'scene_id': scene_id,
            'region_key': row.get('region_key'),
            'review_priority_rank': priority_rank,
            'review_priority_reasons': _review_priority_reasons(row),
            'metrics': {
                key: row.get(key)
                for key in ('tp', 'fp', 'fn', 'tn', 'precision', 'recall', 'f1', 'iou', 'false_positive_rate', 'fp_share', 'fn_share')
            },
            'top_components': components,
        })

    return {
        'version': 'snowslide_scene_review_packet_v1',
        'generated_at': generated_at,
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'next_gpu_run_authorized': False,
        'review_scene_ids_requested': review_scene_ids,
        'review_scene_count': len(review_scenes),
        'review_scenes': review_scenes,
        'component_rows': component_rows,
    }


def _render_scene_review_markdown(packet: dict[str, Any]) -> str:
    lines = [
        '# SnowSlide v5 Scene Review Packet',
        '',
        f"- Production scoring allowed: `{str(packet['production_scoring_allowed']).lower()}`",
        f"- Next GPU run authorized: `{str(packet['next_gpu_run_authorized']).lower()}`",
        '',
        '| Rank | Scene | Reasons | Precision | Recall | F1 | FP share | FN share |',
        '|---:|---|---|---:|---:|---:|---:|---:|',
    ]
    for scene in packet['review_scenes']:
        metrics = scene['metrics']
        lines.append(
            f"| {scene['review_priority_rank']} | {scene['scene_id']} | "
            f"{', '.join(scene['review_priority_reasons'])} | "
            f"{_as_float(metrics.get('precision')):.3f} | "
            f"{_as_float(metrics.get('recall')):.3f} | "
            f"{_as_float(metrics.get('f1')):.3f} | "
            f"{_as_float(metrics.get('fp_share')):.3f} | "
            f"{_as_float(metrics.get('fn_share')):.3f} |",
        )
    lines.extend([
        '',
        '## Component Review',
        '',
        '| Scene | Type | Rank | Pixels | Pixel bbox | Pixel centroid |',
        '|---|---|---:|---:|---|---|',
    ])
    for row in packet['component_rows'][:30]:
        centroid = row.get('pixel_centroid') or {}
        lines.append(
            f"| {row['scene_id']} | {row['component_type']} | {row['component_rank']} | "
            f"{row['pixel_count']} | {json.dumps(row.get('pixel_bbox'), sort_keys=True)} | "
            f"({ _as_float(centroid.get('row')):.1f}, { _as_float(centroid.get('col')):.1f}) |",
        )
    lines.append('')
    return '\n'.join(lines)


def _write_component_review_csv(path: Path, component_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'scene_id',
        'review_priority_rank',
        'component_type',
        'component_rank',
        'pixel_count',
        'row_min',
        'row_max_exclusive',
        'col_min',
        'col_max_exclusive',
        'centroid_row',
        'centroid_col',
        'geo_west',
        'geo_south',
        'geo_east',
        'geo_north',
    ]
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in component_rows:
            pixel_bbox = row.get('pixel_bbox') or {}
            centroid = row.get('pixel_centroid') or {}
            geo_bbox = row.get('geo_bbox') or {}
            writer.writerow({
                'scene_id': row.get('scene_id'),
                'review_priority_rank': row.get('review_priority_rank'),
                'component_type': row.get('component_type'),
                'component_rank': row.get('component_rank'),
                'pixel_count': row.get('pixel_count'),
                'row_min': pixel_bbox.get('row_min'),
                'row_max_exclusive': pixel_bbox.get('row_max_exclusive'),
                'col_min': pixel_bbox.get('col_min'),
                'col_max_exclusive': pixel_bbox.get('col_max_exclusive'),
                'centroid_row': centroid.get('row'),
                'centroid_col': centroid.get('col'),
                'geo_west': geo_bbox.get('west'),
                'geo_south': geo_bbox.get('south'),
                'geo_east': geo_bbox.get('east'),
                'geo_north': geo_bbox.get('north'),
            })


def _candidate_metrics(
    *,
    scenes: list[dict[str, Any]],
    raw_predictions: list[np.ndarray],
    truths: list[np.ndarray],
    threshold: float,
    component_area: int,
    opening_size: int,
    baseline_f1_floor: float,
    request: dict[str, Any],
) -> dict[str, Any]:
    binary_predictions = [
        _postprocess_binary_mask(
            np.asarray(prediction, dtype=np.float32) >= threshold,
            min_component_area_px=component_area,
            opening_size_px=opening_size,
        )
        for prediction in raw_predictions
    ]
    metrics = compute_mask_metrics(binary_predictions, truths)
    metrics.update({
        'status': 'ok',
        'dry_run': True,
        'prediction_threshold': threshold,
        'truth_threshold': float(request.get('truth_threshold') or 0.5),
        'postprocess_min_component_area_px': component_area,
        'postprocess_opening_size_px': opening_size,
        'baseline_f1_floor_used': baseline_f1_floor,
        'beats_baseline': bool(float(metrics.get('f1') or 0.0) > baseline_f1_floor),
        'scene_count': len(scenes),
        'region_coverage': sorted(str(scene.get('scene_id')) for scene in scenes),
        'model_version': request.get('prediction_model_version') or request.get('model_version'),
    })
    return metrics


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, float, float, float, float]:
    metrics = row.get('metrics') if isinstance(row.get('metrics'), dict) else {}
    met_count = sum(
        1
        for key in ('precision_floor_met', 'recall_floor_met', 'f1_floor_met', 'false_positive_rate_ceiling_met')
        if row.get(key) is True
    )
    return (
        100 if row.get('research_grade_floor_met') is True else met_count,
        _as_float(metrics.get('f1')),
        _as_float(metrics.get('precision')),
        _as_float(metrics.get('recall')),
        -_as_float(metrics.get('false_positive_rate')),
    )


def _candidate_row(
    *,
    metrics: dict[str, Any],
    threshold: float,
    component_area: int,
    opening_size: int,
    scope: str,
    acceptance_allowed: bool,
    scene_ids: list[str],
) -> dict[str, Any]:
    precision_floor_met = _as_float(metrics.get('precision')) >= SNOWSLIDE_PRECISION_FLOOR
    recall_floor_met = _as_float(metrics.get('recall')) >= SNOWSLIDE_RECALL_FLOOR
    f1_floor_met = _as_float(metrics.get('f1')) >= SNOWSLIDE_F1_FLOOR
    fpr_floor_met = _as_float(metrics.get('false_positive_rate')) <= SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING
    return {
        'scope': scope,
        'acceptance_allowed': acceptance_allowed,
        'threshold': threshold,
        'postprocess_min_component_area_px': component_area,
        'postprocess_opening_size_px': opening_size,
        'scene_ids': scene_ids,
        'metrics': {
            key: metrics.get(key)
            for key in ('precision', 'recall', 'f1', 'iou', 'false_positive_rate', 'tp', 'fp', 'fn', 'tn')
        },
        'beats_baseline': metrics.get('beats_baseline'),
        'precision_floor_met': precision_floor_met,
        'recall_floor_met': recall_floor_met,
        'f1_floor_met': f1_floor_met,
        'false_positive_rate_ceiling_met': fpr_floor_met,
        'research_grade_floor_met': (
            acceptance_allowed
            and bool(metrics.get('beats_baseline'))
            and precision_floor_met
            and recall_floor_met
            and f1_floor_met
            and fpr_floor_met
        ),
    }


def _build_eval_only_recovery_report(
    *,
    request: dict[str, Any],
    scenes: list[dict[str, Any]],
    raw_predictions: list[np.ndarray],
    truths: list[np.ndarray],
    baselines: list[np.ndarray],
    thresholds: list[float],
    component_areas: list[int],
    review_scene_ids: list[str],
    generated_at: str,
) -> dict[str, Any]:
    baseline_f1_floor, baseline_metrics = _baseline_floor(
        {'baseline_margin': float(request.get('baseline_margin') or 0.05), **request},
        baselines,
        truths,
    )
    scene_ids = [str(scene.get('scene_id')) for scene in scenes]
    candidates: list[dict[str, Any]] = []
    for threshold in thresholds:
        for component_area in component_areas:
            metrics = _candidate_metrics(
                scenes=scenes,
                raw_predictions=raw_predictions,
                truths=truths,
                threshold=threshold,
                component_area=component_area,
                opening_size=0,
                baseline_f1_floor=baseline_f1_floor,
                request=request,
            )
            policy = evaluate_snowslide_research_grade(
                metrics,
                qualification_set_used_for_model_selection=True,
                require_avalcd_provenance=False,
                require_materialization_summary=False,
                expected_scene_ids=tuple(scene_ids),
            )
            row = _candidate_row(
                metrics=metrics,
                threshold=threshold,
                component_area=component_area,
                opening_size=0,
                scope='all_scenes',
                acceptance_allowed=True,
                scene_ids=scene_ids,
            )
            row['policy'] = {
                'decision': policy.get('decision'),
                'metric_floors_met': policy.get('metric_floors_met'),
                'blockers': policy.get('blockers'),
            }
            candidates.append(row)

    review_indexes = [index for index, scene_id in enumerate(scene_ids) if scene_id in set(review_scene_ids)]
    targeted_candidates: list[dict[str, Any]] = []
    if review_indexes:
        targeted_scenes = [scenes[index] for index in review_indexes]
        targeted_predictions = [raw_predictions[index] for index in review_indexes]
        targeted_truths = [truths[index] for index in review_indexes]
        targeted_scene_ids = [scene_ids[index] for index in review_indexes]
        for threshold in thresholds:
            for component_area in component_areas:
                metrics = _candidate_metrics(
                    scenes=targeted_scenes,
                    raw_predictions=targeted_predictions,
                    truths=targeted_truths,
                    threshold=threshold,
                    component_area=component_area,
                    opening_size=0,
                    baseline_f1_floor=baseline_f1_floor,
                    request=request,
                )
                targeted_candidates.append(_candidate_row(
                    metrics=metrics,
                    threshold=threshold,
                    component_area=component_area,
                    opening_size=0,
                    scope='targeted_scene_sensitivity',
                    acceptance_allowed=False,
                    scene_ids=targeted_scene_ids,
                ))

    candidates.sort(key=_candidate_sort_key, reverse=True)
    targeted_candidates.sort(key=_candidate_sort_key, reverse=True)
    passing = [row for row in candidates if row.get('research_grade_floor_met') is True]
    selected = passing[0] if passing else candidates[0]
    return {
        'version': 'snowslide_eval_only_recovery_report_v1',
        'generated_at': generated_at,
        'decision': 'requires_fresh_final_holdout' if passing else 'blocked_research_grade',
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'gpu_training_launched': False,
        'next_gpu_run_authorized': False,
        'fresh_final_holdout_required': bool(passing),
        'scene_review_required_before_training': not bool(passing),
        'baseline_f1_floor_used': baseline_f1_floor,
        'baseline_metrics': baseline_metrics,
        'threshold_grid': thresholds,
        'component_area_grid': component_areas,
        'opening_size_grid': [0],
        'candidate_count': len(candidates),
        'passing_candidate_count': len(passing),
        'selected_candidate': selected,
        'targeted_scene_sensitivity': {
            'acceptance_allowed': False,
            'reason': 'targeted-scene sensitivity is diagnostic only; SnowSlide acceptance requires all seven scenes',
            'scene_ids': [scene_ids[index] for index in review_indexes],
            'best_candidate': targeted_candidates[0] if targeted_candidates else None,
            'candidates': targeted_candidates,
        },
        'candidates': candidates,
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
    recovery_thresholds: list[float] | None = None,
    recovery_component_areas: list[int] | None = None,
    review_scene_ids: list[str] | None = None,
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
    resolved_review_scene_ids = review_scene_ids or list(DEFAULT_REVIEW_SCENE_IDS)
    scene_review_packet = _build_scene_review_packet(
        per_scene=per_scene,
        review_scene_ids=resolved_review_scene_ids,
        generated_at=_now_iso(),
    )
    eval_only_recovery = _build_eval_only_recovery_report(
        request=request,
        scenes=scenes,
        raw_predictions=prediction_probabilities,
        truths=binary_truths,
        baselines=baselines,
        thresholds=recovery_thresholds or list(DEFAULT_RECOVERY_THRESHOLDS),
        component_areas=recovery_component_areas or list(DEFAULT_RECOVERY_COMPONENT_AREAS),
        review_scene_ids=resolved_review_scene_ids,
        generated_at=scene_review_packet['generated_at'],
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
        'scene_review_packet_ref': str(output_root / 'scene_review_packet.json'),
        'eval_only_recovery_report_ref': str(output_root / 'snowslide_eval_only_recovery_report.json'),
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
        'eval_only_recovery_decision': eval_only_recovery['decision'],
        'eval_only_passing_candidate_count': eval_only_recovery['passing_candidate_count'],
        'scene_review_required_before_training': bool(eval_only_recovery.get('scene_review_required_before_training')),
        'requires_human_review': True,
        'acceptance_floor_failures': floor_failures,
        'top_false_positive_scenes': rankings['false_positive_burden'][:3],
        'top_false_negative_scenes': rankings['false_negative_burden'][:3],
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'sar_error_diagnostics.json', report)
    _write_json(output_root / 'next_candidate_decision.json', decision)
    _write_json(output_root / 'scene_review_packet.json', scene_review_packet)
    _write_json(output_root / 'snowslide_eval_only_recovery_report.json', eval_only_recovery)
    (output_root / 'sar_error_diagnostics.md').write_text(_render_markdown(report, decision), encoding='utf-8')
    (output_root / 'scene_review_packet.md').write_text(_render_scene_review_markdown(scene_review_packet), encoding='utf-8')
    _write_component_review_csv(output_root / 'component_review_table.csv', scene_review_packet['component_rows'])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build diagnostic-only SnowSlide SAR error report from existing masks.')
    parser.add_argument('--request', type=Path, default=DEFAULT_REQUEST)
    parser.add_argument('--acceptance-report', type=Path, default=DEFAULT_ACCEPTANCE_REPORT)
    parser.add_argument('--materialization-result-dir', type=Path, default=DEFAULT_MATERIALIZATION_DIR)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--env-file', type=Path, default=None)
    parser.add_argument('--top-components', type=int, default=5)
    parser.add_argument('--recovery-threshold-grid', default=None, help='Comma-delimited evaluation-only threshold grid')
    parser.add_argument('--recovery-component-areas', default=None, help='Comma-delimited component-area grid')
    parser.add_argument('--review-scene-ids', default=None, help='Comma-delimited dominant scene IDs for the review packet')
    args = parser.parse_args(argv)
    report = build_diagnostics(
        request_path=args.request,
        acceptance_report_path=args.acceptance_report,
        materialization_result_dir=args.materialization_result_dir,
        output_root=args.output_root,
        env_file=args.env_file,
        top_components=args.top_components,
        recovery_thresholds=_parse_float_list(args.recovery_threshold_grid, DEFAULT_RECOVERY_THRESHOLDS),
        recovery_component_areas=_parse_int_list(args.recovery_component_areas, DEFAULT_RECOVERY_COMPONENT_AREAS),
        review_scene_ids=_parse_str_list(args.review_scene_ids, DEFAULT_REVIEW_SCENE_IDS),
    )
    recovery = _load_json(args.output_root / 'snowslide_eval_only_recovery_report.json')
    print(json.dumps({
        'status': 'ok',
        'output_root': str(args.output_root),
        'decision': report['decision'],
        'dominant_blocker': report['dominant_blocker'],
        'eval_only_recovery_decision': recovery['decision'],
        'eval_only_passing_candidate_count': recovery['passing_candidate_count'],
        'recommendation': report['recommendation']['recommendation'],
        'production_scoring_allowed': report['production_scoring_allowed'],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
