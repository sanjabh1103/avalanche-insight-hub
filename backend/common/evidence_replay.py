"""Immutable, scientist-only evidence replay frames.

The replay frame deliberately separates raw numerical model/evidence layers from
display metadata.  It is review evidence, not satellite imagery, a forecast,
or a public-risk input.  Frames are deterministic so the stored feature and
replay fingerprints can be checked before a reviewed case enters the
shadow-training candidate lane.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any


EVIDENCE_REPLAY_SCHEMA_VERSION = 'evidence-replay-frame/v1'
SCIENTIST_ONLY_CLAIM_BOUNDARY = (
    'scientist_only_model_rendered_replay_not_satellite_imagery_not_public_risk'
)
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
UTC_TIMESTAMP_RE = re.compile(
    r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?Z$'
)


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _json_safe(value: Any) -> Any:
    """Return a deterministic JSON-safe value without inventing data."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def stable_sha256(value: Any) -> str:
    """Hash canonical JSON for immutable evidence references."""
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _source_hashes(model_metadata: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        'config_hash',
        'feature_schema_hash',
        'manifest_sha256',
        'artifact_sha256',
        'model_sha256',
        'calibration_hash',
    )
    hashes: dict[str, str] = {}
    for key in keys:
        value = model_metadata.get(key)
        if isinstance(value, str) and value.strip():
            hashes[key] = value.strip()
    feature_schema = {
        key: model_metadata.get(key)
        for key in ('selected_features', 'feature_columns')
        if model_metadata.get(key)
    }
    if feature_schema:
        hashes.setdefault('feature_schema_sha256', stable_sha256(feature_schema))
    model_config = {
        key: model_metadata.get(key)
        for key in (
            'model_version',
            'dynamic_model_version',
            'surrogate_model_version',
            'calibration_profile',
            'calibration_profile_version',
            'threshold_profile',
            'fusion_method',
            'dataset_snapshot_id',
            'label_snapshot_id',
        )
        if model_metadata.get(key) is not None
    }
    if model_config:
        hashes.setdefault('model_config_sha256', stable_sha256(model_config))
    return hashes


def _source_identifiers(model_metadata: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        'model_version',
        'dynamic_model_version',
        'surrogate_model_version',
        'dataset_snapshot_id',
        'label_snapshot_id',
        'calibration_profile_version',
        'manifest_storage_ref',
    )
    identifiers: dict[str, str] = {}
    for key in keys:
        value = model_metadata.get(key)
        if value is not None and str(value).strip():
            identifiers[key] = str(value)
    return identifiers


def _forecast_valid_time(forecast_date: str | None, forecast_hour: int | None) -> str | None:
    """Return a UTC-valid time only when the persisted date/hour are usable."""
    if not forecast_date or forecast_hour is None or not 0 <= forecast_hour <= 240:
        return None
    try:
        parsed = datetime.fromisoformat(str(forecast_date).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        base = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
        return (base + timedelta(hours=forecast_hour)).isoformat().replace('+00:00', 'Z')
    except (TypeError, ValueError):
        return None


def _verified_lineage(lineage: Mapping[str, Any]) -> bool:
    if lineage.get('verified') is True:
        return True
    sources = _record(lineage.get('source_lineage'))
    return bool(sources) and all(
        _record(source).get('verified') is True
        for source in sources.values()
    )


def _observation_times(lineage: Mapping[str, Any]) -> list[str]:
    times: set[str] = set()
    for observation in lineage.get('source_observations') or []:
        timestamp = _record(observation).get('acquisition_time')
        if isinstance(timestamp, str) and timestamp.strip():
            times.add(timestamp.strip())
    for source in _record(lineage.get('source_lineage')).values():
        timestamp = _record(source).get('acquisition_time')
        if isinstance(timestamp, str) and timestamp.strip():
            times.add(timestamp.strip())
    return sorted(times)


def _valid_timestamp(value: Any) -> bool:
    """Return true only for a canonical, UTC ISO timestamp.

    The SQL trigger uses the same wire format so local export preflight and
    database materialisation do not disagree on timezone offsets.
    """
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value.strip()):
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None


def _finite_json_values(value: Any) -> bool:
    """Reject NaN/Infinity anywhere in a replay feature payload."""
    if isinstance(value, Mapping):
        return all(_finite_json_values(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_json_values(item) for item in value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def _valid_source_freshness(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    for source, freshness in value.items():
        if not str(source).strip():
            return False
        numeric = _finite_number(freshness)
        if numeric is None or numeric < 0:
            return False
    return True


def _valid_source_hashes(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    return all(
        isinstance(key, str)
        and key.strip()
        and isinstance(raw_hash, str)
        and SHA256_RE.fullmatch(raw_hash.strip())
        for key, raw_hash in value.items()
    )


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def build_evidence_replay_frame(
    *,
    forecast_run_id: str | None,
    region_key: str | None,
    forecast_date: str | None,
    forecast_hour: int | None,
    forecast_grid_id: str | None = None,
    cell: Mapping[str, Any],
    model_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic frame from persisted forecast-cell evidence.

    The function never fills unavailable observations with simulated values.
    A shadow-training lane may use the frame only when it contains a verified,
    non-synthetic observed value and both SHA-256 fingerprints.
    """
    metadata = _record(model_metadata)
    cell_record = _record(cell)
    packet = _record(cell_record.get('verification_packet'))
    fusion = _record(cell_record.get('fusion_evidence'))
    feature_values = _record(cell_record.get('feature_values'))
    weather_inputs = _record(cell_record.get('weather_inputs'))
    terrain_inputs = _record(cell_record.get('terrain_inputs'))
    data_quality = _record(packet.get('data_quality'))
    lineage = _record(packet.get('lineage'))
    evidence_refs = [str(value) for value in packet.get('evidence_refs') or [] if str(value).strip()]
    baseline_ids = [str(value) for value in packet.get('baseline_ids') or [] if str(value).strip()]
    source_hashes = _source_hashes(metadata)
    lineage_verified = _verified_lineage(lineage)
    provenance_complete = bool(
        evidence_refs
        and baseline_ids
        and lineage_verified
        and source_hashes
        and data_quality.get('lineage_verified') is True
        and data_quality.get('freshness_complete') is True
    )

    synthetic_status = (
        'true'
        if packet.get('has_synthetic_evidence') is True or metadata.get('synthetic_inputs_present') is True
        else 'false'
        if packet.get('has_synthetic_evidence') is False and metadata.get('synthetic_inputs_present') is False
        else 'unknown'
    )
    observed_value = _finite_number(packet.get('observed'))
    minimum_sources_satisfied = data_quality.get('minimum_sources_satisfied')
    if observed_value is None:
        observed_status = 'unavailable'
        observed_reason = 'no_independent_observation'
    elif synthetic_status != 'false':
        observed_status = 'unavailable'
        observed_reason = 'synthetic_evidence_status_not_verified_false'
    elif minimum_sources_satisfied is not True:
        observed_status = 'unavailable'
        observed_reason = 'minimum_independent_sources_not_satisfied'
    elif packet.get('anomaly_state') == 'unverified':
        observed_status = 'unavailable'
        observed_reason = 'verification_packet_unverified'
    else:
        observed_status = 'available'
        observed_reason = None

    raw_layers = {
        'feature_values': feature_values,
        'weather_inputs': weather_inputs,
        'terrain_inputs': terrain_inputs,
        'verification_packet': packet,
        'fusion_evidence': fusion,
    }
    modelled = {
        'risk_score': cell_record.get('risk_score'),
        'probability': cell_record.get('probability'),
        'uncertainty_class': cell_record.get('uncertainty_class'),
        'uncertainty_span': cell_record.get('uncertainty_span'),
        'snowpack_proxy': cell_record.get('snowpack_proxy'),
        'physics_narrative': cell_record.get('physics_narrative'),
    }
    observed = {
        'status': observed_status,
        'value': observed_value,
        'unavailable_reason': observed_reason,
        'contributing_sensors': packet.get('contributing_sensors') or [],
        'synthetic_evidence_status': synthetic_status,
        'data_quality': data_quality,
    }
    residual = {
        'baseline_p25': packet.get('baseline_p25'),
        'baseline_p50': packet.get('baseline_p50'),
        'baseline_p75': packet.get('baseline_p75'),
        'residual_zscore': packet.get('residual_zscore'),
        'anomaly_state': packet.get('anomaly_state') or 'unverified',
        'attribution_bucket': packet.get('attribution_bucket') or 'unattributed',
        'disagreement_reasons': packet.get('disagreement_reasons') or [],
    }
    frame_without_hashes = {
        'schema_version': EVIDENCE_REPLAY_SCHEMA_VERSION,
        'claim_boundary': SCIENTIST_ONLY_CLAIM_BOUNDARY,
        'forecast': {
            'forecast_run_id': forecast_run_id,
            'forecast_grid_id': forecast_grid_id,
            'region_key': region_key,
            'forecast_date': forecast_date,
            'forecast_hour': forecast_hour,
            'valid_time_utc': _forecast_valid_time(forecast_date, forecast_hour),
            'cell_row': cell_record.get('row'),
            'cell_col': cell_record.get('col'),
            'coordinates': {
                'lat': cell_record.get('lat'),
                'lng': cell_record.get('lng'),
                'lat_end': cell_record.get('lat_end'),
                'lng_end': cell_record.get('lng_end'),
            },
        },
        'modelled': modelled,
        'observed': observed,
        'residual': residual,
        'raw_layers': raw_layers,
        'lineage': {
            'source_hashes': source_hashes,
            'source_identifiers': _source_identifiers(metadata),
            'evidence_refs': evidence_refs,
            'baseline_ids': baseline_ids,
            'verification_lineage': lineage,
        },
        'alignment': {
            'grid': {
                'forecast_grid_id': forecast_grid_id,
                'cell_row': cell_record.get('row'),
                'cell_col': cell_record.get('col'),
                'bounds': {
                    'lat': cell_record.get('lat'),
                    'lng': cell_record.get('lng'),
                    'lat_end': cell_record.get('lat_end'),
                    'lng_end': cell_record.get('lng_end'),
                },
            },
            'time': {
                'forecast_valid_time_utc': _forecast_valid_time(forecast_date, forecast_hour),
                'observation_times_utc': _observation_times(lineage),
                'source_freshness_hours': packet.get('source_freshness_hours') or {},
            },
        },
        'provenance': {
            'lineage_verified': lineage_verified,
            'source_hashes_present': bool(source_hashes),
            'evidence_refs_present': bool(evidence_refs),
            'baseline_ids_present': bool(baseline_ids),
            'provenance_complete': provenance_complete,
        },
        'display': {
            'label': 'MODEL-RENDERED SCIENTIST REPLAY',
            'render_kind': 'numeric_model_replay',
            'satellite_imagery': False,
            'may_change_public_risk': False,
        },
    }
    feature_snapshot_sha256 = stable_sha256(feature_values) if feature_values else None
    return {
        **frame_without_hashes,
        'feature_snapshot_sha256': feature_snapshot_sha256,
        'replay_snapshot_sha256': stable_sha256(frame_without_hashes),
    }


def replay_is_grounded_for_shadow_training(
    frame: Mapping[str, Any],
    *,
    case: Mapping[str, Any] | None = None,
) -> bool:
    """Return true only for a fully fingerprinted, non-synthetic observation.

    When *case* is provided the replay frame's forecast fields must match the
    case's ``forecast_run_id``, ``region_key``, ``cell_row`` and ``cell_col``
    exactly — mirroring the SQL materialisation trigger.
    """
    record = _record(frame)
    observed = _record(record.get('observed'))
    raw_layers = _record(record.get('raw_layers'))
    feature_values = _record(raw_layers.get('feature_values'))
    feature_hash = record.get('feature_snapshot_sha256')
    replay_hash = record.get('replay_snapshot_sha256')
    forecast = _record(record.get('forecast'))
    alignment = _record(record.get('alignment'))
    alignment_time = _record(alignment.get('time'))
    lineage = _record(record.get('lineage'))
    source_hashes = _record(lineage.get('source_hashes'))

    forecast_run_id = forecast.get('forecast_run_id')
    region_key = forecast.get('region_key')
    forecast_grid_id = forecast.get('forecast_grid_id')
    cell_row = forecast.get('cell_row')
    cell_col = forecast.get('cell_col')
    valid_time = forecast.get('valid_time_utc')
    alignment_grid = _record(alignment.get('grid'))
    alignment_forecast_time = alignment_time.get('forecast_valid_time_utc')
    observation_times = alignment_time.get('observation_times_utc')

    case_aligned = True
    if case is not None:
        case_record = _record(case)
        case_aligned = (
            str(forecast_run_id or '') == str(case_record.get('forecast_run_id') or '')
            and str(region_key or '') == str(case_record.get('region_key') or '')
            and str(cell_row if cell_row is not None else '') == str(case_record.get('cell_row') or '')
            and str(cell_col if cell_col is not None else '') == str(case_record.get('cell_col') or '')
            and (
                case_record.get('forecast_grid_id') is None
                or str(forecast_grid_id or '') == str(case_record.get('forecast_grid_id') or '')
            )
        )

    return bool(
        case_aligned
        and isinstance(forecast_run_id, str)
        and bool(forecast_run_id.strip())
        and isinstance(region_key, str)
        and bool(region_key.strip())
        and isinstance(cell_row, int)
        and not isinstance(cell_row, bool)
        and isinstance(cell_col, int)
        and not isinstance(cell_col, bool)
        and _valid_timestamp(valid_time)
        and 'forecast_grid_id' in forecast
        and (
            forecast_grid_id is None
            or (isinstance(forecast_grid_id, str) and bool(forecast_grid_id.strip()))
        )
        and alignment_grid
        and 'forecast_grid_id' in alignment_grid
        and (
            alignment_grid.get('forecast_grid_id') is None
            or (
                isinstance(alignment_grid.get('forecast_grid_id'), str)
                and bool(alignment_grid.get('forecast_grid_id').strip())
            )
        )
        and alignment_grid.get('forecast_grid_id') == forecast_grid_id
        and alignment_grid.get('cell_row') == cell_row
        and alignment_grid.get('cell_col') == cell_col
        and _valid_timestamp(alignment_forecast_time)
        and alignment_forecast_time == valid_time
        and isinstance(observation_times, (list, tuple))
        and bool(observation_times)
        and all(_valid_timestamp(value) for value in observation_times)
        and observed.get('status') == 'available'
        and observed.get('synthetic_evidence_status') == 'false'
        and feature_values
        and _finite_json_values(feature_values)
        and isinstance(feature_hash, str)
        and SHA256_RE.fullmatch(feature_hash.strip())
        and isinstance(replay_hash, str)
        and SHA256_RE.fullmatch(replay_hash.strip())
        and _record(record.get('provenance')).get('provenance_complete') is True
        and _record(record.get('provenance')).get('lineage_verified') is True
        and _record(record.get('provenance')).get('source_hashes_present') is True
        and _record(record.get('provenance')).get('evidence_refs_present') is True
        and _record(record.get('provenance')).get('baseline_ids_present') is True
        and _valid_source_hashes(source_hashes)
        and _nonempty_strings(_record(lineage).get('evidence_refs'))
        and _nonempty_strings(_record(lineage).get('baseline_ids'))
        and _valid_source_freshness(alignment_time.get('source_freshness_hours'))
    )
