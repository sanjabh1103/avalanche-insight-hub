# Public Content Review Packet

## Status: APPROVED_PUBLIC_CONTENT

This packet contains the approved public content for graph-only v1. Owner approval was recorded as
`APPROVED_PUBLIC_CONTENT` in the Codex release instruction on 2026-08-04.

---

## Graph Counts

| Metric | Value |
|---|---|
| Nodes | 4,926 |
| Edges | 8,183 |
| Content hash | `cc26ff2f74f49fc3632cb2ba1b8504bde2e18d430e8f07348db8c018b9c3a040` |
| File SHA-256 | `df77d44e305e0877c4024e343b93da2c29ac7bf2dea9402e3ae1d0588caf3224` |
| Source commit | `f582d1822b3994a6d10832e66e085ab58c8304f4` |
| Export status | `approved` (clean scoped source snapshot) |

## Node Type Breakdown

- **file**: 907 nodes (all have non-null `sourceHash`)
- **function**: 3,254 nodes (all have `sourceHash: null`)
- **class**: 765 nodes (all have `sourceHash: null`)

## sourceHash Policy

- 907 file nodes include `sourceHash` (SHA-256 of file content) — these are structural file identifiers
- 4,019 function/class nodes have `sourceHash: null` — the source analysis only computed hashes at file level
- This is documented accurately in the AboutPage and AGENTS.md

## Map Status

| Metric | Value |
|---|---|
| Status | `blocked` |
| Reason | No rights-cleared static map snapshot exists |
| Cells | 0 (no fabricated data) |
| UI | Shows explicit `MAP_SNAPSHOT_NOT_AVAILABLE` blocked state |

## Sample Nodes

See `handoff/public-sample/review-sample.json` for full samples.

### File node example:
```json
{
  "id": "file:src/App.tsx",
  "name": "App.tsx",
  "type": "file",
  "relativePath": "src/App.tsx",
  "language": "typescript",
  "tags": [],
  "lineCount": 22,
  "sourceHash": "abc123..."
}
```

### Function node example:
```json
{
  "id": "function:backend/common/abc_optimizer.py:_evaluate",
  "name": "_evaluate",
  "type": "function",
  "relativePath": "backend/common/abc_optimizer.py",
  "language": "python",
  "tags": [],
  "lineCount": 25,
  "sourceHash": null
}
```

## CSP

```
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none';
```

- `connect-src 'self'` — allows same-origin data fetches (graph JSON, map JSON, explanations)
- No external connections allowed

## Source Names and Licenses

| Asset | Source | License | Status |
|---|---|---|---|
| Knowledge graph | Avalanche Insight Hub codebase | MIT | Approved static snapshot |
| Map data | (none — blocked) | — | Blocked |
| React 18.3.1 | Meta | MIT | Approved |
| Vite 5.4.21 | Vite team | MIT | Approved |
| TypeScript 5.6.2 | Microsoft | Apache-2.0 | Approved |
| Vitest 3.2.6 | Vitest team | MIT | Approved |

## Sanitizer Report

- **Files scanned**: 25
- **Findings**: 0
- **Public release status**: PASS
- See `handoff/sanitization-report.json` and `handoff/sanitization-report.md`

## Verification Results

| Check | Result |
|---|---|
| Build | ✓ 48 modules, 1.57s |
| Lint | ✓ 0 errors |
| Tests | ✓ 19/19 passed |
| Public safety | ✓ PASS (4/4 checks) |
| Sanitizer | ✓ PASS (25 files, 0 findings) |
| Browser smoke | ✓ Interactive preview verified: graph data loaded, map blocked state rendered, same-origin requests only; one host-header diagnostic remains for `frame-ancestors` |

| ECC Advisor review | ✓ NO-GO confirmed; source provenance, map approval, and public content approval remain open |

## Known Limitations

1. Graph is a static snapshot from 2026-08-04 — does not auto-update
2. The public graph is pinned to clean scoped source commit `f582d1822b39`
3. Map is blocked — no approved rights-cleared static snapshot exists
4. No live backend, no external API calls, no AI endpoints
5. No external map tiles, fonts, or CDN resources

## Dirty-State Status

- Source snapshot: **CLEAN** (0 non-generated dirty entries)
- Export status: `approved`
- Scope: Graph-only v1; map remains blocked until a rights-cleared snapshot is supplied

---

## Approval

`APPROVED_PUBLIC_CONTENT` has been received and recorded. Deployment remains a separate hosting
and public-URL verification step.
