"""Seed synthetic demo-only scientist validation data.

The rows created by this script are deliberately not scientific evidence. They
exist to unblock credentialed UI and export smoke tests while keeping the real
Himalayan validation queue grounded-only.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from backend.scripts.provision_scientist_demo_user import resolve_supabase_connection


DEMO_REGION_KEY = 'demo_himalayas_synthetic'
CLAIM_BOUNDARY = 'synthetic_demo_not_scientific_evidence'
DEMO_CASE_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, 'avalanche-insight-hub:synthetic-scientist-demo:case:v1'))
DEMO_DAILY_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, 'avalanche-insight-hub:synthetic-scientist-demo:daily:v1'))


def _headers(admin_key: str, prefer: str = 'resolution=merge-duplicates,return=representation') -> dict[str, str]:
    return {
        'apikey': admin_key,
        'Authorization': f'Bearer {admin_key}',
        'Content-Type': 'application/json',
        'Prefer': prefer,
    }


def _postgrest_upsert(
    *,
    supabase_url: str,
    admin_key: str,
    table: str,
    records: list[dict[str, Any]],
    on_conflict: str = 'id',
) -> list[dict[str, Any]]:
    response = requests.post(
        f'{supabase_url.rstrip("/")}/rest/v1/{table}',
        headers=_headers(admin_key),
        params={'on_conflict': on_conflict},
        json=records,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f'UPSERT {table} failed ({response.status_code}): {response.text}')
    if not response.text.strip():
        return []
    payload = response.json()
    return payload if isinstance(payload, list) else [payload]


def build_synthetic_scientist_case(*, created_by: str | None = None) -> dict[str, Any]:
    synthetic_flags = {
        'synthetic_demo': True,
        'training_eligible': False,
        'production_eligible': False,
        'grounded_himalayan_evidence': False,
        'claim_boundary': CLAIM_BOUNDARY,
    }
    return {
        'id': DEMO_CASE_ID,
        'case_type': 'weak_layer',
        'status': 'pending',
        'priority': 5,
        'region_key': DEMO_REGION_KEY,
        'region_name': 'Synthetic Himalayan Demo',
        'forecast_run_id': None,
        'forecast_grid_id': None,
        'forecast_hour': 12,
        'cell_row': 8,
        'cell_col': 9,
        'title': 'Synthetic demo weak-layer review: r8 c9',
        'summary': (
            'Synthetic case for validating scientist co-working flow only. '
            'Do not use as Himalayan event evidence.'
        ),
        'evidence': {
            **synthetic_flags,
            'forecast_outcomes': [],
            'field_reports': [],
            'snowpack_proxy': {
                'estimated_shear_strength': 2.4,
                'snow_settlement_index': 0.42,
                'method': 'synthetic_demo_proxy_v1',
            },
            'scenario': 'Demo case representing a persistent weak-layer discussion workflow.',
        },
        'cell_snapshot': {
            **synthetic_flags,
            'row': 8,
            'col': 9,
            'risk_score': 4,
            'probability': 0.72,
            'uncertainty_class': 'high',
            'problem_type': 'Persistent weak layers',
        },
        'model_metadata': {
            **synthetic_flags,
            'model_version': 'synthetic_demo_not_model_output',
            'source': 'seed_scientist_demo_data.py',
        },
        'gate_key': 'synthetic_demo_flow_validation',
        'claim_boundary': CLAIM_BOUNDARY,
        'requires_two_reviewers': True,
        'disagreement_count': 0,
        'signoff_scope': 'synthetic_demo_flow_only',
        'assigned_to': created_by,
        'created_by': created_by,
    }


def build_synthetic_daily_verification(*, reviewer_id: str | None = None) -> dict[str, Any]:
    return {
        'id': DEMO_DAILY_ID,
        'reviewer_id': reviewer_id,
        'region_key': DEMO_REGION_KEY,
        'region_name': 'Synthetic Himalayan Demo',
        'verification_date': date.today().isoformat(),
        'forecast_run_id': None,
        'forecast_grid_id': None,
        'forecast_hour': 12,
        'scientist_danger_level': '3',
        'model_danger_level': '4',
        'observed_outcome': 'unknown',
        'official_avalanche_problem': 'persistent_weak_layers',
        'model_avalanche_problem': 'wind_slab',
        'confidence': 0.65,
        'notes': 'Synthetic demo-only paired verification row; not scientific evidence.',
        'evidence_refs': {
            'synthetic_demo': True,
            'training_eligible': False,
            'production_eligible': False,
            'grounded_himalayan_evidence': False,
            'claim_boundary': CLAIM_BOUNDARY,
        },
    }


def seed_synthetic_scientist_demo_data(*, scientist_user_id: str | None = None) -> dict[str, Any]:
    connection = resolve_supabase_connection()
    case_rows = _postgrest_upsert(
        supabase_url=connection.url,
        admin_key=connection.admin_key,
        table='scientist_validation_cases',
        records=[build_synthetic_scientist_case(created_by=scientist_user_id)],
    )
    daily_rows = _postgrest_upsert(
        supabase_url=connection.url,
        admin_key=connection.admin_key,
        table='scientist_daily_verifications',
        records=[build_synthetic_daily_verification(reviewer_id=scientist_user_id)],
    )
    return {
        'seed_status': 'ok',
        'region_key': DEMO_REGION_KEY,
        'claim_boundary': CLAIM_BOUNDARY,
        'synthetic_demo': True,
        'training_eligible': False,
        'production_eligible': False,
        'case_ids': [str(row.get('id') or DEMO_CASE_ID) for row in case_rows] or [DEMO_CASE_ID],
        'daily_verification_ids': [str(row.get('id') or DEMO_DAILY_ID) for row in daily_rows] or [DEMO_DAILY_ID],
        'admin_key_source': connection.admin_key_source,
    }


def _load_scientist_user_id(env_path: Path) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if line.startswith('SCIENTIST_DEMO_USER_ID='):
            value = line.split('=', 1)[1].strip()
            return value or None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Seed synthetic demo-only scientist validation data.')
    parser.add_argument('--scientist-env', default='.env.scientist.local')
    args = parser.parse_args(argv)

    summary = seed_synthetic_scientist_demo_data(
        scientist_user_id=_load_scientist_user_id(Path(args.scientist_env)),
    )
    summary['seeded_at'] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
