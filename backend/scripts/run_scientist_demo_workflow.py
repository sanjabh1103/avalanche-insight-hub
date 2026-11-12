"""Run a credentialed scientist demo workflow without printing secrets."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from backend.scripts.seed_scientist_demo_data import CLAIM_BOUNDARY, DEMO_CASE_ID, DEMO_REGION_KEY


DEMO_REVIEW_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, 'avalanche-insight-hub:synthetic-scientist-demo:review:v1'))
DEMO_ACTION_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, 'avalanche-insight-hub:synthetic-scientist-demo:action:v1'))


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (Path('.env.netlify'), Path('.env.local'), Path('.env.scientist.local')):
        values.update(_load_env_file(path))
    values.update({key: value for key, value in os.environ.items() if key.startswith(('SUPABASE_', 'VITE_SUPABASE_', 'SCIENTIST_'))})
    return values


def _required(values: dict[str, str], *names: str) -> str:
    for name in names:
        value = values.get(name)
        if value:
            return value
    raise RuntimeError(f'Missing required env value: {" or ".join(names)}')


def _sign_in(values: dict[str, str]) -> dict[str, Any]:
    supabase_url = _required(values, 'SUPABASE_URL', 'VITE_SUPABASE_URL').rstrip('/')
    publishable_key = _required(values, 'VITE_SUPABASE_PUBLISHABLE_KEY', 'VITE_SUPABASE_ANON_KEY', 'SUPABASE_PUBLISHABLE_KEY')
    email = _required(values, 'SCIENTIST_DEMO_EMAIL')
    password = _required(values, 'SCIENTIST_DEMO_PASSWORD')
    response = requests.post(
        f'{supabase_url}/auth/v1/token',
        params={'grant_type': 'password'},
        headers={'apikey': publishable_key, 'Content-Type': 'application/json'},
        json={'email': email, 'password': password},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f'Scientist sign-in failed: HTTP {response.status_code}')
    payload = response.json()
    user = payload.get('user') or {}
    roles = user.get('app_metadata', {}).get('roles') or []
    if 'scientist' not in roles or 'admin' in roles:
        raise RuntimeError('Signed-in user does not have scientist-only role metadata')
    return {
        'supabase_url': supabase_url,
        'publishable_key': publishable_key,
        'access_token': payload['access_token'],
        'user_id': user.get('id'),
        'email': email,
    }


def _headers(session: dict[str, Any], prefer: str = 'return=representation') -> dict[str, str]:
    return {
        'apikey': session['publishable_key'],
        'Authorization': f"Bearer {session['access_token']}",
        'Content-Type': 'application/json',
        'Prefer': prefer,
    }


def _get_rows(session: dict[str, Any], table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = requests.get(
        f"{session['supabase_url']}/rest/v1/{table}",
        headers=_headers(session),
        params=params,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f'GET {table} failed: HTTP {response.status_code}')
    payload = response.json()
    return payload if isinstance(payload, list) else [payload]


def _post_rows(session: dict[str, Any], table: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    response = requests.post(
        f"{session['supabase_url']}/rest/v1/{table}",
        headers=_headers(session, prefer='resolution=merge-duplicates,return=representation'),
        params={'on_conflict': 'id'},
        json=records,
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f'UPSERT {table} failed: HTTP {response.status_code} {response.text}')
    payload = response.json() if response.text.strip() else []
    return payload if isinstance(payload, list) else [payload]


def _patch_case_in_review(session: dict[str, Any]) -> None:
    response = requests.patch(
        f"{session['supabase_url']}/rest/v1/scientist_validation_cases",
        headers=_headers(session, prefer='return=minimal'),
        params={'id': f'eq.{DEMO_CASE_ID}'},
        json={
            'status': 'in_review',
            'requires_two_reviewers': True,
            'disagreement_count': 0,
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f'PATCH scientist_validation_cases failed: HTTP {response.status_code}')


def run_scientist_demo_workflow(*, output_path: Path) -> dict[str, Any]:
    values = _load_env()
    session = _sign_in(values)
    cases = _get_rows(
        session,
        'scientist_validation_cases',
        {
            'select': '*',
            'id': f'eq.{DEMO_CASE_ID}',
            'region_key': f'eq.{DEMO_REGION_KEY}',
            'limit': '1',
        },
    )
    if not cases:
        raise RuntimeError('Synthetic demo case is missing; run seed_scientist_demo_data.py first')
    case = cases[0]
    if case.get('claim_boundary') != CLAIM_BOUNDARY:
        raise RuntimeError('Synthetic demo case claim boundary is not safe')

    review = {
        'id': DEMO_REVIEW_ID,
        'case_id': DEMO_CASE_ID,
        'reviewer_id': session['user_id'],
        'verdict': 'needs_info',
        'confidence': 0.75,
        'notes': 'Synthetic credentialed smoke review. Requires real field evidence before scientific use.',
        'failure_mode': 'synthetic_demo_no_real_field_evidence',
        'weak_layer_class': None,
        'runout_verdict': None,
        'claim_impact': 'downgrade',
        'official_avalanche_problem': 'persistent_weak_layers',
        'label_quality_verdict': 'location_or_time_uncertain',
        'model_error_verdict': 'model_miscalibrated',
        'terrain_sar_ambiguity': 'terrain_context_required',
        'evidence_needed_next': 'field_observation',
        'confidence_rationale': 'Synthetic demo review proves workflow only; real scientist evidence is still required.',
        'evidence_refs': {
            'attached_publications': [{'id': 'him-strat-2020', 'title': 'HIM-STRAT Himalayan snowpack stability publication'}],
            'claim_boundary': CLAIM_BOUNDARY,
            'synthetic_demo': True,
        },
    }
    _post_rows(session, 'scientist_validation_reviews', [review])
    action = {
        'id': DEMO_ACTION_ID,
        'case_id': DEMO_CASE_ID,
        'review_id': DEMO_REVIEW_ID,
        'action_type': 'evidence_request',
        'status': 'open',
        'priority': 5,
        'summary': 'Collect real field observation before using this demo case as evidence.',
        'owner_role': 'scientist',
        'evidence_refs': {
            'claim_boundary': CLAIM_BOUNDARY,
            'synthetic_demo': True,
            'auto_training_or_promotion': False,
        },
        'created_by': session['user_id'],
    }
    _post_rows(session, 'scientist_validation_actions', [action])
    _patch_case_in_review(session)

    reviews = _get_rows(session, 'scientist_validation_reviews', {'select': '*', 'case_id': f'eq.{DEMO_CASE_ID}'})
    actions = _get_rows(session, 'scientist_validation_actions', {'select': '*', 'case_id': f'eq.{DEMO_CASE_ID}'})
    export = {
        'schema_version': 'scientist-demo-credentialed-workflow/v1',
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'scientist_email': session['email'],
        'case': case,
        'reviews': reviews,
        'actions': actions,
        'reviewer_count': len({row.get('reviewer_id') for row in reviews if row.get('reviewer_id')}),
        'disagreement_count': case.get('disagreement_count') or 0,
        'claim_boundary': CLAIM_BOUNDARY,
        'password_printed': False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(export, indent=2), encoding='utf-8')
    return {
        'workflow_status': 'ok',
        'scientist_email': session['email'],
        'case_id': DEMO_CASE_ID,
        'review_id': DEMO_REVIEW_ID,
        'action_id': DEMO_ACTION_ID,
        'export_path': str(output_path),
        'reviewer_count': export['reviewer_count'],
        'claim_boundary': CLAIM_BOUNDARY,
        'password_printed': False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run credentialed scientist demo review workflow.')
    parser.add_argument('--output', default='/private/tmp/avalanche-insight-hub-scientist-demo-export.json')
    args = parser.parse_args(argv)

    print(json.dumps(run_scientist_demo_workflow(output_path=Path(args.output)), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
