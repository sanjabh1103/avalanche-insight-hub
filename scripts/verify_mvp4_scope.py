#!/usr/bin/env python3
"""Fail-closed scope verifier for the MVP4 ML/release lane.

``scripts/verify_release_scope.py`` is intentionally a knowledge-graph RC
profile and routes MVP4 paths out.  This companion requires a separate exact
allowlist, so an empty knowledge-RC selection can never be mistaken for an
MVP4 release decision.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.verify_release_scope import (
        CUSTOMER_MARKERS,
        GENERATED_NAMES,
        GENERATED_PREFIXES,
        GENERATED_SUFFIXES,
        GEE_MARKERS,
        DENYLIST_PATTERNS,
        canonical_hash,
        current_head,
        file_fingerprint,
        matches_denylist,
        normalize,
        remote_head,
        run_git,
        status_entries,
    )
except ModuleNotFoundError:  # direct execution from the scripts directory
    from verify_release_scope import (  # type: ignore
        CUSTOMER_MARKERS,
        GENERATED_NAMES,
        GENERATED_PREFIXES,
        GENERATED_SUFFIXES,
        GEE_MARKERS,
        DENYLIST_PATTERNS,
        canonical_hash,
        current_head,
        file_fingerprint,
        matches_denylist,
        normalize,
        remote_head,
        run_git,
        status_entries,
    )


SCHEMA_VERSION = "avalanche.mvp4_scope.v1"
SCOPE_TOOL_PATHS = {
    "scripts/verify_mvp4_scope.py",
    "backend/tests/test_mvp4_scope.py",
}
RELEASE_MANIFEST_RELATIVE = "docs/MVP4/00_governance/MVP4_RELEASE_MANIFEST.json"


def snapshot_excluded_paths(relative_manifest: str, relative_allowlist: str) -> set[str]:
    """Return control files excluded from the immutable dirty-entry snapshot.

    The release manifest records the freeze manifest hash. Including it in the
    frozen entry list would make the recorded hash change every time the
    release manifest is updated, so it is deliberately treated as a control
    document rather than candidate source content.
    """
    return {
        relative_manifest,
        relative_allowlist,
        RELEASE_MANIFEST_RELATIVE,
    }

# These are routing markers, not an approval list.  A path still needs to be
# named in the caller-provided allowlist before it can be selected.
MVP4_MARKERS = (
    "docs/mvp4/",
    "backend/data/open_source_labels/",
    "backend/open_forcing/",
    "backend/common/interval_",
    "backend/common/label_time_contract.py",
    "backend/common/open_source_label_lane.py",
    "backend/common/station_free_",
    "backend/common/terrain_diagnostics.py",
    "backend/common/training_reproducibility.py",
    "backend/scripts/audit_training_dataset.py",
    "backend/scripts/audit_exact_time_source_inventory.py",
    "backend/scripts/build_bipad_snapshot.py",
    "backend/scripts/build_day_resolution_overlap_report.py",
    "backend/scripts/build_open_forcing_snapshot.py",
    "backend/scripts/prepare_interval_training.py",
    "backend/tests/test_interval_",
    "backend/tests/test_audit_training_dataset.py",
    "backend/tests/test_build_bipad_snapshot.py",
    "backend/tests/test_build_day_resolution_overlap_report.py",
    "backend/tests/test_training_dataset.py",
    ".github/workflows/public_ml_pilot.yml",
    "scripts/check_mvp4_docs.py",
    "scripts/prepare_mvp4_pre_remote_approval.py",
    "scripts/verify_mvp4_pre_remote_gate.py",
    "scripts/verify_mvp4_shadow_scope_approval.py",
    "schemas/mvp4_pre_remote_approval.template.json",
    "schemas/mvp4_shadow_scope_approval.template.json",
    "backend/tests/test_mvp4_pre_remote_gate.py",
    "backend/tests/test_mvp4_shadow_scope_approval.py",
    "docs/dual_repository_architecture.md",
)
MVP4_CUSTOMER_PREFIXES = ("docs/mvp4/01_customer_review/",)
MVP4_GENERATED_PREFIXES = ("docs/mvp4/05_generated_assets/",)
MVP4_GEE_HANDOFF_MARKERS = (
    "export_gee_scene_aware_snapshot",
    "scene_aware",
)

FROZEN_ENTRY_FIELDS = (
    "path",
    "git_status",
    "kind",
    "sha256",
    "category",
    "allowlist_selectable",
    "reason",
)


def classify_mvp4_path(path: str) -> tuple[str, bool, str]:
    """Return ``category``, whether it may be selected, and the reason."""
    value = normalize(path)

    if matches_denylist(path):
        return "denylist_manual_review", False, "GLM denylist path requires planner approval"
    if any(marker in value for marker in (*GEE_MARKERS, *MVP4_GEE_HANDOFF_MARKERS)):
        return "gee_exclude", False, "separate GEE provenance handoff; not auto-selected"
    if any(marker in value for marker in CUSTOMER_MARKERS):
        return "customer_exclude", False, "customer/delivery material is outside the ML RC"
    if value.startswith(MVP4_CUSTOMER_PREFIXES):
        return "customer_exclude", False, "MVP4 customer-review material is outside the ML RC"
    if value.startswith(MVP4_GENERATED_PREFIXES):
        return "generated_exclude", False, "MVP4 generated delivery output is outside the source RC"
    if value.startswith(".phase-loop/"):
        return "evidence_out", False, "phase evidence is preserved but not source-release content"
    if path in SCOPE_TOOL_PATHS:
        return "scope_tooling", False, "scope tooling is not candidate feature content"
    if (
        value in GENERATED_NAMES
        or value.startswith(GENERATED_PREFIXES)
        or value.endswith(GENERATED_SUFFIXES)
        or "/__pycache__/" in value
        or value.endswith("/__pycache__")
    ):
        return "generated_exclude", False, "generated/cache/media output is not a source candidate"
    if any(marker in value for marker in MVP4_MARKERS):
        return "mvp4_candidate", True, "MVP4 lane; exact allowlist still required"
    return "manual_review", False, "unknown path requires exact owner and hunk review"


def parse_allowlist_text(text: str) -> tuple[list[str], list[str]]:
    """Parse one repository-relative path per line, returning paths/errors."""
    paths: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        normalized = posixpath.normpath(value.replace("\\", "/"))
        if normalized.startswith("/") or normalized == ".." or normalized.startswith("../"):
            errors.append(f"line {line_number}: path must be repository-relative: {value}")
            continue
        if normalized in seen:
            errors.append(f"line {line_number}: duplicate path: {normalized}")
            continue
        seen.add(normalized)
        paths.append(normalized)
    return sorted(paths), errors


def _entry(root: Path, status: str, path: str) -> dict[str, Any]:
    category, selectable, reason = classify_mvp4_path(path)
    kind, sha256 = file_fingerprint(root, path)
    return {
        "path": path,
        "git_status": status,
        "kind": kind,
        "sha256": sha256,
        "category": category,
        "allowlist_selectable": selectable,
        "reason": reason,
    }


def compare_frozen_entries(
    frozen_entries: list[dict[str, Any]],
    current_entries: list[dict[str, Any]],
) -> list[str]:
    """Return fail-closed drift errors for the complete dirty-worktree snapshot."""
    frozen_by_path = {str(entry.get("path")): entry for entry in frozen_entries}
    current_by_path = {str(entry.get("path")): entry for entry in current_entries}
    errors: list[str] = []

    duplicate_frozen = len(frozen_entries) != len(frozen_by_path)
    duplicate_current = len(current_entries) != len(current_by_path)
    if duplicate_frozen:
        errors.append("frozen entry snapshot contains duplicate paths")
    if duplicate_current:
        errors.append("current entry snapshot contains duplicate paths")

    for path in sorted(current_by_path.keys() - frozen_by_path.keys()):
        errors.append(f"frozen entry added: {path}")
    for path in sorted(frozen_by_path.keys() - current_by_path.keys()):
        errors.append(f"frozen entry removed: {path}")
    for path in sorted(frozen_by_path.keys() & current_by_path.keys()):
        before = frozen_by_path[path]
        after = current_by_path[path]
        changed_fields = [
            field
            for field in FROZEN_ENTRY_FIELDS
            if before.get(field) != after.get(field)
        ]
        if changed_fields:
            errors.append(
                f"frozen entry changed: {path} ({', '.join(changed_fields)})"
            )
    return errors


def build_manifest(root: Path, manifest_path: Path, allowlist_path: Path) -> dict[str, Any]:
    relative_manifest = manifest_path.relative_to(root).as_posix()
    allowlist_relative = allowlist_path.relative_to(root).as_posix()
    excluded_paths = snapshot_excluded_paths(relative_manifest, allowlist_relative)
    allowlist, allowlist_errors = parse_allowlist_text(
        allowlist_path.read_text(encoding="utf-8")
    )
    observed = [
        _entry(root, status, path)
        for status, path in status_entries(root)
        if path not in excluded_paths
    ]
    observed = sorted(observed, key=lambda item: item["path"])
    by_path = {item["path"]: item for item in observed}
    missing = [path for path in allowlist if path not in by_path]
    forbidden = [
        path
        for path in allowlist
        if path in by_path and not by_path[path]["allowlist_selectable"]
    ]
    selected = [
        path
        for path in allowlist
        if path in by_path
        and by_path[path]["allowlist_selectable"]
        and "D" not in by_path[path]["git_status"]
    ]
    categories = Counter(item["category"] for item in observed)
    statuses = Counter(item["git_status"] for item in observed)
    errors = list(allowlist_errors)
    errors.extend(f"allowlist path is not dirty/observed: {path}" for path in missing)
    errors.extend(f"allowlist path is forbidden by policy: {path}" for path in forbidden)
    if not selected:
        errors.append("MVP4 allowlist selects no non-deleted candidate path")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "frozen_local_review_only",
        "release_candidate_ready": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(root),
        "branch": run_git(root, "branch", "--show-current"),
        "source_head": current_head(root),
        "private_origin_main": remote_head(root, "origin"),
        "public_main_observed": remote_head(root, "public"),
        "allowlist_path": allowlist_relative,
        "allowlist_sha256": canonical_hash(allowlist),
        "allowlist_errors": errors,
        "worktree_snapshot": {
            "status_command": "git status --porcelain=v1 -uall -z",
            "entry_count": len(observed),
            "dirty": bool(observed),
            "status_counts": dict(sorted(statuses.items())),
            "category_counts": dict(sorted(categories.items())),
        },
        "snapshot_excluded_paths": sorted(excluded_paths),
        "entries": observed,
        "entries_sha256": canonical_hash(observed),
        "selected_paths": selected,
        "selection_hash": canonical_hash(
            [by_path[path] for path in selected]
        ),
        "decision": "NO_GO_UNTIL_MVP4_SCOPE_APPROVED_AND_CLEAN",
        "proof_boundary": "Local scope classification only; no staging, commit, push, sync, deployment, model fit, or customer approval.",
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def verify_manifest(root: Path, manifest_path: Path, allowlist_path: Path, skip_remote: bool) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read manifest: {exc}"]
    try:
        allowlist, allowlist_errors = parse_allowlist_text(
            allowlist_path.read_text(encoding="utf-8")
        )
    except OSError as exc:
        return [f"cannot read allowlist: {exc}"]
    errors.extend(allowlist_errors)
    relative_manifest = manifest_path.relative_to(root).as_posix()
    relative_allowlist = allowlist_path.relative_to(root).as_posix()
    excluded_paths = snapshot_excluded_paths(relative_manifest, relative_allowlist)
    current = sorted(
        [
            _entry(root, status, path)
            for status, path in status_entries(root)
            if path not in excluded_paths
        ],
        key=lambda item: item["path"],
    )
    current_by_path = {item["path"]: item for item in current}
    expected_entries = payload.get("entries")
    if not isinstance(expected_entries, list):
        errors.append("manifest is missing the complete frozen entries list")
    else:
        errors.extend(compare_frozen_entries(expected_entries, current))
        if payload.get("entries_sha256") != canonical_hash(expected_entries):
            errors.append("frozen entries hash does not match manifest entries")
        if payload.get("entries_sha256") != canonical_hash(current):
            errors.append("current worktree entries hash differs from frozen snapshot")
    if payload.get("worktree_snapshot", {}).get("entry_count") != len(current):
        errors.append("worktree entry count changed since freeze")
    expected_selected = payload.get("selected_paths", [])
    if payload.get("allowlist_sha256") != canonical_hash(allowlist):
        errors.append("allowlist content changed since freeze")
    if not isinstance(expected_selected, list) or not expected_selected:
        errors.append("MVP4 selection is empty")
    for path in expected_selected:
        if path not in current_by_path:
            errors.append(f"selected path disappeared since freeze: {path}")
            continue
        entry = current_by_path[path]
        if not entry["allowlist_selectable"]:
            errors.append(f"selected path is forbidden by policy: {path}")
        if "D" in entry["git_status"]:
            errors.append(f"selected path is deleted: {path}")
    if sorted(expected_selected) != allowlist:
        errors.append("allowlist selection differs from manifest selection")
    if payload.get("source_head") != current_head(root):
        errors.append("source HEAD changed since freeze")
    if not skip_remote and payload.get("private_origin_main") != remote_head(root, "origin"):
        errors.append("private origin changed since freeze")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--skip-remote", action="store_true")
    args = parser.parse_args()
    root = Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel")).resolve()
    manifest = (root / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    allowlist = (root / args.allowlist).resolve() if not args.allowlist.is_absolute() else args.allowlist.resolve()
    if args.command == "build":
        payload = build_manifest(root, manifest, allowlist)
        print(json.dumps({
            "status": payload["status"],
            "entry_count": payload["worktree_snapshot"]["entry_count"],
            "selected_count": len(payload["selected_paths"]),
            "freeze_error_count": len(payload["allowlist_errors"]),
            "allowlist_errors": payload["allowlist_errors"],
            "manifest": str(manifest),
        }, sort_keys=True))
        return 2 if payload["allowlist_errors"] else 0
    errors = verify_manifest(root, manifest, allowlist, args.skip_remote)
    if errors:
        print(json.dumps({"status": "FAIL", "error_count": len(errors), "errors": errors}, indent=2))
        return 1
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    print(json.dumps({
        "status": "PASS_MVP4_SCOPE_FREEZE",
        "entry_count": payload["worktree_snapshot"]["entry_count"],
        "selected_count": len(payload["selected_paths"]),
        "release_candidate_ready": payload["release_candidate_ready"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
