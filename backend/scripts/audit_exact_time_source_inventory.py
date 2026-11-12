#!/usr/bin/env python3
"""Inventory exact-time evidence without promoting weak time semantics.

This is a read-only, dependency-free audit.  It verifies every materialized
snapshot hash, counts the timestamp precision actually present in JSONL rows,
and reports why an exact-time source is or is not usable for core training.
Derived multi-source catalogs are listed but excluded from aggregate source
counts so that a catalog cannot masquerade as an additional independent source.

Bounded intervals are reported separately.  The report deliberately never
creates an event timestamp from an interval midpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.common.label_time_contract import (
    has_approved_occurrence_time_review,
)


EXACT_TIMESTAMP_PRECISIONS = {"timestamp", "instant", "exact_timestamp", "exact"}
DERIVED_SOURCE_KEYS = {"mvp4_reviewed_hma_catalog"}
FEATURE_SNAPSHOT_SCHEMAS = {"mvp4_station_free_feature_snapshot_v1"}
REPORT_VERSION = "mvp4_exact_time_source_inventory_v1"
GAP_REPORT_VERSION = "mvp4_bounded_interval_gap_report_v1"


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_season(row: dict[str, Any], manifest: dict[str, Any]) -> str | None:
    timestamp = _parse_timestamp(row.get("event_time") or row.get("event_time_start"))
    if timestamp is None:
        return None
    region_key = str(row.get("region_key") or "").strip()
    starts = manifest.get("region_season_start_months") or {}
    try:
        start_month = int(starts.get(region_key, 7))
    except (TypeError, ValueError):
        start_month = 7
    season_year = timestamp.year if timestamp.month >= start_month else timestamp.year - 1
    return f"{season_year}-{season_year + 1}"


def _precision(row: dict[str, Any]) -> str:
    marker = str(row.get("timestamp_precision") or "unknown").strip().lower() or "unknown"
    exact_value = row.get("event_time") or row.get("timestamp")
    if marker in EXACT_TIMESTAMP_PRECISIONS and _parse_timestamp(exact_value) is not None:
        return "exact_timestamp"
    if marker == "day" and (
        _parse_timestamp(exact_value) is not None
        or _parse_timestamp(row.get("event_time_start")) is not None
    ):
        return "day"
    if (
        _parse_timestamp(row.get("event_time_start")) is not None
        and _parse_timestamp(row.get("event_time_end")) is not None
        and _parse_timestamp(row.get("event_time_end")) > _parse_timestamp(row.get("event_time_start"))
    ):
        return "bounded_interval"
    return "unknown"


def _load_snapshot(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], bytes]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events_path = manifest_path.parent / str(manifest.get("events_path") or "events.jsonl")
    payload = events_path.read_bytes()
    expected_hash = str(manifest.get("event_rows_sha256") or "").strip()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if not expected_hash or expected_hash != actual_hash:
        raise ValueError(f"event snapshot hash mismatch: {events_path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"event snapshot row is not an object: {events_path}:{line_number}")
        rows.append(row)
    return manifest, rows, payload


def _manifest_source_keys(manifest: dict[str, Any]) -> list[str]:
    values = manifest.get("source_keys")
    if isinstance(values, list):
        keys = sorted({str(value).strip() for value in values if str(value).strip()})
        if keys:
            return keys
    source_key = str(manifest.get("source_key") or "").strip()
    return [source_key] if source_key else []


def _is_derived_catalog(manifest: dict[str, Any], source_keys: list[str]) -> bool:
    source_key = str(manifest.get("source_key") or "").strip()
    return source_key in DERIVED_SOURCE_KEYS or len(source_keys) > 1


def _source_scene_id_count(rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        scene_ids = row.get("source_scene_ids")
        if isinstance(scene_ids, list) and any(str(value).strip() for value in scene_ids):
            count += 1
        elif str(row.get("scene_id") or "").strip():
            count += 1
    return count


def _source_manifest_for_row(
    row: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    source_key = str(
        row.get("source_key")
        or row.get("source")
        or row.get("label_source")
        or ""
    ).strip()
    source_manifests = manifest.get("source_manifests")
    if isinstance(source_manifests, dict):
        source_manifest = source_manifests.get(source_key)
        if isinstance(source_manifest, dict):
            return source_manifest
    return manifest


def _exact_time_reviewed(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> bool:
    exact_rows = [row for row in rows if _precision(row) == "exact_timestamp"]
    return bool(exact_rows) and all(
        has_approved_occurrence_time_review(
            row,
            source_manifest=_source_manifest_for_row(row, manifest),
        )
        for row in exact_rows
    )


def _snapshot_record(manifest_path: Path, manifest: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_key = str(manifest.get("source_key") or "").strip() or "unknown"
    source_keys = _manifest_source_keys(manifest)
    derived_catalog = _is_derived_catalog(manifest, source_keys)
    precision_counts = Counter(_precision(row) for row in rows)
    exact_count = precision_counts.get("exact_timestamp", 0)
    exact_time_reviewed = _exact_time_reviewed(rows, manifest)
    interval_count = precision_counts.get("bounded_interval", 0)
    day_count = precision_counts.get("day", 0)
    regions = sorted({str(row.get("region_key") or "").strip() for row in rows if row.get("region_key")})
    seasons_by_region: dict[str, list[str]] = {}
    for region_key in regions:
        seasons_by_region[region_key] = sorted({
            season
            for row in rows
            if str(row.get("region_key") or "").strip() == region_key
            if (season := _canonical_season(row, manifest))
        })
    source_families = sorted({
        str(row.get("origin_source_family") or "").strip()
        for row in rows
        if str(row.get("origin_source_family") or "").strip()
    })
    source_families.extend(
        str(value).strip()
        for value in manifest.get("origin_source_families", [])
        if str(value).strip() and str(value).strip() not in source_families
    )
    license_status = str(
        manifest.get("license_status")
        or manifest.get("source_license_status")
        or "unknown"
    ).strip()
    blockers: set[str] = set()
    if manifest.get("training_eligible") is not True:
        blockers.add("manifest_training_eligible_false")
    if exact_count == 0:
        blockers.add("no_exact_event_timestamp")
    elif not exact_time_reviewed:
        blockers.add("exact_occurrence_time_review_not_approved")
    if interval_count:
        blockers.add("bounded_interval_rows_present")
    if license_status != "permissive_core_reviewed":
        blockers.add("license_not_core_reviewed")
    if derived_catalog:
        blockers.add("derived_catalog_not_independent_source")
    if source_key == "gee_sar":
        if manifest.get("source_scene_id_count") == 0 or _source_scene_id_count(rows) == 0:
            blockers.add("missing_source_scene_ids")
        if str(manifest.get("review_status") or "") != "approved_core":
            blockers.add("source_provenance_not_approved_core")
    exact_time_candidate = exact_count > 0 and not derived_catalog
    qualified_exact_time_candidate = exact_time_candidate and exact_time_reviewed
    core_exact_time_source = (
        qualified_exact_time_candidate
        and manifest.get("training_eligible") is True
        and license_status == "permissive_core_reviewed"
        and not blockers
    )
    return {
        "manifest_path": str(manifest_path),
        "source_key": source_key,
        "source_keys": source_keys,
        "derived_catalog": derived_catalog,
        "source_role": manifest.get("source_role"),
        "review_status": manifest.get("review_status"),
        "license_status": license_status,
        "license": manifest.get("license"),
        "source_url": manifest.get("source_url") or manifest.get("source_csv_url"),
        "origin_source_families": source_families,
        "hash_verified": True,
        "record_count": len(rows),
        "precision_counts": dict(sorted(precision_counts.items())),
        "exact_timestamp_record_count": exact_count,
        "exact_time_reviewed": exact_time_reviewed,
        "qualified_exact_time_candidate": qualified_exact_time_candidate,
        "day_record_count": day_count,
        "bounded_interval_record_count": interval_count,
        "unknown_precision_record_count": precision_counts.get("unknown", 0),
        "regions": regions,
        "positive_seasons_by_region": seasons_by_region,
        "source_scene_id_count": _source_scene_id_count(rows),
        "exact_time_candidate": exact_time_candidate,
        "core_exact_time_source": core_exact_time_source,
        "blockers": sorted(blockers),
    }


def _manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for manifest_path in sorted(root.rglob("snapshot_manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            paths.append(manifest_path)
            continue
        if (
            isinstance(manifest, dict)
            and not manifest.get("events_path")
            and (
                manifest.get("snapshot_schema_version") in FEATURE_SNAPSHOT_SCHEMAS
                or manifest.get("feature_rows_path")
            )
        ):
            continue
        paths.append(manifest_path)
    return paths


def build_evidence_inventory(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    snapshots: list[dict[str, Any]] = []
    for manifest_path in _manifest_paths(root):
        manifest, rows, _payload = _load_snapshot(manifest_path)
        snapshots.append(_snapshot_record(manifest_path, manifest, rows))
    if not snapshots:
        raise ValueError(f"no snapshot_manifest.json files found under {root}")

    standalone = [item for item in snapshots if not item["derived_catalog"]]
    blocker_counts = Counter(
        blocker
        for item in standalone
        for blocker in item["blockers"]
    )
    summary = {
        "snapshot_count": len(snapshots),
        "standalone_source_snapshot_count": len(standalone),
        "derived_catalog_count": len(snapshots) - len(standalone),
        "exact_timestamp_record_count": sum(item["exact_timestamp_record_count"] for item in standalone),
        "day_record_count": sum(item["day_record_count"] for item in standalone),
        "bounded_interval_record_count": sum(item["bounded_interval_record_count"] for item in standalone),
        "exact_time_candidate_count": sum(bool(item["exact_time_candidate"]) for item in standalone),
        "qualified_exact_time_candidate_count": sum(
            bool(item["qualified_exact_time_candidate"]) for item in standalone
        ),
        "core_exact_time_source_count": sum(bool(item["core_exact_time_source"]) for item in standalone),
        "blocking_reason_counts": dict(sorted(blocker_counts.items())),
        "inventory_is_read_only": True,
        "midpoint_substitution_used": False,
    }
    return {
        "version": REPORT_VERSION,
        "root": str(root),
        "summary": summary,
        "snapshots": snapshots,
    }


def _interval_rows(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], float]]:
    result: list[tuple[dict[str, Any], float]] = []
    for row in rows:
        if _precision(row) != "bounded_interval":
            continue
        start = _parse_timestamp(row.get("event_time_start"))
        end = _parse_timestamp(row.get("event_time_end"))
        if start is None or end is None or end <= start:
            continue
        result.append((row, (end - start).total_seconds() / 86400.0))
    return result


def build_bounded_interval_gap_report(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    source_reports: list[dict[str, Any]] = []
    total_intervals = 0
    total_exact = 0
    for manifest_path in _manifest_paths(root):
        manifest, rows, _payload = _load_snapshot(manifest_path)
        source_keys = _manifest_source_keys(manifest)
        if _is_derived_catalog(manifest, source_keys):
            continue
        intervals = _interval_rows(rows)
        if not intervals:
            continue
        widths = [width for _row, width in intervals]
        regions: Counter[str] = Counter()
        seasons: Counter[str] = Counter()
        for row, _width in intervals:
            region = str(row.get("region_key") or "unknown").strip() or "unknown"
            regions[region] += 1
            season = _canonical_season(row, manifest)
            if season:
                seasons[season] += 1
        exact_rows = sum(_precision(row) == "exact_timestamp" for row in rows)
        total_intervals += len(intervals)
        total_exact += exact_rows
        overlap_status = None
        overlap_matches = None
        overlap_ref = manifest.get("source_overlap_report")
        if overlap_ref:
            overlap_path = manifest_path.parent / str(overlap_ref)
            if overlap_path.exists():
                overlap = json.loads(overlap_path.read_text(encoding="utf-8"))
                overlap_status = overlap.get("status")
                overlap_matches = len(overlap.get("matches") or [])
        source_reports.append({
            "manifest_path": str(manifest_path),
            "source_key": str(manifest.get("source_key") or "unknown"),
            "record_count": len(rows),
            "bounded_interval_record_count": len(intervals),
            "exact_occurrence_timestamp_record_count": exact_rows,
            "interval_width_days": {
                "min": min(widths),
                "max": max(widths),
                "mean": round(statistics.mean(widths), 6),
                "median": statistics.median(widths),
            },
            "regions": dict(sorted(regions.items())),
            "positive_seasons": dict(sorted(seasons.items())),
            "overlap_report_status": overlap_status,
            "overlap_match_count": overlap_matches,
            "exact_occurrence_time_recoverability": "not_proven",
            "gap_reason_codes": [
                "no_exact_event_timestamp_in_rows",
                "explicit_interval_only",
                "midpoint_substitution_prohibited",
            ],
            "midpoint_substitution_used": False,
            "core_training_eligible": False,
        })
    if not source_reports:
        return {
            "version": GAP_REPORT_VERSION,
            "root": str(root),
            "summary": {
                "bounded_interval_record_count": 0,
                "exact_occurrence_timestamp_record_count": total_exact,
                "source_count": 0,
                "midpoint_substitution_used": False,
                "core_training_eligible": False,
                "decision": "no_bounded_interval_sources_found",
            },
            "sources": [],
        }
    return {
        "version": GAP_REPORT_VERSION,
        "root": str(root),
        "summary": {
            "bounded_interval_record_count": total_intervals,
            "exact_occurrence_timestamp_record_count": total_exact,
            "source_count": len(source_reports),
            "midpoint_substitution_used": False,
            "core_training_eligible": False,
            "decision": "blocked_until_exact_occurrence_time_source_is_proven",
        },
        "sources": sorted(source_reports, key=lambda item: item["source_key"]),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--inventory-out", type=Path, required=True)
    parser.add_argument("--gap-out", type=Path, required=True)
    args = parser.parse_args(argv)
    inventory = build_evidence_inventory(args.root)
    gap_report = build_bounded_interval_gap_report(args.root)
    _write_json(args.inventory_out, inventory)
    _write_json(args.gap_out, gap_report)
    print(json.dumps({
        "inventory_out": str(args.inventory_out),
        "gap_out": str(args.gap_out),
        "inventory_summary": inventory["summary"],
        "gap_summary": gap_report["summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
