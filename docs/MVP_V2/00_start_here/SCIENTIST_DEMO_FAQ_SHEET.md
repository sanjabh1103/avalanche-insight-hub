# Scientist Demo FAQ Sheet — 31 Expected Questions

Status: 2026-06-21
Purpose: Prepared answers for senior scientists (30+ years experience) at the June 24th demo
Boundary: All answers are evidence-grounded with codebase references. Claim boundaries are respected.

---

## Q1: How does your model handle the extreme class imbalance in Himalayan avalanche data?

Avalanches are rare events — non-avalanche days vastly outnumber avalanche days, often by 100:1 or more. Standard classifiers achieve >90% accuracy by always predicting "no avalanche," generating fatal false negatives.

**Our approach (3 layers):**

1. **KMeansSMOTE** — Synthetic minority oversampling that generates credible synthetic avalanche-day instances via K-means clustering and interpolation. Config: `k_neighbors=5`, `cluster_balance_threshold=0.1`. Unlike naive SMOTE, KMeansSMOTE avoids generating noise in sparse regions.
   - Evidence: `backend/models/surrogate_rf.py:189-200`

2. **Cost-sensitive Random Forest** — Asymmetric class weights `{0:1, 1:4}` penalize false negatives 4× more than false positives. The model cannot achieve high accuracy by ignoring the minority class.
   - Evidence: `backend/models/surrogate_rf.py:17` — `SURROGATE_CLASS_WEIGHT = {0: 1, 1: 4}`

3. **PSS as primary metric** — Peirce Skill Score (not accuracy) measures discrimination ability accounting for both false alarms and missed events. Time-series CV reports mean PSS across 5 chronological folds.
   - Evidence: `backend/models/surrogate_rf.py:241-246` — RF with `class_weight=SURROGATE_CLASS_WEIGHT`

4. **MTS-LSTM governance** — KMeansSMOTE is explicitly forbidden in sequence space (it destroys temporal structure). The LSTM uses weighted sampling + focal-loss style objectives instead.
   - Evidence: `backend/models/mts_lstm.py:10-16` — governance comment block

---

## Q2: What features are you using and how did you select them?

**Feature selection: SVM-RFE (Support Vector Machine Recursive Feature Elimination)**

The literature shows that feeding 40+ raw meteorological variables causes overfitting and computational bloat. SVM-RFE iteratively evaluates feature subsets via cross-validation, reducing to the most predictive 7-15 features.

**Selected features include:**
- Fresh snowfall (24h, 72h rolling windows)
- Cumulative seasonal snow
- Minimum/maximum temperature
- Wind speed and wind loading
- Sunshine duration / shortwave radiation
- Terrain: slope angle, aspect, elevation, roughness
- Snowpack proxy: estimated shear strength

**Key insight from Himalayan research:** Avalanching conditions ripen over 2-3 days, not instantaneously. The rolling windows capture this "ripening" period.

- Evidence: `backend/models/surrogate_rf.py:408-414` — `RFE(estimator=SVC(kernel='linear', class_weight='balanced'), n_features_to_select=15)`
- Target feature count: `SURROGATE_TARGET_FEATURE_COUNT = 15`

---

## Q3: How do you handle the sparse AWS network in the Himalayas?

This is the #1 structural barrier for physical snowpack models (SNOWPACK, SAFRAN-CROCUS-MEPRA) in the Himalayas — they require continuous hourly station data that is unavailable during storms.

**Our approach eliminates AWS dependency entirely:**

1. **Open-Meteo Global Weather API** — Provides temperature, precipitation, snowfall, wind, and radiation at 11km GFS / 9km ECMWF resolution globally. No local stations needed.
2. **DEM-based elevation downscaling** — 90m SRTM DEM used for lapse-rate correction. Each grid cell gets elevation-adjusted weather even in data-sparse terrain.
3. **Snowpack proxy (seasonal_cumulative_v1)** — Replaces physical snowpack models that need station data. Uses cumulative snowfall, temperature gradients, and wind loading as proxies for snowpack stability.
4. **20×20 grid (400 cells)** — Each cell gets independent weather + terrain + snowpack features.

- Evidence: `backend/common/real_features.py:169-186` — Open-Meteo fetch with elevation downscaling
- Evidence: `backend/common/snowpack_proxy.py` — `compute_region_snowpack_proxy()`
- Evidence: `backend/data/dem/himalayas_nepal.tif` — Himalayan DEM file confirmed present

---

## Q4: What is your risk fusion method and why not weighted linear additive?

**The problem with weighted linear additive (traditional GIS):**
It assumes "total compensation" — a safe factor (flat slope) can mathematically offset a dangerous factor (heavy snowfall). A 10° flat slope will never avalanche regardless of snow load, but the additive model produces "moderate" risk. This is physically wrong and dangerous.

**Our solution: Chebyshev Ideal Point Analysis (IPA)**

A non-compensatory Multi-Criteria Decision-Making method that measures the maximum weighted deviation from an ideal hazard point. The **dominant criterion** (highest weighted deviation) drives the final risk level — safe terrain cannot mask critical weather triggers.

**5-criteria hazard vector:**
| Criterion | Weight | What it captures |
|---|---|---|
| Probability | 1.0 | Model-predicted avalanche probability |
| Slope deviation from 38° | 1.0 | Avalanche-prone slope angle (peak at 38°) |
| Aspect risk | 0.8 | Wind loading / solar radiation by aspect |
| Snowpack weakness | 0.9 | Inverse of shear strength (weak layer proxy) |
| Exposure | 0.7 | Infrastructure/road proximity |

- Evidence: `backend/common/risk_math.py:9-15` — `DEFAULT_IPA_WEIGHTS`
- Evidence: `backend/common/risk_math.py:73-94` — `chebyshev_ipa()` function
- Evidence: `backend/daily_inference.py:759` — `ipa_result = chebyshev_ipa(vector, weights)`

---

## Q5: How do you validate the model? What metrics do you use?

**Validation framework:**

| Component | Method | Purpose |
|---|---|---|
| Cross-validation | TimeSeriesSplit (5 folds, chronological) | Prevents temporal leakage |
| Primary metric | PSS (Peirce Skill Score) | Discrimination ability (not accuracy) |
| Calibration | Brier score, ECE | Probability reliability |
| Threshold | Youden index | Optimal decision boundary |
| Holdout | Scientist-approved slices | Downstream promotion gate (not required for pipeline activation) |
| Scientist review | Daily verification workflow | Paired model-vs-scientist comparison |

**Promotion gates (for candidate models):**
- PSS must beat current baseline
- Brier/ECE must pass calibration threshold
- Stability across rolling windows
- Latency and cost ceiling
- Forecast freshness SLA
- Explanation consistency

- Evidence: `backend/models/surrogate_rf.py:14` — `TimeSeriesSplit`
- Evidence: `backend/train_model.py:50` — `TIME_SERIES_SPLITS = 5`
- Evidence: `/scientist/daily-verification` route for paired comparison

---

## Q6: What is the MTS-LSTM and why is it gated?

**Branched Multi-Timescale LSTM (MTS-LSTM)**

A true sequence model with three input branches:
- **Hourly weather branch**: 32-hidden-unit LSTM processing hourly weather sequences
- **Daily weather branch**: 24-hidden-unit LSTM processing daily weather sequences
- **Static terrain branch**: 16-unit encoder for slope, aspect, elevation, roughness

The branches merge into a 32-unit head that outputs avalanche probability. This captures both short-term weather dynamics (hourly storm evolution) and long-term snowpack evolution (daily accumulation/melt cycles).

**Why it's gated (not in production):**
1. Insufficient Himalayan training data for sequence models
2. Promotion gates not yet passed (PSS, Brier, stability, latency, cost)
3. Currently in shadow mode alongside the RF surrogate
4. The RF surrogate remains the production scorer with TreeSHAP explainability

- Evidence: `backend/models/mts_lstm.py:17-56` — `BranchedMTSLSTM` class
- Evidence: `backend/models/mts_lstm.py:10-16` — governance: no SMOTE in sequence space
- Evidence: `backend/lstm_model.py:627-633` — `shadow_mode_active: True`

---

## Q7: How does SAR segmentation work and what is its status?

**SAR (Synthetic Aperture Radar) Avalanche Segmentation**

Uses Sentinel-1 C-band radar which penetrates cloud cover, snowfall, and operates day/night — solving the observational blind spot during storm cycles when optical satellites are useless.

**Model architectures:**
- **Swin Transformer V2 Tiny U-Net** (cold-start) — state-of-the-art transformer for image segmentation
- **ResNet34-UNet** — CNN baseline with encoder-decoder skip connections

**Status: Shadow-gated (`SAR_UNET_PROMOTED=false`)**
- Not in production scoring
- Used only for label mining and research
- Transfer from external labeled Sentinel-1 corpora, not zero-label bootstrapping
- Physics gate: `training_eligible = true` only when `25° ≤ slope ≤ 65°`

**Why gated:** Qualification requires F1/IoU validation, wet/dry snow constraints, revisit timing analysis, and region-specific evaluation before promotion.

- Evidence: `backend/sar_unet_worker.py:57-58` — `SAR_UNET_MODEL_FAMILY = 'resnet34_unet'`
- Evidence: `backend/sar_unet_worker.py:376-379` — supported families: `resnet34_unet`, `swinunet_tiny_diff`
- Evidence: `backend/historical_sar_backfill.py:14-17` — physics gate for training eligibility

---

## Q8: How do you communicate uncertainty to end users?

**Multi-layer uncertainty communication:**

1. **Confidence state** — `normal` or `reduced` with explicit reasons (e.g., `high_uncertainty_share`, `low_sar_coverage_share`)
2. **Uncertainty class** — `low`, `medium`, `high` derived from prediction variance across ensemble/CV folds
3. **95% confidence interval** — Lower and upper bounds displayed per cell
4. **Stale/unavailable/masked states** — Prevents false low-risk messaging. Cells without valid terrain or weather data show `MASKED` or `UNAVAILABLE` instead of a misleading low score.
5. **Data freshness badge** — `PRECOMPUTED BATCH - READY (72h)` or `STALE` with time since last batch

- Evidence: `backend/daily_inference.py:604-610` — `uncertainty_class()` function
- Evidence: `backend/daily_inference.py:1088-1090` — confidence interval computation
- Evidence: `src/lib/partnerEvidenceReadiness.ts` — confidence state logic

---

## Q9: What is TreeSHAP and how is it used?

**TreeSHAP (Tree SHapley Additive exPlanations)**

An exact explainability method for tree-based models that computes Shapley values — the fair contribution of each feature to a specific prediction. Unlike gradient-based approximations, TreeSHAP is mathematically exact for tree ensembles.

**How it's used in the UI:**
- Each grid cell shows a bar chart of top contributing features
- Example: "snowfall_24h contributed +0.15, slope_angle contributed +0.08, wind_loading contributed +0.06"
- The sum of SHAP values equals the difference between the prediction and the baseline

**Honest fallback:**
When the SHAP explainer artifact is unavailable, the UI shows heuristic risk-driver explanations with an explicit `FALLBACK` badge — no false claim of active TreeSHAP.

**Governance:**
TreeSHAP is applied to the **surrogate Random Forest**, not the MTS-LSTM. The contract states that explanations interpret the surrogate aligned to the production forecast, not recurrent model internals.

- Evidence: `backend/daily_inference.py:1100-1180` — SHAP context per cell
- Evidence: `backend/daily_inference.py:1177-1181` — `explainability_mode` and `fusion_method` in cell output

---

## Q10: How does the 3D voxel view work?

**3D Neighborhood Voxel View**

Extrudes ground cells into terrain columns based on DEM elevation data, creating an immersive Minecraft-style block map of the actual mountain topography. Buildings, lifts, and roads are shifted above the terrain surface.

**Key features:**
- Synced with the time slider — users see risk evolve hour-by-hour across specific slope aspects
- Color-coded by danger level (EAWS 1-5 scale)
- Terrain features (roads, infrastructure) visible for context
- Remains visibly volumetric even with sparse OpenStreetMap data

**Why it matters for Himalayas:**
Traditional 2D hazard maps cannot convey slope-specific risk in complex 3D terrain. The voxel view lets forecasters and rescue teams visually track how localized avalanche risk evolves across aspects and elevations.

- Evidence: `src/components/VoxelNeighborhoodModal.tsx`

---

## Q11: What are the claim boundaries? What can't you say?

**Hardcoded claim locks:**

| Claim | Status | Why |
|---|---|---|
| "Himalayan operational accuracy" | ❌ Blocked | `himalayan_accuracy_claim_allowed: false` — no validated local evidence |
| "Official warning service" | ❌ Blocked | No authority handoff or public warning mandate |
| "Promoted SAR detection" | ❌ Blocked | `SAR_UNET_PROMOTED=false` — shadow-gated |
| "Production MTS-LSTM" | ❌ Blocked | Shadow mode only; gates not passed |
| "Validated against field data" | ❌ Blocked | No Himalayan field validation completed |
| "Users can rely on this for field safety" | ❌ Blocked | UI states experimental, not for life-critical decisions |

**Approved language:**
- "Hosted decision-support prototype"
- "Experimental EAWS-style bulletin"
- "Precomputed batch artifacts"
- "Candidate/gated paths with release gates"
- "Scientist co-working and validation workflow"

- Evidence: `src/lib/partnerEvidenceReadiness.ts` — `himalayan_accuracy_claim_allowed: false`
- Evidence: `docs/MVP_V2/00_start_here/PROTOTYPE_TOP15_FEATURES_AND_FUTURE_PLAN.md:7-19` — locked claim wording

---

## Q12: How does this compare to RAvaFcast / Swiss three-stage pipeline?

**RAvaFcast (Swiss three-stage):**
1. RF1/RF2: Station-level danger rating prediction
2. GPxyz: Gaussian process interpolation across terrain
3. Aggregation: Warning-region level danger rating

**Our pipeline:**
1. Open-Meteo global weather → DEM downscaling → terrain features
2. SVM-RFE + RF surrogate → calibrated probability per grid cell
3. Chebyshev IPA fusion → EAWS 1-5 risk level per cell
4. Batch publication → Supabase storage → frontend hydration

**Key differences:**
- We don't need station density — global weather APIs + DEM replace local stations
- We reproduce the RF4 research signal from EnviDat data (research lane)
- GPxyz is blocked pending station coordinates from the partner
- Our risk fusion is non-compensatory (Chebyshev IPA) vs RAvaFcast's station-level approach
- We have embedded explainability (TreeSHAP) and 3D visualization

**What we share:** Batch-first philosophy, RF baseline, calibration discipline, chronological validation.

- Evidence: `backend/reproduction/swiss_ravafcast/train_rf4.py:391-396` — RF4 reproduction
- Evidence: `docs/MVP_V2/Cust_comm2.md:1-14` — customer shared RAvaFcast papers

---

## Q13: What do you need from us to activate the autonomous pipeline?

**Almost nothing — that is the point of the autonomous design.**

The pipeline generates its own training data through three autonomous channels (news extraction, SAR satellite, weather APIs). No historical datasets, station data, snowpack profiles, or occurrence records are required to start.

**What we need (minimal):**

| Ask | Why | Priority |
|---|---|---|
| One scientist point of contact | To avoid fragmented communication and guide operational relevance | Essential |
| 1-2 suggested pilot regions | To focus the autonomous pipeline activation geographically | Essential |
| Operational feedback on pipeline output | To ensure forecasts meet decision-support needs | Essential |

**What we do NOT need:**
- No historical avalanche occurrence records
- No station data or snowpack profiles
- No manual field observations
- No holdout datasets upfront

**Optional (augmentation, not prerequisite):**
If your team later wants to validate autonomous pipeline output against local data, we have prepared partner evidence templates (`docs/MVP_V2/Artifacts/03_partner_handoff_packet/partner_field_dictionary.md`). Scientist-reviewed local data can augment the autonomous pipeline — but this is a downstream enhancement, not a startup requirement.

**Process:** 2-4 week autonomous pipeline sprint (Week 1-2: pipeline activation, Week 3-4: first forecasts + scientist review, Week 4: results and decision).

- Evidence: `docs/MVP_V2/00_start_here/SCIENTIST_COLLABORATION_PITCH_MVP1_MVP2.md:107-117` — "No historical data, station data, or snowpack datasets are required."

---

## Q14: How is the model calibrated and how often is it retrained?

**Calibration:**
- Isotonic regression via `CalibratedClassifierCV` — maps raw RF probabilities to calibrated risk probabilities
- Reduces overconfidence and ensures probability reliability (Brier score)

**Retraining schedule:**
- Weekly cron via GitHub Actions (Sundays)
- Event-count precheck: refuses training when <30 eligible severe events (insufficient for KMeansSMOTE k=5)
- Drift detection with skip-gating (reports drift stats but does not autonomously remediate)

**Parameter optimization:**
- ABC (Artificial Bee Colony) metaheuristic — population-based optimization that navigates multiple local optima in the calibration landscape
- Eliminates subjective expert guessing of model weights
- Employed bees (exploitation) + Onlooker bees (concentrated search) + Scout bees (exploration)

**Promotion:**
- Model promotion requires scientist-approved slices + benchmark pass + stability check
- No autonomous promotion — scientist review creates governed candidates

- Evidence: `backend/models/surrogate_rf.py:10` — `from sklearn.calibration import CalibratedClassifierCV`
- Evidence: `backend/train_model.py:50-55` — `TIME_SERIES_SPLITS`, `MIN_EVENTS_FOR_TRAINING = 30`
- Evidence: `backend/common/abc_optimizer.py:222-227` — ABC optimizer output

---

## Q15: What makes this platform unique compared to existing Himalayan forecasting?

**13 uniqueness factors:**

| # | Factor | Solves which long-standing problem |
|---:|---|---|
| 1 | Chebyshev IPA non-compensatory fusion | Safe terrain masking critical weather triggers |
| 2 | Global weather API + DEM downscaling | Sparse AWS network dependency |
| 3 | SVM-RFE feature elimination | Feature redundancy and overfitting |
| 4 | KMeansSMOTE + cost-sensitive learning | Extreme class imbalance |
| 5 | Batch-first published artifacts with provenance | Black-box trust and reproducibility |
| 6 | Embedded TreeSHAP explainability | Black-box model opacity |
| 7 | 3D voxel terrain visualization | Spatial-temporal disconnect |
| 8 | Honest claim boundaries (hardcoded) | Premature operational claims |
| 9 | Scientist co-working workflow | Expert displacement fear |
| 10 | SAR autonomous label pipeline | Historical occurrence record gaps |
| 11 | MTS-LSTM multi-timescale sequences | Single-timescale modeling limitation |
| 12 | ABC metaheuristic calibration | Subjective parameter weighting |
| 13 | Zero-cost infrastructure | Computational bottlenecks and cost barriers |

**The core differentiator:** This is not just a model — it's an integrated platform that combines honest ML, non-compensatory risk fusion, embedded explainability, 3D visualization, scientist co-working, and governed candidate promotion in a single hosted system. The uniqueness is in the **integration and honesty**, not in any single algorithm.

- Evidence: Full codebase — `backend/common/risk_math.py`, `backend/models/surrogate_rf.py`, `backend/models/mts_lstm.py`, `backend/sar_unet_worker.py`, `backend/common/abc_optimizer.py`, `src/lib/partnerEvidenceReadiness.ts`

---

## Q16: How do I access the scientist workspace and admin dashboard?

Both `/scientist` and `/admin` routes require an authenticated Supabase session via `RoleAccessGate`. The scientist workspace requires a `scientist` role; the admin dashboard requires an `admin` role. Contact the team for demo credentials before the live walkthrough.

- Evidence: `src/components/RoleAccessGate.tsx`, `src/pages/ScientistPage.tsx:67-73`, `src/pages/ScientistDailyVerificationPage.tsx:67-72`

---

## Q17: Why don't I always see daypart bulletins on the forecast map?

The EAWS-style daypart bulletin (`ForecastBulletinBadge`) renders only when the batch pipeline has populated `forecast_bulletins` for the current active forecast run in Supabase. If the bulletin data is absent, the grid still shows cell-level risk scores, calibrated probabilities, and uncertainty classes. The bulletin is an optional enrichment layer, not a blocking dependency.

- Evidence: `src/components/ForecastBulletinBadge.tsx:51` — `if (!bulletin) return null;`; `src/hooks/useForecastState.ts:506` — `normalizeForecastBulletin(response.forecastBulletin ?? manifest.forecastBulletin ?? null)`

---

## Q18: Why doesn't clicking some grid cells open the inspection panel?

Cells marked as **UNAVAILABLE TERRAIN** (greyed out) or **MASKED** are disabled — they don't produce forecasts and don't respond to clicks. Only eligible cells (colored by risk level) respond to clicks and open the `RiskDashboard` inspection panel in the sidebar. The click handler explicitly checks `isUnavailable` before triggering `onCellClick`.

- Evidence: `src/components/AvalancheMap.tsx:161` — `eventHandlers={{ click: () => { if (!isUnavailable) onCellClick(cell); } }}`

---

## Q19: How do I access the 3D voxel terrain view?

The 3D neighborhood view is accessible two ways:
1. **Expert Mode**: Toggle Expert Mode (top-right button), then click "Open 3D" in the Expert Mode panel.
2. **URL parameter**: Add `&3d=1` to any forecast URL (e.g., `/?region=Colorado%20Rockies&3d=1`).

The 3D view renders a Minecraft-style block-by-block terrain using real OSM data for the selected area.

- Evidence: `src/components/ExpertModePanel.tsx:129` — `onClick={onToggle3D}`; `src/hooks/useForecastState.ts:653` — `if (params.get('3d') === '1') setShow3DModal(true)`

---

## Q20: What does "Data age" mean in the UI?

The data age indicator shows time since the last successful batch forecast run. States:
- **Fresh**: < 12 hours since last batch run
- **Aging**: > 12 hours since last batch run
- **Stale**: > 24 hours since last batch run

The system continues serving the last valid published forecast with a freshness warning. This is an honesty feature — it communicates batch pipeline health transparently rather than hiding stale data.

- Evidence: `src/components/DataLatencyBanner.tsx`; `src/hooks/useForecastState.ts` — `forecastAvailability` state

---

## Q21: What does "Gate: mts_head_unavailable" mean in the candidate model display?

The MTS-LSTM deep learning candidate model has not passed its readiness gate — specifically, the multi-temporal snow/head data required for the LSTM's multi-timescale input sequence is unavailable. The surrogate Random Forest (`surrogate_rf_v1`) remains the active scorer. The candidate will enter shadow mode only when all gate criteria are met.

- Evidence: `src/components/AdminDashboard.tsx:527-531` — `dynamic_model_candidate` gate status; `backend/models/mts_lstm.py` — governance requirements

---

## Q22: How does your pipeline compare to RAvaFcast's three-stage architecture in depth?

**RAvaFcast (GMD 2024) three-stage pipeline:**
1. RF1/RF2: Station-level danger rating prediction from weather + snowpack features
2. GPxyz: Gaussian process interpolation across terrain using station coordinates
3. Aggregation: Warning-region level danger rating via elevation-band aggregation

**Our Swiss reproduction lane status:**
- **Stage 1 (RF4):** Initial reproduction signal achieved. Calibrated accuracy 0.8937, macro-F1 0.7508, class-4 F1 0.3636. Feature/parity audit complete comparing `auto_numeric_current`, `paper_candidate_whitelist`, and `leakage_guarded` feature sets.
- **Stage 2 (GPxyz):** Module complete with exact-GP cap and metadata gate. **Blocked** — downloaded EnviDat RF1/RF2 CSVs contain station IDs and elevation but no latitude/longitude. Cannot honestly run GP interpolation without station coordinates.
- **Stage 3 (Aggregation):** Station-row baseline accuracy 0.8085, macro-F1 0.7848. Full RAvaFcast parity needs GP grid and official warning-region polygons.

**Key boundary:** All Swiss reproduction artifacts carry `usage_boundary=research_only` and `production_scoring_allowed=false`. No Himalayan operational claim is made from Swiss-trained artifacts.

**What we need from the partner for full Swiss parity:** Station metadata table with `station_code`, `latitude`, `longitude`, `elevation_m`, and warning-region polygon IDs for all 129 RF2 station IDs.

**Important boundary:** This is only for full Swiss RAvaFcast GPxyz spatial interpolation in the research lane. The autonomous Himalayan pipeline does not require station coordinates — it uses global weather APIs and DEM downscaling.

- Evidence: `backend/reproduction/swiss_ravafcast/train_rf4.py:391-396` — RF4 reproduction
- Evidence: `backend/reproduction/swiss_ravafcast/gpxyz_interpolation.py` — GPxyz module with metadata gate
- Evidence: `docs/MVP_V2/Swiss_Reproduction_Lane.md` — full reproduction status

---

## Q23: Does KMeansSMOTE generate physically plausible synthetic samples?

**Current status:** No. KMeansSMOTE currently interpolates in feature space without physical-plausibility constraints. This means synthetic samples can contain unphysical combinations — for example, high temperatures at high elevations during mid-winter, or wind loading values that contradict terrain aspect.

**Why this matters:** Kaushik et al. 2025 emphasizes physical feature discipline in Himalayan avalanche prediction. Unphysical synthetic samples can create distorted decision boundaries that fail on real data.

**Our plan (Phase 3 fix):** Add a physical-plausibility filter to synthetic sample generation that enforces:
- Lapse-rate consistency: temperature must decrease with elevation at a physically plausible rate (~6.5°C/km)
- Seasonal consistency: winter samples must not have above-freezing temperatures at high elevations
- Terrain-aspect consistency: wind loading values must be consistent with aspect and wind direction

This is a known limitation we are actively addressing. We are transparent about it because a 30-year scientist would detect it immediately.

- Evidence: `backend/models/surrogate_rf.py:189-200` — KMeansSMOTE configuration (no physical filter currently)
- Evidence: `docs/MVP_V2/Avalanche_Prediction_Accuracy_Top10_Gap_Plan.md` — rated 2/5 readiness

---

## Q24: What happens when Open-Meteo is unavailable?

**The system degrades gracefully:**

1. **Last valid forecast served:** The public route continues serving the last successfully published batch forecast from Supabase Storage. No real-time computation is attempted.
2. **Freshness warning:** The DataLatencyBanner shows "STALE" with time since last batch run. The UI explicitly communicates that data is not fresh.
3. **Batch pipeline retry:** The GitHub Actions batch pipeline retries on the next scheduled run. Transient failures trigger retry-on-failure logic.
4. **No silent failure:** The system never serves stale data without a visible freshness warning. Cells are not recalculated — they are served as-is with a stale badge.

**What does NOT happen:**
- No fallback to a different weather API (no secondary provider configured)
- No real-time computation in the browser
- No hiding of the stale state

- Evidence: `src/components/DataLatencyBanner.tsx` — freshness state display
- Evidence: `src/hooks/useForecastState.ts` — `forecastAvailability` state tracking
- Evidence: `backend/daily_inference.py` — batch pipeline (no real-time path)

---

## Q25: What is your data licensing and FAIR compliance posture?

**Data source licensing:**
| Data Source | License | Usage |
|---|---|---|
| Open-Meteo Global Weather API | CC-BY 4.0 | Weather features (temperature, precipitation, wind, radiation) |
| Sentinel-1 SAR | Copernicus Open License (free for research/commercial) | SAR backscatter for avalanche detection research |
| SRTM DEM | NASA Open Data (public domain) | Elevation downscaling and terrain features |
| EnviDat (WSL/SLF) | WSL Terms of Use | Swiss RAvaFcast reproduction (research only) |
| OSM (OpenStreetMap) | ODbL | Infrastructure/road proximity features |

**FAIR principles alignment:**
- **Findable:** All forecast artifacts include manifest files with SHA-256 digests and source references
- **Accessible:** Public forecast data accessible via Supabase REST API; scientist evidence exportable as MD/JSON
- **Interoperable:** EAWS danger scale, WMO IBFWS framing, CAP XML scaffold planned
- **Reusable:** Partner evidence contract enforces provenance, source traceability, and license scope before any training use

**Partner data licensing (conditional):** If partner data is provided in the future, it would be governed by the partner evidence contract (`backend/scripts/build_himalayan_accuracy_readiness_contract.py`). Partner data must include reviewed license scope before claim review. No partner data is used for training without explicit license review. The autonomous pipeline does not require partner data to function.

- Evidence: `docs/MVP_V2/00_start_here/DATA_LICENSING_FAIR_COMPLIANCE.md` — full licensing document
- Evidence: `backend/scripts/build_himalayan_accuracy_readiness_contract.py` — partner evidence contract with license scope fields
- Evidence: `docs/MVP_V2/Himalayan_PrePartner_Evidence_Finite_Checkpoint.md` — FAIR provenance requirements

---

## Q26: What is your plan for migrating from JSONB to object storage?

**Current architecture:** Forecast grids are stored as monolithic JSONB rows in Supabase `forecast_grids`. Each row contains all 400 cells × 72 hours of forecast data. This works for the current prototype scale but creates timeout risks at larger scales.

**Phase 4 migration plan:**
1. **Decompose:** Split monolithic JSONB into per-hour JSON artifacts stored in Supabase Storage (object storage)
2. **Manifest:** Generate a manifest file per forecast run listing all hour artifacts with paths and SHA-256 digests
3. **Lazy loading:** Frontend hydrates only the hours the user is viewing, loading additional hours on demand via the time slider
4. **Durable publication:** Replace fragile fresh-row publication with a durable publication protocol that writes artifacts first, then atomically updates the active run pointer

**What this enables:**
- No single payload > 1MB (prevents timeout issues)
- Horizontal scaling (object storage handles concurrent reads better than JSONB queries)
- Partial loading (mobile users load only current hour, not all 72)
- Audit trail (each hour artifact has its own hash and publication timestamp)

**What this does NOT change:**
- The public UI contract remains the same (same forecast workspace, same cell inspection)
- The batch pipeline still runs upstream (no real-time computation)
- The scientist workbench still accesses the same data (via manifest-based hydration)

- Evidence: `docs/delivery/AVA-ARCH-001/avalanche-forecasting-gap-assessment.md` — architecture gap assessment scoring this 5/5 severity
- Evidence: `supabase/functions/run-forecast/index.ts` — current JSONB publication path

---

## Q27: What is the current status of the autonomous data pipeline?

**Answer:** The autonomous data genesis pipeline is code-ready and scheduled via GitHub Actions. It consists of three data collection paths:

1. **News extraction** (newsdata.io + Gemini LLM): Queries avalanche-related news with Himalayan-specific keywords in English and Hindi. Implements Google's Groundsource methodology, which explicitly identifies avalanches as a target hazard. Gracefully skips when API keys are not configured.

2. **SAR extraction** (Sentinel-1 via Google Earth Engine): Detects wet-snow changes using VV/VH thresholding with terrain masking. Shadow-gated research path. Gracefully skips when GEE credentials are absent.

3. **Weather ingestion** (Open-Meteo): Continuous meteorological data for training and inference.

**Current status:** Pipeline code is activated and scheduled. API keys (NEWSDATA, GEE) need to be configured in GitHub Secrets for live collection to begin. Once activated, first Himalayan events are expected within 2-4 weeks. Model quality improves as data accumulates.

**What we can show at the meeting:** Swiss RF4 reproduction metrics (89.5% accuracy on real EnviDat data), pipeline code, GitHub Actions workflows, and graceful degradation behavior.

- Evidence: `backend/news_ingest.py`, `backend/gee_extractor.py`, `.github/workflows/ml_pipeline.yml`, `backend/reproduction/artifacts/reproduction_summary.md`

---

## Q28: How does this system relate to DRDO's NATSAT system?

**Answer:** NATSAT (Navigation, Avalanche warning & Tracking via Satellite) is a satellite-based warning dissemination system developed by DEAL and DGRE. It delivers alerts to soldiers in high-altitude areas via satellite communication. NATSAT-M (mini terminal) and NATSAT-H (handheld) terminals were transferred to BEL in October 2025.

Our system is a **software intelligence layer that complements NATSAT**:
- NATSAT handles **warning dissemination** — delivering alerts to soldiers via satellite
- Our system handles **AI prediction and data generation** — producing the intelligence that triggers those alerts
- Together: our system generates the avalanche risk forecast → NATSAT delivers the alert to the soldier

We do not compete with NATSAT. We provide the prediction intelligence that NATSAT's dissemination infrastructure needs.

- Evidence: https://www.drdo.gov.in/drdo/en/offerings/products/navigation-avalanche-and-tracking-satellite-natsat

---

## Q29: How does this complement Dr. Praven's group's work?

**Answer:** Dr. Praven's group is "actively working on these aspects and we have developed similar models based on limited data available in the Himalayas." Their aim is "to implement a similar data driven automated pipeline for our operational purposes."

Our system complements their work in two ways:
1. **Autonomous data pipeline**: Our news extraction + SAR + weather pipeline can feed their existing Himalayan models with continuous event data, reducing their data scarcity problem
2. **Swiss reproduction lane**: Our trained Swiss RF4 model (89.5% accuracy) and transferability evidence (Pérez-Guillén et al., 2026) provide a scientific baseline for their Himalayan model development

They provide domain expertise, limited Himalayan data, and operational context. We provide infrastructure, autonomous data generation, and Swiss reproduction artifacts. Mutual benefit.

- Evidence: `docs/MVP/mails.md:112-118` — Dr. Praven's email about similar models and automated pipeline

---

## Q30: How does this relate to HIM-STRAT?

**Answer:** HIM-STRAT (Joshi, Singh & Satyawali, 2020) is a neural network-based model for snow cover simulation and avalanche hazard prediction over the NW Himalaya, developed by DGRE scientists including Dr. Amreek Singh and Dr. P.K. Satyawali (DGRE Director). It simulates snowpack parameters (RAM hardness, shear strength, temperature, density, layer thickness) using manually observed weather data and predicts avalanches using a stability index derived from those parameters.

Our system **extends HIM-STRAT's vision** in three ways:
1. **Autonomous data generation**: HIM-STRAT relies on manually observed weather data. Our autonomous pipeline (news + SAR + weather APIs) can provide continuous data without manual observation burden.
2. **Swiss reproduction baseline**: Our RF4 model (89.5% accuracy on EnviDat) provides a peer-reviewed reference point for evaluating Himalayan model performance.
3. **Infrastructure scale**: HIM-STRAT was developed for Chowkibal–Tangdhar region. Our web-based platform can scale to multiple regions simultaneously.

We are not replacing HIM-STRAT — we are providing the data infrastructure and scientific baseline that can make HIM-STRAT-style approaches more effective.

- Evidence: Joshi, J.C., Kaur, P., Kumar, B., Singh, A., Satyawali, P.K. (2020). "HIM-STRAT: a neural network-based model for snow cover simulation and avalanche hazard prediction over North-West Himalaya." Natural Hazards, 103(1), 1239-1260.

---

## Q31: How does this align with the DRDO-ISRO MoU?

**Answer:** DRDO (DGRE) and ISRO (SAC) signed a memorandum of understanding for:
- Development and validation of satellite-based retrieval algorithms for snow cover, glacier, and terrain parameters
- Integration of high-resolution satellite meteorological forecasts
- Sharing field data and satellite imageries for operational geospatial products over the Himalayan region

Our system directly implements this vision:
- **Satellite retrieval**: We use Google Earth Engine with Sentinel-1 SAR for snow cover change detection
- **Meteorological forecasts**: We ingest Open-Meteo weather data (temperature, precipitation, wind, radiation) at high spatial resolution
- **Operational geospatial products**: Our forecast grids are published as structured artifacts with full provenance

The MoU was signed by Dr. P.K. Satyawali (Director DGRE) and Nilesh Desai (Director, ISRO SAC). Our system is designed to be compatible with the data sharing and product generation vision of this collaboration.

- Evidence: https://www.tribuneindia.com/news/defence/drdo-isro-join-hands-to-enhance-use-of-space-assets-for-himalayan-meteorology/ — DRDO-ISRO MoU announcement
