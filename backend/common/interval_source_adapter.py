"""Build a reviewed, interval-censored label staging snapshot.

The source snapshots used by MVP4 contain day-precision and bounded satellite
detection labels.  This adapter makes their provenance and interval semantics
explicit while keeping the current timestamp-only training path untouched.
It never derives an event timestamp, feature cutoff, or model eligibility from
the source rows.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.common.label_time_contract import normalise_precision
from backend.common.spatial_grouping import spatial_feature_join_key


INTERVAL_LABEL_STAGING_SCHEMA_VERSION = "mvp4_interval_label_staging_v1"
INTERVAL_LABEL_TIME_CONTRACT = "interval_censored_core_v1"
REVIEWED_LICENSE_STATUSES = frozenset(
    {"permissive_core_reviewed", "permissive_shadow_reviewed"}
)
REGION_SEASON_START_MONTHS = {
    "himalayas_nepal": 11,
    "pir_panjal_nw_himalaya": 11,
}


class IntervalSourceAdapterError(ValueError):
    """Raised when source snapshots cannot satisfy the staging contract."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
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
        raise IntervalSourceAdapterError(f"{row_id}: missing {field}")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntervalSourceAdapterError(f"{row_id}: invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntervalSourceAdapterError(f"{row_id}: {field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _row_id(row: Mapping[str, Any], *, position: int) -> str:
    for field in ("source_event_id", "event_id", "external_id", "id"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    raise IntervalSourceAdapterError(f"source row {position}: missing event identifier")


def _load_snapshot(source_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    manifest_path = source_dir / "snapshot_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntervalSourceAdapterError(f"invalid source manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise IntervalSourceAdapterError(f"source manifest must be an object: {manifest_path}")

    source_key = str(manifest.get("source_key") or "").strip()
    if not source_key:
        raise IntervalSourceAdapterError(f"source manifest is missing source_key: {manifest_path}")
    license_status = str(manifest.get("license_status") or "").strip()
    if license_status not in REVIEWED_LICENSE_STATUSES:
        raise IntervalSourceAdapterError(
            f"{source_key}: license_status must be reviewed and permissive; found {license_status!r}"
        )
    license_review_id = str(manifest.get("license_review_id") or "").strip()
    if not license_review_id:
        raise IntervalSourceAdapterError(f"{source_key}: license_review_id is required")

    events_name = str(manifest.get("events_path") or "events.jsonl")
    events_path = source_dir / events_name
    try:
        payload = events_path.read_bytes()
    except OSError as exc:
        raise IntervalSourceAdapterError(f"source events are missing: {events_path}") from exc
    actual_hash = _sha256(payload)
    if actual_hash != str(manifest.get("event_rows_sha256") or ""):
        raise IntervalSourceAdapterError(f"source event hash mismatch: {events_path}")
    rows: list[dict[str, Any]] = []
    try:
        for line in payload.decode("utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("row is not an object")
                rows.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IntervalSourceAdapterError(f"source events are not valid JSONL: {events_path}") from exc
    if not rows:
        raise IntervalSourceAdapterError(f"source events are empty: {events_path}")
    return rows, manifest, payload


def _interval_bounds(row: Mapping[str, Any], *, row_id: str) -> tuple[datetime, datetime]:
    start = _parse_utc(
        row.get("interval_start") or row.get("event_time_start") or row.get("timestamp_start") or row.get("event_time"),
        field="interval_start",
        row_id=row_id,
    )
    end = _parse_utc(
        row.get("interval_end") or row.get("event_time_end") or row.get("timestamp_end"),
        field="interval_end",
        row_id=row_id,
    )
    if end <= start:
        raise IntervalSourceAdapterError(f"{row_id}: interval_end must be after interval_start")
    return start, end


def _normalise_source_row(
    row: Mapping[str, Any],
    *,
    source_key: str,
    license_review_id: str,
    source_overlap_review_status: str,
    position: int,
    selected_regions: set[str],
) -> dict[str, Any] | None:
    if row.get("label") not in (1, True):
        return None
    row_id = _row_id(row, position=position)
    region_key = str(row.get("region_key") or "").strip()
    if region_key not in selected_regions:
        return None
    precision = normalise_precision(row.get("timestamp_precision") or row.get("precision"))
    if precision not in {"day", "interval"}:
        raise IntervalSourceAdapterError(
            f"{row_id}: only day or interval precision is supported; found {precision!r}"
        )
    start, end = _interval_bounds(row, row_id=row_id)
    event_group_id = str(row.get("event_group_id") or "").strip()
    if not event_group_id:
        raise IntervalSourceAdapterError(f"{row_id}: event_group_id is required")
    source_family = str(
        row.get("origin_source_family") or row.get("source_family") or source_key
    ).strip()
    if not source_family:
        raise IntervalSourceAdapterError(f"{row_id}: origin source family is required")
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except (TypeError, ValueError) as exc:
        raise IntervalSourceAdapterError(f"{row_id}: valid lat/lng are required") from exc
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise IntervalSourceAdapterError(f"{row_id}: lat/lng are out of range")
    source_row_sha256 = str(row.get("source_row_sha256") or "").strip()
    if len(source_row_sha256) != 64:
        raise IntervalSourceAdapterError(f"{row_id}: source_row_sha256 must be a SHA-256 value")
    try:
        feature_join_key = spatial_feature_join_key(lat, lng, region_key)
    except ValueError as exc:
        raise IntervalSourceAdapterError(f"{row_id}: could not derive feature join key") from exc

    # Deliberately omit event_time/timestamp.  A source sensing or publication
    # time must never be silently relabelled as the occurrence time.
    return {
        "source_event_id": row_id,
        "event_group_id": event_group_id,
        "source_key": source_key,
        "label_source": source_key,
        "origin_source_family": source_family,
        "region_key": region_key,
        "feature_join_key": feature_join_key,
        "spatial_group_id": feature_join_key,
        "lat": lat,
        "lng": lng,
        "label": 1,
        "interval_start": _iso(start),
        "interval_end": _iso(end),
        "timestamp_precision": precision,
        "source_overlap_review_status": source_overlap_review_status,
        "license_review_id": license_review_id,
        "source_row_sha256": source_row_sha256,
        "feature_cutoff_at": None,
        "feature_cutoff_status": "pending_explicit_feature_snapshot",
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
    }


def _season_id(row: Mapping[str, Any]) -> str:
    start = _parse_utc(row["interval_start"], field="interval_start", row_id=str(row["source_event_id"]))
    month = REGION_SEASON_START_MONTHS.get(str(row["region_key"]), 7)
    year = start.year if start.month >= month else start.year - 1
    return f"{year}-{year + 1}"


def _validate_overlap_report(
    overlap_report: Mapping[str, Any],
    source_keys: set[str],
) -> None:
    if str(overlap_report.get("status") or "").strip().lower() != "reviewed":
        raise IntervalSourceAdapterError("source overlap report must be reviewed")
    report_sources = {
        str(overlap_report.get("source_a") or "").strip(),
        str(overlap_report.get("source_b") or "").strip(),
    }
    if report_sources != source_keys or len(report_sources) != 2:
        raise IntervalSourceAdapterError(
            f"source overlap report sources {sorted(report_sources)} do not match {sorted(source_keys)}"
        )
    if int(overlap_report.get("independent_positive_source_count") or 0) != 2:
        raise IntervalSourceAdapterError("source overlap report must prove two independent sources")
    if overlap_report.get("same_event_must_not_count_as_independent") is not True:
        raise IntervalSourceAdapterError("source overlap report must reject duplicate corroboration")


def build_interval_label_staging(
    source_dirs: Iterable[Path],
    *,
    overlap_report_path: Path,
    region_keys: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    """Build a deterministic, non-training interval label snapshot."""
    directories = [Path(value) for value in source_dirs]
    selected_regions = {str(value).strip() for value in region_keys if str(value).strip()}
    if len(directories) < 2:
        raise IntervalSourceAdapterError("at least two source snapshots are required")
    if not selected_regions:
        raise IntervalSourceAdapterError("at least one target region is required")

    loaded = [_load_snapshot(directory) for directory in directories]
    source_keys = {str(manifest["source_key"]).strip() for _, manifest, _ in loaded}
    if len(source_keys) != len(loaded):
        raise IntervalSourceAdapterError("source snapshots must have unique source_key values")
    try:
        overlap_payload = Path(overlap_report_path).read_bytes()
        overlap_report = json.loads(overlap_payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise IntervalSourceAdapterError("source overlap report is missing or invalid") from exc
    if not isinstance(overlap_report, dict):
        raise IntervalSourceAdapterError("source overlap report must be an object")
    _validate_overlap_report(overlap_report, source_keys)

    rows: list[dict[str, Any]] = []
    source_manifests: dict[str, dict[str, Any]] = {}
    for source_rows, manifest, manifest_payload in loaded:
        source_key = str(manifest["source_key"]).strip()
        source_manifests[source_key] = {
            "source_manifest_sha256": _sha256(manifest_payload),
            "event_rows_sha256": str(manifest["event_rows_sha256"]),
            "license": manifest.get("license"),
            "license_status": manifest.get("license_status"),
            "license_review_id": manifest.get("license_review_id"),
            "source_role": manifest.get("source_role"),
        }
        for position, row in enumerate(source_rows):
            normalised = _normalise_source_row(
                row,
                source_key=source_key,
                license_review_id=str(manifest["license_review_id"]),
                source_overlap_review_status="reviewed",
                position=position,
                selected_regions=selected_regions,
            )
            if normalised is not None:
                rows.append(normalised)
    if not rows:
        raise IntervalSourceAdapterError("no eligible positive rows cover the selected regions")

    rows.sort(key=lambda row: (
        str(row["region_key"]),
        str(row["interval_start"]),
        str(row["source_key"]),
        str(row["source_event_id"]),
    ))
    payload = b"".join(_canonical_bytes(row) for row in rows)
    seasons_by_region: dict[str, list[str]] = {}
    for region in sorted(selected_regions):
        seasons_by_region[region] = sorted(
            {_season_id(row) for row in rows if row["region_key"] == region}
        )
    positive_seasons = sorted({_season_id(row) for row in rows})
    source_counts = Counter(str(row["source_key"]) for row in rows)
    family_counts = Counter(str(row["origin_source_family"]) for row in rows)
    precision_counts = Counter(str(row["timestamp_precision"]) for row in rows)
    manifest = {
        "snapshot_schema_version": INTERVAL_LABEL_STAGING_SCHEMA_VERSION,
        "source_key": "mvp4_interval_label_staging",
        "source_keys": sorted(source_keys),
        "source_manifests": source_manifests,
        "source_overlap_report": "source_overlap_report.json",
        "source_overlap_report_sha256": _sha256(overlap_payload),
        "source_overlap_review_status": "reviewed",
        "required_independent_positive_sources": sorted(source_keys),
        "independent_positive_source_count": 2,
        "same_event_must_not_count_as_independent": True,
        "included_record_count": len(rows),
        "source_record_counts": dict(sorted(source_counts.items())),
        "source_family_counts": dict(sorted(family_counts.items())),
        "timestamp_precision_counts": dict(sorted(precision_counts.items())),
        "bounded_interval_record_count": sum(
            count for precision, count in precision_counts.items() if precision == "interval"
        ),
        "event_rows_sha256": _sha256(payload),
        "positive_season_ids": positive_seasons,
        "positive_season_count": len(positive_seasons),
        "positive_seasons_by_region": seasons_by_region,
        "region_season_start_months": REGION_SEASON_START_MONTHS,
        "target_regions": {
            region: {"season_start_month": REGION_SEASON_START_MONTHS.get(region, 7)}
            for region in sorted(selected_regions)
        },
        "label_time_contract": INTERVAL_LABEL_TIME_CONTRACT,
        "feature_cutoff_required": True,
        "feature_cutoff_status": "pending_explicit_feature_snapshot",
        "training_eligible": False,
        "interval_training_ready": False,
        "production_scoring_eligible": False,
        "staging_only": True,
        "review_status": "reviewed_interval_staging",
        "required_next_action": (
            "Join an explicitly hashed feature snapshot with feature_cutoff_at<=interval_start; "
            "run interval-training validation and obtain scientist/data-owner approval before activation."
        ),
    }
    return rows, manifest, overlap_payload


def write_interval_label_staging(
    output_dir: Path,
    rows: list[dict[str, Any]],
    manifest: Mapping[str, Any],
    overlap_payload: bytes,
) -> None:
    """Write the deterministic staging bundle without changing eligibility flags."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = b"".join(_canonical_bytes(row) for row in rows)
    (output_dir / "events.jsonl").write_bytes(payload)
    (output_dir / "snapshot_manifest.json").write_text(
        json.dumps({**dict(manifest), "events_path": "events.jsonl"}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "source_overlap_report.json").write_bytes(overlap_payload)
    (output_dir / "ATTRIBUTION.md").write_text(
        "# Interval label staging attribution\n\n"
        "This bundle preserves reviewed source attribution and bounded time windows "
        "for interval-censored training preparation. It contains no event-time synthesis, "
        "feature cutoff, model fit, or production eligibility.\n",
        encoding="utf-8",
    )
