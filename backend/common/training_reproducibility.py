"""Deterministic training snapshots, grouping and split contracts.

This module deliberately contains no model code and no network access.  It
turns an assembled training frame into a replayable, leakage-aware manifest
before a model is fitted.  The manifest is private evidence: it is not a
claim that the labels are scientifically sufficient.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


REPRODUCIBILITY_VERSION = "training_reproducibility_v1"
SNAPSHOT_SCHEMA_VERSION = "training_row_snapshot_v1"
DEFAULT_SPATIAL_BIN_KM = 5.0
VOLATILE_FIELDS = {"governed_at", "generated_at", "run_id", "row_order"}
REGION_SEASON_START_MONTHS = {
    "himalayas_nepal": 11,
    "pir_panjal_nw_himalaya": 11,
    "shamshabari_nw_himalaya": 11,
    "great_himalaya_nw_himalaya": 11,
    "karakoram_&_ladakh": 10,
}


class TrainingReproducibilityError(ValueError):
    """Raised when a training frame cannot satisfy the replay contract."""


@dataclass(frozen=True)
class ReproducibilityConfig:
    """Policy values used to construct and validate a training manifest."""

    spatial_bin_km: float = DEFAULT_SPATIAL_BIN_KM
    train_fraction: float = 0.60
    calibration_fraction: float = 0.20
    minimum_seasons: int = 3
    minimum_span_days: float = 30.0
    minimum_positive_seasons: int = 3
    minimum_positive_sources: int = 2

    def __post_init__(self) -> None:
        if self.spatial_bin_km <= 0:
            raise ValueError("spatial_bin_km must be positive")
        if not 0 < self.train_fraction < 1:
            raise ValueError("train_fraction must be between 0 and 1")
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be between 0 and 1")
        if self.train_fraction + self.calibration_fraction >= 1:
            raise ValueError("train and calibration fractions must leave test data")
        if (
            self.minimum_seasons < 1
            or self.minimum_span_days < 0
            or self.minimum_positive_seasons < 1
            or self.minimum_positive_sources < 1
        ):
            raise ValueError("minimum season/span policy is invalid")


def _normalise_timestamp(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return str(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")


def _normalise_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return _normalise_timestamp(value)
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 12)
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalise_value(item) for item in value]
    if value is pd.NA:
        return None
    return value


def canonical_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable, hashable representation of one training row."""
    return {
        str(key): _normalise_value(value)
        for key, value in sorted(row.items(), key=lambda item: str(item[0]))
        if str(key) not in VOLATILE_FIELDS
    }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalise_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _event_group_id(row: Mapping[str, Any], index: int) -> str:
    explicit = str(row.get("event_group_id") or "").strip()
    if explicit:
        return explicit
    parent = str(row.get("source_event_id") or row.get("event_id") or "").strip()
    if parent:
        return f"event:{parent}"
    return f"row:{index}"


def _season_id(timestamp: pd.Timestamp, region_key: str | None = None) -> str:
    """Use the configured regional start month for a snow season."""
    start_month = REGION_SEASON_START_MONTHS.get(str(region_key or ""), 7)
    year = timestamp.year if timestamp.month >= start_month else timestamp.year - 1
    return f"{year}-{year + 1}"


def _spatial_group_id(lat: float, lng: float, region: str, bin_km: float) -> str:
    lat_step = bin_km / 111.0
    latitude = max(-89.0, min(89.0, float(lat)))
    lng_step = bin_km / max(1.0, 111.0 * math.cos(math.radians(latitude)))
    lat_bin = math.floor(float(lat) / lat_step)
    lng_bin = math.floor(float(lng) / lng_step)
    return f"{region or 'unknown'}:{lat_bin}:{lng_bin}"


def _timestamp_series(frame: pd.DataFrame) -> pd.Series:
    if "timestamp" not in frame.columns:
        raise TrainingReproducibilityError("timestamp column is required")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise TrainingReproducibilityError("all training rows require a valid timestamp")
    return timestamps


def enrich_training_groups(
    frame: pd.DataFrame,
    *,
    config: ReproducibilityConfig | None = None,
) -> pd.DataFrame:
    """Add immutable event, spatial, season and paired-negative groups."""
    policy = config or ReproducibilityConfig()
    if frame.empty:
        raise TrainingReproducibilityError("training frame is empty")
    enriched = frame.copy()
    timestamps = _timestamp_series(enriched)
    enriched["timestamp"] = timestamps
    event_groups = [
        _event_group_id(row, index)
        for index, row in enumerate(enriched.to_dict(orient="records"))
    ]
    if "region_key" not in enriched.columns:
        raise TrainingReproducibilityError("region_key column is required")
    if "lat" not in enriched.columns or "lng" not in enriched.columns:
        raise TrainingReproducibilityError("lat/lng columns are required")
    enriched["event_group_id"] = event_groups
    enriched["paired_group_id"] = event_groups
    enriched["season_id"] = [
        _season_id(value, str(region))
        for value, region in zip(timestamps, enriched["region_key"])
    ]
    enriched["spatial_group_id"] = [
        _spatial_group_id(lat, lng, str(region), policy.spatial_bin_km)
        for lat, lng, region in zip(enriched["lat"], enriched["lng"], enriched["region_key"])
    ]
    return enriched


def _group_boundaries(frame: pd.DataFrame, config: ReproducibilityConfig) -> dict[str, Any]:
    grouped = (
        frame.groupby("event_group_id", sort=False)["timestamp"]
        .min()
        .sort_values()
    )
    group_count = len(grouped)
    if group_count < 3:
        raise TrainingReproducibilityError("at least three event groups are required for train/calibration/test")
    train_groups = max(1, int(math.floor(group_count * config.train_fraction)))
    calibration_groups = max(1, int(math.floor(group_count * config.calibration_fraction)))
    if train_groups + calibration_groups >= group_count:
        calibration_groups = max(1, group_count - train_groups - 1)
    train_end = grouped.iloc[train_groups - 1]
    calibration_end = grouped.iloc[train_groups + calibration_groups - 1]
    test_start = grouped.iloc[train_groups + calibration_groups]
    test_end = grouped.iloc[-1]
    return {
        "train": {
            "start": grouped.iloc[0].isoformat().replace("+00:00", "Z"),
            "end": train_end.isoformat().replace("+00:00", "Z"),
            "event_group_count": train_groups,
            "event_group_ids": [str(value) for value in grouped.iloc[:train_groups].index],
        },
        "calibration": {
            "start": grouped.iloc[train_groups].isoformat().replace("+00:00", "Z"),
            "end": calibration_end.isoformat().replace("+00:00", "Z"),
            "event_group_count": calibration_groups,
            "event_group_ids": [
                str(value) for value in grouped.iloc[train_groups:train_groups + calibration_groups].index
            ],
        },
        "test": {
            "start": test_start.isoformat().replace("+00:00", "Z"),
            "end": test_end.isoformat().replace("+00:00", "Z"),
            "event_group_count": group_count - train_groups - calibration_groups,
            "event_group_ids": [str(value) for value in grouped.iloc[train_groups + calibration_groups:].index],
        },
        "event_group_count": group_count,
    }


def _runtime_manifest() -> dict[str, Any]:
    dependency_lock = Path("backend/locks/core-py312.txt")
    lock_hash = hashlib.sha256(dependency_lock.read_bytes()).hexdigest() if dependency_lock.exists() else None
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


def build_reproducibility_manifest(
    frame: pd.DataFrame,
    *,
    config: ReproducibilityConfig | None = None,
    snapshot_path: Path | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonicalize rows, compute the content hash and build split metadata."""
    policy = config or ReproducibilityConfig()
    enriched = enrich_training_groups(frame, config=policy)
    records = [canonical_row(row) for row in enriched.to_dict(orient="records")]
    records.sort(key=lambda row: (
        str(row.get("event_group_id") or ""),
        str(row.get("timestamp") or ""),
        int(row.get("label") or 0),
        str(row.get("sample_id") or ""),
        str(row.get("lat") or ""),
        str(row.get("lng") or ""),
    ))
    lines = b"".join(canonical_json_bytes(record) + b"\n" for record in records)
    snapshot_hash = hashlib.sha256(lines).hexdigest()
    if snapshot_path is not None:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(lines)
        if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != snapshot_hash:
            raise TrainingReproducibilityError("snapshot hash changed during write")

    timestamps = pd.to_datetime(enriched["timestamp"], utc=True)
    split_boundaries = _group_boundaries(enriched, policy)
    seasons = sorted({str(value) for value in enriched["season_id"]})
    sources = sorted({str(value) for value in enriched.get("label_source", pd.Series(dtype=str))})
    positive_rows = enriched[enriched["label"].astype(int) == 1] if "label" in enriched.columns else enriched.iloc[0:0]
    positive_seasons = sorted({str(value) for value in positive_rows["season_id"]})
    positive_sources = sorted({
        str(value)
        for value in positive_rows.get("label_source", pd.Series(dtype=str))
        if str(value).strip()
        and not str(value).lower().startswith(("synthetic_", "cold_start_"))
    })
    regions = sorted({str(value) for value in enriched["region_key"]})
    return {
        "version": REPRODUCIBILITY_VERSION,
        "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_hash": snapshot_hash,
        "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
        "row_count": len(records),
        "columns": sorted(records[0].keys()) if records else [],
        "event_group_count": int(enriched["event_group_id"].nunique()),
        "spatial_group_count": int(enriched["spatial_group_id"].nunique()),
        "season_ids": seasons,
        "source_ids": sources,
        "positive_season_ids": positive_seasons,
        "positive_source_ids": positive_sources,
        "region_keys": regions,
        "oldest_timestamp": timestamps.min().isoformat().replace("+00:00", "Z"),
        "newest_timestamp": timestamps.max().isoformat().replace("+00:00", "Z"),
        "split_boundaries": split_boundaries,
        "group_policy": {
            "spatial_bin_km": policy.spatial_bin_km,
            "season_start_months": dict(REGION_SEASON_START_MONTHS),
            "paired_negatives_share_event_group": True,
        },
        "runtime": dict(runtime or _runtime_manifest()),
    }


def validate_reproducibility_manifest(
    manifest: Mapping[str, Any],
    *,
    strict: bool = True,
    config: ReproducibilityConfig | None = None,
) -> dict[str, Any]:
    """Validate evidence needed before model fitting or promotion."""
    policy = config or ReproducibilityConfig()
    errors: list[str] = []
    required = ("snapshot_hash", "row_count", "event_group_count", "split_boundaries", "runtime")
    for key in required:
        if not manifest.get(key):
            errors.append(f"missing {key}")
    if int(manifest.get("row_count") or 0) < 1:
        errors.append("row_count must be positive")
    if int(manifest.get("event_group_count") or 0) < 3:
        errors.append("at least three event groups are required")
    seasons = [str(value) for value in manifest.get("season_ids") or []]
    if len(set(seasons)) < policy.minimum_seasons:
        errors.append(f"minimum seasons not met: {len(set(seasons))} < {policy.minimum_seasons}")
    positive_seasons = {str(value) for value in manifest.get("positive_season_ids") or []}
    if len(positive_seasons) < policy.minimum_positive_seasons:
        errors.append(
            "minimum positive seasons not met: "
            f"{len(positive_seasons)} < {policy.minimum_positive_seasons}"
        )
    positive_sources = {str(value) for value in manifest.get("positive_source_ids") or []}
    if len(positive_sources) < policy.minimum_positive_sources:
        errors.append(
            "independent positive label sources not met: "
            f"{len(positive_sources)} < {policy.minimum_positive_sources}"
        )
    oldest = pd.to_datetime(manifest.get("oldest_timestamp"), utc=True, errors="coerce")
    newest = pd.to_datetime(manifest.get("newest_timestamp"), utc=True, errors="coerce")
    span_days = None
    if pd.notna(oldest) and pd.notna(newest):
        span_days = float((newest - oldest).total_seconds() / 86400.0)
        if span_days < policy.minimum_span_days:
            errors.append(f"minimum time span not met: {span_days:.3f} < {policy.minimum_span_days}")
    boundaries = manifest.get("split_boundaries")
    if isinstance(boundaries, Mapping):
        splits = [boundaries.get(name) for name in ("train", "calibration", "test")]
        if any(not isinstance(split, Mapping) or not split.get("event_group_ids") for split in splits):
            errors.append("train/calibration/test boundaries must contain event groups")
        else:
            sets = [set(split["event_group_ids"]) for split in splits]
            if any(sets[index] & sets[other] for index in range(3) for other in range(index + 1, 3)):
                errors.append("event groups overlap across train/calibration/test")
    report = {
        "version": REPRODUCIBILITY_VERSION,
        "passed": not errors,
        "strict": strict,
        "errors": errors,
        "snapshot_hash": manifest.get("snapshot_hash"),
        "row_count": manifest.get("row_count"),
        "season_count": len(set(seasons)),
        "positive_season_count": len(positive_seasons),
        "positive_source_count": len(positive_sources),
        "span_days": round(span_days, 3) if span_days is not None else None,
    }
    if strict and errors:
        raise TrainingReproducibilityError("; ".join(errors))
    return report


def build_training_evidence(
    frame: pd.DataFrame,
    *,
    artifact_dir: Path | None = None,
    strict: bool = False,
    config: ReproducibilityConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Build frame groups, manifest and preflight report in one call."""
    policy = config or ReproducibilityConfig()
    snapshot_path = artifact_dir / "event_rows.jsonl" if artifact_dir is not None else None
    enriched = enrich_training_groups(frame, config=policy)
    manifest = build_reproducibility_manifest(
        enriched,
        config=policy,
        snapshot_path=snapshot_path,
    )
    report = validate_reproducibility_manifest(manifest, strict=strict, config=policy)
    return enriched, manifest, report
