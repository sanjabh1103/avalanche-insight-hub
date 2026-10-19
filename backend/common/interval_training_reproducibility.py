"""Deterministic, shadow-only reproducibility for interval-censored labels.

The timestamp-only training path cannot consume day or bounded-interval labels.
This module provides the missing evidence lane without changing that path: it
joins explicit label intervals to fully enclosing feature windows, preserves
provenance and groups, and writes a content-addressed shadow frame.  It never
creates an event timestamp and never marks a row eligible for core training or
production scoring.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.common.interval_shadow_join import (
    IntervalShadowJoinError,
    IntervalShadowJoinPolicy,
    build_interval_shadow_join,
)
from backend.common.interval_training_contract import INTERVAL_TRAINING_PATH_STATUS
from backend.common.label_time_contract import (
    LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
    normalise_precision,
    validate_label_time_rows,
)
from backend.common.spatial_grouping import spatial_feature_join_key


INTERVAL_TRAINING_REPRODUCIBILITY_VERSION = "interval_training_reproducibility_v1"
INTERVAL_TRAINING_FRAME_SCHEMA_VERSION = "interval_training_shadow_frame_v1"
REGION_SEASON_START_MONTHS = {
    "himalayas_nepal": 11,
    "pir_panjal_nw_himalaya": 11,
    "shamshabari_nw_himalaya": 11,
    "great_himalaya_nw_himalaya": 11,
    "karakoram_&_ladakh": 10,
}


class IntervalTrainingReproducibilityError(ValueError):
    """Raised when an interval shadow frame violates its evidence contract."""


@dataclass(frozen=True)
class IntervalTrainingReproducibilityConfig:
    """Deterministic split and grouping policy for the shadow frame."""

    train_fraction: float = 0.60
    calibration_fraction: float = 0.20
    spatial_bin_km: float = 5.0
    minimum_event_groups: int = 3
    minimum_positive_seasons: int = 3
    minimum_positive_sources: int = 2

    def __post_init__(self) -> None:
        if not 0 < self.train_fraction < 1:
            raise ValueError("train_fraction must be between 0 and 1")
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be between 0 and 1")
        if self.train_fraction + self.calibration_fraction >= 1:
            raise ValueError("train and calibration fractions must leave test data")
        if self.spatial_bin_km <= 0:
            raise ValueError("spatial_bin_km must be positive")
        if min(
            self.minimum_event_groups,
            self.minimum_positive_seasons,
            self.minimum_positive_sources,
        ) < 1:
            raise ValueError("minimum evidence counts must be positive")


def _parse_utc(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise IntervalTrainingReproducibilityError(f"missing {field}")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise IntervalTrainingReproducibilityError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntervalTrainingReproducibilityError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 12)
    return value


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _canonical_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _row_id(row: Mapping[str, Any], *, position: int) -> str:
    for field in ("source_event_id", "event_id", "external_id", "row_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    raise IntervalTrainingReproducibilityError(f"label:{position}: missing source event identifier")


def _spatial_group_id(lat: float, lng: float, region_key: str, bin_km: float) -> str:
    return spatial_feature_join_key(lat, lng, region_key, bin_km=bin_km)


def _finite_coordinate(value: Any, *, field: str, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise IntervalTrainingReproducibilityError(f"invalid {field}") from exc
    if not math.isfinite(parsed) or not lower <= parsed <= upper:
        raise IntervalTrainingReproducibilityError(f"invalid {field}")
    return parsed


def _normalise_label(
    row: Mapping[str, Any],
    *,
    position: int,
    require_feature_cutoff: bool = True,
) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise IntervalTrainingReproducibilityError(f"label:{position}: row must be an object")

    row_id = _row_id(row, position=position)
    precision = normalise_precision(row.get("precision") or row.get("timestamp_precision"))
    if precision not in {"day", "interval"}:
        raise IntervalTrainingReproducibilityError(
            f"{row_id}: interval shadow frame requires day or interval precision"
        )

    start = _parse_utc(
        row.get("interval_start") or row.get("event_time_start") or row.get("timestamp_start"),
        field="interval_start",
    )
    end = _parse_utc(
        row.get("interval_end") or row.get("event_time_end") or row.get("timestamp_end"),
        field="interval_end",
    )
    if end <= start:
        raise IntervalTrainingReproducibilityError(f"{row_id}: interval_end must be after interval_start")

    point_fields = [field for field in ("event_time", "timestamp") if row.get(field) not in (None, "")]
    if point_fields:
        if precision != "day":
            raise IntervalTrainingReproducibilityError(
                f"{row_id}: point-time field {point_fields[0]} is forbidden for interval labels"
            )
        for field in point_fields:
            point = _parse_utc(row.get(field), field=field)
            if point != start:
                raise IntervalTrainingReproducibilityError(
                    f"{row_id}: day point-time field {field} does not equal interval_start"
                )

    raw_cutoff = row.get("feature_cutoff_at")
    cutoff = None
    if raw_cutoff not in (None, ""):
        cutoff = _parse_utc(raw_cutoff, field="feature_cutoff_at")
    elif require_feature_cutoff:
        raise IntervalTrainingReproducibilityError(
            f"{row_id}: missing feature_cutoff_at"
        )
    if cutoff is not None and cutoff > start:
        raise IntervalTrainingReproducibilityError(
            f"{row_id}: feature_cutoff_at must be at or before interval_start"
        )

    region_key = str(row.get("region_key") or "").strip()
    source_key = str(row.get("source_key") or "").strip()
    source_family = str(row.get("source_family") or row.get("origin_source_family") or "").strip()
    join_key = str(
        row.get("feature_join_key") or row.get("spatial_group_id") or row.get("join_key") or ""
    ).strip()
    overlap_status = str(row.get("source_overlap_review_status") or "").strip().lower()
    license_review_id = str(row.get("license_review_id") or "").strip()
    if not region_key or not source_key or not source_family or not join_key:
        raise IntervalTrainingReproducibilityError(
            f"{row_id}: region_key, source_key, source family, and feature join key are required"
        )
    if overlap_status not in {"reviewed", "not_required"}:
        raise IntervalTrainingReproducibilityError(
            f"{row_id}: source_overlap_review_status must be reviewed or not_required"
        )
    if not license_review_id:
        raise IntervalTrainingReproducibilityError(f"{row_id}: license_review_id is required")
    if row.get("label") not in (1, True):
        raise IntervalTrainingReproducibilityError(f"{row_id}: interval labels must be positive")
    for field in (
        "training_eligible",
        "core_training_eligible",
        "production_eligible",
        "production_scoring_eligible",
    ):
        if row.get(field) is True:
            raise IntervalTrainingReproducibilityError(f"{row_id}: {field} must remain false")

    lat = _finite_coordinate(row.get("lat"), field="lat", lower=-90.0, upper=90.0)
    lng = _finite_coordinate(row.get("lng"), field="lng", lower=-180.0, upper=180.0)
    event_group_id = str(row.get("event_group_id") or "").strip()
    if not event_group_id:
        raise IntervalTrainingReproducibilityError(f"{row_id}: event_group_id is required")

    cleaned = {
        "source_event_id": row_id,
        "event_group_id": event_group_id,
        "source_key": source_key,
        "origin_source_family": source_family,
        "region_key": region_key,
        "feature_join_key": join_key,
        "event_time_start": _iso(start),
        "event_time_end": _iso(end),
        "timestamp_precision": precision,
        "feature_cutoff_at": _iso(cutoff) if cutoff is not None else None,
        "source_overlap_review_status": overlap_status,
        "license_review_id": license_review_id,
        "source_row_sha256": str(row.get("source_row_sha256") or "").strip() or None,
        "lat": lat,
        "lng": lng,
        "label": 1,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
    }
    return cleaned


def _label_id(row: Mapping[str, Any]) -> str:
    return str(row.get("source_event_id") or row.get("event_id") or row.get("external_id") or "").strip()


def _build_joined_interval_training_frame(
    normalised_labels: list[dict[str, Any]],
    features: Iterable[Mapping[str, Any]],
    *,
    policy: IntervalShadowJoinPolicy | None = None,
) -> list[dict[str, Any]]:
    """Join already-normalized labels and validate the non-promoting frame."""
    label_by_id = {_label_id(row): row for row in normalised_labels}
    if len(label_by_id) != len(normalised_labels):
        raise IntervalTrainingReproducibilityError("duplicate source event identifiers are not allowed")

    try:
        joined = build_interval_shadow_join(
            normalised_labels,
            features,
            policy=policy,
        )
    except IntervalShadowJoinError as exc:
        raise IntervalTrainingReproducibilityError(str(exc)) from exc

    frame: list[dict[str, Any]] = []
    for joined_row in joined["rows"]:
        label_id = str(joined_row["label_id"])
        label = label_by_id.get(label_id)
        if label is None:
            raise IntervalTrainingReproducibilityError(
                f"joined label {label_id} was not present in the normalized label set"
            )
        frame.append({
            "row_id": f"{label_id}:{joined_row['feature_id']}",
            "source_event_id": label_id,
            "event_group_id": label["event_group_id"],
            "spatial_group_id": _spatial_group_id(
                float(label["lat"]),
                float(label["lng"]),
                str(label["region_key"]),
                5.0,
            ),
            "label": 1,
            "label_source": joined_row["label_source_key"],
            "origin_source_family": joined_row["label_source_family"],
            "feature_source_key": joined_row["feature_source_key"],
            "feature_source_family": joined_row["feature_source_family"],
            "region_key": joined_row["region_key"],
            "interval_start": joined_row["interval_start"],
            "interval_end": joined_row["interval_end"],
            "timestamp_precision": label["timestamp_precision"],
            "feature_cutoff_at": joined_row["feature_cutoff_at"],
            "source_overlap_review_status": joined_row["source_overlap_review_status"],
            "license_review_id": label["license_review_id"],
            "source_row_sha256": label["source_row_sha256"],
            "lat": label["lat"],
            "lng": label["lng"],
            "features": joined_row["features"],
            "shadow_only": True,
            "core_training_eligible": False,
            "production_scoring_eligible": False,
        })
    frame.sort(key=lambda row: (
        str(row["event_group_id"]),
        str(row["interval_start"]),
        str(row["row_id"]),
    ))
    validation = validate_interval_training_frame(frame)
    if not validation["passed"]:
        raise IntervalTrainingReproducibilityError(
            f"interval frame validation failed: {validation['error_counts']}"
        )
    return frame


def build_interval_training_frame(
    labels: Iterable[Mapping[str, Any]],
    features: Iterable[Mapping[str, Any]],
    *,
    policy: IntervalShadowJoinPolicy | None = None,
) -> list[dict[str, Any]]:
    """Build a strict interval frame when labels already carry a cutoff."""

    normalised_labels = [
        _normalise_label(row, position=index, require_feature_cutoff=True)
        for index, row in enumerate(labels)
    ]
    return _build_joined_interval_training_frame(normalised_labels, features, policy=policy)


def build_interval_training_frame_from_staging(
    labels: Iterable[Mapping[str, Any]],
    features: Iterable[Mapping[str, Any]],
    *,
    policy: IntervalShadowJoinPolicy | None = None,
) -> list[dict[str, Any]]:
    """Join staging labels whose cutoff is supplied by the feature snapshot.

    This is the only path that may accept a missing label cutoff.  The joined
    feature row must still carry an explicit cutoff no later than the label
    interval start; the output is always shadow-only and remains outside the
    timestamp-only model path.
    """

    normalised_labels = [
        _normalise_label(row, position=index, require_feature_cutoff=False)
        for index, row in enumerate(labels)
    ]
    return _build_joined_interval_training_frame(normalised_labels, features, policy=policy)


def evaluate_interval_training_staging_join(
    labels: Iterable[Mapping[str, Any]],
    features: Iterable[Mapping[str, Any]],
    *,
    policy: IntervalShadowJoinPolicy | None = None,
) -> dict[str, Any]:
    """Return the deterministic join report before attempting frame evidence."""

    normalised_labels = [
        _normalise_label(row, position=index, require_feature_cutoff=False)
        for index, row in enumerate(labels)
    ]
    try:
        return build_interval_shadow_join(
            normalised_labels,
            features,
            policy=policy,
        )
    except IntervalShadowJoinError as exc:
        raise IntervalTrainingReproducibilityError(str(exc)) from exc


def validate_interval_training_frame(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate a shadow frame without fitting a model or writing files."""
    records = [dict(row) for row in rows]
    errors: list[dict[str, Any]] = []
    error_counts: dict[str, int] = {}

    def add(code: str, index: int, message: str) -> None:
        error_counts[code] = error_counts.get(code, 0) + 1
        if len(errors) < 20:
            errors.append({"row_index": index, "code": code, "message": message})

    time_rows: list[dict[str, Any]] = []
    for index, row in enumerate(records):
        if "timestamp" in row or "event_time" in row:
            add("point_time_field_present", index, "interval frame rows must not contain timestamp or event_time")
        if row.get("shadow_only") is not True:
            add("shadow_only_flag_missing", index, "interval frame rows must be shadow_only")
        for field in ("core_training_eligible", "production_scoring_eligible"):
            if row.get(field) is not False:
                add("promotion_flag_not_false", index, f"{field} must be false")
        if not str(row.get("event_group_id") or "").strip():
            add("missing_event_group_id", index, "event_group_id is required")
        if not str(row.get("label_source") or "").strip():
            add("missing_label_source", index, "label_source is required")
        features = row.get("features")
        if not isinstance(features, Mapping) or not features:
            add("missing_features", index, "features must be a non-empty object")
        else:
            for feature_name, feature_value in features.items():
                if feature_value is None:
                    add(
                        "missing_feature_value",
                        index,
                        f"feature {feature_name} is missing",
                    )
        time_rows.append({
            "precision": row.get("timestamp_precision"),
            "interval_start": row.get("interval_start"),
            "interval_end": row.get("interval_end"),
            "feature_cutoff_at": row.get("feature_cutoff_at"),
        })

    time_report = validate_label_time_rows(
        time_rows,
        contract=LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
        require_feature_cutoff=True,
    )
    for code, count in time_report["error_counts"].items():
        error_counts[code] = error_counts.get(code, 0) + int(count)
    for issue in time_report["errors"][: max(0, 20 - len(errors))]:
        errors.append(issue)

    return {
        "version": INTERVAL_TRAINING_FRAME_SCHEMA_VERSION,
        "passed": not error_counts and bool(records),
        "row_count": len(records),
        "valid_row_count": len(records) if not error_counts else 0,
        "precision_counts": time_report["precision_counts"],
        "error_counts": dict(sorted(error_counts.items())),
        "errors": errors,
    }


def _season_id(interval_start: str, region_key: str) -> str:
    timestamp = _parse_utc(interval_start, field="interval_start")
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    year = timestamp.year if timestamp.month >= start_month else timestamp.year - 1
    return f"{year}-{year + 1}"


def _split_boundaries(
    rows: list[dict[str, Any]],
    config: IntervalTrainingReproducibilityConfig,
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        group_id = str(row["event_group_id"])
        start = _parse_utc(row["interval_start"], field="interval_start")
        end = _parse_utc(row["interval_end"], field="interval_end")
        current = groups.get(group_id)
        if current is None:
            groups[group_id] = {"start": start, "end": end}
        else:
            current["start"] = min(current["start"], start)
            current["end"] = max(current["end"], end)
    ordered = sorted(groups.items(), key=lambda item: (item[1]["start"], item[0]))
    if len(ordered) < config.minimum_event_groups:
        raise IntervalTrainingReproducibilityError(
            f"at least {config.minimum_event_groups} event groups are required; found {len(ordered)}"
        )
    train_count = max(1, int(math.floor(len(ordered) * config.train_fraction)))
    calibration_count = max(1, int(math.floor(len(ordered) * config.calibration_fraction)))
    if train_count + calibration_count >= len(ordered):
        calibration_count = max(1, len(ordered) - train_count - 1)
    test_start_index = train_count + calibration_count

    def segment(start_index: int, end_index: int) -> dict[str, Any]:
        selected = ordered[start_index:end_index]
        return {
            "start": _iso(selected[0][1]["start"]),
            "end": _iso(max(item[1]["end"] for item in selected)),
            "event_group_count": len(selected),
            "event_group_ids": [item[0] for item in selected],
        }

    return {
        "train": segment(0, train_count),
        "calibration": segment(train_count, test_start_index),
        "test": segment(test_start_index, len(ordered)),
        "event_group_count": len(ordered),
        "policy": {
            "train_fraction": config.train_fraction,
            "calibration_fraction": config.calibration_fraction,
            "test_is_later_than_calibration": True,
        },
    }


def _runtime_manifest() -> dict[str, Any]:
    lock_path = Path("backend/locks/core-py312.txt")
    lock_hash = hashlib.sha256(lock_path.read_bytes()).hexdigest() if lock_path.is_file() else None
    try:
        code_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        code_sha = None
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dependency_lock_hash": lock_hash,
        "code_sha": code_sha,
    }


def build_interval_training_evidence(
    rows: Iterable[Mapping[str, Any]],
    *,
    config: IntervalTrainingReproducibilityConfig | None = None,
    snapshot_path: Path | None = None,
    runtime: Mapping[str, Any] | None = None,
    snapshot_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a content-addressed shadow manifest for an interval frame."""
    policy = config or IntervalTrainingReproducibilityConfig()
    frame = [dict(row) for row in rows]
    validation = validate_interval_training_frame(frame)
    if not validation["passed"]:
        raise IntervalTrainingReproducibilityError(
            f"interval frame validation failed: {validation['error_counts']}"
        )
    ordered = sorted(
        (_canonical_value(row) for row in frame),
        key=lambda row: (
            str(row.get("event_group_id") or ""),
            str(row.get("interval_start") or ""),
            str(row.get("row_id") or ""),
        ),
    )
    payload = b"".join(_canonical_bytes(row) for row in ordered)
    snapshot_hash = hashlib.sha256(payload).hexdigest()
    snapshot_file_sha256 = None
    if snapshot_path is not None:
        target = Path(snapshot_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        snapshot_file_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        if snapshot_file_sha256 != snapshot_hash:
            raise IntervalTrainingReproducibilityError("interval snapshot hash changed during write")

    seasons = sorted({
        _season_id(str(row["interval_start"]), str(row["region_key"]))
        for row in ordered
    })
    sources = sorted({str(row["label_source"]) for row in ordered})
    source_families = sorted({str(row["origin_source_family"]) for row in ordered})
    if len(seasons) < policy.minimum_positive_seasons:
        raise IntervalTrainingReproducibilityError(
            "interval shadow evidence requires at least "
            f"{policy.minimum_positive_seasons} positive seasons; found {len(seasons)}"
        )
    if len(source_families) < policy.minimum_positive_sources:
        raise IntervalTrainingReproducibilityError(
            "interval shadow evidence requires at least "
            f"{policy.minimum_positive_sources} independent source families; "
            f"found {len(source_families)}"
        )
    regions = sorted({str(row["region_key"]) for row in ordered})
    spatial_groups = sorted({str(row["spatial_group_id"]) for row in ordered})
    split_boundaries = _split_boundaries(ordered, policy)
    return {
        "version": INTERVAL_TRAINING_REPRODUCIBILITY_VERSION,
        "frame_schema": INTERVAL_TRAINING_FRAME_SCHEMA_VERSION,
        "label_time_contract": LABEL_TIME_CONTRACT_INTERVAL_CENSORED_V1,
        "interval_training_path_status": INTERVAL_TRAINING_PATH_STATUS,
        "snapshot_hash": snapshot_hash,
        "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
        "snapshot_file_sha256": snapshot_file_sha256,
        "row_count": len(ordered),
        "event_group_count": split_boundaries["event_group_count"],
        "spatial_group_count": len(spatial_groups),
        "region_keys": regions,
        "positive_season_ids": seasons,
        "positive_source_ids": sources,
        "independent_positive_source_family_ids": source_families,
        "source_counts": {
            source: sum(1 for row in ordered if row["label_source"] == source)
            for source in sources
        },
        "source_family_counts": {
            source_family: sum(
                1 for row in ordered if row["origin_source_family"] == source_family
            )
            for source_family in source_families
        },
        "oldest_interval_start": min(str(row["interval_start"]) for row in ordered),
        "newest_interval_end": max(str(row["interval_end"]) for row in ordered),
        "split_boundaries": split_boundaries,
        "validation": validation,
        "shadow_only": True,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
        "runtime": dict(runtime or _runtime_manifest()),
        "snapshot_provenance": dict(snapshot_provenance or {}),
        "policy": {
            "minimum_event_groups": policy.minimum_event_groups,
            "minimum_positive_seasons": policy.minimum_positive_seasons,
            "minimum_positive_sources": policy.minimum_positive_sources,
            "spatial_bin_km": policy.spatial_bin_km,
            "point_time_synthesis": False,
        },
    }
