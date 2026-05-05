# Top 20 Features — Avalanche Insight Hub

Updated: May 5, 2026

This file remains a broad current-repo feature map, not a pure public-demo list. It now separates four layers with explicit boundaries:

- `current live MVP`
- `repo/admin verified capability`
- `shadow/future science path`
- `research-only precedent`

Evidence baseline used for this refresh:

- Repo truth: `src/App.tsx`, `src/pages/Index.tsx`, current UI components, `package.json`, backend requirements, and active operator paths.
- Live truth: the canonical demo surface is `https://avalanche-insight-hub.netlify.app/`, with `/` and `/admin` as the only customer-safe route references.
- Research truth: client publications, peer-reviewed avalanche papers, EAWS material, and WMO guidance were used to validate or soften claims, not to inflate them.

Proof levels used below:

- `Live demo`: visible in the routed public app or the live admin gate right now.
- `Repo/admin verified`: implemented and verifiable in code or operator surfaces, but not a core public demo moment.
- `Shadow-gated or config-gated`: present in the repo, but held behind release gates, credentials, or non-default runtime paths.

## Current MVP And Verified Stack

### Current Technology Stack Now In Repo

| Layer | Implemented now | Why it matters now | Caveat |
|---|---|---|---|
| Frontend app | React 18, Vite 7, TypeScript 5.8, React Router 6, TanStack React Query 5, Tailwind/Radix, Framer Motion | Delivers a fast forecast workspace with stable state management and modern client routing. | Modern UI tooling is not itself the scientific moat. |
| Mapping and 3D | Leaflet, React-Leaflet, Turf, Recharts, `@react-three/fiber`, `@react-three/drei` | Powers map review, overlays, charts, and voxel-style terrain inspection. | Advanced visualization does not by itself solve sparse-data truth gaps. |
| Platform and delivery | Supabase JS 2, Postgres/PostGIS, Edge Functions, Vite PWA / Workbox | Supports async jobs, auth gating, report replay, and published forecast artifact delivery. | Some operator flows remain gated behind credentials and background jobs. |
| Science and ML runtime | scikit-learn 1.8, imbalanced-learn, SHAP 0.51, PyTorch 2.5+, segmentation-models-pytorch, timm, einops | Gives the repo a credible baseline scorer, explainability path, and future deep-learning expansion path. | Not every imported science dependency is active in the public MVP today. |
| Geospatial backend | rasterio, whitebox, Earth Engine integration | Supports terrain, snow-cover, raster, and geometry workflows needed for avalanche mapping. | Several geospatial chains are repo-valid but not visible in the public route. |
| Verification stack | Vitest, React Testing Library, Playwright | Supports browser and component verification of the public workspace and admin shell. | Not every future-path science flow is fully end-to-end tested yet. |

## Top 3 Demo Story

| Rank | Demo story | Why it matters | Proof |
|---|---|---|---|
| 1 | Precomputed 72h forecast workspace | The public app already delivers a usable batch-first forecast experience instead of making the user wait for heavy compute. | `Live demo` |
| 2 | EAWS-style experimental bulletin with explicit uncertainty | The app already frames danger by daypart, problem type, elevation/aspect, and reduced-confidence states. | `Live demo` |
| 3 | Honest operational decision support | Masked terrain, share/export/report actions, and expert overlays make the forecast easier to use without pretending the science is finished. | `Live demo` |

## Ranked Feature Map

| Rank | Feature | What it does | Proof level | Maturity (1-5) | Why this matters to customer pain | Caveat |
|---|---|---|---|---:|---|---|
| 1 | Precomputed 72h forecast workspace | Loads the latest published batch artifact, exposes ready/partial/stale states, and lazy-hydrates hourly grids. | `Live demo` | 5 | Solves the customer pain of slow, brittle forecast delivery by moving heavy compute off the user path. | Batch-first delivery is real; true full-model reruns are not happening on every click. |
| 2 | EAWS-style experimental daypart bulletin | Shows danger level, avalanche problem, critical elevations/aspects, daypart chips, and peak-window framing. | `Live demo` | 5 | Converts model output into a structured public-facing forecast instead of a raw internal score. | It is explicitly `EAWS-style experimental`, not an official avalanche warning service bulletin. |
| 3 | APT-gated masked terrain contract | Uses the `apt_30_50_v1` slope gate and public masking rules so irrelevant terrain is shown as masked rather than falsely low danger. | `Live demo` | 5 | Addresses a key trust pain: users are less likely to misread out-of-scope terrain as safe terrain. | APT gating improves honesty but does not fully solve snowline or snow-cover eligibility. |
| 4 | Uncertainty and evidence-coverage signaling | Propagates `reduced confidence`, high-uncertainty counts, and thin-SAR-support warnings into the bulletin and dashboard. | `Live demo` | 5 | Answers the customer demand for transparent outputs rather than hidden model guesswork. | Coverage badges do not mean SAR is fully operational across all runs and regions. |
| 5 | Shareable full-state forecast links | Encodes region, bbox, hour, forecast id, selected cell, expert mode, and 3D state in one URL. | `Live demo` | 5 | Solves coordination pain for guides, operators, and rescue-style reviews. | Restoring state depends on the referenced published forecast remaining resolvable. |
| 6 | CSV and JSON export | Exports grid cells, uncertainty fields, SHAP values, metadata, and mapped events. | `Live demo` | 5 | Reduces friction for agency review, offline analysis, and scientific handoff. | Export works only after a forecast artifact is loaded. |
| 7 | Field report capture in the public app | Lets users submit avalanche-related field observations from the forecast workspace and merges successful reports back into the event view. | `Live demo` | 5 | Creates a concrete path to reduce dependence on centralized observation programs alone. | Raw user reports still need downstream governance before they should influence model trust. |
| 8 | Offline field-report sync and reconnect replay | Uses a service worker plus queued replay on startup or reconnect so reports can survive low-connectivity conditions. | `Repo/admin verified` | 4 | Targets the customer pain of sparse or unreliable mountain connectivity. | The mechanism is implemented, but each deployment still needs explicit offline smoke verification. |
| 9 | Expert overlays with runout and asset warnings | Toggles roads, infrastructure, vector polygons, and runout intersection warnings. | `Live demo` | 5 | Moves the product closer to consequence-aware operations instead of map-only hazard viewing. | Overlay quality depends on available runout artifacts and OSM coverage. |
| 10 | 3D voxel neighborhood view | Opens a 3D modal that extrudes terrain and mapped features while respecting masked and unavailable states. | `Repo/admin verified` | 4 | Helps advanced users inspect spatial structure when 2D views hide slope relationships. | Sparse OSM regions fall back to simpler terrain geometry. |
| 11 | Admin operator lane | Provides an authenticated operator route with access gating and a lazily loaded admin dashboard. | `Repo/admin verified` | 4 | Separates public forecast consumption from internal release and monitoring work. | The live proof right now is the gate and route shell; the full dashboard requires an operator session. |
| 12 | Model status and release-evidence surfaces | Shows version, freshness, candidate-shadow status, benchmark timing, and evidence volume in the sidebar and admin lane. | `Repo/admin verified` | 4 | Addresses the customer demand for objective release discipline instead of hand-wavy AI claims. | The readout is only as strong as the upstream `model_status` rows and jobs feeding it. |
| 13 | Batch artifact delivery architecture | Serves published `forecast_runs` and `forecast_grids` through manifests and per-hour payload loading rather than giant one-shot responses. | `Repo/admin verified` | 4 | Makes the app more stable under heavy geospatial payloads and matches the compute-bottleneck reality in avalanche science. | This is a strong architectural capability, but most users experience it indirectly. |
| 14 | Groundsource-style news and field-report ingestion | Uses `backend/news_ingest.py` and `ingest-event` to transform news and field reports into structured avalanche-event records. | `Repo/admin verified` | 4 | Directly addresses missing occurrence records in sparse-data regions. | This is inspired by Google’s flood-domain Groundsource approach; it is not avalanche-standard proof by itself. |
| 15 | Governed event weighting and deduplication | Assigns `label_confidence`, `training_weight`, deposit-vs-release checks, and dedupe logic before records are trusted downstream. | `Repo/admin verified` | 4 | Solves the customer pain that autonomous evidence becomes dangerous if it is ungoverned. | Governance helps, but extracted evidence can still be incomplete or wrong. |
| 16 | Evaluation and outcome-labeling loop | Exposes `label_forecast_outcomes` and `run_evaluation` jobs plus slice-level metrics such as ECE, Brier, and PSS. | `Repo/admin verified` | 4 | Supports rare-event-aware model governance rather than vanity accuracy reporting. | This governance loop is real, but it is mostly an operator capability, not a public MVP moment. |
| 17 | MTS-LSTM candidate shadow path | Keeps an env-gated multi-time-scale LSTM path with PSS/Brier/SAR promotion gates and shadow-mode defaults. | `Shadow-gated or config-gated` | 3 | Gives the repo a credible path beyond a simpler baseline scorer and aligns with the client’s longer ANN/HIM-STRAT lineage. | It should not be described as the active public scoring path unless promotion gates actually pass. |
| 18 | Physics-aware runout seeding and persisted runouts | Uses public-risk and APT-gated runout seeding and can persist runout polygons for later overlay use. | `Repo/admin verified` | 4 | Adds consequence context beyond a colored cell grid, which is important for roads and settlements. | Some runs intentionally skip runout generation or publish empty runout sets. |
| 19 | Multi-hazard schema foundation | Threads `hazard_type` through schema and jobs so the platform can grow beyond avalanche later. | `Repo/admin verified` | 3 | Future-proofs the data model for co-development beyond a single hazard type. | Avalanche is the only implemented hazard flow today. |
| 20 | Open-source and self-hostable stack | Ships as a public React/Vite + Supabase + Python/Modal-style stack that can be inspected and self-operated. | `Repo/admin verified` | 4 | Reduces vendor lock-in and supports scientist-team co-development rather than a black-box vendor posture. | Self-hosting still requires credentials, infrastructure, and operator setup. |

## Future Product Path And Research-Driven Expansions

These items are intentionally separated from the ranked feature map because they are credible next-step directions, not current MVP proof.

| Rank | Future path feature | Why it is credible | Current base in repo or research | Horizon | Readiness (1-5) | Caveat |
|---|---|---|---|---|---:|---|
| 1 | Governed autonomous evidence fusion | The repo already has news ingest, field-report replay, and weighted event governance; the next step is stronger corroboration logic across sources. | `backend/news_ingest.py`, field-report queueing, `training_weight`, client publications on sparse-data pain | 3-6 months | 4 | This still does not replace snow-truth collection by itself. |
| 2 | Scientist-in-the-loop validation suite | The customer wants co-development with their scientist team, and the repo already has evaluation jobs and release evidence surfaces. | `run_evaluation`, `label_forecast_outcomes`, admin surfaces, client research lineage | 3-6 months | 4 | Requires agreed validation protocol and shared review cadence. |
| 3 | Operational SAR artifact pipeline | The repo has SAR coverage semantics and schema hooks; next is promoted mask generation, geometry storage, and operator QA. | `sar_mask_asset_refs`, `sar_event_geometries`, wave-4 planning docs | 6-12 months | 3 | Remote sensing coverage and validation remain the hard bottlenecks. |
| 4 | Promoted MTS-LSTM scorer with RF surrogate explanations | The shadow path and promotion-gate language already exist; the next step is real GPU training plus release qualification. | `lstm_model.py` pathing, wave-4 context, ANN/HIM-STRAT lineage | 6-12 months | 3 | Promotion must be earned with evaluation; it is not a marketing swap. |
| 5 | Snowpack critical-layer validation loop | International research shows that weak-layer simulation is useful only with real-time validation suites. | Mayer 2023, Herla 2024, client HIM-STRAT lineage | 6-12 months | 2 | This requires more data, scientist involvement, and validation discipline than the MVP currently has. |
| 6 | Impact-based alert packaging and dissemination | The forecast UX plus impact overlays create a base for future WMO-style impact messaging and alert packaging. | Public bulletin UI, expert overlays, WMO impact-based warning guidance | 9-15 months | 2 | Official-authority dissemination is outside current MVP proof. |
| 7 | Scientist-grade operator workflows for roads and infrastructure | Impact overlays and runout logic can be hardened into corridor and asset workflows. | Expert overlays, persisted runouts, share/export surfaces | 9-15 months | 3 | Needs better asset data quality and field-operational validation. |
| 8 | Multi-region Himalayan pilot dataset and benchmark pack | The client publication lineage and repo schema create a credible base for a scientist co-development pilot across regions. | Open schema, event governance, publications from 2008-2025 | 12-18 months | 2 | This needs fresh labeled data and a jointly owned benchmark protocol. |

## What This File Intentionally Does Not Claim

- It does not claim the public app is running a fully active LSTM or physics-informed sequence path today.
- It does not claim every forecast click triggers a live ensemble or continuous retraining loop.
- It does not claim Google Groundsource is already an avalanche-standard methodology.
- It does not claim EAWS compliance beyond an `EAWS-style experimental` public framing.
- It does not treat future-path rows as shipped customer-demo capability.
