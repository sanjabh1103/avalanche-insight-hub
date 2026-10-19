"""Shared POC scope contract: cross-validate decision record, result, manifest, and forecast.

C0.1/C0.2/C0.3/C0.8: The consumer release gate and the producer must use the
same validator to ensure exact semantic agreement across all layers:

  decision record ←→ result.json ←→ artifact manifest ←→ forecast semantics

No layer may fall back to values from another layer. All fields must be
explicitly present and exactly equal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.common.pir_panjal_decision_record import DecisionRecord
from backend.common.snowpack_artifact_manifest import ArtifactManifest
from backend.common.snowpack_contracts import ForecastSemanticsContract


class PocScopeError(ValueError):
    """Raised when POC scope layers are inconsistent."""


@dataclass(frozen=True)
class PocScopeBinding:
    """The agreed POC scope across all layers."""
    region_key: str
    elevation_band: str
    headline_horizon_hours: int
    ensemble_members: int
    track_id: str
    evidence_class: str
    official_warning_eligible: bool
    decision_record_sha256: str
    decision_id: str


def validate_poc_scope_consistency(
    *,
    decision_record: DecisionRecord,
    result_data: dict[str, Any],
    manifest: ArtifactManifest,
    forecast: ForecastSemanticsContract,
    expected_decision_record_sha256: str,
    poc_mode: bool,
) -> PocScopeBinding:
    """Cross-validate all POC layers for exact semantic agreement.

    C0.1: Bind decision record, result, artifact manifest, and forecast semantics.
    C0.2: Require exact 48h agreement at the consumer boundary.
    C0.3: Require ensemble_members == 1 for the POC headline path.
    C0.8: Require explicit top-level identity fields; no fallback to nested binding.

    G1: poc_mode is MANDATORY — no default. Callers must explicitly declare
    POC or non-POC mode. This prevents accidental POC semantics inheritance.

    Returns the agreed PocScopeBinding on success.
    Raises PocScopeError on any inconsistency.
    """
    errors: list[str] = []

    # A5: Guard against non-dict result_data — result_data.get() raises
    # AttributeError for None/list/str inputs.
    if not isinstance(result_data, dict):
        raise PocScopeError(
            f'result_data must be a dict, got '
            f'{type(result_data).__name__}: {result_data!r}'
        )
    # G4: Require exact type instances — not just non-None. Passing a list,
    # dict, or generic object would raise raw AttributeError on attribute
    # access. Use isinstance for dataclass subclasses, but reject wrong types.
    if not isinstance(decision_record, DecisionRecord):
        raise PocScopeError(
            f'decision_record must be a DecisionRecord, got '
            f'{type(decision_record).__name__}: {decision_record!r}'
        )
    if not isinstance(manifest, ArtifactManifest):
        raise PocScopeError(
            f'manifest must be an ArtifactManifest, got '
            f'{type(manifest).__name__}: {manifest!r}'
        )
    if not isinstance(forecast, ForecastSemanticsContract):
        raise PocScopeError(
            f'forecast must be a ForecastSemanticsContract, got '
            f'{type(forecast).__name__}: {forecast!r}'
        )
    # G3: Require exact bool type for poc_mode — reject int 1, string "true",
    # or any other truthy value. type() is used instead of isinstance() because
    # isinstance(1, bool) is False but isinstance(True, int) is True.
    if type(poc_mode) is not bool:
        raise PocScopeError(
            f'poc_mode must be a bool, got '
            f'{type(poc_mode).__name__}: {poc_mode!r}'
        )
    # A3: Type-check expected_decision_record_sha256 before string methods.
    if not isinstance(expected_decision_record_sha256, str):
        raise PocScopeError(
            f'expected_decision_record_sha256 must be a string, got '
            f'{type(expected_decision_record_sha256).__name__}: '
            f'{expected_decision_record_sha256!r}'
        )

    # C0.8: Require explicit top-level region_key and elevation_band in result.json.
    # Do NOT fall back to values from the nested decision_record binding.
    # P3/G10: Require string types — do not str()-coerce non-string values.
    raw_result_region = result_data.get('region_key')
    if raw_result_region is not None and not isinstance(raw_result_region, str):
        errors.append(
            f'result.json region_key must be a string, got '
            f'{type(raw_result_region).__name__}: {raw_result_region!r}'
        )
        result_region = ''
    else:
        result_region = (raw_result_region or '').strip()
    raw_result_band = result_data.get('elevation_band')
    if raw_result_band is not None and not isinstance(raw_result_band, str):
        errors.append(
            f'result.json elevation_band must be a string, got '
            f'{type(raw_result_band).__name__}: {raw_result_band!r}'
        )
        result_band = ''
    else:
        result_band = (raw_result_band or '').strip()
    if not result_region:
        errors.append('result.json must have explicit top-level region_key (no fallback)')
    if not result_band:
        errors.append('result.json must have explicit top-level elevation_band (no fallback)')

    # C0.1: Require decision_record binding in result.json with exact fields
    dr_binding = result_data.get('decision_record')
    if not isinstance(dr_binding, dict):
        errors.append('result.json must contain a decision_record binding object')
        dr_binding = {}

    # P3/G10: Require string types for all binding fields — no str() coercion.
    def _require_str(binding: dict, field: str) -> str:
        """Extract a string field from binding, rejecting non-string types."""
        raw = binding.get(field)
        if raw is None:
            return ''
        if not isinstance(raw, str):
            errors.append(
                f'result.json decision_record.{field} must be a string, got '
                f'{type(raw).__name__}: {raw!r}'
            )
            return ''
        return raw.strip()

    binding_sha = _require_str(dr_binding, 'decision_record_sha256')
    binding_decision_id = _require_str(dr_binding, 'decision_id')
    binding_track_id = _require_str(dr_binding, 'track_id')
    binding_evidence_class = _require_str(dr_binding, 'evidence_class')
    binding_official_warning = dr_binding.get('official_warning_eligible')
    binding_horizon = dr_binding.get('headline_horizon_hours')
    binding_ensemble = dr_binding.get('ensemble_members')
    binding_sector = _require_str(dr_binding, 'selected_sector')
    binding_band = _require_str(dr_binding, 'elevation_band')

    if not binding_sha:
        errors.append('result.json decision_record.decision_record_sha256 is required')
    if not binding_decision_id:
        errors.append('result.json decision_record.decision_id is required')
    if not binding_track_id:
        errors.append('result.json decision_record.track_id is required')
    if not binding_evidence_class:
        errors.append('result.json decision_record.evidence_class is required')
    if binding_official_warning is None:
        errors.append('result.json decision_record.official_warning_eligible is required')
    elif not isinstance(binding_official_warning, bool):
        # C0.8: Reject non-boolean types — Python bool(0) == False and
        # bool("false") == True, so we must check the type explicitly to
        # prevent int 0 from being silently accepted as JSON false.
        errors.append(
            f'result.json decision_record.official_warning_eligible must be a '
            f'boolean, got {type(binding_official_warning).__name__}: '
            f'{binding_official_warning!r}'
        )
    if binding_horizon is None:
        errors.append('result.json decision_record.headline_horizon_hours is required')
    elif type(binding_horizon) is not int:
        # P0-5: Reject bool, float, string, and other non-int types.
        # int(48.5) = 48 creates false agreement; int(True) = 1 creates false agreement.
        # bool is a subclass of int in Python, so type(True) is not int is True.
        errors.append(
            f'result.json decision_record.headline_horizon_hours must be an exact '
            f'integer (type int), got {type(binding_horizon).__name__}: '
            f'{binding_horizon!r}'
        )
    if binding_ensemble is None:
        errors.append('result.json decision_record.ensemble_members is required')
    elif type(binding_ensemble) is not int:
        # P0-5: Reject bool, float, string, and other non-int types.
        errors.append(
            f'result.json decision_record.ensemble_members must be an exact '
            f'integer (type int), got {type(binding_ensemble).__name__}: '
            f'{binding_ensemble!r}'
        )
    if not binding_sector:
        errors.append('result.json decision_record.selected_sector is required')
    if not binding_band:
        errors.append('result.json decision_record.elevation_band is required')

    # C0.1: Decision record SHA-256 = external digest = bundled hash
    # P1/G6: Type-check expected_decision_record_sha256 before calling .lower().
    if not isinstance(expected_decision_record_sha256, str):
        errors.append(
            f'expected_decision_record_sha256 must be a string, got '
            f'{type(expected_decision_record_sha256).__name__}: '
            f'{expected_decision_record_sha256!r}'
        )
    elif binding_sha and binding_sha.lower() != expected_decision_record_sha256.lower():
        errors.append(
            f'result.json decision_record_sha256 ({binding_sha!r}) does not match '
            f'external expected digest ({expected_decision_record_sha256!r})'
        )
    if binding_sha and binding_sha.lower() != decision_record.decision_record_sha256.lower():
        errors.append(
            f'result.json decision_record_sha256 ({binding_sha!r}) does not match '
            f'decision record actual hash ({decision_record.decision_record_sha256!r})'
        )

    # C0.1: Exact equality across all layers
    # Layer 1: Decision record
    dr_sector = decision_record.selected_sector
    dr_band = decision_record.elevation_band
    dr_horizon = decision_record.headline_horizon_hours
    dr_ensemble = decision_record.ensemble_members
    dr_track = decision_record.track_id
    dr_evidence = decision_record.evidence_class
    dr_warning = decision_record.official_warning_eligible
    dr_id = decision_record.decision_id

    # Layer 2: result.json top-level
    if result_region and result_region != dr_sector:
        errors.append(
            f'result.json region_key ({result_region!r}) != decision record '
            f'selected_sector ({dr_sector!r})'
        )
    if result_band and result_band != dr_band:
        errors.append(
            f'result.json elevation_band ({result_band!r}) != decision record '
            f'elevation_band ({dr_band!r})'
        )

    # Layer 2b: result.json decision_record binding
    if binding_sector and binding_sector != dr_sector:
        errors.append(
            f'result.json decision_record.selected_sector ({binding_sector!r}) != '
            f'decision record selected_sector ({dr_sector!r})'
        )
    if binding_band and binding_band != dr_band:
        errors.append(
            f'result.json decision_record.elevation_band ({binding_band!r}) != '
            f'decision record elevation_band ({dr_band!r})'
        )
    if binding_horizon is not None:
        # P1/G1: Strict type check — int() is a conversion function, not a
        # type guard. int(48.5)=48, int("48")=48, int(True)=1 all silently
        # pass. We require type(value) is int at the JSON boundary.
        if type(binding_horizon) is not int:
            errors.append(
                f'result.json decision_record.headline_horizon_hours must be '
                f'an exact integer (type int), got {type(binding_horizon).__name__}: '
                f'{binding_horizon!r}'
            )
            binding_horizon_int = None
        else:
            binding_horizon_int = binding_horizon
        if binding_horizon_int is not None and binding_horizon_int != dr_horizon:
            errors.append(
                f'result.json decision_record.headline_horizon_hours ({binding_horizon_int!r}) != '
                f'decision record headline_horizon_hours ({dr_horizon!r})'
            )
    if binding_ensemble is not None:
        # P1/G1: Same strict type check for ensemble_members.
        if type(binding_ensemble) is not int:
            errors.append(
                f'result.json decision_record.ensemble_members must be '
                f'an exact integer (type int), got {type(binding_ensemble).__name__}: '
                f'{binding_ensemble!r}'
            )
            binding_ensemble_int = None
        else:
            binding_ensemble_int = binding_ensemble
        if binding_ensemble_int is not None and binding_ensemble_int != dr_ensemble:
            errors.append(
                f'result.json decision_record.ensemble_members ({binding_ensemble_int!r}) != '
                f'decision record ensemble_members ({dr_ensemble!r})'
            )
    if binding_track_id and binding_track_id != dr_track:
        errors.append(
            f'result.json decision_record.track_id ({binding_track_id!r}) != '
            f'decision record track_id ({dr_track!r})'
        )
    if binding_evidence_class and binding_evidence_class != dr_evidence:
        errors.append(
            f'result.json decision_record.evidence_class ({binding_evidence_class!r}) != '
            f'decision record evidence_class ({dr_evidence!r})'
        )
    if binding_decision_id and binding_decision_id != dr_id:
        errors.append(
            f'result.json decision_record.decision_id ({binding_decision_id!r}) != '
            f'decision record decision_id ({dr_id!r})'
        )
    if binding_official_warning is not None and isinstance(binding_official_warning, bool) and binding_official_warning != dr_warning:
        errors.append(
            f'result.json decision_record.official_warning_eligible '
            f'({binding_official_warning!r}) != decision record ({dr_warning!r})'
        )

    # Layer 3: artifact manifest
    # P1/G6: Require strict string types — do not str()-coerce non-string values.
    raw_manifest_region = manifest.region_key
    if raw_manifest_region is None:
        manifest_region = ''
    elif not isinstance(raw_manifest_region, str):
        errors.append(
            f'manifest region_key must be a string, got '
            f'{type(raw_manifest_region).__name__}: {raw_manifest_region!r}'
        )
        manifest_region = ''
    else:
        manifest_region = raw_manifest_region.strip()
    raw_manifest_band = manifest.elevation_band
    if raw_manifest_band is None:
        manifest_band = ''
    elif not isinstance(raw_manifest_band, str):
        errors.append(
            f'manifest elevation_band must be a string, got '
            f'{type(raw_manifest_band).__name__}: {raw_manifest_band!r}'
        )
        manifest_band = ''
    else:
        manifest_band = raw_manifest_band.strip()
    if manifest_region and manifest_region != dr_sector:
        errors.append(
            f'manifest.json region_key ({manifest_region!r}) != decision record '
            f'selected_sector ({dr_sector!r})'
        )
    if manifest_band and manifest_band != dr_band:
        errors.append(
            f'manifest.json elevation_band ({manifest_band!r}) != decision record '
            f'elevation_band ({dr_band!r})'
        )
    if manifest_region and result_region and manifest_region != result_region:
        errors.append(
            f'manifest.json region_key ({manifest_region!r}) != result.json '
            f'region_key ({result_region!r})'
        )
    if manifest_band and result_band and manifest_band != result_band:
        errors.append(
            f'manifest.json elevation_band ({manifest_band!r}) != result.json '
            f'elevation_band ({result_band!r})'
        )

    # Layer 4: forecast semantics
    # P1/G6: Require strict string types — do not str()-coerce non-string values.
    raw_fs_region = forecast.region_key
    if raw_fs_region is None:
        fs_region = ''
    elif not isinstance(raw_fs_region, str):
        errors.append(
            f'forecast semantics region_key must be a string, got '
            f'{type(raw_fs_region).__name__}: {raw_fs_region!r}'
        )
        fs_region = ''
    else:
        fs_region = raw_fs_region.strip()
    raw_fs_band = forecast.elevation_band
    if raw_fs_band is None:
        fs_band = ''
    elif not isinstance(raw_fs_band, str):
        errors.append(
            f'forecast semantics elevation_band must be a string, got '
            f'{type(raw_fs_band).__name__}: {raw_fs_band!r}'
        )
        fs_band = ''
    else:
        fs_band = raw_fs_band.strip()
    fs_lead_time = forecast.lead_time_h
    fs_ensemble = forecast.ensemble_members
    if fs_region and fs_region != dr_sector:
        errors.append(
            f'forecast semantics region_key ({fs_region!r}) != decision record '
            f'selected_sector ({dr_sector!r})'
        )
    if fs_band and fs_band != dr_band:
        errors.append(
            f'forecast semantics elevation_band ({fs_band!r}) != decision record '
            f'elevation_band ({dr_band!r})'
        )
    # C0.2: Require exact 48h agreement at the consumer boundary.
    # P3/G11: In POC mode, require lead_time_h to be an exact integer (48),
    # not a float (48.0). General non-POC forecasts may support fractional
    # lead times, but the POC contract is strict.
    if isinstance(fs_lead_time, bool) or not isinstance(fs_lead_time, (int, float)):
        errors.append(
            f'forecast semantics lead_time_h must be a number, '
            f'got {type(fs_lead_time).__name__}: {fs_lead_time!r}'
        )
    elif poc_mode and type(fs_lead_time) is not int:
        errors.append(
            f'POC forecast semantics lead_time_h must be an exact integer, '
            f'got {type(fs_lead_time).__name__}: {fs_lead_time!r}'
        )
    elif fs_lead_time != dr_horizon:
        errors.append(
            f'forecast semantics lead_time_h ({fs_lead_time!r}) != decision record '
            f'headline_horizon_hours ({dr_horizon!r})'
        )
    # C0.3: Require ensemble_members == 1 for POC headline.
    # P0-5: Do not use int() coercion — require exact int type.
    if type(fs_ensemble) is not int:
        errors.append(
            f'forecast semantics ensemble_members must be an exact integer '
            f'(type int), got {type(fs_ensemble).__name__}: {fs_ensemble!r}'
        )
    elif fs_ensemble != dr_ensemble:
        errors.append(
            f'forecast semantics ensemble_members ({fs_ensemble!r}) != decision record '
            f'ensemble_members ({dr_ensemble!r})'
        )
    if poc_mode and dr_ensemble != 1:
        errors.append(
            f'POC headline path requires ensemble_members == 1, got {dr_ensemble!r}'
        )
    if poc_mode and dr_horizon != 48:
        errors.append(
            f'POC headline path requires headline_horizon_hours == 48, got {dr_horizon!r}'
        )

    # C0.1: POC-specific invariant checks
    if dr_evidence != 'pipeline-proof-only':
        errors.append(
            f'evidence_class must be "pipeline-proof-only", got {dr_evidence!r}'
        )
    if dr_warning is not False:
        errors.append(
            f'official_warning_eligible must be false, got {dr_warning!r}'
        )
    if dr_track != 'track_1_indian_candidate':
        errors.append(
            f'track_id must be "track_1_indian_candidate", got {dr_track!r}'
        )

    if errors:
        raise PocScopeError(
            'POC scope consistency validation failed:\n  - ' + '\n  - '.join(errors)
        )

    return PocScopeBinding(
        region_key=dr_sector,
        elevation_band=dr_band,
        headline_horizon_hours=dr_horizon,
        ensemble_members=dr_ensemble,
        track_id=dr_track,
        evidence_class=dr_evidence,
        official_warning_eligible=dr_warning,
        decision_record_sha256=decision_record.decision_record_sha256,
        decision_id=dr_id,
    )


def derive_poc_scope_from_decision_record(
    decision_record_path: str,
    expected_sha256: str,
) -> PocScopeBinding:
    """C0.6: Single strict scope-derivation helper for use in preflight,
    producer, and gate. Loads the decision record, verifies its hash, and
    returns the POC scope binding.

    This is the one helper that should be used everywhere the POC scope
    needs to be derived from the decision record.
    """
    from pathlib import Path
    from backend.common.pir_panjal_decision_record import load_decision_record
    dr = load_decision_record(Path(decision_record_path), expected_sha256=expected_sha256)
    return PocScopeBinding(
        region_key=dr.selected_sector,
        elevation_band=dr.elevation_band,
        headline_horizon_hours=dr.headline_horizon_hours,
        ensemble_members=dr.ensemble_members,
        track_id=dr.track_id,
        evidence_class=dr.evidence_class,
        official_warning_eligible=dr.official_warning_eligible,
        decision_record_sha256=dr.decision_record_sha256,
        decision_id=dr.decision_id,
    )
