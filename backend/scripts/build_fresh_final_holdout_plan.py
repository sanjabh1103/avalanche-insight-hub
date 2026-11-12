from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/snowslide-research-grade-v6-2026-05-18/fresh-final-holdout',
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required fresh final holdout input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'fresh final holdout input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _render_markdown(report: dict[str, Any]) -> str:
    return '\n'.join([
        '# Fresh Final Holdout Plan',
        '',
        f"- Status: `{report['status']}`",
        f"- Final reference set: `{report.get('fresh_final_reference_set_key')}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Promotion allowed: `{str(report['promotion_allowed']).lower()}`",
        '',
        report['next_checkpoint'],
        '',
    ])


def build_fresh_final_holdout_plan(
    *,
    snowslide_acceptance_report: Path,
    output_root: Path,
    fresh_final_reference_set_key: str | None = None,
) -> dict[str, Any]:
    acceptance = _load_json(snowslide_acceptance_report, label='snowslide_acceptance_report')
    reference_key = (fresh_final_reference_set_key or '').strip() or None
    if acceptance.get('decision') not in {'requires_fresh_final_holdout', 'accepted_research_grade'}:
        status = 'blocked_pending_snowslide_research_grade'
        next_checkpoint = 'Do not create a final holdout run until SnowSlide research-grade floors pass.'
    elif reference_key is None:
        status = 'blocked_pending_fresh_reference_set'
        next_checkpoint = 'Provide an independent fresh final reference set before Phase 7 promotion readiness.'
    elif reference_key == 'snowslide-heldout-v1':
        status = 'blocked_reuses_snow_slide_qualification_set'
        next_checkpoint = 'Choose a fresh final holdout that was not used for SnowSlide-guided candidate selection.'
    else:
        status = 'ready_for_fresh_final_holdout_evaluation'
        next_checkpoint = 'Materialize and evaluate the fresh final holdout with the same accepted v6 decision rule.'

    report = {
        'version': 'fresh_final_holdout_plan_v1',
        'generated_at': _now_iso(),
        'status': status,
        'snowslide_acceptance_decision': acceptance.get('decision'),
        'fresh_final_reference_set_key': reference_key,
        'rejected_reference_set_keys': ['snowslide-heldout-v1'],
        'production_scoring_allowed': False,
        'promotion_allowed': False,
        'phase7_promotion_ready': False,
        'source_inputs': {
            'snowslide_acceptance_report': str(snowslide_acceptance_report),
        },
        'next_checkpoint': next_checkpoint,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / 'fresh_final_holdout_plan.json', report)
    (output_root / 'fresh_final_holdout_plan.md').write_text(_render_markdown(report), encoding='utf-8')
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build the fresh final holdout gate plan after SnowSlide qualification.')
    parser.add_argument('--snowslide-acceptance-report', type=Path, required=True)
    parser.add_argument('--fresh-final-reference-set-key')
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_fresh_final_holdout_plan(
        snowslide_acceptance_report=args.snowslide_acceptance_report,
        fresh_final_reference_set_key=args.fresh_final_reference_set_key,
        output_root=args.output_root,
    )
    print(json.dumps({
        'status': 'ok',
        'plan_status': report['status'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0 if report['status'] != 'ready_for_fresh_final_holdout_evaluation' else 0


if __name__ == '__main__':
    raise SystemExit(main())
