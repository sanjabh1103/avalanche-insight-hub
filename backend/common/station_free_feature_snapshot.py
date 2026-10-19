"""Content-addressed, station-free feature snapshot contracts.

This module normalizes public weather/reanalysis/satellite-derived feature
rows into explicit validity windows.  It does not fetch data, infer missing
history, or promote a snapshot into model training.  A feature row is usable
for an interval label only when its full validity window contains that label
interval and its explicit availability cutoff is no later than the interval
start.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.common.spatial_grouping import spatial_feature_join_key


FEATURE_SNAPSHOT_SCHEMA_VERSION = "mvp4_station_free_feature_snapshot_v1"
FEATURE_SNAPSHOT_TIME_CONTRACT = "station_free_feature_window_v1"
DEFAULT_FEATURE_NAMES = (
    "temperature_2m",
    "snowfall",
    "precipitation",
    "relative_humidity_2m",
    "windspeed_10m",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_LICENSE_STATUSES = frozenset(
    {"pending", "permissive_core_reviewed", "permissive_shadow_reviewed"}
)
_SOURCE_METADATA_FIELDS = (
    "model",
    "data_provider",
    "dataset_product",
    "source_url",
    "license_url",
    "underlying_license_url",
    "attribution_text",
    "underlying_reanalysis_observations",
    "observation_free",
    "direct_station_data_used",
    "station_feed_semantics",
    "station_feed_clarification",
    "feature_availability_semantics",
    "forecast_ready",
    "retrospective_only",
    "availability_delay_days",
    "cutoff_policy",
    "cutoff_policy_review_status",
    "native_resolution_m",
    "effective_information_scale_m",
)


class StationFreeFeatureSnapshotError(ValueError):
    """Raised when a feature snapshot cannot satisfy its provenance contract."""


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StationFreeFeatureSnapshotError("feature values must be finite or null")
        return round(value, 12)
    return value


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _canonical(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(value: Any, *, field: str, row_id: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise StationFreeFeatureSnapshotError(f"{row_id}: missing {field}")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StationFreeFeatureSnapshotError(f"{row_id}: invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StationFreeFeatureSnapshotError(f"{row_id}: {field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sha_field(value: Any, *, field: str, source_key: str) -> str:
    result = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(result):
        raise StationFreeFeatureSnapshotError(
            f"{source_key}: {field} must be a SHA-256 value"
        )
    return result


def _source_manifest(source_manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source_manifest, Mapping):
        raise StationFreeFeatureSnapshotError("source_manifest must be an object")
    source_key = str(source_manifest.get("source_key") or "").strip()
    source_family = str(source_manifest.get("source_family") or "").strip()
    if not source_key or not source_family:
        raise StationFreeFeatureSnapshotError(
            "source_manifest requires source_key and source_family"
        )
    license_status = str(source_manifest.get("license_status") or "").strip().lower()
    if license_status not in _LICENSE_STATUSES:
        raise StationFreeFeatureSnapshotError(
            f"{source_key}: unsupported license_status {license_status!r}"
        )
    license_review_id = str(source_manifest.get("license_review_id") or "").strip()
    if not license_review_id:
        raise StationFreeFeatureSnapshotError(f"{source_key}: license_review_id is required")
    if source_manifest.get("station_data_used") is not False:
        raise StationFreeFeatureSnapshotError(
            f"{source_key}: station_data_used must be false"
        )
    if source_manifest.get("direct_station_data_used") is True:
        raise StationFreeFeatureSnapshotError(
            f"{source_key}: direct_station_data_used must be false"
        )
    source_snapshot_id = str(source_manifest.get("source_snapshot_id") or "").strip()
    if not source_snapshot_id:
        raise StationFreeFeatureSnapshotError(f"{source_key}: source_snapshot_id is required")
    normalized = {
        "source_key": source_key,
        "source_family": source_family,
        "source_snapshot_id": source_snapshot_id,
        "source_manifest_sha256": _sha_field(
            source_manifest.get("source_manifest_sha256"),
            field="source_manifest_sha256",
            source_key=source_key,
        ),
        "source_content_sha256": _sha_field(
            source_manifest.get("source_content_sha256"),
            field="source_content_sha256",
            source_key=source_key,
        ),
        "license": str(source_manifest.get("license") or "").strip(),
        "license_status": license_status,
        "license_review_id": license_review_id,
        "station_data_used": False,
    }
    for key in _SOURCE_METADATA_FIELDS:
        if key in source_manifest and source_manifest[key] not in (None, ""):
            normalized[key] = source_manifest[key]
    return normalized


def _feature_values(
    value: Any,
    *,
    row_id: str,
    required_feature_names: tuple[str, ...],
) -> dict[str, float | None]:
    if not isinstance(value, Mapping):
        raise StationFreeFeatureSnapshotError(f"{row_id}: features must be an object")
    missing = [name for name in required_feature_names if name not in value]
    if missing:
        raise StationFreeFeatureSnapshotError(
            f"{row_id}: features are missing required variables: {','.join(missing)}"
        )
    normalized: dict[str, float | None] = {}
    for name, raw in value.items():
        key = str(name).strip()
        if not key:
            raise StationFreeFeatureSnapshotError(f"{row_id}: feature name cannot be blank")
        if raw is None:
            normalized[key] = None
            continue
        if isinstance(raw, bool):
            raise StationFreeFeatureSnapshotError(f"{row_id}: feature {key} must be numeric or null")
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise StationFreeFeatureSnapshotError(
                f"{row_id}: feature {key} must be numeric or null"
            ) from exc
        if not math.isfinite(number):
            raise StationFreeFeatureSnapshotError(f"{row_id}: feature {key} must be finite or null")
        normalized[key] = number
    return {key: normalized[key] for key in sorted(normalized)}


def _normalize_row(
    row: Mapping[str, Any],
    *,
    position: int,
    source: Mapping[str, Any],
    selected_regions: set[str],
    required_feature_names: tuple[str, ...],
    spatial_bin_km: float,
) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise StationFreeFeatureSnapshotError(f"feature:{position}: row must be an object")
    row_id = str(row.get("feature_id") or row.get("id") or "").strip()
    if not row_id:
        raise StationFreeFeatureSnapshotError(f"feature:{position}: feature_id is required")
    region_key = str(row.get("region_key") or "").strip()
    if region_key not in selected_regions:
        raise StationFreeFeatureSnapshotError(
            f"{row_id}: feature region {region_key!r} is outside selected regions"
        )
    for field in ("event_time", "timestamp", "label", "source_event_id"):
        if row.get(field) not in (None, ""):
            raise StationFreeFeatureSnapshotError(
                f"{row_id}: feature rows cannot carry event field {field}"
            )
    if row.get("station_data_used") is True or str(row.get("station_id") or "").strip():
        raise StationFreeFeatureSnapshotError(f"{row_id}: station data is forbidden")
    if row.get("direct_station_data_used") is True:
        raise StationFreeFeatureSnapshotError(f"{row_id}: direct station data is forbidden")
    for field in (
        "training_eligible",
        "core_training_eligible",
        "production_eligible",
        "production_scoring_eligible",
    ):
        if row.get(field) is True:
            raise StationFreeFeatureSnapshotError(f"{row_id}: {field} must remain false")

    source_key = str(row.get("source_key") or source["source_key"]).strip()
    source_family = str(row.get("source_family") or source["source_family"]).strip()
    if source_key != source["source_key"] or source_family != source["source_family"]:
        raise StationFreeFeatureSnapshotError(
            f"{row_id}: row source identity does not match source manifest"
        )
    start = _parse_utc(row.get("feature_valid_from"), field="feature_valid_from", row_id=row_id)
    end = _parse_utc(row.get("feature_valid_until"), field="feature_valid_until", row_id=row_id)
    cutoff = _parse_utc(row.get("feature_cutoff_at"), field="feature_cutoff_at", row_id=row_id)
    if end <= start:
        raise StationFreeFeatureSnapshotError(
            f"{row_id}: feature_valid_until must be after feature_valid_from"
        )
    if cutoff > start:
        raise StationFreeFeatureSnapshotError(
            f"{row_id}: feature_cutoff_at must be at or before feature_valid_from"
        )

    feature_join_key = str(row.get("feature_join_key") or "").strip()
    if not feature_join_key:
        try:
            feature_join_key = spatial_feature_join_key(
                row.get("lat"),
                row.get("lng"),
                region_key,
                bin_km=spatial_bin_km,
            )
        except ValueError as exc:
            raise StationFreeFeatureSnapshotError(f"{row_id}: invalid feature coordinates") from exc
    features = _feature_values(
        row.get("features"),
        row_id=row_id,
        required_feature_names=required_feature_names,
    )
    normalized = {
        "feature_id": row_id,
        "source_key": source["source_key"],
        "source_family": source["source_family"],
        "source_snapshot_id": source["source_snapshot_id"],
        "source_manifest_sha256": source["source_manifest_sha256"],
        "source_content_sha256": source["source_content_sha256"],
        "region_key": region_key,
        "feature_join_key": feature_join_key,
        "feature_valid_from": _iso(start),
        "feature_valid_until": _iso(end),
        "feature_cutoff_at": _iso(cutoff),
        "feature_cutoff_status": "explicit",
        "features": features,
        "station_data_used": False,
        "direct_station_data_used": False,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_eligible": False,
        "production_scoring_eligible": False,
    }
    for key in _SOURCE_METADATA_FIELDS:
        if key in source:
            normalized[key] = source[key]
    for key in ("native_source_lat", "native_source_lng", "assignment_method"):
        if row.get(key) not in (None, ""):
            normalized[key] = row[key]
    if "lat" in row and "lng" in row:
        try:
            normalized["lat"] = float(row["lat"])
            normalized["lng"] = float(row["lng"])
        except (TypeError, ValueError) as exc:
            raise StationFreeFeatureSnapshotError(f"{row_id}: invalid feature coordinates") from exc
    return normalized


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    return _sha256(_canonical_bytes(payload))


def build_station_free_feature_snapshot(
    rows: Iterable[Mapping[str, Any]],
    *,
    region_keys: Iterable[str],
    source_manifest: Mapping[str, Any],
    required_feature_names: Iterable[str] = DEFAULT_FEATURE_NAMES,
    spatial_bin_km: float = 5.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize feature rows and return a non-promoting snapshot manifest."""

    selected_regions = {str(value).strip() for value in region_keys if str(value).strip()}
    if not selected_regions:
        raise StationFreeFeatureSnapshotError("at least one region_key is required")
    required = tuple(sorted({str(value).strip() for value in required_feature_names if str(value).strip()}))
    if not required:
        raise StationFreeFeatureSnapshotError("at least one required feature is required")
    source = _source_manifest(source_manifest)
    normalized = [
        _normalize_row(
            row,
            position=index,
            source=source,
            selected_regions=selected_regions,
            required_feature_names=required,
            spatial_bin_km=spatial_bin_km,
        )
        for index, row in enumerate(rows)
    ]
    if not normalized:
        raise StationFreeFeatureSnapshotError("feature snapshot is empty")
    feature_ids = [row["feature_id"] for row in normalized]
    if len(set(feature_ids)) != len(feature_ids):
        raise StationFreeFeatureSnapshotError("duplicate feature_id values are not allowed")
    normalized.sort(key=lambda row: (
        row["region_key"],
        row["feature_join_key"],
        row["feature_valid_from"],
        row["feature_id"],
    ))
    payload = b"".join(_canonical_bytes(row) for row in normalized)
    missing_values = sum(
        1
        for row in normalized
        for name in required
        if row["features"].get(name) is None
    )
    manifest: dict[str, Any] = {
        "snapshot_schema_version": FEATURE_SNAPSHOT_SCHEMA_VERSION,
        "source_key": "mvp4_station_free_feature_snapshot",
        "source_keys": [source["source_key"]],
        "source_manifests": {source["source_key"]: dict(source)},
        "feature_rows_path": "features.jsonl",
        "feature_rows_sha256": _sha256(payload),
        "feature_row_count": len(normalized),
        "feature_join_key_count": len({row["feature_join_key"] for row in normalized}),
        "region_keys": sorted(selected_regions),
        "required_feature_names": list(required),
        "missing_required_feature_value_count": missing_values,
        "oldest_feature_valid_from": normalized[0]["feature_valid_from"],
        "newest_feature_valid_until": max(row["feature_valid_until"] for row in normalized),
        "feature_time_contract": FEATURE_SNAPSHOT_TIME_CONTRACT,
        "validity_semantics": "[feature_valid_from,feature_valid_until)",
        "cutoff_rule": "feature_cutoff_at<=feature_valid_from and feature_cutoff_at<=label_interval_start",
        "station_data_used": False,
        "feature_snapshot_ready": True,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_eligible": False,
        "production_scoring_eligible": False,
        "review_status": "structurally_validated_station_free_snapshot",
        "spatial_bin_km": float(spatial_bin_km),
    }
    manifest["manifest_hash"] = _manifest_hash(manifest)
    return normalized, manifest


def write_station_free_feature_snapshot(
    output_dir: Path,
    rows: list[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> None:
    """Write canonical JSONL and its hash-pinned manifest."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = b"".join(_canonical_bytes(dict(row)) for row in rows)
    expected = str(manifest.get("feature_rows_sha256") or "")
    if _sha256(payload) != expected:
        raise StationFreeFeatureSnapshotError("feature_rows_sha256 does not match rows")
    manifest_payload = dict(manifest)
    manifest_payload["feature_rows_path"] = "features.jsonl"
    manifest_payload["manifest_hash"] = _manifest_hash(manifest_payload)
    (output / "features.jsonl").write_bytes(payload)
    (output / "snapshot_manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "ATTRIBUTION.md").write_text(
        "# Station-free feature snapshot\n\n"
        "This bundle contains public weather/reanalysis/satellite-derived feature rows "
        "with explicit validity windows and availability cutoffs. It contains no station "
        "data and is not training- or production-eligible.\n",
        encoding="utf-8",
    )


def load_station_free_feature_snapshot(
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load and verify a feature snapshot without network or model I/O."""

    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StationFreeFeatureSnapshotError("feature snapshot manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise StationFreeFeatureSnapshotError("feature snapshot manifest must be an object")
    if manifest.get("snapshot_schema_version") != FEATURE_SNAPSHOT_SCHEMA_VERSION:
        raise StationFreeFeatureSnapshotError("unsupported feature snapshot schema")
    if manifest.get("manifest_hash") != _manifest_hash(manifest):
        raise StationFreeFeatureSnapshotError("feature snapshot manifest hash mismatch")
    feature_path = path.parent / str(manifest.get("feature_rows_path") or "features.jsonl")
    try:
        payload = feature_path.read_bytes()
    except OSError as exc:
        raise StationFreeFeatureSnapshotError("feature rows are missing") from exc
    if _sha256(payload) != str(manifest.get("feature_rows_sha256") or ""):
        raise StationFreeFeatureSnapshotError("feature rows hash mismatch")
    rows: list[dict[str, Any]] = []
    try:
        for line in payload.decode("utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("feature row is not an object")
                rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise StationFreeFeatureSnapshotError("feature rows are not valid JSONL") from exc
    if len(rows) != int(manifest.get("feature_row_count") or -1):
        raise StationFreeFeatureSnapshotError("feature row count mismatch")
    if any(row.get("station_data_used") is not False for row in rows):
        raise StationFreeFeatureSnapshotError("feature rows must remain station-free")
    if any(row.get("training_eligible") is True for row in rows):
        raise StationFreeFeatureSnapshotError("feature rows cannot be training-eligible")
    return rows, manifest
