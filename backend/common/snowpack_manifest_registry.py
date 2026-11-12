"""Approved SNOWPACK input/toolchain manifest resolver.

Release mode must resolve forcing, geometry, and toolchain IDs through one
allowlisted registry. Unknown IDs, placeholders, missing metadata, unapproved
records, and content-hash mismatches fail closed.

The default registry is intentionally absent until the operator supplies
approved external manifests. Synthetic fixtures must not be registered as
release inputs.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.regions import repo_root
from backend.common.snowpack_contracts import validate_release_manifest_id


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_FIELDS = (
    "id",
    "kind",
    "content_sha256",
    "source",
    "licence",
    "units",
    "region",
    "elevation_band",
    "valid_from",
    "valid_to",
    "approval_state",
    "manifest_path",
)
_APPROVAL_VALIDITY_FIELDS = ("approval_valid_from", "approval_valid_to")
_VALID_KINDS = frozenset({"forcing", "geometry", "toolchain"})

DEFAULT_REGISTRY_PATH = repo_root() / "config" / "snowpack_manifest_registry.json"


class ManifestRegistryError(ValueError):
    """Raised when the approved SNOWPACK manifest registry is invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_manifest_path(registry_path: Path, manifest_path: str) -> Path:
    """Resolve a registry-relative manifest path without traversal/symlinks."""
    candidate = Path(manifest_path)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in manifest_path:
        raise ManifestRegistryError(
            f"manifest_path must be a relative POSIX path without traversal: {manifest_path!r}"
        )
    original = registry_path.parent / candidate
    if original.is_symlink():
        raise ManifestRegistryError(f"manifest_path must not be a symlink: {manifest_path!r}")
    current = original.parent
    registry_parent = registry_path.parent
    while current != registry_parent:
        if current.is_symlink():
            raise ManifestRegistryError(
                f"manifest_path has a symlinked parent: {manifest_path!r}"
            )
        if current == current.parent:
            break
        current = current.parent
    resolved = original.resolve(strict=True)
    try:
        resolved.relative_to(registry_parent.resolve())
    except ValueError as exc:
        raise ManifestRegistryError(
            f"manifest_path escapes registry directory: {manifest_path!r}"
        ) from exc
    return resolved


def _validate_record(record: Any, *, index: int, registry_path: Path) -> dict[str, str]:
    if not isinstance(record, dict):
        raise ManifestRegistryError(f"registry manifests[{index}] must be an object")

    missing = [field for field in _REQUIRED_FIELDS if field not in record]
    if missing:
        raise ManifestRegistryError(
            f"registry manifests[{index}] missing required fields: {missing}"
        )

    normalized: dict[str, str] = {}
    for field in _REQUIRED_FIELDS:
        value = record[field]
        if not isinstance(value, str) or not value.strip():
            raise ManifestRegistryError(
                f"registry manifests[{index}].{field} must be a non-empty string"
            )
        normalized[field] = value.strip()

    # ``valid_from``/``valid_to`` describe the historical input window.  A
    # retrospective input must not become unusable merely because the
    # operator is executing it later.  When present, the separate approval
    # window governs when this exact record may be executed; both fields are
    # required together and are copied into the snapshot.
    approval_values = {field: record.get(field) for field in _APPROVAL_VALIDITY_FIELDS}
    if any(value is not None for value in approval_values.values()):
        missing_approval = [
            field for field, value in approval_values.items()
            if not isinstance(value, str) or not value.strip()
        ]
        if missing_approval:
            raise ManifestRegistryError(
                f"registry manifests[{index}] approval validity fields must be supplied together: "
                f"{missing_approval}"
            )
        normalized.update({field: str(value).strip() for field, value in approval_values.items()})

    if normalized["kind"] not in _VALID_KINDS:
        raise ManifestRegistryError(
            f"registry manifests[{index}].kind is unsupported: {normalized['kind']!r}"
        )
    try:
        valid_from = datetime.fromisoformat(normalized['valid_from'].replace('Z', '+00:00'))
        valid_to = datetime.fromisoformat(normalized['valid_to'].replace('Z', '+00:00'))
        if valid_from.tzinfo is None or valid_to.tzinfo is None:
            raise ValueError('validity timestamps must be timezone-aware')
        if valid_from > valid_to:
            raise ValueError('valid_from must be <= valid_to')
    except ValueError as exc:
        raise ManifestRegistryError(
            f"registry manifests[{index}] has invalid validity interval: {exc}"
        ) from exc
    if all(field in normalized for field in _APPROVAL_VALIDITY_FIELDS):
        try:
            approval_from = datetime.fromisoformat(
                normalized['approval_valid_from'].replace('Z', '+00:00')
            )
            approval_to = datetime.fromisoformat(
                normalized['approval_valid_to'].replace('Z', '+00:00')
            )
            if approval_from.tzinfo is None or approval_to.tzinfo is None:
                raise ValueError('approval validity timestamps must be timezone-aware')
            if approval_from > approval_to:
                raise ValueError('approval_valid_from must be <= approval_valid_to')
        except ValueError as exc:
            raise ManifestRegistryError(
                f"registry manifests[{index}] has invalid approval validity interval: {exc}"
            ) from exc
    if not _SHA256_RE.fullmatch(normalized["content_sha256"]):
        raise ManifestRegistryError(
            f"registry manifests[{index}].content_sha256 must be SHA-256"
        )
    if normalized["approval_state"] != "approved":
        raise ManifestRegistryError(
            f"registry manifests[{index}] is not approved: {normalized['approval_state']!r}"
        )

    manifest_path = _safe_manifest_path(registry_path, normalized["manifest_path"])
    actual_hash = _sha256_file(manifest_path)
    if actual_hash.lower() != normalized["content_sha256"].lower():
        raise ManifestRegistryError(
            f"registry manifests[{index}] content hash mismatch for {normalized['id']!r}"
        )

    # G0.6: Integrity is not semantic validity. Parse the referenced manifest
    # and require exact agreement with the registry record.
    try:
        referenced = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestRegistryError(
            f"registry manifests[{index}] referenced file is not valid JSON"
        ) from exc
    if not isinstance(referenced, dict):
        raise ManifestRegistryError(
            f"registry manifests[{index}] referenced manifest must be an object"
        )
    semantic_fields = (
        "id", "kind", "source", "licence", "units", "region",
        "elevation_band", "valid_from", "valid_to", "approval_state",
    )
    if any(field in referenced for field in _APPROVAL_VALIDITY_FIELDS) or any(
        field in normalized for field in _APPROVAL_VALIDITY_FIELDS
    ):
        missing_approval = [
            field for field in _APPROVAL_VALIDITY_FIELDS
            if not referenced.get(field)
        ]
        if missing_approval:
            raise ManifestRegistryError(
                f"registry manifests[{index}] referenced manifest missing approval validity fields: "
                f"{missing_approval}"
            )
        semantic_fields += _APPROVAL_VALIDITY_FIELDS
    missing_semantics = [field for field in semantic_fields if not referenced.get(field)]
    if missing_semantics:
        raise ManifestRegistryError(
            f"registry manifests[{index}] referenced manifest missing semantic fields: "
            f"{missing_semantics}"
        )
    for field in semantic_fields:
        if str(referenced[field]) != normalized[field]:
            raise ManifestRegistryError(
                f"registry manifests[{index}] semantic {field} mismatch for "
                f"{normalized['id']!r}"
            )

    if normalized["kind"] in {"forcing", "geometry"}:
        payload_path_value = referenced.get("payload_path")
        payload_sha_value = referenced.get("payload_sha256")
        if not isinstance(payload_path_value, str) or not payload_path_value:
            raise ManifestRegistryError(
                f"registry manifests[{index}] referenced input lacks payload_path"
            )
        if not isinstance(payload_sha_value, str) or not _SHA256_RE.fullmatch(payload_sha_value):
            raise ManifestRegistryError(
                f"registry manifests[{index}] referenced input has invalid payload_sha256"
            )
        payload_path = _safe_manifest_path(registry_path, payload_path_value)
        payload_hash = _sha256_file(payload_path)
        if payload_hash.lower() != payload_sha_value.lower():
            raise ManifestRegistryError(
                f"registry manifests[{index}] payload hash mismatch for {normalized['id']!r}"
            )
        normalized["payload_path"] = payload_path_value
        normalized["payload_sha256"] = payload_sha_value
        normalized["resolved_payload_path"] = str(payload_path)

    # Optional forcing contracts are part of the same hash-verified input
    # boundary. A release may carry the source-to-SNOWPACK mapping and
    # MeteoIO policy alongside the forcing bytes.
    for contract_name in ("mapping_contract", "meteoio_policy"):
        path_field = f"{contract_name}_path"
        hash_field = f"{contract_name}_sha256"
        contract_path_value = referenced.get(path_field)
        contract_hash_value = referenced.get(hash_field)
        if contract_path_value is None and contract_hash_value is None:
            continue
        if (
            not isinstance(contract_path_value, str)
            or not contract_path_value
            or not isinstance(contract_hash_value, str)
            or not _SHA256_RE.fullmatch(contract_hash_value)
        ):
            raise ManifestRegistryError(
                f"registry manifests[{index}] referenced {contract_name} has invalid path/hash"
            )
        contract_path = _safe_manifest_path(registry_path, contract_path_value)
        contract_hash = _sha256_file(contract_path)
        if contract_hash.lower() != contract_hash_value.lower():
            raise ManifestRegistryError(
                f"registry manifests[{index}] {contract_name} hash mismatch for {normalized['id']!r}"
            )
        normalized[path_field] = contract_path_value
        normalized[hash_field] = contract_hash_value
        normalized[f"resolved_{contract_name}_path"] = str(contract_path)

    normalized["resolved_manifest_path"] = str(manifest_path)
    return normalized


def load_approved_payload(record: dict[str, str]) -> dict[str, Any] | list[Any]:
    """Load the hash-verified forcing or geometry payload bytes."""
    kind = record.get("kind")
    if kind not in {"forcing", "geometry"}:
        raise ManifestRegistryError(f"payloads are not supported for kind {kind!r}")
    payload_path = Path(record.get("resolved_payload_path", ""))
    if payload_path.is_symlink() or not payload_path.is_file():
        raise ManifestRegistryError("approved payload is not a regular file")
    actual_hash = _sha256_file(payload_path)
    if actual_hash.lower() != record.get("payload_sha256", "").lower():
        raise ManifestRegistryError("approved payload hash changed after resolution")
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestRegistryError("approved payload must be valid JSON") from exc
    if kind == "forcing":
        if (
            not isinstance(payload, list)
            or not payload
            or not all(isinstance(sample, dict) for sample in payload)
        ):
            raise ManifestRegistryError("forcing payload must be a non-empty list of objects")
        for index, sample in enumerate(payload):
            required = ('time', 'temperature_2m', 'relative_humidity_2m', 'windspeed_10m')
            missing = [field for field in required if sample.get(field) is None]
            has_radiation = any(sample.get(field) is not None for field in (
                'shortwave_radiation', 'net_shortwave_radiation', 'reflected_shortwave_radiation'
            ))
            has_precipitation = any(sample.get(field) is not None for field in (
                'precipitation', 'snowfall', 'snow_depth'
            ))
            if not has_radiation:
                missing.append('radiation')
            if not has_precipitation:
                missing.append('precipitation_or_snow_depth')
            if missing:
                raise ManifestRegistryError(
                    f"forcing payload sample {index} missing required values: {missing}"
                )
            for field, value in sample.items():
                if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                    raise ManifestRegistryError(
                        f"forcing payload sample {index} has non-finite {field}"
                    )
    if kind == "geometry":
        if not isinstance(payload, dict):
            raise ManifestRegistryError("geometry payload must be an object")
        required = ('latitude', 'longitude', 'elevation_m', 'slope_angle', 'aspect', 'crs', 'zone_id', 'dem_sha256')
        missing = [field for field in required if payload.get(field) in (None, '')]
        if missing:
            raise ManifestRegistryError(f"geometry payload missing required fields: {missing}")
        try:
            latitude = float(payload['latitude'])
            longitude = float(payload['longitude'])
            elevation = float(payload['elevation_m'])
            slope = float(payload['slope_angle'])
            aspect = float(payload['aspect'])
        except (TypeError, ValueError) as exc:
            raise ManifestRegistryError('geometry payload has non-numeric coordinates or terrain values') from exc
        if not all(math.isfinite(value) for value in (latitude, longitude, elevation, slope, aspect)):
            raise ManifestRegistryError('geometry payload contains non-finite numeric values')
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ManifestRegistryError('geometry payload coordinates are out of range')
        if not 0 <= slope <= 90 or not 0 <= aspect <= 360:
            raise ManifestRegistryError('geometry payload slope/aspect are out of range')
        if not _SHA256_RE.fullmatch(str(payload['dem_sha256'])):
            raise ManifestRegistryError('geometry payload dem_sha256 must be SHA-256')
    return payload


def load_approved_manifest_registry(
    registry_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Load and hash-verify every approved manifest record."""
    path = Path(registry_path or DEFAULT_REGISTRY_PATH)
    if not path.exists() or path.is_symlink() or not path.is_file():
        raise ManifestRegistryError(
            f"approved SNOWPACK manifest registry is unavailable: {path}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestRegistryError(f"cannot read manifest registry {path}: {exc}") from exc

    if not isinstance(data, dict) or data.get("schema_version") != "snowpack_manifest_registry_v1":
        raise ManifestRegistryError(
            "registry root must be an object with schema_version "
            "snowpack_manifest_registry_v1"
        )
    records = data.get("manifests")
    if not isinstance(records, list) or not records:
        raise ManifestRegistryError("registry manifests must be a non-empty list")

    resolved: dict[str, dict[str, str]] = {}
    payload_paths: set[str] = set()
    for index, record in enumerate(records):
        normalized = _validate_record(record, index=index, registry_path=path)
        manifest_id = normalized["id"]
        if manifest_id in resolved:
            raise ManifestRegistryError(f"duplicate manifest ID: {manifest_id!r}")
        payload_path = normalized.get('resolved_payload_path')
        if payload_path:
            if payload_path in payload_paths:
                raise ManifestRegistryError(
                    f"duplicate forcing/geometry payload reference: {payload_path}"
                )
            payload_paths.add(payload_path)
        resolved[manifest_id] = normalized
    return resolved


def resolve_approved_manifest(
    manifest_id: str,
    *,
    kind: str,
    registry_path: Path | None = None,
    expected_region: str | None = None,
    expected_elevation_band: str | None = None,
) -> dict[str, str]:
    """Resolve one approved, hash-verified manifest and enforce context."""
    try:
        manifest_id = validate_release_manifest_id(manifest_id, field=f'{kind}_manifest_id')
    except ValueError as exc:
        raise ManifestRegistryError(str(exc)) from exc
    if kind not in _VALID_KINDS:
        raise ManifestRegistryError(f"unsupported manifest kind: {kind!r}")

    records = load_approved_manifest_registry(registry_path)
    try:
        record = records[manifest_id]
    except KeyError as exc:
        raise ManifestRegistryError(
            f"unknown or unapproved {kind} manifest ID: {manifest_id!r}"
        ) from exc
    if record["kind"] != kind:
        raise ManifestRegistryError(
            f"manifest ID {manifest_id!r} has kind {record['kind']!r}, expected {kind!r}"
        )
    if expected_region and record["region"] != expected_region:
        raise ManifestRegistryError(
            f"manifest ID {manifest_id!r} is for region {record['region']!r}, "
            f"expected {expected_region!r}"
        )
    if expected_elevation_band and record["elevation_band"] != expected_elevation_band:
        raise ManifestRegistryError(
            f"manifest ID {manifest_id!r} is for elevation band {record['elevation_band']!r}, "
            f"expected {expected_elevation_band!r}"
        )
    return record


def validate_release_manifest_ids(
    *,
    forcing_id: str,
    geometry_id: str,
    toolchain_id: str,
    registry_path: Path | None = None,
    region_key: str | None = None,
    elevation_band: str | None = None,
) -> list[str]:
    """Return fail-closed validation errors for release manifest IDs."""
    errors: list[str] = []
    for field, value, kind in (
        ("forcing_manifest_id", forcing_id, "forcing"),
        ("geometry_manifest_id", geometry_id, "geometry"),
        ("toolchain_manifest_id", toolchain_id, "toolchain"),
    ):
        try:
            resolve_approved_manifest(
                value,
                kind=kind,
                registry_path=registry_path,
                expected_region=region_key,
                expected_elevation_band=elevation_band,
            )
        except ManifestRegistryError as exc:
            errors.append(f"{field}: {exc}")
    return errors
