#!/usr/bin/env python3
"""Find true orphan nodes (zero inbound edges) in a graphify graph.

Filters out standard library nodes and known entry points.
Usage: python3 scripts/find_orphans.py graphify-out/graph.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


# Standard library / external nodes to exclude
STDLIB_NODES = {
    'os', 'sys', 'json', 'typing', 'pathlib', 'argparse', 'datetime',
    'collections', 'math', 're', 'tempfile', 'hashlib', 'unittest',
    'unittest_mock', 'warnings', 'traceback', 'time', 'io', 'copy',
    'functools', 'itertools', 'dataclasses', 'logging', 'csv', 'glob',
    'shutil', 'subprocess', 'threading', 'multiprocessing', 'asyncio',
    'contextlib', 'abc', 'enum', 'string', 'textwrap', 'gzip',
    'urllib_parse', 'Any', 'Optional', 'List', 'Dict', 'Tuple',
    'Union', 'Callable', 'Sequence', 'Mapping', 'Iterable',
    'Generator', 'Iterator', 'ContextManager', 'NamedTuple',
    'Protocol', 'TypeVar', 'Generic', 'ClassVar', 'Final',
    'NotRequired', 'Required', 'TypedDict', 'Literal',
    'numpy', 'np', 'pandas', 'pd', 'torch', 'sklearn',
    'requests', 'joblib', 'scipy',
}

# Legitimate entry points (no inbound callers by design)
ENTRY_POINT_PATTERNS = {
    'main()', 'handler()', 'serve()', 'app', 'create_app',
    'setUp()', 'tearDown()', 'setUpClass()', 'tearDownClass()',
}


def find_orphans(graph_path: str) -> None:
    with open(graph_path) as f:
        g = json.load(f)

    nodes = g.get('nodes', [])
    links = g.get('links', g.get('edges', []))

    # Build inbound edge count per node
    inbound: Counter = Counter()
    outbound: Counter = Counter()
    node_ids = set()
    node_info: dict = {}

    for n in nodes:
        nid = n.get('id', '')
        node_ids.add(nid)
        node_info[nid] = n

    for e in links:
        src = e.get('source', '')
        tgt = e.get('target', '')
        inbound[tgt] += 1
        outbound[src] += 1

    # Find orphans (zero inbound edges)
    orphans = []
    for nid in node_ids:
        if inbound[nid] == 0:
            name = node_info[nid].get('name', node_info[nid].get('id', ''))
            src = node_info[nid].get('src', '')
            loc = node_info[nid].get('loc', '')

            # Skip stdlib
            if name in STDLIB_NODES or nid in STDLIB_NODES:
                continue

            # Skip entry points
            if name in ENTRY_POINT_PATTERNS:
                continue

            # Skip test methods (they're called by test runner)
            if name.startswith('.test_') or name.startswith('test_'):
                continue

            # Skip docs nodes
            if src.startswith('docs/') or src.endswith('.md'):
                continue

            # Skip config files
            if src.endswith(('.json', '.yaml', '.yml', '.toml', '.ini')):
                continue

            orphans.append({
                'id': nid,
                'name': name,
                'src': src,
                'loc': loc,
                'outbound': outbound[nid],
            })

    # Sort by outbound count (potential dead code with outbound deps)
    orphans.sort(key=lambda x: x['outbound'], reverse=True)

    print(f"Graph: {len(nodes)} nodes, {len(links)} links")
    print(f"Orphans (zero inbound, filtered): {len(orphans)}")
    print()

    # Categorize
    true_orphans = [o for o in orphans if o['outbound'] == 0]
    potential_dead = [o for o in orphans if o['outbound'] > 0]

    print(f"  True orphans (0 inbound, 0 outbound): {len(true_orphans)}")
    print(f"  Potential dead code (0 inbound, >0 outbound): {len(potential_dead)}")
    print()

    if potential_dead:
        print("Top 20 potential dead code nodes (0 inbound, most outbound):")
        for o in potential_dead[:20]:
            print(f"  {o['name']} [{o['src']}:{o['loc']}] — {o['outbound']} outbound")

    print()

    # Degree distribution
    degrees = [inbound[nid] + outbound[nid] for nid in node_ids]
    degree_dist = Counter(degrees)
    print("Degree distribution (top 10):")
    for d, c in sorted(degree_dist.items())[:10]:
        print(f"  degree {d}: {c} nodes")


if __name__ == '__main__':
    graph_path = sys.argv[1] if len(sys.argv) > 1 else 'graphify-out/graph.json'
    find_orphans(graph_path)
