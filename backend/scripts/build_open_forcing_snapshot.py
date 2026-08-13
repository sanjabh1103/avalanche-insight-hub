#!/usr/bin/env python3
"""Fetch and freeze one small, provenance-first open-forcing snapshot.

This command intentionally fetches only public, unauthenticated products. It
does not replace unavailable NASA/ECMWF products with fixtures. The resulting
10,000-cell grid is a computational descriptor plus a nearest-native-source
coverage plan; it is not a claim that every cell has 500 m information or that
the source field has been interpolated onto the target grid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.open_forcing.contracts import ASSIMILATION_DISCLOSURE, SourceSnapshot
from backend.open_forcing.coverage import (
    AoiBounds,
    NativeForcingPoint,
    construct_aoi_coverage_plan,
)
from backend.open_forcing.open_meteo_source import (
    OpenMeteoRunRequest,
    NativeSourcePointPayload,
    parse_open_meteo_single_run,
)
from backend.open_forcing.replay import CoverageMask, SourceReplay
from backend.open_forcing.source_registry import ForcingSnapshotManifest, SourceRegistry
from backend.common.regions import load_regions


SCHEMA_VERSION = "open-forcing-snapshot/v1"
_UTC = timezone.utc
_FORECAST_HOURLY_VARIABLES = (
    "cloud_cover",
    "precipitation",
    "relative_humidity_2m",
    "shortwave_radiation",
    "snowfall",
    "surface_pressure",
    "temperature_2m",
    "windspeed_10m",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> datetime:
    return datetime.now(_UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def _fetch(url: str, *, max_bytes: int | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "avalanche-insight-hub-open-forcing-research/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if max_bytes is not None:
            return response.read(max_bytes)
        return response.read()


def _json_value(url: str) -> tuple[bytes, Any]:
    payload = _fetch(url)
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"source did not return JSON: {url}") from exc
    return payload, parsed


def _json_bytes(url: str) -> tuple[bytes, dict[str, Any]]:
    payload, parsed = _json_value(url)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"source JSON must be an object: {url}")
    return payload, parsed


def _first_hourly_time(payload: dict[str, Any]) -> datetime:
    hourly = payload.get("hourly")
    values = hourly.get("time") if isinstance(hourly, dict) else None
    if not isinstance(values, list) or not values or not isinstance(values[0], str):
        raise RuntimeError("hourly response has no usable first time")
    return _parse_time(values[0])


def _snapshot_record(
    *,
    source_id: str,
    product: str,
    issue_time: datetime,
    valid_time: datetime,
    retrieved_at: datetime,
    native_resolution_m: float,
    content_sha256: str,
    license_id: str,
    provider: str,
    model_id: str,
    run_id: str,
    license_review_status: str,
    relative_path: str,
    url: str,
) -> tuple[SourceSnapshot, dict[str, Any]]:
    snapshot = SourceSnapshot(
        source_id=source_id,
        product=product,
        issue_time=issue_time,
        valid_time=valid_time,
        retrieved_at=retrieved_at,
        source_as_of=valid_time,
        native_resolution_m=native_resolution_m,
        content_sha256=content_sha256,
        license_id=license_id,
        provider=provider,
        model_id=model_id,
        run_id=run_id,
        assimilation_disclosure=ASSIMILATION_DISCLOSURE,
        license_review_status=license_review_status,
    )
    snapshot.validate()
    return snapshot, {
        "source_id": snapshot.source_id,
        "product": snapshot.product,
        "issue_time": _iso(snapshot.issue_time),
        "valid_time": _iso(snapshot.valid_time),
        "retrieved_at": _iso(snapshot.retrieved_at),
        "source_as_of": _iso(snapshot.source_as_of),
        "native_resolution_m": snapshot.native_resolution_m,
        "content_sha256": snapshot.content_sha256,
        "license_id": snapshot.license_id,
        "provider": snapshot.provider,
        "model_id": snapshot.model_id,
        "run_id": snapshot.run_id,
        "lead_time_hours": snapshot.lead_time_hours,
        "assimilation_disclosure": snapshot.assimilation_disclosure,
        "license_review_status": snapshot.license_review_status,
        "research_only": snapshot.research_only,
        "snapshot_id": snapshot.snapshot_id,
        "relative_path": relative_path,
        "url": url,
    }


def _write_snapshot(root: Path, relative_path: str, payload: bytes) -> str:
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return _sha256(payload)


def _tile_name(latitude: float, longitude: float) -> tuple[str, str]:
    south = math.floor(latitude)
    west = math.floor(longitude)
    lat_prefix = f"N{south:02d}" if south >= 0 else f"S{abs(south):02d}"
    lon_prefix = f"E{west:03d}" if west >= 0 else f"W{abs(west):03d}"
    directory = lat_prefix
    return directory, f"{lat_prefix}{lon_prefix}.hgt.gz"


def _grid_descriptor(latitude: float, longitude: float, target_resolution_m: float) -> dict[str, Any]:
    rows = cols = int(round(50_000.0 / target_resolution_m))
    if rows <= 0 or rows * cols != 10_000:
        raise ValueError("this first snapshot requires a 50 km x 50 km, 500 m, 10,000-cell grid")
    descriptor = {
        "construction": "projected_configured_grid_descriptor",
        "target_crs": "EPSG:32643",
        "target_resolution_m": target_resolution_m,
        "rows": rows,
        "cols": cols,
        "cell_count": rows * cols,
        "aoi_center_latitude": latitude,
        "aoi_center_longitude": longitude,
        "width_m": rows * target_resolution_m,
        "height_m": cols * target_resolution_m,
        "information_boundary": "grid spacing is not observational resolution",
    }
    descriptor["grid_manifest_hash"] = _sha256(_canonical(descriptor))
    return descriptor


def _model_grid_points(
    latitude: float,
    longitude: float,
    *,
    spacing_deg: float,
    radius: int,
) -> tuple[NativeForcingPoint, ...]:
    """Return a deterministic lattice on the selected model's native grid."""

    if not math.isfinite(spacing_deg) or spacing_deg <= 0:
        raise ValueError("forecast grid spacing must be positive and finite")
    if radius < 0 or radius > 2:
        raise ValueError("forecast grid radius must be between 0 and 2")
    snapped_latitude = round(latitude / spacing_deg) * spacing_deg
    snapped_longitude = round(longitude / spacing_deg) * spacing_deg
    points: list[NativeForcingPoint] = []
    for lat_offset in range(-radius, radius + 1):
        for lon_offset in range(-radius, radius + 1):
            point_latitude = round(snapped_latitude + lat_offset * spacing_deg, 6)
            point_longitude = round(snapped_longitude + lon_offset * spacing_deg, 6)
            point = NativeForcingPoint(
                point_id=f"p{len(points):03d}",
                latitude=point_latitude,
                longitude=point_longitude,
            )
            point.validate()
            points.append(point)
    return tuple(points)


def _aoi_bounds(latitude: float, longitude: float, width_km: float = 50.0) -> AoiBounds:
    """Approximate a local 50 km AOI for deterministic coverage accounting."""

    if not math.isfinite(width_km) or width_km <= 0:
        raise ValueError("AOI width must be positive and finite")
    half_latitude = (width_km * 1000.0 / 2.0) / 111_320.0
    longitude_scale = max(math.cos(math.radians(latitude)), 0.1)
    half_longitude = half_latitude / longitude_scale
    result = AoiBounds(
        min_latitude=latitude - half_latitude,
        min_longitude=longitude - half_longitude,
        max_latitude=latitude + half_latitude,
        max_longitude=longitude + half_longitude,
    )
    result.validate()
    return result


def _coverage_mask(snapshot: SourceSnapshot, grid: dict[str, Any]) -> tuple[CoverageMask, dict[str, Any]]:
    pixel_ids = tuple(
        f"r{row:03d}c{col:03d}"
        for row in range(int(grid["rows"]))
        for col in range(int(grid["cols"]))
    )
    # A point forcing request has evidence only at the deterministic centre
    # cell. We do not broadcast it across 10,000 cells.
    centre = (int(grid["rows"]) // 2) * int(grid["cols"]) + int(grid["cols"]) // 2
    available = tuple(index == centre for index in range(len(pixel_ids)))
    freshness = tuple(0.0 if present else None for present in available)
    mask = CoverageMask(
        grid_manifest_hash=grid["grid_manifest_hash"],
        source_snapshot_id=snapshot.snapshot_id,
        pixel_ids=pixel_ids,
        available=available,
        freshness_hours=freshness,
        max_freshness_hours=6.0,
        missingness_policy="fail_or_hold",
    )
    mask.validate()
    return mask, {
        "grid_manifest_hash": mask.grid_manifest_hash,
        "source_snapshot_id": mask.source_snapshot_id,
        "pixel_ids": mask.pixel_ids,
        "available": mask.available,
        "freshness_hours": mask.freshness_hours,
        "max_freshness_hours": mask.max_freshness_hours,
        "missingness_policy": mask.missingness_policy,
        "coverage_fraction": mask.coverage_fraction,
        "missing_pixel_count": len(mask.missing_pixel_ids),
        "mask_hash": mask.mask_hash,
    }


def _coverage_mask_from_plan(
    snapshot: SourceSnapshot,
    grid: dict[str, Any],
    assignments: tuple[str | None, ...],
) -> tuple[CoverageMask, dict[str, Any]]:
    """Represent nearest-native-point availability without manufacturing values."""

    pixel_ids = tuple(
        f"r{row:03d}c{col:03d}"
        for row in range(int(grid["rows"]))
        for col in range(int(grid["cols"]))
    )
    if len(assignments) != len(pixel_ids):
        raise ValueError("coverage plan assignments must match the target grid")
    available = tuple(assignment is not None for assignment in assignments)
    freshness = tuple(0.0 if present else None for present in available)
    mask = CoverageMask(
        grid_manifest_hash=grid["grid_manifest_hash"],
        source_snapshot_id=snapshot.snapshot_id,
        pixel_ids=pixel_ids,
        available=available,
        freshness_hours=freshness,
        max_freshness_hours=6.0,
        missingness_policy="fail_or_hold",
    )
    mask.validate()
    return mask, {
        "grid_manifest_hash": mask.grid_manifest_hash,
        "source_snapshot_id": mask.source_snapshot_id,
        "pixel_ids": mask.pixel_ids,
        "available": mask.available,
        "freshness_hours": mask.freshness_hours,
        "max_freshness_hours": mask.max_freshness_hours,
        "missingness_policy": mask.missingness_policy,
        "coverage_fraction": mask.coverage_fraction,
        "missing_pixel_count": len(mask.missing_pixel_ids),
        "coverage_method": "nearest_native_source_point_assignment_only",
        "mask_hash": mask.mask_hash,
    }


def _coverage_plan_record(plan: Any, payload: NativeSourcePointPayload, request_url: str) -> dict[str, Any]:
    return {
        "source_id": plan.source_id,
        "provider": plan.provider,
        "model_id": plan.model_id,
        "run_id": plan.run_id,
        "aoi": {
            "min_latitude": plan.aoi.min_latitude,
            "min_longitude": plan.aoi.min_longitude,
            "max_latitude": plan.aoi.max_latitude,
            "max_longitude": plan.aoi.max_longitude,
        },
        "target_rows": plan.target_rows,
        "target_cols": plan.target_cols,
        "target_resolution_m": plan.target_resolution_m,
        "native_resolution_m": plan.native_resolution_m,
        "effective_information_scale_m": plan.effective_information_scale_m,
        "required_variables": plan.required_variables,
        "valid_times": tuple(_iso(value) for value in plan.valid_times),
        "native_points": tuple(
            {"point_id": point.point_id, "latitude": point.latitude, "longitude": point.longitude}
            for point in plan.native_points
        ),
        "assignments": plan.assignments,
        "max_assignment_distance_m": plan.max_assignment_distance_m,
        "coverage_fraction": plan.coverage_fraction,
        "complete_spatial_coverage": plan.complete_spatial_coverage,
        "license_review_status": plan.license_review_status,
        "can_enter_forcing_pipeline": plan.can_enter_forcing_pipeline,
        "research_only": plan.research_only,
        "request_url": request_url,
        "raw_payload_sha256": payload.raw_payload_sha256,
        "information_boundary": "nearest-source coverage accounting only; no interpolation or target-grid values",
    }


def _optional_source_probes(archive_start: str) -> dict[str, Any]:
    day = _parse_time(f"{archive_start}T00:00:00Z")
    year = day.year
    doy = day.timetuple().tm_yday
    imerg_url = (
        "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/"
        f"GPM_3IMERGHH.07/{year}/{doy:03d}/"
    )
    modis_url = f"https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MOD10A1/{year}/{doy:03d}/"
    statuses: dict[str, Any] = {}
    for source_id, url in (("gpm_imerg_early", imerg_url), ("mod10a1", modis_url)):
        try:
            body = _fetch(url, max_bytes=4096)
            text = body.decode("utf-8", "replace")
            if "Earthdata Login" in text or "access requires" in text.lower():
                status = "access_requires_external_authentication"
            else:
                status = "listing_reachable_payload_not_frozen"
            statuses[source_id] = {"status": status, "url": url}
        except urllib.error.HTTPError as exc:
            statuses[source_id] = {
                "status": "unavailable",
                "url": url,
                "http_status": exc.code,
                "reason": "no unauthenticated science payload was downloaded",
            }
        except Exception as exc:  # pragma: no cover - network dependent
            statuses[source_id] = {
                "status": "unavailable",
                "url": url,
                "reason": f"{type(exc).__name__}: {exc}",
            }
    return statuses


def _resolve_region(args: argparse.Namespace) -> dict[str, Any] | None:
    """Resolve a configured target region before fetching any source bytes."""
    region_key = str(getattr(args, "region_key", "") or "").strip()
    if not region_key:
        return None
    regions = load_regions()
    matches = [region for region in regions if region.key == region_key]
    if not matches:
        known = ", ".join(sorted(region.key for region in regions))
        raise ValueError(f"unknown region key {region_key!r}; expected one of: {known}")
    region = matches[0]
    args.latitude, args.longitude = map(float, region.center)
    return {
        "key": region.key,
        "name": region.name,
        "bbox": [float(value) for value in region.bbox],
        "center": [float(value) for value in region.center],
        "season_start": region.season_start,
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    region_record = _resolve_region(args)
    root = Path(args.output_root).expanduser().resolve()
    if (root / "snapshot_manifest.json").exists():
        raise RuntimeError(f"snapshot bundle already exists and is immutable: {root}")
    root.mkdir(parents=True, exist_ok=True)
    retrieved_at = _now()
    grid = _grid_descriptor(args.latitude, args.longitude, args.target_resolution_m)
    registry = SourceRegistry()
    snapshots: list[SourceSnapshot] = []
    snapshot_records: list[dict[str, Any]] = []
    source_bytes: dict[str, bytes] = {}

    forecast_points = _model_grid_points(
        args.latitude,
        args.longitude,
        spacing_deg=args.forecast_grid_spacing_deg,
        radius=args.forecast_grid_radius,
    )
    forecast_request = OpenMeteoRunRequest(
        latitudes=tuple(point.latitude for point in forecast_points),
        longitudes=tuple(point.longitude for point in forecast_points),
        model_id=args.forecast_model_id,
        run_id=args.forecast_run,
        forecast_hours=args.forecast_hours,
        hourly_variables=_FORECAST_HOURLY_VARIABLES,
    )
    forecast_url = forecast_request.url
    forecast_bytes, forecast_json = _json_value(forecast_url)
    forecast_payload = parse_open_meteo_single_run(
        forecast_json,
        forecast_request,
        raw_payload=forecast_bytes,
    )
    forecast_payload.validate()
    forecast_path = "snapshots/open_meteo_nwp/source_points.json"
    forecast_hash = _write_snapshot(root, forecast_path, forecast_bytes)
    forecast_snapshot, forecast_record = _snapshot_record(
        source_id="open_meteo_nwp",
        product="Open-Meteo selected NWP hourly response",
        issue_time=_parse_time(args.forecast_run),
        valid_time=forecast_payload.points[0].times[0],
        retrieved_at=retrieved_at,
        native_resolution_m=args.forecast_native_resolution_m,
        content_sha256=forecast_hash,
        license_id="open_meteo_terms_review_required",
        provider="open-meteo-single-runs",
        model_id=args.forecast_model_id,
        run_id=args.forecast_run,
        license_review_status="pending",
        relative_path=forecast_path,
        url=forecast_url,
    )
    registry.assert_quantitative_allowed(forecast_snapshot.source_id)
    snapshots.append(forecast_snapshot)
    snapshot_records.append(forecast_record)
    source_bytes[forecast_snapshot.source_id] = forecast_bytes

    forecast_coverage_plan = construct_aoi_coverage_plan(
        source_id=forecast_snapshot.source_id,
        provider=forecast_snapshot.provider,
        model_id=forecast_snapshot.model_id,
        run_id=forecast_snapshot.run_id,
        aoi=_aoi_bounds(args.latitude, args.longitude),
        target_rows=int(grid["rows"]),
        target_cols=int(grid["cols"]),
        target_resolution_m=args.target_resolution_m,
        native_resolution_m=args.forecast_native_resolution_m,
        required_variables=forecast_request.hourly_variables,
        valid_times=forecast_payload.points[0].times,
        native_points=tuple(point_series.point for point_series in forecast_payload.points),
        license_review_status=forecast_snapshot.license_review_status,
    )

    archive_params = {
        "latitude": args.latitude,
        "longitude": args.longitude,
        "start_date": args.archive_start_date,
        "end_date": args.archive_end_date,
        "hourly": "temperature_2m,relative_humidity_2m,windspeed_10m,surface_pressure,shortwave_radiation,precipitation,snowfall,cloud_cover",
        "models": "era5_land",
        "timezone": "UTC",
    }
    archive_url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(archive_params)
    archive_bytes, archive_json = _json_bytes(archive_url)
    archive_path = "snapshots/era5_land/archive.json"
    archive_hash = _write_snapshot(root, archive_path, archive_bytes)
    archive_valid_time = _first_hourly_time(archive_json)
    archive_snapshot, archive_record = _snapshot_record(
        source_id="era5_land",
        product="ERA5-Land hourly archive via Open-Meteo",
        issue_time=archive_valid_time,
        valid_time=archive_valid_time,
        retrieved_at=retrieved_at,
        native_resolution_m=9000.0,
        content_sha256=archive_hash,
        license_id="copernicus_licence_review_required",
        provider="ECMWF/Copernicus via Open-Meteo archive",
        model_id="era5_land",
        run_id=f"archive:{args.archive_start_date}:{args.archive_end_date}",
        license_review_status="pending",
        relative_path=archive_path,
        url=archive_url,
    )
    registry.assert_quantitative_allowed(archive_snapshot.source_id)
    snapshots.append(archive_snapshot)
    snapshot_records.append(archive_record)
    source_bytes[archive_snapshot.source_id] = archive_bytes

    tile_dir, tile_name = _tile_name(args.latitude, args.longitude)
    srtm_url = f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{tile_dir}/{tile_name}"
    srtm_bytes = _fetch(srtm_url)
    srtm_path = f"snapshots/srtm_dem/{tile_name}"
    srtm_hash = _write_snapshot(root, srtm_path, srtm_bytes)
    srtm_snapshot, srtm_record = _snapshot_record(
        source_id="srtm_dem",
        product="SRTM elevation tile",
        issue_time=retrieved_at,
        valid_time=retrieved_at,
        retrieved_at=retrieved_at,
        native_resolution_m=30.0,
        content_sha256=srtm_hash,
        license_id="nasa_usgs_terms_review_required",
        provider="NASA/USGS",
        model_id="srtm_dem_v1",
        run_id=tile_name,
        license_review_status="pending",
        relative_path=srtm_path,
        url=srtm_url,
    )
    registry.assert_quantitative_allowed(srtm_snapshot.source_id)
    snapshots.append(srtm_snapshot)
    snapshot_records.append(srtm_record)
    source_bytes[srtm_snapshot.source_id] = srtm_bytes

    manifest = ForcingSnapshotManifest(
        snapshots=tuple(snapshots),
        target_crs=grid["target_crs"],
        target_resolution_m=args.target_resolution_m,
        effective_resolution_m=max(snapshot.native_resolution_m for snapshot in snapshots),
        grid_manifest_hash=grid["grid_manifest_hash"],
        missingness_policy="fail_or_hold",
    )
    manifest.validate(registry)
    coverage_masks = []
    _, forecast_mask_record = _coverage_mask_from_plan(
        forecast_snapshot,
        grid,
        forecast_coverage_plan.assignments,
    )
    coverage_masks.append(forecast_mask_record)
    for snapshot in snapshots[1:]:
        _, record = _coverage_mask(snapshot, grid)
        coverage_masks.append(record)

    payload = b"".join(source_bytes[source_id] for source_id in sorted(source_bytes))
    replay = SourceReplay.from_payload(manifest, payload, created_at=retrieved_at)
    snapshot_manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _iso(retrieved_at),
        "aoi": {
            "center_latitude": args.latitude,
            "center_longitude": args.longitude,
            "width_km": 50.0,
            "height_km": 50.0,
        },
        "target_region": region_record,
        "grid": grid,
        "snapshots": snapshot_records,
        "manifest_hash": manifest.manifest_hash,
        "payload_sha256": replay.payload_sha256,
        "replay_id": replay.replay_id,
        "coverage_masks": coverage_masks,
        "source_point_coverage": _coverage_plan_record(
            forecast_coverage_plan,
            forecast_payload,
            forecast_url,
        ),
        "source_availability": _optional_source_probes(args.archive_start_date),
        "synthetic_inputs_present": False,
        "training_eligible": False,
        "production_eligible": False,
    }
    (root / "snapshot_manifest.json").write_bytes(_canonical(snapshot_manifest) + b"\n")
    return snapshot_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, help="empty or new directory for immutable snapshot files")
    parser.add_argument(
        "--region-key",
        help="configured target region; its center overrides --latitude/--longitude",
    )
    parser.add_argument("--latitude", type=float, default=34.0)
    parser.add_argument("--longitude", type=float, default=75.0)
    parser.add_argument("--target-resolution-m", type=float, default=500.0)
    parser.add_argument("--archive-start-date", default="2025-01-01")
    parser.add_argument("--archive-end-date", default="2025-01-02")
    parser.add_argument("--forecast-model-id", default="ecmwf_ifs025")
    parser.add_argument(
        "--forecast-grid-spacing-deg",
        type=float,
        default=0.25,
        help="selected model-native grid spacing in degrees; ecmwf_ifs025 uses 0.25",
    )
    parser.add_argument(
        "--forecast-grid-radius",
        type=int,
        default=1,
        help="native-grid radius around the snapped centre; default 1 creates 3x3 points",
    )
    parser.add_argument(
        "--forecast-native-resolution-m",
        type=float,
        default=25_000.0,
        help="effective native spacing recorded for the selected forecast grid",
    )
    parser.add_argument(
        "--forecast-hours",
        type=int,
        default=24,
        help="bounded number of hourly values requested from Single Runs",
    )
    parser.add_argument(
        "--forecast-run",
        required=True,
        help="exact UTC model initialization, e.g. 2026-07-31T00:00",
    )
    return parser


def main() -> int:
    manifest = build_snapshot(_parser().parse_args())
    print(json.dumps({
        "output": "snapshot_manifest.json",
        "manifest_hash": manifest["manifest_hash"],
        "replay_id": manifest["replay_id"],
        "cell_count": manifest["grid"]["cell_count"],
        "sources": [record["source_id"] for record in manifest["snapshots"]],
        "source_availability": manifest["source_availability"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
