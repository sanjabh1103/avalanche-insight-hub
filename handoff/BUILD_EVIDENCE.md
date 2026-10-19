# Build Evidence

**Measured at:** 2026-08-04T06:53:17Z

## Build Time

- 71.66s (exit code: 0)

## Bundle Sizes

| File | Size (KB) |
|---|---|
| index-CkmWZGGR.css | 0.93 |
| index-gfeP4EDl.js | 44.06 |
| react-core-5TPL3RWa.js | 138.88 |
| router-B-dTo4Gw.js | 21.58 |

## Data Sizes

| File | Size (MB) |
|---|---|
| code-graph-manifest.json | 0.0 |
| code-graph.json | 4.08 |
| explanations.json | 1.7 |
| forecast-map-manifest.json | 0.0 |
| forecast-map.json | 0.0 |
| source-ledger.json | 0.0 |

## Total Initial Page Load

- 206.45 KB (0.2 MB)

## Graph JSON Parse Estimate

- ~0.054s (estimated from file size)

## Notes

- Graph view defaults to 'architecture' perspective (bounded) — not all 4,926 nodes
- Table view paginates at 50 nodes per page
- Canvas renderer caps at 2,000 visible nodes for O(n²) force simulation
- Search is client-side, debounced at 300ms
- No external network requests at runtime — static JSON is fetched from the same origin
- Interactive browser verification is a separate release gate recorded in handoff/GLM_HANDOFF.md

## Browser Verification

- Verified with Playwright against `vite preview` at `http://127.0.0.1:4175`
- `/`, `/graph`, `/map`, and `/about` all returned the SPA successfully
- An unknown route returned the user-facing `Page not found` recovery screen with Home and Graph links
- `/graph` rendered the architecture perspective with 1,672 visible nodes and 765 edges
- Graph JSON, explanations JSON, and graph manifest loaded with HTTP 200
- `/map` rendered the explicit `MAP_SNAPSHOT_NOT_AVAILABLE` blocked state
- No external network requests were observed; data requests were same-origin only
- One non-blocking browser diagnostic remains: `frame-ancestors` is ignored when delivered via a meta tag; enforce that directive with the eventual host response headers
