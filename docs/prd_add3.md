Based on our ultra-deep analysis of the 15 systemic challenges and the operational realities of Himalayan avalanche forecasting, this blueprint Abandons expensive, synchronous cloud GPUs in favor of a **Zero-to-Low-Cost, Asynchronous, Hybrid Architecture**. 

---

### 1. High-Level Architecture Blueprint

**The Core Paradigm Shift:** Your web app frontend (React/Leaflet/3D Voxel) and database (Supabase) remain the presentation and storage layers. However, all heavy mathematical lifting (Feature Selection, KMeansSMOTE, Inference, Runout Physics) is entirely decoupled from the serverless edge functions and moved to **Offline Batch Processing (GitHub Actions / Lightweight VPS)**.

#### Architecture Components
1. **Frontend (Client-Side):** React.js + Leaflet (2D Map) + Three.js/Arnis (3D Voxels). PWA enabled with Service Workers for offline capabilities.
2. **Database & Realtime (BaaS):** Supabase (PostgreSQL + PostGIS). Houses `avalanche_events` (ground truth) and `forecast_grids` (pre-computed JSONB payloads).
3. **Automated ML Pipeline (CI/CD):** GitHub Actions (Ubuntu runner). Runs weekly model retraining (`train_model.py`) and daily spatial inference (`daily_inference.py`).
4. **Data Oracles (APIs):** Open-Meteo (Weather), Google Earth Engine (Sentinel-1/2 SAR ground truth), Gemini API (News Groundsource), Open-Elevation DEM.

---

### 2. API Specifications & Database RPCs

Instruct  to implement the following explicit interfaces to connect the frontend, database, and offline ML pipeline.

#### A. Supabase Database Schema & RPCs
*   **`forecast_grids` Table:**
    *   Columns: `id`, `region_id`, `forecast_date` (DATE), `grid_geojson` (JSONB), `runout_polygons` (JSONB), `created_at`.
*   **RPC 1: `ingest_event_with_topo(lat, lng, description, source, hazard_type)`**
    *   **Logic:** When the PWA or Gemini Groundsource posts an event, this Postgres function triggers an HTTP request to Open-Elevation (or extracts from a loaded PostGIS DEM raster) to calculate `elevation`, `slope_angle`, and `aspect`.
    *   **Insert:** Saves the event into `avalanche_events` with the Class-III topographical data appended.
*   **API Endpoint 2: `GET /rest/v1/forecast_grids?region_id=eq.{id}&order=forecast_date.desc&limit=1`**
    *   **Logic:** The frontend uses this to instantly load the day's pre-computed 20x20 risk grid, probabilities, uncertainty bounds, and SHAP values. **Zero ML inference happens here.**

#### B. The Offline Python ML Pipeline (GitHub Actions / VPS)
*   **`gee_extractor.py` (Runs Weekly):**
    *   Connects to Google Earth Engine Python API.
    *   Queries `COPERNICUS/S1_GRD` for the past 7 days over defined bounding boxes. Applies VV/VH backscatter thresholding to detect wet-snow debris.
    *   Pushes detected polygon centroids to Supabase `avalanche_events` with `source='gee_sar'`.
*   **`train_model.py` (Runs Weekly):**
    *   Fetches all `avalanche_events` and historical Open-Meteo data from Supabase.
    *   Calculates the **HIM-STRAT proxies** (estimated RAM resistance and shear strength).
    *   Applies `KMeansSMOTE` (from `imbalanced-learn`) to synthesize rare avalanche events.
    *   Applies `RFE` with `SVC(kernel="linear")` to prune 40+ weather features down to the top 15.
    *   Trains a `RandomForestClassifier(class_weight={0:1, 1:4})` wrapped in `CalibratedClassifierCV(method='isotonic')`.
    *   Validates using Peirce Skill Score (PSS > 0.45 threshold). Saves `.joblib` model artifact.
*   **`daily_inference.py` (Runs Daily at 01:00 UTC):**
    *   Downloads `.joblib`, fetches 72h Open-Meteo forecast.
    *   Runs inference across the 20x20 grid coordinates. Calculates `.predict_proba()` and extracts variance across the RF estimators for uncertainty bounds.
    *   Filters cells with probability > 0.65. Passes these to `WhiteboxTools` (`wbt.avalanche_runout()`) over the local DEM to calculate Alpha-Beta physical runout paths.
    *   Uploads the final `grid_geojson` and `runout_polygons` JSONB to Supabase.

---

### 3. Key Implementation Points for 

When prompting , explicitly provide these mathematical and logic rules:
1.  **Temporal Feature Engineering:** Instruct  that the input to the Random Forest is *not* just instantaneous weather. It must engineer `Rain48h`, `FreshSnow72h`, and `TemperatureGradient24h`.
2.  **The HIM-STRAT Proxy Code:** Instruct  to write a lightweight pre-processing function that estimates internal snowpack stability (Class-II data) based on cumulative seasonal temperature and precipitation. *Code context: `def calculate_snowpack_proxies(weather_timeseries): return estimated_shear_strength, estimated_settlement`*.
3.  **Uncertainty Calculation:** Do not let  use raw `.predict_proba()` for uncertainty. It must extract the individual tree predictions: `predictions = [tree.predict_proba(X) for tree in rf.estimators_]`, then calculate the variance across `predictions` to generate `confidence_lower` and `confidence_upper`.
4.  **Non-Compensatory Mapping:** Ensure the frontend 3D voxel color logic implements strict physical cutoffs (e.g., `if cell.slope_angle < 15: cell.color = 'Green' (Safe)` regardless of the ML weather probability).

---

### 4. Refined & Expanded 6 additional User Stories for Implementation

User Story 16: True Epistemic Uncertainty Visualization As a backcountry user, I want to see uncertainty bands on the risk map, so that I know when the AI is guessing due to poor data.
AC 1 (Scikit-learn Bug Fix): The backend MUST calculate confidence_lower and confidence_upper by extracting the variance across the raw Random Forest estimators (rf.estimators_) before wrapping the model in IsotonicRegression for probability calibration.
AC 2: The grid_geojson payload includes probability_calibrated, confidence_lower, and confidence_upper.
AC 3: If (confidence_upper - confidence_lower) > 0.30, the React 3D Voxel cell renders as Grey (Uncertain) and overlays a "?" icon in 2D mode, overriding EAWS colors.
User Story 17: Offline-First Field Reporting (PWA) As a backcountry skier without cell service, I want to log an avalanche on the mountain, so that it syncs to the AI dataset when I return to town.
AC 1: Use Google Workbox to implement a Service Worker with BackgroundSync.
AC 2: POST requests to /rest/v1/rpc/ingest_event_with_topo are caught and stored in IndexedDB when navigator.onLine is false.
AC 3: Upon online event firing, queued events dispatch with a toast: "Syncing X offline reports...".
User Story 18: Alpha-Beta Physical Runout Overlays (OOM Crash Protected) As a local civil defense planner, I want to see the physical runout paths of potential avalanches, so that I know if a road will be buried.
AC 1 (Memory Crash Fix): Before passing high-risk cells (Probability > 0.65) to WhiteboxTools, the backend MUST use rasterio to dynamically crop the DEM to a 5km bounding box around the cell to prevent Out-Of-Memory (OOM) crashes in GitHub Actions.
AC 2: The calculated runout_polygons render on the frontend as semi-transparent red #ff0000 with a dashed border via an "Impact Runout" toggle.
AC 3: Turf.js is used client-side to calculate intersections with OSM road vectors, appending a "Warning" marker to the road if intersected.
User Story 19: Feature-Optimized SHAP Interpretability As a forecaster, I want the SHAP explanations to only show the most critical weather features, so that the UI isn't cluttered with redundant data.
AC 1: The backend SVM-RFE output guarantees exactly 15 pruned features. The frontend Recharts component slices the SHAP array to display only the Top 5 absolute contributors
.
AC 2: SHAP mapping dictionary translates raw variable names to plain-text sentences (e.g., FS72 > 0.5 -> "High risk driven primarily by heavy 3-day snowfall").
User Story 20: Class-II Snowpack Proxy Visibility (Seasonal Memory Fix) As a 40-year veteran forecaster, I want to see the estimated internal snowpack stability metrics alongside weather data, so I know the model isn't ignoring internal physical mechanics.
AC 1 (72h Contradiction Fix): The backend snowpack_proxy.py MUST calculate HIM-STRAT proxies using cumulative temperature and precipitation from the start of the winter season (e.g., Nov 1st), not just a 72h window, to respect snowpack memory physics
.
AC 2: The Expert Mode UI displays the backend-calculated estimated_shear_strength and snow_settlement_index for the selected cell.
User Story 21: Climate Concept Drift Adaptation & Ground Truth Integrity As a system administrator, I want the model to automatically retrain weekly using verified ground truth, adapting to climate change without data leakage.
AC 1 (Data Leakage Fix): The GitHub Action training script MUST use TimeSeriesSplit (Chronological Cross-Validation), never random shuffling, to evaluate the model against temporal autocorrelation
.
AC 2 (Release Zone Mismatch Fix): Gemini Groundsource events indicating valley "deposit zones" rather than mountain "release zones" must be flagged training_eligible = false in PostGIS so they map to the UI but do not poison physics training
.
AC 3 (SAR Shadow Fix): The GEE Python script MUST apply a SRTM DEM Layover and Shadow Mask before VV/VH thresholding to prevent radar shadows from being logged as false avalanches
.
AC 4: The model artifact .joblib is only deployed if the Peirce Skill Score (PSS) > 0.45
.

---

Advanced Scientific Architecture Stories (16-21) 16. True Epistemic Uncertainty: RF variance extraction before Isotonic Calibration; Grey Voxels for low confidence (>30% variance). 17. Offline-First PWA: Google Workbox Service Worker caches reports via IndexedDB when offline; syncs when online. 18. Alpha-Beta Runout Overlays: WhiteboxTools calculates flow paths on dynamically rasterio-cropped 5km DEMs to prevent OOM crashes; Turf.js flags road intersections. 19. Feature-Optimized SHAP: Backend SVM-RFE trims to 15 features
; frontend limits to Top 5 absolute contributors translated to plain text. 20. Class-II Proxy Visibility: snowpack_proxy.py calculates HIM-STRAT proxies using seasonal cumulative inputs (from Nov 1); displayed in Expert Mode. 21. Climate Concept Drift & Data Integrity: GitHub Actions retrains weekly using TimeSeriesSplit; rejects deposit-zone Gemini news (training_eligible=false) and masked SAR shadows; requires PSS > 0.45.

We are implementing the finalized architecture for 'Avalanche Insight Hub'. You must upgrade the repository to satisfy our Unified PRD. Do not delete existing UI features (share links, export, admin panel).
Phase 1: Database & PWA Updates
Update the Supabase schema: Add elevation, slope_angle, aspect, and training_eligible (boolean, default true) to avalanche_events.
Create the forecast_grids table with columns: region_id, forecast_date, grid_geojson (JSONB), and runout_polygons (JSONB).
Update the ingest_event Edge Function: Ping the Open-Elevation API to populate the topographical columns. If Gemini determines the event describes a valley "deposit zone" rather than a mountain "release zone", set training_eligible = false.
Implement User Story 17: Configure Google Workbox in the React frontend with BackgroundSync to cache POST requests to ingest_event in IndexedDB when offline.
Phase 2: Frontend UX Adjustments
Implement User Story 16: Update the 3D Voxel view. If the incoming JSON properties.confidence_upper - properties.confidence_lower > 0.30, render the voxel material as Grey (#808080) overriding the EAWS color.
Implement User Story 19: Slice the SHAP Recharts array to display only the Top 5 absolute values.
Implement User Story 20: Add a "Simulated Snowpack" section in the Expert Mode UI displaying estimated_shear_strength and snow_settlement_index from the grid JSON.
Phase 3: The Asynchronous Python Backend (GitHub Actions) Scaffold a /backend/ directory with the following scripts designed for Ubuntu runners (Do NOT place ML inference in Edge Functions):
gee_extractor.py: Use earthengine-api. Apply an SRTM DEM Layover and Shadow Mask to exclude steep radar shadows, then apply VV/VH thresholding for Sentinel-1 wet-snow detection. Push centroids to Supabase.
train_model.py:
Fetch avalanche_events where training_eligible = true.
Apply KMeansSMOTE(k=5) and RFE(estimator=SVC(kernel='linear'), n_features_to_select=15).
Train a RandomForestClassifier(class_weight={0:1, 1:4}).
CRITICAL: Extract tree variance first: np.std([tree.predict_proba(X) for tree in rf.estimators_], axis=0) to define bounds, then wrap the model in CalibratedClassifierCV(method='isotonic') to calibrate the mean.
Validate strictly using TimeSeriesSplit (chronological, no random shuffling). Save .joblib only if PSS > 0.45.
daily_inference.py:
Calculate HIM-STRAT seasonal proxies using weather data stretching back to Nov 1st (not just 72h).
Run inference on the 20x20 grid.
CRITICAL: For cells with Probability > 0.65, use rasterio to crop the DEM to a 5km bounding box before executing WhiteboxTools Alpha-Beta runout to prevent Out-Of-Memory (OOM) crashes.
Push the final JSONB payload to forecast_grids.
Acknowledge these rigorous scientific constraints and begin executing Phase 1.
