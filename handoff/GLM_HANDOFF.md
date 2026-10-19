# GLM Handoff

## Executive Status

**`APPROVED_GRAPH_ONLY_V1 — LOCAL RELEASE CANDIDATE`**

The implementation and local release gates are complete for graph-only v1. The site builds, lints,
tests pass, and all safety gates pass. Hosting deployment remains a separate manual step.

1. **No approved map snapshot** — map remains in `blocked` state (no fabricated data)
2. **Public URL deployment not performed** — `dist/` is locally verified only

## Codex Audit Gaps — All Fixed

| Gap | Priority | Fix |
|---|---|---|
| CSP `connect-src 'none'` blocks data fetches | P0 | Changed to `connect-src 'self'` |
| Navigation Graph link points to `/` | P0 | Changed to `/graph`, added Home link |
| AboutPage claims 480-cell synthetic map | P0 | Rewritten — map described as blocked, no synthetic claims |
| sourceHash documentation contradicts data | P0 | AboutPage now documents: 907 file nodes have hash, 4019 function/class nodes are null |
| No ESLint 9 config | P1 | Created `eslint.config.js` with flat config, `npm run lint` passes |
| Direct `/graph` returns 404 on static host | P1 | Added `public/404.html`, `public/_redirects`, `public/vercel.json` for SPA fallback |
| `@types/node` uses `^22.7.4` | P1 | Pinned to `22.7.4` (no caret) |
| Browser verification unperformed | P1 | Browser smoke test completed — routes, graph interactions, fallback page, CSP, and same-origin data verified |
| AGENTS.md claims synthetic map | P1 | Rewritten — no synthetic claims, correct paths |
| Stale `site/handoff/HANDOFF_MANIFEST.md` | P2 | Removed `site/` directory entirely |

## What Was Implemented

- Static React + TypeScript + Vite site with no backend
- Code knowledge graph viewer (canvas + table) with 4,926 nodes / 8,183 edges
- 7 graph perspectives (all, architecture, ML pipeline, data flow, security gates, tests, release evidence)
- Search, node type filter, language filter, edge type filter
- Node detail panel with beginner/technical explanation mode toggle
- Deterministic template-based explanations (no AI)
- Strict graph export with field allowlists, canonical JSON, sorted keys, dangling edge rejection
- PII redaction with fail-closed behavior
- Public sanitizer scanning built output for forbidden strings, PII, external resources
- Public safety verification script (checks CSP, field allowlists, map blocked state)
- Map page with explicit blocked state (no fabricated data)
- Home/Start Here page
- About page with accurate limitations, attribution, MIT license, provenance
- CSP header: `connect-src 'self'` (allows same-origin data fetches, blocks external)
- SPA fallback routing (404.html, _redirects, vercel.json)
- Attribution files (ATTRIBUTION.md, NOTICE, source-ledger.json)
- ESLint 9 flat config — `npm run lint` passes
- 20 unit tests (all passing)
- Performance measurements
- Full handoff documentation

## What Was NOT Implemented

- Map rendering for approved snapshots (only blocked state — no approved snapshot exists)
- Canonical remote promotion (the clean scoped snapshot is recorded locally)
- Static hosting deployment and public URL verification

## Test Commands and Actual Outputs

### Build
```
✓ 49 modules transformed.
dist/index.html                       1.01 kB
dist/assets/index-CkmWZGGR.css        0.96 kB
dist/assets/router-B-dTo4Gw.js       22.10 kB
dist/assets/index-oXLBLsWM.js        44.47 kB
dist/assets/react-core-5TPL3RWa.js  142.22 kB
✓ built successfully
```

### Lint
```
> eslint .
(exit code 0, no errors)
```

### Tests
```
Test Files  5 passed (5)
     Tests  20 passed (20)
```

### Public Safety
```
Checking graph data... PASS
Checking map data... PASS
Checking manifest... PASS
Checking built output... PASS
PUBLIC SAFETY VERIFICATION: PASS
```

### Sanitizer
```
Files scanned: 23
Findings: 0
All checks passed.
Public release status: PASS
```

### Browser Smoke Test
```
Preview: vite preview --host 127.0.0.1 --port 4175
Home /: interactive load ✓
Graph /graph: interactive load; architecture perspective rendered ✓
Map /map: interactive blocked state rendered ✓
About /about: interactive load ✓
Unknown route: user-facing Page not found recovery screen served ✓
Graph data /data/code-graph.json: 200 ✓
Explanations /data/explanations.json: 200 ✓
Graph manifest /data/code-graph-manifest.json: 200 ✓
CSP: connect-src 'self' ✓
No external network requests observed ✓
Browser diagnostic: frame-ancestors is ignored in a meta tag; configure it as a host response header before production deployment
```

## Local Preview URL

```
http://127.0.0.1:4175
```

## ECC Advisor Review

- **Initial check:** 2026-08-04T05:56:39Z — NO-GO while the source was dirty and approval was open
- **Corrected review:** clean scoped snapshot required; the approved graph-only export now binds to commit `f582d1822b39`
- **Final review:** local graph-only candidate approved; only public host deployment and live URL verification remain
- **Guidance followed:** no main-repository mutation, no map bypass, no fabricated data, and no deployment claim

## Current Release Gates

1. **No approved map snapshot** — Map is in `blocked` state. See `handoff/MAP_INPUT_REQUEST.md`.
2. **Public hosting deployment** — host selection, deployment, and live URL smoke test remain manual.

## Exact Recommended Next Action

1. **Use** the approved graph-only v1 content in `handoff/PUBLIC_CONTENT_REVIEW_PACKET.md`.
2. **Keep** the map blocked until a rights-cleared static snapshot is supplied.
3. **Deploy** the locally verified `dist/` directory to the selected static host.
4. **Verify** the public URL and record the URL plus rollback hashes.
