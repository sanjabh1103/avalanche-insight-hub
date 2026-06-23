# PPTX Slide Fix Guidance — Avalanche_Insight_Hub_Scientist_Demo.pptx

Status: 2026-06-24
Purpose: Slide-by-slide fix instructions for the scientist demo deck, aligned with codebase verification and adversarial gap analysis.
Boundary: Every fix is verified against the actual codebase. No slide may claim something the code does not support.

---

## Slide 1: Title / Architecture Overview

| Issue | Fix |
|---|---|
| References `pg_cron` — not used in the codebase | Remove pg_cron reference. Add "PWA Background Sync for offline field reports" (evidence: `vite.config.ts` VitePWA BackgroundSync config) |
| Claims "100% remote" | Remove "100% remote" claim. State "batch-first architecture with precomputed artifacts served from Supabase Storage" |

## Slide 2: Data Sources

| Issue | Fix |
|---|---|
| Implies Open-Meteo has 100% uptime | Frame as "Open-Meteo: best-effort global weather API with deterministic fallback to last valid published forecast" |
| Missing fallback behavior | Add: "When Open-Meteo is unavailable, the system serves the last valid forecast with a STALE freshness warning. No real-time computation is attempted." |

## Slide 3: Event Data / PostGIS

| Issue | Fix |
|---|---|
| Hard-coded event counts | Remove all hard-coded event counts. Use "spatial database" not "PostGIS" unless specifically discussing the PostGIS extension |
| Direct PostGIS phrasing | Replace with "Supabase spatial database with PostGIS extension for geometry operations" |

## Slide 4: Snowpack Modeling (CRITICAL)

| Issue | Fix |
|---|---|
| "Snowpack proxy" is ambiguous | Explicitly state: "Weather-Driven Cumulative Heuristic Proxy (seasonal_cumulative_v1)" |
| Missing upgrade path | Add: "Phase 2 target: Upgrade to thermodynamic SNOWPACK/Crocus model when partner station data is available" |
| Missing limitation | Add: "Current proxy does not model heat flux, water percolation, or crystal metamorphism. It uses cumulative snowfall, temperature gradients, and wind loading as stability proxies." |

**Evidence:** `backend/common/snowpack_proxy.py` — `compute_region_snowpack_proxy()`

## Slide 8: Thresholding

| Issue | Fix |
|---|---|
| Fixed threshold description | Replace with "Data-driven Youden index / PSS thresholding" |
| Missing threshold source | Add: "Thresholds are computed from training/OOB distributions only, preventing holdout label leakage" |

**Evidence:** `backend/models/surrogate_rf.py:31-43` — `peirce_skill_score_max()` using ROC curve for optimal threshold

## Slide 9: Cost / Latency

| Issue | Fix |
|---|---|
| "Zero-cost" claim | Remove "zero-cost". State: "GitHub Actions-driven async batch pipeline feeding precomputed forecast grids and SHAP cache" |
| "0ms latency" claim | Remove "0ms latency". State: "Browser loads precomputed artifacts; no synchronous ML computation in the public route" |

## Slide 10: SAR / Remote Sensing (CRITICAL)

| Issue | Fix |
|---|---|
| "Cloud-penetrating, all-weather" overclaim | Add: "Dry snow transparency — C-band Sentinel-1 radar is virtually transparent to dry snow avalanches" |
| Missing terrain limitation | Add: "Steep-terrain geometrical distortion (layover/shadow) in Himalayan valleys" |
| Missing status | Add: "Currently shadow-gated (SAR_UNET_PROMOTED=false). Retrospective calibration tool, not real-time warning." |
| Missing promotion criteria | Add: "Promotion requires F1/IoU validation, wet/dry snow constraint analysis, and region-specific evaluation with scientist sign-off" |

**Evidence:** `backend/sar_unet_worker.py:376-379`, `backend/historical_sar_backfill.py:14-17`

## Slide 11: Terrain Helpers

| Issue | Fix |
|---|---|
| Terrain helpers not referenced by actual name | Use actual function names: `terrain_adjusted_risk_level` and `chebyshev_ideal_hazard_distance` |

**Evidence:** `backend/common/risk_math.py:73-94` — `chebyshev_ipa()` function

## Slide 12: Multi-Orbital SAR

| Issue | Fix |
|---|---|
| "Full multi-orbital union" overclaim | Tone down to: "Terrain-masked Sentinel-1 wet-snow detection with ascending/descending coverage tracking and historical backfill" |
| Missing physics gate | Add: "Physics gate: training eligible only when 25° ≤ slope ≤ 65°" |

## Slide 15: Explainability

| Issue | Fix |
|---|---|
| SHAP vs Gemini hierarchy unclear | State: "Main UI uses deterministic client-side SHAP narratives over precomputed TreeSHAP values. Gemini edge explainer is auxiliary and runs only when SHAP artifacts are unavailable." |
| Missing fallback badge | Add: "When SHAP artifact is unavailable, UI shows FALLBACK badge explicitly — no false claim of active TreeSHAP" |

**Evidence:** `backend/daily_inference.py:1100-1180` — SHAP context per cell; `src/lib/shapLoader.ts` — SHAP artifact loading

## New Slide: Canary Branch Story

Add a new slide (suggested after Slide 3) telling the canary branch cloud preemption story:

**Title:** "Operational Resilience: Canary Branch Preemption"

**Content:**
- When deploying the 23-feature model update, Modal cloud preempted the GPU server
- Governed CI/CD pipeline with shadow-gate discipline quarantined the failure to a shadow branch
- Live Colorado map safely fell back to loaded precomputed artifacts
- No public-facing impact — demonstrates operational resilience
- **Important:** Frame as "governed CI/CD with shadow-gate discipline" NOT "WMO-grade CI/CD pipeline"

---

## Verification Checklist

Before presenting the fixed deck:

- [ ] No slide claims "WMO-grade CI/CD" — use "governed CI/CD with shadow-gate discipline"
- [ ] No slide claims "Zero-Infrastructure" — use "Sensor-Independent Architecture"
- [ ] No slide claims "Crash-Proof Delivery" or "14.4 seconds" — use "batch artifact serving"
- [ ] No slide claims "100% uptime" or "100% remote"
- [ ] No slide claims "zero-cost" or "0ms latency"
- [ ] No slide claims "full multi-orbital union"
- [ | No slide claims "Cloud-penetrating, all-weather" for SAR without dry-snow caveat
- [ ] Slide 4 explicitly states "Weather-Driven Cumulative Heuristic Proxy"
- [ ] Slide 10 explicitly states dry-snow transparency and terrain distortion
- [ ] Slide 15 clarifies SHAP is primary, Gemini is auxiliary
- [ ] No hard-coded event counts on any slide
- [ ] Canary branch story uses "governed CI/CD" not "WMO-grade"
