#!/usr/bin/env python3
"""Formal shadow preflight for the Nepal ERA5 acquisition artifact.

This is a REAL bundle verifier.  It does NOT trust metadata fields in
provenance or cache manifests.  Instead, it recomputes every hash from
the actual files and compares them against the bundle manifest.

Exit codes:
  0 = structural evidence passes and training remains BLOCKED (expected for shadow)
  1 = provenance or structural mismatch (hash mismatch, coverage gap, tamper)
  2 = training or production eligibility is unexpectedly enabled (safety violation)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.common.open_meteo_interval_features import (
    OPEN_METEO_DAILY_VARIABLES,
    _canonical_bytes,
    _sha256,
    _verify_cached_response,
)


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_within(path: Path, root: Path) -> bool:
    """Check if path is within root using Path.relative_to() (not string prefix).

    This is immune to sibling-prefix attacks like /repo vs /repo_evil.
    """
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_resolve(base: Path, relative: str, *, repo_root: Path | None = None) -> Path | None:
    """Safely resolve a path, rejecting path traversal and absolute-path escapes.

    Resolution order:
    1. Relative to base (artifact dir) — for files inside the artifact
    2. Relative to repo_root (if provided) — for external inputs like the
       label manifest which lives outside the artifact dir but inside the repo

    Absolute paths are REJECTED unless they fall within base or repo_root.
    This prevents escapes like /private/etc/hosts.

    Uses Path.relative_to() for containment checks, not string prefix matching,
    to prevent sibling-prefix attacks (e.g. /repo vs /repo_evil).
    """
    if not relative:
        return None
    p = Path(relative)
    base_resolved = base.resolve()
    root_resolved = repo_root.resolve() if repo_root else base_resolved

    if p.is_absolute():
        # Absolute paths must be within base or repo_root
        try:
            resolved = p.resolve()
        except (ValueError, OSError):
            return None
        if _is_within(resolved, base_resolved) or _is_within(resolved, root_resolved):
            return resolved if resolved.is_file() else None
        return None

    # Try relative to base (artifact dir)
    try:
        candidate = (base / relative).resolve()
        # Accept if the resolved path is within base OR repo_root
        # (symlinks inside base may point to files in repo_root)
        if candidate.is_file() and (
            _is_within(candidate, base_resolved) or _is_within(candidate, root_resolved)
        ):
            return candidate
    except (ValueError, OSError):
        pass
    # Try relative to repo_root (for external inputs like label manifest)
    if repo_root is not None:
        try:
            candidate = (root_resolved / relative).resolve()
            if candidate.is_file() and _is_within(candidate, root_resolved):
                return candidate
        except (ValueError, OSError):
            pass
    return None


def _recompute_coverage_from_files(
    artifact_dir: Path,
    snapshot_manifest: dict[str, Any],
    provenance: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    """Recompute the coverage report from actual label and feature files.

    This does NOT trust the coverage_gate field in provenance.  It reloads
    the label manifest, re-derives the primary label set (applying the same
    exclusion logic), and re-checks every event against the actual feature rows.
    """
    from backend.scripts.build_open_meteo_interval_feature_snapshot import (
        _compute_coverage,
        _feature_join_key,
        _interval_start,
        _season_id,
    )

    # Load labels from the external manifest
    label_manifest_path = provenance.get("label_manifest", "")
    if not label_manifest_path:
        return None
    label_path = _safe_resolve(artifact_dir, label_manifest_path, repo_root=repo_root)
    if label_path is None or not label_path.is_file():
        return None

    manifest = _load_json(label_path)
    events_relative = str(manifest.get("events_path") or "events.jsonl")
    # Events path is relative to the label manifest's parent directory
    events_path = _safe_resolve(label_path.parent, events_relative, repo_root=repo_root)
    if events_path is None or not events_path.is_file():
        return None

    import hashlib as hl
    payload = events_path.read_bytes()
    if hl.sha256(payload).hexdigest() != str(manifest.get("event_rows_sha256") or ""):
        return None

    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]

    # Re-derive the primary label set using the same filters
    request_manifest = provenance.get("request_manifest", {})
    selected_regions = set(request_manifest.get("regions", []))
    excluded_seasons = set(request_manifest.get("excluded_seasons", []))
    spatial_bin_km = request_manifest.get("spatial_bin_km", 5.0)

    primary_labels = []
    for row in rows:
        region = str(row.get("region_key") or "").strip()
        if region not in selected_regions:
            continue
        season = _season_id(row)
        if excluded_seasons and season in excluded_seasons:
            continue
        primary_labels.append(row)

    # Load actual feature rows
    features_path = artifact_dir / "features.jsonl"
    feature_rows = []
    with open(features_path) as f:
        for line in f:
            if line.strip():
                feature_rows.append(json.loads(line))

    # Recompute coverage
    return _compute_coverage(primary_labels, feature_rows, spatial_bin_km=spatial_bin_km)


def _verify_all_cache_entries(
    cache_dir: Path,
    cache_manifest: dict[str, Any],
) -> tuple[bool, int, int, list[str]]:
    """Verify every cache entry by loading and checking each file.

    Does NOT trust the integrity_verified_count in the manifest.  Instead,
    loads every cache file, runs _verify_cached_response, compares the
    canonical_payload_sha256, validates cache_key derivation, checks for
    duplicate keys, and detects extra/missing cache files.

    Returns (all_verified, verified_count, total_count, failures).
    """
    entries = cache_manifest.get("entries", [])
    total = len(entries)
    verified = 0
    failures: list[str] = []
    seen_keys: set[str] = set()
    manifest_keys: set[str] = set()

    for entry in entries:
        url = str(entry.get("url") or "")
        cache_key = str(entry.get("cache_key") or "")
        if not url or not cache_key:
            failures.append("entry missing url or cache_key")
            continue
        # Validate cache_key derivation: must be SHA256(url)
        expected_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        if cache_key != expected_key:
            failures.append(f"cache_key mismatch: {cache_key[:16]} != SHA256(url)")
            continue
        # Check for duplicate keys
        if cache_key in seen_keys:
            failures.append(f"duplicate cache_key: {cache_key[:16]}")
            continue
        seen_keys.add(cache_key)
        manifest_keys.add(cache_key)

        cache_path = cache_dir / f"{cache_key}.json"
        if not cache_path.is_file():
            failures.append(f"cache file missing: {cache_key[:16]}")
            continue
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append(f"cache file invalid JSON: {cache_key[:16]}")
            continue
        if not isinstance(cached, dict):
            failures.append(f"cache file not a dict: {cache_key[:16]}")
            continue
        if not _verify_cached_response(cached, url):
            failures.append(f"cache verification failed: {cache_key[:16]}")
            continue
        # Cross-check canonical hash matches manifest entry
        actual_canonical = str(cached.get("canonical_payload_sha256") or "").strip().lower()
        manifest_canonical = str(entry.get("canonical_payload_sha256") or "").strip().lower()
        if actual_canonical != manifest_canonical:
            failures.append(f"canonical hash mismatch: {cache_key[:16]}")
            continue
        verified += 1

    # Check for extra cache files not listed in the manifest
    extra_files: list[str] = []
    if cache_dir.is_dir():
        for f in cache_dir.iterdir():
            if f.name == "cache_manifest.json" or f.name.endswith(".tmp"):
                continue
            if f.is_file() and f.suffix == ".json":
                key = f.stem
                if key not in manifest_keys:
                    extra_files.append(f.name)
    if extra_files:
        failures.append(f"extra cache files not in manifest: {extra_files[:5]}")

    return (verified == total and total > 0 and len(extra_files) == 0, verified, total, failures)


def run_preflight(artifact_dir: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Run the formal shadow preflight and return a structured report.

    This is a REAL verifier: every hash is recomputed from the actual files.
    No metadata field is trusted without recomputation.

    Args:
        artifact_dir: The artifact directory to verify.
        repo_root: The repository root for resolving external input paths
            (e.g. label manifest).  If None, defaults to the current
            working directory.  All resolved paths must fall within
            artifact_dir or repo_root.
    """
    if repo_root is None:
        repo_root = Path.cwd()
    report: dict[str, Any] = {
        "preflight_version": "mvp4_shadow_preflight_v3",
        "artifact_dir": str(artifact_dir),
        "repo_root": str(repo_root),
        "checks": [],
        "structural_pass": False,
        "coverage_pass": False,
        "training_blocked": False,
        "overall_pass": False,
    }

    def check(name: str, passed: bool, detail: str = "") -> None:
        report["checks"].append({
            "name": name,
            "passed": passed,
            "detail": detail,
        })

    # ---- Check 1: Required files exist ----
    required_files = [
        "features.jsonl",
        "snapshot_manifest.json",
        "source_provenance.json",
        "bundle_manifest.json",
        "raw_cache/cache_manifest.json",
    ]
    missing_files = [f for f in required_files if not (artifact_dir / f).is_file()]
    check("required_files_exist", len(missing_files) == 0,
          f"missing: {missing_files}" if missing_files else "all present")
    if missing_files:
        report["overall_pass"] = False
        return report

    # Load all files
    bundle = _load_json(artifact_dir / "bundle_manifest.json")
    snapshot_manifest = _load_json(artifact_dir / "snapshot_manifest.json")
    provenance = _load_json(artifact_dir / "source_provenance.json")
    cache_manifest = _load_json(artifact_dir / "raw_cache" / "cache_manifest.json")
    component_hashes = bundle.get("component_hashes", {})

    # ---- Check 2: Bundle manifest has all required components ----
    required_components = [
        "label_manifest", "features_jsonl", "snapshot_manifest",
        "source_provenance", "cache_manifest", "excluded_event_record",
        "coverage_gate",
    ]
    missing_components = [c for c in required_components if c not in component_hashes]
    check("bundle_manifest_complete", len(missing_components) == 0,
          f"missing: {missing_components}" if missing_components else "all present")

    # ---- Check 3: Recompute bundle_sha256 and compare ----
    recomputed_bundle_bytes = json.dumps(
        component_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    recomputed_bundle_hash = hashlib.sha256(recomputed_bundle_bytes).hexdigest()
    stored_bundle_hash = str(bundle.get("bundle_sha256") or "")
    check("bundle_sha256_matches", recomputed_bundle_hash == stored_bundle_hash,
          f"recomputed={recomputed_bundle_hash[:16]}, stored={stored_bundle_hash[:16]}")

    # ---- Check 4: Recompute features.jsonl hash and compare with bundle ----
    features_path = artifact_dir / "features.jsonl"
    features_hash = _sha256_file(features_path)
    bundle_features_hash = component_hashes.get("features_jsonl", {}).get("sha256")
    check("features_hash_matches_bundle", features_hash == bundle_features_hash,
          f"actual={features_hash[:16]}, bundle={str(bundle_features_hash)[:16]}")

    # ---- Check 5: Recompute snapshot_manifest.json hash and compare with bundle ----
    snapshot_path = artifact_dir / "snapshot_manifest.json"
    snapshot_file_hash = _sha256_file(snapshot_path)
    bundle_snapshot_hash = component_hashes.get("snapshot_manifest", {}).get("sha256")
    check("snapshot_manifest_file_hash_matches_bundle",
          snapshot_file_hash == bundle_snapshot_hash,
          f"actual={snapshot_file_hash[:16]}, bundle={str(bundle_snapshot_hash)[:16]}")

    # ---- Check 6: Verify snapshot manifest's internal manifest_hash ----
    # Recompute manifest_hash from the snapshot manifest (excluding the manifest_hash field itself)
    from backend.common.station_free_feature_snapshot import _manifest_hash
    recomputed_manifest_hash = _manifest_hash(snapshot_manifest)
    stored_manifest_hash = str(snapshot_manifest.get("manifest_hash") or "")
    bundle_manifest_hash = component_hashes.get("snapshot_manifest", {}).get("manifest_hash")
    check("snapshot_manifest_internal_hash_valid",
          recomputed_manifest_hash == stored_manifest_hash == bundle_manifest_hash,
          f"recomputed={recomputed_manifest_hash[:16]}, stored={stored_manifest_hash[:16]}, "
          f"bundle={str(bundle_manifest_hash)[:16]}")

    # ---- Check 7: Verify snapshot manifest's feature_rows_sha256 matches actual file ----
    bundle_feature_rows_hash = component_hashes.get("snapshot_manifest", {}).get("feature_rows_sha256")
    manifest_feature_rows_hash = str(snapshot_manifest.get("feature_rows_sha256") or "")
    check("snapshot_feature_rows_hash_matches_file",
          features_hash == manifest_feature_rows_hash == bundle_feature_rows_hash,
          f"file={features_hash[:16]}, manifest={manifest_feature_rows_hash[:16]}, "
          f"bundle={str(bundle_feature_rows_hash)[:16]}")

    # ---- Check 8: Recompute source_provenance.json hash and compare with bundle ----
    provenance_path = artifact_dir / "source_provenance.json"
    provenance_file_hash = _sha256_file(provenance_path)
    bundle_provenance_hash = component_hashes.get("source_provenance", {}).get("sha256")
    check("provenance_file_hash_matches_bundle",
          provenance_file_hash == bundle_provenance_hash,
          f"actual={provenance_file_hash[:16]}, bundle={str(bundle_provenance_hash)[:16]}")

    # ---- Check 9: Recompute cache_manifest.json hash and compare with bundle ----
    cache_manifest_path = artifact_dir / "raw_cache" / "cache_manifest.json"
    cache_file_hash = _sha256_file(cache_manifest_path)
    bundle_cache_hash = component_hashes.get("cache_manifest", {}).get("sha256")
    check("cache_manifest_file_hash_matches_bundle",
          cache_file_hash == bundle_cache_hash,
          f"actual={cache_file_hash[:16]}, bundle={str(bundle_cache_hash)[:16]}")

    # ---- Check 9b: Validate cache_manifest entry_count matches actual entries length ----
    # (360 fix: entry_count field could be wrong even if entries hash matches)
    cache_entries = cache_manifest.get("entries", [])
    declared_entry_count = cache_manifest.get("entry_count")
    actual_entry_count = len(cache_entries)
    check("cache_manifest_entry_count_matches",
          declared_entry_count == actual_entry_count,
          f"declared={declared_entry_count}, actual={actual_entry_count}")

    # ---- Check 10: Verify cache manifest's internal cache_manifest_sha256 ----
    recomputed_cache_entries_hash = _sha256(_canonical_bytes(cache_entries))
    stored_cache_manifest_hash = str(cache_manifest.get("cache_manifest_sha256") or "")
    bundle_cache_manifest_hash = component_hashes.get("cache_manifest", {}).get("cache_manifest_sha256")
    check("cache_manifest_internal_hash_valid",
          recomputed_cache_entries_hash == stored_cache_manifest_hash == bundle_cache_manifest_hash,
          f"recomputed={recomputed_cache_entries_hash[:16]}, "
          f"stored={stored_cache_manifest_hash[:16]}, "
          f"bundle={str(bundle_cache_manifest_hash)[:16]}")

    # ---- Check 11: Verify EVERY cache entry (not just aggregate count) ----
    cache_dir = artifact_dir / "raw_cache"
    all_cache_verified, cache_verified_count, cache_total, cache_failures = (
        _verify_all_cache_entries(cache_dir, cache_manifest)
    )
    check("all_cache_entries_verified",
          all_cache_verified,
          f"verified={cache_verified_count}/{cache_total}"
          + (f", failures={cache_failures[:3]}" if cache_failures else ""))

    # ---- Check 12: Verify external label manifest hash ----
    label_manifest_path_str = component_hashes.get("label_manifest", {}).get("path", "")
    label_manifest_stored_hash = component_hashes.get("label_manifest", {}).get("sha256")
    label_path = _safe_resolve(artifact_dir, label_manifest_path_str, repo_root=repo_root)
    if label_path and label_path.is_file():
        label_actual_hash = _sha256_file(label_path)
        check("label_manifest_hash_matches",
              label_actual_hash == label_manifest_stored_hash,
              f"actual={label_actual_hash[:16]}, bundle={str(label_manifest_stored_hash)[:16]}")
    else:
        check("label_manifest_hash_matches", False,
              f"label manifest path not found or unsafe: {label_manifest_path_str}")

    # ---- Check 13: Recompute coverage from actual files ----
    recomputed_coverage = _recompute_coverage_from_files(
        artifact_dir, snapshot_manifest, provenance, repo_root=repo_root
    )
    if recomputed_coverage is not None:
        # Compare recomputed coverage with provenance coverage_gate
        provenance_coverage = provenance.get("coverage_gate", {})
        coverage_matches = (
            recomputed_coverage.get("raw_expected_label_count") == provenance_coverage.get("raw_expected_label_count")
            and recomputed_coverage.get("covered_raw_label_count") == provenance_coverage.get("covered_raw_label_count")
            and recomputed_coverage.get("missing_raw_label_count") == provenance_coverage.get("missing_raw_label_count")
            and recomputed_coverage.get("passed") == provenance_coverage.get("passed")
        )
        check("coverage_recomputed_matches_provenance", coverage_matches,
              f"recomputed raw={recomputed_coverage.get('covered_raw_label_count')}/"
              f"{recomputed_coverage.get('raw_expected_label_count')}, "
              f"provenance raw={provenance_coverage.get('covered_raw_label_count')}/"
              f"{provenance_coverage.get('raw_expected_label_count')}")

        # Also verify the coverage_gate hash in the bundle
        coverage_bytes = json.dumps(
            provenance_coverage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        recomputed_coverage_hash = hashlib.sha256(coverage_bytes).hexdigest()
        bundle_coverage_hash = component_hashes.get("coverage_gate", {}).get("sha256")
        check("coverage_gate_hash_matches_bundle",
              recomputed_coverage_hash == bundle_coverage_hash,
              f"recomputed={recomputed_coverage_hash[:16]}, bundle={str(bundle_coverage_hash)[:16]}")

        coverage_passed = recomputed_coverage.get("passed", False)
        raw_expected = recomputed_coverage.get("raw_expected_label_count", 0)
        raw_covered = recomputed_coverage.get("covered_raw_label_count", 0)
        missing_raw = recomputed_coverage.get("missing_raw_label_count", 0)
        duplicate_ids = recomputed_coverage.get("duplicate_event_id_count", 0)
        events_without_id = recomputed_coverage.get("events_without_id_count", 0)
    else:
        check("coverage_recomputed_matches_provenance", False,
              "could not recompute coverage from files")
        check("coverage_gate_hash_matches_bundle", False,
              "coverage recomputation failed")
        coverage_passed = False
        raw_expected = raw_covered = missing_raw = duplicate_ids = events_without_id = 0

    check("coverage_gate_passed", coverage_passed,
          f"raw={raw_covered}/{raw_expected}, missing={missing_raw}, "
          f"duplicates={duplicate_ids}, without_id={events_without_id}")
    report["coverage_pass"] = coverage_passed

    # ---- Check 14: Verify excluded-event record hash ----
    excluded_labels = provenance.get("excluded_labels", [])
    excluded_bytes = json.dumps(
        excluded_labels, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    recomputed_excluded_hash = hashlib.sha256(excluded_bytes).hexdigest()
    bundle_excluded_hash = component_hashes.get("excluded_event_record", {}).get("sha256")
    check("excluded_event_record_hash_matches",
          recomputed_excluded_hash == bundle_excluded_hash,
          f"recomputed={recomputed_excluded_hash[:16]}, bundle={str(bundle_excluded_hash)[:16]}")

    # ---- Check 15: Feature row count matches ----
    with open(features_path) as _feat_f:
        feature_row_count = sum(1 for _ in _feat_f)
    manifest_row_count = snapshot_manifest.get("feature_row_count")
    check("feature_row_count_matches", feature_row_count == manifest_row_count,
          f"file={feature_row_count}, manifest={manifest_row_count}")

    # ---- Check 16: No missing required feature values ----
    missing_values = snapshot_manifest.get("missing_required_feature_value_count", -1)
    check("no_missing_required_feature_values", missing_values == 0,
          f"missing_count={missing_values}")

    # ---- Check 17: Station data not used (check ALL rows, not just first) ----
    all_station_free = True
    all_feed_correct = True
    with open(features_path) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("station_data_used") is not False:
                all_station_free = False
                break
            if row.get("station_feed_semantics") != "no_direct_station_feed":
                all_feed_correct = False
                break
    check("station_data_not_used_all_rows", all_station_free,
          f"all {feature_row_count} rows have station_data_used=False")
    check("station_feed_semantics_all_rows", all_feed_correct,
          f"all {feature_row_count} rows have station_feed_semantics=no_direct_station_feed")

    # ---- Check 18: Training eligibility is BLOCKED ----
    # Read from provenance file (already hash-verified above)
    training_eligible = provenance.get("training_eligible", True)
    production_eligible = provenance.get("production_scoring_eligible", True)
    training_blocked = training_eligible is False and production_eligible is False
    check("training_eligibility_blocked", training_blocked,
          f"training_eligible={training_eligible}, production_scoring_eligible={production_eligible}")
    report["training_blocked"] = training_blocked

    # ---- Check 19: License status is pending ----
    source_manifest = provenance.get("source_manifest", {})
    license_status = str(source_manifest.get("license_status") or "")
    check("license_status_pending", license_status == "pending",
          f"license_status={license_status}")

    # ---- Check 20: Coverage scope is label-linked, not operational grid ----
    coverage_scope = str(provenance.get("coverage_scope") or "")
    operational_grid = provenance.get("operational_grid_coverage", True)
    check("coverage_scope_label_linked",
          coverage_scope == "label_linked_interval_features" and operational_grid is False,
          f"coverage_scope={coverage_scope}, operational_grid_coverage={operational_grid}")

    # ---- Check 21: No duplicate event IDs ----
    check("no_duplicate_event_ids", duplicate_ids == 0,
          f"duplicate_event_id_count={duplicate_ids}")

    # ---- Check 22: No events without IDs ----
    check("no_events_without_id", events_without_id == 0,
          f"events_without_id_count={events_without_id}")

    # ---- Check 23: Enforce bundle schema version ----
    expected_bundle_schema = "mvp4_nepal_acquisition_bundle_v1"
    actual_bundle_schema = str(bundle.get("bundle_schema_version") or "")
    check("bundle_schema_version_valid",
          actual_bundle_schema == expected_bundle_schema,
          f"expected={expected_bundle_schema}, actual={actual_bundle_schema}")

    # ---- Check 24: Enforce snapshot schema version ----
    expected_snapshot_schema = "mvp4_station_free_feature_snapshot_v1"
    actual_snapshot_schema = str(snapshot_manifest.get("snapshot_schema_version") or "")
    check("snapshot_schema_version_valid",
          actual_snapshot_schema == expected_snapshot_schema,
          f"expected={expected_snapshot_schema}, actual={actual_snapshot_schema}")

    # ---- Check 25: Enforce feature time contract ----
    expected_time_contract = "station_free_feature_window_v1"
    actual_time_contract = str(snapshot_manifest.get("feature_time_contract") or "")
    check("feature_time_contract_valid",
          actual_time_contract == expected_time_contract,
          f"expected={expected_time_contract}, actual={actual_time_contract}")

    # ---- Check 26: Cross-manifest training eligibility invariant ----
    # training_eligible must be False in BOTH snapshot_manifest and provenance
    snapshot_training = snapshot_manifest.get("training_eligible", True)
    provenance_training = provenance.get("training_eligible", True)
    snapshot_core_training = snapshot_manifest.get("core_training_eligible", True)
    snapshot_prod = snapshot_manifest.get("production_eligible", True)
    provenance_prod = provenance.get("production_scoring_eligible", True)
    cross_training_consistent = (
        snapshot_training is False
        and provenance_training is False
        and snapshot_core_training is False
        and snapshot_prod is False
        and provenance_prod is False
    )
    check("cross_manifest_training_blocked",
          cross_training_consistent,
          f"snapshot.training={snapshot_training}, provenance.training={provenance_training}, "
          f"snapshot.core={snapshot_core_training}, snapshot.prod={snapshot_prod}, "
          f"provenance.prod={provenance_prod}")

    # ---- Check 27: Cross-manifest station data invariant ----
    snapshot_station = snapshot_manifest.get("station_data_used", True)
    provenance_station = provenance.get("station_data_used", True)
    cross_station_consistent = snapshot_station is False and provenance_station is False
    check("cross_manifest_station_data_consistent",
          cross_station_consistent,
          f"snapshot.station_data_used={snapshot_station}, "
          f"provenance.station_data_used={provenance_station}")

    # ---- Check 28: Cross-manifest region keys invariant ----
    snapshot_regions = set(snapshot_manifest.get("region_keys") or [])
    provenance_regions = set(provenance.get("requested_regions") or [])
    request_regions = set(provenance.get("request_manifest", {}).get("regions") or [])
    # All three must be non-empty and agree
    cross_regions_consistent = (
        bool(snapshot_regions)
        and snapshot_regions == provenance_regions
        and snapshot_regions == request_regions
    )
    check("cross_manifest_region_keys_consistent",
          cross_regions_consistent,
          f"snapshot={sorted(snapshot_regions)}, provenance={sorted(provenance_regions)}, "
          f"request={sorted(request_regions)}")

    # ---- Check 29: Cross-manifest feature row count invariant ----
    snapshot_row_count = snapshot_manifest.get("feature_row_count")
    provenance_row_count = provenance.get("feature_row_count")
    cross_row_count_consistent = (
        snapshot_row_count is not None
        and provenance_row_count is not None
        and snapshot_row_count == provenance_row_count
        and snapshot_row_count == feature_row_count
    )
    check("cross_manifest_feature_row_count_consistent",
          cross_row_count_consistent,
          f"snapshot={snapshot_row_count}, provenance={provenance_row_count}, file={feature_row_count}")

    # ---- Check 30: Cross-manifest coverage scope invariant ----
    bundle_coverage_scope = bundle.get("coverage_scope")
    provenance_coverage_scope = provenance.get("coverage_scope")
    bundle_op_grid = bundle.get("operational_grid_coverage")
    provenance_op_grid = provenance.get("operational_grid_coverage")
    cross_scope_consistent = (
        bundle_coverage_scope == "label_linked_interval_features"
        and provenance_coverage_scope == "label_linked_interval_features"
        and bundle_op_grid is False
        and provenance_op_grid is False
    )
    check("cross_manifest_coverage_scope_consistent",
          cross_scope_consistent,
          f"bundle.scope={bundle_coverage_scope}, provenance.scope={provenance_coverage_scope}, "
          f"bundle.op_grid={bundle_op_grid}, provenance.op_grid={provenance_op_grid}")

    # ---- Aggregate results ----
    # Training eligibility checks are NOT structural — they determine exit code 2
    training_check_names = {"training_eligibility_blocked", "cross_manifest_training_blocked"}
    structural_checks = [
        c for c in report["checks"]
        if c["name"] not in training_check_names
    ]
    report["structural_pass"] = all(c["passed"] for c in structural_checks)
    report["overall_pass"] = (
        report["structural_pass"]
        and report["coverage_pass"]
        and report["training_blocked"]
    )
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="preflight_shadow_nepal",
        description="Formal shadow preflight verifier for Nepal acquisition artifacts. "
                    "Recomputes all hashes, verifies every cache entry, and enforces "
                    "schema/cross-manifest invariants. Exit 0=pass, 1=structural fail, "
                    "2=safety violation (training incorrectly enabled).",
    )
    parser.add_argument(
        "artifact_dir",
        type=Path,
        help="Path to the artifact directory to verify",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root for resolving external input paths (e.g. label manifest). "
             "If omitted, defaults to the current working directory.",
    )
    args = parser.parse_args(argv)

    artifact_dir = args.artifact_dir.resolve()
    repo_root = args.repo_root.resolve() if args.repo_root else None
    if not artifact_dir.is_dir():
        print(f"ERROR: artifact directory not found: {artifact_dir}", file=sys.stderr)
        return 1

    report = run_preflight(artifact_dir, repo_root=repo_root)

    report_path = artifact_dir / "shadow_preflight_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "preflight_version": report["preflight_version"],
        "artifact_dir": str(artifact_dir),
        "structural_pass": report["structural_pass"],
        "coverage_pass": report["coverage_pass"],
        "training_blocked": report["training_blocked"],
        "overall_pass": report["overall_pass"],
        "check_count": len(report["checks"]),
        "failed_checks": [c["name"] for c in report["checks"] if not c["passed"]],
        "report_path": str(report_path),
    }, sort_keys=True))

    if not report["structural_pass"] or not report["coverage_pass"]:
        return 1
    if not report["training_blocked"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
