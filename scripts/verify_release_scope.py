#!/usr/bin/env python3
"""Build and verify a hash-anchored local release-scope manifest.

This tool is intentionally a scope freeze, not a staging or publication tool.
It expands the complete Git worktree status, assigns every path a conservative
review category, and selects only the knowledge-workspace source surface for
the current local review candidate. Unknown or mixed paths stay out of the
candidate. Verification fails closed when a path, status, or content hash
changes after the manifest is built.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "avalanche.release_scope.v1"
DEFAULT_MANIFEST = Path(".phase-loop/release-scope-manifest-20260802.json")

DENYLIST_PATTERNS = (
    "backend/common/verification_exit_gates.py",
    "backend/common/sar_acceptance_policy.py",
    "backend/common/label_governance.py",
    "backend/common/risk_math.py",
    "backend/train_model.py",
    "supabase/config.toml",
    "backend/reproduction/",
    "backend/common/snowpack_physics.py",
)

KNOWLEDGE_RC_EXACT = {
    ".understand-anything/.understandignore",
    ".understand-anything/phase2-structural-graph.json",
    ".understand-anything/phase2-structural-manifest.json",
    "src/components/knowledge-graph/AccessibilityTableView.tsx",
    "src/components/knowledge-graph/AudienceDepthControls.tsx",
    "src/components/knowledge-graph/KnowledgeGraphView.tsx",
    "src/components/knowledge-graph/NodeDetailPanel.tsx",
    "src/components/knowledge-graph/PerspectiveSwitcher.tsx",
    "src/lib/knowledge-graph/audienceModel.ts",
    "src/lib/knowledge-graph/explainer.ts",
    "src/lib/knowledge-graph/explainerApi.ts",
    "src/lib/knowledge-graph/graphData.ts",
    "src/lib/knowledge-graph/perspectives.ts",
    "src/lib/knowledge-graph/safeCodeApi.ts",
    "src/lib/knowledge-graph/sectionGenerators.ts",
    "src/test/knowledge-graph/audience-depth-controls.test.tsx",
    "src/test/knowledge-graph/audience-model.test.ts",
    "src/test/knowledge-graph/code-api-server.test.ts",
    "src/test/knowledge-graph/explainer.test.ts",
    "src/test/knowledge-graph/graph-index.test.ts",
    "src/test/knowledge-graph/graph-view.test.tsx",
    "src/test/knowledge-graph/model-endpoint.test.ts",
    "src/test/knowledge-graph/perspective-filter.test.ts",
    "src/test/knowledge-graph/perspectives.test.ts",
    "src/test/knowledge-graph/provenance-card.test.ts",
    "src/test/knowledge-graph/safe-code-api.test.ts",
    "src/test/knowledge-graph/section-generators.test.ts",
    "src/test/knowledge-graph/vite-node-packet.test.ts",
    "tests/e2e/knowledge-graph-smoke.spec.ts",
    "docs/KNOWLEDGE_GRAPH_GUIDE.md",
    "supabase/functions/knowledge-graph-model/index.test.ts",
    "supabase/functions/knowledge-graph-model/index.ts",
    "supabase/functions/knowledge-graph-model/snapshot-storage.test.ts",
    "src/pages/KnowledgeGraphPage.tsx",
    "src/pages/KnowledgeGraphUnavailable.tsx",
    "scripts/build_structural_knowledge_snapshot.py",
    "scripts/refresh_knowledge_graph_structural.sh",
    "vite-plugin-code-api.ts",
    "backend/tests/test_structural_knowledge_snapshot.py",
    "backend/tests/test_knowledge_graph_model_migration.py",
    "supabase/functions/_shared/knowledgeGraphModelPolicy.ts",
    "supabase/functions/_shared/knowledgeGraphSnapshot.ts",
    "supabase/functions/_shared/knowledgeGraphSnapshotStorage.ts",
    "supabase/migrations/20260806120000_knowledge_graph_model_endpoint.sql",
    "supabase/migrations/20260807120000_create_knowledge_graph_snapshot_bucket.sql",
}

SCOPE_TOOL_EXACT = {"scripts/verify_release_scope.py"}

GEE_MARKERS = (
    "gee_sar",
    "gee_extractor",
    "historical_sar_backfill",
    "provenance_backfill",
    "build_gee_sar_snapshot",
    "test_build_gee_sar_snapshot",
)

CUSTOMER_MARKERS = (
    "shared_content",
    "customer_export",
    "google_drive_upload",
    "upload_ready_prompts",
    "artifacts/marketing/",
    "docs/mvp_v2/",
    "docs/customer",
)

GENERATED_PREFIXES = (
    ".fastembed_cache/",
    ".understand-anything/",
    ".pytest_cache/",
    ".playwright-mcp/",
    "coverage/",
    "dist/",
    "playwright-report/",
)

GENERATED_NAMES = {
    ".DS_Store",
    "playwright-results.json",
    "public/manifest.json",
}

GENERATED_SUFFIXES = (
    ".mp3",
    ".mp4",
    ".onnx",
    ".npz",
    ".npy",
    ".pt",
    ".pth",
    ".tif",
    ".tiff",
)

MVP4_MARKERS = (
    "docs/mvp4/",
    "docs/mvp3/",
    "backend/data/",
    "backend/open_forcing/",
    "backend/common/interval_shadow_join.py",
    "backend/common/label_time_contract.py",
    "backend/common/open_source_label_lane.py",
    "backend/common/ravafcast_",
    "backend/common/shadow_",
    "backend/common/terrain_diagnostics.py",
    "backend/common/training_reproducibility.py",
    "backend/scripts/audit_",
    "backend/scripts/build_bipad_snapshot.py",
    "backend/scripts/build_bounded_source_overlap_report.py",
    "backend/scripts/build_hiaval_snapshot.py",
    "backend/scripts/build_open_forcing_snapshot.py",
)


def run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        check=check,
    )
    return result.stdout.strip()


def git_root() -> Path:
    return Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel")).resolve()


def current_head(root: Path) -> str:
    return run_git(root, "rev-parse", "HEAD")


def remote_head(root: Path, remote: str, branch: str = "refs/heads/main") -> str | None:
    try:
        output = run_git(root, "ls-remote", remote, branch)
    except subprocess.CalledProcessError:
        return None
    return output.split()[0] if output else None


def status_entries(root: Path) -> list[tuple[str, str]]:
    raw = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall", "-z"],
        cwd=root,
    )
    records = raw.split(b"\0")
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            raise ValueError("Malformed NUL-delimited Git status record")
        status = record[:2].decode("utf-8", "surrogateescape")
        path = record[3:].decode("utf-8", "surrogateescape").replace("\\", "/")
        if "R" in status or "C" in status:
            raise ValueError("Rename/copy status requires explicit path review")
        entries.append((status, path))
    return entries


def normalize(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/")).lower()


def matches_denylist(path: str) -> bool:
    value = normalize(path)
    return any(value == pattern or value.startswith(pattern) for pattern in DENYLIST_PATTERNS)


def is_knowledge_candidate(path: str) -> bool:
    return path in KNOWLEDGE_RC_EXACT


def classify_path(path: str) -> tuple[str, bool, str]:
    """Return category, RC selection, and conservative routing reason."""
    value = normalize(path)

    if matches_denylist(path):
        return "denylist_manual_review", False, "GLM denylist path requires planner approval"

    if any(marker in value for marker in GEE_MARKERS):
        return "gee_exclude", False, "separate GEE provenance workstream; never enter this RC"

    if any(marker in value for marker in CUSTOMER_MARKERS):
        return "customer_exclude", False, "customer/delivery material is outside the local code RC"

    if value.startswith(".phase-loop/"):
        return "evidence_out", False, "phase evidence is preserved but not source-release content"

    if path in SCOPE_TOOL_EXACT:
        return "scope_tooling", False, "scope verifier is governance tooling, not candidate feature content"

    # Approved knowledge-graph artifacts are generated files intentionally
    # retained for the local learning release; select them before the broad
    # generated-output exclusion below.
    if is_knowledge_candidate(path):
        return "knowledge_rc_in", True, "approved local knowledge-workspace source surface"

    if value in GENERATED_NAMES or value.startswith(GENERATED_PREFIXES) or value.endswith(
        GENERATED_SUFFIXES
    ) or "/__pycache__/" in value or value.endswith("/__pycache__"):
        return "generated_exclude", False, "generated/cache/media output is not a source candidate"

    if any(marker in value for marker in MVP4_MARKERS):
        return "mvp4_ml_out", False, "MVP4/ML lane remains separate from this knowledge RC"

    if value.startswith((".github/", "docs/", "supabase/", "backend/", "src/")):
        return "manual_review", False, "mixed or unrelated path requires exact hunk/ownership review"

    return "manual_review", False, "no automatic inclusion rule; unknown paths stay excluded"


def file_fingerprint(root: Path, relative_path: str) -> tuple[str, str]:
    path = root / relative_path
    if path.is_symlink():
        target = os.readlink(path).encode("utf-8", "surrogateescape")
        return "symlink", hashlib.sha256(b"symlink\0" + target).hexdigest()
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "file", digest.hexdigest()
    return "missing", ""


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_entries(root: Path, manifest_path: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for status, path in status_entries(root):
        if path == manifest_path:
            continue
        category, rc_selected, reason = classify_path(path)
        kind, sha256 = file_fingerprint(root, path)
        entries.append(
            {
                "path": path,
                "git_status": status,
                "kind": kind,
                "sha256": sha256,
                "category": category,
                "rc_selected": rc_selected,
                "reason": reason,
            }
        )
    return sorted(entries, key=lambda item: item["path"])


def scope_hash(entries: list[dict[str, Any]]) -> str:
    selected = sorted([
        {
            "path": entry["path"],
            "git_status": entry["git_status"],
            "kind": entry["kind"],
            "sha256": entry["sha256"],
        }
        for entry in entries
        if entry["rc_selected"]
    ], key=lambda item: item["path"])
    return canonical_hash(selected)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def build_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    relative_manifest = manifest_path.relative_to(root).as_posix()
    entries = make_entries(root, relative_manifest)
    categories = Counter(entry["category"] for entry in entries)
    statuses = Counter(entry["git_status"] for entry in entries)
    selected = [entry["path"] for entry in entries if entry["rc_selected"]]
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
        "purpose": "Machine-checkable local scope freeze; not staging, commit, push, sync, deployment, or customer approval.",
        "self_excluded_paths": [
            {"path": relative_manifest, "reason": "manifest is generated after the observed status snapshot"}
        ],
        "policy": {
            "unknown_path_policy": "manual_review_and_rc_out",
            "rc_categories": ["knowledge_rc_in"],
            "forbidden_rc_categories": [
                "gee_exclude",
                "customer_exclude",
                "denylist_manual_review",
                "generated_exclude",
                "evidence_out",
                "mvp4_ml_out",
                "manual_review",
                "scope_tooling",
            ],
            "denylist_patterns": list(DENYLIST_PATTERNS),
        },
        "worktree_snapshot": {
            "status_command": "git status --porcelain=v1 -uall -z",
            "entry_count": len(entries),
            "dirty": bool(entries),
            "status_counts": dict(sorted(statuses.items())),
            "category_counts": dict(sorted(categories.items())),
        },
        "rc_selected_paths": selected,
        "rc_scope_sha256": scope_hash(entries),
        "entries": entries,
        "remote_state_changed": False,
        "decision": "NO_GO_UNTIL_EXACT_SCOPE_APPROVED",
        "next_gate": "Verify this manifest without drift, then perform a separately authorized read-only remote audit.",
    }
    atomic_write_json(manifest_path, payload)
    return payload


def verify_manifest(root: Path, manifest_path: Path, skip_remote: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read manifest: {exc}"]

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    relative_manifest = manifest_path.relative_to(root).as_posix()
    expected_entries = payload.get("entries")
    if not isinstance(expected_entries, list):
        return ["manifest entries must be a list"]

    expected_by_path: dict[str, dict[str, Any]] = {}
    for entry in expected_entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path:
            errors.append("entry has no valid path")
            continue
        if path in expected_by_path:
            errors.append(f"duplicate manifest path: {path}")
        expected_by_path[path] = entry

    current_entries = make_entries(root, relative_manifest)
    current_by_path = {entry["path"]: entry for entry in current_entries}
    expected_paths = set(expected_by_path)
    current_paths = set(current_by_path)
    for path in sorted(expected_paths - current_paths):
        errors.append(f"path disappeared since freeze: {path}")
    for path in sorted(current_paths - expected_paths):
        errors.append(f"unclassified/new path after freeze: {path}")

    for path in sorted(expected_paths & current_paths):
        expected = expected_by_path[path]
        current = current_by_path[path]
        for field in ("git_status", "kind", "sha256", "category", "rc_selected"):
            if expected.get(field) != current.get(field):
                errors.append(
                    f"drift for {path}: {field} expected={expected.get(field)!r} current={current.get(field)!r}"
                )
        recalculated_category, recalculated_selected, _ = classify_path(path)
        if expected.get("category") != recalculated_category:
            errors.append(f"policy classification drift for {path}")
        if expected.get("rc_selected") != recalculated_selected:
            errors.append(f"policy selection drift for {path}")

    selected_entries = [entry for entry in expected_entries if entry.get("rc_selected") is True]
    if not selected_entries:
        errors.append("RC selection is empty")
    for entry in selected_entries:
        path = str(entry.get("path", ""))
        category = entry.get("category")
        if category != "knowledge_rc_in":
            errors.append(f"forbidden category selected for RC: {path} ({category})")
        if matches_denylist(path):
            errors.append(f"denylist path selected for RC: {path}")
        value = normalize(path)
        if any(marker in value for marker in GEE_MARKERS):
            errors.append(f"GEE path selected for RC: {path}")
        if any(marker in value for marker in CUSTOMER_MARKERS):
            errors.append(f"customer path selected for RC: {path}")

    if payload.get("source_head") != current_head(root):
        errors.append("source HEAD changed since freeze")
    if not skip_remote:
        expected_origin = payload.get("private_origin_main")
        actual_origin = remote_head(root, "origin")
        if expected_origin != actual_origin:
            errors.append(
                f"private origin changed since freeze: expected={expected_origin!r} current={actual_origin!r}"
            )

    if payload.get("rc_scope_sha256") != scope_hash(expected_entries):
        errors.append("rc_scope_sha256 does not match manifest entries")
    if payload.get("worktree_snapshot", {}).get("entry_count") != len(expected_entries):
        errors.append("worktree entry count does not match manifest entries")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--skip-remote", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = git_root()
    manifest_path = (root / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    if args.command == "build":
        payload = build_manifest(root, manifest_path)
        print(json.dumps({
            "status": payload["status"],
            "entry_count": payload["worktree_snapshot"]["entry_count"],
            "rc_selected_count": len(payload["rc_selected_paths"]),
            "rc_scope_sha256": payload["rc_scope_sha256"],
            "manifest": str(manifest_path),
        }, sort_keys=True))
        return 0

    errors = verify_manifest(root, manifest_path, skip_remote=args.skip_remote)
    if errors:
        print(json.dumps({"status": "FAIL", "error_count": len(errors), "errors": errors}, indent=2))
        return 1
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(json.dumps({
        "status": "PASS_LOCAL_SCOPE_FREEZE",
        "entry_count": payload["worktree_snapshot"]["entry_count"],
        "rc_selected_count": len(payload["rc_selected_paths"]),
        "rc_scope_sha256": payload["rc_scope_sha256"],
        "worktree_dirty": payload["worktree_snapshot"]["dirty"],
        "release_candidate_ready": payload["release_candidate_ready"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
