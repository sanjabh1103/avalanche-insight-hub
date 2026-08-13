"""Shared release-bound initial-state and forecast-semantics contracts.

This module is deliberately small and independent of the native SNOWPACK
runtime.  It defines the byte-addressed JSON envelopes copied into a release
bundle and is used by both the producer and the downloaded-bundle gate.

The contracts prove that a bundle carried explicit state/forecast context;
they do not prove that the supplied state is scientifically appropriate or
that the forcing has been calibrated for the Himalaya.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.snowpack_contracts import (
    ContractValidationError,
    ForecastSemanticsContract,
    InitialSnowStateContract,
    ProvenanceMetadata,
)
from backend.common.snowpack_paths import UnsafePathError, ensure_safe_file


INITIAL_STATE_SCHEMA = 'snowpack_initial_state_v1'
FORECAST_SEMANTICS_SCHEMA = 'snowpack_forecast_semantics_v1'
RUN_ID_PLACEHOLDER = '__RUN_ID__'


class ReleaseSemanticsError(ValueError):
    """Raised when a release semantics manifest is malformed or unbound."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hash binding."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    """Read one regular UTF-8 JSON object and fail closed on every boundary."""
    try:
        with path.open('r', encoding='utf-8') as handle:
            value = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ReleaseSemanticsError(f'{path} is not valid UTF-8 JSON: {exc}') from exc
    if not isinstance(value, dict):
        raise ReleaseSemanticsError(
            f'{path} JSON root must be an object, got {type(value).__name__}'
        )
    return value


def _provenance_from_dict(value: Any) -> ProvenanceMetadata:
    if not isinstance(value, dict):
        raise ReleaseSemanticsError('provenance must be a JSON object')
    try:
        chain = value.get('provenance_chain', ())
        if not isinstance(chain, (list, tuple)) or not all(isinstance(item, str) for item in chain):
            raise ReleaseSemanticsError('provenance_chain must be a list of strings')
        provenance = ProvenanceMetadata(
            source=value.get('source', ''),
            source_class=value.get('source_class', ''),
            licence=value.get('licence', ''),
            timestamp=value.get('timestamp', ''),
            latitude=value.get('latitude'),
            longitude=value.get('longitude'),
            elevation_m=value.get('elevation_m'),
            units=value.get('units', {}),
            hash=value.get('hash', ''),
            run_id=value.get('run_id', ''),
            provenance_chain=tuple(chain),
        )
        provenance.validate()
        try:
            parsed_timestamp = datetime.fromisoformat(
                provenance.timestamp.replace('Z', '+00:00')
            )
        except ValueError as exc:
            raise ReleaseSemanticsError(
                f'provenance.timestamp is not valid ISO-8601: {provenance.timestamp!r}'
            ) from exc
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
            raise ReleaseSemanticsError('provenance.timestamp must be timezone-aware UTC')
        if parsed_timestamp.utcoffset() != timezone.utc.utcoffset(parsed_timestamp):
            raise ReleaseSemanticsError('provenance.timestamp must use UTC offset +00:00')
        return provenance
    except (ContractValidationError, TypeError, ValueError) as exc:
        raise ReleaseSemanticsError(f'invalid provenance: {exc}') from exc


def _state_from_contract(value: Any) -> InitialSnowStateContract:
    if not isinstance(value, dict):
        raise ReleaseSemanticsError('initial-state contract must be a JSON object')
    try:
        state = InitialSnowStateContract(
            state_id=value.get('state_id', ''),
            state_type=value.get('state_type', ''),
            start_time=value.get('start_time', ''),
            source=value.get('source', ''),
            state_sha256=value.get('state_sha256', ''),
            provenance=_provenance_from_dict(value.get('provenance')),
            state_file_path=value.get('state_file_path', ''),
        )
        state.validate()
        return state
    except (ContractValidationError, TypeError, ValueError) as exc:
        raise ReleaseSemanticsError(f'invalid initial-state contract: {exc}') from exc


def _forecast_from_contract(value: Any) -> ForecastSemanticsContract:
    if not isinstance(value, dict):
        raise ReleaseSemanticsError('forecast-semantics contract must be a JSON object')
    # P0-4: Do not default ensemble_members to 1. Require it explicitly
    # for release-bound forecast manifests. Missing field → error.
    # P1/G1: Strict type check — int() silently converts floats (1.5→1),
    # strings ("1"→1), and bools (True→1). Require exact int.
    if 'ensemble_members' not in value:
        raise ReleaseSemanticsError(
            'forecast-semantics ensemble_members is required for release-bound manifests'
        )
    raw_ensemble = value['ensemble_members']
    if type(raw_ensemble) is not int:
        raise ReleaseSemanticsError(
            f'forecast-semantics ensemble_members must be an exact integer, '
            f'got {type(raw_ensemble).__name__}: {raw_ensemble!r}'
        )
    # P1/G1: Strict type check for lead_time_h — must be int or float, not
    # string or bool. bool is a subclass of int in Python, so reject it
    # explicitly.
    raw_lead_time = value.get('lead_time_h', -1)
    if isinstance(raw_lead_time, bool) or not isinstance(raw_lead_time, (int, float)):
        raise ReleaseSemanticsError(
            f'forecast-semantics lead_time_h must be a number (int or float), '
            f'got {type(raw_lead_time).__name__}: {raw_lead_time!r}'
        )
    try:
        forecast = ForecastSemanticsContract(
            mode=value.get('mode', ''),
            source=value.get('source', ''),
            forecast_cycle=value.get('forecast_cycle', ''),
            valid_from=value.get('valid_from', ''),
            valid_to=value.get('valid_to', ''),
            as_of=value.get('as_of', ''),
            lead_time_h=raw_lead_time,
            region_key=value.get('region_key', ''),
            elevation_band=value.get('elevation_band', ''),
            forcing_manifest_id=value.get('forcing_manifest_id', ''),
            member_id=value.get('member_id', ''),
            ensemble_members=raw_ensemble,
        )
        forecast.validate()
        return forecast
    except (ContractValidationError, TypeError, ValueError) as exc:
        raise ReleaseSemanticsError(f'invalid forecast-semantics contract: {exc}') from exc


def initial_state_to_dict(state: InitialSnowStateContract) -> dict[str, Any]:
    return {
        'state_id': state.state_id,
        'state_type': state.state_type,
        'start_time': state.start_time,
        'source': state.source,
        'state_sha256': state.state_sha256,
        'state_file_path': state.state_file_path,
        'provenance': state.provenance.to_dict(),
    }


def forecast_semantics_to_dict(forecast: ForecastSemanticsContract) -> dict[str, Any]:
    return {
        'mode': forecast.mode,
        'source': forecast.source,
        'forecast_cycle': forecast.forecast_cycle,
        'valid_from': forecast.valid_from,
        'valid_to': forecast.valid_to,
        'as_of': forecast.as_of,
        'lead_time_h': forecast.lead_time_h,
        'region_key': forecast.region_key,
        'elevation_band': forecast.elevation_band,
        'forcing_manifest_id': forecast.forcing_manifest_id,
        'member_id': forecast.member_id,
        'ensemble_members': forecast.ensemble_members,
    }


def initial_state_envelope(state: InitialSnowStateContract) -> dict[str, Any]:
    state.validate()
    return {
        'schema_version': INITIAL_STATE_SCHEMA,
        'contract': initial_state_to_dict(state),
    }


def forecast_semantics_envelope(forecast: ForecastSemanticsContract) -> dict[str, Any]:
    forecast.validate()
    return {
        'schema_version': FORECAST_SEMANTICS_SCHEMA,
        'contract': forecast_semantics_to_dict(forecast),
    }


def load_initial_state_manifest(path: Path) -> tuple[InitialSnowStateContract, dict[str, Any]]:
    data = read_json_object(path)
    if data.get('schema_version') != INITIAL_STATE_SCHEMA:
        raise ReleaseSemanticsError(
            f'initial-state schema_version must be {INITIAL_STATE_SCHEMA}'
        )
    state = _state_from_contract(data.get('contract'))
    return state, data


def load_forecast_semantics_manifest(path: Path) -> tuple[ForecastSemanticsContract, dict[str, Any]]:
    data = read_json_object(path)
    if data.get('schema_version') != FORECAST_SEMANTICS_SCHEMA:
        raise ReleaseSemanticsError(
            f'forecast-semantics schema_version must be {FORECAST_SEMANTICS_SCHEMA}'
        )
    forecast = _forecast_from_contract(data.get('contract'))
    return forecast, data


def snow_free_state_hash(state: InitialSnowStateContract) -> str:
    """Hash a snow-free declaration without a self-referential hash field."""
    declaration = initial_state_to_dict(state)
    declaration['state_sha256'] = ''
    return sha256_bytes(canonical_json_bytes({
        'schema_version': INITIAL_STATE_SCHEMA,
        'contract': declaration,
    }))


def bind_initial_state_to_run_id(
    state: InitialSnowStateContract,
    run_id: str,
) -> InitialSnowStateContract:
    """Bind an approved run-bound state template to one release identity.

    A checked-in state manifest cannot know the random GitHub dispatch run ID.
    The only accepted template value is the explicit ``__RUN_ID__`` marker;
    arbitrary mismatches still fail closed.  The snow-free declaration hash is
    recomputed after binding, so the bundle carries a hash of the actual run
    identity rather than a reusable placeholder hash.
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise ReleaseSemanticsError('run_id is required to bind initial state')
    state.validate()
    current_run_id = state.provenance.run_id
    if current_run_id == run_id:
        return state
    if current_run_id != RUN_ID_PLACEHOLDER:
        raise ReleaseSemanticsError(
            'initial-state provenance run_id does not match release run_id'
        )
    bound_provenance = replace(state.provenance, run_id=run_id)
    bound_state = replace(state, provenance=bound_provenance)
    if bound_state.state_type == 'snow_free':
        bound_state = replace(
            bound_state,
            state_sha256=snow_free_state_hash(bound_state),
        )
    bound_state.validate()
    return bound_state


def validate_initial_state_binding(
    state: InitialSnowStateContract,
    *,
    bundle_root: Path | None = None,
    payload_path: Path | None = None,
) -> None:
    """Validate a state hash against a profile payload or snow-free declaration."""
    state.validate()
    if state.state_type == 'snow_free':
        if state.state_sha256 != snow_free_state_hash(state):
            raise ReleaseSemanticsError(
                'snow_free state_sha256 does not match its canonical declaration'
            )
        return
    if not state.state_file_path:
        raise ReleaseSemanticsError('profile state_file_path is required')
    if _unsafe_relative_path(state.state_file_path):
        raise ReleaseSemanticsError('profile state_file_path must be a safe relative path')
    if bundle_root is not None:
        if payload_path is None:
            raise ReleaseSemanticsError('profile state payload is missing')
        try:
            payload = ensure_safe_file(payload_path, root=bundle_root)
        except (OSError, RuntimeError, UnsafePathError) as exc:
            raise ReleaseSemanticsError(f'profile state payload is unsafe: {exc}') from exc
        if sha256_bytes(payload.read_bytes()) != state.state_sha256:
            raise ReleaseSemanticsError('profile state payload hash does not match state_sha256')


def validate_release_semantics_context(
    *,
    state: InitialSnowStateContract,
    forecast: ForecastSemanticsContract,
    run_id: str,
    region_key: str,
    elevation_band: str,
    forcing_manifest_id: str,
) -> None:
    """Bind both contracts to the release identity and forecast context."""
    state.validate()
    forecast.validate()
    if state.provenance.run_id != run_id:
        raise ReleaseSemanticsError('initial-state provenance run_id does not match release run_id')
    if forecast.region_key != region_key:
        raise ReleaseSemanticsError('forecast semantics region does not match release region')
    if forecast.elevation_band != elevation_band:
        raise ReleaseSemanticsError('forecast semantics elevation band does not match release band')
    if forecast.forcing_manifest_id != forcing_manifest_id:
        raise ReleaseSemanticsError('forecast semantics forcing ID does not match release forcing ID')


def validate_forcing_samples_against_forecast(
    samples: list[dict[str, Any]],
    forecast: ForecastSemanticsContract,
) -> dict[str, Any]:
    """Bind forcing sample chronology to a forecast contract.

    Source adapters may provide naive timestamps (Open-Meteo commonly returns
    local-looking UTC strings), so this boundary explicitly interprets a
    naive sample as UTC and reports that the normalization occurred through
    the downstream SMET provenance. Contract timestamps themselves remain
    strictly timezone-aware UTC.

    Historical spin-up samples before ``valid_from`` are allowed, but a
    forecast/ensemble forcing package must contain at least one sample in its
    declared forecast window and must not extend beyond ``valid_to``.
    """
    forecast.validate()
    if not isinstance(samples, list) or not samples:
        raise ReleaseSemanticsError('forcing samples must be a non-empty list')

    def parse_sample(value: Any, index: int) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ReleaseSemanticsError(f'forcing sample {index} has no timestamp')
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError as exc:
            raise ReleaseSemanticsError(
                f'forcing sample {index} timestamp is invalid: {value!r}'
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    valid_from = datetime.fromisoformat(forecast.valid_from.replace('Z', '+00:00')).astimezone(timezone.utc)
    valid_to = datetime.fromisoformat(forecast.valid_to.replace('Z', '+00:00')).astimezone(timezone.utc)
    expected_cycle = datetime.fromisoformat(forecast.forecast_cycle.replace('Z', '+00:00')).astimezone(timezone.utc)
    timestamps: list[datetime] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ReleaseSemanticsError(f'forcing sample {index} must be an object')
        current = parse_sample(sample.get('time', sample.get('timestamp')), index)
        if timestamps and current <= timestamps[-1]:
            raise ReleaseSemanticsError(
                f'forcing sample timestamps must be strictly increasing at index {index}'
            )
        explicit_cycle = sample.get('forecast_cycle')
        if explicit_cycle is not None:
            if parse_sample(explicit_cycle, index) != expected_cycle:
                raise ReleaseSemanticsError(
                    f'forcing sample {index} forecast_cycle does not match contract'
                )
        explicit_member = sample.get('member_id')
        if explicit_member is not None and explicit_member != forecast.member_id:
            raise ReleaseSemanticsError(
                f'forcing sample {index} member_id does not match contract'
            )
        timestamps.append(current)

    if timestamps[-1] > valid_to:
        raise ReleaseSemanticsError(
            f'forcing ends at {timestamps[-1].isoformat()}, after forecast valid_to '
            f'{valid_to.isoformat()}'
        )
    in_window = [timestamp for timestamp in timestamps if valid_from <= timestamp <= valid_to]
    if forecast.mode in {'forecast', 'ensemble', 'historical_forecast_replay'} and not in_window:
        raise ReleaseSemanticsError(
            'forecast/ensemble forcing contains no sample in the declared valid window'
        )
    return {
        'sample_count': len(timestamps),
        'forcing_start': timestamps[0].isoformat(),
        'forcing_end': timestamps[-1].isoformat(),
        'forecast_cycle': expected_cycle.isoformat(),
        'valid_from': valid_from.isoformat(),
        'valid_to': valid_to.isoformat(),
        'member_id': forecast.member_id,
        'naive_sample_timestamps_interpreted_as_utc': any(
            isinstance(sample.get('time', sample.get('timestamp')), str)
            and 'T' in sample.get('time', sample.get('timestamp'))
            and '+' not in sample.get('time', sample.get('timestamp'))
            and not sample.get('time', sample.get('timestamp')).endswith('Z')
            for sample in samples
            if isinstance(sample, dict)
        ),
    }


def _unsafe_relative_path(value: str) -> bool:
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        return True
    path = Path(value)
    return path.is_absolute() or '..' in path.parts


__all__ = [
    'FORECAST_SEMANTICS_SCHEMA',
    'INITIAL_STATE_SCHEMA',
    'RUN_ID_PLACEHOLDER',
    'bind_initial_state_to_run_id',
    'ReleaseSemanticsError',
    'canonical_json_bytes',
    'forecast_semantics_envelope',
    'initial_state_envelope',
    'load_forecast_semantics_manifest',
    'load_initial_state_manifest',
    'sha256_bytes',
    'snow_free_state_hash',
    'validate_forcing_samples_against_forecast',
    'validate_initial_state_binding',
    'validate_release_semantics_context',
]
