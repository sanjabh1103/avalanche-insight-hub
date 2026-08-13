# CD2 Team — ML & Python Module Learning Guide (29 Questions)

> **Generated:** 2026-08-11
> **Audience:** CD2 team members learning the Avalanche Insight Hub codebase
> **Purpose:** Step-by-step guide to understand the top 10 ML questions, top 10 Python module questions, and 9 colleague questions — using Graphify and KS graphs

---

## How to Use This Guide

Each question has three parts:
1. **Answer** — what the code does, with file paths and line numbers
2. **Graphify steps** — how to explore it in the network graph and file tree
3. **KS steps** — how to explore it in the knowledge site

### Quick URL Reference

| Tool | URL | What It Shows |
|---|---|---|
| **Graphify network graph** | `https://dist-silk-sigma-21.vercel.app/graphify/graph.html` | 1,316 community nodes, cross-module edges |
| **Graphify file tree** | `https://dist-silk-sigma-21.vercel.app/graphify/tree.html` | 23,200-node collapsible file hierarchy |
| **Graphify call flow** | `https://dist-silk-sigma-21.vercel.app/graphify/callflow.html` | Mermaid call-flow diagram |
| **KS code graph** | `https://dist-silk-sigma-21.vercel.app/data/code-graph.json` | 5,076-node structural graph (API) |
| **KS explanations** | `https://dist-silk-sigma-21.vercel.app/data/explanations.json` | Pre-generated node explanations (API) |
| **Public GitHub repo** | `https://github.com/sanjabh1103/avalanche-insight-hub` | Source code |
| **Live app (Netlify)** | `https://avalanche-insight-hub.netlify.app/` | Deployed application |

### Graphify Search Method

1. Open the graphify URL in your browser
2. Use `Ctrl+F` (or `Cmd+F`) to search for a term
3. In `graph.html`: nodes with matching labels are highlighted
4. In `tree.html`: matching file/function nodes are visible in the tree
5. Click any node to see its connections or expand its children

### KS API Method

```bash
# Search code-graph.json for a node
curl -s https://dist-silk-sigma-21.vercel.app/data/code-graph.json | \
  python3 -c "import sys,json; g=json.load(sys.stdin); [print(n['id']) for n in g['nodes'] if 'lstm' in n['id'].lower()]"

# Get explanation for a specific node
curl -s https://dist-silk-sigma-21.vercel.app/data/explanations.json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); k='class:backend/lstm_model.py:BranchedMTSLSTM'; print(d.get(k,'Not found'))"
```

---

# Part A — Top 10 Machine Learning Questions

---

## ML-Q1: What models does the system use and how are they organized?

### Answer

The system uses three ML models in a layered architecture:

| Model | File | Role | Status |
|---|---|---|---|
| **RandomForest (RF)** | `backend/models/surrogate_rf.py` | Primary probability model | ✅ Published by default |
| **MTS-LSTM** | `backend/lstm_model.py` + `backend/models/mts_lstm.py` | Sequence-aware shadow candidate | ⏸ Shadow only (gated) |
| **SAR U-Net** | `backend/sar_unet_worker.py` | Satellite radar change detection | ⏸ Gated by env flag |

RF is the production model. LSTM runs in "shadow" mode (trained but not published). SAR U-Net provides satellite-derived features.

**Key code:**
- `backend/models/surrogate_rf.py` line 11: `from sklearn.ensemble import RandomForestClassifier`
- `backend/models/surrogate_rf.py` line 597: `base_model = RandomForestClassifier(n_estimators=SURROGATE_RF_TREES, ...)`
- `backend/lstm_model.py` lines 65-66: `SHADOW_QUALITY_RULE = 'strict_pss_gt_rf_and_brier_lte_rf'`
- `backend/sar_unet_worker.py` line 60: `SAR_UNET_PROMOTED = os.getenv('SAR_UNET_PROMOTED', 'false')`

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `RandomForest` — find the `randomforestclassifier` node
3. Search for `lstm` — 228 nodes appear in the LSTM cluster
4. Search for `sar_unet` — 265 nodes in the SAR U-Net cluster
5. Click the `backend_models_surrogate_rf` community node to see its edges to `train_model`, `inference_grid`, and `calibration`

### KS Steps

1. Open `https://dist-silk-sigma-21.vercel.app/data/code-graph.json` in a JSON viewer
2. Search for nodes containing `surrogate_rf` — 22 nodes
3. Search for nodes containing `lstm` — 45 nodes
4. Search for nodes containing `sar_unet` — 146 nodes
5. Open `https://dist-silk-sigma-21.vercel.app/data/explanations.json` and search for `surrogate_rf` to read pre-generated explanations

---

## ML-Q2: How does the RandomForest model work and what features does it use?

### Answer

RF uses `RandomForestClassifier` from sklearn with TreeSHAP explainability. It consumes both dynamic weather features and static terrain features.

**Dynamic features** (`backend/common/sequence_features.py` lines 20-27):
- Snowfall, precipitation, wind loading, temperature gradient, freezing level

**Static features** (`backend/common/sequence_features.py` lines 29-40):
- Slope, elevation, aspect, terrain roughness, curvature

**Training** (`backend/models/surrogate_rf.py`):
- Line 597: `RandomForestClassifier(n_estimators=SURROGATE_RF_TREES, ...)`
- Lines 258, 285, 325, 350: Multiple RF instances in `fit_surrogate_bundle()` for cross-validation
- Lines 293, 333: `y_prob_fold = rf_fold.predict_proba(x[test_idx])[:, 1]` — probability output

**SHAP explainability** (`backend/models/surrogate_rf.py`):
- `build_tree_shap_explainer()` function generates SHAP values for feature attribution

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `models/` → `surrogate_rf.py`
3. See functions: `fit_surrogate_bundle`, `build_tree_shap_explainer`, `predict_proba`
4. Expand `backend/` → `common/` → `sequence_features.py`
5. See functions: `build_training_branch_arrays`, `_cached_historical_window`

### KS Steps

1. Query KS API: `curl -s https://dist-silk-sigma-21.vercel.app/data/code-graph.json | python3 -c "import sys,json; g=json.load(sys.stdin); [print(n['id']) for n in g['nodes'] if 'surrogate_rf' in n['id'].lower()]"` — 22 nodes
2. Query explanations: search for `surrogate_rf` in explanations.json

---

## ML-Q3: What is the PSS and Brier score gate, and why does it matter?

### Answer

The promotion gate in `backend/train_model.py` prevents models that don't meet quality thresholds from being published.

**Thresholds** (`backend/train_model.py` lines 64-65):
```python
PSS_FLOOR = float(os.getenv('PSS_FLOOR', '0.45'))
BRIER_SCORE_CEILING = float(os.getenv('BRIER_SCORE_CEILING', '0.15'))
```

**Gate logic** (`backend/train_model.py` lines 1140-1164):
- PSS (Peirce Skill Score) must be > 0.45 — measures classification skill above random
- Brier score must be ≤ 0.15 — measures probability calibration quality
- If either fails, training exits with code 2 and refuses to publish to Supabase (lines 1202-1210)

**Why it matters:** PSS > 0.45 ensures the model is meaningfully better than random chance. Brier ≤ 0.15 ensures probability estimates are calibrated (not overconfident or underconfident).

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `pss` — 8 nodes including `timeseries_cv_pss`, `spatial_group_cv_pss`
3. Search for `brier` — 51 nodes including `compute_brier_score`, `brier_score`
4. Search for `verification_exit_gates` — 14 nodes
5. Click `backend_common_verification_exit_gates` to see edges to `train_model` and `risk_math`

### KS Steps

1. Query KS: search `code-graph.json` for `brier` — 6 nodes, `pss` — 2 nodes
2. Open the public repo: `backend/train_model.py` lines 64-65, 1140-1164

---

## ML-Q4: How does the LSTM shadow pipeline work?

### Answer

The LSTM runs as a "shadow" candidate — it's trained alongside RF but not published unless it beats RF.

**Training** (`backend/lstm_model.py` lines 336-597):
- `fit_lstm_head()` trains a BranchedMTSLSTM with 24-hourly and 7-daily sequence branches
- Line 428: `from backend.models.mts_lstm import BranchedMTSLSTM`
- Lines 591-596: LSTM PSS and Brier are computed and compared to RF

**Shadow quality gate** (`backend/lstm_model.py` line 310):
```python
shadow_quality_gate_passed = bool(lstm_pss > rf_pss and lstm_brier <= rf_brier)
```

**Production eligibility** (`backend/lstm_model.py` lines 316-318):
- Must pass shadow quality gate AND
- SAR release gate (env flag) AND
- SAR volume gate (50+ events, 3+ regions, 14+ scene dates)

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `lstm_model.py` — see `fit_lstm_head`, `_predict_stochastic_outputs`, `apply_probability_calibration`
3. Expand `backend/` → `models/` → `mts_lstm.py` — see `BranchedMTSLSTM` class
4. Open `graph.html` and search `lstm` — 228 nodes showing the full LSTM cluster

### KS Steps

1. Query KS: search `code-graph.json` for `lstm` — 45 nodes
2. Read `backend/lstm_model.py` lines 299-333 in the public repo for the full gate logic

---

## ML-Q5: How does probability calibration work?

### Answer

Calibration ensures that when the model says "70% chance of avalanche," it actually happens ~70% of the time.

**Calibration method** (`backend/lstm_model.py` lines 211-260):
- `fit_isotonic_probability_calibrator()` uses IsotonicRegression (non-parametric)
- Falls back to Platt sigmoid (logistic) for small samples
- Line 125-129: `apply_probability_calibration()` applies the calibrator to predictions

**Brier score enforcement** (`backend/train_model.py`):
- Line 65: `BRIER_SCORE_CEILING = 0.15`
- Lines 1158-1159: `brier_gate_passed = bool(brier_score is None or float(brier_score) <= effective_brier_ceiling)`
- Lines 1202-1210: If Brier gate fails, training exits with code 2 — no publication

**RF calibration** (`backend/models/surrogate_rf.py` lines 742-745):
- Calibrated model wraps `predict_proba()` with isotonic regression

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `calibration` — 180 nodes including `compute_calibration_error`, `calibration_drift`
3. Search for `brier` — 51 nodes
4. Click `backend_common_benchmark_package_compute_calibration_error` to see edges

### KS Steps

1. Query KS: search `code-graph.json` for `calibration` — 43 nodes
2. Read `backend/lstm_model.py` lines 211-260 in the public repo

---

## ML-Q6: What is the SAR U-Net and how does it process satellite imagery?

### Answer

SAR U-Net is a segmentation model that detects avalanche changes in before/after satellite radar images.

**Implementation** (`backend/sar_unet_worker.py`):
- Lines 568-603: `predict_probability_mask()` and `predict_bitemporal_probability_mask()` — generate probability masks from SAR imagery
- Line 60: `SAR_UNET_PROMOTED = os.getenv('SAR_UNET_PROMOTED', 'false')` — gated by env flag
- Lines 552-557: In promoted mode, checkpoint mismatches raise errors (fail-closed)

**Usage in inference** (`backend/inference/grid.py` line 399):
- `sar_summary = _fetch_latest_sar_summary(region.key)` — fetches SAR data for inference
- SAR provides features that feed into training volume gates, not direct probability prediction

**Production gate** (`backend/common/sar_unet_production_gate.py`):
- `SarUnetGateResult` class validates checkpoint integrity and promotion readiness

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `sar_unet_worker.py` — see `predict_probability_mask`, `predict_bitemporal_probability_mask`
3. Expand `backend/` → `common/` → `sar_unet_production_gate.py` — see `SarUnetGateResult`
4. Open `graph.html` and search `sar_unet` — 265 nodes

### KS Steps

1. Query KS: search `code-graph.json` for `sar_unet` — 146 nodes
2. Read `backend/sar_unet_worker.py` lines 568-603 in the public repo

---

## ML-Q7: How does SHAP explainability work in the system?

### Answer

SHAP (SHapley Additive exPlanations) attributes feature importance to each prediction, explaining WHY the model made a decision.

**SHAP explainer** (`backend/models/surrogate_rf.py`):
- `build_tree_shap_explainer()` creates a TreeSHAP explainer for the RF model
- Generates SHAP values per feature per prediction

**Edge function** (`supabase/functions/shap-explainer/index.ts`):
- Lines 52-106: Generates natural language explanations from SHAP values using Gemini API
- Has spend cap guardrails — falls back to deterministic summaries when API budget exceeded
- Lines 108-138: HTTP handler processes SHAP context and returns explanations

**Knowledge graph integration** (`src/lib/knowledge-graph/sectionGenerators.ts` line 287):
- SHAP explanations feed into the knowledge graph section generators

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `shap` — 8 nodes including `build_tree_shap_explainer`, `shap_explainer_index`
3. Click `supabase_functions_shap_explainer_index` to see edges to the knowledge graph

### KS Steps

1. Query KS: search `code-graph.json` for `shap` — 32 nodes
2. Read `supabase/functions/shap-explainer/index.ts` in the public repo

---

## ML-Q8: How does the active learning feedback loop work (and why is it disabled)?

### Answer

Active learning feedback captures scientist validation decisions and feeds them back as drift signals for model retraining.

**Implementation** (`backend/common/active_learning_feedback.py`):
- Line 17: `ACTIVE_LEARNING_FEEDBACK_ENABLED = os.getenv('ACTIVE_LEARNING_FEEDBACK_ENABLED', 'false')`
- Functions: `record_feedback()`, `compute_drift_signals()`, `generate_retraining_candidates()`
- `DriftSignal` class captures distribution shifts between model predictions and scientist labels

**Status: SHELVED**
- Only imported by test file: `backend/tests/test_active_learning_feedback.py`
- No production code imports or calls this module
- Disabled by default via environment flag

**Why shelved:** The feedback loop infrastructure exists but is not yet wired into the training pipeline. It's a future enhancement for when scientist validation volume justifies automated retraining triggers.

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `active_learning_feedback` — 39 nodes
3. Click `backend_common_active_learning_feedback` to see it's connected only to test nodes (no production callers)

### KS Steps

1. Query KS: search `code-graph.json` for `active_learning` — 28 nodes
2. Read `backend/common/active_learning_feedback.py` in the public repo

---

## ML-Q9: How does DBSCAN anomaly detection work?

### Answer

DBSCAN clusters anomalous grid cells into spatial zones based on cross-sensor discrepancies.

**Implementation** (`backend/common/anomaly_detector.py`):
- Lines 536-589: `cluster_anomaly_zones()` function
- Line 555: `from sklearn.cluster import DBSCAN`
- Line 574: `db = DBSCAN(eps=eps_km, min_samples=1).fit(coords_km)`
- Groups cells where SAR, optical, and weather data disagree

**What it does NOT do:**
- Does NOT affect model probabilities directly
- Is NOT integrated with LSTM
- Does NOT change avalanche danger levels

**What it DOES do:**
- Identifies spatial clusters of sensor disagreements
- Flags zones for scientist review and attribution
- Supports the verification exit gate system (Gate C→D checks anomaly detection rate ≥ 0.01)

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `anomaly_detector.py`
3. See `cluster_anomaly_zones` and related functions
4. Open `graph.html` and search `anomaly` to see connections to verification gates

### KS Steps

1. Read `backend/common/anomaly_detector.py` lines 536-589 in the public repo
2. Search `code-graph.json` for `anomaly` to find related nodes

---

## ML-Q10: How does the model promotion pipeline work end-to-end?

### Answer

The promotion pipeline is a multi-gate system that prevents underperforming models from reaching production.

**Pipeline flow:**

```
Training → PSS/Brier Gate → Stability Check → SAR Volume Gate → SAR Release Gate → Publication
```

**Step 1: Training** (`backend/train_model.py` line 642)
- `fit_model()` trains RF and optionally LSTM

**Step 2: PSS/Brier Gate** (`backend/train_model.py` lines 1140-1164)
- PSS > 0.45 AND Brier ≤ 0.15
- Failure → exit code 2, no publication

**Step 3: Stability Check** (`backend/train_model.py` line 616)
- `compute_seed_stability_summary()` verifies consistent performance across random seeds

**Step 4: SAR Volume Gate** (`backend/lstm_model.py` lines 312-315)
- Min 50 events, 3 regions, 14 scene dates (LSTM only)

**Step 5: SAR Release Gate** (`backend/lstm_model.py` line 316)
- `SAR_UNET_PROMOTED` env flag must be true (LSTM only)

**Step 6: Publication** (`backend/train_model.py` line 743)
- `publish_metadata()` persists artifact to Supabase

**Promote-report edge function** (`supabase/functions/promote-report/index.ts`):
- Admin-only endpoint for promoting avalanche event verification status
- Calls `promote_event_verification` Supabase RPC

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `promote` — see `promote_report` edge function node
3. Search for `verification_exit_gates` — 14 nodes
4. Search for `train_model` — 47 nodes
5. Click `backend_common_verification_exit_gates` to see the full gate network

### KS Steps

1. Query KS: search `code-graph.json` for `promote` — 16 nodes
2. Read `backend/train_model.py` lines 1140-1210 in the public repo
3. Read `supabase/functions/promote-report/index.ts` in the public repo

---

# Part B — Top 10 Python Module Questions

---

## PY-Q1: How does data flow from external sources into the system?

### Answer

Data flows through adapter modules into feature engineering:

| Source | Adapter Module | Key Function |
|---|---|---|
| **Open-Meteo** (weather) | `backend/common/real_features.py` | `_fetch_open_meteo()` (line 98) |
| **Open-Meteo** (archive) | `backend/common/meteoio_openmeteo.py` | `fetch_weather_history_for_snowpack()` (line 109) |
| **Sentinel-1** (SAR) | `backend/common/s1_snow_depth.py` | `compute_cross_ratio()` (line 47) |
| **SRTM** (terrain) | `backend/common/real_features.py` | `extract_cell_terrain()` |
| **GIBS** (MODIS snow) | `backend/common/gibs_ingestion.py` | `fetch_gibs_snow_cover()` (line 133) |
| **Sensors** (radar/seismic) | `backend/common/sensor_ingestion.py` | `SensorIngestionAdapter` (line 326) |

**Flow:** External API → Adapter → Feature Engineering → Model Input

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → find `meteoio_openmeteo.py`, `real_features.py`, `s1_snow_depth.py`
3. Open `graph.html` and search `meteoio` — 58 nodes showing the weather adapter cluster

### KS Steps

1. Query KS: search `code-graph.json` for `meteoio` — see adapter nodes
2. Read `backend/common/real_features.py` line 98 in the public repo

---

## PY-Q2: How is Supabase used and what tables exist?

### Answer

Supabase is the central persistence layer with 80+ SQL migrations, 15+ tables, and 5+ edge functions.

**Core tables:**
- `avalanche_events` — ground truth labels with governance fields
- `forecasts` — published forecast grids
- `forecast_runs` — forecast run metadata
- `field_reports` — user-submitted observations
- `model_status` — active model candidate state
- `compute_jobs` — background job tracking
- `calibration_profiles` — calibration method configs
- `sar_detection_artifacts` — SAR mask storage

**Edge functions:**
- `run-forecast`, `trigger-job`, `field-report-enrichment`, `ingest-event`, `label-forecast-outcomes`, `shap-explainer`, `promote-report`

**RLS policies:** All tables have Row-Level Security (migration `20260414130000_avalanche_governance_foundation.sql` lines 46-61).

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `supabase/` → `functions/` — see all edge functions
3. Expand `supabase/` → `migrations/` — see 80+ migration files
4. Open `graph.html` and search `supabase` — 964 nodes (largest cluster)

### KS Steps

1. Query KS: search `code-graph.json` for `supabase` — see table and function nodes
2. Read `supabase/config.toml` in the public repo for edge function configuration

---

## PY-Q3: How are forecasts generated end-to-end?

### Answer

The forecast pipeline runs daily via `backend/daily_inference.py`:

1. **Load regions and model artifacts** — `daily_inference.py` entry point
2. **Build spatial grid** — `build_region_grid()` in `backend/common/features.py`
3. **Fetch weather/terrain** — `build_real_feature_row()` in `backend/common/real_features.py`
4. **Snowpack physics** — `compute_cell_snowpack_physics()` in `backend/common/snowpack_physics.py`
5. **Model inference** — `calibrated_model.predict_proba()` in `backend/inference/grid.py` line 507
6. **Risk scoring** — `compute_danger_level()` in `backend/common/risk_math.py` line 201
7. **Bulletin generation** — `build_forecast_bulletin()` in `backend/common/forecast_bulletins.py` line 31
8. **Publication** — `publish_forecast_run()` in `backend/common/forecast_publication.py` line 33

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `forecast` — 698 nodes
3. Search for `inference` — 286 nodes
4. Search for `daily_inference` — see the main entry point
5. Click the `backend_daily_inference` node to see edges to `features`, `real_features`, `risk_math`, `forecast_bulletins`

### KS Steps

1. Query KS: search `code-graph.json` for `forecast` — 182 nodes
2. Read `backend/daily_inference.py` in the public repo

---

## PY-Q4: What are the verification exit gates and their thresholds?

### Answer

Four-phase verification spine in `backend/common/verification_exit_gates.py`:

| Gate | Function | Threshold |
|---|---|---|
| **A→B** | `check_gate_a_to_b()` (line 52) | Min 5 cells with baselines, 1 with GIBS, 1 with SAR |
| **B→C** | `check_gate_b_to_c()` (line 128) | Min 1 cell with optical, 2 discrepancy types |
| **C→D** | `check_gate_c_to_d()` (line 190) | Min 1 cell with fusion, consensus ≥ 0.3 |
| **D (Production)** | `check_gate_d_production()` (line 271) | Min 100 cells, anomaly rate ≥ 0.01 |

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search for `verification_exit_gates` — 14 nodes
3. Click `backend_common_verification_exit_gates` to see edges to `train_model`, `risk_math`, `anomaly_detector`

### KS Steps

1. Query KS: search `code-graph.json` for `verification` — 118 nodes
2. Read `backend/common/verification_exit_gates.py` in the public repo

---

## PY-Q5: How are risk scores and danger levels computed?

### Answer

`backend/common/risk_math.py` separates hazard (EAWS danger 1-5) from impact-risk (WMO standards):

**Key functions:**
- `risk_level()` (line 71) — maps score to EAWS danger level 1-5
- `build_hazard_vector()` (line 96) — constructs hazard features
- `chebyshev_ipa()` (line 117) — Chebyshev max-weighted aggregation
- `compute_danger_level()` (line 201) — configurable danger aggregation
- `impact_risk_score()` (line 167) — separate impact-risk scoring

**Danger level thresholds:**
- <0.15 → Level 1 (Low)
- <0.30 → Level 2 (Moderate)
- <0.50 → Level 3 (Considerable)
- <0.70 → Level 4 (High)
- ≥0.70 → Level 5 (Extreme)

**Hazard factors:** probability, slope deviation, aspect risk, snowpack weakness
**Impact factors:** exposure, vulnerability (separate from hazard)

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `risk_math.py` — see `risk_level`, `compute_danger_level`, `chebyshev_ipa`
3. Open `graph.html` and search `risk_math` — 44 nodes

### KS Steps

1. Query KS: search `code-graph.json` for `risk_math` — 4 nodes
2. Read `backend/common/risk_math.py` lines 71-201 in the public repo

---

## PY-Q6: How does label governance work?

### Answer

`backend/common/label_governance.py` manages label credibility through source weighting, recency decay, and corroboration:

**Source weights** (line 113):
- `field_report`: 1.0
- `sar_unet`: 1.1
- `gee_sar`: 0.9
- `gemini_news`: 0.8

**Key functions:**
- `derive_label_governance()` (line 178) — computes governance from record
- `materialize_label_governance()` (line 208) — persists to record
- `source_weight()` (line 113) — credibility by source type
- `recency_decay()` (line 161) — time-based confidence decay (30-day half-life)
- `is_auto_label_eligible()` (line 226) — F19 auto-label check (min confidence 0.45)

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `label_governance.py`
3. Open `graph.html` and search `label_governance` — 38 nodes

### KS Steps

1. Query KS: search `code-graph.json` for `label_governance` — 4 nodes
2. Read `backend/common/label_governance.py` lines 113-226 in the public repo

---

## PY-Q7: What is the SAR acceptance policy?

### Answer

`backend/common/sar_acceptance_policy.py` enforces strict quality floors for SAR models before promotion:

**Key functions:**
- `evaluate_snowslide_research_grade()` (line 156) — main evaluation gate
- `assert_sar_acceptance_for_promotion()` (line 313) — promotion guard

**Thresholds:**
- Precision floor: 0.70
- Recall floor: 0.50
- F1 floor: 0.60
- False positive rate ceiling: 0.002
- Required scenes: `livigno_20240403`, `nuuk_20160413`, `pish_20230221`, `tromso_20241220`

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `sar_acceptance_policy.py`
3. Open `graph.html` and search `sar_acceptance` — 30 nodes

### KS Steps

1. Read `backend/common/sar_acceptance_policy.py` lines 156-313 in the public repo

---

## PY-Q8: How does the Snowpack physics module work?

### Answer

`backend/common/snowpack_physics.py` provides physics-based snow simulation with three modes:

| Mode | Function | When Used |
|---|---|---|
| **SNOWPACK native** | `run_snowpack_native()` | C++ binary available + Docker |
| **COSIPY** | `run_cosipy_cell()` (line 486) | Python fallback |
| **Heuristic** | `_heuristic_to_physics_result()` (line 554) | Last resort |

**Input:** Open-Meteo historical weather via `fetch_weather_history_for_snowpack()` (line 109)
**Output:** 10 physics fields — weak_layer_depth_m, weak_layer_grain_type, shear_strength_kpa, stability_index, temperature_gradient_per_m, liquid_water_content_pct, layer_count, snow_height_m, bulk_density_kgm3

**SNOWPACK runner:** SMET file → binary execution → .pro profile parsing → evidence capture

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `snowpack_physics.py` — see `run_cosipy_cell`, `fetch_weather_history_for_snowpack`
3. Expand `backend/` → `common/` → `meteoio_openmeteo.py` — see `run_snowpack_native`, `write_smet_file`
4. Open `graph.html` and search `snowpack` — 101 nodes

### KS Steps

1. Query KS: search `code-graph.json` for `snowpack` — 91 nodes
2. Read `backend/common/snowpack_physics.py` in the public repo

---

## PY-Q9: How does model training work end-to-end?

### Answer

`backend/train_model.py` orchestrates the full training pipeline:

**Key functions:**
- `fit_model()` (line 642) — main training orchestration
- `fit_surrogate_bundle()` — RF surrogate training
- `fit_lstm_head()` (line 682) — MTS-LSTM sequence head
- `compute_seed_stability_summary()` (line 616) — stability validation
- `publish_metadata()` (line 743) — artifact persistence

**Configuration:**
- `PSS_FLOOR = 0.45` (line 64)
- `BRIER_SCORE_CEILING = 0.15` (line 65)
- `MIN_EVENTS_FOR_TRAINING = 30` (line 72)
- `TIME_SERIES_SPLITS = 5` (line 66)

**Models trained:**
- RF surrogate with TreeSHAP (reference path)
- MTS-LSTM sequence head (shadow candidate)
- Cold-start synthetic bootstrap (data-efficient mode)

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `train_model.py` — see `fit_model`, `publish_metadata`, `compute_seed_stability_summary`
3. Open `graph.html` and search `train_model` — 47 nodes

### KS Steps

1. Query KS: search `code-graph.json` for `train_model` — 2 nodes
2. Read `backend/train_model.py` lines 642-743 in the public repo

---

## PY-Q10: What scheduled jobs exist and how do they work?

### Answer

GitHub Actions cron jobs in `.github/workflows/ml_pipeline.yml`:

| Schedule | Job | Description |
|---|---|---|
| `7 4 * * 1` (Mon 04:07 UTC) | Weekly training | Full RF + LSTM training |
| `7 4 * * 4` (Thu 04:07 UTC) | Mid-week drift retrain | Drift check + conditional retrain |
| `3 3 * * 1,4` | SAR extraction | Sentinel-1 processing |
| `12 5 * * *` (Daily 05:12 UTC) | Gemini news ingest | News-based event ingestion |
| `17 6 * * *` (Daily 06:17 UTC) | Forecast publication proof | Verify forecast was published |
| `0 5 * * 1` (Mon 05:00 UTC) | LSTM shadow training | Shadow LSTM training |
| `30 5 * * 1` (Mon 05:30 UTC) | LSTM shadow inference | Shadow LSTM inference |
| `0 3 * * *` (Daily 03:00 UTC) | Forecast retention cleanup | Old forecast cleanup |

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `.github/` → `workflows/` → `ml_pipeline.yml`
3. Open `graph.html` and search `cron` — 174 nodes

### KS Steps

1. Query KS: search `code-graph.json` for `cron` — 2 nodes
2. Read `.github/workflows/ml_pipeline.yml` in the public repo

---

# Part C — 9 Colleague Questions (Detailed Answers)

---

## C-Q1: Is `active_learning_feedback.py` a real near-term priority or intentionally shelved?

### Answer

**Intentionally shelved.** The file exists at `backend/common/active_learning_feedback.py` with full functionality (`record_feedback()`, `compute_drift_signals()`, `generate_retraining_candidates()`), but:

- Line 17: `ACTIVE_LEARNING_FEEDBACK_ENABLED = os.getenv('ACTIVE_LEARNING_FEEDBACK_ENABLED', 'false')` — disabled by default
- Only imported by `backend/tests/test_active_learning_feedback.py` — no production callers
- The `DriftSignal` class captures distribution shifts but is never invoked in training or inference

**Why:** The infrastructure is built and tested, but scientist validation volume doesn't yet justify automated retraining triggers. It will be wired when we have enough scientist feedback data to make drift signals meaningful.

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search `active_learning_feedback` — 39 nodes
3. Click `backend_common_active_learning_feedback` — notice it only connects to test nodes, not to `train_model` or `daily_inference`

### KS Steps

1. Read `backend/common/active_learning_feedback.py` in the public repo
2. Search `code-graph.json` for `active_learning` — 28 nodes

---

## C-Q2: Are the SHAP-explainer and promote-report edge functions just for testing or for future use?

### Answer

**Both are wired up and active in production.**

**SHAP-explainer** (`supabase/functions/shap-explainer/index.ts`):
- Lines 52-106: Generates natural language explanations from SHAP values using Gemini API
- Has spend cap guardrails with deterministic fallback
- Referenced in migration `20260419150000_hub_reliability_hardening.sql` line 101
- Referenced in `src/lib/knowledge-graph/sectionGenerators.ts` line 287

**Promote-report** (`supabase/functions/promote-report/index.ts`):
- Lines 11-13: Admin-invoked promotion endpoint
- Lines 60-65: Calls `promote_event_verification` Supabase RPC
- Configured in `supabase/config.toml` line 30
- Migration: `20260421120000_verified_promotion_pipeline.sql` line 58

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `supabase/` → `functions/` → `shap-explainer/` and `promote-report/`
3. Open `graph.html` and search `shap_explainer` — 8 nodes, `promote_report` — 3 nodes

### KS Steps

1. Read `supabase/functions/shap-explainer/index.ts` in the public repo
2. Read `supabase/functions/promote-report/index.ts` in the public repo

---

## C-Q3: Why is RandomForest published but MTS-LSTM and SAR U-Net are not?

### Answer

RF is the **reference model** — it's the baseline that other models must beat. LSTM and SAR U-Net are **shadow candidates** that must pass strict gates before promotion.

**RF promotion** (`backend/train_model.py` lines 1140-1164):
- PSS > 0.45 AND Brier ≤ 0.15 → published to Supabase

**LSTM promotion** (`backend/lstm_model.py` lines 310-318):
- Must beat RF on BOTH PSS (higher) AND Brier (lower)
- Must pass SAR volume gate (50+ events, 3+ regions, 14+ scene dates)
- Must pass SAR release gate (env flag)
- Rule: `strict_pss_gt_rf_and_brier_lte_rf_plus_sar_release_and_volume`

**SAR U-Net promotion** (`backend/sar_unet_worker.py` line 60):
- `SAR_UNET_PROMOTED = os.getenv('SAR_UNET_PROMOTED', 'false')` — disabled by default
- Must pass `sar_acceptance_policy.py` thresholds (precision ≥ 0.70, recall ≥ 0.50, F1 ≥ 0.60)

**Why:** RF is simpler, more interpretable, and meets quality bars. LSTM and SAR U-Net are more complex and need to prove they're better before replacing the working model.

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search `RandomForest` — find the production node
3. Search `lstm` — 228 nodes (shadow cluster)
4. Search `sar_unet` — 265 nodes (gated cluster)
5. Search `verification_exit_gates` — see the gate network connecting all three

### KS Steps

1. Read `backend/lstm_model.py` lines 65-66, 299-333 in the public repo
2. Read `backend/sar_unet_worker.py` line 60 in the public repo

---

## C-Q4: Does the LSTM use only historical data or also live data?

### Answer

**Historical data only.** The LSTM uses cached historical weather windows, not live/real-time data.

**Evidence** (`backend/common/sequence_features.py`):
- Lines 279-291: `_cached_historical_window()` fetches historical weather data
- Lines 294-344: `build_training_branch_arrays()` constructs sequences from historical weather
- Line 375 in `real_features.py`: `fetch_historical_weather_window()` is the data source

**What it uses:**
- 24-hourly sequences (past 24 hours of weather)
- 7-daily sequences (past 7 days of weather)
- Static terrain features (slope, elevation, aspect)

**What it does NOT use:**
- Live weather feeds
- Real-time sensor data
- Current forecast data

**Why:** The LSTM is trained on retrospective data to learn temporal patterns. Live data integration is a future enhancement once the model passes the shadow quality gate.

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `sequence_features.py` — see `_cached_historical_window`, `build_training_branch_arrays`
3. Expand `backend/` → `common/` → `real_features.py` — see `fetch_historical_weather_window`

### KS Steps

1. Read `backend/common/sequence_features.py` lines 279-344 in the public repo
2. Search `code-graph.json` for `lstm` — 45 nodes

---

## C-Q5: Is SAR U-Net for training or prediction?

### Answer

**Prediction.** SAR U-Net generates probability masks from satellite radar imagery — it's not used to train the avalanche probability model.

**Prediction functions** (`backend/sar_unet_worker.py` lines 568-603):
- `predict_probability_mask()` — single-image prediction
- `predict_bitemporal_probability_mask()` — before/after change detection

**Inference usage** (`backend/inference/grid.py` line 399):
- `sar_summary = _fetch_latest_sar_summary(region.key)` — fetches SAR data for inference
- SAR features feed into the training dataset volume gates (counting events), not into probability prediction directly

**What SAR U-Net does:**
- Takes before/after Sentinel-1 radar images
- Outputs a probability mask showing where avalanche changes likely occurred
- These masks are used for label generation and volume counting

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `sar_unet_worker.py` — see `predict_probability_mask`, `predict_bitemporal_probability_mask`
3. Expand `backend/` → `inference/` → `grid.py` — see `_fetch_latest_sar_summary`

### KS Steps

1. Read `backend/sar_unet_worker.py` lines 568-603 in the public repo
2. Search `code-graph.json` for `sar_unet` — 146 nodes

---

## C-Q6: How far does the LSTM fall short of RF on PSS/Brier — is it close or a large gap?

### Answer

The code enforces a **strict comparison** — LSTM must beat RF on both metrics. The gap is not quantified in the code itself; the gate is binary (pass/fail).

**Comparison logic** (`backend/lstm_model.py` lines 591-596):
```python
lstm_pss, threshold = _peirce_skill_score_max(y_test, calibrated_mean_prob)
lstm_brier = float(brier_score_loss(y_test, calibrated_mean_prob))
rf_pss = float(rf_metrics.get('pss_holdout', 0.0) or 0.0)
rf_brier = float(rf_metrics.get('brier_score', 1.0) or 1.0)
```

**Gate** (line 310):
```python
shadow_quality_gate_passed = bool(lstm_pss > rf_pss and lstm_brier <= rf_brier)
```

**Interpretation:** The LSTM hasn't yet passed the gate (it's still in shadow mode). The gap could be small (LSTM close to RF but not quite beating it) or large. The code doesn't log the actual gap — it only records pass/fail. To see the actual numbers, you'd need to run the training pipeline and check the metrics output.

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `lstm_model.py` — find `fit_lstm_head` and the gate logic
3. Search `graph.html` for `pss` — 8 nodes showing PSS computation functions

### KS Steps

1. Read `backend/lstm_model.py` lines 299-333, 591-596 in the public repo
2. Read `backend/models/surrogate_rf.py` for RF PSS/Brier computation

---

## C-Q7: Is the LSTM held back by the promotion gate or by insufficient sequence data?

### Answer

**Both.** The LSTM is held back by a three-tier gate that checks both quality AND data volume:

**Tier 1 — Shadow quality gate** (`backend/lstm_model.py` line 310):
```python
shadow_quality_gate_passed = bool(lstm_pss > rf_pss and lstm_brier <= rf_brier)
```
This is a quality gate — LSTM must beat RF.

**Tier 2 — SAR release gate** (line 316):
```python
sar_release_gate_passed
```
This is an env flag — SAR U-Net must be promoted first.

**Tier 3 — SAR volume gate** (lines 312-315):
```python
# Min 50 events, 3 regions, 14 scene dates
```
This is a data volume gate — there must be enough SAR-validated events.

**Conclusion:** Even if the LSTM beats RF on quality (Tier 1), it cannot be promoted without sufficient SAR-validated data (Tier 3) and SAR U-Net being released (Tier 2). Both quality and data constraints apply.

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/graph.html`
2. Search `lstm` — 228 nodes
3. Search `sar_unet` — 265 nodes
4. Search `verification_exit_gates` — 14 nodes connecting both clusters

### KS Steps

1. Read `backend/lstm_model.py` lines 61-66, 299-333 in the public repo

---

## C-Q8: Are the models probability-based or certainty-based?

### Answer

**Probability-based.** Both RF and LSTM output calibrated probability scores, not binary certainties.

**RF probability** (`backend/models/surrogate_rf.py`):
- Lines 293, 333: `y_prob_fold = rf_fold.predict_proba(x[test_idx])[:, 1]`
- Lines 616, 619: `raw_mean_prob = base_model.predict_proba(x_test_sel)[:, 1]`
- Lines 742, 745: Calibrated model uses `predict_proba()` with isotonic regression

**LSTM probability** (`backend/lstm_model.py`):
- Lines 90-123: `_predict_stochastic_outputs()` uses sigmoid on logits
- Line 120: `prob = 1.0 / (1.0 + np.exp(-logits.reshape(-1)))`
- Lines 131-144: `predict_sequence()` returns mean probability AND uncertainty

**Inference** (`backend/inference/grid.py`):
- Line 507: `rf_probabilities = np.asarray(calibrated_model.predict_proba(selected_frame_all)[:, 1], dtype=float)`

**Calibration enforcement:**
- Brier score ceiling (0.15) ensures probabilities are calibrated
- Isotonic regression maps raw scores to calibrated probabilities
- If Brier gate fails, model is NOT published

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `models/` → `surrogate_rf.py` — find `predict_proba` calls
3. Expand `backend/` → `lstm_model.py` — find `_predict_stochastic_outputs`, `apply_probability_calibration`

### KS Steps

1. Read `backend/models/surrogate_rf.py` lines 293, 616 in the public repo
2. Read `backend/lstm_model.py` lines 90-123, 125-129 in the public repo

---

## C-Q9: Does DBSCAN anomaly detection affect model probabilities? (Calibration concern)

### Answer

**No.** DBSCAN does NOT affect model probabilities. It's a post-hoc spatial clustering tool for anomaly attribution, not a probability modifier.

**What DBSCAN does** (`backend/common/anomaly_detector.py` lines 536-589):
- Line 555: `from sklearn.cluster import DBSCAN`
- Line 574: `db = DBSCAN(eps=eps_km, min_samples=1).fit(coords_km)`
- Groups anomalous cells into spatial zones based on cross-sensor discrepancies (SAR vs optical vs weather)
- Output: cluster labels for zones, not probability adjustments

**What DBSCAN does NOT do:**
- Does NOT modify model probabilities
- Does NOT interact with LSTM or RF
- Does NOT change avalanche danger levels
- Does NOT affect calibration

**The calibration concern is valid but addressed differently:**
- Calibration is enforced via IsotonicRegression in `lstm_model.py` lines 211-260
- Brier score ceiling (0.15) in `train_model.py` prevents uncalibrated models from publishing
- The "90% chance of rain every day" problem is exactly what the Brier gate catches — a model that always says 90% would have a high Brier score and fail the gate

### Graphify Steps

1. Open `https://dist-silk-sigma-21.vercel.app/graphify/tree.html`
2. Expand `backend/` → `common/` → `anomaly_detector.py` — find `cluster_anomaly_zones`
3. Open `graph.html` and search `anomaly` — see it connects to `verification_exit_gates`, NOT to `lstm` or `surrogate_rf`

### KS Steps

1. Read `backend/common/anomaly_detector.py` lines 536-589 in the public repo
2. Read `backend/lstm_model.py` lines 211-260 for calibration logic
3. Read `backend/train_model.py` lines 1158-1159 for Brier gate enforcement

---

# Appendix — Quick Reference Table

## All 29 Questions at a Glance

| # | Question | Key File | Graphify Nodes |
|---|---|---|---|
| **ML-1** | What models does the system use? | `surrogate_rf.py`, `lstm_model.py`, `sar_unet_worker.py` | RF: 22, LSTM: 228, SAR: 265 |
| **ML-2** | How does RF work and what features? | `surrogate_rf.py`, `sequence_features.py` | RF: 22, features: 180 |
| **ML-3** | What is PSS/Brier gate? | `train_model.py` lines 64-65, 1140-1164 | PSS: 8, Brier: 51 |
| **ML-4** | How does LSTM shadow pipeline work? | `lstm_model.py` lines 299-333, 336-597 | LSTM: 228 |
| **ML-5** | How does calibration work? | `lstm_model.py` lines 211-260 | Calibration: 180 |
| **ML-6** | What is SAR U-Net? | `sar_unet_worker.py` lines 568-603 | SAR: 265 |
| **ML-7** | How does SHAP explainability work? | `surrogate_rf.py`, `shap-explainer/index.ts` | SHAP: 8 |
| **ML-8** | How does active learning feedback work? | `active_learning_feedback.py` | 39 (shelved) |
| **ML-9** | How does DBSCAN anomaly detection work? | `anomaly_detector.py` lines 536-589 | 0 (not in graph) |
| **ML-10** | How does model promotion work end-to-end? | `train_model.py`, `lstm_model.py`, `promote-report` | Promote: 16 |
| **PY-1** | How does data flow from external sources? | `real_features.py`, `meteoio_openmeteo.py` | MeteoIO: 58 |
| **PY-2** | How is Supabase used? | `supabase/migrations/`, `supabase/functions/` | Supabase: 964 |
| **PY-3** | How are forecasts generated? | `daily_inference.py`, `forecast_bulletins.py` | Forecast: 698 |
| **PY-4** | What are verification exit gates? | `verification_exit_gates.py` | 14 |
| **PY-5** | How are risk scores computed? | `risk_math.py` lines 71-201 | 44 |
| **PY-6** | How does label governance work? | `label_governance.py` lines 113-226 | 38 |
| **PY-7** | What is SAR acceptance policy? | `sar_acceptance_policy.py` lines 156-313 | 30 |
| **PY-8** | How does Snowpack physics work? | `snowpack_physics.py`, `meteoio_openmeteo.py` | 101 |
| **PY-9** | How does model training work? | `train_model.py` lines 642-743 | 47 |
| **PY-10** | What scheduled jobs exist? | `.github/workflows/ml_pipeline.yml` | Cron: 174 |
| **C-1** | Is active_learning_feedback.py shelved? | `active_learning_feedback.py` line 17 | 39 (shelved) |
| **C-2** | Are SHAP/promote-report edge functions active? | `shap-explainer/index.ts`, `promote-report/index.ts` | SHAP: 8, Promote: 3 |
| **C-3** | Why is RF published but not LSTM/SAR U-Net? | `lstm_model.py` lines 65-66, 310-318 | LSTM: 228, SAR: 265 |
| **C-4** | Does LSTM use historical or live data? | `sequence_features.py` lines 279-344 | LSTM: 228 |
| **C-5** | Is SAR U-Net for training or prediction? | `sar_unet_worker.py` lines 568-603 | SAR: 265 |
| **C-6** | LSTM vs RF on PSS/Brier — large gap? | `lstm_model.py` lines 591-596 | PSS: 8, Brier: 51 |
| **C-7** | LSTM held back by gate or data? | `lstm_model.py` lines 310-318 | LSTM: 228 |
| **C-8** | Are models probability-based? | `surrogate_rf.py` line 293, `lstm_model.py` line 120 | RF: 22, LSTM: 228 |
| **C-9** | Does DBSCAN affect probabilities? | `anomaly_detector.py` lines 536-589 | 0 (not connected to models) |

## Graphify Node Count Reference

| Term | Graphify Nodes | KS Nodes |
|---|---:|---:|
| `lstm` | 228 | 45 |
| `sar_unet` | 265 | 146 |
| `surrogate_rf` / `random_forest` | 22 | — |
| `calibration` | 180 | 43 |
| `brier` | 51 | 6 |
| `pss` | 8 | 2 |
| `shap` | 8 | 32 |
| `promote` | 3 | 16 |
| `active_learning` | 39 | 28 |
| `snowpack` | 101 | 91 |
| `verification` | 14 | 118 |
| `risk_math` | 44 | 4 |
| `label_governance` | 38 | 4 |
| `supabase` | 964 | — |
| `forecast` | 698 | 182 |
| `inference` | 286 | 110 |
| `train_model` | 47 | 2 |
| `meteoio` | 58 | — |
| `cron` | 174 | 2 |
