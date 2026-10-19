# Three-Surface Architecture Map — Avalanche Insight Hub

> **Audience:** All teammates (engineers, scientists, DevOps, stakeholders)
> **Purpose:** Clarify which repository to use for which task
> **Generated:** 2026-08-07

---

## The Three Surfaces

The Avalanche Insight Hub spans three distinct repository surfaces. Each has a different purpose, access level, and toolset.

### Surface 1: Private Repository (Development)

| Field | Value |
|-------|-------|
| **Repository** | `sanjabh11/avalanche-insight-hub` |
| **Access** | Private — team members only |
| **Purpose** | Main development, full codebase, all deliverables |
| **Graph** | graphify graph at `graphify-out/graph.json` (~19,968 nodes, ~37,870 links) |
| **Onboarding docs** | `docs/ONBOARDING_GUIDE.md`, `docs/SCIENTIST_ARCHITECTURE_BRIEF.md`, `docs/GRAPHIFY_EVIDENCE_APPENDIX.md` |
| **Use when** | Writing code, running graphify queries, reviewing validation contracts, onboarding |

**Graphify access:** Full — `graphify god-nodes`, `graphify path`, `graphify explain`, `graphify affected`, `graphify query`

**Key commands:**
```bash
cd ~/avalanche-insight-hub
graphify god-nodes --top 10
graphify path "main()" "upsert_forecast_grid()"
python3 scripts/find_orphans.py graphify-out/graph.json
```

---

### Surface 2: Public Cron Repository (Execution)

| Field | Value |
|-------|-------|
| **Repository** | `sanjabh1103/avalanche-insight-hub` |
| **Access** | Public — anyone can clone |
| **Purpose** | Cron job execution only (ml_pipeline.yml schedule) |
| **Graph** | May or may not be present (sync bug — being fixed) |
| **Onboarding docs** | `docs/KNOWLEDGE_GRAPH_GUIDE.md` only (all other docs deleted by sync) |
| **Use when** | Checking cron schedule, running backend tests in public context, verifying sync output |

**Graphify access:** None — this repo is runners-only. Do NOT run graphify here.

**Key commands:**
```bash
python3 scripts/verify_schedule_contract.py
python3 -m unittest discover -s backend/tests -p 'test_*.py'
```

**Sync flow:** `bash scripts/sync_to_public.sh --expected-public-sha <SHA>` (run from private repo)

---

### Surface 3: Public Knowledge Site (Visual Browsing)

| Field | Value |
|-------|-------|
| **Location** | `~/avalanche-insight-hub-public-knowledge-site` (local) → **https://dist-silk-sigma-21.vercel.app** (deployed) |
| **Access** | Public — URL-only access, no password, no backend, no secrets |
| **Purpose** | Visual graph browsing for non-engineers and external collaborators |
| **Graph (structural)** | Sanitized subset at `public/data/code-graph.json` (~5,076 nodes, ~8,434 edges) — accessible at `/graph` |
| **Graph (graphify)** | Full graphify visualizations at `/graphify/` — 19,968 nodes, 37,870 edges, 1,208 communities |
| **Onboarding docs** | In-app UI — 7-step tour, 6 architectural layers, deterministic explanations, 6 perspectives |
| **Use when** | Browsing architecture visually, sharing with stakeholders, external collaboration |

**Graphify visualizations at `/graphify/`:**
- `/graphify/graph.html` — Interactive network graph (vis-network, 20MB, 19,968 nodes)
- `/graphify/tree.html` — Collapsible file/function tree (D3 v7, 1.5MB)
- `/graphify/callflow.html` — Architecture call-flow diagrams (Mermaid, 380KB)
- `/graphify/` — Index page with links to all 3 visualizations

**Key commands:**
```bash
cd ~/avalanche-insight-hub-public-knowledge-site
npm ci && npm run build && npm run preview
python3 scripts/export_graph.py     # Refresh structural graph from private repo
python3 scripts/verify_public_safety.py  # Fail-closed safety check (structural + graphify)
vercel deploy dist/ --prod --yes    # Deploy to Vercel
```

**Redeploy runbook:** See `docs/KNOWLEDGE_GRAPH_GUIDE.md` → "Redeploy Runbook" section for the full 8-step procedure covering both structural and graphify graphs.

**Security:** CSP enforced (`default-src 'self'`, `worker-src 'self' blob:`, `frame-ancestors 'none'`), X-Frame-Options DENY, X-Content-Type-Options nosniff, field allowlists, denylist zone removal, customer name scrubbing (Partner/Partner/Partner → Agency), PII scanning (fail-closed), no AI endpoints.

---

## Which Surface Should I Use?

| If you are... | Use | Why |
|---------------|-----|-----|
| New engineer learning the codebase | Surface 1 | Full graphify access, onboarding guide, golden path |
| Scientist reviewing validation contracts | Surface 1 | Scientist brief, 5-field pattern, seam map |
| DevOps engineer checking cron jobs | Surface 2 | Schedule contract, cron-only execution |
| Stakeholder browsing architecture visually | Surface 3 | Interactive graph, no CLI needed, sanitized |
| External collaborator (no private access) | Surface 3 | Public, no secrets, CSP-enforced |
| Running the sync from private to public | Surface 1 → 2 | `sync_to_public.sh` from private repo |
| Refreshing the Knowledge Site graph | Surface 1 → 3 | `export_graph.py` reads from private repo |

---

## Graph Refresh Cadence

| Surface | When to refresh | How |
|---------|----------------|-----|
| Private (graphify) | After every merge to main | `graphify update .` (AST-only, ~10s) |
| Private (understand-anything) | After significant code changes | `bash scripts/refresh_knowledge_graph_structural.sh` (requires Understand plugin) |
| Public cron | After every sync | Automatic (if sync bug is fixed) |
| Knowledge Site | After private graph refresh | `python3 scripts/export_graph.py && python3 scripts/sanitize_graph.py && python3 scripts/generate_explanations.py` |

---

## Sync Flow (Surface 1 → Surface 2)

```
Private repo (main)
    │
    ├── sync_to_public.sh --dry-run          # Verify what will be synced
    ├── sync_to_public.sh --expected-public-sha <SHA>  # Execute sync
    │
    └── What gets removed:
        ├── docs/ONBOARDING_GUIDE.md
        ├── docs/SCIENTIST_ARCHITECTURE_BRIEF.md
        ├── docs/GRAPHIFY_EVIDENCE_APPENDIX.md
        ├── docs/THREE_SURFACE_MAP.md (this file)
        ├── AGENTS.md
        ├── scripts/sync_to_public.sh (self-removal)
        └── 20+ other private-only files
        
    └── What survives:
        ├── docs/KNOWLEDGE_GRAPH_GUIDE.md
        ├── scripts/find_orphans.py
        ├── .understand-anything/phase2-structural-graph.json (if sync bug fixed)
        └── All backend/ src/ supabase/ code (with customer→Partner text scrubbing)
```

---

## Export Flow (Surface 1 → Surface 3)

```
Private repo (.understand-anything/phase2-structural-graph.json)
    │
    ├── export_graph.py          # Field allowlists, unknown-field rejection
    ├── sanitize_graph.py        # PII scanning, denylist enforcement, fail-closed
    ├── generate_explanations.py # Deterministic explanations (no AI)
    ├── verify_public_safety.py  # Final safety check
    │
    └── Public Knowledge Site (public/data/code-graph.json)
        ├── 4,979 nodes (filtered to allowed prefixes: backend/, src/, supabase/)
        ├── 8,278 edges
        ├── 0 PII hits (verified)
        └── 23 denylist-adjacent test nodes (test files, not source — documented)
```

---

## Known Issues

1. **sync_to_public.sh graph-preserve bug:** `phase2-structural-graph.json` is gitignored but the sync script tries to preserve it via worktree checkout. Fix in progress.
2. **Understand-anything graph staleness:** The manifest's `analyzedCommit` must match repo HEAD for `export_graph.py` to succeed. Rebuild with `bash scripts/refresh_knowledge_graph_structural.sh` when stale.
3. **Denylist-adjacent test nodes in public graph:** 23 test files that test denylist zones (e.g., `test_label_governance.py`) appear in the public graph. These are test files, not denylist source files. The sanitizer checks exact source paths, not test paths. This is documented but not blocked.
4. **Graphify graph vs understand-anything graph:** The graphify graph (`graphify-out/graph.json`, ~19,968 nodes) is larger than the understand-anything graph (`.understand-anything/phase2-structural-graph.json`, ~4,979 nodes). The Knowledge Site uses the smaller, structural-only graph. The deliverables reference the larger graphify graph.
