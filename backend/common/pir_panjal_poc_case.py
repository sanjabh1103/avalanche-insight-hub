"""Candidate-only case contract for the Pir Panjal POC vertical slice.

This module records one reproducible site/event selection without promoting
it to an approved geometry, forcing source, or scientific label.  The case is
intended to make the next native execution concrete while keeping every
external approval boundary explicit.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


_SCHEMA_VERSION = "pir_panjal_poc_case_v1"
_REGION_KEY = "pir_panjal_nw_himalaya"
_ELEVATION_BAND = "middle"
_ELEVATION_MIN_M = 3200
_ELEVATION_MAX_M = 4000
_HORIZON_HOURS = 48
_ENSEMBLE_MEMBERS = 1
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class PirPanjalPocCaseError(ValueError):
    """Raised when a candidate POC case is malformed or unsafe."""


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PirPanjalPocCaseError(f"{field} must be a non-empty string")
    return value.strip()


def _exact_int(value: Any, field: str) -> int:
    if type(value) is not int:
        raise PirPanjalPocCaseError(f"{field} must be an exact integer")
    return value


def _exact_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise PirPanjalPocCaseError(f"{field} must be an exact boolean")
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PirPanjalPocCaseError(f"{field} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise PirPanjalPocCaseError(f"{field} must be finite")
    return converted


def _sha256_field(value: Any, field: str) -> str:
    result = _required_string(value, field)
    if not _SHA256.fullmatch(result):
        raise PirPanjalPocCaseError(f"{field} must be a SHA-256 digest")
    return result.lower()


def _utc(value: Any, field: str) -> datetime:
    raw = _required_string(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PirPanjalPocCaseError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise PirPanjalPocCaseError(f"{field} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _safe_relative_path(value: Any, field: str) -> Path:
    raw = _required_string(value, field)
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or "\\" in raw or "\x00" in raw:
        raise PirPanjalPocCaseError(f"{field} must be a safe relative path")
    return path


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PirPanjalPocCaseError(f"{field} must be an object")
    return value


def _validate_file_bindings(
    bindings: Mapping[str, Any],
    *,
    repository_root: Path,
) -> None:
    root = repository_root.resolve()
    for field, value in bindings.items():
        relative_path = _safe_relative_path(value["path"], f"{field}.path")
        candidate = repository_root / relative_path
        try:
            candidate.resolve().relative_to(root)
        except ValueError as exc:
            raise PirPanjalPocCaseError(f"{field}.path escapes repository root") from exc
        if candidate.is_symlink() or not candidate.is_file():
            raise PirPanjalPocCaseError(f"{field}.path is not a regular file")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        expected = _sha256_field(value["sha256"], f"{field}.sha256")
        if actual != expected:
            raise PirPanjalPocCaseError(
                f"{field}.sha256 mismatch: expected={expected}, actual={actual}"
            )


@dataclass(frozen=True)
class PirPanjalPocCase:
    """Validated candidate case; never an approval or accuracy label."""

    case_id: str
    region_key: str
    elevation_band: str
    horizon_hours: int
    ensemble_members: int
    site: Mapping[str, Any]
    event: Mapping[str, Any]
    forcing: Mapping[str, Any]
    initial_state: Mapping[str, Any]
    raw_bytes: bytes
    manifest_sha256: str

    @property
    def native_execution_allowed(self) -> bool:
        """Candidate records never unlock native release by themselves."""

        return False


def validate_pir_panjal_forcing_consistency(
    case: PirPanjalPocCase,
    forcing_manifest: Mapping[str, Any],
) -> None:
    """Fail closed when a forcing package drifts from the canonical case.

    The forcing producer and native runner must agree on the same case scope,
    source/model identity, forecast role, target geometry, spin-up interval,
    and initial-state manifest.  This validator intentionally does not choose
    the source or alter either manifest; a mismatch requires a rebuild or an
    explicit governance decision.
    """

    if not isinstance(case, PirPanjalPocCase):
        raise PirPanjalPocCaseError(
            f"case must be a PirPanjalPocCase, got {type(case).__name__}"
        )
    if not isinstance(forcing_manifest, dict):
        raise PirPanjalPocCaseError("forcing manifest must be a JSON object")

    errors: list[str] = []

    def compare(path: str, expected: Any, actual: Any) -> None:
        if actual != expected:
            errors.append(f"{path} mismatch: expected={expected!r}, actual={actual!r}")

    for field, expected in (
        ("case_id", case.case_id),
        ("region_key", case.region_key),
        ("elevation_band", case.elevation_band),
        ("horizon_hours", case.horizon_hours),
        ("ensemble_members", case.ensemble_members),
    ):
        compare(f"forcing.{field}", expected, forcing_manifest.get(field))

    case_forcing = case.forcing
    for field in (
        "source_id",
        "model_id",
        "forecast_role",
        "license_review_status",
        "target_resolution_m",
        "source_native_resolution_m",
        "effective_information_scale_m",
        "no_3km_skill_claim",
    ):
        expected = case_forcing.get(field)
        if expected is not None:
            compare(f"forcing.{field}", expected, forcing_manifest.get(field))

    expected_site = dict(case.site)
    actual_site = forcing_manifest.get("target_site")
    if not isinstance(actual_site, dict):
        errors.append("forcing.target_site must be an object")
    else:
        compare("forcing.target_site", expected_site, actual_site)

    initial_state = case.initial_state
    evaluation_window = _mapping(
        json.loads(case.raw_bytes.decode("utf-8")).get("evaluation_window"),
        "evaluation_window",
    )
    for field, expected in (
        ("valid_from", initial_state.get("start")),
        ("valid_to", evaluation_window.get("end")),
        ("initial_state_manifest_sha256", initial_state.get("manifest_sha256")),
    ):
        compare(f"forcing.{field}", expected, forcing_manifest.get(field))

    start = _utc(initial_state.get("start"), "initial_state.start")
    end = _utc(evaluation_window.get("end"), "evaluation_window.end")
    expected_samples = int((end - start).total_seconds() // 3600)
    sample_count = forcing_manifest.get("sample_count")
    if type(sample_count) is not int or sample_count != expected_samples:
        errors.append(
            "forcing.sample_count mismatch: "
            f"expected={expected_samples!r}, actual={sample_count!r}"
        )

    warmup_hours = forcing_manifest.get("warmup_hours", 0)
    if type(warmup_hours) is not int or warmup_hours < 0:
        errors.append("forcing.warmup_hours must be a non-negative exact integer")
        warmup_hours = 0
    expected_source_start = start - timedelta(hours=warmup_hours)
    expected_source_start_text = expected_source_start.isoformat().replace("+00:00", "Z")
    expected_source_samples = expected_samples + warmup_hours
    source_window = forcing_manifest.get("source_window")
    source_sample_count = forcing_manifest.get("source_sample_count", sample_count)
    if warmup_hours:
        if not isinstance(source_window, dict):
            errors.append("forcing.source_window must be an object when warmup is present")
        else:
            compare("forcing.source_window.start", expected_source_start_text, source_window.get("start"))
            compare("forcing.source_window.end", evaluation_window.get("end"), source_window.get("end"))
        if type(source_sample_count) is not int or source_sample_count != expected_source_samples:
            errors.append(
                "forcing.source_sample_count mismatch: "
                f"expected={expected_source_samples!r}, actual={source_sample_count!r}"
            )

    if forcing_manifest.get("production_eligible") is not False:
        errors.append("forcing.production_eligible must be boolean false for a candidate case")
    if forcing_manifest.get("native_execution_ready") is not False:
        errors.append("forcing.native_execution_ready must be boolean false before approval")

    if errors:
        raise PirPanjalPocCaseError(
            "forcing manifest is inconsistent with canonical Pir Panjal case: "
            + "; ".join(errors)
        )


def _validate_record(
    record: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    if _required_string(record.get("schema_version"), "schema_version") != _SCHEMA_VERSION:
        raise PirPanjalPocCaseError(f"schema_version must be {_SCHEMA_VERSION}")
    case_id = _required_string(record.get("case_id"), "case_id")
    if _required_string(record.get("region_key"), "region_key") != _REGION_KEY:
        raise PirPanjalPocCaseError(f"region_key must be {_REGION_KEY}")
    if _required_string(record.get("elevation_band"), "elevation_band") != _ELEVATION_BAND:
        raise PirPanjalPocCaseError(f"elevation_band must be {_ELEVATION_BAND}")
    if _exact_int(record.get("elevation_min_m"), "elevation_min_m") != _ELEVATION_MIN_M:
        raise PirPanjalPocCaseError("elevation_min_m does not match frozen POC scope")
    if _exact_int(record.get("elevation_max_m"), "elevation_max_m") != _ELEVATION_MAX_M:
        raise PirPanjalPocCaseError("elevation_max_m does not match frozen POC scope")
    if _exact_int(record.get("horizon_hours"), "horizon_hours") != _HORIZON_HOURS:
        raise PirPanjalPocCaseError("horizon_hours does not match frozen POC scope")
    if _exact_int(record.get("ensemble_members"), "ensemble_members") != _ENSEMBLE_MEMBERS:
        raise PirPanjalPocCaseError("ensemble_members does not match frozen POC scope")
    if _required_string(record.get("case_status"), "case_status") != "retrospective_candidate":
        raise PirPanjalPocCaseError("case_status must be retrospective_candidate")
    if _required_string(record.get("evidence_class"), "evidence_class") != "pipeline-proof-only":
        raise PirPanjalPocCaseError("evidence_class must be pipeline-proof-only")
    if _exact_bool(record.get("approved"), "approved"):
        raise PirPanjalPocCaseError("candidate case cannot be approved")
    if _exact_bool(record.get("official_warning_eligible"), "official_warning_eligible"):
        raise PirPanjalPocCaseError("candidate case cannot be warning-eligible")
    if _exact_bool(record.get("scientific_validation_eligible"), "scientific_validation_eligible"):
        raise PirPanjalPocCaseError("candidate case cannot be scientific-validation eligible")

    site = _mapping(record.get("site"), "site")
    _required_string(site.get("site_id"), "site.site_id")
    geometry_status = _required_string(site.get("geometry_status"), "site.geometry_status")
    if geometry_status not in {"candidate_fixture", "derived_candidate"}:
        raise PirPanjalPocCaseError(
            "site.geometry_status must be candidate_fixture or derived_candidate"
        )
    if _required_string(site.get("approval_state"), "site.approval_state") != "candidate_only":
        raise PirPanjalPocCaseError("site.approval_state must be candidate_only")
    if _exact_bool(site.get("approved"), "site.approved"):
        raise PirPanjalPocCaseError("site.approved must be false")
    latitude = _finite_number(site.get("latitude"), "site.latitude")
    longitude = _finite_number(site.get("longitude"), "site.longitude")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise PirPanjalPocCaseError("site coordinates are outside valid bounds")
    dem_elevation = _finite_number(site.get("dem_elevation_m"), "site.dem_elevation_m")
    if not _ELEVATION_MIN_M <= dem_elevation <= _ELEVATION_MAX_M:
        raise PirPanjalPocCaseError("site.dem_elevation_m is outside the frozen middle band")
    slope = _finite_number(site.get("slope_deg"), "site.slope_deg")
    aspect = _finite_number(site.get("aspect_deg"), "site.aspect_deg")
    if not 0 <= slope <= 90 or not 0 <= aspect <= 360:
        raise PirPanjalPocCaseError("site slope/aspect is outside valid bounds")
    source_point_index = _exact_int(site.get("source_point_index"), "site.source_point_index")
    if source_point_index < 0:
        raise PirPanjalPocCaseError("site.source_point_index must be non-negative")
    _finite_number(site.get("source_elevation_m"), "site.source_elevation_m")
    _finite_number(site.get("site_to_source_point_km"), "site.site_to_source_point_km")

    event = _mapping(record.get("primary_event"), "primary_event")
    _required_string(event.get("event_id"), "primary_event.event_id")
    if _required_string(event.get("source"), "primary_event.source") != "HiAVAL":
        raise PirPanjalPocCaseError("primary event source must be HiAVAL")
    if _required_string(event.get("timestamp_precision"), "primary_event.timestamp_precision") != "day":
        raise PirPanjalPocCaseError("primary event must retain day precision")
    if _required_string(event.get("rights"), "primary_event.rights") != "CC BY 4.0":
        raise PirPanjalPocCaseError("primary event rights must remain CC BY 4.0")
    if _required_string(event.get("rights_status"), "primary_event.rights_status") != "research_only":
        raise PirPanjalPocCaseError("primary event rights status must remain research_only")
    if _exact_bool(event.get("site_specific_validation"), "primary_event.site_specific_validation"):
        raise PirPanjalPocCaseError("primary event cannot be site-specific validation")
    if _exact_bool(event.get("is_accuracy_label"), "primary_event.is_accuracy_label"):
        raise PirPanjalPocCaseError("primary event cannot be used as an accuracy label")
    event_start = _utc(event.get("event_time_start"), "primary_event.event_time_start")
    event_end = _utc(event.get("event_time_end"), "primary_event.event_time_end")
    if event_end <= event_start:
        raise PirPanjalPocCaseError("primary event end must follow its start")
    _sha256_field(event.get("source_row_sha256"), "primary_event.source_row_sha256")
    _finite_number(event.get("distance_from_site_km"), "primary_event.distance_from_site_km")

    window = _mapping(record.get("evaluation_window"), "evaluation_window")
    window_start = _utc(window.get("start"), "evaluation_window.start")
    window_end = _utc(window.get("end"), "evaluation_window.end")
    if (window_end - window_start).total_seconds() != _HORIZON_HOURS * 3600:
        raise PirPanjalPocCaseError("evaluation window must be exactly 48 hours")
    if event_end <= window_start or event_start >= window_end:
        raise PirPanjalPocCaseError("primary event must overlap the evaluation window")

    forcing = _mapping(record.get("forcing"), "forcing")
    if _required_string(forcing.get("status"), "forcing.status") != "candidate_fixture":
        raise PirPanjalPocCaseError("forcing.status must be candidate_fixture")
    if _required_string(forcing.get("license_review_status"), "forcing.license_review_status") != "pending":
        raise PirPanjalPocCaseError("forcing license review must remain pending")
    for name in ("snapshot_manifest", "raw_source_points"):
        item = _mapping(forcing.get(name), f"forcing.{name}")
        _safe_relative_path(item.get("path"), f"forcing.{name}.path")
        _sha256_field(item.get("sha256"), f"forcing.{name}.sha256")
    _required_string(forcing.get("source_id"), "forcing.source_id")
    _required_string(forcing.get("model_id"), "forcing.model_id")

    initial_state = _mapping(record.get("initial_state"), "initial_state")
    if _required_string(initial_state.get("strategy"), "initial_state.strategy") != "early_season_spinup":
        raise PirPanjalPocCaseError("initial_state.strategy must be early_season_spinup")
    if _required_string(initial_state.get("status"), "initial_state.status") != "candidate_assumption":
        raise PirPanjalPocCaseError("initial_state.status must be candidate_assumption")
    if _exact_bool(initial_state.get("approved"), "initial_state.approved"):
        raise PirPanjalPocCaseError("initial_state.approved must be false")
    initial_start = _utc(initial_state.get("start"), "initial_state.start")
    if initial_start >= window_start:
        raise PirPanjalPocCaseError("initial-state spin-up must start before the evaluation window")
    if "manifest_path" in initial_state or "manifest_sha256" in initial_state:
        _safe_relative_path(initial_state.get("manifest_path"), "initial_state.manifest_path")
        _sha256_field(initial_state.get("manifest_sha256"), "initial_state.manifest_sha256")

    files = _mapping(record.get("file_bindings"), "file_bindings")
    for name in ("snapshot_manifest", "raw_source_points", "dem_tile", "event_inventory"):
        item = _mapping(files.get(name), f"file_bindings.{name}")
        _safe_relative_path(item.get("path"), f"file_bindings.{name}.path")
        _sha256_field(item.get("sha256"), f"file_bindings.{name}.sha256")
    return site, event, forcing, initial_state, files


def validate_pir_panjal_poc_case_bytes(raw_bytes: bytes) -> PirPanjalPocCase:
    """Validate already-read UTF-8 JSON bytes without a second filesystem read."""

    if not isinstance(raw_bytes, bytes):
        raise PirPanjalPocCaseError("case manifest bytes must be bytes")
    manifest_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        record = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise PirPanjalPocCaseError(f"case manifest is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PirPanjalPocCaseError(f"case manifest is not valid JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise PirPanjalPocCaseError("case manifest must be a JSON object")
    site, event, forcing, initial_state, _ = _validate_record(record)
    return PirPanjalPocCase(
        case_id=_required_string(record.get("case_id"), "case_id"),
        region_key=_REGION_KEY,
        elevation_band=_ELEVATION_BAND,
        horizon_hours=_HORIZON_HOURS,
        ensemble_members=_ENSEMBLE_MEMBERS,
        site=site,
        event=event,
        forcing=forcing,
        initial_state=initial_state,
        raw_bytes=raw_bytes,
        manifest_sha256=manifest_sha256,
    )


def load_pir_panjal_poc_case(
    path: Path | str,
    *,
    repository_root: Path | str | None = None,
    verify_files: bool = False,
) -> PirPanjalPocCase:
    """Load the candidate case once and optionally verify all bound files."""

    manifest_path = Path(path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PirPanjalPocCaseError(f"case manifest is not a regular file: {manifest_path}")
    case = validate_pir_panjal_poc_case_bytes(manifest_path.read_bytes())
    if verify_files:
        root = Path(repository_root) if repository_root is not None else manifest_path.parents[2]
        record = json.loads(case.raw_bytes.decode("utf-8"))
        _validate_file_bindings(record["file_bindings"], repository_root=root)
    return case
