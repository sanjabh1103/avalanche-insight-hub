# Avalanche Insight Hub — Technology Glossary Transcript

## D5-1 — Technology Terms Contract

_Technical field guide_

This deck explains the terminology behind the MVP while keeping each term tied to its current status.

Evidence lanes: Research agenda

Current state and future strategy

- Terms are grouped by platform layer and proof status

- Current terms describe live or repo/admin verified behavior

- Candidate terms describe gated implementation paths

- Future terms describe architecture direction, not completed product

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-2 — Published Forecast Terms

_Technical field guide_

The core product terminology is about published forecast artifacts, not live recomputation in the browser.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- `Forecast Run`: packaged publication event with metadata and freshness

- `Forecast Grid`: spatial cells carrying danger, uncertainty, explanation, and optional runout references

- `Artifact Manifest`: small index describing larger forecast payloads

- `Batch-First Delivery`: heavy work runs upstream before the user opens the website

Evidence level:
`Hosted production` plus `Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-3 — Public Platform Terms

_Technical field guide_

The website is the presentation and review layer over prepared forecast data.

Evidence lanes: Live platform; Technical evidence

Current state and future strategy

- `React`: reusable interface components

- `Vite`: production frontend build tool

- `Leaflet`: map interaction layer

- `Recharts`: dashboard and admin charting layer

- `Single-Page Application`: routed app experience without full page reloads

Evidence level:
`Repo/admin verified` plus `Hosted production`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-4 — Supabase And Access-Control Terms

_Technical field guide_

Supabase provides storage, structured records, authentication, and backend function surfaces.

Evidence lanes: Technical evidence

Current state and future strategy

- `Supabase`: Postgres, Auth, Storage, and Edge Functions

- `Postgres`: structured records for runs, reports, jobs, and model status

- `Row-Level Security`: database access boundaries

- `Edge Function`: lightweight server-side task surface

- `Admin Route`: restricted observability and review lane

Evidence level:
`Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-5 — Offline And Field Workflow Terms

_Technical field guide_

The offline field-report path supports capture and replay, but field reliability still needs deployment-specific testing.

Evidence lanes: Technical evidence

Current state and future strategy

- `PWA`: installable/offline-capable web pattern

- `Service Worker`: browser background process for offline behavior

- `IndexedDB`: local structured browser storage

- `Background Sync`: deferred replay pattern when connectivity returns

- Future strategy: field-device smoke tests and operator review workflow

Evidence level:
`Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-6 — Avalanche Communication Terms

_Technical field guide_

Forecast communication terms must remain bounded because the MVP is decision support, not an official warning authority.

Evidence lanes: Live platform; Research agenda

Current state and future strategy

- `Forecast Bulletin`: structured danger, problem, uncertainty, and terrain summary

- `EAWS-style experimental`: familiar structure without authority-grade equivalence

- `APT`: avalanche-prone terrain used to avoid false low-risk semantics

- `Masked Terrain`: out-of-scope terrain displayed separately from low danger

- `Uncertainty Cue`: visible signal that confidence is limited

Evidence level:
`Hosted production` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-7 — Active Model Terms

_Technical field guide_

The live MVP is anchored on an explainable Random Forest baseline and rare-event-aware training discipline.

Evidence lanes: Technical evidence

Current state and future strategy

- `Random Forest`: current active baseline model family

- `Calibration`: making predicted probabilities match observed frequency

- `Brier Score`: probability calibration metric

- `PSS`: rare-event discrimination metric

- `KMeansSMOTE` and `Recursive Feature Elimination`: training and feature-discipline concepts

Evidence level:
`Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-8 — Explainability Terms

_Technical field guide_

Explainability is implemented as a path and review layer, but the current active full-grid artifact still reports heuristic fallback.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- `SHAP`: family of feature-attribution methods

- `TreeSHAP`: SHAP method specialized for tree models

- Current active artifact: `heuristic_fallback`

- Current status: implemented path, not stronger active-run proof

- Future strategy: active artifact refresh with computed or cached TreeSHAP values

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-9 — Candidate Sequence-Model Terms

_Technical field guide_

MTS-LSTM is a future model strategy and candidate implementation path, not the current public scorer.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- `LSTM`: sequence neural network for temporal patterns

- `MTS-LSTM`: multi-time-scale sequence model candidate

- Current status: repo/admin verified candidate

- Promotion rule: benchmark, stability, and release gates must pass first

- Future strategy: shadow runs before any public scorer change

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-10 — SAR And Remote-Sensing Terms

_Technical field guide_

Remote sensing is important to the strategy, but SAR remains a candidate evidence path.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- `SAR`: Synthetic Aperture Radar, weather-resistant satellite imaging

- `Sentinel-1`: SAR mission context

- `U-Net`: segmentation model family for masks and pixel regions

- Current status: shadow/candidate workflows and coverage caveats

- Future strategy: label coverage, revisit handling, shadow/layover review, and qualification artifacts

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-11 — Modal.com And GPU Terms

_Technical field guide_

Modal.com is the off-path compute plane for candidate workflows, not the current public scorer claim.

Evidence lanes: Technical evidence

Current state and future strategy

- `Modal.com`: remote worker and artifact-volume platform

- `GPU`: parallel hardware used for heavy training or segmentation workloads

- Current Modal use: SAR training/segmentation and MTS-LSTM training candidates

- Current public scorer: Random Forest baseline outside Modal.com

- Future strategy: GPU-backed batch inference only if cost and performance evidence justify it

Evidence level:
`Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-12 — Terrain, Runout, And Geospatial Terms

_Technical field guide_

Terrain and runout terms should be framed as consequence-aware review and validation work, not completed operational authority.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- `DEM`: digital elevation model for slope, elevation, and aspect

- `Alpha-Beta Runout`: terrain-based runout estimation method

- `WhiteboxTools`: geospatial toolkit for future runout validation

- `PostGIS`: proposed geospatial database extension

- Current state: analytical Alpha-Beta fallback; Whitebox smoke proof separate from active public runout proof

Evidence level:
`Repo/admin verified` plus `Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-13 — Data Lineage And Synthetic Boundary Terms

_Technical field guide_

The customer-safe strategy is to preserve data lineage so synthetic or proof-mode data can be removed quickly without contaminating scientist validation.

Evidence lanes: Technical evidence; Research agenda

Current state and future strategy

- `Data Lineage`: records where a training or publication input came from

- `Synthetic Inputs Present`: flag that must remain visible when synthetic support exists

- Current active proof: non-synthetic full-grid technical publication

- Future strategy: strict separation of technical proof, training augmentation, and customer-visible validation data

- Cleanup rule: isolate synthetic seeds, weights, manifests, and claims behind explicit lineage fields

Evidence level:
`Artifact/doc proof only` plus `Repo/admin verified`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-14 — Standards And Interoperability Terms

_Technical field guide_

Standards are part of the future architecture discussion, not current operational certification.

Evidence lanes: Research agenda

Current state and future strategy

- `COG`: Cloud Optimized GeoTIFF for efficient future raster access

- `OGC APIs`: future geospatial interoperability direction

- `CAP`: Common Alerting Protocol for future alert integration discussions

- Current state: not an official warning-service or standards-certified alerting system

- Future strategy: standards mapping after scientist and operator validation

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.

---

## D5-15 — Proof Buckets And Release Gates

_Technical field guide_

The proof-bucket vocabulary is the control system for customer-safe technical discussions.

Evidence lanes: Research agenda

Current state and future strategy

- `Hosted production`: visible on the deployed website

- `Repo/admin verified`: inspectable in source, artifacts, tests, or admin

- `Artifact/doc proof only`: documented or proposed, not public proof

- `Candidate/gated`: implemented path blocked from promotion until evidence passes

- Future strategy: move terms upward only when artifacts and scientist review support promotion

Evidence level:
`Artifact/doc proof only`

Interpretation

Current state
Evidence now
Use only hosted, admin, repo, and artifact proof that exists today.

Gated
Promotion rules
MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.

Future strategy
Validation program
Scientist review decides which technical paths become stronger operational claims.
