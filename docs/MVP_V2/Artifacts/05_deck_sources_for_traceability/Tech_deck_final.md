# Deck 4 Final: Technical Architecture

Updated: May 24, 2026

## Deck Design System

- Theme: Systems Blueprint
- Backgrounds: alternate only between `Light Mist #F4F8F7` and `Deep Spruce #102C2A`
- Primary accent: `Signal Teal #1C7C74`
- Secondary accents: `Circuit Lime #7E9F35`, `Blueprint Ink #26373A`, `Cloud White #FFFFFF`
- Typography: IBM Plex Sans for body, Space Grotesk for headings
- Customer-facing tone: architecture clarity. Every slide separates current, candidate/gated, and proposed states.
- Asset use: use screenshots only for route proof. Use diagrams for architecture.

## Slide 1: Architecture Proof Boundary

**Background:** Deep Spruce
**Customer message:**
The deployed architecture proves a live public route, a live admin route, same-day full-grid cell publication, and a hosted authenticated admin observability view. MVP V2 adds a research-only Swiss RAvaFcast lane and a Himalayan v3 partner-evidence pipeline, while scientist validation and operational qualification remain required before stronger claims.

**Current state and future strategy:**
- Hosted `/` and `/admin` are live
- Public proof: same-day `20x20` / `72h` full-grid cell batch from `2026-05-08`
- Hosted authenticated admin smoke succeeded on May 8, 2026
- Metadata and preview assets use Avalanche Insight Hub branding
- `production_scoring_allowed=false` and `himalayan_accuracy_claim_allowed=false` remain the governing boundaries for new evidence lanes

**Evidence level:** `Hosted production` plus `Repo/admin verified`
**Supporting sources:** [Proof Manifest](../06_Proof_Status_And_Screenshot_Manifest.md), [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md), [Himalayan Pre-Partner Evidence](../../../MVP%20V2/Himalayan_PrePartner_Evidence_Finite_Checkpoint.md)

---

## Slide 2: Current Platform Layers

**Background:** Light Mist
**Customer message:**
The current platform separates presentation, storage, artifact delivery, batch compute, machine learning, governance, partner evidence intake, remote compute, and offline reliability.

**Current state and future strategy:**
- Interface: React, Vite, Leaflet, Recharts
- Data and storage: Supabase, Postgres, Storage, Auth
- Artifact delivery: manifests, hourly grids, runout overlays
- Batch compute: Python jobs
- Governance: model status, benchmark, release gates
- Research evidence: Swiss reproduction artifacts and Himalayan partner-package triage outputs

**Evidence level:** `Repo/admin verified`
**Supporting source:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md)

---

## Slide 3: Interface Layer

**Background:** Light Mist
**Customer message:**
React and Vite form the presentation layer. The browser renders the public workspace and admin route while heavy avalanche science stays outside the browser.

**Current state and future strategy:**
- `/` public forecast workspace
- `/admin` operator observability lane
- Stateful route rendering
- Map, bulletin, timeline, share, export, report controls

**Evidence level:** `Repo/admin verified` plus `Hosted production`
**Supporting source:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md)

---

## Slide 4: Supabase Data And Storage Layer

**Background:** Deep Spruce
**Customer message:**
Supabase is the system of record for structured records, authentication, storage references, and operator-access surfaces.

**Current state and future strategy:**
- Postgres structured records
- Supabase authentication
- Supabase Storage artifact references
- Edge Functions for selected server-side tasks
- Row-Level Security for access boundaries

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md)

---

## Slide 5: Forecast Publication And Artifact Hydration

**Background:** Light Mist
**Customer message:**
The public route hydrates prepared forecast artifacts. Freshness state is part of the product contract.

**Current state and future strategy:**
- Forecast run metadata
- Artifact manifest
- Hourly grid payloads
- Optional runout overlay payloads
- Browser-side loading and decompression

**Evidence level:** `Hosted production` plus `Repo/admin verified`
**Supporting sources:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md), [Evidence Surface Ledger](../../source/Scientist_evidence_surface_ledger.md)

---

## Slide 6: Offline Batch Compute Split

**Background:** Light Mist
**Customer message:**
The core architectural principle is to keep heavy mathematical work outside the public route and outside thin serverless request paths.

**Current state and future strategy:**
- Current: scheduled/operator-triggered Python jobs
- Future direction: GitHub Actions or lightweight VPS
- Heavy work: feature selection, rare-event balancing, inference, runout physics
- Public route: presentation and review

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md), [PRD Addendum](../../../prd_add3.md)

---

## Slide 7: Active Scorer And Explanation Layer

**Background:** Deep Spruce
**Customer message:**
The active model path is a Random Forest baseline. The current active full-grid run uses heuristic explanation fallback; TreeSHAP refresh remains a hardening gate. Candidate deep-learning paths remain gated.

**Current state and future strategy:**
- Active: `surrogate_rf_v1`
- Current run explanation: `heuristic_fallback`
- TreeSHAP: implemented path, not stronger proof for the current active run
- Supporting training concepts: KMeansSMOTE, Recursive Feature Elimination, calibration
- Candidate: MTS-LSTM, gated

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md), [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md)

---

## Slide 8: Admin Governance Lane

**Background:** Light Mist
**Customer message:**
The admin lane exposes the information needed to keep model claims bounded: source health, provenance, model status, stability, benchmarks, jobs, reports, evaluation, and publication controls.

**Current state and future strategy:**
- Source health
- Decision provenance
- Model status
- Stability and benchmark summaries
- Publication controls

**Evidence level:** `Hosted production` plus `Repo/admin verified`
**Screenshot:** ![Hosted authenticated admin full-grid run proof](assets/screenshots/2026-05-08_hosted-admin-auth-full-grid-run.png)
**Supporting sources:** [Proof Manifest](../06_Proof_Status_And_Screenshot_Manifest.md), [Evidence Surface Ledger](../../source/Scientist_evidence_surface_ledger.md)

---

## Slide 9: Offline Field Reporting

**Background:** Light Mist
**Customer message:**
The platform includes offline report queueing and replay. It is implemented capability, but field reliability still needs deployment-specific smoke testing.

**Current state and future strategy:**
- Progressive Web App pattern
- Service Worker registration
- IndexedDB local queue
- Startup and reconnect flush
- Field proof remains deployment-specific

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Current Platform Architecture](../../source/Technical_Architecture_Current_Platform.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md)

---

## Slide 10: Modal.com Candidate Compute Plane

**Background:** Deep Spruce
**Customer message:**
Modal.com supports heavier candidate workflows away from the public route. It is separate from the proof behind current public forecast scoring and from the Himalayan partner-evidence intake pipeline.

**Current state and future strategy:**
- MTS-LSTM training candidate
- SAR segmentation candidate
- Persistent artifact volumes
- Authenticated worker endpoints
- Current public scorer remains Random Forest baseline
- No GPU run is authorized by partner handoff or synthetic validation success

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md), [Modal/GPU Evidence Table](../07_Modal_GPU_Evidence_Table.md)

---

## Slide 11: Future Offline-Batch Paradigm

**Background:** Light Mist
**Customer message:**
The PRD direction keeps React and Supabase as presentation and storage layers while moving heavier math into offline batch processing.

**Current state and future strategy:**
- Presentation: React, Leaflet, 3D views
- Storage: Supabase and Postgres
- Compute: GitHub Actions or lightweight VPS
- Heavy math: feature selection, KMeansSMOTE, inference, runout physics

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [PRD Addendum](../../../prd_add3.md), [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md)

---

## Slide 12: Proposed Data Contract

**Background:** Light Mist
**Customer message:**
The proposed architecture now has two tracks: public forecast publication and research-only partner evidence governance.

**Current state and future strategy:**
- Public path: `avalanche_events`, topographic enrichment, `forecast_grids`, `grid_geojson`, and `runout_polygons`
- Himalayan v3 path: ten evidence CSV templates, `partner_source_manifest`, `source_ref` hashes, and release-gate attestations
- Partner packet: `partner_handoff_readme.md`, `partner_field_dictionary.md`, checksum guide, source manifest template, and blank evidence CSVs
- Triage outputs: source-manifest validation, evidence validation, leakage audit, artifact manifest, source traceability, and status dashboard
- PostGIS remains a proposed geospatial extension, not current partner-evidence proof

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [PRD Addendum](../../../prd_add3.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Partner Schema Mapping](../../../EnviDat_to_Partner_Schema_Mapping.md)

---

## Slide 13: Proposed ML And Runout Pipeline

**Background:** Deep Spruce
**Customer message:**
The proposed future pipeline combines rare-event balancing, feature selection, calibrated Random Forest inference, uncertainty bounds, research-only RAvaFcast reproduction, and memory-safe Alpha-Beta runout processing.

**Current state and future strategy:**
- KMeansSMOTE for rare events
- Recursive Feature Elimination for feature discipline
- Calibrated Random Forest
- Swiss RAvaFcast research lane: Stage 1 RF4, Stage 2 GPxyz blocked until station coordinates, Stage 3 aggregation blocked until grid/polygons
- Tree variance for uncertainty bounds
- WhiteboxTools Alpha-Beta runout with DEM cropping remains a validation path
- Current active runout proof is analytical Alpha-Beta fallback; Whitebox smoke passed separately

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [PRD Addendum](../../../prd_add3.md), [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md)

---

## Slide 14: Current, Partial, Candidate, Proposed

**Background:** Light Mist
**Customer message:**
The technical deck should prevent architecture overclaim by classifying every major system path and evidence lane.

**Current state and future strategy:**
- Current: hosted public route, admin route, RF baseline, artifact hydration
- Partial/current: offline report queueing
- Candidate/gated: MTS-LSTM, SAR, TreeSHAP refresh for the active full-grid run
- Research-only: Swiss RAvaFcast reproduction and Himalayan partner-package triage
- Proposed/validation: GitHub Actions/VPS batch compute, PostGIS terrain enrichment, WhiteboxTools runout

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md), [Claim Ledger](../../source/Scientist_claim_ledger.md)

---

## Slide 15: Architecture Gates And Next Workstreams

**Background:** Deep Spruce
**Customer message:**
The next engineering work is to harden freshness, execute partner handoff, validate architecture choices, and promote only what passes gates.

**Current state and future strategy:**
- Full-grid same-day publication with structured bulletin content is current
- Benchmark packaging
- Admin proof refresh before each customer-send reuse
- Generate and send the v3 handoff packet without synthetic rows
- Run `run_himalayan_partner_package_triage` only after real SASE/DGRE evidence arrives
- Schema and PostGIS migration decision
- Offline-batch execution proof
- TreeSHAP, SAR, and Whitebox runout validation gates

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Validation Protocol](../../source/Scientist_validation_protocol_v0.md), [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md)
