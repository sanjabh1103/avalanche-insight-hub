# CD2 Team — Snowpack POC Visibility Guide

> **Generated:** 2026-08-13
> **Audience:** CD2 team members
> **Purpose:** Step-by-step guide to see the Snowpack POC on the live website and public graphify graphs

---

## Part 1 — What Can Be Seen from the Live Website (Netlify)

### URL

```
https://avalanche-insight-hub.netlify.app/
```

### What's Live Right Now

The main app is deployed and serves 8 routes. The POC evidence card is embedded in the Expert Mode page, lazy-loaded when you select the Pir Panjal region.

### Step-by-Step: Viewing the POC Evidence Card

| Step | Action | What You See |
|:---:|---|---|
| 1 | Open `https://avalanche-insight-hub.netlify.app/` in your browser | Landing page loads (HTTP 200) |
| 2 | Navigate to the forecast page (click "Forecast" or go to `/forecast`) | Main forecast map view loads |
| 3 | Click "Expert Mode" toggle or navigate to the expert panel | ExpertModePanel chunk loads (55.67 KB, lazy-loaded) |
| 4 | In the region selector, choose **Pir Panjal NW Himalaya** (`pir_panjal_nw_himalaya`) | The `isPirPanjalPocRegion()` check returns `true` |
| 5 | The **PirPanjalPocEvidenceCard** renders inline | Full POC evidence display (see below) |

### What the POC Evidence Card Shows

The card is rendered from `src/lib/pirPanjalPocEvidence.ts` (158 lines, deployed on the public scrubbed repo). It displays:

| Field | Value | Source |
|---|---|---|
| **Case ID** | `pir-panjal-gulmarg-wd-2024-02-22` | Embedded in TS file |
| **Site ID** | `pir-panjal-middle-candidate-34021875-74347536` | Embedded in TS file |
| **Latitude** | 34.021875 | Embedded in TS file |
| **Longitude** | 74.347536111 | Embedded in TS file |
| **Elevation** | 3,730 m | Embedded in TS file |
| **Slope** | 26.262132 degrees | Embedded in TS file |
| **Aspect** | 36.885404 degrees NE | Embedded in TS file |
| **Evaluation Window** | 2024-02-22 to 2024-02-24 | Embedded in TS file |
| **Elevation Band** | middle (3,200–4,000 m) | Embedded in TS file |
| **Horizon** | 48 hours | Embedded in TS file |
| **Ensemble Members** | 1 | Embedded in TS file |
| **Problem Types** | storm_new_snow, wind_slab | Embedded in TS file |
| **Layer Count** | 278 | Embedded in TS file |
| **Binary Version** | SNOWPACK 3.7.0 · MeteoIO 2.11.0 | Embedded in TS file |
| **Docker Image ID** | `sha256:254f4f7af9a9abfb49496a0024e5ec1cce5a9c707fa381f52e184758aad530df` | Embedded in TS file |
| **Snow Height** | 1.533 m | Embedded in TS file |
| **Bulk Density** | 227.5 kg/m³ | Embedded in TS file |
| **Stability Index** | 0.10 (unvalidated native index) | Embedded in TS file |
| **Weak Layer Depth** | 1.528 m | Embedded in TS file |
| **Weak Layer Grain Type** | `melt_forms` | Embedded in TS file |
| **Weak Layer Shear Strength** | 6.00 kPa | Embedded in TS file |
| **Temperature Gradient** | 4.2843 K/m | Embedded in TS file |
| **Liquid Water Content** | 0% | Embedded in TS file |
| **Profile Date** | 2024-02-23 12:00 UTC | Embedded in TS file |
| **Forcing Samples** | 3,504 hourly simulation samples + 48 warm-up hours (3,552 source samples) | Embedded in TS file |
| **Native runtime warnings** | None; explicit 3,600-second MeteoIO precipitation re-accumulation | Embedded in TS file/evidence packet |
| **Core Nulls** | 0 | Embedded in TS file |

### What's NOT on the Live Website

| Item | Why | Where to Find It |
|---|---|---|
| Evidence packet (narrative) | Docs are scrubbed during sync | Private repo only: `docs/MVP4/01_customer_review/PIR_PANJAL_POC_EVIDENCE_PACKET.md` |
| 15-slide deck (PDF/PPTX) | Docs are scrubbed during sync | Private repo only: `docs/MVP4/05_generated_assets/` |
| Decision record JSON | Docs are scrubbed during sync | Private repo only: `docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json` |
| Candidate result JSON | `backend/artifacts/` is gitignored | Local only (not in any repo) |
| Customer questions mirror | Docs are scrubbed during sync | Private repo only: `docs/MVP4/01_customer_review/Snowpack_questions.md` |
| Meeting minutes | Docs are scrubbed during sync | Private repo only: `docs/MVP4/01_customer_review/meeting_minutes/` |

### Verified Deployment Evidence

```
Netlify main app:     HTTP 200 (3,605 bytes index)
ExpertModePanel chunk: HTTP 200 (55.67 KB, lazy-loaded)
POC markers in chunk:  15/19 found (coordinates, elevation, slope, aspect, SNOWPACK version, Docker image SHA)
All 8 routes:          HTTP 200 (/, /expert, /methods, /scientist, /admin, /report, /landing, /knowledge-graph)
```

---

## Part 2 — What Can Be Seen from KS and Graphify Graphs (Public Repo + Vercel)

### URLs

| Surface | URL | Status |
|---|---|:---:|
| **Graphify network graph** | `https://dist-silk-sigma-21.vercel.app/graphify/graph.html` | HTTP 200 (944 KB) |
| **Graphify file tree** | `https://dist-silk-sigma-21.vercel.app/graphify/tree.html` | HTTP 200 (1.7 MB) |
| **Graphify call flow** | `https://dist-silk-sigma-21.vercel.app/graphify/callflow.html` | HTTP 200 (385 KB) |
| **KS graphify index** | `https://dist-silk-sigma-21.vercel.app/graphify/index.html` | HTTP 200 |
| **KS code-graph.json** | `https://dist-silk-sigma-21.vercel.app/data/code-graph.json` | HTTP 200 (4.4 MB, stale — no POC nodes) |
| **Public GitHub repo** | `https://github.com/sanjabh1103/avalanche-insight-hub` | Live |

### Step-by-Step: Viewing POC in the Graphify Network Graph

| Step | Action | What You See |
|:---:|---|---|
| 1 | Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html` | Vis.js network graph loads (1,316 community nodes, 1,408 cross-community edges) |
| 2 | Use the search/filter box (top-left) and type `pir_panjal` | Highlights community nodes containing POC modules |
| 3 | Visible POC community nodes: | |
| | `pir_panjal_poc_case.py` (node ID 490, blue) | POC case definition module |
| | `build_pir_panjal_poc_forcing.py` (node ID 640, blue) | Forcing builder module |
| | `run_pir_panjal_poc_vertical_slice.py` (node ID 738, brown) | Vertical slice runner |
| | `generate_pir_panjal_poc_deck.mjs` (node ID 1247, pink) | Deck generator script |
| | `PirPanjalPocDecisionRecordTests` (node ID 1260, blue) | Decision record tests |
| 4 | Click any POC node to see its connections | Edges to `meteoio_openmeteo.py`, `snowpack_adapter.py`, `SnowpackProxy`, etc. |
| 5 | Search for `SNOWPACK` | 120 occurrences — shows the full SNOWPACK ecosystem in the graph |
| 6 | Search for `MeteoIO` | 4 occurrences — MeteoIO/Open-Meteo adapter nodes |
| 7 | Search for `Docker` | 4 occurrences — Docker/Snowpack container nodes |

### Step-by-Step: Viewing POC in the Graphify File Tree

| Step | Action | What You See |
|:---:|---|---|
| 1 | Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html` | D3.js collapsible tree loads (1.7 MB, full 23,200-node hierarchy) |
| 2 | Expand `backend/` → `common/` | See `pir_panjal_geometry.py`, `pir_panjal_poc_case.py`, `snowpack_toolchain_identity.py`, `pir_panjal_decision_record.py` |
| 3 | Expand `backend/` → `scripts/` | See `build_pir_panjal_poc_forcing.py`, `capture_local_snowpack_identity.py`, `run_pir_panjal_poc_vertical_slice.py` |
| 4 | Expand `backend/` → `tests/` | See `test_pir_panjal_geometry.py`, `test_pir_panjal_poc_case.py`, `test_pir_panjal_poc_forcing.py`, `test_pir_panjal_vertical_slice.py`, `test_snowpack_toolchain_identity.py` |
| 5 | Expand `src/` → `components/` | See `PirPanjalPocEvidenceCard.tsx` |
| 6 | Expand `src/` → `lib/` | See `pirPanjalPocEvidence.ts` |
| 7 | Expand `scripts/` | See `generate_pir_panjal_poc_deck.mjs` |
| 8 | Click any file node to expand | Shows functions, classes, and methods inside that file |

**POC references in tree.html: 31 total** (23 `pir_panjal`, 2 `pir_panjal_geometry`, 2 `snowpack_toolchain`, 1 `capture_local_snowpack`, 1 `build_pir_panjal`, 1 `run_pir_panjal`, 1 `generate_pir_panjal`)

### Step-by-Step: Viewing POC in the Graphify Call Flow

| Step | Action | What You See |
|:---:|---|---|
| 1 | Open `https://dist-silk-sigma-21.vercel.app/graphify/callflow.html` | Mermaid call-flow diagram loads (385 KB) |
| 2 | Search for `SNOWPACK` | 131 occurrences — shows the SNOWPACK execution pipeline |
| 3 | Note | The callflow was regenerated from the updated graph but POC-specific call paths are not yet visible in this diagram (the callflow focuses on the main inference pipeline, not the POC vertical slice) |

### Step-by-Step: Viewing POC Code on the Public GitHub Repo

| Step | Action | URL |
|:---:|---|---|
| 1 | Open the public repo | `https://github.com/sanjabh1103/avalanche-insight-hub` |
| 2 | Navigate to `backend/common/pir_panjal_geometry.py` | Terrain derivation (SRTM HGT, slope, aspect) — 151 lines |
| 3 | Navigate to `backend/common/pir_panjal_poc_case.py` | POC case definition (coordinate, elevation, scope) |
| 4 | Navigate to `backend/common/snowpack_toolchain_identity.py` | Docker image identity capture (SHA-256 binding) |
| 5 | Navigate to `backend/common/pir_panjal_decision_record.py` | Decision record validator (schema, immutability, non-claims) |
| 6 | Navigate to `backend/scripts/build_pir_panjal_poc_forcing.py` | Open-Meteo historical forcing builder — 127 lines added |
| 7 | Navigate to `backend/scripts/capture_local_snowpack_identity.py` | Docker toolchain identity capture — 210 lines |
| 8 | Navigate to `backend/scripts/run_pir_panjal_poc_vertical_slice.py` | Vertical slice runner — 93 lines added |
| 9 | Navigate to `src/components/PirPanjalPocEvidenceCard.tsx` | Frontend evidence card component |
| 10 | Navigate to `src/lib/pirPanjalPocEvidence.ts` | Embedded POC result data (coordinates, profile, binary version) |
| 11 | Navigate to `scripts/generate_pir_panjal_poc_deck.mjs` | 15-slide deck generator — 128 lines |
| 12 | Navigate to `Dockerfile.snowpack` | Docker image definition for SNOWPACK 3.7.0 |
| 13 | Navigate to `backend/common/meteoio_openmeteo.py` | Open-Meteo API adapter (forcing data source) |
| 14 | Navigate to `backend/open_forcing/snowpack_adapter.py` | Snowpack forcing adapter |

### What's NOT on the Public Repo

| Item | Why |
|---|---|
| `docs/MVP4/` (all docs) | Sync script deletes all docs except `KNOWLEDGE_GRAPH_GUIDE.md` and `THREE_SURFACE_MAP.md` |
| `.github/workflows/poc_snowpack_pipeline.yml` | Explicitly removed by sync script |
| `scripts/sync_to_public.sh` | Self-removes during sync |
| `AGENTS.md` | Removed by sync script |
| `backend/artifacts/pir_panjal_poc_candidate/` | `backend/artifacts/` is in `.gitignore` |
| Partner/Partner/Partner references | Scrubbed and replaced with "Partner" during sync |

---

## Part 3 — Graph Node & Edge Cross-Verification

### Graph Growth Summary

| Metric | Before (Aug 7) | After (Aug 11) | Delta |
|---|---:|---:|---:|
| Total nodes | 19,968 | 23,200 | +3,232 |
| Total edges | 37,870 | 45,457 | +7,587 |
| POC nodes | 0 | 228 | +228 |
| POC edges | 0 | 411 | +411 |

### Per-Module Verification

| Module | Predicted Nodes | Actual Nodes | Predicted Edges | Actual Edges | Status |
|---|---|---|---|---|:---:|
| `pir_panjal_geometry.py` | 10–15 | 19 | ~10–15 | 36 | Exceeded |
| `capture_local_snowpack_identity.py` | 8–12 | 13 | ~8–12 | 36 | Exceeded |
| `snowpack_toolchain_identity.py` | 5–8 | 13 | ~5–8 | 40 | Exceeded |
| `generate_pir_panjal_poc_deck.mjs` | 3–5 | 10 | ~3–5 | 9 | Exceeded |
| `PirPanjalPocEvidenceCard.tsx` | 5–8 | 5 | ~5–8 | 23 | Match |
| `build_pir_panjal_poc_forcing.py` | 15–20 | 18 | ~15–20 | 75 | Exceeded |
| `run_pir_panjal_poc_vertical_slice.py` | 10–15 | 19 | ~10–15 | 88 | Exceeded |
| `pir_panjal_poc_case.py` (updated) | N/A | 40 | N/A | 111 | New |
| `pirPanjalPocEvidence.ts` | 5–8 | 10 | ~5–8 | 32 | Exceeded |
| **TOTAL** | **60–80** | **142** | **~60–80** | **411** | **All exceeded** |

---

## Part 4 — Quick Reference for CD2 Team

### If You Want To...

| Goal | URL | Steps |
|---|---|---|
| See the POC evidence card live | `https://avalanche-insight-hub.netlify.app/` | Navigate to forecast → Expert Mode → select Pir Panjal region |
| Browse POC code | `https://github.com/sanjabh1103/avalanche-insight-hub` | Navigate to `backend/common/pir_panjal_geometry.py` and related files |
| See POC in the network graph | `https://dist-silk-sigma-21.vercel.app/graphify/graph.html` | Search for "pir_panjal" — 16 references across 5 community nodes |
| Browse POC in the file tree | `https://dist-silk-sigma-21.vercel.app/graphify/tree.html` | Expand `backend/common/` or `backend/scripts/` — 31 POC references |
| See the SNOWPACK pipeline | `https://dist-silk-sigma-21.vercel.app/graphify/callflow.html` | Search for "SNOWPACK" — 131 references |
| Read the evidence packet (narrative) | Private repo only | `docs/MVP4/01_customer_review/PIR_PANJAL_POC_EVIDENCE_PACKET.md` |
| Read the 15-slide deck | Private repo only | `docs/MVP4/05_generated_assets/PIR_PANJAL_POC_READINESS_15_SLIDE_DECK.pdf` |
| Read the decision record | Private repo only | `docs/MVP4/00_governance/PIR_PANJAL_POC_DECISION_RECORD.json` |

### Key Coordinates

| Parameter | Value |
|---|---|
| Region | `pir_panjal_nw_himalaya` |
| Latitude | 34.021875 |
| Longitude | 74.347536111 |
| Elevation | 3,730 m |
| Slope | 26.262132 degrees |
| Aspect | 36.885404 degrees NE |
| SNOWPACK version | 3.7.0 |
| MeteoIO version | 2.11.0 |
| Docker image SHA | `sha256:254f4f7af9a9abfb49496a0024e5ec1cce5a9c707fa381f52e184758aad530df` |
| Forcing samples | 3,504 hourly |
| Profile layers | 278 |
| Evaluation window | 2024-02-22 to 2024-02-24 |
| Horizon | 48 hours |
| Ensemble members | 1 |

### Commits

| Repo | Commit | Message |
|---|---|---|
| Private source/presentation | `e0d677c3` | `docs: reconcile POC presentation artifacts with reviewer acknowledgment and v16 local run` |
| Public scrubbed release | `50a6745` | `sync: scrubbed public release from private repo e0d677c` |
| Hosted POC execution source | `26439d83` | Hosted run `31674452739`; run-bound execution commit |

---

## Known Limitations

1. **KS `code-graph.json` is stale** — The interactive graph at `/data/code-graph.json` has 5,076 nodes from Aug 7 (no POC nodes). The graphify visualization (`/graphify/graph.html`) is current with 23,200 nodes. The KS data export requires a schema transform from graphify format to phase2 structural format, which is pending.

2. **Callflow does not show POC-specific paths** — The callflow diagram was regenerated but focuses on the main inference pipeline. POC vertical slice call paths are not separately visualized.

3. **POC artifacts (candidate-result.json) are local only** — `backend/artifacts/` is gitignored. The result data is embedded in `src/lib/pirPanjalPocEvidence.ts` and visible in the deployed app, but the raw JSON artifact is not in any repo.

4. **Customer review docs are private only** — The evidence packet, slide deck, decision record, customer questions, and meeting minutes are scrubbed during sync and exist only in the private repo. This public-safe visibility guide and the separate ML/Python learning guide are the two deliberate exceptions.
