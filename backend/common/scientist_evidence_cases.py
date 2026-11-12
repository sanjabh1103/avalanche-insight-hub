"""Post-publication, scientist-only verification cases.

Cases are created after a forecast run receives its immutable run ID.  They
are deliberately best-effort and never affect publication, public risk, or
model promotion.  Existing cases are never overwritten.
"""
from __future__ import annotations

import copy
import os
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from backend.common.evidence_replay import build_evidence_replay_frame
from backend.common.supabase_io import has_supabase_credentials, rest_get, rest_insert


SCIENTIST_EVIDENCE_CASES_ENABLED = os.getenv(
    'SCIENTIST_EVIDENCE_CASES_ENABLED', 'false',
).lower() not in {'0', 'false', 'off', 'no'}
MAX_SCIENTIST_EVIDENCE_CASES = int(os.getenv('MAX_SCIENTIST_EVIDENCE_CASES', '12'))


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stable_case_id(*parts: object) -> str:
    key = '|'.join(str(part) for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'avalanche-insight-hub:evidence-replay:{key}'))


def _case_spec(cell: Mapping[str, Any]) -> tuple[str, str, str, int] | None:
    packet = _record(cell.get('verification_packet'))
    anomaly_state = packet.get('anomaly_state')
    risk_score = _as_int(cell.get('risk_score'))
    if cell.get('public_eligible') is False or cell.get('disabled') is True:
        return (
            'masked_terrain',
            'public_mask_validation',
            'Confirm that the withheld cell cannot be interpreted as an ordinary low-risk forecast.',
            4,
        )
    if anomaly_state in {'watch', 'anomaly'}:
        return (
            'verification_discrepancy',
            'verification_discrepancy_review',
            'Review the modelled state against independent observations, baseline residuals, freshness, and provenance.',
            5 if anomaly_state == 'anomaly' else 4,
        )
    if cell.get('runout_seed') is True or risk_score >= 4:
        return (
            'runout',
            'runout_validation',
            'Review whether the high-risk/runout context is supported by the attached model and evidence replay.',
            5 if risk_score >= 4 else 4,
        )
    if cell.get('uncertainty_class') == 'high' or cell.get('snowpack_proxy'):
        return (
            'weak_layer',
            'weak_layer_validation',
            'Review whether the snowpack proxy, uncertainty, and independent evidence support the current claim boundary.',
            4,
        )
    return None


def build_scientist_evidence_cases(
    *,
    forecast_run_id: str,
    region_key: str,
    region_name: str | None,
    forecast_date: str | None,
    forecast_grid_id: str | None = None,
    rows: Sequence[Mapping[str, Any]],
    model_metadata: Mapping[str, Any] | None,
    max_cases: int = MAX_SCIENTIST_EVIDENCE_CASES,
) -> list[dict[str, Any]]:
    """Build review cases without mutating rows or public forecast payloads."""
    cases: list[dict[str, Any]] = []
    metadata = _record(model_metadata)
    for cell in rows:
        if len(cases) >= max(0, max_cases):
            break
        if not isinstance(cell, Mapping):
            continue
        cell_record = _record(cell)
        spec = _case_spec(cell_record)
        if spec is None:
            continue
        case_type, gate_key, summary, priority = spec
        forecast_hour = _as_int(cell_record.get('forecast_hour'))
        replay = build_evidence_replay_frame(
            forecast_run_id=forecast_run_id,
            region_key=region_key,
            forecast_date=forecast_date,
            forecast_hour=forecast_hour,
            forecast_grid_id=forecast_grid_id,
            cell=cell_record,
            model_metadata=metadata,
        )
        cell_snapshot = copy.deepcopy(cell_record)
        cell_snapshot['evidence_replay'] = replay
        evidence = {
            'evidence_replay': replay,
            'verification_packet': replay['raw_layers']['verification_packet'],
            'fusion_evidence': replay['raw_layers']['fusion_evidence'],
            'review_scope': 'independent_evidence_vs_model_claim',
        }
        row = _as_int(cell_record.get('row'))
        col = _as_int(cell_record.get('col'))
        cases.append({
            'id': _stable_case_id(forecast_run_id, region_key, forecast_hour, row, col, gate_key),
            'case_type': case_type,
            'status': 'pending',
            'priority': priority,
            'region_key': region_key,
            'region_name': region_name,
            'forecast_run_id': forecast_run_id,
            'forecast_grid_id': forecast_grid_id,
            'forecast_hour': forecast_hour,
            'cell_row': row,
            'cell_col': col,
            'title': f"{case_type.replace('_', ' ')} review: r{row} c{col}",
            'summary': summary,
            'evidence': evidence,
            'cell_snapshot': cell_snapshot,
            'model_metadata': copy.deepcopy(metadata),
            'gate_key': gate_key,
            'claim_boundary': 'scientist_only_evidence_replay_review',
            'case_origin': 'forecast_publication',
            'requires_two_reviewers': priority >= 5,
            'signoff_scope': 'evidence_replay_review',
        })
    return cases


def _existing_case_ids(case_ids: Sequence[str]) -> set[str]:
    existing: set[str] = set()
    for start in range(0, len(case_ids), 100):
        chunk = case_ids[start:start + 100]
        if not chunk:
            continue
        quoted = ','.join(f'"{case_id}"' for case_id in chunk)
        rows = rest_get(
            'scientist_validation_cases',
            {'select': 'id', 'id': f'in.({quoted})'},
        )
        existing.update(str(row['id']) for row in rows if row.get('id'))
    return existing


def sync_missing_scientist_evidence_cases(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Insert missing cases only; never overwrite a scientist review."""
    if not has_supabase_credentials():
        return {
            'status': 'credentials_unavailable',
            'cases_total': len(cases),
            'cases_synced': 0,
        }
    records = [dict(case) for case in cases if case.get('id')]
    existing_ids = _existing_case_ids([str(case['id']) for case in records])
    missing = [case for case in records if str(case['id']) not in existing_ids]
    if missing:
        rest_insert('scientist_validation_cases', missing, returning='minimal', timeout_seconds=120)
    return {
        'status': 'ok',
        'cases_total': len(records),
        'cases_existing': len(existing_ids),
        'cases_synced': len(missing),
    }


def materialize_published_evidence_cases(
    *,
    forecast_run_id: str,
    region_key: str,
    region_name: str | None,
    forecast_date: str | None,
    forecast_grid_id: str | None = None,
    rows: Sequence[Mapping[str, Any]],
    model_metadata: Mapping[str, Any] | None,
    enabled: bool = SCIENTIST_EVIDENCE_CASES_ENABLED,
) -> dict[str, Any]:
    """Create post-publication review cases behind an explicit feature flag."""
    if not enabled:
        return {'status': 'disabled', 'cases_total': 0, 'cases_synced': 0}
    cases = build_scientist_evidence_cases(
        forecast_run_id=forecast_run_id,
        region_key=region_key,
        region_name=region_name,
        forecast_date=forecast_date,
        forecast_grid_id=forecast_grid_id,
        rows=rows,
        model_metadata=model_metadata,
    )
    if not cases:
        return {'status': 'no_review_cases', 'cases_total': 0, 'cases_synced': 0}
    return sync_missing_scientist_evidence_cases(cases)
