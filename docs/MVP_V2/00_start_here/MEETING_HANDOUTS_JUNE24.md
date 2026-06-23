# Meeting Handouts — June 24 DRDO Meeting

## 1. One-Page Brief for Dr. Amreek

---

**Avalanche Insight Hub — One-Page Brief**

**What we built:** A hosted, scientist-reviewable avalanche decision-support prototype with autonomous data generation, Swiss RAvaFcast reproduction, and batch-first ML architecture.

**Swiss RF4 Results (real data):**
- Accuracy: 89.5% on 29,296 EnviDat RF2 rows, 74 features, 300 trees
- Calibration: Isotonic regression, Brier 0.157, ECE 0.041
- Top SHAP drivers: Elevation, new snow height (HN72_24, HN24_7d), wind transport
- Feature audit: 3 feature sets compared, leakage-guarded

**What's new (the "electric light"):**
- Autonomous data genesis: LLM news extraction (Google Groundsource methodology), Sentinel-1 SAR, Open-Meteo weather
- Zero-data cold start: pipeline generates its own training data
- Probabilistic weather: Open-Meteo Ensemble API (p10/p50/p90)

**How we complement DRDO:**
- NATSAT: We generate AI predictions → NATSAT delivers alerts to soldiers
- HIM-STRAT: We provide autonomous data → feeds DGRE's own neural network snowpack models
- DRDO-ISRO MoU: Our GEE + Open-Meteo pipeline implements satellite snow cover + meteorological forecast vision
- Dr. Praven's group: We provide infrastructure + Swiss baseline → they provide domain expertise + Himalayan data

**What we can't do yet (honest):**
- GPxyz spatial interpolation: blocked (Swiss station coordinates missing)
- No Himalayan validation data
- SAR detection: shadow-gated (not operational)
- No operational deployment

**What we ask:**
1. One scientist POC for the autonomous pipeline sprint
2. 1-2 pilot regions for autonomous pipeline activation
3. Your ideas for augmentation — we explicitly invite them

**Demo:** https://avalanche-insight-hub.netlify.app

---

## 2. Complement Matrix for Dr. Praven

| Dimension | Our System | Dr. Praven's Group | Mutual Benefit |
|-----------|-----------|-------------------|----------------|
| **Data** | Autonomous pipeline (news + SAR + weather) | Limited Himalayan observations | We feed their models; they validate our events |
| **Models** | Swiss RF4 reproduction (89.5%), RF, LSTM | Himalayan-specific models (HIM-STRAT lineage) | Swiss baseline as reference; their models as ground truth |
| **Infrastructure** | Web platform, GitHub Actions, Supabase, Modal GPU | DGRE computing resources, field stations | We provide scalable infra; they provide field validation |
| **Domain expertise** | Software engineering, ML, data pipeline | 30+ years Himalayan avalanche science | They guide truth standards; we implement at scale |
| **Transferability** | Pérez-Guillén et al. (2026): Swiss→Pyrenees transfer proven | Himalayan-specific adaptation needed | Joint validation of Swiss→Himalayan transfer |
| **Operational goal** | Decision-support prototype | Operational automated pipeline | We build the pipeline; they operate it |

**Key insight:** Dr. Praven's email stated: "My aim is to implement a similar data driven automated pipeline for our operational purposes." Our system IS that pipeline — we provide the infrastructure, they provide the operational context.

---

## 3. Comparison Table: Us vs. State of the Art

| System | Method | Accuracy/F1 | Data Source | Explainability | Region |
|--------|--------|------------|-------------|----------------|--------|
| **Our Swiss RF4** | Random Forest + isotonic calibration | **89.5% acc, 0.753 macro F1** | EnviDat RF2 (29K rows) | TreeSHAP (top 10 features) | Swiss Alps |
| RAvaFcast v1.0.0 (Pérez-Guillén 2024) | RF + GPxyz + elevation aggregation | 66% day acc (full domain), 70% (Alps) | EnviDat RF1/RF2 + SNOWPACK | SHAP (NHESS 2025) | Swiss Alps |
| HIM-STRAT (Joshi, Singh 2020) | ANN snowpack simulation | HSS validated, 5 winters | Manual weather + snow stratigraphy | Neural network (black box) | NW Himalaya |
| EGU 2026 DSS (Sharma & Tiwari) | SVM/RF/LightGBM + AHP | ROC-AUC=0.855 | MODIS, Sentinel-2, AMSR-2, SRTM | AHP + permutation importance | NW Himalaya (J&K) |
| CCDT-ADA-Net (IEEE 2026) | Multimodal DL (CCDT + ADA-Net) | ROC-AUC=0.99, F1=0.96 | SAR + optical + snowpack + met (150 events) | Permutation importance | Tianshan, China |
| Google Groundsource (2026) | Gemini LLM news extraction + LSTM | 2.6M flood events extracted | News articles (5M) | N/A (data generation) | Global (150+ countries) |
| Norwegian SAR (Karlsen 2019) | SAR change detection | POD=67%, FAR=46% | Sentinel-1 SAR | Threshold-based | Norway |

**Our position:** We combine the Swiss RF4 approach (highest accuracy on EnviDat) with Groundsource-style autonomous data generation and TreeSHAP explainability — targeting the Himalayan data scarcity problem that HIM-STRAT and EGU 2026 DSS also address.

---

## 4. Honest Limitations List

| Limitation | Status | What's Needed |
|-----------|--------|--------------|
| GPxyz spatial interpolation | Blocked | Swiss station coordinates (latitude, longitude) |
| Himalayan validation | Not started | Pilot region + scientist-reviewed truth labels |
| SAR avalanche detection | Shadow-gated | Labeled SAR dataset + validation gates |
| Operational deployment | Not deployed | Scientist approval + operational integration |
| Himalayan training data | Zero rows | Autonomous pipeline activation (2-4 weeks) |
| SNOWPACK physics model | Not integrated | Would require SNOWPACK or Crocus installation |
| Sub-level danger prediction | Not implemented | Swiss sub-level approach (Maissen et al., 2024) |
| Avalanche problem type | Not classified | Multi-label classifier (Horton et al., 2020) |

---

## 5. Data Sources We Can Use

| Source | Type | Cost | Status |
|--------|------|------|--------|
| Open-Meteo Forecast | Deterministic weather | Free | Active |
| Open-Meteo Ensemble | Probabilistic weather (p10/p50/p90) | Free | Code ready |
| Open-Meteo Archive | Historical weather | Free | Active |
| Google Earth Engine (Sentinel-1) | SAR satellite | Free (with GEE account) | Code ready, credentials needed |
| newsdata.io + Gemini | LLM news extraction | ~$50/mo | Code ready, API key needed |
| NASA GIBS | Snow cover visualization | Free | Available |
| ISRO satellite data | Snow cover, glacier | Via DRDO-ISRO MoU | Collaboration needed |
| DGRE AWS network | 71 surface observatories | Via collaboration | Collaboration needed |
