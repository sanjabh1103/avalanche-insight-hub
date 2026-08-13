#!/usr/bin/env python3
"""Prepare an interval shadow frame from reviewed labels and feature rows.

The command is deliberately bounded and non-promoting.  It emits a blocked
join report when historical feature coverage is absent, and it never fits a
model or marks a frame training/production eligible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.interval_training_reproducibility import (
    IntervalTrainingReproducibilityError,
    build_interval_training_evidence,
    build_interval_training_frame_from_staging,
    evaluate_interval_training_staging_join,
)
from backend.common.station_free_feature_snapshot import load_station_free_feature_snapshot
from backend.common.spatial_grouping import spatial_feature_join_key


def _load_label_snapshot(manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("label snapshot manifest must be an object")
    if manifest.get("training_eligible") is True or manifest.get("production_scoring_eligible") is True:
        raise ValueError("label snapshot promotion flags must remain false")
    events_path = manifest_path.parent / str(manifest.get("events_path") or "events.jsonl")
    payload = events_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != str(manifest.get("event_rows_sha256") or ""):
        raise ValueError("label snapshot event hash mismatch")
    rows = []
    for line in payload.decode("utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("label snapshot row must be an object")
            rows.append(value)
    return rows, manifest


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _prepare_label_rows(
    rows: list[dict[str, Any]],
    *,
    spatial_bin_km: float = 5.0,
    label_manifest: dict[str, Any] | None = None,
    label_manifest_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize missing staging join keys without changing source rows.

    Scene-aware GEE exports carry coordinates and region identity but may not
    persist the derived feature key.  The staging adapter derives the same
    deterministic grouping key used by the feature builder, records the
    derivation, and leaves the source snapshot bytes/hash untouched.
    """

    prepared: list[dict[str, Any]] = []
    derived_ids: list[str] = []
    manifest = label_manifest or {}
    overlap_report_path = Path(str(manifest.get("source_overlap_report") or ""))
    if not overlap_report_path.is_absolute() and label_manifest_path is not None:
        overlap_report_path = label_manifest_path.parent / overlap_report_path
    overlap_report: dict[str, Any] = {}
    if overlap_report_path.is_file():
        overlap_report = json.loads(overlap_report_path.read_text(encoding="utf-8"))
    reviewed_overlap = (
        str(overlap_report.get("status") or "").strip().lower() == "reviewed"
        and int(overlap_report.get("independent_positive_source_count") or 0) >= 2
    )
    source_manifests = manifest.get("source_manifests") if isinstance(manifest.get("source_manifests"), dict) else {}
    source_license_ids: dict[str, str] = {}
    for source_key, binding in source_manifests.items():
        if not isinstance(binding, dict):
            continue
        source_manifest_path = Path(str(binding.get("snapshot_manifest") or ""))
        if not source_manifest_path.is_absolute() and label_manifest_path is not None:
            candidate = label_manifest_path.parent / source_manifest_path
            source_manifest_path = candidate if candidate.is_file() else source_manifest_path
        if source_manifest_path.is_file():
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
            license_id = str(source_manifest.get("license_review_id") or "").strip()
            if license_id:
                source_license_ids[str(source_key)] = license_id
    for index, raw in enumerate(rows):
        row = dict(raw)
        source_key = str(row.get("source_key") or "").strip()
        # These are derived governance bindings, not new labels.  They make
        # the row-level interval contract auditable while preserving the
        # original catalog bytes and hash.
        if "source_overlap_review_status" not in row and reviewed_overlap:
            row["source_overlap_review_status"] = "reviewed"
        if "license_review_id" not in row and source_license_ids.get(source_key):
            row["license_review_id"] = source_license_ids[source_key]
        existing_key = next(
            (
                str(row.get(field) or "").strip()
                for field in ("feature_join_key", "spatial_group_id", "join_key")
                if str(row.get(field) or "").strip()
            ),
            "",
        )
        if not existing_key:
            row_id = str(
                row.get("source_event_id")
                or row.get("event_id")
                or row.get("external_id")
                or f"label:{index}"
            )
            region_key = str(row.get("region_key") or "").strip()
            if not region_key:
                raise ValueError(f"{row_id}: region_key is required to derive feature_join_key")
            try:
                row["feature_join_key"] = spatial_feature_join_key(
                    row.get("lat"),
                    row.get("lng"),
                    region_key,
                    bin_km=spatial_bin_km,
                )
            except ValueError as exc:
                raise ValueError(f"{row_id}: cannot derive feature_join_key") from exc
            row["feature_join_key_derivation"] = "spatial_feature_join_key_v1"
            derived_ids.append(row_id)
        prepared.append(row)
    return prepared, {
        "algorithm": "spatial_feature_join_key_v1",
        "spatial_bin_km": float(spatial_bin_km),
        "derived_count": len(derived_ids),
        "derived_source_event_ids_sha256": hashlib.sha256(
            "\n".join(sorted(derived_ids)).encode("utf-8")
        ).hexdigest()
        if derived_ids
        else None,
        "governance_bindings": {
            "source_overlap_review_status": "reviewed" if reviewed_overlap else None,
            "license_reviewed_source_keys": sorted(source_license_ids),
            "source_snapshot_bytes_unchanged": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-manifest", required=True, type=Path)
    parser.add_argument("--feature-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--region-key", action="append", required=True)
    parser.add_argument(
        "--minimum-label-coverage",
        type=float,
        default=1.0,
        help="minimum joined-label / selected-label ratio; defaults to 1.0 and fails closed",
    )
    parser.add_argument(
        "--select-covered-labels",
        action="store_true",
        help="explicitly build a bounded shadow frame from labels with eligible feature windows",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    labels, label_manifest = _load_label_snapshot(args.label_manifest)
    features, feature_manifest = load_station_free_feature_snapshot(args.feature_manifest)
    selected_regions = sorted({str(value).strip() for value in args.region_key if str(value).strip()})
    if not 0.0 < args.minimum_label_coverage <= 1.0:
        raise ValueError("--minimum-label-coverage must be greater than 0 and no greater than 1")
    labels = [row for row in labels if str(row.get("region_key") or "").strip() in selected_regions]
    labels, join_key_derivation = _prepare_label_rows(
        labels,
        label_manifest=label_manifest,
        label_manifest_path=args.label_manifest,
    )
    features = [row for row in features if str(row.get("region_key") or "").strip() in selected_regions]
    selection_report: dict[str, Any] | None = None
    if args.select_covered_labels:
        try:
            preliminary = evaluate_interval_training_staging_join(labels, features)
        except IntervalTrainingReproducibilityError as exc:
            raise ValueError(f"cannot select covered labels: {exc}") from exc
        covered_ids = {
            str(row.get("label_id") or "")
            for row in preliminary.get("rows", [])
            if str(row.get("label_id") or "")
        }
        all_ids = [
            str(row.get("source_event_id") or row.get("event_id") or row.get("external_id") or "")
            for row in labels
        ]
        excluded_ids = sorted(row_id for row_id in all_ids if row_id and row_id not in covered_ids)
        labels = [
            row for row in labels
            if str(row.get("source_event_id") or row.get("event_id") or row.get("external_id") or "")
            in covered_ids
        ]
        selection_report = {
            "mode": "bounded_shadow_only",
            "selection_rule": "retain labels with at least one eligible full feature window under interval_shadow_join_v1",
            "source_catalog_event_rows_sha256": label_manifest.get("event_rows_sha256"),
            "feature_manifest_hash": feature_manifest.get("manifest_hash"),
            "original_label_count": len(all_ids),
            "selected_label_count": len(labels),
            "excluded_label_count": len(excluded_ids),
            "excluded_label_ids": excluded_ids,
            "preliminary_join_summary": preliminary.get("summary", {}),
            "training_eligible": False,
            "production_scoring_eligible": False,
        }
    join_report = {
        "schema_version": "mvp4_interval_training_shadow_join_report_v1",
        "label_manifest": str(args.label_manifest),
        "label_event_rows_sha256": label_manifest.get("event_rows_sha256"),
        "feature_manifest": str(args.feature_manifest),
        "feature_manifest_hash": feature_manifest.get("manifest_hash"),
        "region_keys": selected_regions,
        "label_join_key_derivation": join_key_derivation,
        "training_eligible": False,
        "production_scoring_eligible": False,
        "shadow_only": True,
    }
    if selection_report is not None:
        join_report["bounded_selection"] = selection_report
    try:
        join = evaluate_interval_training_staging_join(labels, features)
    except IntervalTrainingReproducibilityError as exc:
        join_report["status"] = "blocked_interval_labels"
        join_report["error"] = str(exc)
        _write_json(output / "join_report.json", join_report)
        print(json.dumps({"status": join_report["status"], "error": str(exc)}, sort_keys=True))
        return 2
    join_report["join"] = join
    label_count = int(join.get("summary", {}).get("label_count", 0))
    joined_count = int(join.get("summary", {}).get("joined_count", 0))
    coverage = joined_count / label_count if label_count else 0.0
    join_report["coverage"] = {
        "selected_label_count": label_count,
        "joined_label_count": joined_count,
        "joined_label_coverage": round(coverage, 8),
        "minimum_required": args.minimum_label_coverage,
        "passed": coverage >= args.minimum_label_coverage,
    }
    if coverage < args.minimum_label_coverage:
        join_report["status"] = "blocked_partial_feature_coverage"
        _write_json(output / "join_report.json", join_report)
        print(json.dumps({"status": join_report["status"], "coverage": join_report["coverage"]}, sort_keys=True))
        return 2
    _write_json(output / "join_report.json", join_report)
    if joined_count == 0:
        join_report["status"] = "blocked_no_eligible_feature_window"
        _write_json(output / "join_report.json", join_report)
        print(json.dumps({"status": join_report["status"], "join": join["summary"]}, sort_keys=True))
        return 2

    try:
        frame = build_interval_training_frame_from_staging(labels, features)
        evidence = build_interval_training_evidence(
            frame,
            snapshot_path=output / "interval_training_frame.jsonl",
            snapshot_provenance={
                "label_manifest": str(args.label_manifest),
                "label_event_rows_sha256": label_manifest.get("event_rows_sha256"),
                "feature_manifest": str(args.feature_manifest),
                "feature_manifest_hash": feature_manifest.get("manifest_hash"),
                "feature_rows_sha256": feature_manifest.get("feature_rows_sha256"),
                "feature_source_keys": feature_manifest.get("source_keys"),
                "feature_cutoff_rule": feature_manifest.get("cutoff_rule"),
                "feature_review_status": feature_manifest.get("review_status"),
            },
        )
    except IntervalTrainingReproducibilityError as exc:
        join_report["status"] = "blocked_interval_evidence"
        join_report["error"] = str(exc)
        _write_json(output / "join_report.json", join_report)
        print(json.dumps({"status": join_report["status"], "error": str(exc)}, sort_keys=True))
        return 2

    join_report["status"] = "shadow_frame_written"
    join_report["evidence"] = evidence
    _write_json(output / "join_report.json", join_report)
    print(json.dumps({"status": join_report["status"], "evidence": evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
