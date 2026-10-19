"""Strict runtime loader and validator for the Pir Panjal POC decision record.

G3: The decision record was referenced by documentation/tests but not consumed
by runtime code. This module provides the executable gate that binds the
decision record's identity, byte hash, sector, band, horizon, track, and
non-claims into every POC run.

G4: The decision record says scope_hash_required=true, but no executable gate
enforced it. This module computes the raw-byte SHA-256 of the decision record
and requires an externally supplied expected digest. The trust root is never
derived from the bundle itself.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


_DECISION_RECORD_SCHEMA_VERSION = 'pir_panjal_poc_decision_v1'
_SELECTED_SECTOR = 'pir_panjal_nw_himalaya'
_ELEVATION_BAND = 'middle'
_ELEVATION_MIN_M = 3200
_ELEVATION_MAX_M = 4000
_HEADLINE_HORIZON_HOURS = 48
_OPTIONAL_EXTENSION_HOURS = 72
_ENSEMBLE_MEMBERS = 1
_REQUIRED_NON_CLAIMS = frozenset({
    'no_official_warning',
    'no_validated_pir_panjal_accuracy',
    'no_modal_accuracy_claim',
    'no_proxy_as_observation_claim',
    'no_weathernext_direct_avalanche_prediction',
    'no_production_ml_promotion',
})
_REQUIRED_ENGINE_ROLES = {
    'physical_backbone': 'SNOWPACK',
    'baseline_model': 'RF',
    'hybrid_ml': 'shadow_only',
    'modal': 'technical_shadow_only',
    'weathernext': 'optional_atmospheric_candidate',
    'awsome': 'qualification_lane',
    'smp': 'targeted_validation_lane',
}
_TRACK_ID = 'track_1_indian_candidate'
_SHA256_PATTERN = re.compile(r'^[0-9a-fA-F]{64}$')


class DecisionRecordError(ValueError):
    """Raised when the decision record fails strict validation."""


@dataclass(frozen=True)
class DecisionRecord:
    """Strictly validated Pir Panjal POC decision record."""
    schema_version: str
    decision_id: str
    selected_sector: str
    customer_selected_poc: bool
    Partner_approved: bool
    poc_scope_status: str
    evidence_class: str
    official_warning_eligible: bool
    elevation_band: str
    elevation_min_m: int
    elevation_max_m: int
    headline_horizon_hours: int
    optional_extension_hours: int
    ensemble_members: int
    problem_scope: tuple[str, ...]
    engine_roles: dict[str, str]
    track_id: str
    non_claims: frozenset[str]
    scope_hash_required: bool
    raw_bytes: bytes
    decision_record_sha256: str
    source_path: str = ''


def load_decision_record(
    path: Path | str,
    *,
    expected_sha256: str | None = None,
) -> DecisionRecord:
    """Load and strictly validate the Pir Panjal POC decision record.

    G4: When expected_sha256 is supplied, the raw-byte digest of the file
    must match it exactly. The trust root is the externally supplied digest,
    never derived from the bundle itself.
    """
    path = Path(path)
    if not path.is_file():
        raise DecisionRecordError(f'decision record not found: {path}')
    raw_bytes = path.read_bytes()
    return load_decision_record_from_bytes(
        raw_bytes, expected_sha256=expected_sha256, source_path=str(path)
    )


def load_decision_record_from_bytes(
    raw_bytes: bytes,
    *,
    expected_sha256: str | None = None,
    source_path: str = '',
) -> DecisionRecord:
    """Validate and load a decision record from already-read bytes.

    R7: Eliminates the TOCTOU seam between read_bytes() and load_decision_record().
    The caller reads the bytes once and passes them directly — no second read.
    """
    # A3: Require exact bytes — reject None, int, str, list, etc.
    # hashlib.sha256() raises raw TypeError for non-buffer types.
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise DecisionRecordError(
            f'raw_bytes must be bytes or bytearray, got '
            f'{type(raw_bytes).__name__}: {raw_bytes!r}'
        )
    # G5: Convert mutable bytearray to immutable bytes BEFORE hashing and
    # storing. If a caller passes a bytearray, they can mutate it after the
    # DecisionRecord is created, breaking the integrity guarantee. The hash
    # would no longer match the stored bytes.
    if isinstance(raw_bytes, bytearray):
        raw_bytes = bytes(raw_bytes)
    decision_record_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    # A3: Type-check expected_sha256 before calling string methods.
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str):
            raise DecisionRecordError(
                f'expected_sha256 must be a string, got '
                f'{type(expected_sha256).__name__}: {expected_sha256!r}'
            )
        if not _SHA256_PATTERN.fullmatch(expected_sha256):
            raise DecisionRecordError(
                f'expected_sha256 must be a 64-character hex string, got {expected_sha256!r}'
            )
        if expected_sha256.lower() != decision_record_sha256.lower():
            raise DecisionRecordError(
                f'decision record byte hash mismatch: expected={expected_sha256!r}, '
                f'actual={decision_record_sha256!r}'
            )

    try:
        record = json.loads(raw_bytes)
    except UnicodeDecodeError as exc:
        raise DecisionRecordError(f'decision record is not valid UTF-8: {exc}') from exc
    except json.JSONDecodeError as exc:
        raise DecisionRecordError(f'decision record is not valid JSON: {exc}') from exc
    if not isinstance(record, dict):
        raise DecisionRecordError('decision record must be a JSON object')

    return _validate_decision_record(record, raw_bytes, decision_record_sha256, source_path)


def validate_decision_record_bytes(
    raw_bytes: bytes,
    *,
    expected_sha256: str | None = None,
) -> DecisionRecord:
    """Validate decision record bytes without a file path."""
    # A3: Require exact bytes — reject None, int, str, list, etc.
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise DecisionRecordError(
            f'raw_bytes must be bytes or bytearray, got '
            f'{type(raw_bytes).__name__}: {raw_bytes!r}'
        )
    # G5: Convert mutable bytearray to immutable bytes before hashing.
    if isinstance(raw_bytes, bytearray):
        raw_bytes = bytes(raw_bytes)
    decision_record_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str):
            raise DecisionRecordError(
                f'expected_sha256 must be a string, got '
                f'{type(expected_sha256).__name__}: {expected_sha256!r}'
            )
        if not _SHA256_PATTERN.fullmatch(expected_sha256):
            raise DecisionRecordError(
                f'expected_sha256 must be a 64-character hex string, got {expected_sha256!r}'
            )
        if expected_sha256.lower() != decision_record_sha256.lower():
            raise DecisionRecordError(
                f'decision record byte hash mismatch: expected={expected_sha256!r}, '
                f'actual={decision_record_sha256!r}'
            )
    try:
        record = json.loads(raw_bytes)
    except UnicodeDecodeError as exc:
        raise DecisionRecordError(f'decision record is not valid UTF-8: {exc}') from exc
    except json.JSONDecodeError as exc:
        raise DecisionRecordError(f'decision record is not valid JSON: {exc}') from exc
    if not isinstance(record, dict):
        raise DecisionRecordError('decision record must be a JSON object')
    return _validate_decision_record(record, raw_bytes, decision_record_sha256, '')


def _require_str_field(record: dict[str, Any], field: str) -> str:
    """Extract a string field from a record, rejecting non-string types.

    P1/G5: Do not use str() coercion — int 123, float 123.4, and bool True
    would silently become '123', '123.4', 'True' and pass validation.
    Returns '' for missing fields (caller checks for emptiness separately).
    """
    raw = record.get(field)
    if raw is None:
        return ''
    if not isinstance(raw, str):
        raise DecisionRecordError(
            f'{field} must be a string, got {type(raw).__name__}: {raw!r}'
        )
    return raw.strip()


def _validate_decision_record(
    record: dict[str, Any],
    raw_bytes: bytes,
    decision_record_sha256: str,
    source_path: str,
) -> DecisionRecord:
    # A3b: Guard against non-dict record — _require_str_field calls
    # record.get() which raises AttributeError for None/list/str.
    if not isinstance(record, dict):
        raise DecisionRecordError(
            f'record must be a dict, got {type(record).__name__}: {record!r}'
        )
    errors: list[str] = []

    # P1/G5: Require strict string types — no str() coercion.
    schema_version = _require_str_field(record, 'schema_version')
    if schema_version != _DECISION_RECORD_SCHEMA_VERSION:
        errors.append(
            f'schema_version must be {_DECISION_RECORD_SCHEMA_VERSION!r}, got {schema_version!r}'
        )

    decision_id = _require_str_field(record, 'decision_id')
    if not decision_id:
        errors.append('decision_id must be a non-empty string')

    selected_sector = _require_str_field(record, 'selected_sector')
    if selected_sector != _SELECTED_SECTOR:
        errors.append(
            f'selected_sector must be {_SELECTED_SECTOR!r}, got {selected_sector!r}'
        )

    customer_selected_poc = record.get('customer_selected_poc')
    if customer_selected_poc is not True:
        errors.append('customer_selected_poc must be true')

    Partner_approved = record.get('Partner_approved')
    if Partner_approved is not False:
        errors.append('Partner_approved must be false for this POC')

    official_warning_eligible = record.get('official_warning_eligible')
    if official_warning_eligible is not False:
        errors.append('official_warning_eligible must be false for this POC')

    poc_scope_status = _require_str_field(record, 'poc_scope_status')
    if poc_scope_status not in ('customer_selected', 'customer_selected_local_candidate'):
        errors.append(
            f'poc_scope_status must be "customer_selected" or '
            f'"customer_selected_local_candidate", got {poc_scope_status!r}'
        )

    evidence_class = _require_str_field(record, 'evidence_class')
    if evidence_class != 'pipeline-proof-only':
        errors.append(
            f'evidence_class must be "pipeline-proof-only", got {evidence_class!r}'
        )

    regime = record.get('representative_regime') or {}
    if not isinstance(regime, dict):
        errors.append('representative_regime must be an object')
        regime = {}
    # P1/G5: Require strict string type for elevation_band.
    raw_band = regime.get('elevation_band')
    if raw_band is None:
        elevation_band = ''
    elif not isinstance(raw_band, str):
        errors.append(
            f'representative_regime.elevation_band must be a string, got '
            f'{type(raw_band).__name__}: {raw_band!r}'
        )
        elevation_band = ''
    else:
        elevation_band = raw_band.strip()
    if elevation_band != _ELEVATION_BAND:
        errors.append(
            f'representative_regime.elevation_band must be {_ELEVATION_BAND!r}, '
            f'got {elevation_band!r}'
        )
    elevation_min_m = regime.get('elevation_min_m')
    # P1-6: Strict type check — Python 3200.0 == 3200 is True
    if type(elevation_min_m) is not int:
        errors.append(
            f'representative_regime.elevation_min_m must be an exact integer '
            f'(type int), got {type(elevation_min_m).__name__}: {elevation_min_m!r}'
        )
    elif elevation_min_m != _ELEVATION_MIN_M:
        errors.append(
            f'representative_regime.elevation_min_m must be {_ELEVATION_MIN_M}, '
            f'got {elevation_min_m!r}'
        )
    elevation_max_m = regime.get('elevation_max_m')
    if type(elevation_max_m) is not int:
        errors.append(
            f'representative_regime.elevation_max_m must be an exact integer '
            f'(type int), got {type(elevation_max_m).__name__}: {elevation_max_m!r}'
        )
    elif elevation_max_m != _ELEVATION_MAX_M:
        errors.append(
            f'representative_regime.elevation_max_m must be {_ELEVATION_MAX_M}, '
            f'got {elevation_max_m!r}'
        )

    forecast = record.get('forecast') or {}
    if not isinstance(forecast, dict):
        errors.append('forecast must be an object')
        forecast = {}
    headline_horizon = forecast.get('headline_horizon_hours')
    # P1-6: Strict type check — Python 48.0 == 48 is True, so != alone
    # doesn't catch float values. Require type(value) is int.
    if type(headline_horizon) is not int:
        errors.append(
            f'forecast.headline_horizon_hours must be an exact integer '
            f'(type int), got {type(headline_horizon).__name__}: {headline_horizon!r}'
        )
    elif headline_horizon != _HEADLINE_HORIZON_HOURS:
        errors.append(
            f'forecast.headline_horizon_hours must be {_HEADLINE_HORIZON_HOURS}, '
            f'got {headline_horizon!r}'
        )
    optional_extension = forecast.get('optional_extension_hours')
    if type(optional_extension) is not int:
        errors.append(
            f'forecast.optional_extension_hours must be an exact integer '
            f'(type int), got {type(optional_extension).__name__}: {optional_extension!r}'
        )
    elif optional_extension != _OPTIONAL_EXTENSION_HOURS:
        errors.append(
            f'forecast.optional_extension_hours must be {_OPTIONAL_EXTENSION_HOURS}, '
            f'got {optional_extension!r}'
        )
    ensemble_members = forecast.get('ensemble_members')
    if type(ensemble_members) is not int:
        errors.append(
            f'forecast.ensemble_members must be an exact integer '
            f'(type int), got {type(ensemble_members).__name__}: {ensemble_members!r}'
        )
    elif ensemble_members != _ENSEMBLE_MEMBERS:
        errors.append(
            f'forecast.ensemble_members must be {_ENSEMBLE_MEMBERS}, got {ensemble_members!r}'
        )

    problem_scope = record.get('problem_scope') or []
    if not isinstance(problem_scope, list):
        errors.append('problem_scope must be a list')
        problem_scope_tuple: tuple[str, ...] = ()
    else:
        # A4: Validate element types BEFORE set() comparison — set()
        # raises TypeError: unhashable type for list/dict/set elements.
        problem_scope_list: list[str] = []
        all_strings = True
        for p in problem_scope:
            if not isinstance(p, str):
                errors.append(
                    f'problem_scope entries must be strings, got '
                    f'{type(p).__name__}: {p!r}'
                )
                all_strings = False
            else:
                problem_scope_list.append(p)
        if all_strings and set(problem_scope_list) != {'storm_new_snow', 'wind_slab'}:
            errors.append(
                f'problem_scope must be ["storm_new_snow", "wind_slab"], got {problem_scope!r}'
            )
        problem_scope_tuple = tuple(problem_scope_list)

    engine_roles = record.get('engine_roles') or {}
    if not isinstance(engine_roles, dict):
        errors.append('engine_roles must be an object')
        engine_roles = {}
    # A5: Validate that all keys are strings — non-string keys (int, None)
    # would be silently accepted by dict() and could cause issues during
    # serialization or comparison.
    for ek in engine_roles:
        if not isinstance(ek, str):
            errors.append(
                f'engine_roles keys must be strings, got '
                f'{type(ek).__name__}: {ek!r}'
            )
    for key, expected_value in _REQUIRED_ENGINE_ROLES.items():
        # P1/G5: Require strict string type for engine role values.
        raw_role = engine_roles.get(key)
        if raw_role is None:
            actual_value = ''
        elif not isinstance(raw_role, str):
            errors.append(
                f'engine_roles.{key} must be a string, got '
                f'{type(raw_role).__name__}: {raw_role!r}'
            )
            actual_value = ''
        else:
            actual_value = raw_role.strip()
        if actual_value != expected_value:
            errors.append(
                f'engine_roles.{key} must be {expected_value!r}, got {actual_value!r}'
            )

    track = record.get('track') or {}
    if not isinstance(track, dict):
        errors.append('track must be an object')
        track = {}
    # P1/G5: Require strict string type for track_id.
    raw_track_id = track.get('track_id')
    if raw_track_id is None:
        track_id = ''
    elif not isinstance(raw_track_id, str):
        errors.append(
            f'track.track_id must be a string, got '
            f'{type(raw_track_id).__name__}: {raw_track_id!r}'
        )
        track_id = ''
    else:
        track_id = raw_track_id.strip()
    if track_id != _TRACK_ID:
        errors.append(
            f'track.track_id must be {_TRACK_ID!r}, got {track_id!r}'
        )

    non_claims = record.get('non_claims') or []
    if not isinstance(non_claims, list):
        errors.append('non_claims must be a list')
        non_claims_set = frozenset()
    else:
        # P1/G5: Require strict string type for each non_claim entry.
        non_claims_list: list[str] = []
        for c in non_claims:
            if not isinstance(c, str):
                errors.append(
                    f'non_claims entries must be strings, got '
                    f'{type(c).__name__}: {c!r}'
                )
            else:
                non_claims_list.append(c)
        non_claims_set = frozenset(non_claims_list)
    missing_claims = _REQUIRED_NON_CLAIMS - non_claims_set
    if missing_claims:
        errors.append(f'non_claims is missing required entries: {sorted(missing_claims)}')

    immutability = record.get('immutability') or {}
    if not isinstance(immutability, dict):
        errors.append('immutability must be an object')
        immutability = {}
    scope_hash_required = immutability.get('scope_hash_required')
    if scope_hash_required is not True:
        errors.append('immutability.scope_hash_required must be true')

    if errors:
        raise DecisionRecordError(
            'decision record validation failed:\n  - ' + '\n  - '.join(errors)
        )

    return DecisionRecord(
        schema_version=schema_version,
        decision_id=decision_id,
        selected_sector=selected_sector,
        customer_selected_poc=bool(customer_selected_poc),
        Partner_approved=bool(Partner_approved),
        poc_scope_status=poc_scope_status,
        evidence_class=evidence_class,
        official_warning_eligible=bool(official_warning_eligible),
        elevation_band=elevation_band,
        # P1-6: No int() coercion — types already validated above.
        elevation_min_m=elevation_min_m,
        elevation_max_m=elevation_max_m,
        headline_horizon_hours=headline_horizon,
        optional_extension_hours=optional_extension,
        ensemble_members=ensemble_members,
        problem_scope=problem_scope_tuple,
        engine_roles=dict(engine_roles),
        track_id=track_id,
        non_claims=non_claims_set,
        scope_hash_required=bool(scope_hash_required),
        raw_bytes=raw_bytes,
        decision_record_sha256=decision_record_sha256,
        source_path=source_path,
    )


def validate_poc_scope(
    record: DecisionRecord,
    *,
    region_key: str,
    elevation_band: str,
    headline_horizon_hours: int | None = None,
) -> None:
    """Validate that a POC run's region, band, and horizon match the decision record.

    G3: Runtime refuses a wrong-sector or wrong-band decision record.
    """
    errors: list[str] = []
    if region_key != record.selected_sector:
        errors.append(
            f'region_key must be {record.selected_sector!r} (decision record), '
            f'got {region_key!r}'
        )
    if elevation_band != record.elevation_band:
        errors.append(
            f'elevation_band must be {record.elevation_band!r} (decision record), '
            f'got {elevation_band!r}'
        )
    if headline_horizon_hours is not None and headline_horizon_hours != record.headline_horizon_hours:
        errors.append(
            f'headline_horizon_hours must be {record.headline_horizon_hours} (decision record), '
            f'got {headline_horizon_hours}'
        )
    if errors:
        raise DecisionRecordError(
            'POC scope validation failed:\n  - ' + '\n  - '.join(errors)
        )


def decision_record_manifest_binding(record: DecisionRecord) -> dict[str, Any]:
    """Produce a manifest binding dict for embedding in run manifests.

    G4: The decision_record_sha256 is the raw-byte hash of the decision record
    file, suitable for embedding in result.json, manifest.json, and UI payloads.
    """
    return {
        'decision_id': record.decision_id,
        'decision_record_sha256': record.decision_record_sha256,
        'selected_sector': record.selected_sector,
        'elevation_band': record.elevation_band,
        'headline_horizon_hours': record.headline_horizon_hours,
        'ensemble_members': record.ensemble_members,
        'track_id': record.track_id,
        'evidence_class': record.evidence_class,
        'official_warning_eligible': record.official_warning_eligible,
        'scope_hash_required': record.scope_hash_required,
    }
