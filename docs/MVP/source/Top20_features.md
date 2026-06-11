# Top 20 Features And Current Technical Architecture - Avalanche Insight Hub

Updated: May 22, 2026

This file is the broad MVP-plus feature and technology source map. It is not a pure public-demo list. It now reflects the current repo after the scientist co-working, European shadow, Modal/GPU, daily verification, and governance updates.

Use this file when preparing technical discussion with scientists, directors, engineers, or partners. For hand-holding scientist review instructions, use `docs/learning/top20.md`.

## Proof Boundary

| Boundary | Current wording to use |
|---|---|
| Public app | A batch-first avalanche decision-support website that serves published forecast artifacts. |
| Current public scorer | `surrogate_rf_v1`, an explainable Random Forest baseline. |
| Scientist workflow | Role-gated review and daily verification tools for scientist co-working. |
| Modal.com / GPU | Off-path compute for SAR, candidate MTS-LSTM, release evaluation, and artifact reruns. |
| European data | Shadow-validation and benchmark evidence, not proof of Himalayan accuracy. |
| Synthetic demo data | Demo and smoke-test data only; never training-eligible or production-eligible. |
| Official warning status | Not an official avalanche warning authority and not a field-safety instruction. |

## Evidence Baseline For This Refresh

| Source of truth | Current repo evidence | Caveat |
|---|---|---|
| Routes | `src/App.tsx` defines `/`, `/admin`, `/scientist`, and `/scientist/daily-verification`. | Hosted browser proof should be rerun before a fresh external meeting. |
| Public forecast workspace | `src/pages/Index.tsx`, forecast artifact loaders, map controls, export/share/report components. | Current artifact freshness must be checked on the deployed site before citing a live run id. |
| Admin lane | `src/pages/AdminPage.tsx`, `src/components/AdminDashboard.tsx`, `src/components/AdminAccessGate.tsx`. | Admin remains admin-only; do not widen it to scientist users. |
| Scientist lane | `src/pages/ScientistPage.tsx`, `src/components/RoleAccessGate.tsx`, `src/components/ScientistValidationWorkbench.tsx`. | Scientist accounts need Supabase `app_metadata.roles=["scientist"]`. |
| Daily verification | `src/pages/ScientistDailyVerificationPage.tsx`, `src/lib/scientistValidation.ts`. | Paired comparison evidence only; no automatic model promotion. |
| Database migrations | `supabase/migrations/20260520120000_scientist_validation_workbench.sql`, `20260521120000_scientist_validation_governance_hardening.sql`, `20260521143000_scientist_daily_verification_and_action_closure.sql`. | Apply in order; the hardening migration is required before exposing the workflow. |
| Modal worker | `backend/modal_worker_app.py`, `docs/Modal_GPU_Scientist_Coworking_Operating_Note.md`, `docs/MVP/source/Modal_GPU_ML_Inventory.md`. | Modal is off-path compute, not the active public forecast engine. |
| European shadow pack | `docs/superpowers/plans/Euro_plans/README.md`. | Use as SAR and methodology evidence only, not Himalayan validation proof. |

## Current Technology Stack

| Layer | Technology in repo | Role | Boundary / caveat |
|---|---|---|---|
| Frontend framework | React 18, TypeScript 5.8, Vite 7 | Single-page web app, routed workspaces, production build. | UI quality does not equal scientific validation. |
| Routing and state | React Router 6, TanStack React Query 5 | Public, admin, scientist, and daily-verification routes; async data state. | Route access still depends on Supabase auth and RLS. |
| UI system | Tailwind CSS, Radix UI, shadcn-style components, lucide-react, Framer Motion | Accessible controls, panels, cards, dialogs, icons, toasts, motion. | Keep scientist pages work-focused, not marketing styled. |
| Mapping | Leaflet, React-Leaflet, Turf, leaflet.heat, d3-geo | Forecast grid map, overlays, events, geospatial interaction. | Cell-level display is a review surface, not slope-specific safety advice. |
| 3D / visual inspection | Three.js, `@react-three/fiber`, `@react-three/drei` | Voxel-style terrain and neighborhood inspection. | Visualization helps review; it is not DEM or field validation by itself. |
| Charts and analytics | Recharts plus local matrix summaries | Admin metrics, daily-verification analytics, agreement summaries. | Metrics need enough paired records before strong interpretation. |
| Auth and database | Supabase JS 2, Supabase Auth, Postgres/PostGIS, RLS policies | User roles, forecast records, review records, daily verification, geospatial points/geometry, admin tables. | Generated Supabase TS types may lag new scientist tables; check before strict typing claims. |
| Database extensions | PostGIS, pg_cron, pg_net, pgcrypto | Geospatial storage/queries, scheduled jobs, HTTP job calls, UUID/security helpers. | Extension availability must be verified per Supabase project. |
| File and artifact storage | Supabase Storage, artifact manifests, Modal volumes | Forecast manifests, hourly grids, model artifacts, SAR masks, checkpoints. | Object references must be reproducible before promotion claims. |
| Edge backend | Supabase Edge Functions on Deno | Forecast lookup, job trigger, ingest, evaluation, labeling, enrichment. | Edge Functions orchestrate and query; heavy ML belongs off-path. |
| Python ML backend | Python, pandas, NumPy, scikit-learn 1.8, imbalanced-learn, joblib, SHAP 0.51 | RF training/inference, balancing, feature selection, calibration, explanations. | Current active public scorer is RF, not promoted MTS-LSTM. |
| Deep learning | PyTorch 2.5+, segmentation-models-pytorch, timm, einops | SAR U-Net families and MTS-LSTM candidate paths. | Candidate/shadow only until gates pass. |
| Geospatial backend | rasterio, pyshp, SciPy, Earth Engine API, WhiteboxTools | DEM, terrain, raster, snow cover, runout and geospatial workflows. | Whitebox/runout and snowpack proxies require artifact-specific proof. |
| Remote compute | Modal.com, FastAPI worker, Modal volumes, T4 GPU functions | SAR segmentation/training, MTS-LSTM training, release evaluation, batch reruns. | Off-path validation compute; not continuous public serving. |
| Deployment | Netlify, Node 20 build, SPA redirect to `index.html` | Frontend production hosting and route fallback. | Live smoke must be rerun after each deployment. |
| PWA/offline | Vite PWA, Workbox, service worker, IndexedDB report queue | Field-report offline queue and reconnect replay. | Requires explicit device/browser smoke for field pilot. |
| Verification | Vitest, React Testing Library, Playwright, pytest | Component, unit, backend, and browser smoke tests. | Do not claim passing status without current command evidence. |

## Architecture Layers

| Layer | What happens | Primary files / systems | Scientist-facing meaning |
|---|---|---|---|
| 1. Browser interface | User opens public, admin, or scientist route. | `src/main.tsx`, `src/App.tsx`, `src/pages/*`. | Scientists can review public forecast output and enter structured validation evidence. |
| 2. Forecast artifact display | Public app loads published forecast metadata and per-hour grid artifacts. | `src/lib/forecastArtifacts.ts`, Supabase tables/storage. | Heavy compute is not run by the browser during review. |
| 3. Review and evidence surface | User inspects cells, events, field reports, uncertainty, explanations, SAR caveats, and snowpack proxies. | `CellEvidenceDrawer`, `RiskDashboard`, `ForecastBulletinBadge`, `SnowpackProxyCard`, map components. | Evidence is shown with caveats so scientists can accept, reject, or request more data. |
| 4. Scientist governance | Scientist creates structured reviews, daily verification rows, and action-ledger items. | `scientist_validation_cases`, `scientist_validation_reviews`, `scientist_validation_actions`, `scientist_daily_verifications`. | Human judgment feeds governed next actions, not automatic retraining. |
| 5. Operator and evaluation lane | Admin monitors jobs, data health, model status, evaluation metrics, and release gates. | `/admin`, `AdminDashboard`, Supabase Edge Functions, Python scripts. | Operators can run and inspect evidence without giving scientists broad admin access. |
| 6. Batch ML and publication | Python generates features, trains/evaluates models, runs inference, and publishes forecast artifacts. | `backend/train_model.py`, `backend/daily_inference.py`, `backend/models/surrogate_rf.py`. | Published forecast packets become the evidence reviewed in the UI. |
| 7. Remote candidate compute | Modal worker runs heavy SAR, candidate MTS-LSTM, and release-evaluation jobs. | `backend/modal_worker_app.py`, Modal volumes, GPU functions. | GPU output returns as shadow evidence for review, not automatic public scoring. |
| 8. Partnership data loop | Partner data, field reports, public-source candidates, and European shadow packs feed validation queues. | case-pack scripts, Euro plans, onboarding/outreach docs. | Real Himalayan validation still requires scientist-confirmed or partner-provided source rows. |

## API And Integration Surfaces

### Browser Routes

| Route | Audience | Access control | Main function |
|---|---|---|---|
| `/` | Public users, scientists, operators | Public route | Published forecast workspace with map, bulletin, time slider, field report, share, export, overlays, and 3D inspection. |
| `/admin` | Operators/admins | `AdminAccessGate`, admin role only | System controls, job triggers, source health, model status, evaluation, governance and scientist workbench visibility. |
| `/scientist` | Scientists and admins | `RoleAccessGate`, `scientist` or `admin` role | Scientist-safe validation queue, structured review, reference attachment, action ledger, sign-off export. |
| `/scientist/daily-verification` | Scientists and admins | `RoleAccessGate`, `scientist` or `admin` role | Paired scientist-vs-model danger/problem comparison, analytics, export. |

### Supabase Edge Functions

| Function endpoint | Triggered by | Current role | Key payload / output |
|---|---|---|---|
| `run-forecast` | Public refresh button / app lookup | Looks up fresh or latest published forecast run/grid for a region. | Input: `regionName` or `regionKey`; output: forecast metadata, freshness, artifact refs. |
| `trigger-job` | Admin dashboard | Orchestrates operator jobs and Modal worker calls when configured. | Input: `type`, `hazard_type`, optional region/artifact settings; output: job status and runtime capability snapshot. |
| `ingest-event` | Field/news/event ingestion | Converts external or user event reports into governed avalanche-event rows. | Input: event text/location/source fields; output: inserted/updated event and compute job record. |
| `field-report-enrichment` | Admin/operator job | Normalizes raw field reports into reviewable event evidence. | Input: report id/context; output: enriched event/report evidence. |
| `ingest-snow-cover` | Scheduled/operator job | Pulls or refreshes snow-cover context. | Input: region/hazard context; output: snow-cover refresh job and records. |
| `recent-activity-refresh` | Scheduled/operator job | Materializes recent event/activity summaries. | Input: region/hazard context; output: activity summary rows. |
| `label-forecast-outcomes` | Admin/operator job | Links forecasts or forecast grids to observed outcomes. | Input: hazard/region/date settings; output: forecast outcome labels. |
| `run-evaluation` | Admin/operator job | Computes evaluation metrics and slices. | Output includes Brier, calibration/ECE-style metrics, PSS and slice summaries where available. |
| `shap-explainer` | Explanation path | Generates/serves explanation narrative where available. | Explanation support only; active artifact may still use heuristic fallback. |
| `promote-report` | Report governance | Promotion/report workflow support. | Must remain governed; no automatic scientific claim promotion. |

### External Data And API Integrations

| Integration | Where used | Purpose | Credential posture | Boundary |
|---|---|---|---|---|
| Supabase REST/Auth/Storage APIs | Browser client, Edge Functions, Python scripts | Main database, authentication, artifact storage, and function invocation surface. | Browser uses publishable/anon key; service-role key must stay server-side or local-only. | RLS and role metadata define who can read/write protected scientist/admin data. |
| Open-Meteo forecast/archive APIs | `backend/common/real_features.py`, `backend/common/snowpack_proxy.py`, UI weather values | Weather and historical weather features for forecast and snowpack proxy context. | No user-facing secret required for current use. | Weather features support the model and proxy context; they do not prove avalanche outcomes. |
| NASA GIBS / Earthdata snow cover | `supabase/functions/ingest-snow-cover`, admin snow-cover job | Snow-cover summary and fallback snow context. | Public metadata endpoint in current function; Earthdata credentials may be needed for deeper SAR/data paths. | Snow cover is context; weak-layer proof still needs scientist/partner data. |
| ASF DAAC Search / Sentinel-1 | `trigger-job`, SAR refresh paths, SAR scripts | Sentinel-1 scene search and SAR candidate evidence. | ASF token or username/password are optional runtime secrets for SAR-enabled mode. | SAR remains shadow/candidate unless release gates pass. |
| Google Gemini API | `backend/news_ingest.py`, `trigger-job`, `ingest-event`, `shap-explainer` | News/event extraction, deposit-zone governance aid, explanation summary fallback. | `GEMINI_API_KEY` is server-side only; usage is tracked in `system_config`. | Gemini output is evidence to govern, not automatic truth or training eligibility. |
| OpenStreetMap / Overpass API | `ImpactOverlays`, `VoxelNeighborhoodModal`, `overpassClient` | Roads, infrastructure, and 3D neighborhood context. | No app secret; client fetch has degraded/rate-limit handling. | OSM coverage varies by region and must not be treated as authoritative asset inventory. |
| Nominatim reverse geocoding | `trigger-job` | Converts lat/lon to coarse place/state/county labels. | No app secret; polite public endpoint use. | Location labels are convenience metadata, not scientific validation. |
| Modal.com worker API | `backend/modal_worker_app.py`, operator scripts | Remote compute, GPU training/segmentation, candidate inference, release evaluation. | Bearer token / Modal secrets; never browser-exposed. | Off-path compute only; no automatic public promotion. |

### Modal.com Worker API

| Endpoint | Method | Compute posture | Purpose | Promotion boundary |
|---|---|---|---|---|
| `/sar-segment` | `POST` | GPU-backed `T4` path when deployed with CUDA | SAR segmentation and held-out prediction masks. | Shadow evidence only unless SAR release gates pass. |
| `/train-sar-unet` | `POST` | GPU-backed `T4`, long timeout | Train candidate SAR U-Net checkpoint. | Candidate checkpoint only. |
| `/train-sar-unet/result/{call_id}` | `GET` | Modal async result lookup | Poll SAR training job result. | Job completion is not production promotion. |
| `/train-mtslstm` | `POST` | GPU-backed `T4`, long timeout | Train candidate MTS-LSTM sequence model. | Candidate evidence only. |
| `/train-mtslstm/result/{call_id}` | `GET` | Modal async result lookup | Poll MTS-LSTM training result. | Requires benchmark and scientist gates before use. |
| `/infer-mtslstm` | `POST` | Modal-backed CPU/memory-sized path today | Remote batch inference from candidate artifacts. | Not the active public scorer. |
| `/infer-mtslstm/result/{call_id}` | `GET` | Modal async result lookup | Poll candidate inference result. | No public scoring change by itself. |
| `/evaluate-release` | `POST` | Modal worker evaluation path | Held-out release evaluation and gate evidence. | Evaluation evidence only; no automatic release approval. |

### Core Supabase Tables And Views

| Data surface | Role |
|---|---|
| `forecast_runs`, `forecast_active_runs` | Published forecast run metadata and active run lookup. |
| `forecast_grids` | Grid-level forecast metadata and compatibility path. |
| `forecast_outcomes` | Outcome labels used to compare forecasts with observed events. |
| `field_reports` | User or scientist field reports before/after enrichment and governance. |
| `avalanche_events` / event tables | Structured event evidence from field/news/source ingestion. |
| `model_status` | Current scorer, candidate state, gates, benchmark and evidence summaries. |
| `evaluation_runs`, `evaluation_metrics` | Evaluation jobs and metric slices. |
| `compute_jobs` | Job queue and operator-run history. |
| `system_config` | Operational settings, Gemini usage accounting, runtime flags. |
| `scientist_validation_cases` | Review cases for weak-layer, runout, false positive/negative, masking, SAR, and model gates. |
| `scientist_validation_reviews` | Scientist verdicts with structured EAWS/problem, label, model-error, evidence, and confidence fields. |
| `scientist_validation_actions` | Non-automatic action ledger for claim blocks/downgrades, data/label remediation, benchmark slices, evidence requests, and reviewer disagreement. |
| `scientist_daily_verifications` | Paired scientist-vs-model danger/problem rows for daily verification analytics. |

## Model, GPU, And Accuracy Architecture

| Capability | Current implementation | GPU / Modal use | Current status | Safe wording |
|---|---|---|---|---|
| Random Forest baseline | `backend/models/surrogate_rf.py`, `backend/train_model.py`, `backend/daily_inference.py`. | No GPU and no Modal dependency for current public scorer. | Active baseline. | "The public forecast is anchored on a governed Random Forest baseline." |
| Rare-event handling | KMeansSMOTE, feature selection/RFE, calibration and split-aware evaluation. | CPU path today. | Active training discipline. | "The baseline is designed for rare-event governance, not vanity accuracy." |
| TreeSHAP | `build_tree_shap_explainer`, `compute_tree_shap`, `src/lib/shapLoader.ts`. | CPU path. | Implemented, but active artifacts can use heuristic fallback. | "TreeSHAP is available as an explanation path; check artifact metadata before claiming active SHAP." |
| MTS-LSTM | `backend/lstm_model.py`, `backend/models/mts_lstm.py`, Modal worker training/inference hooks. | Training uses Modal GPU; inference is Modal CPU/memory-sized today. | Candidate/shadow. | "MTS-LSTM is a candidate sequence model and must beat gates before promotion." |
| SAR U-Net | `backend/sar_unet_worker.py`, `backend/sar_unet_training.py`, `backend/models/swinunet_tiny_diff.py`. | Modal GPU for segmentation/training. | Shadow/candidate. | "SAR provides candidate remote-sensing evidence, not promoted public scoring." |
| Release evaluation | `backend/scripts/evaluate_canary_release.py`, `run-evaluation`, `/evaluate-release`. | Modal worker can run heavy release evaluation. | Gate evidence. | "Evaluation informs release decisions; it does not authorize promotion alone." |
| Snowpack proxy | `backend/common/snowpack_proxy.py`, UI snowpack proxy copy. | CPU/geospatial feature path. | Proxy context. | "Snowpack proxy needs scientist and partner snowpack validation before weak-layer claims strengthen." |
| European shadow benchmarks | AvalCD, SnowSlide, SLF/SPOT6-style evidence pack. | Modal may support SAR runs and evaluation. | Shadow-only. | "European evidence improves method discipline but does not prove Himalayan accuracy." |

## Top 20 Feature Map

| # | Feature | What it does | Primary technology / API | Proof level | Maturity (1-5) | Boundary |
|---:|---|---|---|---|---:|---|
| 1 | Published batch forecast workspace | Loads a prepared forecast artifact instead of running heavy compute in the browser. | React route `/`, `run-forecast`, `forecast_runs`, storage manifests. | Live/repo capability | 5 | Current artifact freshness must be checked before each meeting. |
| 2 | Region selector and loading state | Lets users pick a region and see ready/partial/stale/unavailable state. | `RegionSelector`, `run-forecast`, forecast metadata. | Live/repo capability | 5 | Region coverage depends on available published artifacts. |
| 3 | 72-hour time slider / daypart review | Moves through forecast hours and daypart context. | `TimeSlider`, hourly grid artifacts, bulletin metadata. | Live/repo capability | 5 | Time navigation reflects published package quality. |
| 4 | EAWS-style experimental bulletin | Shows danger level, problem, elevation/aspect, peak window, uncertainty. | `forecastBulletins`, `ForecastBulletinBadge`, EAWS-style fields. | Live/repo capability | 5 | Experimental decision-support bulletin only. |
| 5 | Forecast grid cell risk inspection | Shows cell risk, probability, problem, drivers, terrain context. | Leaflet grid, `GridCell`, sidebar components. | Live/repo capability | 5 | Cell output is not slope-specific safety advice. |
| 6 | Masked / unavailable terrain behavior | Withholds normal risk coloring where terrain/snow/public eligibility is not suitable. | APT/public eligibility logic, grid UI. | Live/repo capability | 5 | Masking avoids false low-risk messaging but needs field review. |
| 7 | Risk drivers and explanation fields | Shows dominant driver, explanation mode, fallback labels, and SHAP path. | RF metadata, `shapLoader`, `riskNarratives`. | Repo capability | 4 | Check artifact metadata before claiming active TreeSHAP. |
| 8 | Uncertainty and reduced-confidence signaling | Flags thin evidence, high uncertainty, and reduced confidence. | Forecast metadata, UI badges, uncertainty fields. | Live/repo capability | 5 | Needs scientist calibration by region. |
| 9 | SAR coverage and residual-shadow warnings | Displays SAR support and residual-shadow limitations. | SAR metadata, Modal SAR outputs, admin/model status. | Shadow/repo capability | 3 | SAR remains gated and unpromoted. |
| 10 | Weather and snowpack proxy context | Shows weather summary and snowpack proxy indicators. | Python features, snowpack proxy module, UI cards. | Repo capability | 4 | Proxy context is not validated HIM-STRAT/SNOWPACK proof. |
| 11 | Historical events / field evidence overlay | Adds events and field evidence near forecast context. | `avalancheEvents`, `field_reports`, map overlays. | Repo/live capability | 4 | Event data may be incomplete or uncertain. |
| 12 | Field report submission and offline queue | Captures reports and queues them during weak connectivity. | Field report form, service worker, IndexedDB, Edge ingestion. | Repo/live capability | 4 | Raw reports require governance before training use. |
| 13 | Shareable forecast links | Encodes region, hour, selected cell, and UI state. | `forecastRestore`, React Router query state. | Live/repo capability | 5 | Link quality depends on artifact still being resolvable. |
| 14 | CSV / JSON forecast export | Exports forecast cells, metadata, evidence and uncertainty fields. | `ExportForecast`, browser downloads. | Live/repo capability | 5 | Export reflects loaded artifact fields. |
| 15 | Expert overlays and runout / asset review | Shows roads, infrastructure, runout and impact context. | `ImpactOverlays`, runout artifacts, OSM/geometry data. | Repo/live capability | 4 | Consequence context, not official impact certification. |
| 16 | 3D voxel neighborhood inspection | Opens terrain/cell context in a 3D view. | Three.js, `VoxelNeighborhoodModal`. | Repo capability | 4 | Visualization only; not field validation. |
| 17 | Scientist-safe route | Gives scientists validation tools without admin control. | `/scientist`, `RoleAccessGate`, Supabase Auth roles. | Repo capability | 4 | Requires proper scientist account provisioning. |
| 18 | Structured scientist validation queue | Captures verdict, EAWS problem, label quality, model error, terrain/SAR ambiguity, next evidence, confidence rationale. | `scientistValidation.ts`, review tables, workbench UI. | Repo capability | 4 | Reviews create governed evidence, not automatic promotion. |
| 19 | Daily paired scientist-vs-model verification | Stores scientist vs model danger/problem, outcome and analytics. | `/scientist/daily-verification`, `scientist_daily_verifications`. | Repo capability | 4 | Needs enough real paired rows before strong conclusions. |
| 20 | Modal/GPU and European shadow validation | Runs off-path compute and keeps European evidence as benchmark/candidate discipline. | Modal worker API, Euro plans, SAR scripts, release evaluation. | Shadow/research capability | 3 | Not Himalayan proof and not public scoring authority. |

## Scientist Co-Working And Governance Details

| Mechanism | What exists now | Why it matters |
|---|---|---|
| Role-separated access | `/admin` remains admin-only; `/scientist` accepts scientist/admin roles. | Scientists can work independently without broad operator access. |
| Structured review taxonomy | EAWS problem fields, label quality, model error, terrain/SAR ambiguity, evidence-needed-next, confidence rationale. | Turns expert opinion into reviewable data instead of loose notes only. |
| Two-reviewer governance | Priority-5 cases require two distinct reviewers; disagreement keeps case in review. | Prevents one-person approval of high-risk cases. |
| Action ledger | Reviews create claim, data, label, benchmark, model-gap, evidence, or disagreement actions. | Builds a learning loop without automatic retraining. |
| Reference library | Seven local publication references can be attached to review evidence. | Connects current review to prior research lineage. |
| Daily verification analytics | Agreement rate, danger-level confusion matrix, problem confusion matrix, observed outcome distribution. | Enables model-vs-scientist comparison after enough records exist. |
| Synthetic/demo boundary | Demo rows are explicitly non-training and non-production. | Keeps tests and smoke flows from contaminating scientific evidence. |
| Public-source candidates | Candidate Himalayan rows use `himalayas_real_candidate`, not grounded truth regions. | Prepares meeting review without fabricating validation. |

## Deployment And Runtime Notes

| Area | Current detail |
|---|---|
| Frontend hosting | Netlify builds with `npm run build`, publishes `dist`, and routes all paths to `index.html`. |
| Node target | `netlify.toml` pins `NODE_VERSION = "20"` for production build. |
| Supabase env vars | Browser build requires `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` or `VITE_SUPABASE_PUBLISHABLE_KEY`. |
| Backend secrets | Service-role keys and Modal tokens must stay server-side or local-only; never commit or expose in browser code. |
| Scientist credentials | Demo credentials are written only to ignored `.env.scientist.local` by the provisioning workflow. |
| Modal worker auth | Worker routes expect bearer-token style protection unless explicitly configured for anonymous local testing. |
| Migrations | Scientist validation migrations must be applied in order before claiming live scientist workflow readiness. |

## What This File Intentionally Does Not Claim

- It does not claim Avalanche Insight Hub is an official avalanche warning authority.
- It does not claim the public route is driven by promoted MTS-LSTM, SAR, or Modal GPU inference.
- It does not claim European shadow evidence proves Himalayan prediction accuracy.
- It does not claim synthetic demo data is training-eligible or production-eligible.
- It does not claim TreeSHAP is active for every current forecast artifact; artifact metadata controls that claim.
- It does not claim scientist validation is complete until real scientist verdicts, meeting outcomes, and partner data are recorded.

## Companion Files

| File | Purpose |
|---|---|
| `docs/learning/top20.md` | Step-by-step scientist learning and feature verification guide. |
| `docs/Scientist_Onboarding.md` | Scientist route onboarding and workflow overview. |
| `docs/Scientist_Coworking_Completion_Tracker.md` | Implementation and external-proof status tracker. |
| `docs/SASE_DGRE_Partnership_Brief.md` | Partner-facing scientific collaboration brief. |
| `docs/SASE_DGRE_Outreach_Kit.md` | Sendable outreach kit and data ask. |
| `docs/SNOWPACK_HIMSTRAT_Partner_Data_Adapter.md` | Partner snowpack/HIM-STRAT data contract. |
| `docs/Modal_GPU_Scientist_Coworking_Operating_Note.md` | Current Modal/GPU role and claim boundaries. |
| `docs/superpowers/plans/Euro_plans/README.md` | European shadow evidence pack index and transfer boundary. |
| `docs/MVP/source/Modal_GPU_ML_Inventory.md` | Detailed Modal/GPU and ML inventory. |
| `docs/MVP/source/Technical_Architecture_Current_Platform.md` | Longer architecture narrative; should be updated next if this source is used for a new deck. |
