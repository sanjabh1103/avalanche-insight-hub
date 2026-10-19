#!/usr/bin/env python3
"""Measure build and data performance metrics.

Records:
- Build time
- Bundle sizes
- Graph JSON fetch/parse time (estimated from file size)
- Initial page load size
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

SITE_ROOT = Path("/Users/sanjayb/avalanche-insight-hub-public-knowledge-site")
DIST_DIR = SITE_ROOT / "dist"
HANDOFF_DIR = SITE_ROOT / "handoff"


def measure_build_time() -> dict:
    """Measure npm run build time."""
    import subprocess
    start = time.time()
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(SITE_ROOT),
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - start
    return {
        "buildTimeSeconds": round(elapsed, 2),
        "buildExitCode": result.returncode,
    }


def measure_bundle_sizes() -> dict:
    """Measure bundle sizes from dist/."""
    assets = {}
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        for path in assets_dir.glob("*"):
            if path.is_file():
                assets[path.name] = {
                    "sizeBytes": path.stat().st_size,
                    "sizeKB": round(path.stat().st_size / 1024, 2),
                }
    return assets


def measure_data_sizes() -> dict:
    """Measure data file sizes."""
    data = {}
    data_dir = DIST_DIR / "data"
    if data_dir.exists():
        for path in data_dir.glob("*"):
            if path.is_file():
                data[path.name] = {
                    "sizeBytes": path.stat().st_size,
                    "sizeMB": round(path.stat().st_size / (1024 * 1024), 2),
                }
    return data


def measure_total_page_load() -> dict:
    """Estimate total initial page load size."""
    total = 0
    # HTML
    html_path = DIST_DIR / "index.html"
    if html_path.exists():
        total += html_path.stat().st_size
    # CSS
    for path in (DIST_DIR / "assets").glob("*.css"):
        total += path.stat().st_size
    # JS (entry point + react core + router)
    for path in (DIST_DIR / "assets").glob("*.js"):
        total += path.stat().st_size
    return {
        "totalInitialLoadBytes": total,
        "totalInitialLoadKB": round(total / 1024, 2),
        "totalInitialLoadMB": round(total / (1024 * 1024), 2),
    }


def main():
    print("=== Performance Measurements ===")

    # Build time
    print("Measuring build time...")
    build_metrics = measure_build_time()
    print(f"  Build time: {build_metrics['buildTimeSeconds']}s (exit: {build_metrics['buildExitCode']})")

    # Bundle sizes
    print("Measuring bundle sizes...")
    bundles = measure_bundle_sizes()
    for name, info in bundles.items():
        print(f"  {name}: {info['sizeKB']} KB")

    # Data sizes
    print("Measuring data sizes...")
    data = measure_data_sizes()
    for name, info in data.items():
        print(f"  {name}: {info['sizeMB']} MB")

    # Total page load
    print("Measuring total initial page load...")
    page_load = measure_total_page_load()
    print(f"  Total initial load: {page_load['totalInitialLoadKB']} KB ({page_load['totalInitialLoadMB']} MB)")

    # Graph fetch/parse estimate (based on file size, not actual fetch)
    graph_path = DIST_DIR / "data" / "code-graph.json"
    graph_parse_estimate = None
    if graph_path.exists():
        size_mb = graph_path.stat().st_size / (1024 * 1024)
        # Rough estimate: JSON.parse speed is ~50-100 MB/s on modern hardware
        graph_parse_estimate = round(size_mb / 75, 3)  # seconds
        print(f"  Graph JSON parse estimate: {graph_parse_estimate}s ({size_mb:.2f} MB)")

    report = {
        "measuredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browserDeviceProfile": "Not measured — requires browser runtime",
        "buildTime": build_metrics,
        "bundleSizes": bundles,
        "dataSizes": data,
        "totalInitialLoad": page_load,
        "graphJsonParseEstimateSeconds": graph_parse_estimate,
        "notes": [
            "Graph view defaults to 'architecture' perspective (bounded) — not all 4,926 nodes",
            "Table view paginates at 50 nodes per page",
            "Canvas renderer caps at 2,000 visible nodes for O(n²) force simulation",
            "Search is client-side, debounced at 300ms",
            "No external network requests at runtime — static JSON is fetched from the same origin",
            "Interactive browser verification is a separate release gate recorded in handoff/GLM_HANDOFF.md",
        ],
    }

    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    build_evidence_path = HANDOFF_DIR / "BUILD_EVIDENCE.md"
    existing_browser_section = ""
    if build_evidence_path.exists():
        existing_evidence = build_evidence_path.read_text()
        browser_marker = "## Browser Verification"
        if browser_marker in existing_evidence:
            existing_browser_section = "\n" + existing_evidence[existing_evidence.index(browser_marker):].rstrip() + "\n"

    with open(build_evidence_path, "w") as f:
        f.write("# Build Evidence\n\n")
        f.write(f"**Measured at:** {report['measuredAt']}\n\n")
        f.write(f"## Build Time\n\n- {build_metrics['buildTimeSeconds']}s (exit code: {build_metrics['buildExitCode']})\n\n")
        f.write("## Bundle Sizes\n\n")
        f.write("| File | Size (KB) |\n|---|---|\n")
        for name, info in sorted(bundles.items()):
            f.write(f"| {name} | {info['sizeKB']} |\n")
        f.write("\n## Data Sizes\n\n")
        f.write("| File | Size (MB) |\n|---|---|\n")
        for name, info in sorted(data.items()):
            f.write(f"| {name} | {info['sizeMB']} |\n")
        f.write(f"\n## Total Initial Page Load\n\n- {page_load['totalInitialLoadKB']} KB ({page_load['totalInitialLoadMB']} MB)\n\n")
        if graph_parse_estimate:
            f.write(f"## Graph JSON Parse Estimate\n\n- ~{graph_parse_estimate}s (estimated from file size)\n\n")
        f.write("## Notes\n\n")
        for note in report["notes"]:
            f.write(f"- {note}\n")
        if existing_browser_section:
            f.write(existing_browser_section)
        else:
            f.write("\n## Browser Verification\n\n")
            f.write("- Interactive browser verification is a separate release gate; see handoff/GLM_HANDOFF.md\n")
            f.write("- Static build output checks do not prove browser interaction\n")

    # Also save JSON
    with open(HANDOFF_DIR / "performance-metrics.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport written to {HANDOFF_DIR / 'BUILD_EVIDENCE.md'}")


if __name__ == "__main__":
    main()
