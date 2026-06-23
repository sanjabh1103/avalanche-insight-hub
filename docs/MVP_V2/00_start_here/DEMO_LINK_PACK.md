# Demo Link Pack - Top 15 Feature Walkthrough

Status: 2026-06-21
Purpose: Prepared shareable URLs for scientist-facing demo of the Avalanche Insight Hub prototype
Boundary: All links point to the hosted prototype for decision-support demonstration, not official warnings

## Base URL

```
https://avalanche-insight-hub.netlify.app
```

## Demo Links by Feature

### 1. Public Forecast Workspace (Feature #1)
**Link:** `https://avalanche-insight-hub.netlify.app/`
**What to show:** Default public route loads the forecast workspace with map, bulletin, time controls, and cell inspection.

### 2. Published Batch Forecast Artifacts (Feature #2)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1`
**What to show:** The app loads precomputed artifacts from storage, not browser-side computation. The data badge shows "PRECOMPUTED BATCH".

### 3. 20x20 Grid and 72-Hour Review (Feature #3)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&hour=0`
**What to show:** Grid metadata chip shows grid size (20x20) and loaded/total hours (e.g., "1/24h loaded"). Use the time slider to load later hours on demand.

### 4. EAWS-Style Experimental Bulletin (Feature #4)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1`
**What to show:** Bulletin badge shows danger level, avalanche problem, critical elevation/aspect, and peak window. Note the "experimental" framing.

### 5. Interactive Map and Time Slider (Feature #5)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&hour=6`
**What to show:** Click daypart chips (morning/afternoon/evening) or drag the time slider to see grid state changes across forecast hours.

### 6. Cell-Level Risk Inspection (Feature #6)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&cell=0,0`
**What to show:** Click any grid cell to see risk level, probability, hazard, exposure, vulnerability, problem type, and model version context.

### 7. Terrain and Snow/Public Eligibility Masking (Feature #7)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&cell=0,0`
**What to show:** Masked cells show "MASKED" or "UNAVAILABLE" labels instead of false low-risk. Compare a masked cell vs a normal cell.

### 8. Uncertainty and Reduced-Confidence Cues (Feature #8)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1`
**What to show:** Bulletin shows confidence state (normal/reduced) and uncertainty summary. Data latency banner shows freshness status.

### 9. Weather Summary and Snowpack Proxy (Feature #9)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&cell=0,0`
**What to show:** Risk dashboard weather card shows snowfall, wind speed, temperature, precipitation, and snow depth with proper units (no duplicates).

### 10. Explainability and Risk-Driver Display (Feature #10)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&cell=0,0`
**What to show:** Risk dashboard shows TreeSHAP or fallback explainability contributions with origin badge ("TREESHAP" or "FALLBACK").

### 11. Historical Events and Field Reports (Feature #11)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1`
**What to show:** Toggle historical events in expert mode. Open field report form from the action tray.

### 12. Shareable Forecast Links (Feature #12)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&cell=0,0&hour=6&expert=1&3d=1`
**What to show:** Click SHARE button to copy a URL that preserves region, forecast hour, selected cell, expert mode, and 3D state.

### 13. CSV and JSON Forecast Export (Feature #13)
**Link:** `https://avalanche-insight-hub.netlify.app/?forecast=shared-forecast-run-1&cell=0,0`
**What to show:** Click EXPORT to download forecast cells, probabilities, uncertainty fields, and problem types as CSV or JSON.

### 14. Admin/Operator Control (Feature #14)
**Link:** `https://avalanche-insight-hub.netlify.app/admin`
**What to show:** Admin dashboard with job controls, model status, source health, evaluation metrics, and publication traces. Requires admin password.

### 15. Scientist Validation Lane (Feature #15)
**Link:** `https://avalanche-insight-hub.netlify.app/scientist`
**What to show:** Role-gated review workspace with paired scientist-vs-model comparison, verdicts, notes, and exportable evidence.

## Himalayan Demo Links

The Himalayan (Nepal) region is fully operational with a published 72-hour forecast artifact.

**Active run ID:** `e6cac8c5-1cc8-4054-b99f-bf2e63dfc90a`
**Forecast date:** 2026-06-21
**Status:** ready / published
**Grid:** 20×20 (400 cells, all ready)
**Danger level:** 3 (Considerable) — wet snow problem

### Himalayan Region Links

**Default view:**
`https://avalanche-insight-hub.netlify.app/?region=Himalayas%20(Nepal)`

**With forecast artifact loaded:**
`https://avalanche-insight-hub.netlify.app/?region=Himalayas%20(Nepal)&forecast=e6cac8c5-1cc8-4054-b99f-bf2e63dfc90a`

**12-hour forecast:**
`https://avalanche-insight-hub.netlify.app/?region=Himalayas%20(Nepal)&forecast=e6cac8c5-1cc8-4054-b99f-bf2e63dfc90a&hour=12`

**36-hour forecast with cell selected:**
`https://avalanche-insight-hub.netlify.app/?region=Himalayas%20(Nepal)&forecast=e6cac8c5-1cc8-4054-b99f-bf2e63dfc90a&hour=36&cell=28.0,86.25`

**Expert mode with 3D voxel view:**
`https://avalanche-insight-hub.netlify.app/?region=Himalayas%20(Nepal)&forecast=e6cac8c5-1cc8-4054-b99f-bf2e63dfc90a&expert=1&3d=1`

### Himalayan Claim Boundaries

- `himalayan_accuracy_claim_allowed` is set to `false` — no validated accuracy claims are made for this region
- SAR coverage badge shows "UNAVAILABLE" — shadow-gated globally (`sar_shadow_only: true`)
- Snowpack proxy uses `seasonal_cumulative_v1` (regional mode) — not a physics-based snowpack model
- The forecast demonstrates pipeline capability and decision-support visualization, not operational forecasting for Nepal

## Demo Flow Recommendation

1. Start with link #1 (public workspace) to establish context
2. Use link #4 (bulletin) to show the experimental EAWS-style summary
3. Use link #6 (cell inspection) to dive into risk decomposition
4. Use link #10 (explainability) to show TreeSHAP/fallback distinction
5. Use link #3 (grid/horizon) to show lazy-loading and honest metadata
6. Switch to Himalayan region to show multi-region capability and wet snow problem
7. Use link #12 (shareable link) to demonstrate state preservation
8. End with link #14/#15 (admin/scientist) for workflow discussion

## Claim Boundaries

- All demo links show a **hosted decision-support prototype**, not an official warning service
- Colorado proof geography does not prove Himalayan operational accuracy
- TreeSHAP explainability is artifact-dependent; fallback mode is shown honestly
- Grid display is review evidence, not slope-specific safety advice
- Shared links prove review context, not scientific acceptance
