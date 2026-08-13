#!/usr/bin/env python3
"""Audit local import closure for the frozen knowledge-graph release scope.

This is a read-only companion to verify_release_scope.py. It does not expand
the release candidate. It reports local imports that are selected, unchanged
baseline dependencies, or modified/untracked dependencies that require review.
The latter fail closed so a scope list cannot be mistaken for a buildable
candidate when an implementation file is missing from the approved scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.verify_release_scope import (
        DEFAULT_MANIFEST,
        classify_path,
        file_fingerprint,
        git_root,
        status_entries,
        verify_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - supports direct script import
    from verify_release_scope import (  # type: ignore
        DEFAULT_MANIFEST,
        classify_path,
        file_fingerprint,
        git_root,
        status_entries,
        verify_manifest,
    )


IMPORT_PATTERN = re.compile(
    r"(?:\bfrom\s*|\bimport\s*(?:type\s*)?)[\"']([^\"']+)[\"']"
)
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
INDEX_NAMES = (
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "index.mjs",
    "index.cjs",
)
BLOCKING_STATES = {
    "missing_blocker",
    "untracked_external_dependency",
    "changed_external_dependency",
}
BASELINE_SUBSTITUTION_CANDIDATES = {
    "supabase/functions/_shared/auth.ts",
}


def resolve_local_import(root: Path, source_path: str, specifier: str) -> str | None:
    if not specifier.startswith("."):
        return None
    candidate = (root / source_path).parent / specifier
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    if resolved.is_file():
        return resolved.relative_to(root.resolve()).as_posix()
    for suffix in SOURCE_SUFFIXES:
        with_suffix = Path(f"{resolved}{suffix}")
        if with_suffix.is_file():
            return with_suffix.relative_to(root.resolve()).as_posix()
    if resolved.is_dir():
        for name in INDEX_NAMES:
            index_path = resolved / name
            if index_path.is_file():
                return index_path.relative_to(root.resolve()).as_posix()
    return None


def git_head_sha256(root: Path, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def tracked_in_head(root: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path}"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def dependency_state(
    root: Path,
    path: str,
    selected: set[str],
    status_by_path: dict[str, str],
    approved_baseline_dependencies: set[str],
) -> dict[str, Any]:
    category, _, reason = classify_path(path)
    kind, current_sha = file_fingerprint(root, path)
    status = status_by_path.get(path, "")
    head_sha = git_head_sha256(root, path)

    if path in selected:
        state = "selected"
    elif kind == "missing":
        state = "missing_blocker"
    elif not tracked_in_head(root, path):
        state = "untracked_external_dependency"
    elif current_sha != head_sha or status.strip():
        if path in approved_baseline_dependencies:
            state = "approved_baseline_substitution"
        else:
            state = "changed_external_dependency"
    else:
        state = "baseline_dependency"

    return {
        "path": path,
        "state": state,
        "blocking": state in BLOCKING_STATES,
        "git_status": status,
        "kind": kind,
        "current_sha256": current_sha,
        "head_sha256": head_sha,
        "category": category,
        "classification_reason": reason,
    }


def scan_closure(
    root: Path,
    manifest: dict[str, Any],
    approved_baseline_dependencies: set[str] | None = None,
) -> dict[str, Any]:
    selected = set(manifest["rc_selected_paths"])
    approved_baseline_dependencies = approved_baseline_dependencies or set()
    status_by_path = {path: status for status, path in status_entries(root)}
    imports: list[dict[str, str]] = []
    source_paths = sorted(
        path for path in selected if path.endswith((".ts", ".tsx", ".js", ".jsx"))
    )
    for source_path in source_paths:
        source = root / source_path
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        for specifier in IMPORT_PATTERN.findall(text):
            resolved = resolve_local_import(root, source_path, specifier)
            if resolved:
                imports.append({"from": source_path, "specifier": specifier, "to": resolved})

    unique_imports: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in imports:
        key = (item["from"], item["to"])
        if key not in seen:
            seen.add(key)
            unique_imports.append(item)

    dependencies = {
        path: dependency_state(
            root,
            path,
            selected,
            status_by_path,
            approved_baseline_dependencies,
        )
        for path in sorted({item["to"] for item in unique_imports} - selected)
    }
    for item in unique_imports:
        if item["to"] in dependencies:
            item["state"] = dependencies[item["to"]]["state"]

    blockers = [item for item in dependencies.values() if item["blocking"]]
    return {
        "schema_version": "avalanche.knowledge_release_closure.v1",
        "selected_count": len(selected),
        "selected_source_count": len(source_paths),
        "resolved_import_count": len(unique_imports),
        "external_dependency_count": len(dependencies),
        "blocking_dependency_count": len(blockers),
        "imports": unique_imports,
        "dependencies": list(dependencies.values()),
        "blocking_dependencies": blockers,
        "approved_baseline_dependencies": sorted(approved_baseline_dependencies),
        "decision": "NO_GO_CANDIDATE_CLOSURE" if blockers else "CLOSURE_BASELINE_COMPLETE",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--allow-baseline-dependency",
        action="append",
        default=[],
        help="Explicitly allow a known changed dependency to use its HEAD copy in the candidate.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = git_root()
    manifest_path = (root / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    errors = verify_manifest(root, manifest_path)
    if errors:
        print(json.dumps({"status": "FAIL_SCOPE_MANIFEST", "errors": errors}, indent=2))
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    approved = set(args.allow_baseline_dependency)
    unsupported = approved - BASELINE_SUBSTITUTION_CANDIDATES
    if unsupported:
        print(json.dumps({
            "status": "FAIL_UNSUPPORTED_BASELINE_DEPENDENCY",
            "paths": sorted(unsupported),
            "allowed_paths": sorted(BASELINE_SUBSTITUTION_CANDIDATES),
        }, indent=2))
        return 2
    report = scan_closure(root, manifest, approved)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["blocking_dependency_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
