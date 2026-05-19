from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path(
    'backend/artifacts/european-shadow-qualification/sar-v8-client-closeout-2026-05-19',
)
DEFAULT_AVALCD_BENCHMARK = Path(
    'backend/artifacts/european-shadow-real-benchmarks/'
    'european-shadow-real-avalcd-scene-blended-v8-2026-05-19/european_shadow_benchmark_report.json',
)
DEFAULT_SNOWSLIDE_ACCEPTANCE = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v8-2026-05-19/acceptance_report.json',
)
DEFAULT_SNOWSLIDE_SWEEP = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v8-2026-05-19/snowslide_v8_threshold_sweep_report.json',
)
DEFAULT_MANUAL_REVIEW_PACKET = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v8-2026-05-19/diagnostics/manual_label_review_packet.json',
)
DEFAULT_SNOWSLIDE_DIAGNOSTICS = Path(
    'backend/artifacts/european-shadow-qualification/'
    'snowslide-research-grade-v8-2026-05-19/diagnostics/sar_error_diagnostics.json',
)
SCHEMA_VERSION = 'european_shadow_sar_closeout_pack_v2'
DEPRECATED_SCHEMA_VERSIONS = {'european_shadow_sar_closeout_pack_v1'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'required closeout input not found: {label} ({path})')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'closeout input must be a JSON object: {label} ({path})')
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _deprecate_existing_v1_outputs(output_root: Path) -> None:
    for filename in ('european_shadow_sar_closeout_pack.json', 'european_shadow_sar_closeout_pack.md'):
        path = output_root / filename
        if not path.exists():
            continue
        if path.suffix == '.json':
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                payload = {}
            if payload.get('version') not in DEPRECATED_SCHEMA_VERSIONS:
                continue
        deprecated = output_root / f'{path.stem}.deprecated_v1{path.suffix}'
        path.replace(deprecated)


def _truthy_production_paths(value: Any, *, path: str = '$') -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f'{path}.{key}'
            if key == 'production_scoring_allowed' and item is True:
                matches.append(child_path)
            matches.extend(_truthy_production_paths(item, path=child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(_truthy_production_paths(item, path=f'{path}[{index}]'))
    return matches


def _avalcd_sar_metrics(benchmark: dict[str, Any]) -> dict[str, Any]:
    for source_report in benchmark.get('source_reports') or []:
        if isinstance(source_report, dict) and source_report.get('source_key') == 'avalcd_zenodo_v1':
            metrics = source_report.get('sar_prediction_metrics')
            if isinstance(metrics, dict):
                return metrics
    return {}


def _metric_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        'precision': metrics.get('precision'),
        'recall': metrics.get('recall'),
        'f1': metrics.get('f1'),
        'false_positive_rate': metrics.get('false_positive_rate'),
        'threshold': metrics.get('threshold') or metrics.get('prediction_threshold'),
        'postprocess_min_component_area_px': metrics.get('postprocess_min_component_area_px'),
        'postprocess_opening_size_px': metrics.get('postprocess_opening_size_px'),
    }


def _provided(value: str | None) -> bool:
    normalized = str(value or '').strip().lower()
    if not normalized:
        return False
    return normalized not in {'tbd', 'tbd before presentation', 'unknown', 'unassigned', 'none', 'n/a'}


def _scene_region(scene_id: str) -> str:
    if scene_id.startswith('tromso_'):
        return 'Norway'
    if scene_id.startswith('nuuk_'):
        return 'Greenland Nuuk'
    if scene_id.startswith('livigno_'):
        return 'Italian Alps'
    if scene_id.startswith('pish_'):
        return 'Pamir'
    return 'unknown'


def _scene_verdict(metrics: dict[str, Any]) -> str:
    precision = float(metrics.get('precision') or 0.0)
    recall = float(metrics.get('recall') or 0.0)
    f1 = float(metrics.get('f1') or 0.0)
    fpr = float(metrics.get('false_positive_rate') or 0.0)
    if precision >= 0.70 and recall >= 0.50 and f1 >= 0.60 and fpr <= 0.002:
        return 'passes_research_grade_alone'
    if precision >= 0.60 and recall >= 0.50 and f1 >= 0.57 and fpr <= 0.0025:
        return 'near_pass'
    if precision < 0.45 or f1 < 0.50 or fpr > 0.004:
        return 'severe_scene_failure'
    return 'below_floor'


def _per_scene_results(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in diagnostics.get('per_scene') or []:
        if not isinstance(row, dict):
            continue
        scene_id = str(row.get('scene_id') or row.get('id') or '')
        metrics = {
            'precision': row.get('precision'),
            'recall': row.get('recall'),
            'f1': row.get('f1'),
            'false_positive_rate': row.get('false_positive_rate'),
            'fp_share': row.get('fp_share'),
            'fn_share': row.get('fn_share'),
        }
        rows.append({
            'scene_id': scene_id,
            'region': _scene_region(scene_id),
            'metrics': metrics,
            'verdict': _scene_verdict(metrics),
        })
    return sorted(rows, key=lambda item: float(item['metrics'].get('f1') or 0.0), reverse=True)


def _region_coverage(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    for source_report in benchmark.get('source_reports') or []:
        if not isinstance(source_report, dict) or source_report.get('source_key') != 'avalcd_zenodo_v1':
            continue
        data_quality = source_report.get('data_quality') if isinstance(source_report.get('data_quality'), dict) else {}
        counts = data_quality.get('region_counts') if isinstance(data_quality.get('region_counts'), dict) else {}
        return [
            {'region_key': key, 'scene_count': value, 'metric_status': 'region_metrics_pending'}
            for key, value in sorted(counts.items())
        ]
    return []


def validate_v2_closeout_pack(payload: dict[str, Any]) -> None:
    version = payload.get('version')
    if version in DEPRECATED_SCHEMA_VERSIONS:
        raise ValueError(f'closeout pack schema {version} is deprecated; regenerate as {SCHEMA_VERSION}')
    if version != SCHEMA_VERSION:
        raise ValueError(f'closeout pack schema must be {SCHEMA_VERSION}; got {version}')


def _render_markdown(report: dict[str, Any]) -> str:
    avalcd = report['avalcd_gate']
    snow = report['snowslide_gate']
    review = report['manual_review']
    lines = [
        '# European Shadow SAR V8 Client Closeout',
        '',
        f"- Decision: `{report['decision']}`",
        f"- Client presentation ready: `{str(report['client_presentation_ready']).lower()}`",
        f"- SAR production ready: `{str(report['sar_production_ready']).lower()}`",
        f"- Production scoring allowed: `{str(report['production_scoring_allowed']).lower()}`",
        f"- Phase 7 ready: `{str(report['phase7_ready']).lower()}`",
        '',
        '## Evidence Summary',
        '',
        '| Gate | Result | Status |',
        '|---|---|---|',
        (
            f"| AvalCD scene-blended | precision `{avalcd['metrics'].get('precision')}`, "
            f"recall `{avalcd['metrics'].get('recall')}`, F1 `{avalcd['metrics'].get('f1')}` | "
            f"`{avalcd['status']}` |"
        ),
        (
            f"| SnowSlide research-grade | precision `{snow['metrics'].get('precision')}`, "
            f"recall `{snow['metrics'].get('recall')}`, F1 `{snow['metrics'].get('f1')}`, "
            f"FPR `{snow['metrics'].get('false_positive_rate')}` | `{snow['decision']}` |"
        ),
        (
            f"| Non-GPU SnowSlide sweep | passing candidates `{report['non_gpu_sweep'].get('passing_candidate_count')}` | "
            f"`{report['non_gpu_sweep'].get('decision')}` |"
        ),
        (
            f"| Manual component review | {review['component_review_item_count']} components | "
            f"`{review['decision']}` |"
        ),
        '',
        '## Presentation Authorization',
        '',
        f"- Authorized: `{str(report['presentation_authorization']['authorized']).lower()}`",
        f"- Authorized by: `{report['presentation_authorization'].get('authorized_by')}`",
        f"- Authorization ID: `{report['presentation_authorization'].get('presentation_authorization_id')}`",
        f"- Manual review owner status: `{report['manual_review'].get('owner_status')}`",
        '',
        '## Current Stop Condition',
        '',
        report['current_stop_condition'],
        '',
        '## Safe Client Framing',
        '',
        '- European shadow-data and SAR qualification infrastructure is implemented.',
        '- AvalCD v8 has real scene-blended evidence and passes the internal AvalCD precision/recall gate.',
        '- SnowSlide v8 does not pass research-grade held-out acceptance, so SAR production scoring remains blocked.',
        '- The next scientific action is manual review of the 30-component v8 packet before any v9 candidate design.',
        '',
        '## Next Manual Action',
        '',
        report['next_manual_action'],
        '',
    ]
    return '\n'.join(lines)


def build_closeout_pack(
    *,
    avalcd_benchmark_path: Path,
    snowslide_acceptance_path: Path,
    snowslide_sweep_path: Path,
    manual_review_packet_path: Path,
    snowslide_diagnostics_path: Path,
    output_root: Path,
    allow_shadow_only_presentation: bool = False,
    authorized_by: str | None = None,
    authorization_reason: str | None = None,
    authorization_evidence_ref: str | None = None,
    manual_review_owner: str | None = None,
    manual_review_target_date: str | None = None,
) -> dict[str, Any]:
    avalcd_benchmark = _load_json(avalcd_benchmark_path, label='avalcd_benchmark')
    snowslide_acceptance = _load_json(snowslide_acceptance_path, label='snowslide_acceptance')
    snowslide_sweep = _load_json(snowslide_sweep_path, label='snowslide_sweep')
    manual_review_packet = _load_json(manual_review_packet_path, label='manual_review_packet')
    snowslide_diagnostics = _load_json(snowslide_diagnostics_path, label='snowslide_diagnostics')

    production_true_paths = []
    for label, artifact in {
        'avalcd_benchmark': avalcd_benchmark,
        'snowslide_acceptance': snowslide_acceptance,
        'snowslide_sweep': snowslide_sweep,
        'manual_review_packet': manual_review_packet,
        'snowslide_diagnostics': snowslide_diagnostics,
    }.items():
        production_true_paths.extend(f'{label}:{path}' for path in _truthy_production_paths(artifact))

    avalcd_sar = _avalcd_sar_metrics(avalcd_benchmark)
    avalcd_metrics = avalcd_sar.get('metrics') if isinstance(avalcd_sar.get('metrics'), dict) else {}
    avalcd_quality = avalcd_sar.get('quality_gate') if isinstance(avalcd_sar.get('quality_gate'), dict) else {}
    snow_metrics = snowslide_acceptance.get('metrics') if isinstance(snowslide_acceptance.get('metrics'), dict) else {}
    component_count = len(manual_review_packet.get('component_review_items') or [])

    avalcd_passed = (
        avalcd_sar.get('evaluation_mode') == 'scene_blended'
        and avalcd_quality.get('passed') is True
        and avalcd_quality.get('precision_floor_met') is True
        and avalcd_quality.get('recall_floor_met') is True
    )
    snowslide_passed = snowslide_acceptance.get('decision') in {
        'accepted_research_grade',
        'requires_fresh_final_holdout',
    }
    manual_review_required = manual_review_packet.get('decision') == 'manual_scene_label_review_required'
    authorization_present = (
        allow_shadow_only_presentation
        and _provided(authorized_by)
        and _provided(authorization_reason)
    )
    manual_owner_present = _provided(manual_review_owner) and _provided(manual_review_target_date)

    blockers: list[dict[str, Any]] = []
    presentation_blockers: list[dict[str, Any]] = []
    if production_true_paths:
        blockers.append({'gate': 'production_scoring_guard', 'paths': production_true_paths})
        presentation_blockers.append({'gate': 'production_scoring_guard', 'paths': production_true_paths})
    if not avalcd_passed:
        blockers.append({'gate': 'avalcd_scene_blended_gate', 'actual': avalcd_sar.get('quality_gate')})
        presentation_blockers.append({'gate': 'avalcd_scene_blended_gate', 'actual': avalcd_sar.get('quality_gate')})
    if not snowslide_passed:
        blockers.append({
            'gate': 'snowslide_research_grade',
            'actual': snowslide_acceptance.get('decision'),
            'blockers': snowslide_acceptance.get('blockers'),
        })
    if manual_review_required:
        blockers.append({
            'gate': 'manual_component_review',
            'actual': 'pending',
            'required': 'completed manual_label_review_decisions.csv',
        })
    if not authorization_present:
        presentation_blockers.append({
            'gate': 'shadow_only_presentation_authorization',
            'actual': 'missing_or_incomplete',
            'required': 'allow flag, named authorizer, and authorization reason',
        })
    if not manual_owner_present:
        presentation_blockers.append({
            'gate': 'manual_review_owner',
            'actual': 'unassigned',
            'required': 'named reviewer and target completion date',
        })

    decision = 'client_presentation_ready_shadow_only'
    if production_true_paths:
        decision = 'blocked_production_guard_violation'
    elif not avalcd_passed:
        decision = 'blocked_avalcd_gate'
    elif not snowslide_passed:
        decision = 'blocked_sar_production_pending_manual_review'

    sar_production_ready = (
        snowslide_acceptance.get('decision') == 'accepted_research_grade'
        and bool(snowslide_acceptance.get('fresh_final_holdout_passed')) is True
        and bool(snowslide_acceptance.get('promotion_allowed')) is True
    )
    client_presentation_ready = (
        avalcd_passed
        and not production_true_paths
        and authorization_present
        and manual_owner_present
    )

    report = {
        'version': SCHEMA_VERSION,
        'generated_at': _now_iso(),
        'decision': decision,
        'client_presentation_ready': client_presentation_ready,
        'sar_production_ready': sar_production_ready,
        'phase7_ready': False,
        'production_scoring_allowed': False,
        'promotion_allowed': sar_production_ready,
        'next_gpu_run_authorized': False,
        'blockers': blockers,
        'presentation_blockers': presentation_blockers,
        'presentation_authorization': {
            'authorized': authorization_present,
            'presentation_authorization_id': str(uuid.uuid4()) if authorization_present else None,
            'authorized_at': _now_iso() if authorization_present else None,
            'authorized_by': authorized_by,
            'authorization_reason': authorization_reason,
            'authorization_evidence_ref': authorization_evidence_ref,
        },
        'avalcd_gate': {
            'status': 'passed' if avalcd_passed else 'blocked',
            'evaluation_mode': avalcd_sar.get('evaluation_mode'),
            'quality_gate': avalcd_quality,
            'metrics': _metric_summary(avalcd_metrics),
        },
        'snowslide_gate': {
            'decision': snowslide_acceptance.get('decision'),
            'accepted_research_grade': snowslide_acceptance.get('accepted_research_grade'),
            'metrics': _metric_summary(snow_metrics),
            'blockers': snowslide_acceptance.get('blockers') or [],
        },
        'non_gpu_sweep': {
            'decision': snowslide_sweep.get('decision'),
            'passing_candidate_count': snowslide_sweep.get('passing_candidate_count'),
            'bounded_candidate_warranted': snowslide_sweep.get('bounded_candidate_warranted'),
        },
        'manual_review': {
            'decision': manual_review_packet.get('decision'),
            'recommended_next_step': manual_review_packet.get('recommended_next_step'),
            'component_review_item_count': component_count,
            'next_gpu_run_authorized': manual_review_packet.get('next_gpu_run_authorized'),
            'owner': manual_review_owner,
            'target_date': manual_review_target_date,
            'owner_status': 'assigned' if manual_owner_present else 'unassigned',
            'competency_required': 'SAR domain literacy plus glaciology/avalanche field literacy',
            'estimated_reviewer_hours': 6,
        },
        'per_scene_snowslide_results': _per_scene_results(snowslide_diagnostics),
        'avalcd_region_coverage': _region_coverage(avalcd_benchmark),
        'statistical_limitations': {
            'snowslide_scene_count': 7,
            'confidence_intervals_computed': False,
            'note': 'SnowSlide n=7 is a qualification signal, not a high-power statistical estimate; per-scene variance should be disclosed.',
        },
        'current_stop_condition': (
            'Stop at manual SnowSlide v8 component review. The SAR lane is evidence-rich and shadow-ready for '
            'client discussion, but not accepted for production scoring because SnowSlide precision and F1 floors fail.'
        ),
        'next_manual_action': (
            'Complete manual_label_review_decisions.csv for the 30 v8 components, then resolve the worksheet. '
            'Only a labels-valid model-side outcome can justify a separate no-launch v9 candidate design review.'
        ),
        'source_inputs': {
            'avalcd_benchmark': str(avalcd_benchmark_path),
            'snowslide_acceptance': str(snowslide_acceptance_path),
            'snowslide_sweep': str(snowslide_sweep_path),
            'manual_review_packet': str(manual_review_packet_path),
            'snowslide_diagnostics': str(snowslide_diagnostics_path),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _deprecate_existing_v1_outputs(output_root)
    _write_json(output_root / 'european_shadow_sar_closeout_pack.json', report)
    (output_root / 'european_shadow_sar_closeout_pack.md').write_text(
        _render_markdown(report),
        encoding='utf-8',
    )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build a client-safe European shadow SAR v8 closeout packet.')
    parser.add_argument('--avalcd-benchmark', type=Path, default=DEFAULT_AVALCD_BENCHMARK)
    parser.add_argument('--snowslide-acceptance', type=Path, default=DEFAULT_SNOWSLIDE_ACCEPTANCE)
    parser.add_argument('--snowslide-sweep', type=Path, default=DEFAULT_SNOWSLIDE_SWEEP)
    parser.add_argument('--manual-review-packet', type=Path, default=DEFAULT_MANUAL_REVIEW_PACKET)
    parser.add_argument('--snowslide-diagnostics', type=Path, default=DEFAULT_SNOWSLIDE_DIAGNOSTICS)
    parser.add_argument('--output-root', type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument('--allow-shadow-only-presentation', action='store_true')
    parser.add_argument('--authorized-by')
    parser.add_argument('--authorization-reason')
    parser.add_argument('--authorization-evidence-ref')
    parser.add_argument('--manual-review-owner')
    parser.add_argument('--manual-review-target-date')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_closeout_pack(
        avalcd_benchmark_path=args.avalcd_benchmark,
        snowslide_acceptance_path=args.snowslide_acceptance,
        snowslide_sweep_path=args.snowslide_sweep,
        manual_review_packet_path=args.manual_review_packet,
        snowslide_diagnostics_path=args.snowslide_diagnostics,
        output_root=args.output_root,
        allow_shadow_only_presentation=args.allow_shadow_only_presentation,
        authorized_by=args.authorized_by,
        authorization_reason=args.authorization_reason,
        authorization_evidence_ref=args.authorization_evidence_ref,
        manual_review_owner=args.manual_review_owner,
        manual_review_target_date=args.manual_review_target_date,
    )
    print(json.dumps({
        'status': 'ok',
        'decision': report['decision'],
        'client_presentation_ready': report['client_presentation_ready'],
        'sar_production_ready': report['sar_production_ready'],
        'production_scoring_allowed': report['production_scoring_allowed'],
        'output_root': str(args.output_root),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
