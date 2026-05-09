# Technical Glossary And Acronyms

Updated: May 8, 2026

## How To Use This Glossary

Each entry follows the same format:

- **Full name**
- **Simple explanation**
- **Why it matters here**
- **Where it appears in this platform**

The goal is to make scientist and developer discussions easier without assuming prior web, machine-learning, or avalanche-software experience.

## Admin Route

- **Full name:** Administration route
- **Simple explanation:** A restricted part of the website used for internal observability, control, and review rather than public forecast reading.
- **Why it matters here:** It shows model status, release evidence, benchmark summaries, and provenance that are too detailed for the public route.
- **Where it appears in this platform:** `src/pages/AdminPage.tsx`, `src/components/AdminDashboard.tsx`, route `/admin`

## APT

- **Full name:** Avalanche-Prone Terrain
- **Simple explanation:** Terrain that is relevant to avalanche hazard, as opposed to terrain that should not be interpreted as avalanche risk terrain.
- **Why it matters here:** The platform uses masking so out-of-scope terrain does not look like a genuine low-risk forecast.
- **Where it appears in this platform:** public map semantics, bulletin framing, `docs/MVP/source/Demo_decision_brief.md`

## Artifact Manifest

- **Full name:** Artifact manifest
- **Simple explanation:** A small file that describes a larger package of forecast files, including what files exist and where they are stored.
- **Why it matters here:** The live platform downloads prepared forecast packages from storage instead of recomputing them in the browser.
- **Where it appears in this platform:** `src/lib/forecastArtifacts.ts`, `forecast_runs` storage references, published forecast artifacts

## API

- **Full name:** Application Programming Interface
- **Simple explanation:** A defined way for one software component to talk to another software component.
- **Why it matters here:** The browser talks to backend services, storage, and server-side functions through APIs rather than by reading raw files directly.
- **Where it appears in this platform:** Supabase client usage, Edge Function calls, storage downloads, browser and background-sync flows

## Batch-First Delivery

- **Full name:** Batch-first delivery
- **Simple explanation:** A design where the heavy computation is performed ahead of time, and the website later serves the finished result.
- **Why it matters here:** It keeps the live forecast experience fast and operationally stable.
- **Where it appears in this platform:** `backend/daily_inference.py`, forecast artifact publication flow, public route loading behavior

## Benchmark

- **Full name:** Benchmark
- **Simple explanation:** A controlled way of measuring how well a model or workflow performs against a known set of test cases or metrics.
- **Why it matters here:** Candidate models should only be promoted if they beat or justify themselves against the current baseline on agreed evaluation slices.
- **Where it appears in this platform:** model-status summaries, evaluation artifacts, `docs/MVP/source/Scientist_benchmark_pack_v0.md`

## Brier Score

- **Full name:** Brier Score
- **Simple explanation:** A metric that checks how well predicted probabilities match real outcomes. Lower is better.
- **Why it matters here:** The platform uses probability-based hazard scoring, so calibration matters, not just yes-or-no accuracy.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, benchmark summaries, candidate-gate logic

## Calibration

- **Full name:** Probability calibration
- **Simple explanation:** The process of making predicted probabilities better match real-world frequencies.
- **Why it matters here:** A model that says “80% likely” should be right about 80% of the time in the long run, otherwise its confidence language becomes misleading.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, `backend/lstm_model.py`, training and evaluation logic

## Candidate Model

- **Full name:** Candidate model
- **Simple explanation:** A model that exists in the system but is not yet the active public model.
- **Why it matters here:** The platform already contains stronger or more experimental paths, but they stay blocked until evidence justifies promotion.
- **Where it appears in this platform:** `model_status`, `backend/common/model_status_state.py`, `backend/lstm_model.py`

## CPU

- **Full name:** Central Processing Unit
- **Simple explanation:** The general-purpose processor used for many ordinary computing tasks.
- **Why it matters here:** Some remote inference in this platform still runs in CPU-and-memory-sized environments rather than on a GPU.
- **Where it appears in this platform:** `backend/modal_worker_app.py`, Modal.com remote inference configuration

## DEM

- **Full name:** Digital Elevation Model
- **Simple explanation:** A digital terrain surface that describes elevation across the landscape.
- **Why it matters here:** Avalanche forecasting depends heavily on slope, elevation, aspect, and other terrain-derived features.
- **Where it appears in this platform:** `backend/common/real_features.py`, Modal.com volumes for DEM assets, terrain feature engineering

## Edge Function

- **Full name:** Edge Function
- **Simple explanation:** A lightweight server-side function that runs close to users instead of inside the browser.
- **Why it matters here:** The platform uses Edge Functions for selected backend tasks such as enrichment, event handling, and evaluation helpers.
- **Where it appears in this platform:** `supabase/functions/*`, Supabase-based server-side routes

## Forecast Bulletin

- **Full name:** Forecast bulletin
- **Simple explanation:** A structured summary of avalanche hazard that explains danger, problem framing, uncertainty, and terrain relevance.
- **Why it matters here:** The platform is not only a model viewer; it turns model output into a usable operational communication layer.
- **Where it appears in this platform:** `backend/common/forecast_bulletins.py`, public route bulletin components

## GPU

- **Full name:** Graphics Processing Unit
- **Simple explanation:** A specialized processor built to perform many mathematical operations in parallel.
- **Why it matters here:** Deep-learning training and image-style segmentation often run much faster on a GPU than on a regular CPU because they involve large repeated matrix operations.
- **Where it appears in this platform:** `backend/modal_worker_app.py`, Modal.com worker configuration, SAR and MTS-LSTM training paths

## IndexedDB

- **Full name:** IndexedDB
- **Simple explanation:** A browser-side database for storing structured data locally on a device.
- **Why it matters here:** It allows field reports to be queued locally when connectivity is weak.
- **Where it appears in this platform:** `src/lib/offlineFieldReports.ts`

## JSON

- **Full name:** JavaScript Object Notation
- **Simple explanation:** A text format used for structured data exchange between software components.
- **Why it matters here:** Forecast manifests, hourly payloads, and many backend or frontend data structures are stored or exchanged as JSON.
- **Where it appears in this platform:** `src/lib/forecastArtifacts.ts`, Supabase responses, forecast artifact files

## Inference

- **Full name:** Inference
- **Simple explanation:** The process of using a trained model to produce a prediction.
- **Why it matters here:** Training builds the model; inference uses the model to score forecast cells or candidate runs.
- **Where it appears in this platform:** `backend/daily_inference.py`, `backend/modal_worker_app.py`, `backend/scripts/trigger_and_poll_inference.py`

## LSTM

- **Full name:** Long Short-Term Memory
- **Simple explanation:** A type of neural network designed to learn from sequences over time.
- **Why it matters here:** Avalanche conditions depend on how weather and snow evolve across time, not only on a single snapshot.
- **Where it appears in this platform:** `backend/lstm_model.py`, candidate sequence-model workflow

## Modal.com

- **Full name:** Modal.com
- **Simple explanation:** A cloud execution platform used here to run heavier model-training and remote-sensing jobs away from the public website.
- **Why it matters here:** It provides remote workers, attached storage volumes, and optional GPU hardware without pushing those heavy dependencies into the web app.
- **Where it appears in this platform:** `backend/modal_worker_app.py`, `docs/MODAL_WORKER.md`, training and segmentation trigger scripts

## MTS-LSTM

- **Full name:** Multi-Time-Scale Long Short-Term Memory
- **Simple explanation:** A sequence model that tries to learn patterns across more than one time scale, such as shorter and longer weather windows.
- **Why it matters here:** It is the main candidate path for moving beyond the current tree-based baseline while still keeping promotion gated.
- **Where it appears in this platform:** `backend/lstm_model.py`, `backend/train_model.py`, `backend/modal_worker_app.py`

## Postgres

- **Full name:** PostgreSQL, commonly called Postgres
- **Simple explanation:** A widely used open-source relational database system.
- **Why it matters here:** It stores structured records such as forecast runs, publication events, reports, and model-status summaries.
- **Where it appears in this platform:** Supabase database layer, `src/integrations/supabase/types.ts`, database migrations

## PSS

- **Full name:** Peirce Skill Score
- **Simple explanation:** A performance metric that compares true positive rate and false positive rate. Higher is better.
- **Why it matters here:** Avalanche events are rare, so the system needs a metric that is more informative than simple accuracy.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, candidate-model gate summaries, training metrics

## PWA

- **Full name:** Progressive Web App
- **Simple explanation:** A website that uses browser features to behave more like an installable application, including offline support and background behavior.
- **Why it matters here:** It helps field-report capture remain usable when connectivity is unreliable.
- **Where it appears in this platform:** `src/lib/pwa.ts`, offline queue behavior, service-worker registration

## Random Forest

- **Full name:** Random Forest
- **Simple explanation:** A machine-learning method that combines many decision trees to make a final prediction.
- **Why it matters here:** It is the current active live scorer because it is practical, governable, and compatible with explanation tooling.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, `backend/train_model.py`, `backend/daily_inference.py`

## React

- **Full name:** React
- **Simple explanation:** A user-interface library for building web applications out of reusable components.
- **Why it matters here:** It powers the website screens, stateful interactions, and route rendering.
- **Where it appears in this platform:** `src/main.tsx`, `src/App.tsx`, all frontend components and pages

## Row-Level Security

- **Full name:** Row-Level Security
- **Simple explanation:** A database feature that controls which rows a user is allowed to read or change.
- **Why it matters here:** It helps separate public access, authenticated access, and administration access safely.
- **Where it appears in this platform:** Supabase database policies, authentication and storage access rules

## SAR

- **Full name:** Synthetic Aperture Radar
- **Simple explanation:** A radar imaging method used by satellites to observe the Earth regardless of daylight and with strong resistance to cloud interference.
- **Why it matters here:** It offers a weather-independent remote-sensing evidence path that may help avalanche detection and coverage analysis in the future.
- **Where it appears in this platform:** `backend/sar_unet_worker.py`, `backend/sar_unet_training.py`, SAR artifact fields, candidate evidence workflows

## Sentinel-1

- **Full name:** Sentinel-1
- **Simple explanation:** A European satellite mission that carries a C-band Synthetic Aperture Radar instrument.
- **Why it matters here:** It is the remote-sensing context behind the platform’s SAR-related work and terminology.
- **Where it appears in this platform:** SAR evidence discussions, SAR qualification path, external remote-sensing grounding

## Service Worker

- **Full name:** Service Worker
- **Simple explanation:** A browser background process that can intercept network activity, cache files, and manage offline or deferred tasks.
- **Why it matters here:** It supports offline readiness and queued field-report replay.
- **Where it appears in this platform:** `src/lib/pwa.ts`, Vite PWA integration, background sync behavior

## SHAP

- **Full name:** SHapley Additive exPlanations
- **Simple explanation:** A family of explanation methods that estimate how much each input feature contributed to a model output.
- **Why it matters here:** It helps explain why the platform’s tree-based hazard model produced a particular result.
- **Where it appears in this platform:** explanation surfaces, TreeSHAP workflow, `backend/models/surrogate_rf.py`

## Single-Page Application

- **Full name:** Single-Page Application
- **Simple explanation:** A web application that loads once and then updates the visible screen dynamically without full page reloads for each interaction.
- **Why it matters here:** It allows the forecast workspace to behave like a richer application rather than a sequence of static pages.
- **Where it appears in this platform:** React frontend, `src/App.tsx`, browser route handling

## Supabase

- **Full name:** Supabase
- **Simple explanation:** A backend platform that combines a Postgres database, authentication, storage, and server-side functions.
- **Why it matters here:** It is the main application backend used by the web platform.
- **Where it appears in this platform:** `src/integrations/supabase/client.ts`, `src/integrations/supabase/types.ts`, `supabase/functions/*`

## TanStack Query

- **Full name:** TanStack Query
- **Simple explanation:** A library for fetching, caching, and updating server-side data in web applications.
- **Why it matters here:** It provides the frontend with a standard pattern for managing server-state interactions.
- **Where it appears in this platform:** `src/App.tsx` through `QueryClientProvider`

## Training

- **Full name:** Model training
- **Simple explanation:** The process of fitting a model to historical data so it can later make predictions.
- **Why it matters here:** Training creates both the active baseline artifacts and the candidate-model artifacts used in shadow evaluation.
- **Where it appears in this platform:** `backend/train_model.py`, remote training paths in `backend/modal_worker_app.py`

## TreeSHAP

- **Full name:** Tree SHapley Additive exPlanations
- **Simple explanation:** A SHAP method specialized for tree-based models such as Random Forest models.
- **Why it matters here:** It explains the current live scorer without replacing it.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, `src/lib/shapLoader.ts`, public inspection flows

## U-Net

- **Full name:** U-Net
- **Simple explanation:** A neural-network architecture commonly used for image segmentation, where the goal is to label pixels or image regions.
- **Why it matters here:** The platform’s candidate SAR path uses U-Net style model families for segmentation of radar scenes.
- **Where it appears in this platform:** `backend/sar_unet_worker.py`, `backend/sar_unet_training.py`, `backend/common/sar_model_family.py`

## Vite

- **Full name:** Vite
- **Simple explanation:** A modern frontend build tool that provides fast development serving and optimized production bundles.
- **Why it matters here:** It builds and serves the React web application.
- **Where it appears in this platform:** `package.json` build scripts, `vite.config.ts`, frontend runtime setup

## Architecture Addendum Terms

The terms below are especially important for Deck 3 and for the future offline-batch architecture in `docs/prd_add3.md`.

## Alpha-Beta Runout

- **Full name:** Alpha-Beta physical runout estimation
- **Simple explanation:** A terrain-based method for estimating how far avalanche debris may travel downslope.
- **Why it matters here:** It supports consequence-aware review for roads, settlements, and mapped assets, but it still needs implementation and validation before stronger claims.
- **Where it appears in this platform:** proposed WhiteboxTools runout path in `docs/prd_add3.md`, future architecture addendum, runout-overlay discussions

## Forecast Grid

- **Full name:** Forecast grid
- **Simple explanation:** A spatial grid of forecast cells, where each cell can carry probability, danger level, uncertainty, explanation values, or runout references.
- **Why it matters here:** It is the map-shaped forecast data that the UI turns into cells, bulletins, and detail views.
- **Where it appears in this platform:** current artifact payloads, proposed `forecast_grids` table in `docs/prd_add3.md`

## Forecast Run

- **Full name:** Forecast run
- **Simple explanation:** A packaged forecast publication event with metadata about date, region, model version, artifact locations, and freshness.
- **Why it matters here:** It lets the platform distinguish the latest published forecast from same-day freshness.
- **Where it appears in this platform:** `forecast_runs`, artifact manifests, public model-status wording, admin publication surfaces

## GitHub Actions

- **Full name:** GitHub Actions
- **Simple explanation:** GitHub's automation runner system for scheduled jobs, tests, and build tasks.
- **Why it matters here:** It is one proposed low-cost place to run offline batch forecast jobs without putting heavy math inside Supabase Edge Functions.
- **Where it appears in this platform:** future offline-batch architecture direction in `docs/prd_add3.md`

## KMeansSMOTE

- **Full name:** KMeans Synthetic Minority Oversampling Technique
- **Simple explanation:** A rare-event class-balancing method that groups minority examples and synthesizes additional training samples.
- **Why it matters here:** Avalanche events are rare, so training needs rare-event-aware handling instead of generic accuracy framing.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, `backend/train_model.py`, PRD feature-selection and training discussions

## Lightweight VPS

- **Full name:** Lightweight Virtual Private Server
- **Simple explanation:** A low-cost rented server used to run scheduled backend jobs when CI runners or serverless functions are not enough.
- **Why it matters here:** It is a practical fallback or complement for offline batch processing when jobs outgrow GitHub Actions limits.
- **Where it appears in this platform:** future offline-batch architecture direction in `docs/prd_add3.md`

## PostGIS

- **Full name:** PostGIS
- **Simple explanation:** A geospatial extension for Postgres that adds geometry, geography, raster, and spatial-query capabilities.
- **Why it matters here:** It can support terrain enrichment, geospatial filtering, and spatial relationships directly inside the database.
- **Where it appears in this platform:** proposed terrain enrichment and geospatial storage direction in `docs/prd_add3.md`

## Proof Bucket

- **Full name:** Proof bucket
- **Simple explanation:** A label that states how a claim is proven.
- **Why it matters here:** It prevents slide builders from presenting internal, gated, or proposed capabilities as if they were public-route proof.
- **Where it appears in this platform:** MVP deck source files, claim ledger, evidence map, proof manifest

## Recursive Feature Elimination

- **Full name:** Recursive Feature Elimination (RFE)
- **Simple explanation:** A feature-selection technique that repeatedly removes weaker inputs until a smaller feature set remains.
- **Why it matters here:** It keeps model inputs disciplined and supports cleaner SHAP explanations.
- **Where it appears in this platform:** `backend/models/surrogate_rf.py`, `backend/train_model.py`, PRD feature-optimized SHAP discussions

## Repo/Admin Verified

- **Full name:** Repo/admin verified
- **Simple explanation:** A proof bucket for capabilities implemented and inspectable in source, tests, artifacts, or authenticated admin/operator surfaces, but not necessarily visible to public users.
- **Why it matters here:** It is real implementation evidence, but it should not be confused with a public website screenshot.
- **Where it appears in this platform:** MVP deck source files, claim ledger, evidence map, proof manifest

## Stale Published Batch

- **Full name:** Stale published batch
- **Simple explanation:** A forecast artifact that is successfully published and usable, but older than the target publication date.
- **Why it matters here:** Stale-state language remains necessary when no same-day artifact exists. The current May 8 hosted public proof is not stale; it is same-day full-grid technical publication evidence with `sameDayPublished=true`.
- **Where it appears in this platform:** public model-status wording, proof manifest, deck-source screenshot captions, fallback-state copy

## WhiteboxTools

- **Full name:** WhiteboxTools
- **Simple explanation:** A geospatial analysis toolkit for terrain and raster processing.
- **Why it matters here:** It is the proposed tool for Alpha-Beta runout processing in the PRD, but it remains proposed or exploratory until implementation and validation artifacts prove it.
- **Where it appears in this platform:** proposed runout architecture in `docs/prd_add3.md`
