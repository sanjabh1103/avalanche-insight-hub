#!/usr/bin/env python3
"""Verify an open-forcing snapshot bundle offline, without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.open_forcing.contracts import SourceSnapshot
from backend.open_forcing.coverage import (
    AoiBounds,
    NativeForcingPoint,
    construct_aoi_coverage_plan,
)
from backend.open_forcing.open_meteo_source import OpenMeteoRunRequest, parse_open_meteo_single_run
from backend.open_forcing.replay import CoverageMask, SourceReplay
from backend.open_forcing.source_registry import ForcingSnapshotManifest, SourceRegistry


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _sha256(encoded)


def _validate_grid_descriptor(grid: Mapping[str, Any]) -> int:
    """Recompute the v1 grid hash before accepting coverage metadata."""

    required = {
        "construction",
        "target_crs",
        "target_resolution_m",
        "rows",
        "cols",
        "cell_count",
        "aoi_center_latitude",
        "aoi_center_longitude",
        "width_m",
        "height_m",
        "information_boundary",
        "grid_manifest_hash",
    }
    if not isinstance(grid, Mapping) or not required.issubset(grid):
        raise RuntimeError("snapshot grid descriptor is incomplete")
    rows = int(grid["rows"])
    cols = int(grid["cols"])
    target_resolution_m = float(grid["target_resolution_m"])
    cell_count = int(grid["cell_count"])
    if rows <= 0 or cols <= 0 or target_resolution_m <= 0 or cell_count != rows * cols:
        raise RuntimeError("snapshot grid dimensions are inconsistent")
    descriptor = {
        "construction": str(grid["construction"]),
        "target_crs": str(grid["target_crs"]),
        "target_resolution_m": target_resolution_m,
        "rows": rows,
        "cols": cols,
        "cell_count": cell_count,
        "aoi_center_latitude": float(grid["aoi_center_latitude"]),
        "aoi_center_longitude": float(grid["aoi_center_longitude"]),
        "width_m": float(grid["width_m"]),
        "height_m": float(grid["height_m"]),
        "information_boundary": str(grid["information_boundary"]),
    }
    if _canonical_hash(descriptor) != str(grid["grid_manifest_hash"]).lower():
        raise RuntimeError("snapshot grid descriptor hash mismatch")
    return cell_count


def _validate_source_point_coverage(
    record: Mapping[str, Any],
    *,
    forecast_snapshot: SourceSnapshot,
    forecast_bytes: bytes,
    cell_count: int,
) -> None:
    """Rebuild the nearest-source plan and parse its raw payload again."""

    required = {
        "source_id",
        "provider",
        "model_id",
        "run_id",
        "aoi",
        "target_rows",
        "target_cols",
        "target_resolution_m",
        "native_resolution_m",
        "required_variables",
        "valid_times",
        "native_points",
        "assignments",
        "max_assignment_distance_m",
        "coverage_fraction",
        "complete_spatial_coverage",
        "license_review_status",
        "can_enter_forcing_pipeline",
        "research_only",
        "raw_payload_sha256",
    }
    if not required.issubset(record):
        raise RuntimeError("source-point coverage record is incomplete")
    if record["source_id"] != forecast_snapshot.source_id:
        raise RuntimeError("source-point coverage references the wrong source")
    if record["provider"] != forecast_snapshot.provider or record["model_id"] != forecast_snapshot.model_id:
        raise RuntimeError("source-point coverage provenance does not match the snapshot")
    if record["run_id"] != forecast_snapshot.run_id:
        raise RuntimeError("source-point coverage run does not match the snapshot")
    if record["raw_payload_sha256"] != forecast_snapshot.content_sha256:
        raise RuntimeError("source-point raw payload hash does not match the source snapshot")

    native_points = tuple(
        NativeForcingPoint(
            point_id=str(point["point_id"]),
            latitude=float(point["latitude"]),
            longitude=float(point["longitude"]),
        )
        for point in record["native_points"]
    )
    valid_times = tuple(_parse_time(str(value)) for value in record["valid_times"])
    request = OpenMeteoRunRequest(
        latitudes=tuple(point.latitude for point in native_points),
        longitudes=tuple(point.longitude for point in native_points),
        model_id=forecast_snapshot.model_id,
        run_id=forecast_snapshot.run_id,
        forecast_hours=len(valid_times),
        hourly_variables=tuple(str(value) for value in record["required_variables"]),
    )
    try:
        source_payload = json.loads(forecast_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("source-point payload is not valid JSON") from exc
    parsed_payload = parse_open_meteo_single_run(
        source_payload,
        request,
        raw_payload=forecast_bytes,
    )
    if parsed_payload.raw_payload_sha256 != record["raw_payload_sha256"]:
        raise RuntimeError("source-point parser hash does not match the manifest")
    if tuple(_parse_time(value.isoformat()) for value in parsed_payload.points[0].times) != valid_times:
        raise RuntimeError("source-point valid times do not match the raw payload")
    if tuple(point.point for point in parsed_payload.points) != native_points:
        raise RuntimeError("source-point coordinates do not match the raw payload")

    aoi_record = record["aoi"]
    if not isinstance(aoi_record, Mapping):
        raise RuntimeError("source-point AOI record is invalid")
    plan = construct_aoi_coverage_plan(
        source_id=str(record["source_id"]),
        provider=str(record["provider"]),
        model_id=str(record["model_id"]),
        run_id=str(record["run_id"]),
        aoi=AoiBounds(
            min_latitude=float(aoi_record["min_latitude"]),
            min_longitude=float(aoi_record["min_longitude"]),
            max_latitude=float(aoi_record["max_latitude"]),
            max_longitude=float(aoi_record["max_longitude"]),
        ),
        target_rows=int(record["target_rows"]),
        target_cols=int(record["target_cols"]),
        target_resolution_m=float(record["target_resolution_m"]),
        native_resolution_m=float(record["native_resolution_m"]),
        required_variables=tuple(str(value) for value in record["required_variables"]),
        valid_times=valid_times,
        native_points=native_points,
        max_assignment_distance_m=float(record["max_assignment_distance_m"]),
        license_review_status=str(record["license_review_status"]),
    )
    plan.validate()
    if plan.target_cell_count != cell_count:
        raise RuntimeError("source-point coverage target dimensions do not match the grid")
    if tuple(record["assignments"]) != plan.assignments:
        raise RuntimeError("source-point coverage assignments do not reproduce")
    if float(record["coverage_fraction"]) != plan.coverage_fraction:
        raise RuntimeError("source-point coverage fraction does not reproduce")
    if bool(record["complete_spatial_coverage"]) != plan.complete_spatial_coverage:
        raise RuntimeError("source-point complete-coverage flag does not reproduce")
    if bool(record["can_enter_forcing_pipeline"]) != plan.can_enter_forcing_pipeline:
        raise RuntimeError("source-point pipeline gate does not reproduce")
    if record["research_only"] is not True or not plan.research_only:
        raise RuntimeError("source-point coverage must remain research-only")


def replay_bundle(root: Path) -> dict[str, Any]:
    manifest_record = json.loads((root / "snapshot_manifest.json").read_text())
    cell_count = _validate_grid_descriptor(manifest_record.get("grid", {}))
    snapshots = []
    source_bytes: dict[str, bytes] = {}
    for record in manifest_record["snapshots"]:
        path = root / record["relative_path"]
        payload = path.read_bytes()
        digest = _sha256(payload)
        if digest != record["content_sha256"]:
            raise RuntimeError(f"source hash mismatch: {record['source_id']}")
        source_bytes[record["source_id"]] = payload
        snapshots.append(SourceSnapshot(
            source_id=record["source_id"],
            product=record["product"],
            issue_time=_parse_time(record["issue_time"]),
            valid_time=_parse_time(record["valid_time"]),
            retrieved_at=_parse_time(record["retrieved_at"]),
            source_as_of=_parse_time(record["source_as_of"]),
            native_resolution_m=float(record["native_resolution_m"]),
            content_sha256=record["content_sha256"],
            license_id=record["license_id"],
            provider=record["provider"],
            model_id=record["model_id"],
            run_id=record["run_id"],
            lead_time_hours=record.get("lead_time_hours"),
            assimilation_disclosure=record["assimilation_disclosure"],
            license_review_status=record.get("license_review_status", "pending"),
            research_only=bool(record.get("research_only", True)),
        ))

    manifest = ForcingSnapshotManifest(
        snapshots=tuple(snapshots),
        target_crs=manifest_record["grid"]["target_crs"],
        target_resolution_m=float(manifest_record["grid"]["target_resolution_m"]),
        effective_resolution_m=max(snapshot.native_resolution_m for snapshot in snapshots),
        grid_manifest_hash=manifest_record["grid"]["grid_manifest_hash"],
        missingness_policy="fail_or_hold",
    )
    manifest.validate(SourceRegistry())
    if manifest.manifest_hash != manifest_record["manifest_hash"]:
        raise RuntimeError("forcing manifest hash mismatch")
    payload = b"".join(source_bytes[source_id] for source_id in sorted(source_bytes))
    replay = SourceReplay.from_payload(
        manifest,
        payload,
        created_at=_parse_time(manifest_record["created_at"]),
    )
    if replay.payload_sha256 != manifest_record["payload_sha256"]:
        raise RuntimeError("replay payload hash mismatch")
    if replay.replay_id != manifest_record["replay_id"]:
        raise RuntimeError("replay identity mismatch")

    source_point_record = manifest_record.get("source_point_coverage")
    if source_point_record is not None:
        forecast_snapshot = next(
            (snapshot for snapshot in snapshots if snapshot.source_id == "open_meteo_nwp"),
            None,
        )
        if forecast_snapshot is None:
            raise RuntimeError("source-point coverage exists without an NWP snapshot")
        _validate_source_point_coverage(
            source_point_record,
            forecast_snapshot=forecast_snapshot,
            forecast_bytes=source_bytes[forecast_snapshot.source_id],
            cell_count=cell_count,
        )

    mask_hashes = []
    snapshot_ids = {snapshot.snapshot_id for snapshot in snapshots}
    for record in manifest_record["coverage_masks"]:
        if record["source_snapshot_id"] not in snapshot_ids:
            raise RuntimeError("coverage mask references an unknown source snapshot")
        mask = CoverageMask(
            grid_manifest_hash=record["grid_manifest_hash"],
            source_snapshot_id=record["source_snapshot_id"],
            pixel_ids=tuple(record["pixel_ids"]),
            available=tuple(record["available"]),
            freshness_hours=tuple(record["freshness_hours"]),
            max_freshness_hours=float(record["max_freshness_hours"]),
            missingness_policy=record["missingness_policy"],
        )
        if len(mask.pixel_ids) != cell_count:
            raise RuntimeError("coverage mask does not cover the declared grid cell count")
        if mask.mask_hash != record["mask_hash"]:
            raise RuntimeError("coverage mask hash mismatch")
        mask_hashes.append(mask.mask_hash)

    return {
        "replayed": True,
        "manifest_hash_match": True,
        "replay_id_match": True,
        "source_hashes_verified": len(snapshots),
        "coverage_masks_verified": len(mask_hashes),
        "cell_count": cell_count,
        "synthetic_inputs_present": False,
        "training_eligible": False,
        "production_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    report = replay_bundle(args.root.expanduser().resolve())
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
