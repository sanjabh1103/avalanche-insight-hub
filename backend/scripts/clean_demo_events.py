from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.common.supabase_io import rest_delete, rest_get


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_wrapping_quotes(value)
    return values


def load_env(env_file: Path) -> None:
    raw_values = parse_env_file(env_file.expanduser().resolve())
    supabase_url = raw_values.get('SUPABASE_URL') or raw_values.get('VITE_SUPABASE_URL')
    service_role_key = raw_values.get('SUPABASE_SERVICE_ROLE_KEY')
    if not supabase_url or not service_role_key:
        raise RuntimeError('SUPABASE_URL/VITE_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required')
    os.environ.setdefault('SUPABASE_URL', supabase_url.rstrip('/'))
    os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', service_role_key)


def normalize_signatures(raw: str) -> list[str]:
    return [item.strip().lower() for item in raw.split(',') if item.strip()]


def lower_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.lower()
    return json.dumps(value, sort_keys=True, default=str).lower()


def matched_signatures(value: str, signatures: list[str]) -> list[str]:
    lowered = value.lower()
    return [signature for signature in signatures if signature in lowered]


@dataclass(frozen=True)
class EventCandidate:
    id: str
    description: str
    timestamp: str
    source: str
    location_name: str | None
    field_report_id: str | None
    client_report_id: str | None
    match_reasons: list[str]


@dataclass(frozen=True)
class FieldReportCandidate:
    id: str
    description: str
    timestamp: str
    client_report_id: str | None
    match_reasons: list[str]


def select_event_candidates(
    rows: list[dict[str, Any]],
    *,
    signatures: list[str],
    region_name: str | None,
) -> list[EventCandidate]:
    selected: list[EventCandidate] = []
    normalized_region = region_name.lower() if region_name else None
    for row in rows:
        description = str(row.get('description') or '')
        features = row.get('features') if isinstance(row.get('features'), dict) else {}
        location_name = features.get('location_name') if isinstance(features.get('location_name'), str) else None
        searchable = f'{description}\n{lower_text(features)}'
        matched = matched_signatures(searchable, signatures)
        if not matched:
            continue
        if normalized_region:
            region_haystack = ' '.join(filter(None, [location_name or '', searchable])).lower()
            if normalized_region not in region_haystack:
                continue
        selected.append(
            EventCandidate(
                id=str(row.get('id') or ''),
                description=description,
                timestamp=str(row.get('timestamp') or ''),
                source=str(row.get('source') or ''),
                location_name=location_name,
                field_report_id=str(features.get('field_report_id')) if features.get('field_report_id') else None,
                client_report_id=str(features.get('client_report_id')) if features.get('client_report_id') else None,
                match_reasons=matched,
            ),
        )
    return selected


def select_field_report_candidates(
    rows: list[dict[str, Any]],
    *,
    signatures: list[str],
    linked_field_report_ids: set[str],
    linked_client_report_ids: set[str],
) -> list[FieldReportCandidate]:
    selected: list[FieldReportCandidate] = []
    for row in rows:
        report_id = str(row.get('id') or '')
        client_report_id = str(row.get('client_report_id') or '') or None
        description = str(row.get('description') or '')
        reasons: list[str] = []
        if report_id in linked_field_report_ids:
            reasons.append('linked_avalanche_event')
        if client_report_id and client_report_id in linked_client_report_ids:
            reasons.append('linked_client_report')
        reasons.extend(matched_signatures(description, signatures))
        if not reasons:
            continue
        selected.append(
            FieldReportCandidate(
                id=report_id,
                description=description,
                timestamp=str(row.get('timestamp') or ''),
                client_report_id=client_report_id,
                match_reasons=sorted(set(reasons)),
            ),
        )
    return selected


def delete_by_ids(table: str, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    id_filter = ','.join(ids)
    return rest_delete(table, filters={'id': f'in.({id_filter})'})


def clean_demo_events(
    *,
    env_file: Path,
    signatures: list[str],
    created_after: str | None,
    region_name: str | None,
    limit: int,
    apply: bool,
) -> dict[str, Any]:
    load_env(env_file)

    event_params = {
        'select': 'id,description,timestamp,source,features,label_confidence,training_weight',
        'order': 'timestamp.desc',
        'limit': str(limit),
    }
    report_params = {
        'select': 'id,description,timestamp,client_report_id,review_status,sync_status',
        'order': 'timestamp.desc',
        'limit': str(limit),
    }
    if created_after:
        event_params['timestamp'] = f'gte.{created_after}'
        report_params['timestamp'] = f'gte.{created_after}'

    event_rows = rest_get('avalanche_events', params=event_params)
    event_candidates = select_event_candidates(
        event_rows,
        signatures=signatures,
        region_name=region_name,
    )

    linked_field_report_ids = {candidate.field_report_id for candidate in event_candidates if candidate.field_report_id}
    linked_client_report_ids = {candidate.client_report_id for candidate in event_candidates if candidate.client_report_id}

    field_report_rows = rest_get('field_reports', params=report_params)
    field_report_candidates = select_field_report_candidates(
        field_report_rows,
        signatures=signatures,
        linked_field_report_ids=linked_field_report_ids,
        linked_client_report_ids=linked_client_report_ids,
    )

    event_ids = sorted({candidate.id for candidate in event_candidates if candidate.id})
    field_report_ids = sorted({candidate.id for candidate in field_report_candidates if candidate.id})

    summary: dict[str, Any] = {
        'apply': apply,
        'region_name': region_name,
        'created_after': created_after,
        'signatures': signatures,
        'candidate_counts': {
            'avalanche_events': len(event_ids),
            'field_reports': len(field_report_ids),
        },
        'avalanche_events': [
            {
                'id': candidate.id,
                'timestamp': candidate.timestamp,
                'source': candidate.source,
                'location_name': candidate.location_name,
                'description': candidate.description,
                'field_report_id': candidate.field_report_id,
                'client_report_id': candidate.client_report_id,
                'match_reasons': candidate.match_reasons,
            }
            for candidate in event_candidates
        ],
        'field_reports': [
            {
                'id': candidate.id,
                'timestamp': candidate.timestamp,
                'client_report_id': candidate.client_report_id,
                'description': candidate.description,
                'match_reasons': candidate.match_reasons,
            }
            for candidate in field_report_candidates
        ],
    }

    if not apply:
        return summary

    deleted_events = delete_by_ids('avalanche_events', event_ids)
    deleted_field_reports = delete_by_ids('field_reports', field_report_ids)
    summary['deleted_counts'] = {
        'avalanche_events': len(deleted_events),
        'field_reports': len(deleted_field_reports),
    }
    summary['deleted_event_ids'] = [row.get('id') for row in deleted_events]
    summary['deleted_field_report_ids'] = [row.get('id') for row in deleted_field_reports]
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Safely remove demo/smoke field reports and avalanche events.')
    parser.add_argument('--env-file', type=Path, required=True, help='Path to the environment file with Supabase credentials.')
    parser.add_argument('--signatures', default='smoke,test,codex,cli', help='Comma-separated case-insensitive text signatures to match.')
    parser.add_argument('--created-after', default=None, help='Only inspect rows created at or after this ISO timestamp.')
    parser.add_argument('--region-name', default=None, help='Optional region name filter applied to avalanche_events.features.location_name.')
    parser.add_argument('--limit', type=int, default=500, help='Maximum recent rows to inspect per table.')
    parser.add_argument('--apply', action='store_true', help='Actually delete the matched rows. Default is dry-run.')
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = clean_demo_events(
        env_file=args.env_file,
        signatures=normalize_signatures(args.signatures),
        created_after=args.created_after,
        region_name=args.region_name,
        limit=args.limit,
        apply=args.apply,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
