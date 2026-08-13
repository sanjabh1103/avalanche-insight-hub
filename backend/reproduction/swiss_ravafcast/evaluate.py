from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.reproduction.swiss_ravafcast.constants import USAGE_BOUNDARY


SUMMARY_SCHEMA_VERSION = 'swiss_ravafcast_reproduction_summary_v1'


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'expected JSON object in {path}')
    return payload


def assert_research_only(payload: dict[str, Any], *, label: str) -> None:
    if payload.get('usage_boundary') != USAGE_BOUNDARY:
        raise ValueError(f'{label} must be research_only')
    if payload.get('production_scoring_allowed') is not False:
        raise ValueError(f'{label} must keep production_scoring_allowed=false')
    if payload.get('model_status_mutation_allowed') not in (False, None):
        raise ValueError(f'{label} must not allow model status mutation')


def _phase_status(
    *,
    validation_report: dict[str, Any],
    rf4_result: dict[str, Any],
    gpxyz_report: dict[str, Any],
    aggregation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    validation_reports = validation_report.get('reports') if isinstance(validation_report.get('reports'), list) else []
    rf4_metrics = rf4_result.get('metrics') if isinstance(rf4_result.get('metrics'), dict) else {}
    readiness = gpxyz_report.get('readiness') if isinstance(gpxyz_report.get('readiness'), dict) else {}
    aggregation_metrics = aggregation_result.get('metrics') if isinstance(aggregation_result.get('metrics'), dict) else {}

    return [
        {
            'phase': 0,
            'name': 'research_only_reproduction_sandbox',
            'status': 'complete',
            'evidence': 'backend/reproduction/swiss_ravafcast isolated from production scoring',
        },
        {
            'phase': 1,
            'name': 'envidat_data_acquisition_and_validation',
            'status': 'complete' if len(validation_reports) >= 2 else 'blocked_missing_validation_reports',
            'evidence': {
                'resource_count': len(validation_reports),
                'row_counts': {
                    str(report.get('resource_key')): report.get('row_count')
                    for report in validation_reports
                    if isinstance(report, dict)
                },
            },
        },
        {
            'phase': 2,
            'name': 'stage1_rf4_danger_reproduction',
            'status': 'initial_reproduction_signal_pending_parity_audit'
            if rf4_metrics
            else 'blocked_missing_rf4_metrics',
            'evidence': {
                'accuracy': rf4_metrics.get('accuracy'),
                'macro_f1': rf4_metrics.get('macro_f1'),
                'class_4_f1': (rf4_metrics.get('per_class_f1') or {}).get('4')
                if isinstance(rf4_metrics.get('per_class_f1'), dict)
                else None,
            },
        },
        {
            'phase': 3,
            'name': 'stage2_gpxyz_interpolation',
            'status': 'complete' if readiness.get('ready') is True else readiness.get('decision', 'blocked_missing_readiness'),
            'evidence': {
                'station_count': readiness.get('station_count'),
                'missing_required_columns': readiness.get('missing_required_columns') or [],
            },
        },
        {
            'phase': 4,
            'name': 'stage3_elevation_band_aggregation',
            'status': 'station_row_baseline_only_pending_gpxyz_grid_and_warning_polygons'
            if aggregation_metrics
            else 'blocked_missing_aggregation_metrics',
            'evidence': {
                'accuracy': aggregation_metrics.get('accuracy'),
                'macro_f1': aggregation_metrics.get('macro_f1'),
                'claim_boundary': aggregation_result.get('claim_boundary'),
            },
        },
        {
            'phase': 5,
            'name': 'consolidated_reproduction_summary',
            'status': 'complete',
            'evidence': SUMMARY_SCHEMA_VERSION,
        },
        {
            'phase': 6,
            'name': 'partner_schema_and_customer_wishlist_delta',
            'status': 'documented_pending_partner_data',
            'evidence': 'docs/EnviDat_to_Partner_Schema_Mapping.md and docs/MVP V2/Remote_Sensing_Operational_Wishlist_Delta.md',
        },
        {
            'phase': 7,
            'name': 'operational_avalanche_landslide_detection',
            'status': 'not_authorized_pending_validation_datasets_and_release_gates',
            'evidence': 'no full operational detection claim is allowed from Swiss reproduction artifacts alone',
        },
    ]


def build_reproduction_summary(
    *,
    validation_report: dict[str, Any],
    rf4_result: dict[str, Any],
    gpxyz_report: dict[str, Any],
    aggregation_result: dict[str, Any],
) -> dict[str, Any]:
    for label, payload in (
        ('validation_report', validation_report),
        ('rf4_result', rf4_result),
        ('gpxyz_report', gpxyz_report),
        ('aggregation_result', aggregation_result),
    ):
        assert_research_only(payload, label=label)

    readiness = gpxyz_report.get('readiness') if isinstance(gpxyz_report.get('readiness'), dict) else {}
    blockers = [
        {
            'blocker': 'station_coordinates_required_for_gpxyz',
            'why': 'The downloaded RF1/RF2 CSVs include station id and elevation but not latitude/longitude.',
            'needed_input': 'station_code, latitude, longitude, elevation_m station metadata table',
            'severity': 'high',
        },
        {
            'blocker': 'official_warning_region_geometry_required',
            'why': 'Stage-3 RAvaFcast parity needs warning-region polygons and grid aggregation, not only station-row grouping.',
            'needed_input': 'official warning-region polygons and elevation-band policy',
            'severity': 'high',
        },
        {
            'blocker': 'operational_detection_validation_required',
            'why': 'The customer wishlist adds avalanche/landslide detection maps and alerts, which need separate labeled validation datasets.',
            'needed_input': 'task-specific avalanche and landslide detection labels, alert policy, and release gates',
            'severity': 'high',
        },
    ]
    if readiness.get('ready') is True:
        blockers = [blocker for blocker in blockers if blocker['blocker'] != 'station_coordinates_required_for_gpxyz']

    return {
        'schema_version': SUMMARY_SCHEMA_VERSION,
        'usage_boundary': USAGE_BOUNDARY,
        'production_scoring_allowed': False,
        'model_status_mutation_allowed': False,
        'full_operational_detection_claim_allowed': False,
        'sar_remote_sensing_shadow_gated': True,
        'rf4_claim_boundary': 'initial_reproduction_signal_pending_parity_audit',
        'stage3_claim_boundary': 'station_row_baseline_not_full_ravafcast_grid_warning_region_parity',
        'swiss_reproduction_phase_status': _phase_status(
            validation_report=validation_report,
            rf4_result=rf4_result,
            gpxyz_report=gpxyz_report,
            aggregation_result=aggregation_result,
        ),
        'headline_metrics': {
            'rf4_accuracy': (rf4_result.get('metrics') or {}).get('accuracy'),
            'rf4_macro_f1': (rf4_result.get('metrics') or {}).get('macro_f1'),
            'rf4_class_4_f1': ((rf4_result.get('metrics') or {}).get('per_class_f1') or {}).get('4')
            if isinstance((rf4_result.get('metrics') or {}).get('per_class_f1'), dict)
            else None,
            'elev_simple_station_row_accuracy': (aggregation_result.get('metrics') or {}).get('accuracy'),
            'elev_simple_station_row_macro_f1': (aggregation_result.get('metrics') or {}).get('macro_f1'),
            'gpxyz_decision': readiness.get('decision'),
        },
        'remaining_blockers': blockers,
        'next_actions': [
            'Run RF4 feature/parity audit before presenting the current accuracy as paper-comparable.',
            'Request or derive reviewed Swiss station metadata with station_code, latitude, longitude, and elevation_m.',
            'Add official warning-region polygons before claiming full RAvaFcast Stage-3 parity.',
            'Keep avalanche/landslide remote-sensing detection maps shadow-only until separate validation datasets and gates exist.',
            'Use the customer wishlist delta as a product-scope backlog, not as evidence of operational readiness.',
        ],
    }


def markdown_summary(payload: dict[str, Any]) -> str:
    lines = [
        '# Swiss RAvaFcast Reproduction Summary',
        '',
        f"Schema: `{payload['schema_version']}`",
        '',
        '## Claim Boundary',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Model status mutation allowed | `{str(payload['model_status_mutation_allowed']).lower()}` |",
        f"| Full operational detection claim allowed | `{str(payload['full_operational_detection_claim_allowed']).lower()}` |",
        f"| SAR / remote sensing shadow gated | `{str(payload['sar_remote_sensing_shadow_gated']).lower()}` |",
        f"| RF4 claim boundary | `{payload['rf4_claim_boundary']}` |",
        f"| Stage 3 claim boundary | `{payload['stage3_claim_boundary']}` |",
        '',
        '## Headline Metrics',
        '',
        '| Metric | Value |',
        '|---|---:|',
    ]
    for key, value in payload['headline_metrics'].items():
        lines.append(f'| `{key}` | `{value}` |')

    lines.extend(['', '## Phase Status', '', '| Phase | Status | Evidence |', '|---:|---|---|'])
    for phase in payload['swiss_reproduction_phase_status']:
        lines.append(f"| {phase['phase']} | `{phase['status']}` | {phase['evidence']} |")

    lines.extend(['', '## Remaining Blockers', '', '| Blocker | Needed Input | Severity |', '|---|---|---|'])
    for blocker in payload['remaining_blockers']:
        lines.append(f"| `{blocker['blocker']}` | {blocker['needed_input']} | {blocker['severity']} |")

    lines.extend(['', '## Next Actions', ''])
    for action in payload['next_actions']:
        lines.append(f'- {action}')
    lines.append('')
    return '\n'.join(lines)


def write_reproduction_summary(
    *,
    validation_report_path: Path,
    rf4_result_path: Path,
    gpxyz_report_path: Path,
    aggregation_result_path: Path,
    output_json: Path,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    payload = build_reproduction_summary(
        validation_report=read_json(validation_report_path),
        rf4_result=read_json(rf4_result_path),
        gpxyz_report=read_json(gpxyz_report_path),
        aggregation_result=read_json(aggregation_result_path),
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    if output_markdown is not None:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(markdown_summary(payload), encoding='utf-8')
    return payload
