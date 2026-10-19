"""Snowpack execution and provenance contracts (Phase 1c + 1d).

Backward-compatible contracts for forcing manifests, atmospheric ensemble
members, SNOWPACK runs, complete vertical profiles, observations and SMP
profiles, post-processing products, avalanche episodes, and validation
reports.

Per Imp_plan.md Phase 1c:
  - Add backward-compatible contracts with provenance fields.
  - Preserve existing scalar proxy fields but add: profile layers, depth
    reference, observation method, source class, uncertainty, quality flags,
    run/provenance identifiers.

Per Imp_plan.md Phase 1d:
  - Define execution statuses: planned, configuration_validated, running,
    completed, partial, failed.
  - Prohibit 'completed' for dry-run-only paths.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Execution status semantics (Phase 1d)
# ---------------------------------------------------------------------------

# Valid execution statuses per Imp_plan.md Phase 1d + Phase 0.5 false-green closure.
# Phase 0.5 additions: toolchain_unavailable, native_running, fallback_proxy.
VALID_EXECUTION_STATUSES = frozenset({
    'planned',
    'configuration_validated',
    'toolchain_unavailable',  # Binary/toolchain missing — blocked
    'inputs_unavailable',     # Required inputs absent — blocked
    'native_running',         # Native binary actually invoked and executing
    'running',
    'completed',
    'partial',
    'failed',
    'fallback_proxy',         # Fell back to proxy/heuristic, not native
})

LEGACY_EXECUTION_STATUS_MAP = frozenset({'skipped'})


def normalize_execution_status(status: object) -> str:
    """Normalize legacy execution status without treating it as completion."""
    if status == 'skipped':
        return 'inputs_unavailable'
    if not isinstance(status, str) or status not in VALID_EXECUTION_STATUSES:
        raise ContractValidationError(f'Invalid execution status: {status!r}')
    return status

# Statuses that represent actual native execution (not dry-run, not proxy)
NATIVE_EXECUTION_STATUSES = frozenset({'completed', 'partial', 'running', 'native_running'})

# Statuses that represent dry-run or non-execution
DRY_RUN_STATUSES = frozenset({
    'configuration_validated', 'planned', 'failed',
    'toolchain_unavailable', 'inputs_unavailable', 'fallback_proxy',
})

# It is a contract violation to use 'completed' for a dry-run-only path.
# This is the key rule from Phase 1d: "Prohibit completed for dry-run-only paths."


class ContractValidationError(Exception):
    """Raised when a snowpack contract validation fails."""


_RELEASE_RUN_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
_RELEASE_ENGINES = frozenset({'snowpack_direct', 'awsome'})


def validate_release_manifest_id(manifest_id: object, *, field: str = 'manifest_id') -> str:
    """Validate a release manifest ID with the same safety contract as run IDs."""
    if not isinstance(manifest_id, str) or not manifest_id:
        raise ValueError(f'{field} must be a non-empty string')
    if manifest_id != manifest_id.strip():
        raise ValueError(f'{field} must not have surrounding whitespace')
    if '..' in manifest_id or '/' in manifest_id or '\\' in manifest_id or '\x00' in manifest_id:
        raise ValueError(f'{field} contains an unsafe path-like sequence')
    if not _RELEASE_RUN_ID_RE.fullmatch(manifest_id):
        raise ValueError(f'{field} must be 1-128 characters of safe ASCII')
    return manifest_id


def validate_release_run_id(run_id: object) -> str:
    """Validate a release run ID without normalizing or generating it.

    Release identity is an input contract. Empty values, whitespace, path
    separators, traversal markers, non-ASCII values, and oversized IDs fail
    closed instead of falling back to a timestamp-derived identity.
    """
    if not isinstance(run_id, str) or not run_id:
        raise ValueError('release run_id must be a non-empty string')
    if run_id != run_id.strip():
        raise ValueError('release run_id must not have surrounding whitespace')
    if '..' in run_id or '/' in run_id or '\\' in run_id or '\x00' in run_id:
        raise ValueError('release run_id contains an unsafe path-like sequence')
    if not _RELEASE_RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            'release run_id must be 1-128 characters of safe ASCII '
            '[A-Za-z0-9._:-]'
        )
    return run_id


def validate_release_engine(engine: object, *, no_fallback: object) -> str:
    """Require one explicit engine whenever fallback is forbidden."""
    if no_fallback is not True:
        raise ValueError('release/acceptance mode requires no_fallback=True')
    if not isinstance(engine, str) or engine not in _RELEASE_ENGINES:
        raise ValueError(
            'release/acceptance mode requires engine=snowpack_direct or engine=awsome'
        )
    return engine


def validate_run_id_binding(**identities: object) -> str:
    """Require all named release identities to be valid and exactly equal."""
    if not identities:
        raise ValueError('at least one release identity is required')
    validated = {
        name: validate_release_run_id(value)
        for name, value in identities.items()
    }
    values = set(validated.values())
    if len(values) != 1:
        raise ValueError(
            'release identity mismatch: '
            + ', '.join(f'{name}={value!r}' for name, value in validated.items())
        )
    return next(iter(values))


def validate_execution_status(status: str, *, is_dry_run: bool = False) -> None:
    """Validate that an execution status is valid and semantically correct.

    Args:
        status: The execution status string to validate.
        is_dry_run: If True, the status must not be 'completed', 'native_running',
            or 'partial' (native-execution-only statuses).

    Raises:
        ContractValidationError: If status is invalid or semantically incorrect.
    """
    if status not in VALID_EXECUTION_STATUSES:
        raise ContractValidationError(
            f'Invalid execution status "{status}". '
            f'Valid statuses: {sorted(VALID_EXECUTION_STATUSES)}'
        )
    if is_dry_run and status in NATIVE_EXECUTION_STATUSES:
        raise ContractValidationError(
            f'Dry-run-only path cannot have status "{status}". '
            f'Dry-run paths must use: {sorted(DRY_RUN_STATUSES)}'
        )


# ---------------------------------------------------------------------------
# Phase 0.5: Strict 'completed' validation (false-green closure)
# ---------------------------------------------------------------------------

# Required output suffixes for a 'completed' native run.
# Per codex audit: .smet, .pro, .sno, .haz, processed meteorology, execution log.
COMPLETED_REQUIRED_OUTPUT_SUFFIXES = frozenset({
    '.smet',  # Forcing artifact
    '.pro',   # Profile time series
    '.sno',   # Snow profile
    '.haz',   # Hazard file
    '.log',   # Execution log
})

# Processed meteorology output extensions (SNOWPACK can emit .smet for meteo out)
COMPLETED_REQUIRED_OUTPUT_TYPES = frozenset({
    'profile',            # .pro
    'snow_profile',       # .sno
    'hazard',             # .haz
    'forcing',            # .smet (input forcing)
    'processed_meteo',    # processed meteorology output
    'execution_log',      # .log
})


def validate_completed_status(
    *,
    native_binary_invoked: bool,
    output_dir_is_clean: bool,
    output_suffixes_present: set[str],
    manifest_validated: bool,
    has_hash_verification: bool,
    no_fallback: bool,
    toolchain_id: str,
    forcing_manifest_id: str,
    geometry_manifest_id: str,
    run_id: str,
) -> list[str]:
    """Validate that a 'completed' status meets all Phase 0.5 requirements.

    Per codex audit Phase 0.5, 'completed' requires ALL of:
      - native binary actually invoked
      - clean run-specific output directory
      - non-empty .smet, .pro, .sno, .haz
      - processed meteorology and execution log
      - verified SHA-256 manifest
      - no fallback
      - linked toolchain, forcing, geometry, and run identifiers

    Returns list of violation strings (empty = valid for completed).
    """
    violations: list[str] = []
    if not native_binary_invoked:
        violations.append('completed: native binary was not actually invoked')
    if not output_dir_is_clean:
        violations.append('completed: output directory was not clean/run-specific (stale files detected)')
    missing = COMPLETED_REQUIRED_OUTPUT_SUFFIXES - output_suffixes_present
    if missing:
        violations.append(f'completed: missing required output suffixes: {sorted(missing)}')
    if not manifest_validated:
        violations.append('completed: artifact manifest was not validated')
    if not has_hash_verification:
        violations.append('completed: SHA-256 hash verification not performed')
    if not no_fallback:
        violations.append('completed: fallback was used — completed requires no fallback')
    if not toolchain_id:
        violations.append('completed: toolchain identifier is required')
    if not forcing_manifest_id:
        violations.append('completed: forcing manifest identifier is required')
    if not geometry_manifest_id:
        violations.append('completed: geometry manifest identifier is required')
    if not run_id:
        violations.append('completed: run identifier is required')
    return violations


# ---------------------------------------------------------------------------
# Source class classification (Phase 1c / Phase 2)
# ---------------------------------------------------------------------------

VALID_SOURCE_CLASSES = frozenset({
    'direct',          # Direct measurement (AWS, snow pit, SMP)
    'derived',         # Derived from direct measurements (e.g., interpolated)
    'proxy',           # Proxy feature (e.g., weather-derived snowpack proxy)
    'synthetic',       # Synthetic/test data
    'nwp',             # NWP model output
    'reanalysis',      # Reanalysis product
    'ensemble',        # Ensemble member
    'remote_sensing',  # Remote sensing (satellite, SAR)
})


# ---------------------------------------------------------------------------
# Provenance metadata (shared across all contracts)
# ---------------------------------------------------------------------------

_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class ProvenanceMetadata:
    """Provenance metadata required for all snowpack artifacts.

    Per Imp_plan.md Phase 1c and cross-cutting rules:
      - Preserve source, licence, timestamp, coordinate, unit and hash metadata.
      - Distinguish direct, derived, proxy and synthetic data.
    """
    source: str                    # Source identifier (e.g., "open_meteo_archive", "Partner_station")
    source_class: str              # One of VALID_SOURCE_CLASSES
    licence: str                   # Licence or rights statement
    timestamp: str                 # ISO 8601 timestamp of data generation
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    units: dict[str, str] = field(default_factory=dict)
    hash: str = ''                 # SHA-256 of the artifact content
    run_id: str = ''               # Run/provenance identifier
    provenance_chain: tuple[str, ...] = ()  # Chain of source IDs

    def validate(self) -> None:
        if self.source_class not in VALID_SOURCE_CLASSES:
            raise ContractValidationError(
                f'Invalid source_class "{self.source_class}". '
                f'Valid classes: {sorted(VALID_SOURCE_CLASSES)}'
            )
        if not self.source:
            raise ContractValidationError('ProvenanceMetadata: source is required')
        if not self.licence:
            raise ContractValidationError('ProvenanceMetadata: licence is required')
        if not self.timestamp:
            raise ContractValidationError('ProvenanceMetadata: timestamp is required')
        if not self.units:
            raise ContractValidationError('ProvenanceMetadata: units are required')
        if not self.run_id:
            raise ContractValidationError('ProvenanceMetadata: run_id is required')
        if not _SHA256_RE.fullmatch(self.hash.lower()):
            raise ContractValidationError('ProvenanceMetadata: hash must be a SHA-256 hex digest')
        # Validate ISO timestamp format
        try:
            datetime.fromisoformat(self.timestamp)
        except ValueError:
            raise ContractValidationError(
                f'ProvenanceMetadata: timestamp "{self.timestamp}" is not valid ISO 8601'
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            'source': self.source,
            'source_class': self.source_class,
            'licence': self.licence,
            'timestamp': self.timestamp,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'elevation_m': self.elevation_m,
            'units': dict(self.units),
            'hash': self.hash,
            'run_id': self.run_id,
            'provenance_chain': list(self.provenance_chain),
        }


def _parse_utc_timestamp(value: object, *, field: str) -> datetime:
    """Parse a required timezone-aware UTC timestamp for release contracts."""
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f'{field} must be a non-empty ISO-8601 string')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ContractValidationError(f'{field} is not valid ISO-8601: {value!r}') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractValidationError(f'{field} must be timezone-aware UTC')
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractValidationError(f'{field} must use UTC offset +00:00')
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class InitialSnowStateContract:
    """Explicit initial snow/soil state required for a native release run.

    ``snow_free`` is only a declaration that must itself be hash-bound. A
    profile-backed state additionally requires a relative state file path.
    The contract does not decide whether snow-free initialization is
    scientifically appropriate; that decision remains an operator/data gate.
    """

    state_id: str
    state_type: str                 # 'snow_free' or 'profile'
    start_time: str                 # timezone-aware UTC ISO-8601
    source: str
    state_sha256: str
    provenance: ProvenanceMetadata
    state_file_path: str = ''

    def validate(self) -> None:
        if not self.state_id:
            raise ContractValidationError('InitialSnowState: state_id is required')
        if self.state_type not in ('snow_free', 'profile'):
            raise ContractValidationError(
                f'InitialSnowState: invalid state_type {self.state_type!r}'
            )
        _parse_utc_timestamp(self.start_time, field='InitialSnowState.start_time')
        if not self.source:
            raise ContractValidationError('InitialSnowState: source is required')
        if not _SHA256_RE.fullmatch(self.state_sha256.lower()):
            raise ContractValidationError(
                'InitialSnowState: state_sha256 must be a SHA-256 hex digest'
            )
        if self.state_type == 'profile' and not self.state_file_path:
            raise ContractValidationError(
                'InitialSnowState: profile state requires state_file_path'
            )
        if self.state_type == 'snow_free' and self.state_file_path:
            raise ContractValidationError(
                'InitialSnowState: snow_free state must not reference a profile file'
            )
        self.provenance.validate()


@dataclass(frozen=True)
class ForecastSemanticsContract:
    """Bind forcing to cycle, valid window, member, and lead-time semantics.

    ``historical_forecast_replay`` is explicit because Open-Meteo's
    ``gfs_seamless`` archive is a stitched historical forecast product, not a
    single issued forecast replay and not a reanalysis product.
    """

    mode: str                       # analysis, forecast, reanalysis, ensemble, historical_forecast_replay
    source: str
    forecast_cycle: str             # timezone-aware UTC ISO-8601
    valid_from: str                 # timezone-aware UTC ISO-8601
    valid_to: str                   # timezone-aware UTC ISO-8601
    as_of: str                      # timezone-aware UTC ISO-8601
    lead_time_h: float
    region_key: str
    elevation_band: str
    forcing_manifest_id: str
    member_id: str = ''
    ensemble_members: int = 1

    def validate(self) -> None:
        if self.mode not in (
            'analysis', 'forecast', 'reanalysis', 'ensemble',
            'historical_forecast_replay',
        ):
            raise ContractValidationError(
                f'ForecastSemantics: invalid mode {self.mode!r}'
            )
        if not self.source:
            raise ContractValidationError('ForecastSemantics: source is required')
        cycle = _parse_utc_timestamp(
            self.forecast_cycle, field='ForecastSemantics.forecast_cycle'
        )
        valid_from = _parse_utc_timestamp(
            self.valid_from, field='ForecastSemantics.valid_from'
        )
        valid_to = _parse_utc_timestamp(
            self.valid_to, field='ForecastSemantics.valid_to'
        )
        as_of = _parse_utc_timestamp(self.as_of, field='ForecastSemantics.as_of')
        if valid_from > valid_to:
            raise ContractValidationError(
                'ForecastSemantics: valid_from must be <= valid_to'
            )
        if as_of > valid_from:
            raise ContractValidationError(
                'ForecastSemantics: as_of must be <= valid_from'
            )
        if cycle > as_of:
            raise ContractValidationError(
                'ForecastSemantics: forecast_cycle must be <= as_of'
            )
        if self.lead_time_h < 0:
            raise ContractValidationError('ForecastSemantics: lead_time_h must be >= 0')
        derived_lead_h = (valid_from - as_of).total_seconds() / 3600.0
        if abs(derived_lead_h - float(self.lead_time_h)) > 1e-6:
            raise ContractValidationError(
                'ForecastSemantics: lead_time_h does not match as_of → valid_from'
            )
        if not self.region_key or not self.elevation_band:
            raise ContractValidationError(
                'ForecastSemantics: region_key and elevation_band are required'
            )
        try:
            validate_release_manifest_id(
                self.forcing_manifest_id,
                field='ForecastSemantics.forcing_manifest_id',
            )
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if self.mode == 'ensemble' and not self.member_id:
            raise ContractValidationError(
                'ForecastSemantics: ensemble mode requires member_id'
            )
        # R3: Reject non-int ensemble_members BEFORE any numeric comparison.
        # bool is a subclass of int in Python, so type(True) is not int is True.
        # float 1.5 passes `>= 1` but is not an exact integer.
        # string "1" and None would cause TypeError on `<` comparison.
        if type(self.ensemble_members) is not int:
            raise ContractValidationError(
                f'ForecastSemantics: ensemble_members must be an exact int, '
                f'got {type(self.ensemble_members).__name__}: '
                f'{self.ensemble_members!r}'
            )
        if self.ensemble_members < 1:
            raise ContractValidationError(
                'ForecastSemantics: ensemble_members must be >= 1'
            )
        if self.ensemble_members > 1 and not self.member_id:
            raise ContractValidationError(
                'ForecastSemantics: ensemble_members > 1 requires member_id'
            )


# ---------------------------------------------------------------------------
# 1. Forcing Manifest Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ForcingManifestContract:
    """Contract for a forcing manifest (SMET file package).

    Per Imp_plan.md Phase 1c: forcing manifests must have complete provenance.
    Per Imp_plan.md Phase 4: reject incomplete forcing rather than silently
    filling critical variables.
    """
    region_key: str
    elevation_band: str
    aspect_class: str
    forecast_horizon_h: int
    variables: tuple[str, ...]       # Required: TA, RH, VW, ISWR, ILWR, PSUM
    smet_file_path: str
    provenance: ProvenanceMetadata
    member_id: str = ''              # Ensemble member ID (empty for deterministic)
    is_complete: bool = True         # False if any critical variable is missing
    forecast_semantics: ForecastSemanticsContract | None = None

    # SNOWPACK accepts semantic alternatives rather than one exact field list.
    # See the official requirements: ISWR/RSWR/NET_SW, ILWR/TSS, PSUM/HS.
    REQUIRED_VARIABLE_GROUPS = (
        frozenset({'TA'}),
        frozenset({'RH'}),
        frozenset({'VW'}),
        frozenset({'ISWR', 'RSWR', 'NET_SW'}),
        frozenset({'ILWR', 'TSS'}),
        frozenset({'PSUM', 'HS'}),
    )

    def missing_required_groups(self) -> list[tuple[str, ...]]:
        """Return semantic forcing groups that have no supplied alternative."""
        supplied = set(self.variables)
        return [tuple(sorted(group)) for group in self.REQUIRED_VARIABLE_GROUPS if not supplied.intersection(group)]

    def validate(self) -> None:
        if not self.region_key:
            raise ContractValidationError('ForcingManifest: region_key is required')
        if not self.elevation_band:
            raise ContractValidationError('ForcingManifest: elevation_band is required')
        if self.aspect_class not in ('N', 'E', 'S', 'W', 'flat'):
            raise ContractValidationError(
                f'ForcingManifest: invalid aspect_class "{self.aspect_class}"'
            )
        if self.forecast_horizon_h < 0:
            raise ContractValidationError(
                f'ForcingManifest: forecast_horizon_h must be >= 0, got {self.forecast_horizon_h}'
            )
        missing_groups = self.missing_required_groups()
        if missing_groups:
            raise ContractValidationError(
                'ForcingManifest: missing semantic forcing groups: '
                f'{missing_groups}'
            )
        self.provenance.validate()
        if self.forecast_semantics is not None:
            self.forecast_semantics.validate()
            if self.forecast_semantics.region_key != self.region_key:
                raise ContractValidationError(
                    'ForcingManifest: forecast semantics region does not match manifest'
                )
            if self.forecast_semantics.elevation_band != self.elevation_band:
                raise ContractValidationError(
                    'ForcingManifest: forecast semantics elevation band does not match manifest'
                )
            if self.forecast_semantics.member_id and self.member_id:
                if self.forecast_semantics.member_id != self.member_id:
                    raise ContractValidationError(
                        'ForcingManifest: forecast semantics member does not match manifest'
                    )
        if not self.is_complete:
            raise ContractValidationError(
                'ForcingManifest: incomplete forcing cannot be validated. '
                'Reject incomplete forcing rather than silently filling critical variables.'
            )


# ---------------------------------------------------------------------------
# 2. Atmospheric Ensemble Member Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnsembleMemberContract:
    """Contract for a single atmospheric ensemble member.

    Per Imp_plan.md Phase 4: begin with 10-20 members for development,
    target 20-50 only after compute/value verification.
    """
    member_id: str
    source: str                      # e.g., "weathernext", "open_meteo", "imdaa"
    forecast_cycle: str              # ISO 8601
    lead_time_h: int
    variables: tuple[str, ...]
    provenance: ProvenanceMetadata
    perturbation_type: str = 'none'  # 'none', 'calibrated', 'fgn_inspired'

    def validate(self) -> None:
        if not self.member_id:
            raise ContractValidationError('EnsembleMember: member_id is required')
        if not self.source:
            raise ContractValidationError('EnsembleMember: source is required')
        if self.lead_time_h < 0:
            raise ContractValidationError(
                f'EnsembleMember: lead_time_h must be >= 0, got {self.lead_time_h}'
            )
        if self.perturbation_type not in ('none', 'calibrated', 'fgn_inspired'):
            raise ContractValidationError(
                f'EnsembleMember: invalid perturbation_type "{self.perturbation_type}"'
            )
        self.provenance.validate()


@dataclass(frozen=True)
class NativeEnsembleMemberLineageContract:
    """Bind one atmospheric member to its complete SNOWPACK execution lineage.

    This is intentionally separate from ``EnsembleMemberContract``. The older
    contract describes an atmospheric member; this contract is only satisfied
    when that member has explicit forcing, geometry, initial-state, native run,
    and output-manifest identities.
    """

    member_id: str
    source: str
    forecast_cycle: str
    lead_time_h: float
    region_key: str
    elevation_band: str
    forcing_manifest_id: str
    geometry_manifest_id: str
    initial_state_manifest_id: str
    snowpack_run_id: str
    output_manifest_id: str
    provenance: ProvenanceMetadata
    execution_status: str = 'planned'

    def validate(self) -> None:
        try:
            validate_release_manifest_id(self.member_id, field='EnsembleLineage.member_id')
            validate_release_manifest_id(self.forcing_manifest_id, field='EnsembleLineage.forcing_manifest_id')
            validate_release_manifest_id(self.geometry_manifest_id, field='EnsembleLineage.geometry_manifest_id')
            validate_release_manifest_id(self.initial_state_manifest_id, field='EnsembleLineage.initial_state_manifest_id')
            validate_release_manifest_id(self.output_manifest_id, field='EnsembleLineage.output_manifest_id')
            validate_release_run_id(self.snowpack_run_id)
        except ValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if not self.source.strip() or not self.region_key.strip() or not self.elevation_band.strip():
            raise ContractValidationError(
                'EnsembleLineage source, region_key, and elevation_band are required'
            )
        if not isinstance(self.lead_time_h, (int, float)) or not math.isfinite(float(self.lead_time_h)):
            raise ContractValidationError('EnsembleLineage lead_time_h must be finite')
        if self.lead_time_h < 0:
            raise ContractValidationError('EnsembleLineage lead_time_h must be >= 0')
        _parse_utc_timestamp(self.forecast_cycle, field='EnsembleLineage.forecast_cycle')
        try:
            validate_execution_status(self.execution_status)
        except ContractValidationError as exc:
            raise ContractValidationError(str(exc)) from exc
        if self.provenance.run_id != self.snowpack_run_id:
            raise ContractValidationError(
                'EnsembleLineage provenance.run_id must match snowpack_run_id'
            )
        self.provenance.validate()


def validate_native_ensemble_lineage(
    members: Sequence[NativeEnsembleMemberLineageContract],
    *,
    stage: str,
) -> tuple[NativeEnsembleMemberLineageContract, ...]:
    """Validate bounded member counts and shared execution context.

    ``development`` intentionally means exactly three members. ``verification``
    means 10–20 members, matching the planned staged rollout. This function
    does not claim scientific calibration or operational ensemble skill.
    """

    values = tuple(members)
    bounds = {'development': (3, 3), 'verification': (10, 20)}
    if stage not in bounds:
        raise ContractValidationError(
            f'EnsembleLineage unsupported stage {stage!r}; expected development or verification'
        )
    minimum, maximum = bounds[stage]
    if not minimum <= len(values) <= maximum:
        raise ContractValidationError(
            f'EnsembleLineage {stage} requires {minimum}-{maximum} members; got {len(values)}'
        )
    for member in values:
        member.validate()
    for field_name in ('member_id', 'snowpack_run_id', 'output_manifest_id'):
        identities = [getattr(member, field_name) for member in values]
        if len(set(identities)) != len(identities):
            raise ContractValidationError(f'EnsembleLineage duplicate {field_name}')
    context_fields = (
        'forecast_cycle', 'lead_time_h', 'region_key', 'elevation_band',
        'geometry_manifest_id', 'initial_state_manifest_id',
    )
    first = values[0]
    for member in values[1:]:
        for field_name in context_fields:
            if getattr(member, field_name) != getattr(first, field_name):
                raise ContractValidationError(
                    f'EnsembleLineage member context mismatch for {field_name}'
                )
    return values


# ---------------------------------------------------------------------------
# 3. SNOWPACK Run Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnowpackRunContract:
    """Contract for a SNOWPACK simulation run.

    Per Imp_plan.md Phase 1d: execution status must distinguish dry-run from
    native execution. 'completed' is prohibited for dry-run-only paths.
    """
    run_id: str
    region_key: str
    elevation_band: str
    aspect_class: str
    slope_angle: float
    forcing_manifest_id: str
    execution_status: str
    provenance: ProvenanceMetadata
    is_dry_run: bool = False
    output_paths: tuple[str, ...] = ()
    binary_version: str = ''         # SNOWPACK/MeteoIO version
    started_at: str = ''
    completed_at: str = ''
    initial_state: InitialSnowStateContract | None = None
    forecast_semantics: ForecastSemanticsContract | None = None

    def validate(self) -> None:
        if not self.run_id:
            raise ContractValidationError('SnowpackRun: run_id is required')
        if not self.region_key:
            raise ContractValidationError('SnowpackRun: region_key is required')
        validate_execution_status(self.execution_status, is_dry_run=self.is_dry_run)
        self.provenance.validate()
        if self.initial_state is not None:
            self.initial_state.validate()
        if self.forecast_semantics is not None:
            self.forecast_semantics.validate()
            if self.forecast_semantics.region_key != self.region_key:
                raise ContractValidationError(
                    'SnowpackRun: forecast semantics region does not match run'
                )
            if self.forecast_semantics.elevation_band != self.elevation_band:
                raise ContractValidationError(
                    'SnowpackRun: forecast semantics elevation band does not match run'
                )
            if self.forecast_semantics.forcing_manifest_id != self.forcing_manifest_id:
                raise ContractValidationError(
                    'SnowpackRun: forecast forcing ID does not match run forcing ID'
                )
        # If status is 'completed', must have output paths
        if self.execution_status == 'completed' and not self.output_paths:
            raise ContractValidationError(
                'SnowpackRun: status "completed" requires non-empty output_paths'
            )
        # If status is 'completed', must not be a dry run
        if self.execution_status == 'completed' and self.is_dry_run:
            raise ContractValidationError(
                'SnowpackRun: dry-run path cannot have status "completed"'
            )
        # Phase 0.5: 'completed' requires binary_version (toolchain linkage)
        if self.execution_status == 'completed' and not self.binary_version:
            raise ContractValidationError(
                'SnowpackRun: status "completed" requires binary_version (toolchain linkage)'
            )
        # Phase 0.5: 'completed' requires forcing_manifest_id
        if self.execution_status == 'completed' and not self.forcing_manifest_id:
            raise ContractValidationError(
                'SnowpackRun: status "completed" requires forcing_manifest_id'
            )

    def validate_for_native_release(self) -> None:
        """Require the state and forecast contracts before native promotion."""
        self.validate()
        if self.execution_status != 'completed':
            raise ContractValidationError(
                'SnowpackRun: native release validation requires completed status'
            )
        if self.initial_state is None:
            raise ContractValidationError(
                'SnowpackRun: native release requires initial_state'
            )
        if self.forecast_semantics is None:
            raise ContractValidationError(
                'SnowpackRun: native release requires forecast_semantics'
            )


# ---------------------------------------------------------------------------
# 4. Vertical Profile Contract (preserves full profile structure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProfileLayer:
    """A single layer in a vertical snowpack profile."""
    depth_m: float
    thickness_m: float
    grain_type: str
    grain_size_mm: float
    density_kgm3: float
    temperature_k: float
    liquid_water_content_pct: float
    hardness: str = ''               # Swiss hand hardness code
    shear_strength_kpa: float | None = None
    uncertainty: float = 0.0         # Uncertainty estimate (0-1)


@dataclass(frozen=True)
class VerticalProfileContract:
    """Contract for a complete vertical snowpack profile.

    Per Imp_plan.md Phase 1c: preserve existing scalar proxy fields but add
    profile layers, depth reference, observation method, source class,
    uncertainty, quality flags, run/provenance identifiers.

    This contract is backward-compatible: the existing SnowpackProxy scalar
    fields (estimated_shear_strength, snow_settlement_index) can be derived
    from a complete profile, but the full profile structure is preserved.
    """
    profile_id: str
    region_key: str
    elevation_band: str
    aspect_class: str
    timestamp: str                   # ISO 8601
    depth_reference: str             # 'ground' or 'surface'
    observation_method: str          # 'snowpack_native', 'snow_pit', 'smp', 'aws_derived'
    layers: tuple[ProfileLayer, ...]
    provenance: ProvenanceMetadata
    snow_height_m: float = 0.0
    swe_mm: float = 0.0
    quality_flags: tuple[str, ...] = ()
    # Backward-compatible scalar proxies (derived from layers)
    estimated_shear_strength_kpa: float | None = None
    snow_settlement_index: float | None = None

    def validate(self) -> None:
        if not self.profile_id:
            raise ContractValidationError('VerticalProfile: profile_id is required')
        if self.depth_reference not in ('ground', 'surface'):
            raise ContractValidationError(
                f'VerticalProfile: invalid depth_reference "{self.depth_reference}"'
            )
        if self.observation_method not in (
            'snowpack_native', 'snow_pit', 'smp', 'aws_derived', 'proxy'
        ):
            raise ContractValidationError(
                f'VerticalProfile: invalid observation_method "{self.observation_method}"'
            )
        if not self.layers:
            raise ContractValidationError('VerticalProfile: must have at least one layer')
        self.provenance.validate()
        # Proxy data must retain proxy source class
        if self.observation_method == 'proxy':
            if self.provenance.source_class not in ('proxy', 'derived', 'synthetic'):
                raise ContractValidationError(
                    'VerticalProfile: proxy observation_method requires '
                    f'source_class in (proxy, derived, synthetic), got {self.provenance.source_class}'
                )


# ---------------------------------------------------------------------------
# 5. Avalanche Episode Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AvalancheEpisodeContract:
    """Contract for a tracked avalanche episode.

    Per Imp_plan.md Phase 9: define a stateful AvalancheEpisode object with
    problem type, spatial cells/bands, first detection, persistence, peak
    probability, expected decay, affected aspect/elevation, source members,
    confidence/coverage.

    Key rule: no episode is presented as an official warning.
    """
    episode_id: str
    problem_type: str                # storm_slab, wind_slab, persistent_weak_layer, wet_snow
    region_key: str
    elevation_band: str
    aspect_class: str
    first_detection: str             # ISO 8601
    persistence_h: int
    peak_probability: float
    expected_decay_h: int
    source_members: tuple[str, ...]
    confidence: float                # 0-1
    coverage: float                  # 0-1
    is_official_warning: bool = False  # Must always be False until Partner approves

    def validate(self) -> None:
        if not self.episode_id:
            raise ContractValidationError('AvalancheEpisode: episode_id is required')
        if self.problem_type not in (
            'storm_slab', 'wind_slab', 'persistent_weak_layer', 'wet_snow'
        ):
            raise ContractValidationError(
                f'AvalancheEpisode: invalid problem_type "{self.problem_type}"'
            )
        for field_name, value in (
            ('region_key', self.region_key),
            ('elevation_band', self.elevation_band),
            ('aspect_class', self.aspect_class),
        ):
            if not isinstance(value, str) or not value:
                raise ContractValidationError(
                    f'AvalancheEpisode: {field_name} is required'
                )
        _parse_utc_timestamp(
            self.first_detection, field='AvalancheEpisode.first_detection'
        )
        if type(self.persistence_h) is not int or self.persistence_h < 0:
            raise ContractValidationError(
                'AvalancheEpisode: persistence_h must be a non-negative integer'
            )
        if type(self.expected_decay_h) is not int or self.expected_decay_h < 1:
            raise ContractValidationError(
                'AvalancheEpisode: expected_decay_h must be a positive integer'
            )
        if not isinstance(self.source_members, (tuple, list)) or not all(
            isinstance(member, str) and member for member in self.source_members
        ):
            raise ContractValidationError(
                'AvalancheEpisode: source_members must contain non-empty strings'
            )
        if self.is_official_warning:
            raise ContractValidationError(
                'AvalancheEpisode: is_official_warning must be False. '
                'Official warnings require Partner approval.'
            )
        if not (0.0 <= self.peak_probability <= 1.0):
            raise ContractValidationError(
                f'AvalancheEpisode: peak_probability must be 0-1, got {self.peak_probability}'
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ContractValidationError(
                f'AvalancheEpisode: confidence must be 0-1, got {self.confidence}'
            )
        if not (0.0 <= self.coverage <= 1.0):
            raise ContractValidationError(
                f'AvalancheEpisode: coverage must be 0-1, got {self.coverage}'
            )


# ---------------------------------------------------------------------------
# 6. Validation Report Contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationReportContract:
    """Contract for a validation report.

    Per Imp_plan.md Phase 11: physical validation comes first, probabilistic
    validation follows only after label approval.
    """
    report_id: str
    region_key: str
    validation_type: str             # 'physical' or 'probabilistic'
    metrics: dict[str, float]
    paired_coverage: float           # 0-1
    provenance: ProvenanceMetadata
    is_label_approved: bool = False  # Required for probabilistic validation

    def validate(self) -> None:
        if not self.report_id:
            raise ContractValidationError('ValidationReport: report_id is required')
        if self.validation_type not in ('physical', 'probabilistic'):
            raise ContractValidationError(
                f'ValidationReport: invalid validation_type "{self.validation_type}"'
            )
        if self.validation_type == 'probabilistic' and not self.is_label_approved:
            raise ContractValidationError(
                'ValidationReport: probabilistic validation requires is_label_approved=True '
                '(Partner label approval required)'
            )
        if not (0.0 <= self.paired_coverage <= 1.0):
            raise ContractValidationError(
                f'ValidationReport: paired_coverage must be 0-1, got {self.paired_coverage}'
            )
        self.provenance.validate()


# ---------------------------------------------------------------------------
# Utility: compute hash for provenance
# ---------------------------------------------------------------------------

def compute_artifact_hash(content: str | bytes) -> str:
    """Compute SHA-256 hash of artifact content for provenance."""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()
