Based on an ultra-deep synthesis of your existing web app infrastructure (`PRD.md`), the adversarial constraints of a solo developer, and the cutting-edge 2024–2025 academic research on avalanche forecasting, I have designed a **Zero-Cost, High-Accuracy Asynchronous Architecture Plan**. 

This plan abandons expensive, synchronous GPU deep-learning (which fails due to hardware costs and spatial data bottlenecks) and instead leverages **Automated CI/CD Pipelines (GitHub Actions)**, **Google Earth Engine (GEE)**, and **Class-Balanced Machine Learning (Random Forest + SVM-RFE)**. 

Here is the exact, step-by-step blueprint with critical instructions, user stories, and API endpoints formatted specifically for your AI coding assistant (Codex/Windsurf) to implement.

---

# 🏔️ Avalanche Insight Hub: Codex Implementation Blueprint

**Context for Codex:** You are upgrading an existing React + Supabase web app ("Avalanche Insight Hub"). Your goal is to migrate the backend ML architecture from naive synchronous edge functions to a robust, asynchronous batch-processing pipeline utilizing GitHub Actions, PostGIS, and classical Machine Learning. 

## 1. Core Architectural Shift (The "How")
*   **Frontend:** React, Leaflet, 3D Voxel View (Arnis-style). Unchanged, but will now consume *pre-computed* uncertainty-aware JSON grids.
*   **Database:** Supabase (PostgreSQL + PostGIS).
*   **Heavy Compute (Free Tier):** GitHub Actions (Ubuntu runners) for model training and daily inference.
*   **Ground Truth (Free Tier):** Google Earth Engine (GEE) Python API for Sentinel-1/2 satellite extraction.

---

## 2. Database Schema & Migration Instructions

**Codex Instruction:** Execute the following SQL migrations in Supabase to support Topo-Snapping and Calibrated Uncertainty.

```sql
-- 1. Enhance the events table to hold topographical Class-III data
ALTER TABLE avalanche_events 
ADD COLUMN elevation NUMERIC,
ADD COLUMN slope_angle NUMERIC,
ADD COLUMN aspect NUMERIC,
ADD COLUMN source VARCHAR(50) DEFAULT 'manual'; -- 'manual', 'gemini_news', 'gee_sar', 'gee_opt'

-- 2. Create the pre-computed forecast grids table
CREATE TABLE forecast_grids (
    id SERIAL PRIMARY KEY,
    region VARCHAR(100),
    forecast_date DATE,
    grid_geojson JSONB, -- Contains the 20x20 cells
    runout_polygons JSONB, -- Contains Alpha-Beta runout vectors
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Structure of the properties inside grid_geojson features:
-- {
--   "risk_level": 1-5,
--   "probability": 0.85, (Calibrated via Isotonic Regression)
--   "confidence_lower": 0.65, (Variance across RF trees)
--   "confidence_upper": 0.95,
--   "shap_values": {"snowfall": 0.4, "wind_drift": 0.3...}
-- }
```

---

## 3. The 4-Phase Python Backend (GitHub Actions)

**Codex Instruction:** Create a `.github/workflows/` directory with two cron jobs. Create a `/backend/` directory for the Python scripts. Use `scikit-learn`, `imbalanced-learn`, `earthengine-api`, and `whitebox`.

### Phase 1: Topo-Snapping & Event Ingestion (Edge Function)
When an event is submitted via the UI or the Gemini Groundsource news scraper, it must not use street-level geocoding (which snaps to valley towns). 
*   **Task:** Modify the `ingest_event` Supabase Edge Function.
*   **Logic:** Take the GPS coordinate, ping the free Open-Elevation API (or Mapbox Terrain RGB), calculate the exact elevation, slope, and aspect, and insert it into `avalanche_events`. 

### Phase 2: Multi-Modal GEE Ground Truth (Weekly Cron)
*   **Task:** Create `/backend/gee_extractor.py` triggered every Sunday.
*   **Logic:** 
    1. Authenticate with GEE using a Service Account.
    2. Query Sentinel-1 (SAR VV/VH thresholding for wet snow avalanches) and Sentinel-2 (NDSI optical change-detection for dry snow slabs).
    3. Export the resulting geometries as GeoJSON and insert them into Supabase `avalanche_events` with `source='gee_sar'`.

### Phase 3: Automated ML Training Pipeline (Weekly Cron)
*   **Task:** Create `/backend/train_model.py`. This is the core of the upgrade.
*   **Logic based on 2025 Research:**
    1. **Fetch Data:** Pull historical `avalanche_events` and Open-Meteo historical data from Supabase.
    2. **KMeansSMOTE:** Apply `KMeansSMOTE` from `imbalanced-learn` to synthetically oversample the minority avalanche class, preventing the model from just guessing "safe".
    3. **SVM-RFE Feature Selection:** Pass the 40+ weather variables through Support Vector Machine Recursive Feature Elimination (`RFE` with `SVC(kernel="linear")`). Select only the top 15 features (e.g., 3-day accumulated snow, wind drift, temperature gradient).
    4. **Cost-Sensitive Random Forest:** Train a `RandomForestClassifier(class_weight={0: 1, 1: 4})` to heavily penalize false negatives.
    5. **Probability Calibration:** Wrap the RF in `CalibratedClassifierCV(method='isotonic')` to generate true statistical probabilities, not just tree vote-fractions.
    6. **Deploy:** Save the `.joblib` model artifact to Supabase Storage.

### Phase 4: Daily Asynchronous Inference & Runout (Daily Cron)
*   **Task:** Create `/backend/daily_inference.py` triggered every day at 01:00 UTC.
*   **Logic:**
    1. Download the latest `.joblib` model.
    2. Fetch 72h Open-Meteo forecasts for the defined regions.
    3. **Inference:** Run the 15-feature RF model across the 20x20 grid coordinates. Calculate `predict_proba()` and extract tree variance for uncertainty bounds.
    4. **Runout Physics:** Pass the high-risk grid cells to `WhiteboxTools` (Python package). Use the DEM to calculate the Alpha-Beta empirical runout paths down the slope (simulating granular flow, *not* water).
    5. **Store:** Push the final grid and runout polygons to the `forecast_grids` table as a single JSONB payload.

---

## 4. API Endpoints & Queries (Supabase RPCs)

**Codex Instruction:** Create the following PostgREST endpoints in Supabase to serve the frontend instantly without computational lag.

1.  **`GET /rest/v1/forecast_grids?region=eq.{region_id}&order=forecast_date.desc&limit=1`**
    *   *Purpose:* Fetches the pre-computed 24h/72h risk grid and runout polygons. The frontend Leaflet/3D Voxel component renders this instantly.
2.  **`POST /functions/v1/ingest_event`**
    *   *Purpose:* Endpoint for the React frontend (Field Reports) and Gemini (News Scraper). Expects `{lat, lng, description, hazard_type}`.
    *   *Action:* Performs Topo-Snapping (Elevation, Slope) before inserting into PostGIS.
3.  **`GET /rest/v1/avalanche_events?select=lat,lng,confidence,source`**
    *   *Purpose:* Populates the historical Heatmap/Events layer.

---

## 5. Detailed User Stories for Codex Implementation

**Codex Instruction:** Verify implementation against these specific Acceptance Criteria (AC).

### User Story 1: True Epistemic Uncertainty Visualization
**As a backcountry user**, I want to see uncertainty bands on the risk map, **so that** I know when the AI is guessing due to poor data.
*   **AC 1:** The JSON payload from the backend includes `confidence_lower` and `confidence_upper`.
*   **AC 2:** If the variance between these bounds exceeds 30% (probability is highly uncertain), the React 3D Voxel cell renders as **Grey (Uncertain)** instead of Red/Green.
*   **AC 3:** Clicking a cell displays the calibrated probability (e.g., "75% chance of Level 4") alongside the SHAP values.

### User Story 2: Offline-First Field Reporting (PWA)
**As a backcountry skier without cell service**, I want to log an avalanche on the mountain, **so that** it syncs to the AI dataset when I return to town.
*   **AC 1:** Implement a Service Worker in React to cache POST requests to `/ingest_event`.
*   **AC 2:** When network status is restored, the queued events are dispatched.
*   **AC 3:** The UI shows a "Syncing X offline reports..." toast notification.

### User Story 3: Alpha-Beta Physical Runout Overlays
**As a local civil defense planner**, I want to see the physical runout paths of potential avalanches, **so that** I know if a road will be buried.
*   **AC 1:** The map includes an "Impact Runout" toggle layer.
*   **AC 2:** When toggled, the `runout_polygons` (calculated by WhiteboxTools in the backend) are drawn over the map as semi-transparent red polygons.
*   **AC 3:** If a runout polygon intersects an OSM road vector, a "Warning" icon appears on the highway.

### User Story 4: Feature-Optimized SHAP Interpretability
**As a forecaster**, I want the SHAP explanations to only show the most critical weather features, **so that** the UI isn't cluttered with redundant data.
*   **AC 1:** Because the backend SVM-RFE pruned the inputs from 40 to 15, the frontend SHAP bar chart strictly displays a maximum of the top 5 contributing features (e.g., "3-Day New Snow", "Wind Drift").
*   **AC 2:** SHAP values are translated into local-language, plain-text sentences via a lightweight UI mapping (e.g., "High risk driven primarily by 30cm fresh snow").

---

 