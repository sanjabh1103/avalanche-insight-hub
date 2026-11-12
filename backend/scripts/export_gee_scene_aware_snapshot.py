#!/usr/bin/env python3
"""Build a bounded, read-only, scene-aware GEE Sentinel-1 snapshot.

The normal GEE runtime can persist scene lineage as part of its operational
path.  This exporter replaces that callback with a local read-only callback,
preserves scene IDs and sensing windows as interval-censored evidence, and
writes no Supabase rows.  Completed chunks are atomically cached so a stalled
Earth Engine request can be resumed without repeating earlier work.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import re
import signal
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


GEE_SCENE_AWARE_SNAPSHOT_VERSION = "mvp4_gee_scene_aware_interval_snapshot_v1"
GEE_SCENE_CHUNK_CACHE_VERSION = "mvp4_gee_scene_chunk_cache_v1"
SOURCE_KEY = "gee_sar_scene_aware"
ORIGIN_SOURCE_FAMILY = "gee_sar_sentinel1_scene_detection"
LICENSE_REVIEW_ID = "mvp4-gee-sar-scene-aware-api-terms-rights-pending-20260804"
LICENSE_STATUS = "pending_rights_review"
LICENSE_TERMS_URL = "https://developers.google.com/earth-engine/reference/Additional.API.Terms"
LICENSE_REUSE_SCOPE = (
    "pending Earth Engine account/use/output scope review; underlying Sentinel terms are not blanket clearance"
)
REGION_SEASON_START_MONTHS = {
    "himalayas_nepal": 11,
    "pir_panjal_nw_himalaya": 11,
}
REGION_SEASON_END_MONTHS = {
    "himalayas_nepal": 5,
    "pir_panjal_nw_himalaya": 5,
}
_POINT_RE = re.compile(
    r"POINT\s*\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)",
    re.IGNORECASE,
)


class GeeSceneAwareSnapshotError(ValueError):
    """Raised when the scene-aware snapshot contract cannot be satisfied."""


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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise GeeSceneAwareSnapshotError(f"missing {field}")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GeeSceneAwareSnapshotError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GeeSceneAwareSnapshotError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _coordinate(value: Any, *, field: str, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise GeeSceneAwareSnapshotError(f"invalid {field}") from exc
    if not math.isfinite(parsed) or not lower <= parsed <= upper:
        raise GeeSceneAwareSnapshotError(f"invalid {field}")
    return parsed


def _point(raw: Mapping[str, Any], features: Mapping[str, Any]) -> tuple[float, float]:
    centroid = features.get("sar_centroid")
    if isinstance(centroid, Mapping):
        try:
            return (
                _coordinate(centroid.get("lat"), field="lat", lower=-90.0, upper=90.0),
                _coordinate(centroid.get("lng"), field="lng", lower=-180.0, upper=180.0),
            )
        except GeeSceneAwareSnapshotError:
            pass
    match = _POINT_RE.search(str(raw.get("location") or ""))
    if not match:
        raise GeeSceneAwareSnapshotError("missing SAR centroid/location")
    return (
        _coordinate(match.group(2), field="lat", lower=-90.0, upper=90.0),
        _coordinate(match.group(1), field="lng", lower=-180.0, upper=180.0),
    )


def _scene_ids(raw: Mapping[str, Any], features: Mapping[str, Any]) -> list[str]:
    values = raw.get("source_scene_ids")
    if not isinstance(values, list) or not values:
        values = features.get("sar_scene_ids")
    if not isinstance(values, list):
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _season_id(value: datetime, region_key: str) -> str:
    start_month = REGION_SEASON_START_MONTHS.get(region_key, 7)
    year = value.year if value.month >= start_month else value.year - 1
    return f"{year}-{year + 1}"


def iter_chunk_windows(
    *,
    region_key: str,
    start: datetime,
    end: datetime,
    chunk_days: int,
    snow_season_only: bool = False,
) -> Iterable[tuple[datetime, datetime]]:
    """Yield deterministic query windows, optionally restricted to November-April."""
    if end <= start:
        raise ValueError("end must be after start")
    if chunk_days <= 0:
        raise ValueError("chunk_days must be positive")
    if snow_season_only and region_key not in REGION_SEASON_END_MONTHS:
        raise ValueError(f"no snow-season window is configured for {region_key}")

    if not snow_season_only:
        cursor = start
        while cursor < end:
            window_end = min(cursor + timedelta(days=chunk_days), end)
            yield cursor, window_end
            cursor = window_end
        return

    season_start_month = REGION_SEASON_START_MONTHS[region_key]
    season_end_month = REGION_SEASON_END_MONTHS[region_key]
    for season_year in range(start.year - 1, end.year + 1):
        season_start = datetime(season_year, season_start_month, 1, tzinfo=timezone.utc)
        season_end = datetime(season_year + 1, season_end_month, 1, tzinfo=timezone.utc)
        cursor = max(start, season_start)
        season_limit = min(end, season_end)
        while cursor < season_limit:
            window_end = min(cursor + timedelta(days=chunk_days), season_limit)
            yield cursor, window_end
            cursor = window_end


def _lineage_by_scene(raw: Mapping[str, Any], features: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    refs = features.get("scene_lineage_refs")
    if not isinstance(refs, list):
        refs = raw.get("scene_lineage_refs")
    if not isinstance(refs, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        scene_id = str(ref.get("scene_id") or "").strip()
        if scene_id:
            output[scene_id] = {
                "acquisition_time": ref.get("acquisition_time"),
                "orbit": ref.get("orbit"),
                "coverage_state": ref.get("coverage_state"),
            }
    return output


def _has_complete_scene_acquisition_times(events: Sequence[Mapping[str, Any]]) -> bool:
    """Return false for a cached chunk whose scene lineage is incomplete."""
    for raw in events:
        if not isinstance(raw, Mapping):
            return False
        features = raw.get("features") if isinstance(raw.get("features"), Mapping) else {}
        scene_ids = _scene_ids(raw, features)
        if not scene_ids:
            return False
        lineage = _lineage_by_scene(raw, features)
        if any(not str(lineage.get(scene_id, {}).get("acquisition_time") or "").strip() for scene_id in scene_ids):
            return False
    return True


def _normalise_event(
    raw: Mapping[str, Any],
    *,
    region_key: str,
    index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(raw, Mapping):
        raise GeeSceneAwareSnapshotError("raw GEE event must be an object")
    features = raw.get("features") if isinstance(raw.get("features"), Mapping) else {}
    observed_region = str(features.get("region_key") or region_key).strip()
    if observed_region != region_key:
        raise GeeSceneAwareSnapshotError("raw GEE event region does not match requested region")
    scene_ids = _scene_ids(raw, features)
    if not scene_ids:
        raise GeeSceneAwareSnapshotError("raw GEE event has no source scene IDs")

    start = _parse_utc(
        features.get("sar_window_start") or raw.get("event_time_start"),
        field="sar_window_start",
    )
    end = _parse_utc(
        features.get("sar_window_end") or raw.get("event_time_end"),
        field="sar_window_end",
    )
    if end <= start:
        raise GeeSceneAwareSnapshotError("sar_window_end must be after sar_window_start")
    lat, lng = _point(raw, features)
    raw_hash = _sha256(_canonical_bytes(raw))
    source_event_id = f"gee-scene:{region_key}:{raw_hash[:24]}"
    lineage = _lineage_by_scene(raw, features)
    row = {
        "source_key": SOURCE_KEY,
        "origin_source_family": ORIGIN_SOURCE_FAMILY,
        "source_event_id": source_event_id,
        "external_id": source_event_id,
        "event_group_id": source_event_id,
        "region_key": region_key,
        "lat": lat,
        "lng": lng,
        "event_time_start": _iso(start),
        "event_time_end": _iso(end),
        "feature_cutoff_at": None,
        "label": 1,
        "label_time_contract": "interval_censored_core_v1",
        "timestamp_precision": "interval",
        "location_precision": "sar_polygon_centroid",
        "source_scene_ids": scene_ids,
        "source_row_sha256": raw_hash,
        "source_reference": "COPERNICUS/S1_GRD via Google Earth Engine",
        "source_provenance_review_status": "captured_pending_review",
        "source_overlap_review_status": "pending",
        "license_review_id": LICENSE_REVIEW_ID,
        "license_status": LICENSE_STATUS,
        "license_terms_url": LICENSE_TERMS_URL,
        "license_reuse_scope": LICENSE_REUSE_SCOPE,
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
        "shadow_only": True,
        "metadata": {
            "raw_event_index": index,
            "raw_event_sha256": raw_hash,
            "source_model": raw.get("source_model"),
            "scene_count": features.get("scene_count"),
            "sar_scene_time_summary": features.get("sar_scene_time"),
            "sar_window_start": _iso(start),
            "sar_window_end": _iso(end),
            "query_window_source": features.get("query_window_source"),
            "source_query_window_start": raw.get("source_query_window_start"),
            "source_query_window_end": raw.get("source_query_window_end"),
            "scene_lineage_sha256": features.get("scene_lineage_sha256"),
            "scene_lineage_refs": lineage,
            "sar_coverage_state": features.get("sar_coverage_state"),
            "training_bucket": features.get("training_bucket"),
        },
    }
    scenes = [
        {
            "region_key": region_key,
            "sensor": "sentinel1_gee",
            "scene_id": scene_id,
            "acquisition_time": lineage.get(scene_id, {}).get("acquisition_time"),
            "orbit": lineage.get(scene_id, {}).get("orbit"),
            "coverage_state": lineage.get(scene_id, {}).get("coverage_state"),
            "source_event_id": source_event_id,
            "source_window_start": _iso(start),
            "source_window_end": _iso(end),
            "lineage_review_status": "captured_pending_review",
        }
        for scene_id in scene_ids
    ]
    return row, scenes


def build_snapshot(
    raw_events_by_region: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Normalize raw scene-aware events without promoting them."""
    rows: list[dict[str, Any]] = []
    scene_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    excluded: Counter[str] = Counter()
    seen_raw_hashes: set[str] = set()
    for region_key in sorted(raw_events_by_region):
        for index, raw in enumerate(raw_events_by_region[region_key]):
            try:
                raw_hash = _sha256(_canonical_bytes(raw))
                if raw_hash in seen_raw_hashes:
                    excluded["duplicate_raw_event"] += 1
                    continue
                row, scenes = _normalise_event(raw, region_key=region_key, index=index)
            except GeeSceneAwareSnapshotError as exc:
                reason = str(exc)
                if reason == "raw GEE event has no source scene IDs":
                    excluded["missing_scene_ids"] += 1
                elif "region" in reason:
                    excluded["region_mismatch"] += 1
                elif "window" in reason:
                    excluded["invalid_interval"] += 1
                else:
                    excluded["invalid_raw_event"] += 1
                continue
            seen_raw_hashes.add(raw_hash)
            rows.append(row)
            for scene in scenes:
                scene_by_key.setdefault((region_key, scene["scene_id"]), scene)

    rows.sort(key=lambda row: (row["region_key"], row["event_time_start"], row["source_event_id"]))
    scenes = [scene_by_key[key] for key in sorted(scene_by_key)]
    event_payload = b"".join(_canonical_bytes(row) for row in rows)
    scene_payload = b"".join(_canonical_bytes(scene) for scene in scenes)
    seasons_by_region = {
        region_key: sorted(
            {
                _season_id(
                    datetime.fromisoformat(row["event_time_start"].replace("Z", "+00:00")),
                    region_key,
                )
                for row in rows
                if row["region_key"] == region_key
            }
        )
        for region_key in sorted(raw_events_by_region)
    }
    seasons = sorted({season for values in seasons_by_region.values() for season in values})
    body: dict[str, Any] = {
        "snapshot_schema_version": GEE_SCENE_AWARE_SNAPSHOT_VERSION,
        "source_key": SOURCE_KEY,
        "origin_source_family": ORIGIN_SOURCE_FAMILY,
        "source_role": "independent_sar_derived_interval_shadow",
        "source_collection": "COPERNICUS/S1_GRD",
        "label_time_contract": "interval_censored_core_v1",
        "license_status": LICENSE_STATUS,
        "license_review_id": LICENSE_REVIEW_ID,
        "license_terms_url": LICENSE_TERMS_URL,
        "license_reuse_scope": LICENSE_REUSE_SCOPE,
        "raw_record_count": sum(len(values) for values in raw_events_by_region.values()),
        "included_record_count": len(rows),
        "excluded_record_counts": dict(sorted(excluded.items())),
        "event_rows_sha256": _sha256(event_payload),
        "scene_manifest_sha256": _sha256(scene_payload),
        "positive_season_ids": seasons,
        "positive_season_count": len(seasons),
        "positive_seasons_by_region": seasons_by_region,
        "positive_source_ids": [SOURCE_KEY] if rows else [],
        "positive_source_count": 1 if rows else 0,
        "origin_source_families": [ORIGIN_SOURCE_FAMILY] if rows else [],
        "target_regions": {
            region_key: {
                "season_start_month": REGION_SEASON_START_MONTHS.get(region_key, 7),
            }
            for region_key in sorted(raw_events_by_region)
        },
        "regions": sorted(raw_events_by_region),
        "exact_timestamp_record_count": 0,
        "bounded_interval_record_count": len(rows),
        "source_scene_reference_count": sum(len(row["source_scene_ids"]) for row in rows),
        "unique_scene_id_count": len(scenes),
        "missing_scene_acquisition_time_count": sum(
            1 for scene in scenes if not str(scene.get("acquisition_time") or "").strip()
        ),
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
        "shadow_only": True,
        "feature_cutoff_required": True,
        "feature_cutoff_status": "pending_explicit_feature_snapshot",
        "interval_training_ready": False,
        "review_status": (
            "scene_provenance_captured_pending_time_rights_overlap_review"
            if rows
            else "no_scene_aware_rows"
        ),
        "required_next_action": (
            "Review scene-to-event semantics, source rights, overlap, and feature cutoffs before interval training."
            if rows
            else "Repair the GEE extraction or credential path before attempting a source snapshot."
        ),
        "events_path": "events.jsonl",
        "source_scenes_path": "source_scenes.jsonl",
    }
    body["manifest_hash"] = _sha256(_canonical_bytes(body))
    return rows, body, scenes


def write_snapshot(
    output_dir: Path,
    rows: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    scenes: Iterable[Mapping[str, Any]],
) -> None:
    """Write the final snapshot only after all payload hashes validate."""
    row_list = [dict(row) for row in rows]
    scene_list = [dict(scene) for scene in scenes]
    event_payload = b"".join(_canonical_bytes(row) for row in row_list)
    scene_payload = b"".join(_canonical_bytes(scene) for scene in scene_list)
    if _sha256(event_payload) != manifest.get("event_rows_sha256"):
        raise GeeSceneAwareSnapshotError("event payload hash does not match manifest")
    if _sha256(scene_payload) != manifest.get("scene_manifest_sha256"):
        raise GeeSceneAwareSnapshotError("scene payload hash does not match manifest")
    manifest_body = {str(key): value for key, value in manifest.items() if key != "manifest_hash"}
    if _sha256(_canonical_bytes(manifest_body)) != manifest.get("manifest_hash"):
        raise GeeSceneAwareSnapshotError("manifest hash does not match manifest content")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "events.jsonl").write_bytes(event_payload)
    (output_dir / "source_scenes.jsonl").write_bytes(scene_payload)
    (output_dir / "snapshot_manifest.json").write_text(
        json.dumps(dict(manifest), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "ATTRIBUTION.md").write_text(
        "# GEE scene-aware interval snapshot\n\n"
        "This bounded read-only export preserves Sentinel-1 scene IDs and sensing windows. "
        "It makes no exact avalanche-occurrence-time claim. Rights, overlap, feature cutoffs, "
        "and scientist review remain pending.\n",
        encoding="utf-8",
    )


def _chunk_cache_path(cache_dir: Path, region_key: str, start: datetime, end: datetime) -> Path:
    safe_region = re.sub(r"[^A-Za-z0-9_.-]+", "_", region_key).strip("._") or "region"
    return cache_dir / safe_region / f"{start.strftime('%Y%m%dT%H%M%SZ')}__{end.strftime('%Y%m%dT%H%M%SZ')}.json"


def _read_chunk_cache(
    path: Path,
    *,
    region_key: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("raw_events")
        if payload.get("cache_schema_version") != GEE_SCENE_CHUNK_CACHE_VERSION:
            return None
        if payload.get("region_key") != region_key or payload.get("start") != _iso(start) or payload.get("end") != _iso(end):
            return None
        if not isinstance(events, list) or not all(isinstance(event, Mapping) for event in events):
            return None
        if payload.get("raw_record_count") != len(events):
            return None
        if payload.get("raw_events_sha256") != _sha256(_canonical_bytes(events)):
            return None
        return [dict(event) for event in events]
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_chunk_cache(
    cache_dir: Path,
    *,
    region_key: str,
    start: datetime,
    end: datetime,
    events: Sequence[Mapping[str, Any]],
) -> Path:
    event_list = [dict(event) for event in events]
    payload = {
        "cache_schema_version": GEE_SCENE_CHUNK_CACHE_VERSION,
        "region_key": region_key,
        "start": _iso(start),
        "end": _iso(end),
        "raw_record_count": len(event_list),
        "raw_events_sha256": _sha256(_canonical_bytes(event_list)),
        "raw_events": event_list,
    }
    path = _chunk_cache_path(cache_dir, region_key, start, end)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return path


@contextmanager
def _chunk_timeout(seconds: float | None):
    if seconds is None or seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)

    def _alarm_handler(_signum, _frame):
        raise TimeoutError(f"GEE chunk exceeded {seconds:g}s")

    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


@contextmanager
def _gee_request_deadline(gee_module: Any, seconds: float | None):
    """Apply the Earth Engine client's per-request deadline when requested.

    The exporter makes synchronous ``getInfo`` calls.  The signal-based chunk
    guard remains useful as an outer budget, but the Earth Engine client also
    needs its own RPC deadline so a lower-level request cannot remain blocked
    until the chunk guard or workflow timeout.  Restore the prior client
    deadline after the chunk so this read-only exporter does not leak process
    configuration into a caller.
    """
    if seconds is None or seconds <= 0:
        yield
        return
    data = getattr(gee_module, "data", None)
    set_deadline = getattr(data, "setDeadline", None)
    state_getter = getattr(data, "_get_state", None)
    if not callable(set_deadline):
        raise GeeSceneAwareSnapshotError(
            "requested GEE request timeout but the Earth Engine client does not expose data.setDeadline"
        )
    previous_deadline_ms = 0.0
    if callable(state_getter):
        try:
            previous_deadline_ms = float(getattr(state_getter(), "deadline_ms", 0.0) or 0.0)
        except (TypeError, ValueError):
            previous_deadline_ms = 0.0
    set_deadline(float(seconds) * 1000.0)
    try:
        yield
    finally:
        set_deadline(previous_deadline_ms)


def _read_only_scene_lineage(**kwargs: Any) -> list[dict[str, Any]]:
    """Mirror the extractor's lineage shape without any remote call."""
    scene_ids = kwargs.get("scene_ids") or []
    orbits = kwargs.get("orbits") or []
    acquisition_times = kwargs.get("acquisition_times") or []
    metadata = dict(kwargs.get("metadata") or {})
    rows = []
    for index, scene_id in enumerate(scene_ids):
        normalized = str(scene_id).strip()
        if not normalized:
            continue
        rows.append(
            {
                "region_key": kwargs.get("region_key"),
                "sensor": kwargs.get("sensor"),
                "scene_id": normalized,
                "orbit": orbits[index] if index < len(orbits) else None,
                "acquisition_time": acquisition_times[index] if index < len(acquisition_times) else None,
                "cloud_cover": None,
                "coverage_state": kwargs.get("coverage_state"),
                "eecu_cost": None,
                "task_id": kwargs.get("task_id"),
                "metadata": {
                    **metadata,
                    "lineage_method": "gee_s1_scene_catalog_v1",
                    "persisted": False,
                    "read_only_export": True,
                },
            }
        )
    return rows


@contextmanager
def _force_read_only_lineage(gee_module: Any):
    original = getattr(gee_module, "_persist_scene_lineage", None)
    if original is None:
        yield
        return
    gee_module._persist_scene_lineage = _read_only_scene_lineage
    try:
        yield
    finally:
        gee_module._persist_scene_lineage = original


def _attach_query_window(
    events: Iterable[Mapping[str, Any]],
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Bind raw detections to the filterDate interval, never to a point time."""
    window_start = _iso(start)
    window_end = _iso(end)
    enriched: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            enriched.append(dict(event))
            continue
        copy = dict(event)
        features = dict(event.get("features") or {}) if isinstance(event.get("features"), Mapping) else {}
        features.setdefault("sar_window_start", window_start)
        features.setdefault("sar_window_end", window_end)
        features.setdefault("timestamp_precision", "bounded_interval")
        features.setdefault("query_window_source", "gee_filter_date_bounds")
        copy["features"] = features
        copy.setdefault("source_query_window_start", window_start)
        copy.setdefault("source_query_window_end", window_end)
        enriched.append(copy)
    return enriched


def collect_from_gee(
    *,
    region_keys: Sequence[str],
    start: datetime,
    end: datetime,
    chunk_days: int,
    cache_dir: Path | None = None,
    chunk_timeout_seconds: float | None = None,
    request_timeout_seconds: float | None = None,
    progress: bool = True,
    snow_season_only: bool = False,
    require_scene_acquisition_times: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Collect raw chunks with read-only lineage and deterministic resumption."""
    if end <= start:
        raise ValueError("end must be after start")
    if chunk_days <= 0:
        raise ValueError("chunk_days must be positive")
    if chunk_timeout_seconds is not None and chunk_timeout_seconds < 0:
        raise ValueError("chunk_timeout_seconds must be non-negative")
    if request_timeout_seconds is not None and request_timeout_seconds < 0:
        raise ValueError("request_timeout_seconds must be non-negative")
    import backend.gee_extractor as gee
    from backend.common.regions import load_regions

    requested = {str(value).strip() for value in region_keys if str(value).strip()}
    configured = {region.key: region for region in load_regions()}
    unknown = sorted(requested - set(configured))
    if unknown:
        raise ValueError(f"unknown region key(s): {', '.join(unknown)}")

    cache_root = Path(cache_dir) if cache_dir is not None else None
    ee_session = None
    raw_by_region: dict[str, list[dict[str, Any]]] = {key: [] for key in sorted(requested)}
    with _force_read_only_lineage(gee):
        for region_key in sorted(requested):
            for cursor, window_end in iter_chunk_windows(
                region_key=region_key,
                start=start,
                end=end,
                chunk_days=chunk_days,
                snow_season_only=snow_season_only,
            ):
                cached_events = (
                    _read_chunk_cache(
                        _chunk_cache_path(cache_root, region_key, cursor, window_end),
                        region_key=region_key,
                        start=cursor,
                        end=window_end,
                    )
                    if cache_root is not None
                    else None
                )
                if (
                    cached_events is not None
                    and require_scene_acquisition_times
                    and not _has_complete_scene_acquisition_times(cached_events)
                ):
                    if progress:
                        print(
                            f"[gee] {region_key} {_iso(cursor)}..{_iso(window_end)} "
                            "source=cache status=refresh_incomplete_scene_lineage",
                            file=sys.stderr,
                            flush=True,
                        )
                    cached_events = None
                if cached_events is not None:
                    events = cached_events
                    source = "cache"
                else:
                    if progress:
                        print(
                            f"[gee] {region_key} {_iso(cursor)}..{_iso(window_end)} source=live status=fetching",
                            file=sys.stderr,
                            flush=True,
                        )
                    if ee_session is None:
                        ee_session = gee._initialize_ee()
                    process_kwargs = {
                        "start_date": cursor,
                        "end_date": window_end,
                    }
                    if "persist_lineage" in inspect.signature(gee._process_region).parameters:
                        process_kwargs["persist_lineage"] = False
                    try:
                        with _gee_request_deadline(ee_session, request_timeout_seconds):
                            with _chunk_timeout(chunk_timeout_seconds):
                                events = list(gee._process_region(ee_session, configured[region_key], **process_kwargs) or [])
                    except TimeoutError as exc:
                        raise GeeSceneAwareSnapshotError(
                            f"GEE chunk timed out for {region_key} {_iso(cursor)}..{_iso(window_end)}"
                        ) from exc
                    events = _attach_query_window(events, start=cursor, end=window_end)
                    if cache_root is not None:
                        _write_chunk_cache(
                            cache_root,
                            region_key=region_key,
                            start=cursor,
                            end=window_end,
                            events=events,
                        )
                    source = "live"
                if source == "cache":
                    events = _attach_query_window(events, start=cursor, end=window_end)
                raw_by_region[region_key].extend(events)
                if progress:
                    print(
                        f"[gee] {region_key} {_iso(cursor)}..{_iso(window_end)} source={source} "
                        f"status=complete raw_events={len(events)}",
                        file=sys.stderr,
                        flush=True,
                    )
    return build_snapshot(raw_by_region)


def _parse_cli_time(value: str, *, field: str) -> datetime:
    return _parse_utc(value, field=field)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-key", action="append", default=[])
    parser.add_argument("--start", default="2021-11-01T00:00:00Z")
    parser.add_argument("--end", default="2024-04-30T00:00:00Z")
    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--chunk-timeout-seconds", type=float, default=300.0)
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=None,
        help="Set the Earth Engine client's per-RPC deadline; 0 disables the client deadline",
    )
    parser.add_argument("--snow-season-only", action="store_true")
    parser.add_argument(
        "--require-scene-acquisition-times",
        action="store_true",
        help="Refresh cached chunks until every referenced scene has an acquisition time",
    )
    args = parser.parse_args(argv)
    start = _parse_cli_time(args.start, field="start")
    end = _parse_cli_time(args.end, field="end")
    region_keys = args.region_key or ["himalayas_nepal"]
    cache_dir = args.cache_dir or args.output_dir / ".chunks"
    rows, manifest, scenes = collect_from_gee(
        region_keys=region_keys,
        start=start,
        end=end,
        chunk_days=args.chunk_days,
        cache_dir=cache_dir,
        chunk_timeout_seconds=args.chunk_timeout_seconds,
        request_timeout_seconds=args.request_timeout_seconds,
        snow_season_only=args.snow_season_only,
        require_scene_acquisition_times=args.require_scene_acquisition_times,
    )
    write_snapshot(args.output_dir, rows, manifest, scenes)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "cache_dir": str(cache_dir),
                "request_timeout_seconds": args.request_timeout_seconds,
                "included_record_count": manifest["included_record_count"],
                "positive_season_ids": manifest["positive_season_ids"],
                "unique_scene_id_count": manifest["unique_scene_id_count"],
                "missing_scene_acquisition_time_count": manifest["missing_scene_acquisition_time_count"],
                "event_rows_sha256": manifest["event_rows_sha256"],
                "scene_manifest_sha256": manifest["scene_manifest_sha256"],
                "manifest_hash": manifest["manifest_hash"],
                "review_status": manifest["review_status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
