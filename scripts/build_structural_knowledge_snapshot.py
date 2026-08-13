#!/usr/bin/env python3
"""Build a deterministic Phase 2 structural knowledge-graph snapshot.

This is the operator-controlled fallback when the full Understand semantic
orchestration is unavailable. It consumes the deterministic scan/import-map/
Tree-sitter batch results already produced under .understand-anything/intermediate.
It never claims semantic summaries, layers, or tours are complete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple


STATUS_EXCLUDE_PREFIXES = (
    '.understand-anything/', '.phase-loop/', '.fastembed_cache/',
    '.pytest_cache/', '.playwright-mcp/', '.playwright/', 'coverage/', 'dist/',
    'node_modules/', '.devin/', '.fable5/', '.claude/', '.codeium/', '.agents/',
    '.windsurf/', '.lovable/', 'playwright-report/', 'test-results/', 'artifacts/',
)

# Denylist zones from AGENTS.md — CRITICAL: these must never appear in the graph
DENYLIST_PATTERNS = (
    'backend/common/verification_exit_gates.py',
    'backend/common/sar_acceptance_policy.py',
    'backend/common/label_governance.py',
    'backend/common/risk_math.py',
    'backend/train_model.py',
    'supabase/config.toml',
    'backend/reproduction/',
    'backend/common/snowpack_physics.py',
)

# Allowlist — only these path prefixes are included in the graph.
# This is a defense-in-depth layer on top of .understandignore.
# Workspace, cache, agent metadata, and generated artifacts are excluded.
ALLOWED_PREFIXES = (
    'backend/',
    'src/',
    'supabase/',
    'tests/',
    'scripts/',
    'config/',
)

# Explicitly excluded path prefixes (checked after ALLOWED_PREFIXES).
# These would otherwise pass the allowlist but are not application code.
EXCLUDED_EXTRA_PREFIXES = (
    '.devin/',
    '.fable5/',
    '.fastembed_cache/',
    '.claude/',
    '.codeium/',
    '.agents/',
    '.pytest_cache/',
    '.playwright/',
    '.playwright-mcp/',
    '.windsurf/',
    '.phase-loop/',
    '.understand-anything/',
    '.lovable/',
    '.githooks/',
    'playwright-report/',
    'test-results/',
    'artifacts/',
    'node_modules/',
    'dist/',
    'coverage/',
    'backend/data/',
    'backend/artifacts/',
    'backend/artifacts-test-plan/',
)


def is_denylisted(path: str) -> bool:
    normalized = path.replace('\\', '/').lower()
    return any(normalized == p.lower() or normalized.startswith(p.lower()) for p in DENYLIST_PATTERNS)


def is_allowlisted(path: str) -> bool:
    """Check if a path is within the allowed application code prefixes."""
    normalized = path.replace('\\', '/')
    # Must match at least one allowed prefix
    if not any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return False
    # Must not match any explicitly excluded prefix
    for excluded in EXCLUDED_EXTRA_PREFIXES:
        if normalized.lower().startswith(excluded.lower()):
            return False
    return True


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class StructureResultDeduplication(NamedTuple):
    results: list[dict[str, Any]]
    duplicate_paths: list[str]
    duplicate_row_count: int
    conflicting_paths: list[str]


def deduplicate_structure_results(
    results: list[dict[str, Any]],
) -> StructureResultDeduplication:
    """Collapse overlapping structure batches without choosing conflicting data.

    The intermediate structure batches can overlap at batch boundaries. Identical
    rows are safe to collapse; conflicting rows for the same path must fail closed
    so the graph never silently chooses one structural interpretation.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        path = str(row.get("path") or "")
        if not path:
            raise ValueError("Structural row is missing a path")
        grouped.setdefault(path, []).append(row)

    unique_results: list[dict[str, Any]] = []
    duplicate_paths: list[str] = []
    conflicting_paths: list[str] = []
    duplicate_row_count = 0

    for path in sorted(grouped):
        rows = grouped[path]
        fingerprints = {canonical_bytes(row) for row in rows}
        if len(fingerprints) > 1:
            conflicting_paths.append(path)
            continue
        unique_results.append(rows[0])
        if len(rows) > 1:
            duplicate_paths.append(path)
            duplicate_row_count += len(rows) - 1

    if conflicting_paths:
        raise ValueError(
            "Conflicting structural rows for paths: "
            + ", ".join(conflicting_paths)
        )

    return StructureResultDeduplication(
        results=unique_results,
        duplicate_paths=duplicate_paths,
        duplicate_row_count=duplicate_row_count,
        conflicting_paths=conflicting_paths,
    )


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout


def source_worktree_status(root: Path) -> str:
    raw = git_output(root, 'status', '--short', '--untracked-files=all')
    retained: list[str] = []
    for line in raw.splitlines():
        path = line[3:] if len(line) > 3 else ''
        if ' -> ' in path:
            path = path.split(' -> ', 1)[-1]
        if any(path.startswith(prefix) for prefix in STATUS_EXCLUDE_PREFIXES):
            continue
        retained.append(line)
    return '\n'.join(retained) + ('\n' if retained else '')


def test_target_candidates(path: str) -> list[str]: 
    candidates: list[str] = []
    if path.startswith("backend/tests/test_") and path.endswith(".py"):
        stem = path.rsplit("/", 1)[-1][len("test_"):-3]
        candidates.extend([
            f"backend/common/{stem}.py",
            f"backend/{stem}.py",
            f"backend/inference/{stem}.py",
            f"backend/models/{stem}.py",
        ])
    elif path.startswith("src/test/"):
        filename = path.rsplit("/", 1)[-1]
        stem = filename
        for token in (".test.", ".spec."):
            if token in stem:
                stem = stem.split(token, 1)[0]
                break
        candidates.extend([f"src/{stem}", f"src/lib/{stem}", f"src/components/{stem}"])
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--intermediate", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    intermediate = (args.intermediate or root / ".understand-anything" / "intermediate").resolve()
    output = root / ".understand-anything" / "phase2-structural-graph.json"
    manifest_path = root / ".understand-anything" / "phase2-structural-manifest.json"

    scan = json.loads((intermediate / "scan-result.json").read_text())
    import_map = json.loads((intermediate / "import-map.json").read_text())["importMap"]
    results: list[dict[str, Any]] = []
    for path in sorted(intermediate.glob("structure-batch-*.json")):
        results.extend(json.loads(path.read_text()).get("results", []))
    # CRITICAL: Filter out denylist zone files before building the graph
    denylist_violations = [str(row["path"]) for row in results if is_denylisted(str(row["path"]))]
    results = [row for row in results if not is_denylisted(str(row["path"]))]
    # Defense-in-depth: Filter out workspace/cache/agent paths via allowlist
    allowlist_excluded = [str(row["path"]) for row in results if not is_allowlisted(str(row["path"]))]
    results = [row for row in results if is_allowlisted(str(row["path"]))]
    deduplication = deduplicate_structure_results(results)
    results = deduplication.results
    included_paths = sorted({str(row["path"]) for row in results})
    included_set = set(included_paths)

    def source_sha(path: str) -> str:
        file_path = root / path
        # G14: Reject symlinks to prevent hashing wrong content
        if file_path.is_symlink():
            raise ValueError(f"Symlink detected in source path: {path}")
        # G14: Skip files larger than 10MB to prevent memory issues
        if file_path.stat().st_size > 10_000_000:
            raise ValueError(f"File too large for hashing ({file_path.stat().st_size} bytes): {path}")
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    source_hashes = [
        {"path": path, "sha256": source_sha(path), "size_bytes": (root / path).stat().st_size}
        for path in included_paths
        if (root / path).is_file() and not (root / path).is_symlink()
    ]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    function_ids: dict[tuple[str, str], str] = {}

    for row in sorted(results, key=lambda item: str(item.get("path", ""))):
        path = str(row["path"])
        file_id = f"file:{path}"
        nodes.append({
            "id": file_id,
            "type": "file",
            "name": Path(path).name,
            "filePath": path,
            "language": row.get("language"),
            "fileCategory": row.get("fileCategory"),
            "lineCount": row.get("totalLines"),
            "complexity": "structural_only",
            "summary": "Deterministic structural node; semantic summary unavailable.",
            "tags": ["structural_only", str(row.get("language") or "unknown")],
            "sourceSha256": source_sha(path),
        })
        node_ids.add(file_id)
        for fn in row.get("functions") or []:
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            function_id = f"function:{path}:{name}"
            function_ids[(path, name)] = function_id
            nodes.append({
                "id": function_id,
                "type": "function",
                "name": name,
                "filePath": path,
                "startLine": fn.get("startLine"),
                "endLine": fn.get("endLine"),
                "params": fn.get("params") or [],
                "complexity": "structural_only",
                "summary": "Deterministically extracted function; semantic summary unavailable.",
                "tags": ["structural_only", "function"],
            })
            node_ids.add(function_id)
            edges.append({"source": file_id, "target": function_id, "type": "contains", "direction": "forward", "weight": 1.0})
        for cls in row.get("classes") or []:
            name = str(cls.get("name") or "").strip()
            if not name:
                continue
            class_id = f"class:{path}:{name}"
            nodes.append({
                "id": class_id,
                "type": "class",
                "name": name,
                "filePath": path,
                "startLine": cls.get("startLine"),
                "endLine": cls.get("endLine"),
                "methods": cls.get("methods") or [],
                "complexity": "structural_only",
                "summary": "Deterministically extracted class; semantic summary unavailable.",
                "tags": ["structural_only", "class"],
            })
            node_ids.add(class_id)
            edges.append({"source": file_id, "target": class_id, "type": "contains", "direction": "forward", "weight": 1.0})

    if len(nodes) != len(node_ids):
        raise ValueError("Structural graph contains duplicate node IDs after batch normalization")

    for path in included_paths:
        for imported_path in import_map.get(path, []):
            source, target = f"file:{path}", f"file:{imported_path}"
            if target in node_ids:
                edges.append({"source": source, "target": target, "type": "imports", "direction": "forward", "weight": 1.0})

    for row in results:
        path = str(row["path"])
        for call in row.get("callGraph") or []:
            source = function_ids.get((path, str(call.get("caller") or "")))
            target = function_ids.get((path, str(call.get("callee") or "")))
            if source and target:
                edges.append({"source": source, "target": target, "type": "calls", "direction": "forward", "weight": 1.0, "lineNumber": call.get("lineNumber")})

    for test_path in included_paths:
        if "/tests/" not in f"/{test_path}/" and not test_path.startswith("tests/") and not test_path.startswith("src/test/"):
            continue
        for candidate in test_target_candidates(test_path):
            if candidate in included_set:
                edges.append({"source": f"file:{candidate}", "target": f"file:{test_path}", "type": "tested_by", "direction": "forward", "weight": 1.0})
                break

    deduped_edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge["source"], edge["target"], edge["type"])
        if key not in seen and edge["source"] in node_ids and edge["target"] in node_ids:
            seen.add(key)
            deduped_edges.append(edge)

    analyzed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    analyzed_commit = git_output(root, "rev-parse", "HEAD").strip()
    status_output = source_worktree_status(root)
    dirty_digest = sha256_bytes(status_output.encode())
    graph = {
        "version": "phase2-structural-v2",
        "kind": "codebase-structural",
        "project": {
            "name": "Avalanche Insight Hub",
            "description": "Deterministic structural graph generated from the current checkout.",
            "languages": sorted({str(row.get("language")) for row in results if row.get("language")}),
            "frameworks": ["Python", "React", "Supabase", "Vite"],
            "gitCommitHash": analyzed_commit,
        },
        "nodes": nodes,
        "edges": deduped_edges,
        "layers": [],
        "tour": [],
        "provenance": {
            "analysisMode": "deterministic_structural_fallback",
            "semanticStatus": "unavailable_external_model_402",
            "includedPrefixes": list(ALLOWED_PREFIXES),
            "excludedPrefixes": ["docs/", "public/", ".git/", ".phase-loop/", ".understand-anything/"] + list(EXCLUDED_EXTRA_PREFIXES),
            "scanFileCount": scan.get("totalFiles"),
            "filteredByIgnore": scan.get("filteredByIgnore"),
            "filteredByAllowlist": len(allowlist_excluded),
            "allowlistExcludedPaths": allowlist_excluded,
            "worktreeDirty": bool(status_output.strip()),
            "worktreeStatusCount": len(status_output.splitlines()),
            "worktreeStatusSha256": dirty_digest,
            "structureResultDuplicatePathCount": len(deduplication.duplicate_paths),
            "structureResultDuplicateRowCount": deduplication.duplicate_row_count,
            "warnings": ["Full semantic Understand orchestration was unavailable; no LLM summaries, layers, or tour were generated."],
        },
    }
    graph_bytes = canonical_bytes(graph)
    # CRITICAL: Atomic write — write to temp file, then rename
    import tempfile
    import os
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(output.parent), suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(graph_bytes)
        os.replace(tmp_path, str(output))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    manifest = {
        "schemaVersion": "phase2_structural_graph_manifest_v1",
        "snapshotId": "phase2-structural-fallback-v2",
        "status": "structural_only_semantic_unavailable",
        "semanticStatus": "unavailable_external_model_402",
        "analyzedAt": analyzed_at,
        "analyzedCommit": analyzed_commit,
        "worktreeDirty": bool(status_output.strip()),
        "worktreeStatusCount": len(status_output.splitlines()),
        "worktreeStatusSha256": dirty_digest,
        "graphPath": str(output.relative_to(root)),
        "graphSha256": sha256_bytes(graph_bytes),
        "nodeCount": len(nodes),
        "edgeCount": len(deduped_edges),
        "sourceFileCount": len(source_hashes),
        "duplicateStructurePaths": deduplication.duplicate_paths,
        "duplicateStructureRows": deduplication.duplicate_row_count,
        "conflictingStructurePaths": deduplication.conflicting_paths,
        "sourceHashes": source_hashes,
        "includedPrefixes": list(ALLOWED_PREFIXES),
        "excludedPrefixes": ["docs/", "public/", ".git/", ".phase-loop/", ".understand-anything/"] + list(EXCLUDED_EXTRA_PREFIXES),
        "filteredByIgnore": scan.get("filteredByIgnore"),
        "filteredByAllowlist": len(allowlist_excluded),
        "allowlistExcludedPaths": allowlist_excluded,
        "verification": {
            "allEdgeEndpointsExist": all(edge["source"] in node_ids and edge["target"] in node_ids for edge in deduped_edges),
            "semanticSummaryAvailable": False,
            "fingerprintBaseline": "not written by this fallback",
            "denylistViolations": denylist_violations,
            "denylistClean": len(denylist_violations) == 0,
        },
        "warnings": ["This is not a replacement for the semantic Understand graph and is not customer-ready."],
    }
    # HIGH-3: Manifest HMAC integrity (advisor-approved: HMAC, not PKI)
    import hmac
    manifest["generatorVersion"] = "phase2-structural-v2"
    manifest["operatorIdentity"] = git_output(root, "config", "user.name").strip()
    # Compute HMAC over the manifest WITHOUT the manifestHmac field
    manifest_for_hmac = {k: v for k, v in manifest.items() if k != "manifestHmac"}
    manifest_bytes_for_hmac = (json.dumps(manifest_for_hmac, indent=2, sort_keys=True) + "\n").encode()
    hmac_secret = os.environ.get("KG_MANIFEST_HMAC_SECRET", "local-dev-default-secret")
    manifest_hmac = hmac.new(hmac_secret.encode(), manifest_bytes_for_hmac, hashlib.sha256).hexdigest()
    manifest["manifestHmac"] = manifest_hmac

    # CRITICAL: Atomic write for manifest
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    tmp_fd2, tmp_manifest_path = tempfile.mkstemp(dir=str(manifest_path.parent), suffix='.tmp')
    try:
        with os.fdopen(tmp_fd2, 'wb') as f:
            f.write(manifest_bytes)
        os.replace(tmp_manifest_path, str(manifest_path))
    except Exception:
        if os.path.exists(tmp_manifest_path):
            os.unlink(tmp_manifest_path)
        raise
    print(json.dumps({"graphSha256": manifest["graphSha256"], "analyzedCommit": analyzed_commit, "nodeCount": len(nodes), "edgeCount": len(deduped_edges), "sourceFileCount": len(source_hashes), "semanticStatus": manifest["semanticStatus"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
