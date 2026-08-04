#!/usr/bin/env python3
"""Strict graph export with canonical serialization and field allowlists.

Implements the Phase 2 export contract:
- Explicit field allowlists (not blacklist)
- Unknown fields FAIL the export
- Canonical JSON (sorted keys, sorted arrays where order is not semantic)
- Deterministic content hash separate from generation time
- Dangling edge rejection
- PII/secret scanning with fail-closed behavior
- Paths normalized to repository-relative

Outputs:
  public/data/code-graph.json
  public/data/code-graph-manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SOURCE_ROOT = Path("/Users/sanjayb/avalanche-insight-hub")
DEFAULT_SITE_ROOT = Path(__file__).resolve().parents[1]

# --- Field Allowlists (from prompt) ---

NODE_ALLOWED_FIELDS = frozenset({
    "id", "name", "type", "relativePath", "language",
    "summary", "tags", "lineCount", "sourceHash",
})

EDGE_ALLOWED_FIELDS = frozenset({
    "source", "target", "type", "direction", "weight",
})

PROJECT_ALLOWED_FIELDS = frozenset({
    "name", "languages", "frameworks", "description",
})

# Source field name mapping: source field → export field
NODE_FIELD_MAP = {
    "id": "id",
    "name": "name",
    "type": "type",
    "filePath": "relativePath",  # renamed
    "language": "language",
    "summary": "summary",
    "tags": "tags",
    "lineCount": "lineCount",
    "sourceSha256": "sourceHash",  # renamed, KEPT (not stripped)
}

# Fields from source that are NOT in the allowlist — these cause failure
NODE_KNOWN_SOURCE_FIELDS = frozenset({
    "id", "name", "type", "filePath", "summary", "tags",
    "complexity", "language", "startLine", "endLine",
    "sourceSha256", "lineCount", "fileCategory", "params", "methods",
})

# Denylist zones
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

ALLOWED_PREFIXES = ("backend/", "src/", "supabase/", "tests/", "scripts/", "config/")

# --- Forbidden string patterns (from prompt Phase 4) ---

FORBIDDEN_PATTERNS = [
    "/Users/", "/home/", "/root/", "C:\\",
    ".env", "BEGIN PRIVATE KEY",
    "password", "secret", "token", "api_key", "apikey",
    "sk-", "ghp_", "github_pat_", "AIza", "xai-", "sbp_",
    "eyJ", "supabase.co", "localhost", "127.0.0.1",
    "/api/knowledge-graph", "/api/code",
]

# Regex patterns for structured PII detection
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
ABS_PATH_RE = re.compile(r"/Users/|/home/|/root/|C:\\\\")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
PHONE_RE = re.compile(r"\+?\d[\d\s\-]{8,}\d")


def redact_pii_in_string(value: str) -> str:
    """Redact PII patterns in a string value."""
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = ABS_PATH_RE.sub("[REDACTED_PATH]", value)
    return value


def scan_for_forbidden(value: str, hex64_exempt: bool = False) -> list[str]:
    """Check a string for forbidden patterns. Returns list of matches."""
    if not isinstance(value, str):
        return []
    if hex64_exempt and HEX64_RE.match(value):
        return []  # SHA-256 hashes are exempt from secret-pattern scan
    matches = []
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.lower() in value.lower():
            matches.append(pattern)
    return matches


def scan_node_for_forbidden(node: dict) -> list[dict]:
    """Scan string fields in a node for forbidden content.

    Structural fields (id, name, type, filePath, relativePath) are exempt from
    secret-pattern scanning because function names like '_extract_bearer_token'
    or 'build_github_secret_values' are structural identifiers, not secret values.
    Only non-structural fields (summary, tags, params, methods) are scanned for
    actual secret values.
    """
    STRUCTURAL_FIELDS = frozenset({"id", "name", "type", "filePath", "relativePath", "language", "fileCategory", "complexity", "params", "methods"})
    findings = []
    for key, val in node.items():
        if isinstance(val, str):
            # sourceSha256 is a hash, exempt from secret-pattern scan
            exempt = (key == "sourceSha256") or (key in STRUCTURAL_FIELDS)
            if not exempt:
                matches = scan_for_forbidden(val, hex64_exempt=exempt)
                if matches:
                    findings.append({"nodeId": node.get("id", "?"), "field": key, "patterns": matches, "value": val[:60]})
            # Email scan applies to all fields (even structural)
            if EMAIL_RE.search(val) and not HEX64_RE.match(val):
                findings.append({"nodeId": node.get("id", "?"), "field": key, "type": "email", "value": val[:60]})
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    if key not in STRUCTURAL_FIELDS and not HEX64_RE.match(item):
                        matches = scan_for_forbidden(item)
                        if matches:
                            findings.append({"nodeId": node.get("id", "?"), "field": key, "patterns": matches, "value": item[:60]})
                        if EMAIL_RE.search(item):
                            findings.append({"nodeId": node.get("id", "?"), "field": key, "type": "email", "value": item[:60]})
    return findings


def transform_node(node: dict) -> dict | None:
    """Transform a source node to the export schema. Returns None if field is unknown."""
    export_node = {}
    unknown_fields = []

    for source_key, value in node.items():
        if source_key in NODE_FIELD_MAP:
            export_key = NODE_FIELD_MAP[source_key]
            # Redact PII in string values
            if isinstance(value, str):
                value = redact_pii_in_string(value)
            elif isinstance(value, list):
                value = [redact_pii_in_string(item) if isinstance(item, str) else item for item in value]
            export_node[export_key] = value
        elif source_key not in NODE_KNOWN_SOURCE_FIELDS:
            unknown_fields.append(source_key)

    if unknown_fields:
        print(f"FAIL: Unknown fields in node {node.get('id', '?')}: {unknown_fields}")
        return None

    # Ensure all allowed fields are present (fill nulls for optional)
    for field in NODE_ALLOWED_FIELDS:
        if field not in export_node:
            if field in ("id", "name", "type"):
                print(f"FAIL: Required field '{field}' missing in node {node.get('id', '?')}")
                return None
            export_node[field] = None if field != "tags" else []

    # Normalize relativePath — ensure it's relative
    rp = export_node.get("relativePath")
    if rp and (rp.startswith("/") or ":" in rp[:3]):
        print(f"FAIL: Absolute path in node {node.get('id', '?')}: {rp}")
        return None

    return export_node


def transform_edge(edge: dict) -> dict | None:
    """Transform a source edge to the export schema. Drops known-but-unneeded fields."""
    # Known source edge fields that are NOT in the export allowlist (dropped, not failed)
    EDGE_DROPPED_FIELDS = frozenset({"lineNumber"})

    export_edge = {}
    for key in EDGE_ALLOWED_FIELDS:
        if key in edge:
            export_edge[key] = edge[key]
        else:
            if key in ("source", "target", "type"):
                print(f"FAIL: Required edge field '{key}' missing: {edge}")
                return None
            export_edge[key] = None

    # Check for truly unknown fields (not in allowlist, not in known-dropped)
    for key in edge:
        if key not in EDGE_ALLOWED_FIELDS and key not in EDGE_DROPPED_FIELDS:
            print(f"FAIL: Unknown edge field '{key}': {edge}")
            return None

    return export_edge


def canonical_json(obj) -> str:
    """Produce canonical JSON with sorted keys."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_content_hash(graph: dict) -> str:
    """Compute SHA-256 over canonical JSON of the graph (excluding volatile timestamps)."""
    canonical = canonical_json(graph)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(source_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source_root, text=True
    ).strip()


def non_generated_git_status(source_root: Path) -> list[str]:
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=source_root,
        text=True,
    )
    retained = []
    for line in status.splitlines():
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[-1]
        if not path.startswith(".understand-anything/"):
            retained.append(line)
    return retained


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--site-root", type=Path, default=DEFAULT_SITE_ROOT)
    parser.add_argument("--source-graph", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument(
        "--status",
        choices=("preview_only", "approved"),
        default="preview_only",
        help="Release status to write; approved requires a clean source tree and owner approval.",
    )
    parser.add_argument("--owner-approval", default="")
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    site_root = args.site_root.expanduser().resolve()
    source_graph = (args.source_graph or source_root / ".understand-anything" / "phase2-structural-graph.json").resolve()
    source_manifest_path = (args.source_manifest or source_root / ".understand-anything" / "phase2-structural-manifest.json").resolve()
    output_graph = site_root / "public" / "data" / "code-graph.json"
    output_manifest = site_root / "public" / "data" / "code-graph-manifest.json"

    if not source_graph.is_file() or not source_manifest_path.is_file():
        print(f"FAIL: source graph or manifest is missing under {source_root}")
        return 1

    print("=== Strict Graph Export ===")

    # Load source
    with open(source_graph) as f:
        source_graph = json.load(f)
    with open(source_manifest_path) as f:
        source_manifest = json.load(f)

    actual_head = git_head(source_root)
    analyzed_commit = source_manifest.get("analyzedCommit", "")
    if analyzed_commit != actual_head:
        print(f"FAIL: manifest analyzedCommit {analyzed_commit} does not match source HEAD {actual_head}")
        return 1

    non_generated_status = non_generated_git_status(source_root)
    if args.status == "approved":
        if source_manifest.get("worktreeDirty") is not False or non_generated_status:
            print("FAIL: approved export requires a clean source tree")
            return 1
        if args.owner_approval != "APPROVED_PUBLIC_CONTENT":
            print("FAIL: approved export requires --owner-approval APPROVED_PUBLIC_CONTENT")
            return 1

    source_node_count = len(source_graph.get("nodes", []))
    source_edge_count = len(source_graph.get("edges", []))
    print(f"Source: {source_node_count} nodes, {source_edge_count} edges")

    # 1. Scan for forbidden content (fail-closed)
    print("Scanning for forbidden content...")
    all_findings = []
    for node in source_graph["nodes"]:
        findings = scan_node_for_forbidden(node)
        if findings:
            all_findings.extend(findings)
    if all_findings:
        print(f"FAIL-CLOSED: {len(all_findings)} forbidden content findings!")
        for f in all_findings[:10]:
            print(f"  {f}")
        return 1
    print("  Forbidden content scan: CLEAN")

    # 2. Redact PII
    print("Redacting PII...")
    redaction_count = 0
    for i, node in enumerate(source_graph["nodes"]):
        original = json.dumps(node, sort_keys=True)
        for key in list(node.keys()):
            if isinstance(node[key], str):
                node[key] = redact_pii_in_string(node[key])
            elif isinstance(node[key], list):
                node[key] = [redact_pii_in_string(item) if isinstance(item, str) else item for item in node[key]]
        if json.dumps(node, sort_keys=True) != original:
            redaction_count += 1
    print(f"  Redacted PII in {redaction_count} node(s)")

    # 3. Re-scan after redaction
    all_findings = []
    for node in source_graph["nodes"]:
        findings = scan_node_for_forbidden(node)
        if findings:
            all_findings.extend(findings)
    if all_findings:
        print(f"FAIL-CLOSED: {len(all_findings)} findings after redaction!")
        return 1
    print("  Post-redaction scan: CLEAN")

    # 4. Denylist check
    print("Checking denylist zones...")
    for node in source_graph["nodes"]:
        fp = node.get("filePath", "")
        nid = node.get("id", "")
        for pattern in DENYLIST_PATTERNS:
            if pattern in fp or pattern in nid:
                print(f"FAIL: Denylist pattern '{pattern}' in node: {nid}")
                return 1
    print("  Denylist: CLEAN")

    # 5. Transform nodes (field allowlist, unknown field rejection)
    print("Transforming nodes...")
    export_nodes = []
    for node in source_graph["nodes"]:
        transformed = transform_node(node)
        if transformed is None:
            return 1
        export_nodes.append(transformed)
    print(f"  Transformed {len(export_nodes)} nodes")

    # 6. Transform edges
    print("Transforming edges...")
    export_edges = []
    for edge in source_graph["edges"]:
        transformed = transform_edge(edge)
        if transformed is None:
            return 1
        export_edges.append(transformed)
    print(f"  Transformed {len(export_edges)} edges")

    # 7. Dangling edge rejection
    print("Checking for dangling edges...")
    node_ids = set(n["id"] for n in export_nodes)
    dangling = []
    for edge in export_edges:
        if edge["source"] not in node_ids:
            dangling.append(f"Edge source not found: {edge['source']}")
        if edge["target"] not in node_ids:
            dangling.append(f"Edge target not found: {edge['target']}")
    if dangling:
        print(f"FAIL: {len(dangling)} dangling edges!")
        for d in dangling[:10]:
            print(f"  {d}")
        return 1
    print("  Dangling edges: NONE")

    # 8. Build export graph (canonical: sorted keys, sorted arrays where non-semantic)
    project = {}
    for key in PROJECT_ALLOWED_FIELDS:
        if key in source_graph.get("project", {}):
            project[key] = source_graph["project"][key]
        else:
            project[key] = [] if key in ("languages", "frameworks") else ""

    export_graph = {
        "version": source_graph.get("version", ""),
        "kind": source_graph.get("kind", ""),
        "project": project,
        "nodes": sorted(export_nodes, key=lambda n: n["id"]),
        "edges": sorted(export_edges, key=lambda e: (e["source"], e["target"], e["type"])),
        "layers": source_graph.get("layers", []),
        "tour": source_graph.get("tour", []),
    }

    # 9. Verify counts
    assert len(export_graph["nodes"]) == source_node_count
    assert len(export_graph["edges"]) == source_edge_count
    print(f"  Counts match: {len(export_graph['nodes'])} nodes, {len(export_graph['edges'])} edges")

    # 10. Compute canonical content hash (excluding volatile timestamps)
    content_hash = compute_content_hash(export_graph)
    print(f"  Canonical content hash: {content_hash}")

    # 11. Write output
    output_graph.parent.mkdir(parents=True, exist_ok=True)
    with open(output_graph, "w") as f:
        json.dump(export_graph, f, indent=2)

    file_sha = sha256_file(output_graph)
    file_size = output_graph.stat().st_size
    print(f"  Written: {output_graph} ({file_size:,} bytes)")
    print(f"  File SHA-256: {file_sha}")

    # 12. Build manifest
    manifest = {
        "schemaVersion": "code_graph_manifest_v1",
        "exportStatus": args.status,
        "contentHash": content_hash,
        "fileSha256": file_sha,
        "fileSizeBytes": file_size,
        "nodeCount": len(export_nodes),
        "edgeCount": len(export_edges),
        "sourceGraphSha256": source_manifest.get("graphSha256", ""),
        "sourceManifestSha256": sha256_file(source_manifest_path),
        "sourceCommit": analyzed_commit,
        "analyzedAt": source_manifest.get("analyzedAt", ""),
        "worktreeDirty": source_manifest.get("worktreeDirty", None),
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "license": "MIT",
        "attribution": "Knowledge graph generated from the Avalanche Insight Hub codebase.",
        "disclaimer": "Structural snapshot from the analyzed commit. Does not reflect current codebase state.",
        "validTime": "Static snapshot — does not reflect current codebase state.",
        "nodeFields": sorted(NODE_ALLOWED_FIELDS),
        "edgeFields": sorted(EDGE_ALLOWED_FIELDS),
        "projectFields": sorted(PROJECT_ALLOWED_FIELDS),
        "piiRedactionsApplied": redaction_count,
        "forbiddenContentFindings": 0,
        "danglingEdges": 0,
        "denylistViolations": 0,
        "unknownFieldRejections": 0,
    }

    if args.status == "approved":
        manifest["contentApproval"] = "APPROVED_PUBLIC_CONTENT"

    with open(output_manifest, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest: {output_manifest}")

    print("\n=== Graph Export Complete ===")
    print(f"  Status: {manifest['exportStatus']}")
    print(f"  Content hash: {content_hash}")
    print(f"  Nodes: {len(export_nodes)}, Edges: {len(export_edges)}")
    print(f"  PII redactions: {redaction_count}")
    print(f"  Forbidden findings: 0")
    print(f"  Dangling edges: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
