from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.scripts.build_snowslide_manual_label_review_packet import (
    COMPONENT_DECISIONS,
    DEFAULT_DIAGNOSTICS_ROOT,
    REVIEW_STATUSES,
    SCENE_DECISIONS,
)


LABEL_REMEDIATION_COMPONENT_DECISIONS = {
    'truth_missing_or_underlabeled',
    'registration_or_projection_issue',
    'exclude_pending_source_review',
}
TERRAIN_CONTEXT_COMPONENT_DECISIONS = {'terrain_or_sar_ambiguity'}


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _parse_bool(value: Any, *, field: str, action_id: str) -> bool:
    cleaned = _clean(value).lower()
    if cleaned in {'true', '1', 'yes', 'y'}:
        return True
    if cleaned in {'false', '0', 'no', 'n'}:
        return False
    raise ValueError(f'{field} must be true/false for action_id={action_id}')


def _validate_row(row: dict[str, Any], packet_action_ids: set[str]) -> dict[str, Any]:
    action_id = _clean(row.get('action_id'))
    if not action_id:
        raise ValueError('manual review row is missing action_id')
    if action_id not in packet_action_ids:
        raise ValueError(f'manual review row references action_id not present in packet: {action_id}')

    review_status = _clean(row.get('review_status'))
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f'review_status must be one of {REVIEW_STATUSES} for action_id={action_id}')

    component_decision = _clean(row.get('component_decision'))
    scene_decision = _clean(row.get('scene_decision')) or 'review_incomplete'
    if scene_decision not in SCENE_DECISIONS:
        raise ValueError(f'scene_decision must be one of {SCENE_DECISIONS} for action_id={action_id}')

    if review_status == 'pending':
        return {
            **row,
            'action_id': action_id,
            'review_status': review_status,
            'component_decision': component_decision,
            'scene_decision': scene_decision,
            'requires_label_edit_bool': False,
            'reviewer_notes': _clean(row.get('reviewer_notes')),
        }

    if component_decision not in COMPONENT_DECISIONS:
        raise ValueError(f'component_decision must be one of {COMPONENT_DECISIONS} for action_id={action_id}')
    if not _clean(row.get('reviewer_notes')):
        raise ValueError(f'reviewer_notes must be provided for reviewed action_id={action_id}')
    return {
        **row,
        'action_id': action_id,
        'review_status': review_status,
        'component_decision': component_decision,
        'scene_decision': scene_decision,
        'requires_label_edit_bool': _parse_bool(row.get('requires_label_edit'), field='requires_label_edit', action_id=action_id),
        'reviewer_notes': _clean(row.get('reviewer_notes')),
    }


def _scene_decision(rows: list[dict[str, Any]]) -> str:
    if any(row['review_status'] == 'pending' for row in rows):
        return 'review_incomplete'
    if any(row['requires_label_edit_bool'] or row['component_decision'] in LABEL_REMEDIATION_COMPONENT_DECISIONS for row in rows):
        return 'label_remediation_required'
    if any(row['component_decision'] in TERRAIN_CONTEXT_COMPONENT_DECISIONS for row in rows):
        return 'terrain_context_required'
    return 'labels_valid_model_gap'


def _overall_decision(scene_outcomes: list[dict[str, Any]]) -> str:
    decisions = {row['scene_decision'] for row in scene_outcomes}
    if 'review_incomplete' in decisions:
        return 'review_incomplete'
    if 'label_remediation_required' in decisions:
        return 'label_remediation_required'
    if 'terrain_context_required' in decisions:
        return 'terrain_context_required'
    return 'labels_valid_model_gap'


def _remediation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remediation: list[dict[str, Any]] = []
    for row in rows:
        if row['review_status'] == 'reviewed' and (
            row['requires_label_edit_bool'] or row['component_decision'] in LABEL_REMEDIATION_COMPONENT_DECISIONS
        ):
            remediation.append({
                'action_id': row['action_id'],
                'scene_id': row.get('scene_id'),
                'component_type': row.get('component_type'),
                'component_rank': row.get('component_rank'),
                'component_decision': row['component_decision'],
                'requires_label_edit': str(row['requires_label_edit_bool']).lower(),
                'row_min': row.get('row_min'),
                'row_max_exclusive': row.get('row_max_exclusive'),
                'col_min': row.get('col_min'),
                'col_max_exclusive': row.get('col_max_exclusive'),
                'geo_west': row.get('geo_west'),
                'geo_south': row.get('geo_south'),
                'geo_east': row.get('geo_east'),
                'geo_north': row.get('geo_north'),
                'reviewer_notes': row['reviewer_notes'],
            })
    return remediation


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_markdown(outcome: dict[str, Any]) -> str:
    lines = [
        '# SnowSlide v5 Manual Scene/Label Review Outcome',
        '',
        f"- Decision: `{outcome['decision']}`",
        f"- Production scoring allowed: `{str(outcome['production_scoring_allowed']).lower()}`",
        f"- Next GPU run authorized: `{str(outcome['next_gpu_run_authorized']).lower()}`",
        f"- Promotion allowed: `{str(outcome['promotion_allowed']).lower()}`",
        f"- Future candidate design warranted: `{str(outcome['future_candidate_design_warranted']).lower()}`",
        '',
        '## Scene Outcomes',
        '',
        '| Scene | Decision | Reviewed | Pending | Label edits |',
        '|---|---|---:|---:|---:|',
    ]
    for scene in outcome['scene_outcomes']:
        lines.append(
            f"| {scene['scene_id']} | {scene['scene_decision']} | {scene['reviewed_component_count']} | "
            f"{scene['pending_component_count']} | {scene['label_edit_component_count']} |",
        )
    lines.extend([
        '',
        'This outcome does not authorize production scoring, promotion, or a GPU run.',
        '',
    ])
    return '\n'.join(lines)


def resolve_manual_label_review(
    *,
    manual_label_review_decisions: Path,
    manual_label_review_packet: Path,
    output_root: Path,
) -> dict[str, Any]:
    packet = _load_json(manual_label_review_packet, label='manual_label_review_packet')
    packet_items = packet.get('component_review_items')
    if not isinstance(packet_items, list) or not packet_items:
        raise ValueError('manual_label_review_packet must include component_review_items[]')
    packet_action_ids = {str(item.get('action_id')) for item in packet_items if isinstance(item, dict) and item.get('action_id')}
    rows = _load_csv(manual_label_review_decisions, label='manual_label_review_decisions')
    if not rows:
        raise ValueError('manual_label_review_decisions did not contain any rows')
    validated = [_validate_row(row, packet_action_ids) for row in rows]
    observed_action_ids = {row['action_id'] for row in validated}
    missing_action_ids = sorted(packet_action_ids - observed_action_ids)
    if missing_action_ids:
        raise ValueError(f'manual_label_review_decisions missing action IDs from packet: {missing_action_ids}')

    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in validated:
        by_scene[_clean(row.get('scene_id'))].append(row)

    scene_outcomes: list[dict[str, Any]] = []
    for scene_id, scene_rows in sorted(by_scene.items()):
        decision = _scene_decision(scene_rows)
        label_edit_count = sum(1 for row in scene_rows if row.get('requires_label_edit_bool'))
        reviewed_count = sum(1 for row in scene_rows if row['review_status'] == 'reviewed')
        pending_count = sum(1 for row in scene_rows if row['review_status'] == 'pending')
        scene_outcomes.append({
            'scene_id': scene_id,
            'scene_decision': decision,
            'component_count': len(scene_rows),
            'reviewed_component_count': reviewed_count,
            'pending_component_count': pending_count,
            'label_edit_component_count': label_edit_count,
            'component_decision_counts': dict(Counter(row['component_decision'] or 'pending' for row in scene_rows)),
        })

    decision = _overall_decision(scene_outcomes)
    remediation = _remediation_rows(validated)
    outcome = {
        'version': 'snowslide_manual_label_review_outcome_v1',
        'generated_at': _now_iso(),
        'source_inputs': {
            'manual_label_review_decisions': str(manual_label_review_decisions),
            'manual_label_review_packet': str(manual_label_review_packet),
        },
        'decision': decision,
        'production_scoring_allowed': False,
        'next_gpu_run_authorized': False,
        'promotion_allowed': False,
        'future_candidate_design_warranted': decision == 'labels_valid_model_gap',
        'recommended_next_step': {
            'review_incomplete': 'complete_manual_label_review_decisions',
            'label_remediation_required': 'prepare_label_or_source_remediation_checkpoint',
            'terrain_context_required': 'review_scene_terrain_and_sar_context_before_training',
            'labels_valid_model_gap': 'prepare_separate_candidate_design_plan_without_auto_launch',
        }[decision],
        'pending_component_count': sum(row['review_status'] == 'pending' for row in validated),
        'reviewed_component_count': sum(row['review_status'] == 'reviewed' for row in validated),
        'scene_outcomes': scene_outcomes,
        'component_decision_counts': dict(Counter(row['component_decision'] or 'pending' for row in validated)),
        'label_remediation_component_count': len(remediation),
        'label_remediation_manifest': str(output_root / 'snowslide_label_remediation_manifest.csv') if remediation else None,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'manual_label_review_outcome.json', outcome)
    (output_root / 'manual_label_review_outcome.md').write_text(_render_markdown(outcome), encoding='utf-8')
    if remediation:
        _write_csv(
            output_root / 'snowslide_label_remediation_manifest.csv',
            remediation,
            fieldnames=list(remediation[0].keys()),
        )
    return outcome


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Resolve completed SnowSlide manual label review decisions.')
    parser.add_argument('--manual-label-review-decisions', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'manual_label_review_decisions.csv')
    parser.add_argument('--manual-label-review-packet', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT / 'manual_label_review_packet.json')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_DIAGNOSTICS_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outcome = resolve_manual_label_review(
        manual_label_review_decisions=args.manual_label_review_decisions,
        manual_label_review_packet=args.manual_label_review_packet,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'decision': outcome['decision'],
        'recommended_next_step': outcome['recommended_next_step'],
        'production_scoring_allowed': outcome['production_scoring_allowed'],
        'next_gpu_run_authorized': outcome['next_gpu_run_authorized'],
        'future_candidate_design_warranted': outcome['future_candidate_design_warranted'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 2 if outcome['decision'] == 'review_incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
