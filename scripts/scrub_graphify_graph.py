#!/usr/bin/env python3
"""Scrub customer/partner names from the Graphify knowledge graph and regenerate HTML visualizations.

This script mirrors the scrubbing logic of export_graph.py but for the Graphify graph
(graphify-out/graph.json). It:
1. Loads the original graphify graph
2. Scrubs all customer/partner names (Partner, Partner, Partner, a partner, shared_content)
3. Writes the scrubbed graph to graphify-out/graph-scrubbed.json
4. Regenerates all 3 HTML visualizations from the scrubbed graph
5. Verifies no customer names remain in any output file
6. Generates integrity hashes for deployed files

Usage:
    python3 scripts/scrub_graphify_graph.py
    python3 scripts/scrub_graphify_graph.py --source-root /path/to/repo
    python3 scripts/scrub_graphify_graph.py --check-only  # verify only, no scrub
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --- Scrub patterns (must match export_graph.py + sync_to_public.sh) ---
# KS uses "Agency" for customer names (advisor decision: "client" is awkward
# when the actual client views the KS)
SCRUB_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Partner", re.IGNORECASE), "Agency"),
    (re.compile(r"Partner", re.IGNORECASE), "Agency"),
    (re.compile(r"Partner", re.IGNORECASE), "Agency"),  # Partner is Partner's sub-org
    (re.compile(r"a partner", re.IGNORECASE), "a partner"),
    (re.compile(r"shared_content_export", re.IGNORECASE), "shared_content_export"),
    (re.compile(r"shared_content", re.IGNORECASE), "shared_content"),
]

# Patterns to verify (must be 0 after scrubbing)
VERIFY_PATTERNS: list[str] = [
    "Partner", "Partner", "Partner", "Partner", "Partner", "Partner",
    "a partner", "a partner", "shared_content",
]

# Alias scanner — patterns that might indicate missed customer references
ALIAS_PATTERNS: list[str] = [
    "Defence Research",
    "Snow and Avalanche",
    " Defence ",
    " defence research",
    "Himalayan avalanche",  # geographic term, but worth flagging in context
]


def scrub_string(s: str) -> str:
    """Apply all scrub patterns to a string."""
    for pattern, replacement in SCRUB_PATTERNS:
        s = pattern.sub(replacement, s)
    return s


def scrub_obj(obj):
    """Recursively scrub all strings in a nested object."""
    if isinstance(obj, str):
        return scrub_string(obj)
    elif isinstance(obj, list):
        return [scrub_obj(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    return obj


def verify_clean(text: str, label: str) -> bool:
    """Verify no customer names remain in text. Returns True if clean."""
    all_clean = True
    for pat in VERIFY_PATTERNS:
        count = text.count(pat)
        if count > 0:
            print(f"  FAIL: {label} contains '{pat}' x{count}")
            all_clean = False
    return all_clean


def scan_aliases(text: str, label: str) -> list[str]:
    """Scan for potential alias references that might indicate missed customer names."""
    found = []
    for alias in ALIAS_PATTERNS:
        count = text.lower().count(alias.lower())
        if count > 0:
            found.append(f"  WARN: {label} contains '{alias}' x{count} (review manually)")
    return found


def compute_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file for integrity verification."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrub Graphify graph and regenerate HTML")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ.get("SOURCE_ROOT", str(Path(__file__).resolve().parents[1]))),
        help="Path to the repo root (default: SOURCE_ROOT env or parent of scripts/)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify existing scrubbed files, do not regenerate",
    )
    parser.add_argument(
        "--viz-node-limit",
        type=int,
        default=int(os.environ.get("GRAPHIFY_VIZ_NODE_LIMIT", "25000")),
        help="Max nodes for HTML viz (default: 25000)",
    )
    args = parser.parse_args()

    graphify_out = args.source_root / "graphify-out"
    original_graph = graphify_out / "graph.json"
    scrubbed_graph = graphify_out / "graph-scrubbed.json"

    if not original_graph.exists():
        print(f"ERROR: {original_graph} not found. Run 'graphify .' first.")
        return 1

    # --- Step 1: Check-only mode ---
    if args.check_only:
        print("=== CHECK-ONLY MODE ===")
        if not scrubbed_graph.exists():
            print(f"  FAIL: {scrubbed_graph} not found. Run scrub first.")
            return 1
        with open(scrubbed_graph) as f:
            text = f.read()
        clean = verify_clean(text, "graph-scrubbed.json")
        aliases = scan_aliases(text, "graph-scrubbed.json")
        for a in aliases:
            print(a)
        # Check HTML files
        for html_file in ["graph.html", "GRAPH_TREE-scrubbed.html", "avalanche-callflow-scrubbed.html"]:
            p = graphify_out / html_file
            if p.exists():
                with open(p) as f:
                    html_text = f.read()
                html_clean = verify_clean(html_text, html_file)
                clean = clean and html_clean
                html_aliases = scan_aliases(html_text, html_file)
                for a in html_aliases:
                    print(a)
        print(f"\nOverall: {'PASS' if clean else 'FAIL'}")
        return 0 if clean else 1

    # --- Step 2: Load and scrub graph ---
    print("=== STEP 1: Scrub Graphify Graph ===")
    print(f"  Loading: {original_graph}")
    with open(original_graph) as f:
        g = json.load(f)

    node_count = len(g.get("nodes", []))
    link_count = len(g.get("links", g.get("edges", [])))
    print(f"  Original: {node_count} nodes, {link_count} links")

    # Verify original has customer names (sanity check)
    original_text = json.dumps(g)
    original_Partner = original_text.count("Partner") + original_text.count("Partner")
    if original_Partner == 0:
        print("  WARN: Original graph has 0 Partner occurrences — may already be scrubbed")

    # Scrub
    print("  Scrubbing customer/partner names...")
    g_scrubbed = scrub_obj(g)

    # Verify scrubbed
    scrubbed_text = json.dumps(g_scrubbed)
    if not verify_clean(scrubbed_text, "scrubbed graph"):
        print("  FAIL: Scrubbing incomplete — customer names remain")
        return 1
    print(f"  Agency occurrences: {scrubbed_text.count('Agency')}")

    # Scan for aliases
    aliases = scan_aliases(scrubbed_text, "scrubbed graph")
    for a in aliases:
        print(a)

    # Write scrubbed graph
    print(f"  Writing: {scrubbed_graph}")
    with open(scrubbed_graph, "w") as f:
        json.dump(g_scrubbed, f, separators=(",", ":"))
    print(f"  Size: {scrubbed_graph.stat().st_size:,} bytes")

    # --- Step 2b: Scrub community labels file ---
    labels_file = graphify_out / ".graphify_labels.json"
    if labels_file.exists():
        print(f"\n  Scrubbing community labels: {labels_file}")
        labels_backup = graphify_out / ".graphify_labels-original-backup.json"
        if not labels_backup.exists():
            subprocess.run(["cp", str(labels_file), str(labels_backup)], check=True)
        with open(labels_file) as f:
            labels = json.load(f)
        labels_scrubbed = scrub_obj(labels)
        with open(labels_file, "w") as f:
            json.dump(labels_scrubbed, f, indent=2)
        labels_text = json.dumps(labels_scrubbed)
        if not verify_clean(labels_text, ".graphify_labels.json"):
            print("  FAIL: Labels scrubbing incomplete")
            return 1
        print("  Labels scrubbed: PASS")

    # --- Step 3: Regenerate HTML visualizations ---
    print("\n=== STEP 2: Regenerate HTML Visualizations ===")

    # Swap in scrubbed graph temporarily
    backup = graphify_out / "graph-original-backup.json"
    print(f"  Backing up original to: {backup}")
    if not backup.exists():
        subprocess.run(["cp", str(original_graph), str(backup)], check=True)

    print("  Swapping in scrubbed graph...")
    subprocess.run(["cp", str(scrubbed_graph), str(original_graph)], check=True)

    try:
        # Regenerate graph.html via cluster-only (raises viz limit)
        print("  Regenerating graph.html (cluster-only)...")
        env = os.environ.copy()
        env["GRAPHIFY_VIZ_NODE_LIMIT"] = str(args.viz_node_limit)
        result = subprocess.run(
            ["graphify", "cluster-only", str(args.source_root)],
            capture_output=True, text=True, env=env, cwd=str(args.source_root)
        )
        if result.returncode != 0:
            print(f"  WARN: cluster-only returned {result.returncode}")
            print(f"  stderr: {result.stderr[:500]}")
        graph_html = graphify_out / "graph.html"
        if graph_html.exists():
            print(f"  graph.html: {graph_html.stat().st_size:,} bytes")
        else:
            print("  FAIL: graph.html not generated")
            return 1

        # Regenerate GRAPH_TREE.html
        print("  Regenerating GRAPH_TREE.html...")
        tree_html = graphify_out / "GRAPH_TREE-scrubbed.html"
        result = subprocess.run(
            ["graphify", "tree", "--output", str(tree_html)],
            capture_output=True, text=True, cwd=str(args.source_root)
        )
        if tree_html.exists():
            print(f"  GRAPH_TREE-scrubbed.html: {tree_html.stat().st_size:,} bytes")

        # Regenerate callflow HTML
        print("  Regenerating callflow HTML...")
        callflow_html = graphify_out / "avalanche-callflow-scrubbed.html"
        result = subprocess.run(
            ["graphify", "export", "callflow-html", "--output", str(callflow_html)],
            capture_output=True, text=True, cwd=str(args.source_root)
        )
        if callflow_html.exists():
            print(f"  avalanche-callflow-scrubbed.html: {callflow_html.stat().st_size:,} bytes")

    finally:
        # Always restore original graph and labels
        print("  Restoring original graph...")
        subprocess.run(["cp", str(backup), str(original_graph)], check=True)
        labels_backup = graphify_out / ".graphify_labels-original-backup.json"
        if labels_backup.exists():
            print("  Restoring original labels...")
            subprocess.run(["cp", str(labels_backup), str(labels_file)], check=True)

    # --- Step 4: Verify all HTML files are clean ---
    print("\n=== STEP 3: Verify All HTML Files ===")
    all_clean = True
    html_files = {
        "graph.html": graphify_out / "graph.html",
        "GRAPH_TREE-scrubbed.html": graphify_out / "GRAPH_TREE-scrubbed.html",
        "avalanche-callflow-scrubbed.html": graphify_out / "avalanche-callflow-scrubbed.html",
    }
    for name, path in html_files.items():
        if not path.exists():
            print(f"  SKIP: {name} not found")
            continue
        with open(path) as f:
            text = f.read()
        clean = verify_clean(text, name)
        all_clean = all_clean and clean
        # Scan aliases
        file_aliases = scan_aliases(text, name)
        for a in file_aliases:
            print(a)

    # --- Step 5: Generate integrity hashes ---
    print("\n=== STEP 4: Integrity Hashes ===")
    hashes = {}
    for name, path in html_files.items():
        if path.exists():
            h = compute_hash(path)
            hashes[name] = h
            print(f"  {name}: {h[:16]}...")

    # Write hashes to file
    hashes_file = graphify_out / ".scrubbed-hashes.json"
    with open(hashes_file, "w") as f:
        json.dump({
            "scrubbedAt": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(args.source_root)
            ).stdout.strip(),
            "originalCommit": subprocess.run(
                ["git", "log", "--format=%H", "-1", "--", "graphify-out/graph.json"],
                capture_output=True, text=True, cwd=str(args.source_root)
            ).stdout.strip(),
            "hashes": hashes,
        }, f, indent=2)
    print(f"  Written: {hashes_file}")

    # --- Final ---
    print(f"\n=== {'PASS' if all_clean else 'FAIL'} ===")
    if all_clean:
        print("All Graphify HTML files are clean of customer names.")
        print("\nTo deploy to KS:")
        print("  cp graphify-out/graph.html ~/avalanche-insight-hub-public-knowledge-site/dist/graphify/graph.html")
        print("  cp graphify-out/GRAPH_TREE-scrubbed.html ~/avalanche-insight-hub-public-knowledge-site/dist/graphify/tree.html")
        print("  cp graphify-out/avalanche-callflow-scrubbed.html ~/avalanche-insight-hub-public-knowledge-site/dist/graphify/callflow.html")
        print("  cd ~/avalanche-insight-hub-public-knowledge-site && vercel deploy dist/ --prod --yes")
    return 0 if all_clean else 1


if __name__ == "__main__":
    sys.exit(main())
