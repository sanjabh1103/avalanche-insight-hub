#!/usr/bin/env python3
"""Generate deterministic explanations for graph nodes and map cells.

All explanations are template-based and deterministic — no AI calls.
Outputs:
  - public/data/explanations.json (nodeId → explanation text)
  - public/data/area-explanations.json only when an approved map has cells
"""
from __future__ import annotations

import json
from pathlib import Path

SITE_ROOT = Path("/Users/sanjayb/avalanche-insight-hub-public-knowledge-site")
GRAPH_PATH = SITE_ROOT / "public" / "data" / "code-graph.json"
MAP_PATH = SITE_ROOT / "public" / "data" / "forecast-map.json"
OUTPUT_GRAPH_EXPL = SITE_ROOT / "public" / "data" / "explanations.json"
OUTPUT_MAP_EXPL = SITE_ROOT / "public" / "data" / "area-explanations.json"


def explain_file_node(node: dict, incoming: list, outgoing: list) -> str:
    """Generate explanation for a file node."""
    name = node.get("name", "unknown")
    file_path = node.get("relativePath", "unknown")
    language = node.get("language", "unknown")
    line_count = node.get("lineCount", 0)
    tags = node.get("tags", [])

    parts = []
    parts.append(f"This is the {language} file '{name}', located at {file_path}.")

    if line_count:
        parts.append(f"It contains {line_count} lines of code.")

    if tags:
        parts.append(f"It is tagged as: {', '.join(tags)}.")

    # Describe what it contains
    contains = [e for e in outgoing if e.get("type") == "contains"]
    if contains:
        contained_names = []
        for edge in contains[:5]:
            target = edge.get("target", "")
            # Extract name from ID like "function:path:funcName"
            parts_id = target.split(":")
            if len(parts_id) >= 2:
                contained_names.append(parts_id[-1])
        if contained_names:
            if len(contains) > 5:
                parts.append(f"It contains {len(contains)} components, including: {', '.join(contained_names)}, and {len(contains) - 5} more.")
            else:
                parts.append(f"It contains: {', '.join(contained_names)}.")

    # Describe what contains it
    contained_by = [e for e in incoming if e.get("type") == "contains"]
    if contained_by:
        parts.append(f"This file is part of the project structure and is referenced by {len(contained_by)} other components.")

    parts.append("In the avalanche forecasting system, this file contributes to the overall codebase structure that supports snow and avalanche risk analysis.")

    return " ".join(parts)


def explain_function_node(node: dict, incoming: list, outgoing: list) -> str:
    """Generate explanation for a function node."""
    name = node.get("name", "unknown")
    file_path = node.get("relativePath", "unknown")
    language = node.get("language", "unknown")
    params = node.get("params", [])
    tags = node.get("tags", [])

    parts = []
    parts.append(f"This is the {language} function '{name}', defined in {file_path}.")

    if params:
        parts.append(f"It accepts {len(params)} parameter(s): {', '.join(params)}.")

    if tags:
        parts.append(f"It is tagged as: {', '.join(tags)}.")

    # Describe connections
    called_by = [e for e in incoming if e.get("type") in ("calls", "called_by")]
    calls = [e for e in outgoing if e.get("type") in ("calls", "called_by")]
    if calls:
        call_names = []
        for edge in calls[:5]:
            target = edge.get("target", "")
            parts_id = target.split(":")
            if len(parts_id) >= 2:
                call_names.append(parts_id[-1])
        if call_names:
            if len(calls) > 5:
                parts.append(f"It calls {len(calls)} other functions, including: {', '.join(call_names)}, and {len(calls) - 5} more.")
            else:
                parts.append(f"It calls: {', '.join(call_names)}.")
    if called_by:
        parts.append(f"It is called by {len(called_by)} other function(s).")

    # Context based on file path
    if "backend/common/" in file_path:
        parts.append("This function is part of the shared backend utilities that support avalanche risk modeling and data processing.")
    elif "backend/scripts/" in file_path:
        parts.append("This function is part of the operational scripts that support deployment, data management, and system setup.")
    elif "backend/tests/" in file_path or file_path.startswith("tests/"):
        parts.append("This function is part of the test suite that verifies system correctness and reliability.")
    elif "src/" in file_path:
        parts.append("This function is part of the frontend application that provides the user interface for avalanche forecasting.")
    elif "supabase/" in file_path:
        parts.append("This function is part of the database layer that manages data storage and retrieval.")
    elif "scripts/" in file_path:
        parts.append("This function is part of the build and utility scripts that support the development workflow.")

    return " ".join(parts)


def explain_class_node(node: dict, incoming: list, outgoing: list) -> str:
    """Generate explanation for a class node."""
    name = node.get("name", "unknown")
    file_path = node.get("relativePath", "unknown")
    language = node.get("language", "unknown")
    methods = node.get("methods", [])
    tags = node.get("tags", [])

    parts = []
    parts.append(f"This is the {language} class '{name}', defined in {file_path}.")

    if methods:
        if len(methods) <= 5:
            parts.append(f"It has {len(methods)} method(s): {', '.join(methods)}.")
        else:
            parts.append(f"It has {len(methods)} methods, including: {', '.join(methods[:5])}, and {len(methods) - 5} more.")

    if tags:
        parts.append(f"It is tagged as: {', '.join(tags)}.")

    # Describe connections
    contained_by = [e for e in incoming if e.get("type") == "contains"]
    contains = [e for e in outgoing if e.get("type") == "contains"]
    if contains:
        parts.append(f"It contains {len(contains)} member(s).")
    if contained_by:
        parts.append(f"It is defined within a file in the project structure.")

    # Context based on file path
    if "backend/common/" in file_path:
        parts.append("This class is part of the shared backend utilities that support avalanche risk modeling and data processing.")
    elif "src/" in file_path:
        parts.append("This class is part of the frontend application that provides the user interface for avalanche forecasting.")
    elif "supabase/" in file_path:
        parts.append("This class is part of the database layer that manages data storage and retrieval.")

    return " ".join(parts)


def explain_node(node: dict, incoming: list, outgoing: list) -> str:
    """Generate explanation for any node type."""
    node_type = node.get("type", "unknown")
    if node_type == "file":
        return explain_file_node(node, incoming, outgoing)
    elif node_type == "function":
        return explain_function_node(node, incoming, outgoing)
    elif node_type == "class":
        return explain_class_node(node, incoming, outgoing)
    else:
        name = node.get("name", "unknown")
        return f"This is a {node_type} node named '{name}' in the codebase structure."


def explain_map_cell(cell: dict) -> str:
    """Generate explanation for a map grid cell."""
    risk_score = cell.get("riskScore", 1)
    risk_label = cell.get("riskLabel", "Unknown")
    problem_type = cell.get("problemType", "Unknown")
    elevation = cell.get("elevationMeters", 0)
    slope = cell.get("slopeAngleDeg", 0)
    aspect = cell.get("aspectDeg", 0)
    lat = cell.get("centerLat", 0)
    lng = cell.get("centerLng", 0)
    apt_eligible = cell.get("aptEligible", False)

    parts = []
    parts.append(f"This grid cell covers the area around {lat}°N, {lng}°E in the Nepal Himalaya region.")

    parts.append(f"The avalanche risk level is {risk_label} (score: {risk_score}/5).")

    risk_descriptions = {
        1: "Natural avalanches are unlikely. Generally safe conditions for backcountry travel, but standard precautions still apply.",
        2: "Human-triggered avalanches are possible in specific terrain features. Evaluate slopes carefully before committing.",
        3: "Human-triggered avalanches are likely in specific terrain. Dangerous conditions require expert-level decision-making.",
        4: "Both natural and human-triggered avalanches are likely. Very dangerous conditions — avoid avalanche terrain.",
        5: "Large natural avalanches are expected. Extraordinarily dangerous — stay away from all avalanche paths.",
    }
    parts.append(risk_descriptions.get(risk_score, "Risk conditions are uncertain."))

    parts.append(f"The primary avalanche problem type is '{problem_type}'.")

    parts.append(f"Elevation: approximately {elevation}m above sea level.")
    parts.append(f"Slope angle: {slope}°. Aspect: {aspect}°.")

    if apt_eligible:
        parts.append("This slope is within the 30°–50° angle range that is typically prone to avalanches (APT-eligible).")
    else:
        parts.append("This slope is outside the typical avalanche-prone angle range (30°–50°).")

    parts.append("Note: This is a static educational snapshot, not an operational forecast.")

    return " ".join(parts)


def main() -> int:
    print("=== Deterministic Explanations Generation ===")

    # Load graph
    print(f"Loading graph: {GRAPH_PATH}")
    with open(GRAPH_PATH) as f:
        graph = json.load(f)

    # Build edge index
    incoming_by_target = {}
    outgoing_by_source = {}
    for edge in graph["edges"]:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        outgoing_by_source.setdefault(src, []).append(edge)
        incoming_by_target.setdefault(tgt, []).append(edge)

    # Generate graph explanations
    print("Generating graph node explanations...")
    explanations = {}
    for node in graph["nodes"]:
        nid = node["id"]
        incoming = incoming_by_target.get(nid, [])
        outgoing = outgoing_by_source.get(nid, [])
        explanations[nid] = explain_node(node, incoming, outgoing)

    print(f"  Generated {len(explanations)} explanations")

    with open(OUTPUT_GRAPH_EXPL, "w") as f:
        json.dump(explanations, f, separators=(",", ":"))
    print(f"  Written: {OUTPUT_GRAPH_EXPL}")

    # Generate map explanations
    print(f"Loading map: {MAP_PATH}")
    with open(MAP_PATH) as f:
        map_data = json.load(f)

    if map_data.get("status") == "blocked":
        # Do not leave a misleading empty map artifact behind. The UI loads the
        # blocked map manifest directly and must not imply that map explanations
        # are available.
        if OUTPUT_MAP_EXPL.exists():
            OUTPUT_MAP_EXPL.unlink()
        print("  Map is blocked; no map explanation artifact generated")
        print("\n=== Deterministic Explanations Generation Complete ===")
        print(f"  Graph explanations: {len(explanations)}")
        print("  Map explanations: 0 (blocked)")
        return 0

    print("Generating map cell explanations...")
    map_explanations = {}
    for cell in map_data["cells"]:
        cid = cell["id"]
        map_explanations[cid] = explain_map_cell(cell)

    print(f"  Generated {len(map_explanations)} explanations")

    with open(OUTPUT_MAP_EXPL, "w") as f:
        json.dump(map_explanations, f, separators=(",", ":"))
    print(f"  Written: {OUTPUT_MAP_EXPL}")

    print("\n=== Explanations Generation Complete ===")
    print(f"  Graph explanations: {len(explanations)}")
    print(f"  Map explanations: {len(map_explanations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
