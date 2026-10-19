#!/usr/bin/env python3
"""Acquire a bounded station-free historical feature snapshot for labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.open_meteo_interval_features import (
    OpenMeteoArchiveClient,
    OpenMeteoIntervalFeatureError,
    OPEN_METEO_DAILY_VARIABLES,
    build_open_meteo_interval_features,
)
from backend.common.station_free_feature_snapshot import (
    build_station_free_feature_snapshot,
    write_station_free_feature_snapshot,
)
from backend.common.spatial_grouping import spatial_feature_join_key


def _load_labels(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events_path = manifest_path.parent / str(manifest.get("events_path") or "events.jsonl")
    payload = events_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != str(manifest.get("event_rows_sha256") or ""):
        raise ValueError("label event hash mismatch")
    return [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]


def _interval_start(row: dict[str, Any]) -> str:
    for field in ("interval_start", "event_time_start", "timestamp_start"):
        value = row.get(field)
        if value not in (None, ""):
            return str(value)
    raise ValueError("label row is missing an interval start bound")


def _feature_join_key(row: dict[str, Any], *, spatial_bin_km: float) -> str:
    for field in ("feature_join_key", "spatial_group_id", "join_key"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    try:
        return spatial_feature_join_key(
            row.get("lat"),
            row.get("lng"),
            str(row.get("region_key") or "").strip(),
            bin_km=spatial_bin_km,
        )
    except ValueError as exc:
        row_id = str(row.get("source_event_id") or row.get("event_id") or "label")
        raise ValueError(f"{row_id}: cannot resolve feature_join_key") from exc


def _season_id(row: dict[str, Any]) -> str:
    timestamp = datetime.fromisoformat(_interval_start(row).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    year = timestamp.year if timestamp.month >= 11 else timestamp.year - 1
    return f"{year}-{year + 1}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--region-key", action="append", required=True)
    parser.add_argument("--season", action="append", dest="seasons")
    parser.add_argument("--exclude-season", action="append", dest="excluded_seasons",
                        help="season ID to exclude from the primary snapshot (e.g. 2025-2026)")
    parser.add_argument("--feature-join-key", action="append", dest="feature_join_keys")
    parser.add_argument("--max-spatial-groups", type=int)
    parser.add_argument(
        "--license-review-id",
        default="mvp4-open-meteo-reanalysis-license-review-pending",
    )
    parser.add_argument("--model", default="era5_land")
    parser.add_argument("--spatial-bin-km", type=float, default=5.0)
    parser.add_argument(
        "--max-request-days",
        type=int,
        default=366,
        help="maximum daily archive window per request; smaller windows reduce transient rate-limit failures",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
        help="per-request network timeout; keeps bounded acquisition from hanging indefinitely",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="directory for request-addressed raw response cache with payload-integrity verification; enables safe resume on interruption",
    )
    parser.add_argument(
        "--strict-coverage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="reject the run (exit 2) unless every expected positive label has a corresponding feature row (default: true)",
    )
    return parser


def _compute_coverage(
    labels: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    *,
    spatial_bin_km: float,
) -> dict[str, Any]:
    """Compute strict expected-input coverage for positive labels.

    Tracks both raw event-level coverage and unique feature-key coverage.
    Multiple labels may share the same (feature_join_key, interval_start,
    interval_end) triple; one feature row legitimately serves all of them.
    The gate fails closed if any retained event lacks a mapping to a
    feature row, or if any event is missing an event ID.
    """
    # Build event-to-key mapping: every retained event must map to a feature key
    event_to_key: dict[str, str] = {}
    events_without_id: list[dict[str, Any]] = []
    duplicate_event_ids: list[str] = []
    unique_keys: dict[str, dict[str, Any]] = {}
    key_multiplicity: dict[str, int] = {}

    for row in labels:
        if row.get("label") not in (1, True):
            continue
        event_id = str(row.get("source_event_id") or row.get("event_id") or "")
        if not event_id:
            events_without_id.append({
                "region_key": str(row.get("region_key") or ""),
                "lat": row.get("lat"),
                "lng": row.get("lng"),
                "interval_start": _interval_start(row),
            })
            continue
        if event_id in event_to_key:
            duplicate_event_ids.append(event_id)
            continue
        join_key = _feature_join_key(row, spatial_bin_km=spatial_bin_km)
        start = _interval_start(row)
        end_value = None
        for field in ("interval_end", "event_time_end", "timestamp_end"):
            value = row.get(field)
            if value not in (None, ""):
                end_value = str(value)
                break
        if end_value is None:
            continue
        feature_key = f"{join_key}|{start}|{end_value}"
        event_to_key[event_id] = feature_key
        if feature_key not in unique_keys:
            unique_keys[feature_key] = {
                "feature_join_key": join_key,
                "interval_start": start,
                "interval_end": end_value,
                "region_key": str(row.get("region_key") or ""),
            }
            key_multiplicity[feature_key] = 0
        key_multiplicity[feature_key] += 1

    # Build actual feature key set from feature rows
    actual: set[str] = set()
    for frow in feature_rows:
        join_key = str(frow.get("feature_join_key") or "")
        valid_from = str(frow.get("feature_valid_from") or "")
        valid_until = str(frow.get("feature_valid_until") or "")
        if join_key and valid_from and valid_until:
            actual.add(f"{join_key}|{valid_from}|{valid_until}")

    # Event-level coverage: which events have a feature key that exists in actual
    missing_event_ids: list[str] = []
    covered_event_count = 0
    for event_id, feature_key in event_to_key.items():
        if feature_key in actual:
            covered_event_count += 1
        else:
            missing_event_ids.append(event_id)

    # Unique key-level coverage
    missing_keys = sorted(set(unique_keys) - actual)
    covered_unique_key_count = len(unique_keys) - len(missing_keys)

    raw_expected = len(event_to_key)
    unique_expected = len(unique_keys)
    raw_coverage_fraction = covered_event_count / raw_expected if raw_expected else 1.0
    unique_coverage_fraction = covered_unique_key_count / unique_expected if unique_expected else 1.0

    return {
        # Event-level (raw labels) accounting
        "raw_expected_label_count": raw_expected,
        "covered_raw_label_count": covered_event_count,
        "missing_raw_label_count": len(missing_event_ids),
        "missing_event_ids": sorted(missing_event_ids),
        "raw_label_coverage_fraction": round(raw_coverage_fraction, 8),
        # Unique feature-key accounting
        "unique_expected_feature_key_count": unique_expected,
        "covered_unique_feature_key_count": covered_unique_key_count,
        "missing_unique_feature_key_count": len(missing_keys),
        "unique_feature_key_coverage_fraction": round(unique_coverage_fraction, 8),
        # Multiplicity: how many events share each key
        "key_multiplicity": {
            "min": min(key_multiplicity.values()) if key_multiplicity else 0,
            "max": max(key_multiplicity.values()) if key_multiplicity else 0,
            "mean": round(sum(key_multiplicity.values()) / len(key_multiplicity), 4) if key_multiplicity else 0,
        },
        # Events without IDs (gate failure)
        "events_without_id_count": len(events_without_id),
        "events_without_id": events_without_id,
        # Duplicate event IDs (gate failure)
        "duplicate_event_id_count": len(duplicate_event_ids),
        "duplicate_event_ids": sorted(duplicate_event_ids),
        # Overall gate: fails if any raw event is uncovered, any event lacks an ID,
        # or any event ID is duplicated
        "passed": (
            len(missing_event_ids) == 0
            and len(events_without_id) == 0
            and len(duplicate_event_ids) == 0
        ),
        "coverage_fraction": round(raw_coverage_fraction, 8),  # primary fraction is raw-level
        # Legacy fields for backward compatibility (deprecated, use raw_* and unique_* instead)
        "expected_label_count": raw_expected,
        "covered_label_count": covered_event_count,
        "missing_label_count": len(missing_event_ids),
        "missing_labels": [
            {**unique_keys[event_to_key[eid]], "source_event_id": eid}
            for eid in sorted(missing_event_ids)
        ],
    }


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle_manifest(
    output_dir: Path,
    *,
    label_manifest_path: Path,
    label_manifest_sha256: str,
    snapshot_manifest: dict[str, Any],
    source_provenance: dict[str, Any],
    cache_manifest: dict[str, Any] | None,
    excluded_labels: list[dict[str, Any]],
    coverage_report: dict[str, Any],
) -> dict[str, Any]:
    """Write a bundle manifest linking all artifact hashes for external verification.

    The bundle manifest is the single entry point for verifying the complete
    artifact.  It contains hashes for:
    - label snapshot manifest (external input)
    - feature rows (features.jsonl)
    - feature snapshot manifest (snapshot_manifest.json)
    - source provenance (source_provenance.json)
    - cache manifest (raw_cache/cache_manifest.json)
    - excluded-event record (embedded in provenance, hashed separately)
    - coverage gate report (embedded in provenance)

    The bundle manifest itself is hashed so that external auditors can
    verify the entire artifact with one digest.
    """
    features_path = output_dir / "features.jsonl"
    snapshot_manifest_path = output_dir / "snapshot_manifest.json"
    provenance_path = output_dir / "source_provenance.json"
    cache_manifest_path = output_dir / "raw_cache" / "cache_manifest.json"

    # Compute file-level hashes
    component_hashes = {
        "label_manifest": {
            "path": str(label_manifest_path),
            "sha256": label_manifest_sha256,
        },
        "features_jsonl": {
            "path": str(features_path),
            "sha256": _sha256_file(features_path) if features_path.is_file() else None,
        },
        "snapshot_manifest": {
            "path": str(snapshot_manifest_path),
            "sha256": _sha256_file(snapshot_manifest_path) if snapshot_manifest_path.is_file() else None,
            "manifest_hash": snapshot_manifest.get("manifest_hash"),
            "feature_rows_sha256": snapshot_manifest.get("feature_rows_sha256"),
        },
        "source_provenance": {
            "path": str(provenance_path),
            "sha256": _sha256_file(provenance_path) if provenance_path.is_file() else None,
        },
    }
    if cache_manifest_path.is_file():
        component_hashes["cache_manifest"] = {
            "path": str(cache_manifest_path),
            "sha256": _sha256_file(cache_manifest_path),
            "cache_manifest_sha256": cache_manifest.get("cache_manifest_sha256") if cache_manifest else None,
        }
    else:
        component_hashes["cache_manifest"] = {
            "path": str(cache_manifest_path),
            "sha256": None,
            "cache_manifest_sha256": None,
        }

    # Excluded-event record hash (deterministic serialization of excluded labels)
    excluded_record_bytes = json.dumps(
        excluded_labels, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    component_hashes["excluded_event_record"] = {
        "excluded_label_count": len(excluded_labels),
        "sha256": hashlib.sha256(excluded_record_bytes).hexdigest(),
    }

    # Coverage gate hash (deterministic serialization of coverage report)
    coverage_bytes = json.dumps(
        coverage_report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    component_hashes["coverage_gate"] = {
        "passed": coverage_report.get("passed"),
        "sha256": hashlib.sha256(coverage_bytes).hexdigest(),
    }

    bundle = {
        "bundle_schema_version": "mvp4_nepal_acquisition_bundle_v1",
        "output_dir": str(output_dir),
        "component_hashes": component_hashes,
        # Summary fields for quick audit
        "primary_label_row_count": coverage_report.get("raw_expected_label_count"),
        "covered_primary_label_row_count": coverage_report.get("covered_raw_label_count"),
        "primary_unique_feature_key_count": coverage_report.get("unique_expected_feature_key_count"),
        "covered_primary_unique_feature_key_count": coverage_report.get("covered_unique_feature_key_count"),
        "coverage_gate_passed": coverage_report.get("passed"),
        "coverage_scope": "label_linked_interval_features",
        "operational_grid_coverage": False,
        "training_eligible": False,
        "production_scoring_eligible": False,
    }
    # Bundle hash: hash the component_hashes for a stable digest
    bundle_bytes = json.dumps(
        component_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    bundle["bundle_sha256"] = hashlib.sha256(bundle_bytes).hexdigest()

    bundle_path = output_dir / "bundle_manifest.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = _load_labels(args.label_manifest)
    selected_regions = {str(value).strip() for value in args.region_key if str(value).strip()}
    selected_seasons = {str(value).strip() for value in (args.seasons or []) if str(value).strip()}
    excluded_seasons = {str(value).strip() for value in (args.excluded_seasons or []) if str(value).strip()}
    selected_join_keys = {str(value).strip() for value in (args.feature_join_keys or []) if str(value).strip()}

    # Split labels into primary (included) and excluded sets
    primary_labels: list[dict[str, Any]] = []
    excluded_labels: list[dict[str, Any]] = []
    for row in rows:
        region = str(row.get("region_key") or "").strip()
        if region not in selected_regions:
            continue
        season = _season_id(row)
        if excluded_seasons and season in excluded_seasons:
            excluded_labels.append({
                **row,
                "included_in_primary_snapshot": False,
                "exclusion_reason": "partial_or_sparse_current_season",
            })
            continue
        if selected_seasons and season not in selected_seasons:
            continue
        if selected_join_keys and _feature_join_key(row, spatial_bin_km=args.spatial_bin_km) not in selected_join_keys:
            continue
        primary_labels.append(row)

    labels = primary_labels
    if args.max_spatial_groups is not None and args.max_spatial_groups <= 0:
        raise ValueError("max-spatial-groups must be positive")
    if args.max_spatial_groups is not None:
        keys = sorted(
            {
                _feature_join_key(row, spatial_bin_km=args.spatial_bin_km)
                for row in labels
            }
        )
        allowed = set(keys[: args.max_spatial_groups])
        labels = [
            row
            for row in labels
            if _feature_join_key(row, spatial_bin_km=args.spatial_bin_km) in allowed
        ]

    resolved_feature_join_keys = sorted(
        {_feature_join_key(row, spatial_bin_km=args.spatial_bin_km) for row in labels}
    )

    # Compute the actual included seasons from the primary label set
    included_seasons = sorted({_season_id(row) for row in labels})

    cache_dir = args.cache_dir
    if cache_dir is None:
        cache_dir = args.output_dir / "raw_cache"

    request_manifest = {
        "source_key": args.model,
        "model": args.model,
        "daily_variables": list(OPEN_METEO_DAILY_VARIABLES),
        "regions": sorted(selected_regions),
        "seasons": sorted(selected_seasons),
        "included_seasons": included_seasons,
        "excluded_seasons": sorted(excluded_seasons),
        "feature_join_keys": sorted(selected_join_keys),
        "resolved_feature_join_keys": resolved_feature_join_keys,
        "max_spatial_groups": args.max_spatial_groups,
        "spatial_bin_km": args.spatial_bin_km,
        "cutoff_policy": "valid_time_shadow",
        "max_request_days": args.max_request_days,
        "request_timeout_seconds": args.request_timeout_seconds,
        "cache_dir": str(cache_dir),
        "strict_coverage": args.strict_coverage,
    }
    source_manifest_sha256 = hashlib.sha256(
        json.dumps(request_manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    label_manifest_sha256 = hashlib.sha256(args.label_manifest.read_bytes()).hexdigest()
    client = OpenMeteoArchiveClient(request_timeout_seconds=args.request_timeout_seconds)
    feature_rows, source_manifest, fetch_records = build_open_meteo_interval_features(
        labels,
        client=client,
        source_manifest_sha256=source_manifest_sha256,
        license_review_id=args.license_review_id,
        model=args.model,
        spatial_bin_km=args.spatial_bin_km,
        max_request_days=args.max_request_days,
        cache_dir=cache_dir,
    )
    normalized, manifest = build_station_free_feature_snapshot(
        feature_rows,
        region_keys=selected_regions,
        source_manifest=source_manifest,
        spatial_bin_km=args.spatial_bin_km,
    )

    # Strict 100% expected-input coverage gate
    coverage_report = _compute_coverage(
        labels, normalized, spatial_bin_km=args.spatial_bin_km,
    )
    if args.strict_coverage and not coverage_report["passed"]:
        output = args.output_dir
        output.mkdir(parents=True, exist_ok=True)
        (output / "coverage_gate_report.json").write_text(
            json.dumps(
                {
                    "gate": "strict_expected_input_coverage",
                    "status": "FAILED",
                    "model": args.model,
                    "raw_expected_label_count": coverage_report["raw_expected_label_count"],
                    "covered_raw_label_count": coverage_report["covered_raw_label_count"],
                    "missing_raw_label_count": coverage_report["missing_raw_label_count"],
                    "missing_event_ids": coverage_report["missing_event_ids"],
                    "raw_label_coverage_fraction": coverage_report["raw_label_coverage_fraction"],
                    "unique_expected_feature_key_count": coverage_report["unique_expected_feature_key_count"],
                    "covered_unique_feature_key_count": coverage_report["covered_unique_feature_key_count"],
                    "missing_unique_feature_key_count": coverage_report["missing_unique_feature_key_count"],
                    "unique_feature_key_coverage_fraction": coverage_report["unique_feature_key_coverage_fraction"],
                    "events_without_id_count": coverage_report["events_without_id_count"],
                    "coverage_fraction": coverage_report["coverage_fraction"],
                    "missing_labels": coverage_report["missing_labels"],
                    "request_manifest": request_manifest,
                    "label_manifest": str(args.label_manifest),
                    "label_manifest_sha256": label_manifest_sha256,
                    "training_eligible": False,
                    "production_scoring_eligible": False,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "COVERAGE_GATE_FAILED",
            "raw_expected_label_count": coverage_report["raw_expected_label_count"],
            "covered_raw_label_count": coverage_report["covered_raw_label_count"],
            "missing_raw_label_count": coverage_report["missing_raw_label_count"],
            "unique_expected_feature_key_count": coverage_report["unique_expected_feature_key_count"],
            "covered_unique_feature_key_count": coverage_report["covered_unique_feature_key_count"],
            "coverage_fraction": coverage_report["coverage_fraction"],
            "report_path": str(output / "coverage_gate_report.json"),
        }, sort_keys=True))
        return 2

    output = args.output_dir
    write_station_free_feature_snapshot(output, normalized, manifest)
    (output / "source_provenance.json").write_text(
        json.dumps(
            {
                "version": "mvp4_open_meteo_interval_fetch_provenance_v1",
                "source_manifest": source_manifest,
                "fetch_records": fetch_records,
                "request_manifest": request_manifest,
                "label_manifest": str(args.label_manifest),
                "label_manifest_sha256": label_manifest_sha256,
                "requested_regions": sorted(selected_regions),
                "requested_seasons": sorted(selected_seasons),
                "included_seasons": included_seasons,
                "excluded_seasons": sorted(excluded_seasons),
                "excluded_label_count": len(excluded_labels),
                "excluded_labels": excluded_labels,
                "label_row_count": len(labels),
                "feature_row_count": len(normalized),
                "station_data_used": False,
                "training_eligible": False,
                "production_scoring_eligible": False,
                "coverage_gate": coverage_report,
                "coverage_gate_passed": coverage_report["passed"],
                # Explicit manifest semantics to prevent scope misinterpretation
                "primary_label_row_count": len(labels),
                "primary_unique_feature_key_count": coverage_report["unique_expected_feature_key_count"],
                "covered_primary_label_row_count": coverage_report["covered_raw_label_count"],
                "covered_primary_unique_feature_key_count": coverage_report["covered_unique_feature_key_count"],
                "coverage_scope": "label_linked_interval_features",
                "operational_grid_coverage": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Write bundle manifest linking all artifact hashes
    cache_manifest_data = None
    cache_manifest_path = output / "raw_cache" / "cache_manifest.json"
    if cache_manifest_path.is_file():
        try:
            cache_manifest_data = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache_manifest_data = None
    bundle = _write_bundle_manifest(
        output,
        label_manifest_path=args.label_manifest,
        label_manifest_sha256=label_manifest_sha256,
        snapshot_manifest=manifest,
        source_provenance=source_manifest,
        cache_manifest=cache_manifest_data,
        excluded_labels=excluded_labels,
        coverage_report=coverage_report,
    )
    print(json.dumps({
        "output_dir": str(output),
        "label_row_count": len(labels),
        "feature_row_count": len(normalized),
        "spatial_request_count": len(fetch_records),
        "feature_rows_sha256": manifest["feature_rows_sha256"],
        "manifest_hash": manifest["manifest_hash"],
        "training_eligible": manifest["training_eligible"],
        "station_data_used": manifest["station_data_used"],
        "coverage_gate_passed": coverage_report["passed"],
        "coverage_fraction": coverage_report["coverage_fraction"],
        "excluded_label_count": len(excluded_labels),
        "bundle_sha256": bundle["bundle_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OpenMeteoIntervalFeatureError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
