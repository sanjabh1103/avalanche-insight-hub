#!/usr/bin/env python3
"""Audit terrain assembly for a hash-verified event snapshot.

This is an evidence-only diagnostic.  It does not fetch weather, build a
training frame, alter DEMs, or change training eligibility.  It applies the
same ``extract_cell_terrain`` implementation used by the training path and
persists stable failure reasons so a terrain-loss claim can be investigated
without rerunning a remote training job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from backend.common.real_features import extract_cell_terrain
from backend.common.regions import Region, load_regions, repo_root
from backend.common.terrain_diagnostics import (
    build_terrain_loss_report,
    classify_terrain_failure,
    validate_terrain_gate,
)
from backend.common.training_dataset import match_region, parse_point_wkt


TERRAIN_SNAPSHOT_AUDIT_VERSION = "mvp4_terrain_snapshot_audit_v1"


def _load_snapshot(manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("snapshot manifest must be a JSON object")
    raw_events_path = str(manifest.get("events_path") or "events.jsonl")
    events_path = Path(raw_events_path)
    if not events_path.is_absolute():
        events_path = manifest_path.parent / events_path
    payload = events_path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    expected_hash = str(manifest.get("event_rows_sha256") or "")
    if not expected_hash or expected_hash != actual_hash:
        raise ValueError(f"event snapshot hash mismatch: {events_path}")
    rows = [
        json.loads(line)
        for line in payload.decode("utf-8").splitlines()
        if line.strip()
    ]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"event snapshot must be non-empty JSONL: {events_path}")
    return rows, manifest, actual_hash


def _finite_coordinate(row: dict[str, Any]) -> tuple[float, float] | None:
    raw_lat = row.get("lat", row.get("latitude"))
    raw_lng = row.get("lng", row.get("longitude"))
    if raw_lat is None or raw_lng is None:
        point = parse_point_wkt(row.get("location"))
        if point is None:
            return None
        lat, lng = point
    else:
        try:
            lat, lng = float(raw_lat), float(raw_lng)
        except (TypeError, ValueError):
            return None
    if not (
        math.isfinite(lat)
        and math.isfinite(lng)
        and -90.0 <= lat <= 90.0
        and -180.0 <= lng <= 180.0
    ):
        return None
    return lat, lng


def _season_id(row: dict[str, Any], region: Region) -> str | None:
    raw = str(
        row.get("event_time")
        or row.get("timestamp")
        or row.get("event_time_start")
        or ""
    )
    if len(raw) < 10:
        return None
    try:
        event_date = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    try:
        season_start_month = int(str(region.season_start or "07-01").split("-", 1)[0])
    except (TypeError, ValueError):
        season_start_month = 7
    season_year = event_date.year if event_date.month >= season_start_month else event_date.year - 1
    return f"{season_year}-{season_year + 1}"


def _increment_nested(
    target: dict[str, Counter[str]],
    key: str,
    reason: str,
) -> None:
    target[key][reason] += 1


def _sorted_counter_map(values: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        key: dict(sorted(counter.items()))
        for key, counter in sorted(values.items())
        if counter
    }


def audit_rows(
    rows: Iterable[dict[str, Any]],
    *,
    manifest: dict[str, Any],
    snapshot_sha256: str,
    region_keys: list[str] | None = None,
    dem_root: Path | None = None,
) -> dict[str, Any]:
    configured_regions = load_regions()
    regions_by_key = {region.key: region for region in configured_regions}
    selected_keys = sorted(set(region_keys or regions_by_key.keys()))
    unknown = sorted(set(selected_keys) - set(regions_by_key))
    if unknown:
        raise ValueError(f"unknown region key(s): {unknown}")

    selected_regions = [regions_by_key[key] for key in selected_keys]
    if dem_root is None:
        configured_dem_root = str(os.getenv("DEM_ROOT") or os.getenv("DEM_DIR") or "").strip()
        effective_dem_root = (
            Path(configured_dem_root).expanduser()
            if configured_dem_root
            else repo_root() / "backend" / "data" / "dem"
        )
    else:
        effective_dem_root = dem_root.expanduser()
    raw_rows = list(rows)
    invalid_point_count = 0
    region_mismatch_count = 0
    out_of_scope_count = 0
    candidate_rows = 0
    terrain_success = 0
    missing_dem = 0
    terrain_failed = 0
    terrain_clamped = 0
    failure_reasons: Counter[str] = Counter()
    failure_reasons_by_region: dict[str, Counter[str]] = defaultdict(Counter)
    failure_reasons_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    failure_reasons_by_season: dict[str, Counter[str]] = defaultdict(Counter)
    candidates_by_region: Counter[str] = Counter()
    candidates_by_source: Counter[str] = Counter()
    candidates_by_season: Counter[str] = Counter()
    missing_dem_by_region: Counter[str] = Counter()
    missing_dem_by_source: Counter[str] = Counter()
    missing_dem_by_season: Counter[str] = Counter()
    failed_by_region: Counter[str] = Counter()
    failed_by_source: Counter[str] = Counter()
    failed_by_season: Counter[str] = Counter()
    success_by_region: Counter[str] = Counter()
    success_by_source: Counter[str] = Counter()
    success_by_season: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    season_counts: Counter[str] = Counter()
    failure_records: list[dict[str, Any]] = []

    for row in raw_rows:
        point = _finite_coordinate(row)
        if point is None:
            invalid_point_count += 1
            continue
        lat, lng = point
        explicit_region_key = str(row.get("region_key") or "").strip()
        explicit_region = regions_by_key.get(explicit_region_key)
        coordinate_region = match_region(lat, lng, configured_regions)
        if explicit_region is not None:
            if coordinate_region is None or coordinate_region.key != explicit_region.key:
                region_mismatch_count += 1
                continue
            region = explicit_region
        else:
            region = coordinate_region
        if region is None:
            region_mismatch_count += 1
            continue
        if region.key not in selected_keys:
            out_of_scope_count += 1
            continue

        candidate_rows += 1
        candidates_by_region[region.key] += 1
        source_key = str(row.get("source_key") or row.get("source") or "unknown")
        source_counts[source_key] += 1
        candidates_by_source[source_key] += 1
        season = _season_id(row, region)
        if season:
            season_counts[season] += 1
            candidates_by_season[season] += 1
        dem_path = effective_dem_root / f"{region.key}.tif"
        event_identity = str(
            row.get("event_group_id")
            or row.get("external_id")
            or row.get("id")
            or f"row-{candidate_rows}"
        )
        if not dem_path.exists():
            missing_dem += 1
            reason = "missing_dem"
            failure_reasons[reason] += 1
            failure_reasons_by_region[region.key][reason] += 1
            failure_reasons_by_source[source_key][reason] += 1
            if season:
                failure_reasons_by_season[season][reason] += 1
            missing_dem_by_region[region.key] += 1
            missing_dem_by_source[source_key] += 1
            if season:
                missing_dem_by_season[season] += 1
            failure_records.append({
                "event_group_id": event_identity,
                "external_id": row.get("external_id"),
                "source_key": source_key,
                "region_key": region.key,
                "season_id": season,
                "reason": reason,
            })
            continue
        try:
            terrain = extract_cell_terrain(str(dem_path), lat=lat, lng=lng)
            if not isinstance(terrain, dict):
                raise ValueError("terrain extractor returned a non-object")
        except Exception as exc:  # noqa: BLE001 - stable diagnostic classification
            terrain_failed += 1
            reason = classify_terrain_failure(exc)
            failure_reasons[reason] += 1
            failure_reasons_by_region[region.key][reason] += 1
            failure_reasons_by_source[source_key][reason] += 1
            if season:
                failure_reasons_by_season[season][reason] += 1
            failed_by_region[region.key] += 1
            failed_by_source[source_key] += 1
            if season:
                failed_by_season[season] += 1
            failure_records.append({
                "event_group_id": event_identity,
                "external_id": row.get("external_id"),
                "source_key": source_key,
                "region_key": region.key,
                "season_id": season,
                "reason": reason,
            })
            continue

        terrain_success += 1
        success_by_region[region.key] += 1
        success_by_source[source_key] += 1
        if season:
            success_by_season[season] += 1
        if float(terrain.get("clamped_to_bounds", 0.0) or 0.0) > 0:
            terrain_clamped += 1

    # Feed the same policy validator used by the strict training audit, while
    # keeping the snapshot row count and scope accounting explicit in output.
    gate_report = build_terrain_loss_report({
        "raw_rows": candidate_rows,
        "no_point": 0,
        "no_timestamp": 0,
        "no_region": 0,
        "no_dem": missing_dem,
        "terrain_failed": terrain_failed,
        "terrain_success": terrain_success,
        "terrain_failure_reasons": dict(failure_reasons),
        "terrain_failure_reasons_by_region": _sorted_counter_map(failure_reasons_by_region),
        "terrain_candidates_by_region": dict(candidates_by_region),
        "terrain_candidates_by_source": dict(candidates_by_source),
        "terrain_candidates_by_season": dict(candidates_by_season),
        "terrain_missing_dem_by_region": dict(missing_dem_by_region),
        "terrain_missing_dem_by_source": dict(missing_dem_by_source),
        "terrain_missing_dem_by_season": dict(missing_dem_by_season),
        "terrain_failed_by_region": dict(failed_by_region),
        "terrain_failed_by_source": dict(failed_by_source),
        "terrain_failed_by_season": dict(failed_by_season),
        "terrain_success_by_region": dict(success_by_region),
        "terrain_success_by_source": dict(success_by_source),
        "terrain_success_by_season": dict(success_by_season),
        "assembled_ok": terrain_success,
    })
    return {
        **gate_report,
        "version": TERRAIN_SNAPSHOT_AUDIT_VERSION,
        "snapshot_source_key": str(manifest.get("source_key") or "unknown"),
        "snapshot_sha256": snapshot_sha256,
        "snapshot_row_count": len(raw_rows),
        "selected_region_keys": selected_keys,
        "out_of_scope_row_count": out_of_scope_count,
        "invalid_point_count": invalid_point_count,
        "region_mismatch_count": region_mismatch_count,
        "source_counts": dict(sorted(source_counts.items())),
        "season_counts": dict(sorted(season_counts.items())),
        "terrain_clamped_count": terrain_clamped,
        "failure_reasons_by_source": _sorted_counter_map(failure_reasons_by_source),
        "failure_reasons_by_season": _sorted_counter_map(failure_reasons_by_season),
        "failure_records": failure_records,
        "gate_errors": validate_terrain_gate(gate_report),
    }


def audit_snapshot(
    manifest_path: Path,
    *,
    region_keys: list[str] | None = None,
    dem_root: Path | None = None,
) -> dict[str, Any]:
    rows, manifest, snapshot_sha256 = _load_snapshot(manifest_path)
    report = audit_rows(
        rows,
        manifest=manifest,
        snapshot_sha256=snapshot_sha256,
        region_keys=region_keys,
        dem_root=dem_root,
    )
    report["snapshot_manifest_path"] = str(manifest_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--region-keys", default="")
    parser.add_argument("--dem-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    region_keys = [key.strip() for key in args.region_keys.split(",") if key.strip()] or None
    report = audit_snapshot(
        args.snapshot_manifest,
        region_keys=region_keys,
        dem_root=args.dem_root,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "version": report["version"],
        "snapshot_sha256": report["snapshot_sha256"],
        "snapshot_row_count": report["snapshot_row_count"],
        "selected_region_keys": report["selected_region_keys"],
        "candidate_rows": report["candidate_rows"],
        "terrain_success": report["terrain_success"],
        "terrain_loss_count": report["terrain_loss_count"],
        "terrain_loss_rate": report["terrain_loss_rate"],
        "failure_reasons": report["failure_reasons"],
        "gate_errors": report["gate_errors"],
    }, indent=2, sort_keys=True))
    return 2 if args.strict and report["gate_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
