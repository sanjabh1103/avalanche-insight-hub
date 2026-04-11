# Avalanche Insight Hub — PRD Acceptance Test Sheet

**Version:** 1.0  
**Date:** 2026-04-11  
**Status:** Production Ready  
**Live URL:** https://avalanche-compass.lovable.app/

---

## How to Use This Document

1. Run each test in order (Story 1 → 15)
2. Mark **PASS** or **FAIL** with timestamp
3. If FAIL, file bug with story number reference
4. All 15 must PASS for v1.0 certification

---

## Pre-Test Setup

```bash
# Database verification (run in Supabase SQL Editor)
\i supabase/verify_schema.sql
SELECT conname FROM pg_constraint WHERE conname = 'field_reports_location_valid_range';
SELECT jobid, schedule, jobname, active FROM cron.job WHERE jobname = 'daily-enrichment-job';

# Confirm Edge Functions deployed
supabase functions list
# Expected: run-forecast, trigger-job
```

---

## Story-by-Story Acceptance Tests

### Story #1: Region Selection (Preset or BBox)
**PRD AC:** 9+ presets, map flies to center/zoom, forecast button triggers real Open-Meteo + ensemble inference.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 1.1 | Click Region dropdown | Shows: Colorado Rockies, Swiss Alps, Himalayas, Andes, Japanese Alps, Southern Alps NZ, Scottish Highlands, Pyrenees | ⬜ PASS / ⬜ FAIL | |
| 1.2 | Select "Himalayas" | Map animates to center [28.6, 83.8], zoom 9 | ⬜ PASS / ⬜ FAIL | |
| 1.3 | Click "RUN 24H FORECAST" | Button shows loader, toast "Running 24h forecast with real weather data..." | ⬜ PASS / ⬜ FAIL | |
| 1.4 | Wait 5-15s | Grid appears, toast "Forecast complete • Source: open-meteo" | ⬜ PASS / ⬜ FAIL | |

**Story #1 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 1.1-1.4)

---

### Story #2: 20×20 Risk Grid Display
**PRD AC:** EAWS 1–5 colors + problem type, visible on zoom, cells clickable.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 2.1 | Observe grid after forecast | 20×20 colored rectangles overlay map | ⬜ PASS / ⬜ FAIL | |
| 2.2 | Check color range | Colors from green (1) to red/black (5) visible | ⬜ PASS / ⬜ FAIL | |
| 2.3 | Zoom in/out | Grid rectangles scale with map, remain aligned | ⬜ PASS / ⬜ FAIL | |
| 2.4 | Click any grid cell | Sidebar opens with RiskDashboard showing cell details | ⬜ PASS / ⬜ FAIL | |

**Story #2 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 2.1-2.4)

---

### Story #3: 24h Timeline Playback
**PRD AC:** Colors + SHAP update live from hourly_grids, works on mobile touch.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 3.1 | Drag timeline slider | Grid colors change as hour changes (0→24) | ⬜ PASS / ⬜ FAIL | |
| 3.2 | Click play button | Slider auto-advances, grid updates each hour | ⬜ PASS / ⬜ FAIL | |
| 3.3 | Pause at hour 12 | Grid frozen at h12 state, SHAP panel updates | ⬜ PASS / ⬜ FAIL | |
| 3.4 | Mobile: touch-drag slider | Same behavior as desktop | ⬜ PASS / ⬜ FAIL | |

**Story #3 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 3.1-3.4)

---

### Story #4: SHAP Explainability
**PRD AC:** Bar chart shows top features, real Open-Meteo values globally.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 4.1 | Click any cell | RiskDashboard shows SHAP Feature Importance section | ⬜ PASS / ⬜ FAIL | |
| 4.2 | Check SHAP bars | 5-7 colored bars with feature names (slope, new_snow_24h, wind_drift, etc.) | ⬜ PASS / ⬜ FAIL | |
| 4.3 | Verify "Live Weather (Open-Meteo)" | Green panel shows: snowfall_24h, wind_speed, temperature, precipitation | ⬜ PASS / ⬜ FAIL | |
| 4.4 | Test Himalayas/Andes (non-US) | Same real weather values appear (not zeros/simulated) | ⬜ PASS / ⬜ FAIL | |

**Story #4 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 4.1-4.4)

---

### Story #5: Field Report Submission
**PRD AC:** Modal opens, Gemini classifies, PostGIS dedup, marker appears in seconds.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 5.1 | Click "FIELD REPORT" | Modal opens with description, lat, lng fields | ⬜ PASS / ⬜ FAIL | |
| 5.2 | Enter invalid lat (95) | Toast error: "Invalid latitude. Must be between -90 and 90." | ⬜ PASS / ⬜ FAIL | |
| 5.3 | Enter valid data, submit | Toast success: "Field report submitted" | ⬜ PASS / ⬜ FAIL | |
| 5.4 | Check Supabase | New row in `field_reports` table with AI classification | ⬜ PASS / ⬜ FAIL | |

**Story #5 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 5.1-5.4)

---

### Story #6: Historical Events Layer
**PRD AC:** Confidence-colored CircleMarkers with popups.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 6.1 | Click "SHOW EVENTS" | Button shows loader, then events appear as circles | ⬜ PASS / ⬜ FAIL | |
| 6.2 | Observe markers | Colors match confidence (green=high, red=low) | ⬜ PASS / ⬜ FAIL | |
| 6.3 | Click a marker | Popup shows: location, date, danger, summary | ⬜ PASS / ⬜ FAIL | |
| 6.4 | Click "HIDE EVENTS" | All markers removed from map | ⬜ PASS / ⬜ FAIL | |

**Story #6 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 6.1-6.4)

---

### Story #7: Admin Job Triggers
**PRD AC:** Toasts, ACTIVE JOBS counter, Recent Jobs log with realtime updates.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 7.1 | Open sidebar → Admin tab | Panel shows with ACTIVE JOBS, Recent Jobs, Model Status | ⬜ PASS / ⬜ FAIL | |
| 7.2 | Click "Trigger Daily Enrichment" | Toast "Job triggered", new row in Recent Jobs | ⬜ PASS / ⬜ FAIL | |
| 7.3 | Watch ACTIVE JOBS | Counter increments during job, decrements on complete | ⬜ PASS / ⬜ FAIL | |
| 7.4 | Verify Recent Jobs | Shows job type, status, runtime in realtime | ⬜ PASS / ⬜ FAIL | |

**Story #7 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 7.1-7.4)

---

### Story #8: Model Status Badge
**PRD AC:** Shows version, last inference time, data freshness, F1 score.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 8.1 | Look at top-right corner | Badge visible with model info | ⬜ PASS / ⬜ FAIL | |
| 8.2 | Hover/click badge | Shows: version, F1 score, last inference, data freshness | ⬜ PASS / ⬜ FAIL | |
| 8.3 | Run new forecast | Badge updates with new "last inference" time | ⬜ PASS / ⬜ FAIL | |

**Story #8 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 8.1-8.3)

---

### Story #9: Export CSV/JSON
**PRD AC:** Visible Export button, downloads full dataset.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 9.1 | Run forecast | Two export buttons visible: "CSV", "JSON" | ⬜ PASS / ⬜ FAIL | |
| 9.2 | Click "CSV" | File downloads: `avalanche-forecast-{region}-h{hour}.csv` | ⬜ PASS / ⬜ FAIL | |
| 9.3 | Open CSV | Contains: row, col, lat, lng, riskScore, hazard, exposure, vulnerability, shapValues | ⬜ PASS / ⬜ FAIL | |
| 9.4 | Click "JSON" | File downloads with metadata + grid + events | ⬜ PASS / ⬜ FAIL | |

**Story #9 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 9.1-9.4)

---

### Story #10: Full-State Share Links
**PRD AC:** URL with query params; incognito link restores identical grid + timeline.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 10.1 | Run forecast, select cell | Click "SHARE" button | ⬜ PASS / ⬜ FAIL | |
| 10.2 | Check clipboard | URL format: `?region=Himalayas&hour=12&cell=5,8&forecast=xyz` | ⬜ PASS / ⬜ FAIL | |
| 10.3 | Open in incognito | Same region, hour, selected cell, grid restored | ⬜ PASS / ⬜ FAIL | |
| 10.4 | Verify toast | "Restored shared forecast view" message | ⬜ PASS / ⬜ FAIL | |

**Story #10 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 10.1-10.4)

---

### Story #11: Global Coverage (Sparse Regions)
**PRD AC:** Real Open-Meteo weather for all regions (Nepal/Andes/etc.).

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 11.1 | Select "Andes" | Map flies to South America | ⬜ PASS / ⬜ FAIL | |
| 11.2 | Run forecast | Toast shows "Source: open-meteo" | ⬜ PASS / ⬜ FAIL | |
| 11.3 | Check SHAP panel | Real values: snowfall_24h > 0, wind_speed realistic | ⬜ PASS / ⬜ FAIL | |
| 11.4 | Repeat for Himalayas | Same real weather values (not simulated) | ⬜ PASS / ⬜ FAIL | |

**Story #11 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 11.1-11.4)

---

### Story #12: Mobile Responsive
**PRD AC:** Hamburger menu, large touch targets, SHAP accessible, timeline touch.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 12.1 | Resize to mobile (375px) | Layout adapts, hamburger menu appears | ⬜ PASS / ⬜ FAIL | |
| 12.2 | Click hamburger | Sidebar opens with full functionality | ⬜ PASS / ⬜ FAIL | |
| 12.3 | Touch timeline | Drag works, play/pause buttons large enough | ⬜ PASS / ⬜ FAIL | |
| 12.4 | Click grid cell | RiskDashboard scrollable, readable | ⬜ PASS / ⬜ FAIL | |

**Story #12 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 12.1-12.4)

---

### Story #13: Safety Disclaimer
**PRD AC:** Red banner always visible, non-dismissible, references EAWS.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 13.1 | Load any page | Red disclaimer banner at top | ⬜ PASS / ⬜ FAIL | |
| 13.2 | Try to dismiss | No X button, cannot be closed | ⬜ PASS / ⬜ FAIL | |
| 13.3 | Read text | Contains: "experimental", "not for life-critical decisions", "EAWS" reference | ⬜ PASS / ⬜ FAIL | |
| 13.4 | Navigate tabs | Banner persists across Dashboard/Admin views | ⬜ PASS / ⬜ FAIL | |

**Story #13 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 13.1-13.4)

---

### Story #14: pg_cron Daily Enrichment
**PRD AC:** Midnight UTC job runs Gemini + NewsData.io → new events added.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 14.1 | SQL: `SELECT * FROM cron.job` | `daily-enrichment-job` exists, active=true, schedule=`0 0 * * *` | ⬜ PASS / ⬜ FAIL | |
| 14.2 | Check `compute_jobs` table | Historical entries with type="enrichment" | ⬜ PASS / ⬜ FAIL | |
| 14.3 | Manual trigger via Admin | Job starts, completes, new events may appear | ⬜ PASS / ⬜ FAIL | |
| 14.4 | Verify NewsData.io integration | Check `system_config` for API key and usage | ⬜ PASS / ⬜ FAIL | |

**Story #14 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 14.1-14.4)

---

### Story #15: Realtime Job Status & Analytics
**PRD AC:** Admin panel shows forecast analytics, Gemini usage, compute_jobs realtime.

| Step | Action | Expected Result | Status | Time |
|------|--------|-----------------|--------|------|
| 15.1 | Run 2-3 forecasts | Check `forecast_analytics` table has entries | ⬜ PASS / ⬜ FAIL | |
| 15.2 | Admin panel → check analytics | Shows: region_name, weather_source, avg_risk, cell_count | ⬜ PASS / ⬜ FAIL | |
| 15.3 | Check `system_config` | Gemini usage stats tracked | ⬜ PASS / ⬜ FAIL | |
| 15.4 | Trigger multiple jobs | Recent Jobs list updates without refresh (realtime) | ⬜ PASS / ⬜ FAIL | |

**Story #15 Status:** ⬜ **PASS** / ⬜ **FAIL** (requires all 15.1-15.4)

---

## Non-Functional Requirements Checklist

| Requirement | Test | Status |
|-------------|------|--------|
| Performance | Forecast completes in <15s | ⬜ PASS / ⬜ FAIL |
| Reliability | Graceful fallback if edge function fails | ⬜ PASS / ⬜ FAIL |
| Security | RLS policies active (verify via SQL) | ⬜ PASS / ⬜ FAIL |
| Accessibility | High-contrast danger colors visible | ⬜ PASS / ⬜ FAIL |
| Scalability | Concurrent users don't crash edge functions | ⬜ PASS / ⬜ FAIL |
| Explainability | Every cell shows SHAP values | ⬜ PASS / ⬜ FAIL |

---

## Final Certification

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Stories Passed | 15/15 | __/15 | ⬜ |
| Non-Functional Passed | 6/6 | __/6 | ⬜ |
| Console Errors | 0 | __ | ⬜ |
| Mobile Usable | Yes | ⬜ Yes / ⬜ No | ⬜ |

**Overall v1.0 Status:** ⬜ **CERTIFIED** / ⬜ **NOT CERTIFIED**

**Tested By:** _________________  **Date:** _________________  
**Signature:** _________________

---

## Quick Reference: Database Verification Queries

```sql
-- 1. Schema verification
\i supabase/verify_schema.sql

-- 2. Coordinate constraint
SELECT conname FROM pg_constraint WHERE conname = 'field_reports_location_valid_range';

-- 3. Cron job status
SELECT jobid, schedule, jobname, active FROM cron.job WHERE jobname = 'daily-enrichment-job';

-- 4. RLS status
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true;

-- 5. Recent forecasts
SELECT id, created_at, region_name, weather_source, avg_risk 
FROM forecast_analytics ORDER BY created_at DESC LIMIT 5;

-- 6. Field reports count
SELECT COUNT(*) FROM field_reports;

-- 7. Model status
SELECT * FROM model_status;
```

---

## Bug Reporting Template

```
Story: #__
Test Step: __.__
Expected: 
Actual: 
Severity: 🔴 High / 🟡 Medium / 🟢 Low
Screenshot: 
Console Error: 
```
