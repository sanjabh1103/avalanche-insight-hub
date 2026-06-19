from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.sar_acceptance_policy import (
    SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING,
    SNOWSLIDE_PRECISION_FLOOR,
    SNOWSLIDE_RECALL_FLOOR,
)


DEFAULT_DIAGNOSTICS_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v5-2026-05-18/diagnostics',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required diagnostic input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'required diagnostic input must be a JSON object: {label} ({path})')
    return payload


def _load_component_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f'required diagnostic input not found: component_review_table ({path})')
    with path.open('r', encoding='utf-8', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ''):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _scene_by_id(scene_review_packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenes = scene_review_packet.get('review_scenes')
    if not isinstance(scenes, list):
        raise ValueError('scene_review_packet must include review_scenes[]')
    return {
        str(scene.get('scene_id')): scene
        for scene in scenes
        if isinstance(scene, dict) and scene.get('scene_id')
    }


def _scene_metrics(scene: dict[str, Any]) -> dict[str, float]:
    metrics = scene.get('metrics') if isinstance(scene.get('metrics'), dict) else {}
    return {
        'precision': _as_float(metrics.get('precision')),
        'recall': _as_float(metrics.get('recall')),
        'f1': _as_float(metrics.get('f1')),
        'false_positive_rate': _as_float(metrics.get('false_positive_rate')),
        'fp_share': _as_float(metrics.get('fp_share')),
        'fn_share': _as_float(metrics.get('fn_share')),
    }


def classify_scene_review(scene: dict[str, Any]) -> dict[str, Any]:
    metrics = _scene_metrics(scene)
    precision_gap = metrics['precision'] < SNOWSLIDE_PRECISION_FLOOR
    recall_gap = metrics['recall'] < SNOWSLIDE_RECALL_FLOOR
    high_fp_share = metrics['fp_share'] >= 0.25
    high_fn_share = metrics['fn_share'] >= 0.25
    fpr_gap = metrics['false_positive_rate'] > SNOWSLIDE_FALSE_POSITIVE_RATE_CEILING

    if high_fp_share and high_fn_share and abs(metrics['fp_share'] - metrics['fn_share']) <= 0.10:
        decision = 'mixed_precision_recall_review'
        buckets = ['scene_systematic_precision_gap', 'scene_systematic_recall_gap', 'no_training_until_reviewed']
        reason = 'false-positive and false-negative burden are both high and balanced'
    elif recall_gap or (high_fn_share and metrics['fn_share'] > metrics['fp_share']):
        decision = 'recall_first_label_or_threshold_review'
        buckets = ['scene_systematic_recall_gap', 'no_training_until_reviewed']
        reason = 'recall is below floor or false-negative burden dominates'
    elif precision_gap or high_fp_share or fpr_gap:
        decision = 'precision_first_label_or_terrain_review'
        buckets = ['scene_systematic_precision_gap', 'no_training_until_reviewed']
        reason = 'precision is below floor, false-positive share is high, or false-positive rate is above ceiling'
    else:
        decision = 'context_review_no_training'
        buckets = ['no_training_until_reviewed']
        reason = 'scene included for context but does not dominate a specific precision/recall gap'

    return {
        'scene_id': scene.get('scene_id'),
        'review_priority_rank': _as_int(scene.get('review_priority_rank')),
        'scene_review_decision': decision,
        'review_buckets': buckets,
        'reason': reason,
        'metrics': metrics,
    }


def _component_bucket(component_type: str) -> str:
    if component_type == 'false_negative':
        return 'large_false_negative_label_or_threshold_review'
    if component_type == 'false_positive':
        return 'large_false_positive_label_or_terrain_review'
    return 'no_training_until_reviewed'


def _component_action(row: dict[str, Any], scene_decision: dict[str, Any]) -> dict[str, Any]:
    component_type = str(row.get('component_type') or '')
    return {
        'scene_id': row.get('scene_id'),
        'review_priority_rank': _as_int(row.get('review_priority_rank')),
        'scene_review_decision': scene_decision['scene_review_decision'],
        'scene_review_buckets': scene_decision['review_buckets'],
        'component_type': component_type,
        'component_rank': _as_int(row.get('component_rank')),
        'component_review_bucket': _component_bucket(component_type),
        'blocking_bucket': 'no_training_until_reviewed',
        'pixel_count': _as_int(row.get('pixel_count')),
        'pixel_bbox': {
            'row_min': _as_int(row.get('row_min')),
            'row_max_exclusive': _as_int(row.get('row_max_exclusive')),
            'col_min': _as_int(row.get('col_min')),
            'col_max_exclusive': _as_int(row.get('col_max_exclusive')),
        },
        'pixel_centroid': {
            'row': _as_float(row.get('centroid_row')),
            'col': _as_float(row.get('centroid_col')),
        },
        'geo_bbox': {
            'west': _as_float(row.get('geo_west')),
            'south': _as_float(row.get('geo_south')),
            'east': _as_float(row.get('geo_east')),
            'north': _as_float(row.get('geo_north')),
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _write_actions_csv(path: Path, actions: list[dict[str, Any]]) -> None:
    fieldnames = [
        'scene_id',
        'review_priority_rank',
        'scene_review_decision',
        'scene_review_buckets',
        'component_type',
        'component_rank',
        'component_review_bucket',
        'blocking_bucket',
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for action in actions:
            pixel_bbox = action['pixel_bbox']
            centroid = action['pixel_centroid']
            geo_bbox = action['geo_bbox']
            writer.writerow({
                'scene_id': action['scene_id'],
                'review_priority_rank': action['review_priority_rank'],
                'scene_review_decision': action['scene_review_decision'],
                'scene_review_buckets': ';'.join(action['scene_review_buckets']),
                'component_type': action['component_type'],
                'component_rank': action['component_rank'],
                'component_review_bucket': action['component_review_bucket'],
                'blocking_bucket': action['blocking_bucket'],
                'pixel_count': action['pixel_count'],
                'row_min': pixel_bbox['row_min'],
                'row_max_exclusive': pixel_bbox['row_max_exclusive'],
                'col_min': pixel_bbox['col_min'],
                'col_max_exclusive': pixel_bbox['col_max_exclusive'],
                'centroid_row': centroid['row'],
                'centroid_col': centroid['col'],
                'geo_west': geo_bbox['west'],
                'geo_south': geo_bbox['south'],
                'geo_east': geo_bbox['east'],
                'geo_north': geo_bbox['north'],
            })


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        '# SnowSlide v5 Component Review Summary',
        '',
        f"- Decision: `{summary['decision']}`",
        f"- Recommended next step: `{summary['recommended_next_step']}`",
        f"- Production scoring allowed: `{str(summary['production_scoring_allowed']).lower()}`",
        f"- Next GPU run authorized: `{str(summary['next_gpu_run_authorized']).lower()}`",
        '',
        '## Scene Decisions',
        '',
        '| Rank | Scene | Decision | Precision | Recall | F1 | FP share | FN share |',
        '|---:|---|---|---:|---:|---:|---:|---:|',
    ]
    for scene in summary['scene_review_decisions']:
        metrics = scene['metrics']
        lines.append(
            f"| {scene['review_priority_rank']} | {scene['scene_id']} | {scene['scene_review_decision']} | "
            f"{metrics['precision']:.3f} | {metrics['recall']:.3f} | {metrics['f1']:.3f} | "
            f"{metrics['fp_share']:.3f} | {metrics['fn_share']:.3f} |",
        )
    lines.extend([
        '',
        '## Top Actions',
        '',
        '| Scene | Type | Rank | Bucket | Pixels | Pixel bbox |',
        '|---|---|---:|---|---:|---|',
    ])
    for action in summary['component_review_actions'][:20]:
        lines.append(
            f"| {action['scene_id']} | {action['component_type']} | {action['component_rank']} | "
            f"{action['component_review_bucket']} | {action['pixel_count']} | "
            f"{json.dumps(action['pixel_bbox'], sort_keys=True)} |",
        )
    lines.extend([
        '',
        'No source labels were edited by this checkpoint. No GPU training is authorized until these component reviews are resolved.',
        '',
    ])
    return '\n'.join(lines)


def build_component_review_summary(
    *,
    component_review_table: Path,
    scene_review_packet: Path,
    sar_error_diagnostics: Path,
    eval_only_recovery_report: Path,
    output_root: Path,
) -> dict[str, Any]:
    component_rows = _load_component_rows(component_review_table)
    scene_packet = _load_json(scene_review_packet, label='scene_review_packet')
    error_report = _load_json(sar_error_diagnostics, label='sar_error_diagnostics')
    recovery_report = _load_json(eval_only_recovery_report, label='snowslide_eval_only_recovery_report')
    scenes = _scene_by_id(scene_packet)
    if not scenes:
        raise ValueError('scene_review_packet did not contain any review scenes')
    if not component_rows:
        raise ValueError('component_review_table did not contain any component rows')

    scene_decisions = [
        classify_scene_review(scene)
        for scene in sorted(scenes.values(), key=lambda item: _as_int(item.get('review_priority_rank')))
    ]
    scene_decision_by_id = {str(decision['scene_id']): decision for decision in scene_decisions}
    actions = [
        _component_action(row, scene_decision_by_id[str(row.get('scene_id'))])
        for row in component_rows
        if str(row.get('scene_id')) in scene_decision_by_id
    ]
    actions = sorted(
        actions,
        key=lambda item: (
            int(item['review_priority_rank']),
            0 if item['component_type'] == 'false_negative' else 1,
            -int(item['pixel_count']),
        ),
    )
    bucket_counts = Counter(action['component_review_bucket'] for action in actions)
    scene_decision_counts = Counter(decision['scene_review_decision'] for decision in scene_decisions)
    summary = {
        'version': 'snowslide_component_review_summary_v1',
        'generated_at': _now_iso(),
        'source_inputs': {
            'component_review_table': str(component_review_table),
            'scene_review_packet': str(scene_review_packet),
            'sar_error_diagnostics': str(sar_error_diagnostics),
            'snowslide_eval_only_recovery_report': str(eval_only_recovery_report),
        },
        'decision': 'manual_scene_label_review_required',
        'recommended_next_step': 'manual_scene_label_review',
        'production_scoring_allowed': False,
        'next_gpu_run_authorized': False,
        'promotion_allowed': False,
        'snow_slide_research_grade_decision': recovery_report.get('decision'),
        'eval_only_passing_candidate_count': recovery_report.get('passing_candidate_count'),
        'dominant_blocker': error_report.get('dominant_blocker'),
        'scene_review_decisions': scene_decisions,
        'scene_decision_counts': dict(scene_decision_counts),
        'component_bucket_counts': dict(bucket_counts),
        'component_review_actions': actions,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'component_review_summary.json', summary)
    (output_root / 'component_review_summary.md').write_text(_render_markdown(summary), encoding='utf-8')
    _write_actions_csv(output_root / 'component_review_actions.csv', actions)
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Summarize SnowSlide v5 component-review actions from existing diagnostics.')
    parser.add_argument('--component-review-table', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'component_review_table.csv')
    parser.add_argument('--scene-review-packet', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'scene_review_packet.json')
    parser.add_argument('--sar-error-diagnostics', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'sar_error_diagnostics.json')
    parser.add_argument('--eval-only-recovery-report', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'snowslide_eval_only_recovery_report.json')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = build_component_review_summary(
        component_review_table=args.component_review_table,
        scene_review_packet=args.scene_review_packet,
        sar_error_diagnostics=args.sar_error_diagnostics,
        eval_only_recovery_report=args.eval_only_recovery_report,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'decision': summary['decision'],
        'recommended_next_step': summary['recommended_next_step'],
        'production_scoring_allowed': summary['production_scoring_allowed'],
        'next_gpu_run_authorized': summary['next_gpu_run_authorized'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
