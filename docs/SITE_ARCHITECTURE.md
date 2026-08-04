# Site Architecture

## Overview

Static single-page application built with Vite + React + TypeScript. No backend, no server-side code, no runtime API calls.

## Tech Stack

| Component | Technology | Version |
|---|---|---|
| Framework | React | 18.3.1 |
| Build tool | Vite | 5.4.21 |
| Language | TypeScript | 5.6.2 |
| Router | react-router-dom | 6.30.4 |
| Test runner | Vitest | 3.2.6 |

## Directory Structure

```
avalanche-insight-hub-public-knowledge-site/
├── docs/                    # Policy and architecture docs
├── handoff/                 # Handoff artifacts, reports, evidence
│   ├── advisor/             # Advisor call logs
│   └── public-sample/       # Review samples
├── public/                  # Static assets served as-is
│   ├── data/                # Graph, map, explanations, source ledger
│   ├── ATTRIBUTION.md       # Attribution for all assets
│   └── NOTICE                # NOTICE file
├── scripts/                 # Python scripts (no external deps)
│   ├── export_graph.py      # Strict graph export with allowlists
│   ├── generate_explanations.py  # Deterministic explanations
│   ├── sanitize_output.py   # Built output sanitizer
│   ├── verify_public_safety.py  # Public safety verification
│   └── measure_performance.py   # Performance metrics
├── src/                     # React source code
│   ├── components/          # UI components
│   ├── lib/                 # Loaders, perspectives
│   ├── pages/               # Page components
│   └── test/                # Unit tests
├── index.html               # HTML entry with CSP
├── package.json             # Pinned dependencies
├── tsconfig.json            # TypeScript config
└── vite.config.ts           # Vite config
```

## Data Flow

```
Source repo (read-only)
    │
    ├── export_graph.py ──→ public/data/code-graph.json
    │                        public/data/code-graph-manifest.json
    │
    ├── generate_explanations.py ──→ public/data/explanations.json
    │
    └── (map blocked — no data generated)

Build:
    npm run build ──→ dist/
                       ├── index.html (with CSP)
                       ├── assets/*.js, *.css
                       └── data/*.json (copied from public/)

Runtime:
    Browser ──→ fetch('/data/code-graph.json') ──→ JSON.parse ──→ React state
    No external network requests (CSP: connect-src 'self'; static data is same-origin)
```

## Pages

| Route | Page | Description |
|---|---|---|
| `/` | HomePage | Start here — what this site contains, how to use it |
| `/graph` | GraphPage | Knowledge graph viewer (canvas + table) |
| `/map` | MapPage | Map viewer (currently blocked state) |
| `/about` | AboutPage | Limitations, attribution, MIT license, provenance |

## Graph Viewer Architecture

- **GraphCanvas** — Custom canvas-based force-directed renderer (no external graph library)
  - O(n²) force simulation, caps at 2,000 visible nodes
  - Defaults to 'architecture' perspective (bounded)
- **TableView** — Sortable, paginated table (50 nodes/page)
- **SearchBar** — Debounced client-side search (300ms)
- **FilterPanel** — Perspective, node type, language, edge type filters
- **NodeDetailPanel** — Node details with beginner/technical explanation mode toggle
  - Beginner: plain text explanation
  - Technical: color-coded [STRUCTURAL FACT] / [DERIVED] / [INTERPRETATION] / [UNKNOWN]
- **ProvenanceCard** — Graph manifest display

## Security

- **CSP:** `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none';`
- **No external resources:** No CDN, no external fonts, no analytics, no external scripts
- **No external runtime API calls:** All data is static JSON fetched from the same origin
- **Field allowlists:** Graph nodes and edges only contain whitelisted fields
- **PII redaction:** Emails and absolute paths redacted before export
- **Fail-closed sanitizer:** Any forbidden content finding blocks the build
