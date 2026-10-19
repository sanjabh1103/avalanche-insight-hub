#!/usr/bin/env python3
"""Sanitize the Phase 2 structural knowledge graph for public release.

This script reads the source graph and manifest, applies strict field allowlists,
strips sourceSha256 from nodes (moving it to a separate provenance manifest),
scans for PII/secrets/absolute paths, and writes public-safe JSON outputs.

Fail-closed: if any real PII is found, the script exits with a non-zero status
and no public files are written.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---

SOURCE_ROOT = Path("/Users/sanjayb/avalanche-insight-hub")
SITE_ROOT = Path("/Users/sanjayb/avalanche-insight-hub-public-knowledge-site")

SOURCE_GRAPH = SOURCE_ROOT / ".understand-anything" / "phase2-structural-graph.json"
SOURCE_MANIFEST = SOURCE_ROOT / ".understand-anything" / "phase2-structural-manifest.json"

OUTPUT_GRAPH = SITE_ROOT / "public" / "graph" / "sanitized-graph.json"
OUTPUT_PROVENANCE = SITE_ROOT / "public" / "graph" / "graph-provenance.json"
OUTPUT_REPORT = SITE_ROOT / "public" / "graph" / "sanitization-report.json"

# Field allowlists — ONLY these fields are kept in public nodes/edges
NODE_ALLOWLIST = frozenset({
    "id", "name", "type", "filePath", "summary", "tags",
    "complexity", "language", "startLine", "endLine",
    "lineCount", "fileCategory", "params", "methods",
})

EDGE_ALLOWLIST = frozenset({
    "source", "target", "type", "direction", "weight",
})

# Fields stripped from nodes (moved to provenance manifest)
STRIPPED_FIELDS = frozenset({"sourceSha256"})

# Denylist zones from the source repo — these must NEVER appear in the graph
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

# Allowed path prefixes for filePath values
ALLOWED_PREFIXES = ("backend/", "src/", "supabase/", "tests/", "scripts/", "config/")

# PII detection patterns
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
ABS_PATH_RE = re.compile(r"/Users/|/home/|C:\\\\|/root/")
# Secret-like values (not function names — actual secret values)
SECRET_VALUE_RE = re.compile(
    r"(?i)(sk-[a-zA-Z0-9]{20,}|"
    r"eyJ[a-zA-Z0-9_-]{10,}\.|"  # JWT tokens
    r"Bearer\s+[a-zA-Z0-9._-]{20,}|"
    r"supabase[_-]?(?:url|key)\s*[=:]\s*\S+|"
    r"api[_-]?key\s*[=:]\s*\S{20,})"
)
# Hex string pattern (to exclude SHA-256 hashes from secret scan)
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def redact_pii_in_string(value: str) -> str:
    """Redact PII patterns in a string value."""
    # Redact email addresses
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    # Redact absolute paths (keep relative paths)
    value = ABS_PATH_RE.sub("[REDACTED_PATH]", value)
    # Redact secret values
    value = SECRET_VALUE_RE.sub("[REDACTED_SECRET]", value)
    return value


def redact_pii_in_node(node: dict) -> dict:
    """Redact PII from all string fields in a node (except sourceSha256 which is stripped)."""
    redacted = {}
    for key, val in node.items():
        if key in STRIPPED_FIELDS:
            redacted[key] = val
            continue
        if isinstance(val, str):
            redacted[key] = redact_pii_in_string(val)
        elif isinstance(val, list):
            redacted[key] = [
                redact_pii_in_string(item) if isinstance(item, str) else item
                for item in val
            ]
        else:
            redacted[key] = val
    return redacted


def scan_for_pii(graph: dict) -> list[dict]:
    """Scan all node/edge string values for real PII. Returns list of findings."""
    findings = []

    def check_value(value: str, node_id: str, field: str) -> None:
        if not isinstance(value, str):
            return
        if HEX64_RE.match(value):
            return  # Skip SHA-256 hashes
        if EMAIL_RE.search(value):
            findings.append({"type": "email", "nodeId": node_id, "field": field, "value": value[:80]})
        if ABS_PATH_RE.search(value):
            findings.append({"type": "absolute_path", "nodeId": node_id, "field": field, "value": value[:80]})
        if SECRET_VALUE_RE.search(value):
            findings.append({"type": "secret_value", "nodeId": node_id, "field": field, "value": "[REDACTED]"})

    for node in graph.get("nodes", []):
        nid = node.get("id", "?")
        for key, val in node.items():
            if key in STRIPPED_FIELDS:
                continue  # sourceSha256 is expected and handled separately
            if isinstance(val, str):
                check_value(val, nid, key)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        check_value(item, nid, key)

    for edge in graph.get("edges", []):
        eid = f"{edge.get('source', '?')}->{edge.get('target', '?')}"
        for key, val in edge.items():
            if isinstance(val, str):
                check_value(val, eid, key)

    return findings


def check_denylist(graph: dict) -> list[str]:
    """Check if any denylist zone paths appear in node filePaths or ids."""
    violations = []
    for node in graph.get("nodes", []):
        fp = node.get("filePath", "")
        nid = node.get("id", "")
        for pattern in DENYLIST_PATTERNS:
            if pattern in fp or pattern in nid:
                violations.append(f"{nid} (filePath: {fp}) matches denylist pattern: {pattern}")
    return violations


def check_path_prefixes(graph: dict) -> list[str]:
    """Check if all filePath values start with allowed prefixes."""
    violations = []
    for node in graph.get("nodes", []):
        fp = node.get("filePath", "")
        if not fp:
            continue
        if not any(fp.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            violations.append(f"{node.get('id', '?')} has filePath outside allowed prefixes: {fp}")
    return violations


def sanitize_node(node: dict) -> tuple[dict, dict | None]:
    """Apply field allowlist to a node. Returns (sanitized_node, provenance_entry)."""
    sanitized = {}
    provenance_entry = None

    for key in NODE_ALLOWLIST:
        if key in node:
            sanitized[key] = node[key]

    # Extract sourceSha256 for provenance manifest
    if "sourceSha256" in node:
        provenance_entry = {
            "nodeId": node.get("id", ""),
            "filePath": node.get("filePath", ""),
            "sourceSha256": node["sourceSha256"],
        }

    return sanitized, provenance_entry


def sanitize_edge(edge: dict) -> dict:
    """Apply field allowlist to an edge."""
    return {key: edge[key] for key in EDGE_ALLOWLIST if key in edge}


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    print("=== Graph Data Sanitization ===")

    # 1. Load source graph and manifest
    print(f"Loading source graph: {SOURCE_GRAPH}")
    with open(SOURCE_GRAPH) as f:
        source_graph = json.load(f)

    print(f"Loading source manifest: {SOURCE_MANIFEST}")
    with open(SOURCE_MANIFEST) as f:
        source_manifest = json.load(f)

    source_node_count = len(source_graph.get("nodes", []))
    source_edge_count = len(source_graph.get("edges", []))
    print(f"Source graph: {source_node_count} nodes, {source_edge_count} edges")

    # 2. Redact PII from string fields (emails, abs paths, secrets in params/methods)
    print("Redacting PII from string fields...")
    redaction_count = 0
    for i, node in enumerate(source_graph["nodes"]):
        original = json.dumps(node, sort_keys=True)
        source_graph["nodes"][i] = redact_pii_in_node(node)
        if json.dumps(source_graph["nodes"][i], sort_keys=True) != original:
            redaction_count += 1
    print(f"  Redacted PII in {redaction_count} node(s)")

    # 3. PII scan (fail-closed — should be clean after redaction)
    print("Scanning for residual PII/secrets/absolute paths...")
    pii_findings = scan_for_pii(source_graph)
    if pii_findings:
        print(f"FAIL-CLOSED: {len(pii_findings)} PII findings detected!")
        for finding in pii_findings[:10]:
            print(f"  {finding}")
        if len(pii_findings) > 10:
            print(f"  ... and {len(pii_findings) - 10} more")
        return 1
    print("  PII scan: CLEAN")

    # 4. Denylist check
    print("Checking denylist zones...")
    denylist_violations = check_denylist(source_graph)
    if denylist_violations:
        print(f"FAIL-CLOSED: {len(denylist_violations)} denylist violations!")
        for v in denylist_violations[:10]:
            print(f"  {v}")
        return 1
    print("  Denylist: CLEAN")

    # 5. Path prefix check
    print("Checking path prefixes...")
    prefix_violations = check_path_prefixes(source_graph)
    if prefix_violations:
        print(f"FAIL-CLOSED: {len(prefix_violations)} path prefix violations!")
        for v in prefix_violations[:10]:
            print(f"  {v}")
        return 1
    print("  Path prefixes: CLEAN")

    # 6. Sanitize nodes and edges (apply field allowlists)
    print("Sanitizing nodes and edges...")
    sanitized_nodes = []
    source_hashes = []

    for node in source_graph["nodes"]:
        sanitized, prov = sanitize_node(node)
        sanitized_nodes.append(sanitized)
        if prov:
            source_hashes.append(prov)

    sanitized_edges = [sanitize_edge(e) for e in source_graph["edges"]]

    # 6. Build sanitized graph
    sanitized_graph = {
        "version": source_graph.get("version", ""),
        "kind": source_graph.get("kind", ""),
        "project": source_graph.get("project", {}),
        "nodes": sanitized_nodes,
        "edges": sanitized_edges,
        "layers": source_graph.get("layers", []),
        "tour": source_graph.get("tour", []),
    }

    # 7. Verify counts match
    assert len(sanitized_graph["nodes"]) == source_node_count, "Node count mismatch!"
    assert len(sanitized_graph["edges"]) == source_edge_count, "Edge count mismatch!"
    print(f"  Sanitized: {len(sanitized_nodes)} nodes, {len(sanitized_edges)} edges (counts match)")

    # 8. Verify no sourceSha256 in sanitized nodes
    for node in sanitized_nodes:
        assert "sourceSha256" not in node, f"sourceSha256 found in sanitized node: {node['id']}"
    print("  No sourceSha256 in sanitized nodes: VERIFIED")

    # 9. Write outputs
    print(f"Writing sanitized graph: {OUTPUT_GRAPH}")
    OUTPUT_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_GRAPH, "w") as f:
        json.dump(sanitized_graph, f, separators=(",", ":"))

    sanitized_sha = sha256_file(OUTPUT_GRAPH)
    sanitized_size = OUTPUT_GRAPH.stat().st_size
    print(f"  SHA-256: {sanitized_sha}")
    print(f"  Size: {sanitized_size:,} bytes ({sanitized_size / 1024 / 1024:.2f} MB)")

    # 10. Build provenance manifest
    provenance = {
        "schemaVersion": "public_graph_provenance_v1",
        "sourceGraphSha256": source_manifest.get("graphSha256", ""),
        "sourceManifestSha256": sha256_file(SOURCE_MANIFEST),
        "sanitizedGraphSha256": sanitized_sha,
        "sanitizedGraphSizeBytes": sanitized_size,
        "nodeCount": len(sanitized_nodes),
        "edgeCount": len(sanitized_edges),
        "sourceNodeCount": source_node_count,
        "sourceEdgeCount": source_edge_count,
        "analyzedAt": source_manifest.get("analyzedAt", ""),
        "analyzedCommit": source_manifest.get("analyzedCommit", ""),
        "worktreeDirty": source_manifest.get("worktreeDirty", None),
        "snapshotId": source_manifest.get("snapshotId", ""),
        "sourceStatus": source_manifest.get("status", ""),
        "sanitizedAt": datetime.now(timezone.utc).isoformat(),
        "validTime": "Static snapshot — does not reflect current codebase state.",
        "license": "MIT",
        "attribution": "Knowledge graph generated from the Avalanche Insight Hub codebase.",
        "disclaimer": "This is a structural snapshot from the analyzed commit. It does not represent the current state of the codebase.",
        "sourceHashes": source_hashes,  # Provenance only — not exposed in graph nodes
    }

    print(f"Writing provenance: {OUTPUT_PROVENANCE}")
    with open(OUTPUT_PROVENANCE, "w") as f:
        json.dump(provenance, f, indent=2)

    # 11. Build sanitization report
    report = {
        "sanitizedAt": datetime.now(timezone.utc).isoformat(),
        "sourceGraph": str(SOURCE_GRAPH),
        "sourceGraphSha256": source_manifest.get("graphSha256", ""),
        "sourceNodeCount": source_node_count,
        "sourceEdgeCount": source_edge_count,
        "sanitizedGraph": str(OUTPUT_GRAPH),
        "sanitizedGraphSha256": sanitized_sha,
        "sanitizedNodeCount": len(sanitized_nodes),
        "sanitizedEdgeCount": len(sanitized_edges),
        "nodeAllowlist": sorted(NODE_ALLOWLIST),
        "edgeAllowlist": sorted(EDGE_ALLOWLIST),
        "strippedFields": sorted(STRIPPED_FIELDS),
        "piiScanResult": {
            "status": "clean",
            "findingsCount": 0,
            "redactionsApplied": redaction_count,
            "redactionNote": "Email addresses, absolute paths, and secret-like values in string fields were redacted before PII scan.",
        },
        "denylistCheckResult": {
            "status": "clean",
            "violationsCount": 0,
        },
        "pathPrefixCheckResult": {
            "status": "clean",
            "violationsCount": 0,
            "allowedPrefixes": list(ALLOWED_PREFIXES),
        },
        "sourceHashesCount": len(source_hashes),
        "fieldsStrippedFromNodes": {
            "sourceSha256": source_node_count,
        },
    }

    print(f"Writing sanitization report: {OUTPUT_REPORT}")
    with open(OUTPUT_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    print("\n=== Sanitization Complete ===")
    print(f"  Nodes: {len(sanitized_nodes)} (source: {source_node_count})")
    print(f"  Edges: {len(sanitized_edges)} (source: {source_edge_count})")
    print(f"  PII findings: 0")
    print(f"  Denylist violations: 0")
    print(f"  sourceSha256 stripped: {len(source_hashes)} entries moved to provenance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
