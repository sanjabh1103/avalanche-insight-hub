# Deck 5 Final: Technology Glossary And Future Strategy

Updated: May 24, 2026

## Deck Design System

- Theme: Technical Field Guide
- Backgrounds: alternate only between `Light Paper #F8F6F0` and `Deep Slate #1E2A31`
- Primary accent: `Signal Teal #1C7C74`
- Secondary accents: `Risk Amber #C9862B`, `Blueprint Ink #26373A`, `Cloud White #FFFFFF`
- Typography: IBM Plex Sans for body, Space Grotesk for headings
- Customer-facing tone: plain-English technical explanation with current/candidate/future status labels.
- Asset use: use diagrams and compact tables before screenshots.

## Slide 1: Technology Terms Contract

**Background:** Deep Slate
**Customer message:**
This deck explains the terminology behind MVP V2 while keeping each term tied to its current status and claim boundary.

**Current state and future strategy:**
- Terms are grouped by platform layer and proof status
- Current terms describe live or repo/admin verified behavior
- Candidate terms describe gated implementation paths
- Research-only terms describe Swiss RAvaFcast and Himalayan partner-evidence work
- Future terms describe architecture direction, not completed product

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Claim Ledger](../../source/Scientist_claim_ledger.md)

---

## Slide 2: Published Forecast Terms

**Background:** Light Paper
**Customer message:**
The core product terminology is about published forecast artifacts, not live recomputation in the browser.

**Current state and future strategy:**
- `Forecast Run`: packaged publication event with metadata and freshness
- `Forecast Grid`: spatial cells carrying danger, uncertainty, explanation, and optional runout references
- `Artifact Manifest`: small index describing larger forecast payloads
- `Batch-First Delivery`: heavy work runs upstream before the user opens the website

**Evidence level:** `Hosted production` plus `Repo/admin verified`
**Supporting sources:** [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Current Architecture](../../source/Technical_Architecture_Current_Platform.md)

---

## Slide 3: Public Platform Terms

**Background:** Light Paper
**Customer message:**
The website is the presentation and review layer over prepared forecast data.

**Current state and future strategy:**
- `React`: reusable interface components
- `Vite`: production frontend build tool
- `Leaflet`: map interaction layer
- `Recharts`: dashboard and admin charting layer
- `Single-Page Application`: routed app experience without full page reloads

**Evidence level:** `Repo/admin verified` plus `Hosted production`
**Supporting sources:** [Current Architecture](../../source/Technical_Architecture_Current_Platform.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md)

---

## Slide 4: Supabase And Access-Control Terms

**Background:** Deep Slate
**Customer message:**
Supabase provides storage, structured records, authentication, and backend function surfaces.

**Current state and future strategy:**
- `Supabase`: Postgres, Auth, Storage, and Edge Functions
- `Postgres`: structured records for runs, reports, jobs, and model status
- `Row-Level Security`: database access boundaries
- `Edge Function`: lightweight server-side task surface
- `Admin Route`: restricted observability and review lane

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Current Architecture](../../source/Technical_Architecture_Current_Platform.md)

---

## Slide 5: Offline And Field Workflow Terms

**Background:** Light Paper
**Customer message:**
The offline field-report path supports capture and replay, but field reliability still needs deployment-specific testing.

**Current state and future strategy:**
- `PWA`: installable/offline-capable web pattern
- `Service Worker`: browser background process for offline behavior
- `IndexedDB`: local structured browser storage
- `Background Sync`: deferred replay pattern when connectivity returns
- Future strategy: field-device smoke tests and operator review workflow

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Current Architecture](../../source/Technical_Architecture_Current_Platform.md)

---

## Slide 6: Avalanche Communication Terms

**Background:** Light Paper
**Customer message:**
Forecast communication terms must remain bounded because the MVP is decision support, not a statutory warning service.

**Current state and future strategy:**
- `Forecast Bulletin`: structured danger, problem, uncertainty, and terrain summary
- `EAWS-style experimental`: familiar structure without authority-grade equivalence
- `APT`: avalanche-prone terrain used to avoid false low-risk semantics
- `Masked Terrain`: out-of-scope terrain displayed separately from low danger
- `Uncertainty Cue`: visible signal that confidence is limited

**Evidence level:** `Hosted production` plus `Artifact/doc proof only`
**Supporting sources:** [Top 20 Features](../../source/Top20_features.md), [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md)

---

## Slide 7: Active Model Terms

**Background:** Deep Slate
**Customer message:**
The live MVP is anchored on an explainable Random Forest baseline and rare-event-aware training discipline. Swiss RF4 reproduction is a separate research lane.

**Current state and future strategy:**
- `Random Forest`: current active baseline model family
- `Calibration`: making predicted probabilities match observed frequency
- `Brier Score`: probability calibration metric
- `PSS`: rare-event discrimination metric
- `KMeansSMOTE` and `Recursive Feature Elimination`: training and feature-discipline concepts
- `RF4 reproduction`: research-only Swiss danger-level signal, not paper parity and not Himalayan proof

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Current Architecture](../../source/Technical_Architecture_Current_Platform.md), [Benchmark Pack](../../source/Scientist_benchmark_pack_v0.md)

---

## Slide 8: Explainability Terms

**Background:** Light Paper
**Customer message:**
Explainability is implemented as a path and review layer, but the current active full-grid artifact still reports heuristic fallback.

**Current state and future strategy:**
- `SHAP`: family of feature-attribution methods
- `TreeSHAP`: SHAP method specialized for tree models
- Current active artifact: `heuristic_fallback`
- Current status: implemented path, not stronger active-run proof
- Future strategy: active artifact refresh with computed or cached TreeSHAP values

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md), [Claim Ledger](../../source/Scientist_claim_ledger.md)

---

## Slide 9: Candidate Sequence-Model Terms

**Background:** Light Paper
**Customer message:**
MTS-LSTM is a future model strategy and candidate implementation path, not the current public scorer.

**Current state and future strategy:**
- `LSTM`: sequence neural network for temporal patterns
- `MTS-LSTM`: multi-time-scale sequence model candidate
- Current status: repo/admin verified candidate
- Promotion rule: benchmark, stability, and release gates must pass first
- Future strategy: shadow runs before any public scorer change

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md), [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md)

---

## Slide 10: SAR And Remote-Sensing Terms

**Background:** Deep Slate
**Customer message:**
Remote sensing is important to the strategy, but SAR remains a candidate evidence path.

**Current state and future strategy:**
- `SAR`: Synthetic Aperture Radar, weather-resistant satellite imaging
- `Sentinel-1`: SAR mission context
- `U-Net`: segmentation model family for masks and pixel regions
- Current status: shadow/candidate workflows and coverage caveats
- Current boundary: shadow-gated, no SAR production claim
- Future strategy: label coverage, revisit handling, shadow/layover review, and qualification artifacts

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md), [Research Appendix](../../source/Demo_research_appendix.md)

---

## Slide 11: Modal.com And GPU Terms

**Background:** Light Paper
**Customer message:**
Modal.com is the off-path compute plane for candidate workflows, not the current public scorer claim.

**Current state and future strategy:**
- `Modal.com`: remote worker and artifact-volume platform
- `GPU`: parallel hardware used for heavy training or segmentation workloads
- Current Modal use: SAR training/segmentation and MTS-LSTM training candidates
- Current public scorer: Random Forest baseline outside Modal.com
- Future strategy: GPU-backed batch inference only if cost and performance evidence justify it

**Evidence level:** `Repo/admin verified`
**Supporting sources:** [Modal/GPU Inventory](../../source/Modal_GPU_ML_Inventory.md), [Modal/GPU Evidence Table](../07_Modal_GPU_Evidence_Table.md)

---

## Slide 12: Terrain, Runout, And Geospatial Terms

**Background:** Light Paper
**Customer message:**
Terrain and runout terms should be framed as consequence-aware review and validation work, not completed operational authority.

**Current state and future strategy:**
- `DEM`: digital elevation model for slope, elevation, and aspect
- `Alpha-Beta Runout`: terrain-based runout estimation method
- `WhiteboxTools`: geospatial toolkit for future runout validation
- `PostGIS`: proposed geospatial database extension
- Current state: analytical Alpha-Beta fallback; Whitebox smoke proof separate from active public runout proof

**Evidence level:** `Repo/admin verified` plus `Artifact/doc proof only`
**Supporting sources:** [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md)

---

## Slide 13: Data Lineage And Synthetic Boundary Terms

**Background:** Deep Slate
**Customer message:**
The customer-safe strategy is to preserve data lineage so synthetic, proof-mode, or partner-intake data cannot contaminate scientist validation.

**Current state and future strategy:**
- `Data Lineage`: records where a training or publication input came from
- `source_ref`: SHA-256-qualified pointer from each partner evidence row to a reviewed source package
- `partner_source_manifest`: partner-declared source owner, license, review, date range, and evidence-package reference
- `triage_artifact_manifest`: generated inventory of output files, sizes, hashes, and purposes
- Current active proof: non-synthetic full-grid technical publication; synthetic support remains visibly flagged where present
- Future strategy: strict separation of technical proof, partner intake, training eligibility, and customer-visible validation data
- Cleanup rule: isolate synthetic seeds, weights, manifests, and claims behind explicit lineage fields

**Evidence level:** `Artifact/doc proof only` plus `Repo/admin verified`
**Supporting sources:** [Proof Manifest](../06_Proof_Status_And_Screenshot_Manifest.md), [Claim Ledger](../../source/Scientist_claim_ledger.md), [Partner Schema Mapping](../../../EnviDat_to_Partner_Schema_Mapping.md)

---

## Slide 14: Standards And Interoperability Terms

**Background:** Light Paper
**Customer message:**
Standards are part of the future architecture discussion, not current operational certification. MVP V2 adds evidence-governance vocabulary for partner data.

**Current state and future strategy:**
- `COG`: Cloud Optimized GeoTIFF for efficient future raster access
- `OGC APIs`: future geospatial interoperability direction
- `CAP`: Common Alerting Protocol for future alert integration discussions
- `D_forecast`: raw or official forecast label that may contain human forecast noise
- `D_tidy`: quality-controlled danger label backed by nowcast, observer, event, or reanalysis evidence
- `GPxyz`: Gaussian-process interpolation using latitude, longitude, and elevation in the Swiss RAvaFcast setting
- `Refined discretization`: expected-danger thresholding learned only from training or out-of-bag distributions
- Current state: not a statutory warning-service or standards-certified alerting system
- Future strategy: standards mapping after scientist and operator validation

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Technical Glossary](../../source/Technical_Glossary_And_Acronyms.md), [Future Core Model](../../source/Technical_Architecture_Future_Core_Model.md), [Swiss Reproduction Lane](../../../MVP%20V2/Swiss_Reproduction_Lane.md)

---

## Slide 15: Proof Buckets And Release Gates

**Background:** Deep Slate
**Customer message:**
The proof-bucket vocabulary is the control system for customer-safe technical discussions.

**Current state and future strategy:**
- `Hosted production`: visible on the deployed website
- `Repo/admin verified`: inspectable in source, artifacts, tests, or admin
- `Artifact/doc proof only`: documented or proposed, not public proof
- `Candidate/gated`: implemented path blocked from promotion until evidence passes
- `Research-only`: Swiss RAvaFcast and Himalayan partner intake artifacts that must keep `production_scoring_allowed=false`
- `Claims blocked`: `himalayan_accuracy_claim_allowed=false` until local evidence, holdout, scientist review, and release gates pass
- Future strategy: move terms upward only when artifacts and scientist review support promotion

**Evidence level:** `Artifact/doc proof only`
**Supporting sources:** [Slide Evidence Map](../05_Slide_Evidence_Map.md), [Proof Manifest](../06_Proof_Status_And_Screenshot_Manifest.md)
