"""Explicit, provenance-preserving adapters for independent open labels.

The lane is inert unless a caller supplies a local snapshot.  Records default
to staging and become training-eligible only when the caller explicitly asks
for ``shadow_training`` and supplies a source-specific license review ID.
Production scoring is never enabled by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.european_shadow_sources import normalize_staged_european_record
from backend.common.label_time_contract import normalise_precision


OPEN_SOURCE_LABEL_MANIFEST_VERSION = 'open_source_label_manifest_v1'
OPEN_SOURCE_LABEL_RECORD_VERSION = 'open_source_training_event_v1'
MINIMUM_REVIEW_SEASONS = 3
REGION_SEASON_START_MONTHS = {
    'himalayas_nepal': 11,
    'pir_panjal_nw_himalaya': 11,
    'shamshabari_nw_himalaya': 11,
    'great_himalaya_nw_himalaya': 11,
    'karakoram_&_ladakh': 10,
}


def _load_snapshot(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValueError(f'open-source label snapshot cannot be read: {path}') from exc
    if not payload.strip():
        raise ValueError('open-source label snapshot is empty')

    records: Any
    if path.suffix.lower() == '.jsonl':
        records = [
            json.loads(line)
            for line in payload.decode('utf-8').splitlines()
            if line.strip()
        ]
    else:
        records = json.loads(payload.decode('utf-8'))
        if isinstance(records, dict):
            records = records.get('records') if isinstance(records.get('records'), list) else [records]
    if not isinstance(records, list) or not records:
        raise ValueError('open-source label snapshot must contain a non-empty record list')
    if not all(isinstance(record, dict) for record in records):
        raise ValueError('every open-source label snapshot record must be an object')
    return records, payload


def _finite_coordinate(raw: Any, field: str, *, lower: float, upper: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'open-source label record requires valid lat/lng ({field})') from exc
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'open-source label record requires valid lat/lng ({field})')
    return value


def _confidence(raw: dict[str, Any]) -> float:
    candidate = raw.get('label_confidence', raw.get('confidence'))
    try:
        value = float(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError('open-source label record requires label_confidence') from exc
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError('open-source label record label_confidence must be between 0 and 1')
    return value


def _parse_event_time(value: Any) -> datetime:
    """Parse an event timestamp before it can enter the label manifest."""
    raw = str(value or '').strip()
    if not raw:
        raise ValueError('open-source label record requires event_time/timestamp')
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('open-source label record event_time must be ISO-8601') from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _snow_season_id(event_time: Any, region_key: str | None = None) -> str:
    """Use the configured regional snow-season start month."""
    parsed = _parse_event_time(event_time)
    start_month = REGION_SEASON_START_MONTHS.get(str(region_key or '').strip(), 7)
    year = parsed.year if parsed.month >= start_month else parsed.year - 1
    return f'{year}-{year + 1}'


def _event_from_staged_record(
    raw: dict[str, Any],
    staged: dict[str, Any],
) -> dict[str, Any]:
    lat = _finite_coordinate(raw.get('lat', raw.get('latitude')), 'lat', lower=-90.0, upper=90.0)
    lng = _finite_coordinate(raw.get('lng', raw.get('longitude')), 'lng', lower=-180.0, upper=180.0)
    event_time = _parse_event_time(staged.get('event_time'))
    label = staged.get('label', 1)
    if label not in (1, True):
        raise ValueError('open-source occurrence label must be positive (label=1)')

    source_key = str(staged['source_key'])
    external_id = str(staged['external_id'])
    training_eligible = bool(staged.get('training_eligible'))
    timestamp_precision = normalise_precision(staged.get('timestamp_precision'))
    if training_eligible and timestamp_precision != 'exact':
        raise ValueError(
            'open-source day/interval labels cannot enter the timestamp-only training lane; '
            'interval-aware training must be implemented before these rows are eligible '
            '(explicit timestamp_precision=exact is required)',
        )
    event_id = f'open:{source_key}:{external_id}'
    metadata = staged.get('metadata') if isinstance(staged.get('metadata'), dict) else {}
    source_provenance = {
        'source_key': source_key,
        'source_label': staged.get('source_label'),
        'data_lane': staged.get('data_lane'),
        'external_id': external_id,
        'source_url': metadata.get('source_url'),
        'citation': staged.get('attribution'),
        'license_review_id': staged.get('license_review_id'),
        'asset_refs': staged.get('asset_refs') or {},
        'event_type': raw.get('event_type'),
        'location_name': raw.get('location_name'),
        'source_reference': raw.get('source_reference') or raw.get('reference'),
        'source_row_sha256': raw.get('source_row_sha256'),
        'location_precision': raw.get('location_precision'),
        'timestamp_precision': raw.get('timestamp_precision'),
    }
    confidence = _confidence(raw)
    return {
        'id': event_id,
        'event_id': event_id,
        'source_event_id': external_id,
        'event_group_id': str(staged.get('event_group_id') or f'{source_key}:{external_id}'),
        'origin_source_family': str(
            staged.get('origin_source_family')
            or metadata.get('origin_source_family')
            or source_key
        ),
        'region_key': str(raw.get('region_key') or ''),
        'location': f'SRID=4326;POINT({lng:.12g} {lat:.12g})',
        'timestamp': event_time.isoformat().replace('+00:00', 'Z'),
        'event_time_start': staged.get('event_time_start') or raw.get('event_time_start'),
        'event_time_end': staged.get('event_time_end') or raw.get('event_time_end'),
        'timestamp_precision': staged.get('timestamp_precision') or raw.get('timestamp_precision'),
        'hazard_type': 'avalanche',
        'severity': raw.get('severity'),
        'source': source_key,
        'fusion_source': source_key,
        'label_source': source_key,
        'source_model': source_key,
        'source_scene_ids': [external_id],
        'training_eligible': training_eligible,
        'training_eligible_reason': 'open_source_shadow' if training_eligible else 'open_source_staging',
        'label_role': 'core' if training_eligible else 'shadow',
        'verification_status': 'unverified',
        'confidence': confidence,
        'label_confidence': confidence,
        'training_weight': staged.get('training_weight'),
        'review_basis': 'open_source_occurrence',
        'geometry_type': 'point',
        'geometry_ref': (staged.get('asset_refs') or {}).get('geometry_ref'),
        'features': {'open_source_provenance': source_provenance},
        'topo_profile': {'metadata': source_provenance},
        'open_source_record_version': OPEN_SOURCE_LABEL_RECORD_VERSION,
    }


def load_open_source_label_events(
    path: str | Path,
    *,
    source_key: str | None = None,
    requested_role: str = 'staging',
    license_review_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load and normalize one explicit open-source snapshot."""
    raw_records, _ = _load_snapshot(Path(path).expanduser())
    events: list[dict[str, Any]] = []
    for raw in raw_records:
        prepared = dict(raw)
        if license_review_id and not prepared.get('license_review_id'):
            prepared['license_review_id'] = license_review_id
        staged = normalize_staged_european_record(
            prepared,
            source_key=source_key,
            requested_role=requested_role,
        )
        events.append(_event_from_staged_record(prepared, staged))
    return events


def build_open_source_label_manifest(
    path: str | Path,
    *,
    source_key: str | None = None,
    requested_role: str = 'staging',
    license_review_id: str | None = None,
) -> dict[str, Any]:
    """Build a hash and usage manifest without activating the data lane."""
    snapshot_path = Path(path).expanduser()
    raw_records, payload = _load_snapshot(snapshot_path)
    events = load_open_source_label_events(
        snapshot_path,
        source_key=source_key,
        requested_role=requested_role,
        license_review_id=license_review_id,
    )
    source_keys = sorted({str(event['label_source']) for event in events})
    season_counts: dict[str, int] = {}
    source_season_counts: dict[str, dict[str, int]] = {}
    invalid_season_count = 0
    for event in events:
        try:
            season_id = _snow_season_id(event.get('timestamp'), event.get('region_key'))
        except ValueError:
            invalid_season_count += 1
            continue
        season_counts[season_id] = season_counts.get(season_id, 0) + 1
        source = str(event.get('label_source') or 'unknown')
        by_source = source_season_counts.setdefault(source, {})
        by_source[season_id] = by_source.get(season_id, 0) + 1
    season_ids = sorted(season_counts)
    return {
        'version': OPEN_SOURCE_LABEL_MANIFEST_VERSION,
        'snapshot_path': str(snapshot_path),
        'snapshot_sha256': hashlib.sha256(payload).hexdigest(),
        'source_key': source_keys[0] if len(source_keys) == 1 else 'mixed',
        'source_keys': source_keys,
        'requested_role': requested_role,
        'license_review_id_present': bool(license_review_id),
        'record_count': len(raw_records),
        'training_eligible_count': sum(1 for event in events if event.get('training_eligible')),
        'production_eligible_count': 0,
        'season_ids': season_ids,
        'season_counts': season_counts,
        'source_season_counts': source_season_counts,
        'season_start_months': dict(REGION_SEASON_START_MONTHS),
        'invalid_season_count': invalid_season_count,
        'coverage_gate': {
            'minimum_review_seasons': MINIMUM_REVIEW_SEASONS,
            'observed_season_count': len(season_ids),
            'passed': len(season_ids) >= MINIMUM_REVIEW_SEASONS,
            'later_season_holdout': season_ids[-1] if season_ids else None,
        },
    }
