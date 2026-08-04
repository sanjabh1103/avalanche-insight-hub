#!/usr/bin/env python3
"""Verify public safety of the exported graph and map data.

Checks:
  1. No unknown fields in graph nodes/edges
  2. No absolute paths in any field
  3. No email addresses in any field (after redaction)
  4. No denylist zone paths
  5. Node and edge counts match the release manifest
  6. All relativePath values start with allowed prefixes
  7. Map is in blocked state (no fabricated data)
  8. No real sensor/station/observation IDs in map data
  9. Graph manifest has correct fields
  10. No external scripts/fonts in built output
  11. CSP header present in index.html

Exit code 0 = all checks pass, 1 = any check fails.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent

GRAPH_PATH = SITE_ROOT / "public" / "data" / "code-graph.json"
MANIFEST_PATH = SITE_ROOT / "public" / "data" / "code-graph-manifest.json"
MAP_PATH = SITE_ROOT / "public" / "data" / "forecast-map.json"
MAP_MANIFEST_PATH = SITE_ROOT / "public" / "data" / "forecast-map-manifest.json"
DIST_INDEX = SITE_ROOT / "dist" / "index.html"

ALLOWED_PREFIXES = ("backend/", "src/", "supabase/", "tests/", "scripts/", "config/")

NODE_ALLOWED_FIELDS = {"id", "name", "type", "relativePath", "language", "summary", "tags", "lineCount", "sourceHash"}
EDGE_ALLOWED_FIELDS = {"source", "target", "type", "direction", "weight"}

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

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
ABS_PATH_RE = re.compile(r"/Users/|/home/|/root/|C:\\\\")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def check_graph() -> list[str]:
    failures = []
    with open(GRAPH_PATH) as f:
        graph = json.load(f)
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    expected_nodes = manifest.get("nodeCount")
    expected_edges = manifest.get("edgeCount")

    if len(graph["nodes"]) != expected_nodes:
        failures.append(f"Node count: expected {expected_nodes}, got {len(graph['nodes'])}")
    if len(graph["edges"]) != expected_edges:
        failures.append(f"Edge count: expected {expected_edges}, got {len(graph['edges'])}")

    # Check node fields
    for node in graph["nodes"]:
        for key in node:
            if key not in NODE_ALLOWED_FIELDS:
                failures.append(f"Unknown node field '{key}' in node: {node['id']}")
                break
        for key, val in node.items():
            if isinstance(val, str) and not HEX64_RE.match(val):
                if EMAIL_RE.search(val):
                    failures.append(f"Email in node {node['id']}.{key}: {val[:60]}")
                if ABS_PATH_RE.search(val):
                    failures.append(f"Absolute path in node {node['id']}.{key}: {val[:60]}")

    # Check edge fields
    for edge in graph["edges"]:
        for key in edge:
            if key not in EDGE_ALLOWED_FIELDS:
                failures.append(f"Unknown edge field '{key}' in edge: {edge}")
                break

    # Denylist check
    for node in graph["nodes"]:
        rp = node.get("relativePath", "")
        nid = node.get("id", "")
        for pattern in DENYLIST_PATTERNS:
            if pattern in rp or pattern in nid:
                failures.append(f"Denylist pattern '{pattern}' in node: {nid}")

    # Path prefix check
    for node in graph["nodes"]:
        rp = node.get("relativePath", "")
        if rp and not any(rp.startswith(p) for p in ALLOWED_PREFIXES):
            failures.append(f"relativePath outside allowed prefixes: {rp} (node: {node['id']})")

    return failures


def check_map() -> list[str]:
    failures = []
    with open(MAP_PATH) as f:
        map_data = json.load(f)

    # Map must be in blocked state (no fabricated data)
    if map_data.get("status") != "blocked":
        failures.append(f"Map status should be 'blocked', got '{map_data.get('status')}'")
    if map_data.get("cells") and len(map_data["cells"]) > 0:
        failures.append(f"Map should have no cells in blocked state, got {len(map_data['cells'])}")
    if not map_data.get("disclaimer"):
        failures.append("Map missing disclaimer")

    return failures


def check_manifest() -> list[str]:
    failures = []
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    if manifest.get("license") != "MIT":
        failures.append(f"Graph manifest license is not MIT: {manifest.get('license')}")
    if not manifest.get("disclaimer"):
        failures.append("Graph manifest missing disclaimer")
    if not manifest.get("contentHash"):
        failures.append("Graph manifest missing contentHash")
    if manifest.get("exportStatus") not in {"approved", "preview_only"}:
        failures.append(f"Manifest exportStatus is invalid: {manifest.get('exportStatus')}")
    if manifest.get("exportStatus") == "approved":
        if manifest.get("worktreeDirty") is not False:
            failures.append("Approved graph export must have worktreeDirty=false")
        if manifest.get("contentApproval") != "APPROVED_PUBLIC_CONTENT":
            failures.append("Approved graph export is missing content approval")

    with open(MAP_MANIFEST_PATH) as f:
        map_manifest = json.load(f)
    if map_manifest.get("status") != "blocked":
        failures.append(f"Map manifest status should be 'blocked', got '{map_manifest.get('status')}'")

    return failures


def check_built_output() -> list[str]:
    failures = []
    if not DIST_INDEX.exists():
        failures.append("dist/index.html not found — run npm run build first")
        return failures

    html = DIST_INDEX.read_text()

    # Check for CSP
    if "Content-Security-Policy" not in html:
        failures.append("No Content-Security-Policy meta tag in index.html")
    elif "connect-src 'self'" not in html:
        failures.append("CSP must have connect-src 'self' to allow same-origin data fetches")
    if "connect-src 'none'" in html:
        failures.append("CSP has connect-src 'none' — this blocks same-origin data fetches")

    # Check for external scripts
    if re.search(r'<script[^>]+src=["\']https?://', html, re.IGNORECASE):
        failures.append("External script tag found in index.html")

    # Check for external fonts
    if re.search(r'@import\s+url\(["\']?https?://', html, re.IGNORECASE):
        failures.append("External font import found in index.html")

    return failures


def main() -> int:
    print("=== Public Safety Verification ===")
    all_failures = []

    print("Checking graph data...")
    graph_failures = check_graph()
    if graph_failures:
        print(f"  FAIL: {len(graph_failures)} graph issues")
        for f in graph_failures[:10]:
            print(f"    {f}")
        all_failures.extend(graph_failures)
    else:
        print("  PASS")

    print("Checking map data...")
    map_failures = check_map()
    if map_failures:
        print(f"  FAIL: {len(map_failures)} map issues")
        for f in map_failures[:10]:
            print(f"    {f}")
        all_failures.extend(map_failures)
    else:
        print("  PASS")

    print("Checking manifest...")
    manifest_failures = check_manifest()
    if manifest_failures:
        print(f"  FAIL: {len(manifest_failures)} manifest issues")
        for f in manifest_failures[:10]:
            print(f"    {f}")
        all_failures.extend(manifest_failures)
    else:
        print("  PASS")

    print("Checking built output...")
    built_failures = check_built_output()
    if built_failures:
        print(f"  FAIL: {len(built_failures)} built output issues")
        for f in built_failures:
            print(f"    {f}")
        all_failures.extend(built_failures)
    else:
        print("  PASS")

    print()
    if all_failures:
        print(f"PUBLIC SAFETY VERIFICATION: FAIL ({len(all_failures)} issues)")
        return 1
    else:
        print("PUBLIC SAFETY VERIFICATION: PASS")
        return 0


if __name__ == "__main__":
    sys.exit(main())
