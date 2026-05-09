# Avalanche Insight Hub — Technical Architecture Transcript

## T-1 — Architecture Proof Boundary

_Architecture addendum_

The deployed architecture proves a live public route, a live admin route, same-day full-grid cell publication, and a hosted authenticated admin observability view. Scientist validation and operational qualification remain the next hardening items before stronger operational claims.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- Hosted `/` and `/admin` are live

- Public proof: same-day `20x20` / `72h` full-grid cell batch from `2026-05-08`

- Hosted authenticated admin smoke succeeded on May 8, 2026

- Metadata and preview assets use Avalanche Insight Hub branding

Evidence level:
`Hosted production` plus `Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-2 — Current Platform Layers

_Architecture addendum_

The current platform separates presentation, storage, artifact delivery, batch compute, machine learning, governance, remote compute, and offline reliability.

Evidence lanes: Technical evidence

Current state and future strategy

- Interface: React, Vite, Leaflet, Recharts

- Data and storage: Supabase, Postgres, Storage, Auth

- Artifact delivery: manifests, hourly grids, runout overlays

- Batch compute: Python jobs

- Governance: model status, benchmark, release gates

Evidence level:
`Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-3 — Interface Layer

_Architecture addendum_

React and Vite form the presentation layer. The browser renders the public workspace and admin route while heavy avalanche science stays outside the browser.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- `/` public forecast workspace

- `/admin` operator observability lane

- Stateful route rendering

- Map, bulletin, timeline, share, export, report controls

Evidence level:
`Repo/admin verified` plus `Hosted production`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-4 — Supabase Data And Storage Layer

_Architecture addendum_

Supabase is the system of record for structured records, authentication, storage references, and operator-access surfaces.

Evidence lanes: Technical evidence

Current state and future strategy

- Postgres structured records

- Supabase authentication

- Supabase Storage artifact references

- Edge Functions for selected server-side tasks

- Row-Level Security for access boundaries

Evidence level:
`Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-5 — Forecast Publication And Artifact Hydration

_Architecture addendum_

The public route hydrates prepared forecast artifacts. Freshness state is part of the product contract.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- Forecast run metadata

- Artifact manifest

- Hourly grid payloads

- Optional runout overlay payloads

- Browser-side loading and decompression

Evidence level:
`Hosted production` plus `Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-6 — Offline Batch Compute Split

_Architecture addendum_

The core architectural principle is to keep heavy mathematical work outside the public route and outside thin serverless request paths.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Current: scheduled/operator-triggered Python jobs

- Future direction: GitHub Actions or lightweight VPS

- Heavy work: feature selection, rare-event balancing, inference, runout physics

- Public route: presentation and review

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-7 — Active Scorer And Explanation Layer

_Architecture addendum_

The active model path is a Random Forest baseline. The current active full-grid run uses heuristic explanation fallback; TreeSHAP refresh remains a hardening gate. Candidate deep-learning paths remain gated.

Evidence lanes: Technical evidence

Current state and future strategy

- Active: `surrogate_rf_v1`

- Current run explanation: `heuristic_fallback`

- TreeSHAP: implemented path, not stronger proof for the current active run

- Supporting training concepts: KMeansSMOTE, Recursive Feature Elimination, calibration

- Candidate: MTS-LSTM, gated

Evidence level:
`Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-8 — Admin Governance Lane

_Architecture addendum_

The admin lane exposes the information needed to keep model claims bounded: source health, provenance, model status, stability, benchmarks, jobs, reports, evaluation, and publication controls.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- Source health

- Decision provenance

- Model status

- Stability and benchmark summaries

- Publication controls

Evidence level:
`Hosted production` plus `Repo/admin verified`

Hosted route proof

---

## T-9 — Offline Field Reporting

_Architecture addendum_

The platform includes offline report queueing and replay. It is implemented capability, but field reliability still needs deployment-specific smoke testing.

Evidence lanes: Technical evidence

Current state and future strategy

- Progressive Web App pattern

- Service Worker registration

- IndexedDB local queue

- Startup and reconnect flush

- Field proof remains deployment-specific

Evidence level:
`Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-10 — Modal.com Candidate Compute Plane

_Architecture addendum_

Modal.com supports heavier candidate workflows away from the public route. It is separate from the proof behind current public forecast scoring.

Evidence lanes: Technical evidence

Current state and future strategy

- MTS-LSTM training candidate

- SAR segmentation candidate

- Persistent artifact volumes

- Authenticated worker endpoints

- Current public scorer remains Random Forest baseline

Evidence level:
`Repo/admin verified`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-11 — Future Offline-Batch Paradigm

_Architecture addendum_

The PRD direction keeps React and Supabase as presentation and storage layers while moving heavier math into offline batch processing.

Evidence lanes: Research agenda

Current state and future strategy

- Presentation: React, Leaflet, 3D views

- Storage: Supabase and Postgres

- Compute: GitHub Actions or lightweight VPS

- Heavy math: feature selection, KMeansSMOTE, inference, runout physics

Evidence level:
`Artifact/doc proof only`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-12 — Proposed Data Contract

_Architecture addendum_

The proposed architecture simplifies future publication around topographic enrichment, <code>forecast_grids</code>, JSONB payloads, and optional PostGIS support.

Evidence lanes: Research agenda

Current state and future strategy

- `avalanche_events`

- topographic enrichment: elevation, slope angle, aspect

- `forecast_grids`

- `grid_geojson`

- `runout_polygons`

- PostGIS as proposed geospatial extension

Evidence level:
`Artifact/doc proof only`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-13 — Proposed ML And Runout Pipeline

_Architecture addendum_

The proposed future pipeline combines rare-event balancing, feature selection, calibrated Random Forest inference, uncertainty bounds, and memory-safe Alpha-Beta runout processing.

Evidence lanes: Research agenda

Current state and future strategy

- KMeansSMOTE for rare events

- Recursive Feature Elimination for feature discipline

- Calibrated Random Forest

- Tree variance for uncertainty bounds

- WhiteboxTools Alpha-Beta runout with DEM cropping remains a validation path

- Current active runout proof is analytical Alpha-Beta fallback; Whitebox smoke passed separately

Evidence level:
`Artifact/doc proof only`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-14 — Current, Partial, Candidate, Proposed

_Architecture addendum_

The technical deck should prevent architecture overclaim by classifying every major system path.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- Current: hosted public route, admin route, RF baseline, artifact hydration

- Partial/current: offline report queueing

- Candidate/gated: MTS-LSTM, SAR, TreeSHAP refresh for the active full-grid run

- Proposed/validation: GitHub Actions/VPS batch compute, PostGIS terrain enrichment, WhiteboxTools runout

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## T-15 — Architecture Gates And Next Workstreams

_Architecture addendum_

The next engineering work is to harden freshness, validate architecture choices, and promote only what passes gates.

Evidence lanes: Research agenda

Current state and future strategy

- Full-grid same-day publication with structured bulletin content is current

- Benchmark packaging

- Admin proof refresh before each customer-send reuse

- Schema and PostGIS migration decision

- Offline-batch execution proof

- TreeSHAP, SAR, and Whitebox runout validation gates

Evidence level:
`Artifact/doc proof only`

Architecture interpretation

Current
Deployed platform
Public route, admin route, Supabase records, and artifact hydration stay separate from future claims.

Gated
Candidate paths
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future
Validation program
Scientist review decides which technical paths become stronger operational claims.
