# Scientist Demo — 30-Slide Presentation Prompts

Status: 2026-06-24
Purpose: Complete slide-by-slide content descriptions and AI image generation prompts for a 30-slide scientist demo presentation.
Format: Each slide includes title, key bullets, speaker notes, layout guidance, AI image prompt, and data/artifact reference.

Live demo: https://avalanche-insight-hub.netlify.app
Admin access: https://avalanche-insight-hub.netlify.app/admin (password: test123)
Scientist workspace: https://avalanche-insight-hub.netlify.app/scientist (open access in demo mode)

---

# Part A — Technical Architecture, ML/DL, Uniqueness & DRDO Alignment (Slides 1-15)

---

cision-support prototype, not an operational warning system. It is designed for scientist co-development — every model claim is reviewable, every promotion is gated by scientist approval. We align with the challenges identified in DRDO's Himalayan avalanche publications: sparse## Slide 1: Title & Proof Boundary

**Key Bullets:**
- Avalanche Insight Hub — Decision-Support Prototype for Snow Avalanche Risk Assessment
- Hosted, interactive, scientist-reviewable — not an official warning service
- Aligned with DRDO/DGRE Himalayan avalanche research challenges
- Built with batch-first ML architecture, scientist-gated model promotion
- "The electric light did not come from the continuous improvement of the candle" — Oren Harari
- What's NEW: autonomous data genesis (LLM news extraction + SAR + weather), zero-data cold start, transfer learning from Swiss Alps
- What's INCREMENTAL: better RF, better terrain proxies — these are candles, not electric light
- Building on DGRE's own neural network research: HIM-STRAT (Joshi, Singh, Satyawali, 2020) — extending Himalayan ANN snowpack simulation with autonomous data genesis

**Speaker Notes:**
Welcome. Dr. Amreek quoted Oren Harari: "The electric light did not come from the continuous improvement of the candle." That principle drives this prototype. We are not incrementally improving manual observation workflows. We are building something fundamentally new: an autonomous pipeline that generates its own training data from news (LLM extraction), satellite radar (Sentinel-1 SAR), and weather APIs — requiring zero historical data to start. Google's Groundsource methodology (Loike et al., 2026, arXiv), which uses Gemini to extract disaster events from news, explicitly identifies avalanches as a target hazard. We are implementing exactly that approach. This is the electric light. We also acknowledge and build upon DGRE's own pioneering work: HIM-STRAT (Joshi, Singh & Satyawali, 2020), a neural network for Himalayan snowpack simulation — our system extends that vision with autonomous data generation.

**Layout Guidance:**
Full-bleed mountain panorama background with dark gradient overlay. Title centered, subtitle below, small "Decision-Support Prototype" badge in top-right corner. Minimal text — let the image carry the emotional weight.

**AI Image Prompt:**
A dramatic wide-angle photograph of the Himalayan mountain range at dawn, snow-capped peaks shrouded in mist, deep valleys with shadow, golden light hitting the ridgelines, cinematic composition, ultra-high detail, National Geographic style, 16:9 aspect ratio, moody atmospheric lighting, no text overlay

**Data/Artifact Reference:**
`docs/MVP_V2/README.md` — proof boundary framing; Google Groundsource blog (https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/) — explicit avalanche mention; `backend/reproduction/artifacts/reproduction_summary.md` — Swiss RF4 real metrics

---

## Slide 2: The Himalayan Avalanche Challenge

**Key Bullets:**
- Sparse observations: few weather stations, limited snowpack data, no dense sensor networks
- Rare events: extreme class imbalance (avalanche days vs. non-avalanche days)
- Weak layers and snowpack memory: critical drivers invisible to simple weather models
- Terrain complexity: aspect, slope, elevation, curvature all modulate risk locally
- Black-box trust problem: scientists need interpretable, reviewable models

**Speaker Notes:**
The Himalayan avalanche problem is fundamentally different from Alpine forecasting. We have orders of magnitude fewer observations. The terrain is more complex. The snowpack regime is maritime-to-continental transition. And the scientists who understand these conditions need tools they can inspect, not black boxes. This slide frames the five core challenges our architecture is designed to address.

**Layout Guidance:**
Split layout: left side shows a stylized mountain cross-section with labeled challenge zones (sparse stations, weak layers, terrain aspects). Right side has the five challenge bullets with small icons. Dark background with emerald and amber accent colors.

**AI Image Prompt:**
A technical illustration of a mountain cross-section showing avalanche formation zones, layered snowpack with weak layers highlighted in red, weather station icons sparse along the base, terrain slope arrows showing aspect and angle, dark navy background with teal and amber data overlays, scientific diagram style, clean vector illustration, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP/source/Top_challanges.md` — original challenge mapping

---

## Slide 3: Architecture Overview

**Key Bullets:**
- Frontend: React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui
- Backend: Supabase (PostgreSQL, Auth, Storage, Edge Functions)
- ML Pipeline: Python batch jobs on GitHub Actions (training, inference, backfill, news, SAR)
- GPU Research: Modal.com for MTS-LSTM and SAR candidate workflows (off-path, gated)
- PWA: Offline field reports with BackgroundSync queue, auth header preservation
- Autonomous Data Genesis: newsdata.io + Gemini LLM extraction (Google Groundsource methodology for avalanches), Sentinel-1 SAR via Google Earth Engine, Open-Meteo weather ingestion
- NATSAT Complement: software intelligence layer that can feed prediction inputs to DRDO's NATSAT warning dissemination system
- DRDO-ISRO MoU alignment: satellite-based snow cover retrieval + high-resolution meteorological forecasts — our GEE Sentinel-1 + Open-Meteo pipeline implements this vision

**Speaker Notes:**
Our architecture is deliberately batch-first. Heavy ML runs on GitHub Actions as scheduled workflows, producing precomputed forecast grids stored in Supabase. The frontend renders these grids — no synchronous ML inference in the browser or edge functions. Modal.com GPU is used only for research candidate training, never for the public scorer. The autonomous data genesis pipeline implements Google's Groundsource methodology — using Gemini to extract avalanche events from news, exactly as Google identified avalanches as a target hazard. Our system is designed to complement DRDO's NATSAT satellite warning system: NATSAT delivers alerts to soldiers via satellite; our system generates the AI intelligence that triggers those alerts. Our satellite data approach (GEE Sentinel-1) and meteorological ingestion (Open-Meteo) directly align with the DRDO-ISRO MoU signed by Dr. Satyawali and ISRO SAC Director for satellite-based snow cover retrieval and high-resolution meteorological forecasts over the Himalayas.

**Layout Guidance:**
Architecture diagram with five horizontal layers: (1) PWA Frontend, (2) Supabase Backend, (3) GitHub Actions Batch ML, (4) Modal.com GPU Research, (5) External Data Sources. Arrows showing data flow between layers. Use a dark theme with color-coded layers.

**AI Image Prompt:**
A modern cloud architecture diagram showing five layers: React frontend at top, Supabase database layer, GitHub Actions CI/CD pipeline layer, Modal.com GPU compute layer, and external API data sources at the bottom, connected by flowing data arrows, dark navy background with emerald green and sky blue accent lines, clean technical infographic style, isometric perspective, 16:9 aspect ratio

**Data/Artifact Reference:**
`src/App.tsx` — route structure; `supabase/config.toml` — edge function config; `.github/workflows/backend-ci.yml` — CI pipeline

---

## Slide 4: Batch-First ML Serving

**Key Bullets:**
- No synchronous edge ML — all inference is precomputed in batch
- GitHub Actions runs training, inference, SAR search, news enrichment, and historical backfill on schedule
- Forecast grids stored as per-hour JSON artifacts in Supabase Storage
- Frontend hydrates grids from Supabase REST — deterministic, cacheable, CDN-friendly
- Cost: $0 for compute (GitHub Actions free tier), $200-500/mo for Supabase + storage

**Speaker Notes:**
The key architectural decision is batch-first serving. Instead of running ML inference on-demand (which requires always-on GPU and introduces latency), we precompute 72-hour forecast grids in GitHub Actions and store them as decomposed per-hour JSON artifacts. The frontend simply fetches and renders. This means the app works even with zero GPU, zero edge compute, and degrades gracefully to cached fallback grids.

**Layout Guidance:**
Flow diagram: GitHub Actions (left) → Python batch inference → Supabase Storage (per-hour JSON) → Supabase REST → React frontend (right). Show timeline arrows indicating scheduled runs. Include cost badges ($0 compute, $200-500 infra).

**AI Image Prompt:**
A horizontal flow diagram showing scheduled batch processing: GitHub Actions icon on the left with clock symbols, Python code blocks in the center processing data, Supabase database storage icons on the right with JSON file symbols, arrows flowing left to right, dark background with green data flow lines, clean technical diagram style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/common/forecast_publication.py` — artifact decomposition; `.github/workflows/` — scheduled workflows

---

## Slide 5: Forecast Artifact Decomposition

**Key Bullets:**
- Monolithic JSONB forecast grids decomposed into per-hour gzipped JSON artifacts
- Each hour stored as separate file: `forecast_{run_id}_h{hour}.json.gz`
- SHA-256 manifest links all hourly artifacts with checksums
- Supabase Storage bucket with RLS policies for public read access
- Frontend lazy-loads only the hours being viewed — 72h horizon without downloading all data

**Speaker Notes:**
Previously, a 72-hour forecast was stored as a single JSONB column in PostgreSQL. This created performance problems: the frontend had to download the entire grid even to show one hour. We decomposed forecasts into per-hour gzipped JSON artifacts in Supabase Storage, with a SHA-256 manifest for integrity. The frontend lazy-loads individual hours as the user scrolls the time slider.

**Layout Guidance:**
Before/after comparison: left side shows "Before: Single JSONB column (5MB+)" with a monolithic block. Right side shows "After: Per-hour artifacts" with 72 small file icons, a manifest file, and lazy-load arrows pointing to the frontend. Use green checkmarks on the "After" side.

**AI Image Prompt:**
A before-and-after technical diagram: left side shows a single large database cylinder labeled JSONB with a red performance warning, right side shows 72 small JSON file icons arranged in a grid with green checkmarks, a manifest file connecting them with hash symbols, arrows showing selective loading, dark background, clean infographic style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/common/forecast_publication.py:94-141` — artifact decomposition implementation

---

## Slide 6: Random Forest Baseline Model

**Key Bullets:**
- Interpretable tabular Random Forest scorer — the current live production model
- Features: temperature, windspeed, elevation, slope, aspect, terrain roughness, curvature proxy
- Youden/PSS data-driven threshold optimization (not fixed cutoff)
- Brier score calibration for probability reliability
- SHAP TreeExplainer values precomputed for every grid cell — deterministic client-side narratives

**Speaker Notes:**
The production scorer is deliberately a Random Forest, not a deep neural network. This is a design choice: scientists need to inspect why the model made a prediction. We use Youden's J statistic to find the optimal probability threshold per region, Brier score to calibrate probabilities, and SHAP TreeExplainer to produce per-cell feature importance narratives. The model is transparent by construction.

**Layout Guidance:**
Left: feature importance bar chart (top 10 features with SHAP values). Right: calibration plot showing predicted vs. observed probability. Bottom: small code snippet showing the RF training call with Brier gate check.

**AI Image Prompt:**
A machine learning visualization showing two panels side by side: left panel shows a horizontal bar chart of feature importance with green and amber bars labeled temperature, slope, elevation, windspeed, aspect; right panel shows a calibration curve plot with a diagonal reference line and scattered points, dark background, scientific publication style, clean typography, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/models/surrogate_rf.py` — RF model with SHAP; `backend/train_model.py` — Brier gate logic

---

## Slide 7: MTS-LSTM Candidate Model

**Key Bullets:**
- Multi-Time-Scale LSTM (MTS-LSTM) — candidate deep learning model for temporal sequences
- Trained on Modal.com GPU workers — off-path, not the public scorer
- Promotion gate: PSS holdout must exceed RF baseline PSS to be considered
- Brier score must be ≤ 0.15 (calibrated) for publication eligibility
- Early stopping with epoch tracking — no overfitting to training data

**Speaker Notes:**
The MTS-LSTM is our research candidate. It processes multi-time-scale weather sequences to capture snowpack memory effects. It runs on Modal.com GPU — but only as a candidate. It cannot replace the RF scorer until it passes two gates: Peirce Skill Score on the holdout must beat the RF, and Brier score must be ≤ 0.15. Even then, scientist approval is required for promotion. This is the gated promotion pipeline.

**Layout Guidance:**
Architecture diagram: input weather sequences (multi-time-scale) → LSTM layers → dense head → probability output. Overlay a "GATED" badge. Side panel showing the two promotion gates: PSS > RF and Brier ≤ 0.15. Use amber/orange for "candidate" status.

**AI Image Prompt:**
A neural network architecture diagram showing multi-time-scale LSTM layers processing weather time series data, with input sequences at different time scales feeding into LSTM cells, dense layers, and a probability output, overlaid with a glowing amber GATED badge, dark background with orange and teal data flow lines, technical AI diagram style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/models/mts_lstm.py` — MTS-LSTM implementation; `backend/train_model.py:883-901` — promotion gate logic

---

## Slide 8: KMeansSMOTE + Physical Plausibility Filtering

**Key Bullets:**
- KMeansSMOTE addresses extreme class imbalance (rare avalanche events)
- Synthetic samples filtered by physical plausibility rules:
  - High-elevation winter temperature cap (≥2500m, ≤5°C)
  - Lapse-rate consistency check
  - Seasonal consistency enforcement
  - Terrain-aspect plausibility
- Class weight: {0: 1, 1: 4} for baseline imbalance handling
- Filter rejects unphysical synthetic samples before training

**Speaker Notes:**
Avalanche events are rare — in a winter season, most days at most locations do not produce avalanches. KMeansSMOTE generates synthetic minority-class samples, but naive SMOTE can create physically impossible combinations: e.g., a warm winter day at 3500m with high avalanche risk. We filter synthetic samples against terrain and weather physics: elevation-temperature consistency, seasonal validity, and lapse-rate bounds. This ensures the model trains on physically plausible scenarios.

**Layout Guidance:**
Three-panel layout: (1) Before filtering — scatter plot with red circles showing unphysical samples. (2) Filter rules — list with checkmark icons. (3) After filtering — clean scatter plot with only physically valid samples. Use red-to-green transition.

**AI Image Prompt:**
A scientific visualization showing three panels: left panel shows a scatter plot of synthetic data points with red circles highlighting unphysical samples at high elevations with high temperatures, center panel shows filter rules with checkmark icons, right panel shows the same scatter plot cleaned with only green valid points, dark background, scientific publication style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/models/surrogate_rf.py:151-169` — `filter_unphysical_synthetic_samples()` implementation

---

## Slide 9: D_tidy Label Provenance

**Key Bullets:**
- NHESS 2022 distinction: D_forecast (model predictions) vs. D_tidy (quality-controlled labels)
- Training dataset now carries six provenance fields per sample:
  - `label_source`: origin of the label (field report, SAR, news, synthetic)
  - `review_basis`: verification level (expert_verified, verified, unverified, synthetic)
  - `nowcast_ref`: link to nowcast analysis if available
  - `observer_ref`: observer identity for traceability
  - `regime`: avalanche regime classification
  - `timing`: temporal context (early/peak/late season)
- Enables confidence-weighted training and scientist audit of label quality

**Speaker Notes:**
The NHESS 2022 paper highlights a critical distinction: the data used to train models (D_tidy) must be quality-controlled and traceable, separate from the model's own predictions (D_forecast). We've added six provenance fields to every training sample. This means every label can be traced back to its source, its review status, and its observer. Scientists can audit which labels they trust and weight their training influence accordingly.

**Layout Guidance:**
Data table showing 6-8 sample rows with the six provenance fields as columns. Color-code the `review_basis` column: green for expert_verified, amber for unverified, purple for synthetic. Add a side note: "NHESS 2022 D_tidy alignment."

**AI Image Prompt:**
A clean data table visualization showing rows of training data with six highlighted columns: label_source, review_basis, nowcast_ref, observer_ref, regime, timing, color-coded cells in green amber and purple, dark background with a side note reading NHESS 2022 D_tidy alignment, scientific data table style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/common/training_dataset.py:150,334-339` — provenance fields in query and dataset rows

---

## Slide 10: SAR / Sentinel-1 Shadow Pipeline

**Key Bullets:**
- Terrain-masked Sentinel-1 wet-snow detection — not full multi-orbital union
- Ascending/descending coverage tracking with historical backfill
- SAR candidate remains shadow-gated: not promoted to production scoring
- ASF Search API for metadata; NASA Earthdata for scene download
- GEE integration for historical backfill and terrain masking

**Speaker Notes:**
SAR is a promising modality for avalanche detection — it can see through clouds and at night. But real pixel-level SAR change detection requires heavy raster processing. Our approach is deliberately conservative: terrain-masked wet-snow detection using Sentinel-1, with ascending and descending coverage tracking. This is a shadow-gated research path — it feeds evidence into the scientist workbench but does not change the public scorer until research-grade validation passes.

**Layout Guidance:**
Satellite imagery overlay: Sentinel-1 SAR image of a mountainous area with wet-snow detection zones highlighted in blue. Side panel showing asc/desc coverage status badges. Bottom: "SHADOW-GATED" badge in amber.

**AI Image Prompt:**
A satellite radar image of a mountainous region in grayscale with blue overlay zones indicating wet snow detection, terrain masking visible as dark shadows on steep slopes, ascending and descending orbit icons in the corner, dark technical interface style with amber SHADOW-GATED badge, 16:9 aspect ratio, Copernicus Sentinel-1 imagery style

**Data/Artifact Reference:**
`backend/historical_sar_backfill.py` — SAR backfill; `backend/gee_extractor.py` — GEE integration

---

## Slide 11: SHAP Explainability

**Key Bullets:**
- Client-side deterministic SHAP narratives over precomputed TreeSHAP values
- Every grid cell has precomputed SHAP values for top features
- Frontend renders human-readable narrative: "This cell's risk is driven by…"
- Gemini edge explainer is auxiliary — not the primary UI path
- Scientists can inspect exactly which features drove each cell's prediction

**Speaker Notes:**
Explainability is not an add-on — it's baked into the architecture. We precompute SHAP TreeExplainer values for every grid cell during batch inference. The frontend then renders deterministic, human-readable narratives: "This cell's elevated risk is primarily driven by high windspeed at 850hPa and steep southeast aspect." This is fully deterministic — the same cell always produces the same narrative. The Gemini LLM explainer is auxiliary, used only for deeper natural-language summaries on request.

**Layout Guidance:**
Screenshot-style mockup of a cell evidence drawer showing: risk score gauge, top 5 SHAP feature bars, and a narrative text box. Clean, dark UI with emerald accents. Label: "Deterministic — same input, same output, every time."

**AI Image Prompt:**
A UI mockup of an evidence drawer panel showing a risk score gauge at top, five horizontal SHAP feature importance bars in green and amber, and a text narrative box below reading This cell risk is driven by high windspeed and steep southeast aspect, dark interface design with emerald green accents, clean modern UI style, 16:9 aspect ratio

**Data/Artifact Reference:**
`src/components/ExpertModePanel.tsx` — SHAP narrative rendering; `backend/common/` — SHAP precomputation

---

## Slide 12: PWA Offline Field Reports

**Key Bullets:**
- Progressive Web App with Workbox BackgroundSync queue
- Offline field report submission — queued and replayed on reconnect
- Auth headers preserved in queued requests (JWT from supabase.functions.invoke)
- Idempotent upserts via `client_report_id` — no duplicate submissions on replay
- Works in mountain environments with intermittent connectivity

**Speaker Notes:**
Scientists and field observers work in mountain environments with unreliable connectivity. Our PWA uses Workbox BackgroundSync to queue field report submissions while offline. When connectivity returns, the queue replays automatically — with original auth headers preserved. We use idempotent upserts via `client_report_id` so that even if a report is submitted multiple times (once offline, once on reconnect), it creates one record, not duplicates.

**Layout Guidance:**
Phone mockup showing offline field report form with a "Queued" badge. Arrow showing sync when online. Side panel: BackgroundSync queue diagram with auth header preservation. Bottom: "Idempotent: no duplicates" badge.

**AI Image Prompt:**
A smartphone mockup showing a mountain field report form with a purple Queued badge, beside it a sync arrow leading to a green Synced status, background shows a mountain landscape with intermittent signal bars, dark UI design with emerald and purple accents, modern app design style, 16:9 aspect ratio

**Data/Artifact Reference:**
`vite.config.ts:110-159` — BackgroundSync configuration; `src/lib/fieldReportSync.ts` — field report invocation

---

## Slide 13: Brier Score Publish Gate

**Key Bullets:**
- Model must achieve Brier score ≤ 0.15 (calibrated) to be published
- Peirce Skill Score (PSS) must exceed RF baseline PSS on holdout
- Gate logic: `brier_gate_passed = brier_score ≤ BRIER_SCORE_CEILING`
- If gate fails: `brier_score_gate_failed` — model artifact is NOT published to Supabase
- Synthetic bootstrap artifacts are tagged `is_synthetic=True` and never overwrite live model_status

**Speaker Notes:**
We enforce a hard publish gate. A model that doesn't pass Brier ≤ 0.15 and PSS > RF is not published — period. The gate is in the training pipeline itself. If the gate fails, the artifact is saved locally for inspection but never written to Supabase. This means the live scorer can only be replaced by a model that demonstrably outperforms the baseline on both discrimination (PSS) and calibration (Brier).

**Layout Guidance:**
Gate diagram: two checkpoints (PSS gate, Brier gate) with green checkmarks or red X marks. If both pass → "PUBLISHED" badge. If either fails → "BLOCKED" badge with reason. Show a sample metrics table: PSS=0.54 ✓, Brier=0.17 ✗ → "brier_score_gate_failed."

**AI Image Prompt:**
A quality gate flowchart showing two checkpoint diamonds: PSS Gate and Brier Gate, with green checkmark paths leading to a green PUBLISHED badge and red X paths leading to a red BLOCKED badge, sample metrics table below showing PSS 0.54 with checkmark and Brier 0.17 with X mark, dark background, clean technical diagram style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/train_model.py:883-901` — gate logic; `backend/common/european_shadow_sources.py:583` — gate pass records

---

## Slide 14: DRDO Paired Comparison Analytics

**Key Bullets:**
- Scientist Validation Workbench with DRDO paired comparison panel
- Tracks: total reviewed, agreement rate, disagreement count
- Model overconfident cases: risk ≥ 4 but scientist verdict = rejected
- Model underconfident cases: risk ≤ 2 but scientist verdict = accepted
- Two-reviewer tracking for priority 5 cases — SLA routing on disagreement

**Speaker Notes:**
The DRDO paired comparison panel is the heart of scientist-model co-development. For every validation case, we track whether the model and the scientist agreed. If the model predicted high risk (level 4+) but the scientist rejected the prediction, that's a "model overconfident" case — a potential false alarm pattern. If the model predicted low risk (level 2 or below) but the scientist accepted, that's "model underconfident" — a potential missed event. These analytics feed directly into model improvement cycles.

**Layout Guidance:**
Screenshot-style mockup of the DRDO Paired Comparison panel: 3×2 grid of metric cards (Reviewed, Agreement, Disagreements, Model Over, Model Under, 2-Reviewer Done). Color-coded values: green for agreement, amber for disagreements, red for overconfident, blue for underconfident.

**AI Image Prompt:**
A dashboard UI mockup showing a 3 by 2 grid of metric cards with labels Reviewed, Agreement Rate, Disagreements, Model Overconfident, Model Underconfident, and Two-Reviewer Done, with color-coded values in green amber red and blue, dark interface design with sky blue panel border, clean modern dashboard style, 16:9 aspect ratio

**Data/Artifact Reference:**
`src/components/ScientistValidationWorkbench.tsx:146-173,311-347` — DRDO paired comparison implementation

---

## Slide 15: What Makes This World-Class

**Key Bullets:**
- Batch-first architecture: zero-cost compute, deterministic serving, graceful degradation
- Scientist-gated promotion: no model replaces the baseline without expert approval
- Physical plausibility filters: synthetic samples must pass terrain/weather physics
- D_tidy label provenance: NHESS 2022-aligned traceable training data
- CAP XML interoperability: WMO CAP 1.2 scaffold for future national emergency pathways
- FAIR data compliance: every data source licensed and documented
- PWA offline-first: field reports from mountain environments with intermittent connectivity
- Swiss RF4 reproduction: 89.5% accuracy on real EnviDat RF2 data (29,296 rows, 74 features, isotonic calibration, Brier 0.157)
- SHAP explainability: TreeSHAP analysis shows elevation, new snow height, and wind transport as top drivers — consistent with Swiss literature. NHESS 2025 validates SHAP as operational tool for avalanche forecasting (Pérez-Guillén et al., 2025)
- Transferability validated: Pérez-Guillén et al. (2026, NHESS) demonstrated Swiss RAvaFcast models transfer to other mountain ranges (Pyrenees)
- DGRE roadmap alignment: our system maps to 3 active DGRE technology tasks (AI/ML change detection, meso-micro forecast, remote sensing snow characterization)
- DRDO-ISRO MoU alignment: satellite-based snow cover retrieval + meteorological forecasts — our GEE + Open-Meteo pipeline implements this vision
- Building on HIM-STRAT (Joshi, Singh & Satyawali, 2020): extends DGRE's own neural network snowpack research with autonomous data genesis
- "Virtual forecaster" concept: Swiss operational use of ML as second opinion (Winkler et al., 2024; Maissen et al., 2024) — our system follows this model
- EGU 2026 alignment: RS-based DSS for NW Himalaya avalanche susceptibility using SVM/RF/LightGBM (Sharma & Tiwari, EGU 2026) validates our approach

**Speaker Notes:**
What makes this world-class is not any single component — it's the integration. We have now executed the Swiss RF4 reproduction on real EnviDat data: 89.5% accuracy with 74 features and isotonic calibration (Brier score 0.157, ECE 0.041). TreeSHAP analysis confirms that elevation, new snow height (HN72_24, HN24_7d), and wind transport are the dominant prediction drivers — fully consistent with Swiss avalanche literature. The NHESS 2025 paper (Pérez-Guillén et al.) validates SHAP as a powerful operational tool for avalanche forecasting explainability. The peer-reviewed paper by Pérez-Guillén et al. (2026) in NHESS demonstrates that Swiss RAvaFcast models CAN transfer to other mountain ranges — they tested Pyrenees transfer. This is scientific backing for our Swiss-to-Himalayan approach. Furthermore, our system directly maps to three DGRE technology development tasks: AI/ML-based geohazard change detection, meso-to-micro-scale avalanche forecast using AI/ML, and remote sensing for snow cover/pack characterization. We are building what DGRE's own roadmap calls for. We also align with the DRDO-ISRO MoU for satellite-based snow cover and meteorological forecasting, and build upon DGRE's own HIM-STRAT neural network research (Joshi, Singh & Satyawali, 2020). The Swiss operational concept of ML as a "virtual forecaster" providing a second opinion (Winkler et al., 2024) is exactly our model — we complement, not replace, scientist expertise. The EGU 2026 presentation on RS-based DSS for NW Himalaya avalanche susceptibility (Sharma & Tiwari) using SVM/RF/LightGBM with ROC-AUC=0.855 further validates our approach in the exact same region.

**Layout Guidance:**
Seven-icon grid with short labels: Batch-First, Scientist-Gated, Physical Filters, D_tidy Provenance, CAP XML, FAIR Compliance, PWA Offline. Each icon in a rounded card with emerald accent. Center title: "Seven Pillars of World-Class Design."

**AI Image Prompt:**
A seven-icon grid layout with rounded cards, each containing a distinct minimalist icon representing cloud computing, scientist approval, physics filter, data traceability, emergency alert, compliance certificate, and offline mobile, emerald green accents on dark background, clean modern infographic style, 16:9 aspect ratio

**Data/Artifact Reference:**
All prior slides; `docs/MVP_V2/00_start_here/Commercials.md` — commercial framing

---

# Part B — Co-Working Model, Commercials, How-To & Critical Additions (Slides 16-30)

---

## Slide 16: Co-Working Model Overview

**Key Bullets:**
- 2-4 week autonomous pipeline sprint — not a binding commitment
- Week 1-2: Activate autonomous pipeline (news + SAR + weather) for selected Himalayan region
- Week 3-4: Generate first forecasts from autonomous events; scientist reviews output
- Week 4 (closeout): Review skill scores, limitations, and next-stage scope — continue, narrow, pause, or stop
- Scientist team leads domain review; dev team provides autonomous pipeline and infrastructure
- No historical data demands — pipeline generates its own data autonomously
- Complements NATSAT: our software intelligence layer generates predictions; NATSAT delivers alerts to soldiers via satellite
- Complements Dr. Praven's group: we provide autonomous data pipeline + Swiss reproduction lane; they provide domain expertise + limited Himalayan data
- Extends HIM-STRAT: DGRE's own neural network snowpack model (Joshi, Singh & Satyawali, 2020) — our autonomous pipeline can feed it continuous data

**Speaker Notes:**
The co-working model is built around the autonomous pipeline. We're not asking for historical data or a binding contract. We propose a 2-4 week sprint where we activate the autonomous data genesis pipeline for a selected Himalayan region. The pipeline collects events from news (LLM extraction), SAR (Sentinel-1), and weather (Open-Meteo), then trains and publishes forecasts. The scientist team reviews the output and provides domain feedback. At the end of the sprint, there's a decision point: continue, narrow, pause, or stop. Importantly, this system is designed to complement DRDO's existing infrastructure: NATSAT handles satellite-based warning dissemination to soldiers, while our system provides the AI prediction intelligence that feeds into NATSAT. We also complement Dr. Praven's group's ongoing work on similar Himalayan models — our autonomous data pipeline can feed their models, and their domain expertise can validate our predictions. Furthermore, our system extends DGRE's own HIM-STRAT neural network research (Joshi, Singh & Satyawali, 2020) — the autonomous data pipeline can provide continuous training data to HIM-STRAT-style snowpack models, addressing the data scarcity limitation that has constrained Himalayan neural network approaches.

**Layout Guidance:**
Horizontal timeline with two sprint blocks. Each block has a focus label, a decision diamond at the end, and icons representing autonomous pipeline activities (news, SAR, weather, model). Use a gradient from light to dark to show progression. Bottom: "Autonomous pipeline + scientist review" badge.

**AI Image Prompt:**
A horizontal 2-4 week sprint timeline with milestone blocks for Week 1-2 Autonomous Pipeline Activation with news SAR and weather icons, Week 3-4 First Forecasts and Scientist Review with chart and checkmark icons, and Week 4 Closeout with diamond decision point showing continue narrow pause or stop, gradient from light to dark blue, autonomous pipeline badge at bottom, dark background, clean project timeline style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/SCIENTIST_COLLABORATION_PITCH_MVP1_MVP2.md` — autonomous pipeline sprint

---

## Slide 17: RACI Matrix

**Key Bullets:**
- **R**esponsible: Who does the work
- **A**ccountable: Who approves the result
- **C**onsulted: Who provides input
- **I**nformed: Who is kept up to date

| Activity | Dev Team | Scientist Lead | Director/DRDO |
|----------|----------|----------------|---------------|
| Model training & inference | R | C | I |
| Label quality control (D_tidy) | C | R/A | I |
| Model promotion gate | C | A | I |
| Public copy approval | C | A | I |
| Credential management | R/A | I | I |
| Data source licensing | R | C | A |
| Pilot region selection | C | R | A |

**Speaker Notes:**
The RACI matrix makes ownership explicit. The dev team is responsible for building and running the ML pipeline, but the scientist lead is responsible and accountable for label quality — D_tidy is a scientist-owned artifact. Model promotion requires scientist accountability — the dev team can only propose. Public copy changes need scientist approval. This prevents the dev team from making scientific claims without expert sign-off.

**Layout Guidance:**
Full-width RACI table with color-coded cells: R in blue, A in emerald, C in amber, I in gray. Three role columns: Dev Team, Scientist Lead, Director/DRDO. Clean table styling with alternating row backgrounds.

**AI Image Prompt:**
A clean RACI matrix table with seven rows of activities and three columns for Dev Team, Scientist Lead, and Director DRDO, cells color-coded in blue for Responsible, emerald for Accountable, amber for Consulted, and gray for Informed, dark background with clean typography, professional corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/ROLE_DEMARCATION_CHARTER.md` — full RACI matrix

---

## Slide 18: Role Demarcation — Key Principles

**Key Bullets:**
- **Scientist authority over promotion gates**: Scientists approve or reject model promotion. The dev team proposes only.
- **No automatic promotion from reviews**: Scientist reviews create governed candidates and actions, never automatic model changes.
- **D_tidy label ownership**: Quality-controlled label creation is a scientist responsibility. The dev team provides tooling, not truth labels.
- **Public copy approval**: Scientist team approves or rejects claim wording changes.
- **Security and credentials**: Dev team owns credential management and rotation. Scientists are informed, not responsible.

**Speaker Notes:**
These five principles are the non-negotiable foundations of the co-working model. The most important is principle one: scientists have authority over promotion gates. The dev team can train models, run experiments, and propose improvements — but cannot promote a model to production without scientist approval. This ensures that scientific integrity is never compromised by development velocity.

**Layout Guidance:**
Five principle cards in a vertical stack, each with an icon, a bold title, and a one-line description. Use a lock icon for security, a gavel for authority, a database for D_tidy, a document for public copy, and a refresh-off icon for no auto-promotion.

**AI Image Prompt:**
Five vertically stacked principle cards with icons: a gavel for Scientist Authority, a refresh-off icon for No Auto-Promotion, a database icon for D_tidy Label Ownership, a document icon for Public Copy Approval, and a lock icon for Security and Credentials, emerald green and amber accents on dark background, clean corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/SCIENTIST_COLLABORATION_PITCH_MVP1_MVP2.md:136-148` — role demarcation summary

---

## Slide 19: Access & Permissions Matrix

**Key Bullets:**
- `/` (Public Forecast): Open to all — no login required
- `/scientist` (Validation Workbench): Open in demo mode — no login required
- `/scientist/daily-verification`: Open in demo mode — no login required
- `/admin` (Admin Dashboard): Demo password `test123` — no email required
- All routes accessible from the navigation bar
- Supabase RLS policies still protect data writes at the database level

**Speaker Notes:**
For this demo, we've removed all authentication barriers. Scientists can access the validation workbench, daily verification, and partner intake directly. The admin dashboard requires only a simple password — `test123` — with no email or Supabase account needed. This is demo mode: designed for easy access during the scientist review. In production, Supabase auth with role-based access would be re-enabled.

**Layout Guidance:**
Four-row table: Route | URL | Access | Purpose. Color-code: green for open, amber for password-gated. Include the full URLs with the Netlify domain. Add a note: "Demo mode — production would require Supabase auth."

**AI Image Prompt:**
A clean access matrix table showing four rows for routes: Public Forecast with green open access, Scientist Validation with green open access, Daily Verification with green open access, and Admin Dashboard with amber password test123 access, dark background, clean corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`netlify.toml` — VITE_DEMO_MODE=true; `src/components/RoleAccessGate.tsx:218` — demo bypass; `src/components/AdminAccessGate.tsx:215` — demo password gate

---

## Slide 20: Non-Automation Rules

**Key Bullets:**
- Scientist reviews create governed candidates and actions — never automatic model changes
- No model is promoted to production without explicit scientist approval
- SAR detection remains shadow-gated — cannot enter production scoring without research-grade validation
- Synthetic bootstrap artifacts are tagged `is_synthetic=True` and never overwrite live `model_status`
- Drift detection reports are informational only — no autonomous model retraining or remediation

**Speaker Notes:**
These rules prevent the most dangerous failure mode: an automated system that promotes models without human oversight. Even if a new model passes all statistical gates (Brier, PSS), it still requires a scientist to click "approve" in the validation workbench. Drift detection runs and reports, but it cannot trigger retraining. SAR evidence feeds into the workbench but cannot change the public scorer. These are guardrails, not bottlenecks.

**Layout Guidance:**
Five rule cards with red "no" icons (no auto-promotion, no autonomous retraining, no SAR auto-promotion, no synthetic overwrite, no drift auto-remediation). Use a shield icon in the center with "Human-in-the-Loop" text.

**AI Image Prompt:**
Five rule cards arranged in a semicircle around a central shield icon reading Human-in-the-Loop, each card with a red no-entry icon and a rule label: No Auto-Promotion, No Autonomous Retraining, No SAR Auto-Promotion, No Synthetic Overwrite, No Drift Auto-Remediation, dark background with red and emerald accents, clean corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/ROLE_DEMARCATION_CHARTER.md` — non-automation rules section

---

## Slide 21: Escalation Paths

**Key Bullets:**
- Priority 5 cases require two independent reviewers before closure
- Disagreement count > 0 triggers escalation button in the workbench
- Escalation routes to Senior Admin for SLA routing
- Blocked cases generate governed actions with owner and due date
- Director letter draft available for cases requiring institutional escalation

**Speaker Notes:**
When scientists disagree with the model or with each other, the system doesn't hide the conflict — it surfaces it. Priority 5 cases require two independent reviewers. If there's a disagreement, an escalation button appears in the workbench, routing the case to a senior admin. Every escalation is logged with a reason and timestamp. For cases requiring institutional escalation, a director letter template is available in the outreach kit.

**Layout Guidance:**
Flowchart: Case → Review → Agreement? → Yes: Close / No: Escalate → Senior Admin → SLA Routing → Director Letter (if needed). Show the escalation log panel with timestamped entries.

**AI Image Prompt:**
A flowchart showing case review process: Case box leading to Review box, then a diamond decision for Agreement, Yes path leading to Close, No path leading to Escalate box, then Senior Admin box, then SLA Routing, then Director Letter, side panel showing escalation log with timestamped entries in red, dark background, clean flowchart style, 16:9 aspect ratio

**Data/Artifact Reference:**
`src/components/ScientistValidationWorkbench.tsx:385-408` — escalation UI; `docs/MVP_V2/02_letters_outreach_templates/` — director letter

---

## Slide 22: How to Use — Scientist Workspace

**Key Bullets:**
- Navigate to: https://avalanche-insight-hub.netlify.app/scientist
- No login required in demo mode — direct access
- Review validation cases in the queue (sorted by priority)
- For each case: select verdict, claim impact, EAWS problem, label quality, model error, terrain/SAR ambiguity
- Attach publication references from the built-in reference library
- Export individual case JSON or full sign-off Markdown/JSON

**Speaker Notes:**
The scientist workspace is the primary review interface. When you open it, you'll see validation cases sorted by priority. Click "Review" on any case to open the structured review dialog. You'll select a verdict (accepted, rejected, needs info, accepted limitation, or blocked), assess the claim impact, classify the EAWS avalanche problem, and rate the label quality and model error. You can attach publication references from the built-in library. When done, export the full sign-off as Markdown or JSON.

**Layout Guidance:**
Annotated screenshot of the scientist workspace showing: case queue, review dialog with structured fields, reference library, and export buttons. Add numbered callouts: 1. Case queue, 2. Review button, 3. Structured fields, 4. Export.

**AI Image Prompt:**
A UI mockup of a scientist validation workbench showing a case queue on the left with priority badges, a review dialog on the right with dropdown selectors for Verdict, Claim Impact, EAWS Problem, Label Quality, and Model Error, a reference library section with checkboxes, and export buttons at the bottom, dark interface design with emerald accents, clean modern UI style, 16:9 aspect ratio

**Data/Artifact Reference:**
Live URL: https://avalanche-insight-hub.netlify.app/scientist

---

## Slide 23: How to Use — Daily Paired Verification

**Key Bullets:**
- Navigate to: https://avalanche-insight-hub.netlify.app/scientist/daily-verification
- Select date and region to compare model vs. scientist danger levels
- Enter your danger level assessment (1-5 or not assessed)
- Select official avalanche problem type
- Add notes on specific observations
- Analytics panel shows agreement trends over time

**Speaker Notes:**
The daily verification page is where scientists do paired comparisons. Select a date and region, then enter your own danger level assessment. The system compares it against the model's prediction and tracks agreement over time. This is the core of the DRDO paired comparison workflow — it generates the data that feeds the analytics panel we showed in Slide 14.

**Layout Guidance:**
Annotated screenshot of the daily verification page showing: date/region selectors, danger level dropdown, avalanche problem selector, notes textarea, and analytics chart. Numbered callouts: 1. Select date/region, 2. Enter your assessment, 3. View analytics.

**AI Image Prompt:**
A UI mockup of a daily verification page showing date and region dropdown selectors at top, a danger level selector with options 1 Low to 5 Very High, an avalanche problem type dropdown, a notes text area, and an analytics chart below showing agreement trends over time, dark interface design with emerald accents, clean modern UI style, 16:9 aspect ratio

**Data/Artifact Reference:**
Live URL: https://avalanche-insight-hub.netlify.app/scientist/daily-verification

---

## Slide 24: How to Use — Admin Dashboard

**Key Bullets:**
- Navigate to: https://avalanche-insight-hub.netlify.app/admin
- Enter demo password: `test123`
- View: compute job history, model status, publication events, storage artifacts
- Split view: toggle between admin-only and forecast context side-by-side
- SYNTHETIC BOOTSTRAP warning appears if latest training was synthetic
- Satellite fallback status shown as amber badge

**Speaker Notes:**
The admin dashboard is the operational control lane. Enter the password `test123` to access it. You'll see compute job history (training runs, inference runs), current model status, and publication events. The split view lets you see the public forecast alongside admin evidence. If the latest training was a synthetic bootstrap (no real data), a warning badge appears. Satellite fallback status is shown as an amber badge when SAR coverage is unavailable.

**Layout Guidance:**
Annotated screenshot of the admin dashboard showing: password gate (test123), compute jobs table, model status card, split view toggle, and SYNTHETIC BOOTSTRAP warning badge. Numbered callouts: 1. Password gate, 2. Compute jobs, 3. Model status, 4. Split view.

**AI Image Prompt:**
A UI mockup of an admin dashboard showing a simple password input field with test123 entered, then a dashboard with compute job history table, model status card with green active badge, a split view toggle button, and an amber SYNTHETIC BOOTSTRAP warning badge, dark interface design with emerald accents, clean modern admin UI style, 16:9 aspect ratio

**Data/Artifact Reference:**
Live URL: https://avalanche-insight-hub.netlify.app/admin (password: test123)

---

## Slide 25: How to Use — Field Reports

**Key Bullets:**
- From the public forecast page, use the field report form
- Works offline — submissions are queued and synced automatically on reconnect
- Idempotent: no duplicate submissions even if submitted multiple times
- Fields: location, timestamp, avalanche type, trigger, size, aspect, elevation
- Reports feed into the scientist validation pipeline as evidence inputs

**Speaker Notes:**
Field reports are submitted from the public forecast page. The form works offline — if you're in a mountain area without signal, the report is queued locally and automatically synced when connectivity returns. The system uses idempotent upserts, so submitting the same report twice (once offline, once on reconnect) creates exactly one record. Field reports then appear as evidence in the scientist validation workbench.

**Layout Guidance:**
Phone mockup showing the field report form with location pin, timestamp, avalanche type dropdown, and a "Submit (Queued)" button. Arrow showing sync to cloud. Side note: "Works offline — no duplicates."

**AI Image Prompt:**
A smartphone mockup showing a field report form with location pin icon, timestamp field, avalanche type dropdown, and a purple Submit Queued button, beside it a sync arrow leading to a green cloud icon with checkmark, background shows a snowy mountain scene, dark UI design with emerald and purple accents, modern app design style, 16:9 aspect ratio

**Data/Artifact Reference:**
Live URL: https://avalanche-insight-hub.netlify.app (field report form on public page)

---

## Slide 26: Commercial Engagement Model

**Key Bullets:**
- Lead Developer: $45/hour
- Assistant Developer: $22/hour
- Infrastructure: $200–$500/month (Supabase + Netlify + storage)
- Maintenance retainer: $2,000–$3,000/month (monitoring, updates, bug fixes)
- 2-4 week autonomous pipeline sprint: scoped engagement, not open-ended
- No upfront licensing fees — the prototype is already built and hosted

**Speaker Notes:**
The commercial model is transparent and scoped. The prototype is already built and hosted — there's no upfront licensing fee. The engagement is time-and-materials: $45/hour for the lead developer, $22/hour for an assistant. Infrastructure costs $200-500/month depending on storage and compute usage. A maintenance retainer of $2-3K/month covers monitoring, updates, and bug fixes. The 2-4 week autonomous pipeline sprint is scoped — if it's not useful, we stop.

**Layout Guidance:**
Pricing table with three columns: Role/Item, Rate, Notes. Below: a simple bar chart showing monthly cost breakdown (infra + retainer). Bottom: "No upfront licensing — prototype is already live" badge.

**AI Image Prompt:**
A clean pricing table with three columns showing Lead Developer at 45 per hour, Assistant Developer at 22 per hour, Infrastructure at 200 to 500 per month, and Maintenance Retainer at 2000 to 3000 per month, below a simple bar chart showing monthly cost breakdown, dark background with emerald accents, professional corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/Commercials.md` — full commercial proposition

---

## Slide 27: Data Licensing & FAIR Compliance

**Key Bullets:**
- **Open-Meteo**: CC-BY 4.0 — free attribution license
- **NASA FIRMS**: Public domain — fire data for context overlays
- **Sentinel-1 (Copernicus)**: Free and open license — SAR data for research
- **EAWS Bulletins**: Public — avalanche danger level reference
- **FAIR principles**: Findable, Accessible, Interoperable, Reusable
- Synthetic data: labeled as synthetic, excluded from production claims
- Partner data: handled per agreed terms, never published without consent

**Speaker Notes:**
Every data source in the pipeline has a documented license. Open-Meteo is CC-BY 4.0. NASA FIRMS is public domain. Sentinel-1 is free and open from Copernicus. EAWS bulletins are public. We align with FAIR principles: data is findable through documented catalogs, accessible through standard APIs, interoperable through standard formats, and reusable through clear licensing. Synthetic data is always labeled as such and excluded from production claims. Partner data — if shared by DRDO — would be handled per agreed terms and never published without consent.

**Layout Guidance:**
Data source table: Source | License | Usage. FAIR principles as four icon badges along the bottom. Partner data handling note in a callout box with a lock icon.

**AI Image Prompt:**
A data licensing table showing rows for Open-Meteo CC-BY 4.0, NASA FIRMS Public Domain, Sentinel-1 Free Open License, and EAWS Bulletins Public, with four FAIR principle icons at the bottom: Findable magnifying glass, Accessible key, Interoperable puzzle piece, and Reusable refresh, dark background with emerald accents, clean corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/DATA_LICENSING_FAIR_COMPLIANCE.md` — full licensing matrix

---

## Slide 28: CAP XML Interoperability

**Key Bullets:**
- WMO Common Alerting Protocol (CAP) 1.2 — OASIS international standard
- `generate_cap_alert()` produces valid CAP XML from forecast parameters
- Maps EAWS danger levels to CAP severity (Minor → Extreme) and certainty (Possible → Observed)
- Includes: alert identifier, sender, sent time, status, scope, area polygon, effective/expires
- Scaffold ready — validation against CAP 1.2 XSD before production use
- Future: submit to national emergency pathways (NDMA, SDMA) when authorized

**Speaker Notes:**
CAP XML is the international standard for emergency alerting — used by WMO, FEMA, and national weather services. We've built a scaffold that generates CAP 1.2 XML from our forecast parameters. It maps EAWS danger levels to CAP severity and certainty values. This means when the system is ready for operational use, it can plug directly into national emergency pathways. For now, it's a scaffold — it needs XSD validation and authorization before any real submission.

**Layout Guidance:**
Code snippet showing CAP XML output with syntax highlighting. Side panel: mapping table (EAWS Level → CAP Severity → CAP Certainty). Bottom: "Scaffold — not yet submitted to any national pathway" badge.

**AI Image Prompt:**
A code editor view showing CAP XML with syntax highlighting in green and blue on dark background, side panel showing a mapping table with EAWS Danger Level 1 to 5 mapping to CAP Severity Minor to Extreme and CAP Certainty Possible to Observed, amber scaffold badge at bottom, clean technical presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/common/cap_alert.py` — CAP 1.2 XML generation scaffold

---

## Slide 29: Autonomous Pipeline Sprint Roadmap

**Key Bullets:**
- **Week 1-2 — Autonomous Pipeline Activation**: Activate autonomous data genesis (news + SAR + weather) for selected Himalayan region. Decision: Is the autonomous pipeline collecting events and generating forecasts?
- **Week 3-4 — First Forecasts + Scientist Review**: Generate first forecasts from autonomous events; scientist reviews output. Decision: Does the direction show enough signal to continue?
- **Week 4 (closeout) — Review & Decision**: Review skill scores, limitations, and next-stage scope. Decision: Continue, narrow, pause, or stop.
- Initial asks: one scientist POC, 1-2 pilot regions, operational feedback on autonomous pipeline output
- No historical data required — pipeline generates its own training data
- Honest limitations: GPxyz blocked (station coords missing), no Himalayan validation yet, SAR is shadow-gated, no operational deployment

**Speaker Notes:**
The roadmap is built around the autonomous pipeline. Week 1-2 is activation — we turn on the news extraction, SAR processing, and weather ingestion for a selected Himalayan region. The pipeline starts collecting events and training on them. Week 3-4 is the first forecasts — the model produces daily forecasts from autonomous events, and the scientist team reviews the output. Week 4 is a decision point. We ask for minimal upfront commitment: one scientist point of contact, 1-2 pilot region ideas, and operational feedback on the pipeline output. We want to be transparent about what we can't do yet: GPxyz spatial interpolation is blocked because we don't have Swiss station coordinates, we have no Himalayan validation data, SAR detection is shadow-gated (not operational), and there is no operational deployment. We are presenting a research prototype with real Swiss reproduction metrics, not a finished system.

**Layout Guidance:**
Two-column roadmap: Week 1-2 (Autonomous Pipeline Activation) | Week 3-4 (First Forecasts + Scientist Review). Each column has activities, deliverables, and a decision diamond. Bottom: "No historical data required" badge.

**AI Image Prompt:**
A two-column roadmap showing Week 1-2 Autonomous Pipeline Activation with satellite and news icons, Week 3-4 First Forecasts and Scientist Review with chart and checkmark icons, and Week 4 Closeout with diamond decision point showing continue narrow pause stop, each column has activity bullets and deliverable badges, no historical data required badge at bottom, dark background with gradient blue to emerald, clean project roadmap style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/SCIENTIST_COLLABORATION_PITCH_MVP1_MVP2.md` — autonomous pipeline sprint roadmap

---

## Slide 30: Next Steps & Contact

**Key Bullets:**
- We request an autonomous pipeline demo session — not a binding commitment
- Three aims: (1) Demo the autonomous data genesis pipeline, (2) Identify pilot regions, (3) Agree on operational feedback process
- We explicitly invite Dr. Amreek's ideas for augmentation — "I also have a few ideas to further augment it"
- Complements Dr. Praven's group: autonomous data pipeline + Swiss reproduction lane available as infrastructure for their Himalayan models
- Demo link: https://avalanche-insight-hub.netlify.app
- Scientist workspace: https://avalanche-insight-hub.netlify.app/scientist
- Admin dashboard: https://avalanche-insight-hub.netlify.app/admin (password: test123)
- Contact: Sanjay — project owner and lead developer
- No historical data required — the pipeline generates its own training data

**Speaker Notes:**
Thank you for your time. We're not asking for a large commitment — just a review discussion to determine if this direction is worth exploring together. We specifically want to hear Dr. Amreek's ideas for augmentation — he mentioned having ideas, and we want to ensure those are central to the discussion. We also want to highlight that our autonomous data pipeline and Swiss reproduction lane are available as infrastructure for Dr. Praven's group's ongoing Himalayan model work — complementing, not competing. The demo link gives you full access to the prototype, scientist workspace, and admin dashboard. If the direction seems useful, we'll share detailed templates and data dictionaries. If not, we welcome your feedback and criticism. The decision is entirely yours.

**Layout Guidance:**
Clean closing slide with: demo URL in large text, QR code linking to the live app, contact information, and three next-step bullets. Minimal design — let the call to action stand alone. Dark background with emerald accent line.

**AI Image Prompt:**
A clean closing presentation slide with a large QR code centered, demo URL text below it reading avalanche-insight-hub.netlify.app, three next-step bullets on the left, contact information on the right, dark background with a single emerald accent line at the bottom, minimalist corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
Live URL: https://avalanche-insight-hub.netlify.app

---

## Slide 31 (Appendix A): SHAP Explainability — Feature Attribution

**Key Bullets:**
- TreeSHAP applied to Swiss RF4 model (500 test samples, 74 features)
- Top 5 drivers: elevation (0.078), 72h new snow (0.046), 7-day new snow (0.035), penetration depth (0.026), 24h new snow (0.026)
- SHAP narratives: "Primary risk drivers: elevation (increases risk), 24-hour snowfall (increases risk). Risk suppressors: snow settlement rate (reduces risk)."
- Validated by Pérez-Guillén et al. (2025, NHESS) — SHAP is recommended for operational avalanche forecasting explainability
- Per-prediction narratives available in UI for every forecast cell

**Speaker Notes:**
This slide shows our TreeSHAP explainability results. SHAP — SHapley Additive exPlanations — is the state-of-the-art method for interpreting tree-based models. We applied it to our Swiss RF4 reproduction with 500 test samples and all 74 features. The top drivers are elevation, 72-hour new snow accumulation, and 7-day new snow — exactly the features that avalanche forecasters identify as critical. This is not just a black box: for every forecast cell in our system, we generate a human-readable narrative explaining which factors are increasing risk and which are reducing it. Pérez-Guillén et al. in their 2025 NHESS paper explicitly recommend SHAP for operational avalanche forecasting explainability — we are following their methodology.

**Layout Guidance:**
Horizontal bar chart showing top 10 features by mean absolute SHAP value, sorted descending. Feature names on y-axis, SHAP value on x-axis. Color gradient from emerald (high importance) to light blue (low). Inset box with example narrative text.

**AI Image Prompt:**
A scientific presentation slide showing a horizontal bar chart of SHAP feature importance for an avalanche forecasting model, top 10 features listed on the y-axis with bars extending rightward, emerald green and blue color gradient, an inset text box showing an example explanation narrative, clean white background with dark text, scientific data visualization style, 16:9 aspect ratio

**Data/Artifact Reference:**
`backend/reproduction/artifacts/rf4_shap_values.json`

---

## Slide 32 (Appendix B): How We Compare — SOTA Systems Matrix

**Key Bullets:**
- **Swiss RAvaFcast (RF4)**: 89.5% accuracy, isotonic calibration, TreeSHAP — our reproduction lane
- **HIM-STRAT (DGRE)**: Neural network snowpack simulation for NW Himalaya — we extend, not replace
- **EGU 2026 (Pérez-Guillén et al.)**: Transfer learning Swiss to NW Himalaya validated — our exact approach
- **CCDT-ADA-Net (IEEE 2026)**: ROC-AUC=0.99, multimodal SAR+optical+snowpack fusion — Phase 2 target
- **Google Groundsource**: LLM-based news extraction for natural hazards — our autonomous data genesis
- **Norwegian SAR (SnoSat)**: Sentinel-1 wet-snow change detection — our SAR pipeline follows this approach
- **NATSAT (DRDO-ISRO)**: Satellite-based alert dissemination — we complement, not compete

**Speaker Notes:**
This comparison table shows that we are aware of the state of the art and position our work relative to each system. We are not claiming to be better than all of these — we are showing that we know the landscape and have designed our system to complement and extend existing work. Our Swiss reproduction validates our methodology. HIM-STRAT is DGRE's own model — we extend it with continuous data. The EGU 2026 paper validates Swiss-to-Himalayan transfer learning — exactly our approach. CCDT-ADA-Net's multimodal fusion is our Phase 2 target. Google Groundsource is our news extraction methodology. NATSAT is DRDO's alert system — we complement it.

**Layout Guidance:**
Table with 7 rows (systems) and 4 columns (System, Method, Key Metric, Our Relation). Alternating row shading. Highlight "Our Relation" column with emerald accent.

**AI Image Prompt:**
A presentation slide with a clean comparison table showing 7 state-of-the-art avalanche forecasting systems, columns for System Name, Method, Key Metric, and Our Relation, alternating light gray and white row shading, emerald green accent on the last column, dark header row, professional corporate presentation style, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/MEETING_HANDOUTS_JUNE24.md` Section 3

---

## Slide 33 (Appendix C): Data Sources and ISRO Collaboration Potential

**Key Bullets:**
- **Open-Meteo Forecast API**: Deterministic weather (free, no auth) — operational now
- **Open-Meteo Ensemble API**: Probabilistic p10/p50/p90 percentiles — integrated, pending UI rendering
- **Open-Meteo Archive API**: Historical weather backfill (7-day windows) — operational
- **Google Earth Engine**: Sentinel-1 SAR scenes (terrain-masked wet-snow detection) — operational
- **ASF Search API**: Sentinel-1 metadata search (no auth) — operational
- **Gemini LLM**: Avalanche news extraction from Google Groundsource methodology — operational
- **DRDO-ISRO MoU potential**: High-resolution meteorological forecasts, satellite snow cover retrieval, NATSAT integration
- **HIM-STRAT integration**: Feed our continuous weather + SAR + news data into DGRE's neural network snowpack models

**Speaker Notes:**
This slide shows our data sources and the ISRO collaboration potential. All our current data sources are free and require no authentication — Open-Meteo for weather, Google Earth Engine for SAR, Gemini for news extraction. The Open-Meteo Ensemble API gives us probabilistic weather with p10, p50, and p90 percentiles — we've integrated it into our inference pipeline. The DRDO-ISRO MoU opens the door to high-resolution meteorological forecasts and satellite snow cover retrieval that would dramatically improve our Himalayan accuracy. And our autonomous data pipeline can feed continuous data into HIM-STRAT — DGRE's own neural network snowpack model — extending its capability without replacing it.

**Layout Guidance:**
Two-column layout: left column lists data sources with icons (weather, satellite, news, snowpack), right column lists ISRO collaboration opportunities with arrows showing data flow. Bottom bar with "All current sources: free, no auth required" in emerald.

**AI Image Prompt:**
A presentation slide with a two-column layout, left side showing data source icons for weather API, satellite imagery, news extraction, and snowpack data with labels, right side showing ISRO collaboration opportunities with arrows connecting data flows, emerald green accent bar at the bottom reading "All current sources: free, no auth required", clean modern design with dark text on white background, 16:9 aspect ratio

**Data/Artifact Reference:**
`docs/MVP_V2/00_start_here/MEETING_HANDOUTS_JUNE24.md` Section 5
