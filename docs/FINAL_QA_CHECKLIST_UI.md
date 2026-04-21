# Final QA Checklist — UI Verification

Use this checklist to verify the 5.0/5.0 deployment from the browser. Each item maps to code changes we just shipped.

---

## 1. Dashboard & Risk Display

- [ ] **Load the app** (`/`)
  - Select any region (e.g., "Colorado Rockies")
  - Confirm the **RiskDashboard** renders without console errors
  - Verify risk level badge shows 1–5 with color coding

- [ ] **Select a grid cell**
  - Click any map cell
  - Confirm sidebar opens with **probability**, **terrain_risk_score**, and **chebyshev_hazard_distance** visible
  - Verify `terrain_adjusted_probability` reflects the non-compensatory fusion (should not be a simple average)

- [ ] **Cross-check Chebyshev math**
  - Pick a flat cell (low slope angle, e.g., <10°) with high weather risk (>0.7 probability)
  - Confirm the final `risk_score` is elevated (≥3) despite flat terrain — this proves the IPA fusion is active

---

## 2. Admin Tab & Job Triggers

- [ ] **Open Admin tab**
  - Click "Admin" in the sidebar tabs
  - Confirm **AdminDashboard** loads without crashing

- [ ] **Trigger a job**
  - Click "Refresh Sentinel" or similar job trigger
  - Verify:
    - Toast notification appears
    - Job appears in status list with "queued" → "running" → "completed"
  - This validates the `label-forecast-outcomes` edge function path (now hardened against statement timeouts)

---

## 3. 3D Modal & Voxel View

- [ ] **Open 3D modal**
  - Click "3D" button or set URL param `?3d=1`
  - Confirm **VoxelNeighborhoodModal** opens

- [ ] **Verify terrain extrusion**
  - Look for voxel columns rising from the base plane — ground cells should extrude into low terrain columns
  - Buildings/lifts/roads should appear above the terrain surface
  - If OSM data is sparse, you should still see volumetric terrain (not a flat plane)

- [ ] **Close and reopen**
  - Close modal, reopen — should load consistently without deadlock

---

## 4. Forecast Grid Hydration

- [ ] **Run a forecast**
  - Click "RUN 24H" or "RUN 72H"
  - Wait for completion toast

- [ ] **Verify grid persistence**
  - Refresh the page
  - Confirm the same forecast rehydrates from `forecast_grids` table (check `id` in URL or sidebar)
  - Verify `model_metadata` in the grid includes:
    - `calibration_profile`
    - `selected_features`
    - `resampling` info

- [ ] **SHAP cache read**
  - Select a cell
  - Confirm SHAP explanation loads instantly (no 3s+ delay)
  - This validates `forecast_shap_cache` is being read

---

## 5. URL State & Share

- [ ] **Expert mode via URL**
  - Visit `/?region=Colorado%20Rockies&expert=1`
  - Confirm expert panel auto-opens
  - Verify overlays (heatmap, roads, infra) can be toggled

- [ ] **Share forecast**
  - Click "Share" button
  - Copy link, open in incognito window
  - Confirm shared forecast restores:
    - Correct region
    - Correct hour
    - Selected cell (if `&cell=row,col` present)

---

## 6. Real-time & Events

- [ ] **Historical events toggle**
  - Turn on "Show Historical Events"
  - Confirm heatmap renders
  - Click an event marker — should show popup with severity, confidence, description

- [ ] **Field report submission**
  - Open "Report" form
  - Submit a test field report (use low severity, mark as test)
  - Confirm:
    - Toast confirmation
    - Event appears on map within seconds (realtime subscription)
    - Event has `features.location_name` populated

---

## 7. Mobile Responsiveness (Quick Check)

- [ ] **Mobile viewport**
  - DevTools → iPhone SE (375×667)
  - Confirm:
    - Sidebar collapses to hamburger menu
    - Map remains interactive
    - Risk cards stack vertically
    - No horizontal scroll

---

## Sign-Off Criteria

| Component | Pass Criteria |
|-----------|---------------|
| Dashboard | Risk displays with terrain-adjusted fusion |
| Admin | Jobs trigger and complete without timeout |
| 3D Modal | Terrain voxels visible, no deadlock on reopen |
| Forecast | Persists, rehydrates, SHAP loads fast |
| URL/Share | Deep links restore state |
| Events | Realtime updates, field reports ingest |
| Mobile | Layout adapts, no overflow |

**If all boxes checked → 5.0/5.0 verified.**
