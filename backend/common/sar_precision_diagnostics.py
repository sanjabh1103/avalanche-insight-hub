from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SAR_PRECISION_DIAGNOSTICS_VERSION = 'sar_precision_diagnostics_v1'
DEFAULT_PRECISION_FLOOR = 0.60
DEFAULT_RECALL_FLOOR = 0.50


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _f_beta(precision: float, recall: float, beta: float) -> float:
    beta_sq = float(beta) ** 2
    return (1.0 + beta_sq) * precision * recall / max((beta_sq * precision) + recall, 1e-9)


def _rank_scenes(scene_breakdown: list[dict[str, Any]]) -> dict[str, Any]:
    if not scene_breakdown:
        return {
            'weakest_precision_scene': None,
            'largest_fp_volume_scene': None,
            'scene_fp_burden': [],
        }

    normalized: list[dict[str, Any]] = []
    for scene in scene_breakdown:
        precision = _as_float(scene.get('precision'))
        fp = _as_int(scene.get('fp'))
        tp = _as_int(scene.get('tp'))
        normalized.append({
            'scene_id': str(scene.get('scene_id') or ''),
            'region_key': str(scene.get('region_key') or 'unknown'),
            'precision': precision,
            'recall': _as_float(scene.get('recall')),
            'f1': _as_float(scene.get('f1')),
            'false_positive_rate': _as_float(scene.get('false_positive_rate')),
            'fp': fp,
            'tp': tp,
            'fn': _as_int(scene.get('fn')),
            'tn': _as_int(scene.get('tn')),
            'fp_share_of_predictions': fp / max(fp + tp, 1),
            'predicted_positive_rate': _as_float(scene.get('predicted_positive_rate')),
            'truth_positive_rate': _as_float(scene.get('truth_positive_rate')),
            'positive_rate_ratio': _as_float(scene.get('positive_rate_ratio')),
        })

    return {
        'weakest_precision_scene': min(normalized, key=lambda item: (item['precision'], -item['fp'])),
        'largest_fp_volume_scene': max(normalized, key=lambda item: item['fp']),
        'scene_fp_burden': sorted(normalized, key=lambda item: item['fp'], reverse=True),
    }


def _region_burden(metrics_payload: dict[str, Any], scene_breakdown: list[dict[str, Any]]) -> list[dict[str, Any]]:
    region_breakdown = metrics_payload.get('region_breakdown')
    if not isinstance(region_breakdown, dict):
        artifact = metrics_payload.get('sar_prediction_artifact')
        region_breakdown = artifact.get('region_breakdown') if isinstance(artifact, dict) else None
    if not isinstance(region_breakdown, dict):
        by_region: dict[str, dict[str, int]] = {}
        for scene in scene_breakdown:
            region = str(scene.get('region_key') or 'unknown')
            counts = by_region.setdefault(region, {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0})
            for key in counts:
                counts[key] += _as_int(scene.get(key))
        region_breakdown = by_region

    rows: list[dict[str, Any]] = []
    for region, raw in region_breakdown.items():
        if not isinstance(raw, dict):
            continue
        tp = _as_int(raw.get('tp'))
        fp = _as_int(raw.get('fp'))
        fn = _as_int(raw.get('fn'))
        tn = _as_int(raw.get('tn'))
        precision = _as_float(raw.get('precision'), tp / max(tp + fp, 1))
        recall = _as_float(raw.get('recall'), tp / max(tp + fn, 1))
        rows.append({
            'region_key': str(region),
            'precision': precision,
            'recall': recall,
            'f1': _as_float(raw.get('f1'), (2.0 * precision * recall) / max(precision + recall, 1e-9)),
            'false_positive_rate': _as_float(raw.get('false_positive_rate'), fp / max(fp + tn, 1)),
            'fp': fp,
            'tp': tp,
            'fn': fn,
            'tn': tn,
            'fp_share_of_predictions': fp / max(fp + tp, 1),
        })
    return sorted(rows, key=lambda item: item['fp'], reverse=True)


def build_sar_precision_diagnostics(
    metrics_payload: dict[str, Any],
    *,
    source_path: str | Path | None = None,
    precision_floor: float = DEFAULT_PRECISION_FLOOR,
    recall_floor: float = DEFAULT_RECALL_FLOOR,
) -> dict[str, Any]:
    threshold_metrics = [
        dict(row)
        for row in metrics_payload.get('threshold_metrics', [])
        if isinstance(row, dict)
    ]
    for row in threshold_metrics:
        row['precision_floor_met'] = _as_float(row.get('precision')) >= float(precision_floor)
        row['recall_floor_met'] = _as_float(row.get('recall')) >= float(recall_floor)
        row['precision_recall_floor_met'] = bool(row['precision_floor_met'] and row['recall_floor_met'])
        row['f0_5'] = _f_beta(_as_float(row.get('precision')), _as_float(row.get('recall')), 0.5)

    validation_metrics = dict(metrics_payload.get('validation_metrics') or {})
    max_precision_row = max(
        threshold_metrics or [validation_metrics],
        key=lambda row: (_as_float(row.get('precision')), _as_float(row.get('recall'))),
    )
    best_f0_5_row = max(
        threshold_metrics or [validation_metrics],
        key=lambda row: (_as_float(row.get('f0_5'), _f_beta(_as_float(row.get('precision')), _as_float(row.get('recall')), 0.5)), _as_float(row.get('precision'))),
    )
    precision_floor_met = any(row['precision_floor_met'] for row in threshold_metrics) or (
        not threshold_metrics and _as_float(validation_metrics.get('precision')) >= float(precision_floor)
    )
    precision_recall_floor_met = any(row['precision_recall_floor_met'] for row in threshold_metrics) or (
        not threshold_metrics
        and _as_float(validation_metrics.get('precision')) >= float(precision_floor)
        and _as_float(validation_metrics.get('recall')) >= float(recall_floor)
    )
    recall_floor_met = any(row['precision_recall_floor_met'] for row in threshold_metrics) or (
        not threshold_metrics and _as_float(validation_metrics.get('recall')) >= float(recall_floor)
    )
    if not precision_floor_met:
        failure_reason = 'no_threshold_met_precision_floor'
    elif not precision_recall_floor_met:
        failure_reason = 'no_threshold_met_precision_and_recall_floor'
    else:
        failure_reason = None

    scene_breakdown = [
        dict(row)
        for row in metrics_payload.get('scene_breakdown', [])
        if isinstance(row, dict)
    ]
    scene_ranking = _rank_scenes(scene_breakdown)

    return {
        'version': SAR_PRECISION_DIAGNOSTICS_VERSION,
        'generated_at': _utc_now_iso(),
        'source_path': str(source_path) if source_path is not None else None,
        'model_version': metrics_payload.get('candidate_model_version') or metrics_payload.get('model_version'),
        'model_family': metrics_payload.get('model_family'),
        'dataset_version': (metrics_payload.get('dataset_audit') or {}).get('dataset_version'),
        'precision_floor': float(precision_floor),
        'recall_floor': float(recall_floor),
        'precision_floor_met': bool(precision_floor_met),
        'recall_floor_met': bool(recall_floor_met),
        'precision_recall_floor_met': bool(precision_recall_floor_met),
        'failure_reason': failure_reason,
        'selected_validation_metrics': validation_metrics,
        'max_precision': _as_float(max_precision_row.get('precision')),
        'best_precision_threshold': _as_float(max_precision_row.get('threshold')),
        'best_precision_recall': _as_float(max_precision_row.get('recall')),
        'best_f0_5_threshold': _as_float(best_f0_5_row.get('threshold')),
        'best_f0_5': _as_float(best_f0_5_row.get('f0_5'), _f_beta(_as_float(best_f0_5_row.get('precision')), _as_float(best_f0_5_row.get('recall')), 0.5)),
        'threshold_curve': threshold_metrics,
        'scene_diagnostics': scene_ranking,
        'region_fp_burden': _region_burden(metrics_payload, scene_breakdown),
        'flags': {
            'weakest_precision_scene_id': (
                scene_ranking['weakest_precision_scene']['scene_id']
                if scene_ranking['weakest_precision_scene'] else None
            ),
            'largest_fp_volume_scene_id': (
                scene_ranking['largest_fp_volume_scene']['scene_id']
                if scene_ranking['largest_fp_volume_scene'] else None
            ),
            'recommended_next_step': (
                'diagnostic_first_no_blind_training'
                if not precision_recall_floor_met
                else 'eligible_for_heldout_check'
            ),
        },
    }
