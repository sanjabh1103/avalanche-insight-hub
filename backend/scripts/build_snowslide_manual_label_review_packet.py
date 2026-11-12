from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DIAGNOSTICS_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v5-2026-05-18/diagnostics',
)

REVIEW_STATUSES = ('pending', 'reviewed')
COMPONENT_DECISIONS = (
    'truth_missing_or_underlabeled',
    'valid_model_miss',
    'prediction_false_alarm',
    'terrain_or_sar_ambiguity',
    'registration_or_projection_issue',
    'exclude_pending_source_review',
)
SCENE_DECISIONS = (
    'label_remediation_required',
    'labels_valid_model_gap',
    'terrain_context_required',
    'review_incomplete',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required manual-review input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'required manual-review input must be a JSON object: {label} ({path})')
    return payload


def _load_csv(path: Path, *, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f'required manual-review input not found: {label} ({path})')
    with path.open('r', encoding='utf-8', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ''):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ''):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _scene_reviews(summary: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = summary.get('scene_review_decisions')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('component_review_summary must include scene_review_decisions[]')
    return [scene for scene in scenes if isinstance(scene, dict) and scene.get('scene_id')]


def _review_focus(scene_review_decision: str, component_type: str) -> str:
    if scene_review_decision == 'recall_first_label_or_threshold_review':
        return 'recall_gap'
    if scene_review_decision == 'precision_first_label_or_terrain_review':
        return 'precision_gap'
    if scene_review_decision == 'mixed_precision_recall_review':
        return 'mixed_precision_recall_gap'
    if component_type == 'false_negative':
        return 'false_negative_context'
    if component_type == 'false_positive':
        return 'false_positive_context'
    return 'context_review'


def _review_question(scene_review_decision: str, component_type: str) -> str:
    if component_type == 'false_negative':
        if scene_review_decision == 'recall_first_label_or_threshold_review':
            return (
                'Is this missed truth component a valid avalanche label that v5 failed to recover, '
                'or is it under-labeled/registration/threshold context needing source review?'
            )
        return (
            'Is this missed truth component a valid avalanche label, a marginal/ambiguous SAR signal, '
            'or a source-label/registration issue?'
        )
    if component_type == 'false_positive':
        if scene_review_decision == 'precision_first_label_or_terrain_review':
            return (
                'Is this predicted component a true false alarm from terrain/SAR texture, an unlabeled avalanche, '
                'or a registration/source-label issue?'
            )
        return (
            'Does this predicted component correspond to unlabeled avalanche evidence, a valid false alarm, '
            'or terrain/SAR ambiguity?'
        )
    return 'Review this component against source labels and SAR context before authorizing any model work.'


def _action_id(row: dict[str, Any]) -> str:
    scene_id = str(row.get('scene_id') or 'unknown_scene')
    component_type = str(row.get('component_type') or 'component')
    rank = _as_int(row.get('component_rank'))
    return f'{scene_id}__{component_type}__{rank:03d}'


def _component_item(row: dict[str, Any], scene_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scene_id = str(row.get('scene_id') or '')
    scene = scene_by_id.get(scene_id)
    if scene is None:
        raise ValueError(f'component action references unknown review scene: {scene_id}')
    scene_decision = str(scene.get('scene_review_decision') or '')
    component_type = str(row.get('component_type') or '')
    metrics = scene.get('metrics') if isinstance(scene.get('metrics'), dict) else {}
    return {
        'action_id': _action_id(row),
        'scene_id': scene_id,
        'review_priority_rank': _as_int(row.get('review_priority_rank')),
        'scene_review_decision': scene_decision,
        'scene_review_buckets': row.get('scene_review_buckets') or '',
        'component_type': component_type,
        'component_rank': _as_int(row.get('component_rank')),
        'component_review_bucket': row.get('component_review_bucket') or '',
        'blocking_bucket': row.get('blocking_bucket') or 'no_training_until_reviewed',
        'review_focus': _review_focus(scene_decision, component_type),
        'review_question': _review_question(scene_decision, component_type),
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
        'scene_metrics': {
            'precision': _as_float(metrics.get('precision')),
            'recall': _as_float(metrics.get('recall')),
            'f1': _as_float(metrics.get('f1')),
            'false_positive_rate': _as_float(metrics.get('false_positive_rate')),
            'fp_share': _as_float(metrics.get('fp_share')),
            'fn_share': _as_float(metrics.get('fn_share')),
        },
    }


def _worksheet_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        bbox = item['pixel_bbox']
        centroid = item['pixel_centroid']
        geo = item['geo_bbox']
        rows.append({
            'action_id': item['action_id'],
            'scene_id': item['scene_id'],
            'review_priority_rank': item['review_priority_rank'],
            'scene_review_decision': item['scene_review_decision'],
            'component_type': item['component_type'],
            'component_rank': item['component_rank'],
            'component_review_bucket': item['component_review_bucket'],
            'blocking_bucket': item['blocking_bucket'],
            'review_focus': item['review_focus'],
            'pixel_count': item['pixel_count'],
            'row_min': bbox['row_min'],
            'row_max_exclusive': bbox['row_max_exclusive'],
            'col_min': bbox['col_min'],
            'col_max_exclusive': bbox['col_max_exclusive'],
            'centroid_row': centroid['row'],
            'centroid_col': centroid['col'],
            'geo_west': geo['west'],
            'geo_south': geo['south'],
            'geo_east': geo['east'],
            'geo_north': geo['north'],
            'review_question': item['review_question'],
            'allowed_review_statuses': ';'.join(REVIEW_STATUSES),
            'allowed_component_decisions': ';'.join(COMPONENT_DECISIONS),
            'allowed_scene_decisions': ';'.join(SCENE_DECISIONS),
            'review_status': 'pending',
            'component_decision': '',
            'requires_label_edit': '',
            'scene_decision': 'review_incomplete',
            'reviewer_notes': '',
        })
    return rows


def _merge_existing_review_decisions(path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not path.exists():
        return rows
    existing_by_action_id: dict[str, dict[str, Any]] = {}
    with path.open('r', encoding='utf-8', newline='') as handle:
        for existing in csv.DictReader(handle):
            action_id = str(existing.get('action_id') or '').strip()
            if action_id:
                existing_by_action_id[action_id] = dict(existing)
    preserved_fields = {
        'review_status',
        'component_decision',
        'requires_label_edit',
        'scene_decision',
        'reviewer_notes',
    }
    merged: list[dict[str, Any]] = []
    for row in rows:
        existing = existing_by_action_id.get(str(row.get('action_id') or ''))
        if existing:
            row = {
                **row,
                **{
                    field: existing.get(field, row.get(field, ''))
                    for field in preserved_fields
                    if existing.get(field, '') != ''
                },
            }
        merged.append(row)
    return merged


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        '# SnowSlide v5 Manual Scene/Label Review Packet',
        '',
        f"- Decision: `{packet['decision']}`",
        f"- Recommended next step: `{packet['recommended_next_step']}`",
        f"- Production scoring allowed: `{str(packet['production_scoring_allowed']).lower()}`",
        f"- Next GPU run authorized: `{str(packet['next_gpu_run_authorized']).lower()}`",
        f"- Promotion allowed: `{str(packet['promotion_allowed']).lower()}`",
        '',
        '## Review Scenes',
        '',
        '| Rank | Scene | Review type | Precision | Recall | F1 | FP share | FN share |',
        '|---:|---|---|---:|---:|---:|---:|---:|',
    ]
    for scene in packet['scene_reviews']:
        metrics = scene.get('metrics') if isinstance(scene.get('metrics'), dict) else {}
        lines.append(
            f"| {scene.get('review_priority_rank')} | {scene.get('scene_id')} | {scene.get('scene_review_decision')} | "
            f"{_as_float(metrics.get('precision')):.3f} | {_as_float(metrics.get('recall')):.3f} | "
            f"{_as_float(metrics.get('f1')):.3f} | {_as_float(metrics.get('fp_share')):.3f} | "
            f"{_as_float(metrics.get('fn_share')):.3f} |",
        )
    lines.extend([
        '',
        '## Component Review Questions',
        '',
        '| Action ID | Scene | Type | Rank | Pixels | Review focus | Question |',
        '|---|---|---|---:|---:|---|---|',
    ])
    for item in packet['component_review_items'][:30]:
        lines.append(
            f"| {item['action_id']} | {item['scene_id']} | {item['component_type']} | "
            f"{item['component_rank']} | {item['pixel_count']} | {item['review_focus']} | "
            f"{item['review_question']} |",
        )
    lines.extend([
        '',
        'Complete `manual_label_review_decisions.csv` with closed-choice values before any model-side work is reconsidered.',
        '',
    ])
    return '\n'.join(lines)


def build_manual_label_review_packet(
    *,
    component_review_actions: Path,
    component_review_summary: Path,
    scene_review_packet: Path,
    sar_error_diagnostics: Path,
    eval_only_recovery_report: Path,
    output_root: Path,
) -> dict[str, Any]:
    actions = _load_csv(component_review_actions, label='component_review_actions')
    summary = _load_json(component_review_summary, label='component_review_summary')
    scene_packet = _load_json(scene_review_packet, label='scene_review_packet')
    error_report = _load_json(sar_error_diagnostics, label='sar_error_diagnostics')
    recovery_report = _load_json(eval_only_recovery_report, label='snowslide_eval_only_recovery_report')

    scenes = _scene_reviews(summary)
    scene_by_id = {str(scene.get('scene_id')): scene for scene in scenes}
    if not actions:
        raise ValueError('component_review_actions did not contain any rows')

    items = [_component_item(row, scene_by_id) for row in actions]
    worksheet_path = output_root / 'manual_label_review_decisions.csv'
    worksheet_rows = _merge_existing_review_decisions(worksheet_path, _worksheet_rows(items))
    generated_at = _now_iso()
    packet = {
        'version': 'snowslide_manual_label_review_packet_v1',
        'generated_at': generated_at,
        'source_inputs': {
            'component_review_actions': str(component_review_actions),
            'component_review_summary': str(component_review_summary),
            'scene_review_packet': str(scene_review_packet),
            'sar_error_diagnostics': str(sar_error_diagnostics),
            'snowslide_eval_only_recovery_report': str(eval_only_recovery_report),
        },
        'decision': 'manual_scene_label_review_required',
        'recommended_next_step': 'complete_manual_label_review_decisions',
        'production_scoring_allowed': False,
        'next_gpu_run_authorized': False,
        'promotion_allowed': False,
        'future_candidate_design_warranted': False,
        'snow_slide_research_grade_decision': recovery_report.get('decision'),
        'eval_only_passing_candidate_count': recovery_report.get('passing_candidate_count'),
        'dominant_blocker': error_report.get('dominant_blocker'),
        'allowed_values': {
            'review_status': list(REVIEW_STATUSES),
            'component_decision': list(COMPONENT_DECISIONS),
            'scene_decision': list(SCENE_DECISIONS),
        },
        'scene_reviews': scenes,
        'source_scene_review_packet_scene_count': len(scene_packet.get('review_scenes') or []),
        'component_review_items': items,
        'manual_decision_csv': str(worksheet_path),
        'manual_actions_csv': str(output_root / 'manual_label_review_actions.csv'),
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'manual_label_review_packet.json', packet)
    (output_root / 'manual_label_review_packet.md').write_text(_render_markdown(packet), encoding='utf-8')
    fieldnames = list(worksheet_rows[0].keys())
    _write_csv(worksheet_path, worksheet_rows, fieldnames=fieldnames)
    readonly_fieldnames = [name for name in fieldnames if name not in {
        'allowed_review_statuses',
        'allowed_component_decisions',
        'allowed_scene_decisions',
        'review_status',
        'component_decision',
        'requires_label_edit',
        'scene_decision',
        'reviewer_notes',
    }]
    _write_csv(
        output_root / 'manual_label_review_actions.csv',
        [{key: row[key] for key in readonly_fieldnames} for row in worksheet_rows],
        fieldnames=readonly_fieldnames,
    )
    return packet


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a manual SnowSlide v5 scene/label review packet from existing diagnostics.')
    parser.add_argument('--component-review-actions', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'component_review_actions.csv')
    parser.add_argument('--component-review-summary', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'component_review_summary.json')
    parser.add_argument('--scene-review-packet', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'scene_review_packet.json')
    parser.add_argument('--sar-error-diagnostics', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'sar_error_diagnostics.json')
    parser.add_argument('--eval-only-recovery-report', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'snowslide_eval_only_recovery_report.json')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    packet = build_manual_label_review_packet(
        component_review_actions=args.component_review_actions,
        component_review_summary=args.component_review_summary,
        scene_review_packet=args.scene_review_packet,
        sar_error_diagnostics=args.sar_error_diagnostics,
        eval_only_recovery_report=args.eval_only_recovery_report,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'decision': packet['decision'],
        'recommended_next_step': packet['recommended_next_step'],
        'component_review_item_count': len(packet['component_review_items']),
        'production_scoring_allowed': packet['production_scoring_allowed'],
        'next_gpu_run_authorized': packet['next_gpu_run_authorized'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
