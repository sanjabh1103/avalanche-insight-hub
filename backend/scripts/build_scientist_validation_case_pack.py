"""Build a starter scientist-validation case pack from forecast artifacts.

The output is review evidence only. It should seed the validation workbench or
meeting packet, not promote SAR, MTS-LSTM, TreeSHAP, Whitebox, or field
validation claims by itself.
"""

from __future__ import annotations

import argparse
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.supabase_io import has_supabase_credentials, rest_get, rest_upsert


CASE_TYPES = {
    'weak_layer',
    'runout',
    'false_positive',
    'false_negative',
    'masked_terrain',
    'sar_candidate',
    'model_gate',
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def _stable_case_id(*parts: object) -> str:
    key = '|'.join(str(part) for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'avalanche-insight-hub:scientist-validation:{key}'))


def _priority_for_cell(cell: dict[str, Any]) -> int:
    risk = int(cell.get('risk_score') or 0)
    uncertainty = str(cell.get('uncertainty_class') or '')
    if risk >= 4 or uncertainty == 'high':
        return 5
    if risk >= 3:
        return 4
    return 3


def _case(
    *,
    case_type: str,
    title: str,
    summary: str,
    priority: int,
    region: dict[str, Any],
    forecast_hour: int | None,
    cell: dict[str, Any] | None,
    evidence: dict[str, Any],
    gate_key: str,
) -> dict[str, Any]:
    if case_type not in CASE_TYPES:
        raise ValueError(f'Unsupported case_type: {case_type}')
    cell_row = cell.get('row') if cell else None
    cell_col = cell.get('col') if cell else None
    case_id = _stable_case_id(
        case_type,
        region.get('region_key'),
        region.get('forecast_date'),
        forecast_hour,
        cell_row,
        cell_col,
        gate_key,
    )
    return {
        'id': case_id,
        'case_type': case_type,
        'status': 'pending',
        'priority': priority,
        'region_key': region.get('region_key'),
        'region_name': region.get('region_name'),
        'forecast_run_id': region.get('forecast_run_id'),
        'forecast_grid_id': region.get('forecast_grid_id'),
        'forecast_hour': forecast_hour,
        'cell_row': cell_row,
        'cell_col': cell_col,
        'title': title,
        'summary': summary,
        'evidence': evidence,
        'cell_snapshot': cell or {},
        'model_metadata': region.get('model_metadata') or {},
        'gate_key': gate_key,
        'claim_boundary': 'decision_support_validation',
        'requires_two_reviewers': priority >= 5,
        'signoff_scope': 'single_case_review',
    }


def _region_context(grid: dict[str, Any]) -> dict[str, Any]:
    metadata = grid.get('model_metadata') if isinstance(grid.get('model_metadata'), dict) else {}
    return {
        'region_key': grid.get('region_key'),
        'region_name': grid.get('region_name'),
        'forecast_date': grid.get('forecast_date'),
        'forecast_run_id': metadata.get('forecast_run_id') or grid.get('forecast_run_id'),
        'forecast_grid_id': metadata.get('compatibility_forecast_grid_id') or grid.get('id'),
        'model_metadata': metadata,
    }


def _cell_evidence(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        'risk_score': cell.get('risk_score'),
        'probability': cell.get('probability'),
        'uncertainty_class': cell.get('uncertainty_class'),
        'uncertainty_span': cell.get('uncertainty_span'),
        'problem_slug': cell.get('problem_slug'),
        'problem_type': cell.get('problem_type'),
        'runout_seed': cell.get('runout_seed'),
        'public_eligible': cell.get('public_eligible'),
        'public_mask_reasons': cell.get('public_mask_reasons') or [],
        'explainability_mode': cell.get('explainability_mode'),
        'explainability_reason': cell.get('explainability_reason'),
        'dominant_driver_feature': cell.get('dominant_driver_feature'),
        'snowpack_proxy': cell.get('snowpack_proxy'),
        'coverage_flags': cell.get('coverage_flags'),
    }


def _collect_cell_cases(forecast_grids: list[dict[str, Any]], max_per_type: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for grid in forecast_grids:
        region = _region_context(grid)
        cells = grid.get('grid_geojson') if isinstance(grid.get('grid_geojson'), list) else []
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            hour = int(cell.get('forecast_hour') or 0)
            evidence = _cell_evidence(cell)
            if cell.get('public_eligible') is False and counts['masked_terrain'] < max_per_type:
                cases.append(_case(
                    case_type='masked_terrain',
                    title=f"Masked terrain review: r{cell.get('row')} c{cell.get('col')}",
                    summary='Confirm the cell is withheld clearly and is not being interpreted as normal low risk.',
                    priority=4,
                    region=region,
                    forecast_hour=hour,
                    cell=cell,
                    evidence=evidence,
                    gate_key='public_mask_validation',
                ))
                counts['masked_terrain'] += 1
            if (cell.get('runout_seed') or int(cell.get('risk_score') or 0) >= 4) and counts['runout'] < max_per_type:
                cases.append(_case(
                    case_type='runout',
                    title=f"Runout plausibility review: r{cell.get('row')} c{cell.get('col')}",
                    summary='Review whether the runout context is plausible for known terrain traps, roads, and assets.',
                    priority=_priority_for_cell(cell),
                    region=region,
                    forecast_hour=hour,
                    cell=cell,
                    evidence=evidence,
                    gate_key='runout_validation',
                ))
                counts['runout'] += 1
            if (cell.get('snowpack_proxy') or cell.get('uncertainty_class') == 'high') and counts['weak_layer'] < max_per_type:
                cases.append(_case(
                    case_type='weak_layer',
                    title=f"Weak-layer proxy review: r{cell.get('row')} c{cell.get('col')}",
                    summary='Review whether snowpack proxy and uncertainty evidence are adequate for decision-support wording.',
                    priority=_priority_for_cell(cell),
                    region=region,
                    forecast_hour=hour,
                    cell=cell,
                    evidence=evidence,
                    gate_key='weak_layer_validation',
                ))
                counts['weak_layer'] += 1
    return cases


def _collect_outcome_cases(outcomes: list[dict[str, Any]], max_per_type: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for outcome in outcomes:
        predicted = int(outcome.get('predicted_risk_score') or 0)
        observed = bool(outcome.get('event_observed'))
        if predicted >= 4 and not observed and counts['false_positive'] < max_per_type:
            case_type = 'false_positive'
        elif predicted <= 2 and observed and counts['false_negative'] < max_per_type:
            case_type = 'false_negative'
        else:
            continue
        counts[case_type] += 1
        region = {
            'region_key': outcome.get('region_key'),
            'region_name': outcome.get('region_name'),
            'forecast_run_id': outcome.get('forecast_run_id'),
            'forecast_grid_id': outcome.get('forecast_grid_id') or outcome.get('forecast_id'),
            'model_metadata': {},
        }
        cell = {
            'row': outcome.get('cell_row'),
            'col': outcome.get('cell_col'),
            'risk_score': predicted,
        }
        cases.append(_case(
            case_type=case_type,
            title=f"{case_type.replace('_', ' ')} review: r{cell['row']} c{cell['col']}",
            summary='Review whether this apparent forecast failure is caused by data, terrain, label matching, or model behavior.',
            priority=5,
            region=region,
            forecast_hour=outcome.get('forecast_hour'),
            cell=cell,
            evidence=outcome,
            gate_key='forecast_outcome_failure_review',
        ))
    return cases


def _field_report_region_key(report: dict[str, Any]) -> str | None:
    features = report.get('features') if isinstance(report.get('features'), dict) else {}
    return report.get('region_key') or features.get('region_key')


def _field_report_region_name(report: dict[str, Any]) -> str | None:
    features = report.get('features') if isinstance(report.get('features'), dict) else {}
    return report.get('region_name') or features.get('region_name')


def _collect_field_report_cases(field_reports: list[dict[str, Any]], max_per_type: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for report in field_reports:
        if counts['weak_layer'] >= max_per_type:
            break
        features = report.get('features') if isinstance(report.get('features'), dict) else {}
        region = {
            'region_key': _field_report_region_key(report),
            'region_name': _field_report_region_name(report),
            'forecast_date': report.get('observed_at') or report.get('report_date') or report.get('created_at'),
            'forecast_run_id': report.get('forecast_run_id'),
            'forecast_grid_id': report.get('forecast_grid_id') or report.get('forecast_id'),
            'model_metadata': {
                'source': 'field_reports',
                'field_report_id': report.get('id'),
                'observer_role': report.get('observer_role'),
            },
        }
        cell = {
            'row': report.get('cell_row') or features.get('cell_row'),
            'col': report.get('cell_col') or features.get('cell_col'),
            'risk_score': report.get('observed_risk_score') or features.get('observed_risk_score'),
            'problem_type': report.get('problem_type') or features.get('problem_type'),
            'snowpack_proxy': report.get('snowpack_profile') or features.get('snowpack_profile'),
        }
        cases.append(_case(
            case_type='weak_layer',
            title=f"Field-report weak-layer review: {report.get('id') or 'unlinked report'}",
            summary='Review whether the field report provides grounded weak-layer evidence for the forecast case.',
            priority=4,
            region=region,
            forecast_hour=report.get('forecast_hour'),
            cell=cell,
            evidence=report,
            gate_key='field_report_validation',
        ))
        counts['weak_layer'] += 1
    return cases


def _collect_gate_cases(
    *,
    dynamic_model_candidate: dict[str, Any],
    publication_proof: dict[str, Any],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    region = {
        'region_key': publication_proof.get('region_key'),
        'region_name': publication_proof.get('region_name'),
        'forecast_run_id': publication_proof.get('forecast_run_id'),
        'forecast_grid_id': None,
        'model_metadata': {
            'dynamic_model_candidate': dynamic_model_candidate,
            'publication_proof': publication_proof,
        },
    }
    if dynamic_model_candidate and not dynamic_model_candidate.get('ready_for_activation'):
        cases.append(_case(
            case_type='model_gate',
            title='MTS-LSTM promotion gate review',
            summary='Confirm the candidate model remains gated until benchmark, SAR, and quality gates pass.',
            priority=4,
            region=region,
            forecast_hour=None,
            cell=None,
            evidence=dynamic_model_candidate,
            gate_key='mts_lstm_promotion_gate',
        ))
    sar_gates = dynamic_model_candidate.get('gates') if isinstance(dynamic_model_candidate.get('gates'), dict) else {}
    if not sar_gates.get('sar_release_gate_passed'):
        cases.append(_case(
            case_type='sar_candidate',
            title='SAR candidate release gate review',
            summary='Confirm SAR remains candidate/off-path until held-out release and volume gates pass.',
            priority=4,
            region=region,
            forecast_hour=None,
            cell=None,
            evidence=sar_gates,
            gate_key='sar_release_gate',
        ))
    return cases


def _normalize_region_keys(region_keys: set[str] | list[str] | tuple[str, ...] | None) -> set[str]:
    return {str(region_key) for region_key in (region_keys or set()) if str(region_key).strip()}


def _filter_by_region(items: list[dict[str, Any]], region_keys: set[str]) -> list[dict[str, Any]]:
    if not region_keys:
        return items
    return [
        item for item in items
        if (item.get('region_key') or _field_report_region_key(item)) in region_keys
    ]


def build_case_pack(
    artifact_dir: Path,
    max_per_type: int = 6,
    region_keys: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    requested_region_keys = _normalize_region_keys(region_keys)
    forecast_grids = _load_json(artifact_dir / 'forecast_grids.json', [])
    if isinstance(forecast_grids, dict):
        forecast_grids = [forecast_grids]
    outcomes = _load_json(artifact_dir / 'forecast_outcomes.json', [])
    field_reports = _load_json(artifact_dir / 'field_reports.json', [])
    dynamic_model_candidate = _load_json(artifact_dir / 'dynamic_model_candidate.json', {})
    publication_proof = _load_json(artifact_dir / 'publication_proof.json', {})

    forecast_grids = _filter_by_region(forecast_grids if isinstance(forecast_grids, list) else [], requested_region_keys)
    outcomes = _filter_by_region(outcomes if isinstance(outcomes, list) else [], requested_region_keys)
    field_reports = _filter_by_region(field_reports if isinstance(field_reports, list) else [], requested_region_keys)
    include_gate_cases = not requested_region_keys or publication_proof.get('region_key') in requested_region_keys

    cases = []
    cases.extend(_collect_cell_cases(forecast_grids, max_per_type=max_per_type))
    cases.extend(_collect_outcome_cases(outcomes, max_per_type=max_per_type))
    cases.extend(_collect_field_report_cases(field_reports, max_per_type=max_per_type))
    if include_gate_cases:
        cases.extend(_collect_gate_cases(
            dynamic_model_candidate=dynamic_model_candidate if isinstance(dynamic_model_candidate, dict) else {},
            publication_proof=publication_proof if isinstance(publication_proof, dict) else {},
        ))

    type_counts = Counter(case['case_type'] for case in cases)
    warnings = []
    if requested_region_keys and not cases:
        warnings.append('not_enough_grounded_cases_for_requested_regions')
    return {
        'schema_version': 'scientist-validation-case-pack/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'artifact_dir': str(artifact_dir),
        'summary': {
            'case_count': len(cases),
            'case_type_counts': dict(sorted(type_counts.items())),
            'requested_region_keys': sorted(requested_region_keys),
            'grounded_source_counts': {
                'forecast_grids': len(forecast_grids),
                'forecast_outcomes': len(outcomes),
                'field_reports': len(field_reports),
                'gate_evidence': 1 if include_gate_cases and isinstance(publication_proof, dict) and publication_proof else 0,
            },
            'warnings': warnings,
            'claim_boundary': 'review_evidence_only_not_scientist_validation_closure',
        },
        'cases': cases,
    }


def _existing_case_ids(case_ids: list[str]) -> set[str]:
    existing: set[str] = set()
    if not case_ids:
        return existing
    for start in range(0, len(case_ids), 100):
        chunk = case_ids[start:start + 100]
        quoted = ','.join(f'"{case_id}"' for case_id in chunk)
        rows = rest_get(
            'scientist_validation_cases',
            {
                'select': 'id',
                'id': f'in.({quoted})',
            },
        )
        existing.update(str(row['id']) for row in rows if row.get('id'))
    return existing


def sync_case_pack_to_supabase(pack: dict[str, Any], *, update_existing: bool = False) -> dict[str, Any]:
    if not has_supabase_credentials():
        raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to sync validation cases')
    cases = [case for case in pack.get('cases', []) if isinstance(case, dict) and case.get('id')]
    existing_ids = _existing_case_ids([str(case['id']) for case in cases])
    if update_existing:
        records = cases
    else:
        records = [case for case in cases if str(case['id']) not in existing_ids]
    if records:
        rest_upsert(
            'scientist_validation_cases',
            records,
            on_conflict='id',
            returning='minimal',
            timeout_seconds=120,
        )
    return {
        'sync_status': 'ok',
        'cases_total': len(cases),
        'cases_existing': len(existing_ids),
        'cases_synced': len(records),
        'update_existing': update_existing,
        'claim_boundary': 'review_evidence_only_not_scientist_validation_closure',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build scientist validation case pack from forecast artifacts.')
    parser.add_argument('--artifact-dir', default='backend/artifacts/20260504T070406Z')
    parser.add_argument('--output', default=None)
    parser.add_argument('--max-per-type', type=int, default=6)
    parser.add_argument(
        '--region-key',
        action='append',
        default=[],
        help='Restrict the pack to grounded artifacts for this region key. Repeat for multiple regions.',
    )
    parser.add_argument(
        '--sync-supabase',
        action='store_true',
        help='Insert missing cases into scientist_validation_cases using the service-role key.',
    )
    parser.add_argument(
        '--update-existing',
        action='store_true',
        help='Update existing cases by id. By default existing cases are preserved to avoid overwriting reviews.',
    )
    args = parser.parse_args(argv)

    artifact_dir = Path(args.artifact_dir)
    pack = build_case_pack(artifact_dir, max_per_type=args.max_per_type, region_keys=set(args.region_key))
    output = Path(args.output) if args.output else artifact_dir / 'scientist_validation_case_pack.json'
    output.write_text(json.dumps(pack, indent=2), encoding='utf-8')
    summary = {'output': str(output), **pack['summary']}
    if args.sync_supabase:
        summary['supabase_sync'] = sync_case_pack_to_supabase(
            pack,
            update_existing=bool(args.update_existing),
        )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
