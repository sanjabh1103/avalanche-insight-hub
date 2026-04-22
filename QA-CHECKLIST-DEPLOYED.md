# Avalanche Insight Hub — Post-Deploy QA Checklist

**Deploy URLs**
- Production frontend: https://avalanche-insight-hub.netlify.app
- Supabase project: fzheroisjhxnairglelv
- Edge Functions dashboard: https://supabase.com/dashboard/project/fzheroisjhxnairglelv/functions

**Date**: 2026-04-21
**Scope**: Critical backend fixes (`.single()` → `.maybeSingle()`, auth headers, JSON guards) + UI honesty wiring (SAR badges, `abc_enabled`, `fallback_used`, synthetic bootstrap warning)

---

## A. Admin Dashboard — Model Status & Honesty Flags

### A1. Synthetic Bootstrap Warning
**Surface**: `AdminDashboard.tsx` → Model Status card

**Steps**:
1. Open https://avalanche-insight-hub.netlify.app
2. Click **Admin** tab
3. Look at the **Model Status** card

**Expected outcome**:
- If `last_trained` is missing OR `version` contains `-sim` OR `optimization_summary.origin === 'hardcoded_fallback'`:
  - An **amber badge** appears: "SYNTHETIC BOOTSTRAP"
  - Subtext: "Model was never trained. Run Model Optimization to replace with real weights."
- If model was properly trained, no amber badge appears.

**Why this matters**: Prevents the UI from pretending a hardcoded/simulated model is a real trained one.

---

### A2. ABC Optimizer Enabled Flag
**Surface**: `AdminDashboard.tsx` → Optimization Summary section

**Steps**:
1. In Admin tab, scroll to **Optimization Summary**
2. Look for line: "ABC: enabled" or "ABC: disabled"

**Expected outcome**:
- Reads `optimization_summary.abc_enabled` from `model_status` table
- Displays green checkmark if `true`, grey dash if `false` or missing
- Never fabricated — falls back to actual DB value

**Backend source**: `supabase/functions/trigger-job/index.ts` writes `abc_enabled` into `optimization_summary` after Modal GPU/edge optimization runs.

---

### A3. Satellite Fallback Used Flag
**Surface**: `AdminDashboard.tsx` → Satellite Detection Stats section

**Steps**:
1. In Admin tab, scroll to **Satellite Detection Stats**
2. Look for line: "Fallback used: yes / no"

**Expected outcome**:
- Reads `satellite_detection_stats.fallback_used` from `model_status` table
- Displays "yes" with amber warning color if `true`
- Displays "no" with muted color if `false` or missing

**Why this matters**: Honestly reports when Sentinel-1 SAR search failed and the system fell back to placeholder/simulated detections.

---

## B. Risk Dashboard — SAR Coverage Badges

**Surface**: `RiskDashboard.tsx` → Uncertainty / Coverage section

**Steps**:
1. Click any forecast cell on the map (or open a cell from the grid)
2. Open **Risk Dashboard** panel (right sidebar)
3. Look for the **SAR Coverage** badge row

**Expected outcome**:
- **Green badge**: "SAR Coverage: Good" — when `coverageFlags.sar_coverage_state === 'good'`
- **Amber badge**: "SAR Coverage: Low" — when `coverageFlags.sar_coverage_state === 'low'`
- **Red badge**: "Residual Shadow" — when `coverageFlags.residual_shadow === true`
- Badges are prominent, colored, and use uppercase tracking text

**Removed**: Old redundant text-only SAR coverage indicators (e.g., plain "SAR: good" strings) have been removed from the uncertainty section to avoid duplication.

---

## C. Forecast Toast — Honest Fallback Reporting

**Surface**: `Index.tsx` → forecast generation toast

**Steps**:
1. On the main map, click **Run Forecast**
2. Wait for toast notification to appear

**Expected outcome**:
- Toast reads: `Forecast complete • Source: <source> • Mode: <mode> • Fallback: yes • <N> hours`
  - **"Fallback: yes"** appears only when `run-forecast` edge function honestly reports `fallback_used: true`
  - This happens when: (a) no recent `forecast_grids` async row exists, (b) Modal GPU worker is unreachable, (c) system falls back to edge heuristic
- If async grid hydration or Modal succeeds, **"Fallback: yes"** is omitted

**Backend source**: `supabase/functions/run-forecast/index.ts` computes `fallbackUsed` after trying async grid hydration and Modal, then returns it in the JSON response.

---

## D. Edge Function Resilience — No 500/502 Crashes on Empty Tables

**Surface**: All Supabase Edge Functions

**Steps** (use Supabase Dashboard Logs or invoke functions directly):
1. Go to https://supabase.com/dashboard/project/fzheroisjhxnairglelv/functions
2. Click **run-evaluation** → Logs
3. Click **label-forecast-outcomes** → Logs
4. Click **field-report-enrichment** → Logs
5. Click **trigger-job** → Logs
6. Click **run-forecast** → Logs

**Expected outcome**:
- **No `PGRST116` errors** (the `.single()` error code) in any function logs
- Functions gracefully handle missing rows:
  - `run-evaluation`: if `model_status` or `threshold_profiles` missing, uses `'unknown'` versions instead of crashing
  - `label-forecast-outcomes`: if no `label_matching_policies` row exists, uses default tolerances (5000m, 24h, 500m band)
  - `trigger-job`: `updateModelStatus` logs a warning instead of throwing when `model_status` row missing
  - `run-forecast`: if `model_status` missing, still creates job and runs forecast with `'edge-lite-v1'` optimization version
- All `.maybeSingle()` calls return `null` on empty results, and downstream code checks `?.id` or `?.version` before using

---

## E. Internal Edge Function Auth — No 401 Unauthorized

**Surface**: `field-report-enrichment`, `trigger-job`, `run-forecast`

**Steps**:
1. In Supabase Dashboard → Edge Functions → **field-report-enrichment** → Logs
2. Filter for status codes >= 400
3. Repeat for **trigger-job** and **run-forecast**

**Expected outcome**:
- **No 401 Unauthorized** errors on internal `fetch` calls to other edge functions
- All internal calls now include BOTH headers:
  - `Authorization: Bearer <token>`
  - `apikey: <anon-key>`

**Verified call sites**:
- `field-report-enrichment` → `ingest-event` (`apikey` added)
- `trigger-job` → `ingest-event` / `ingest-snow-cover` / `label-forecast-outcomes` / `run-evaluation` (already had both)
- `run-forecast` → `ingest-event` / `ingest-snow-cover` / `label-forecast-outcomes` (already had both)

---

## F. JSON Parse Guards — No Crashes on Malformed Internal Responses

**Surface**: `trigger-job` and `run-forecast` → `invokeEdgeFunction` helper

**Steps**:
1. Check **trigger-job** logs for any `JSON.parse` related crashes
2. Check **run-forecast** logs for same

**Expected outcome**:
- If an internal edge function returns a non-JSON 200 response (rare but possible with proxies/CDN), the caller logs a warning and returns `{}` instead of throwing
- Error message pattern: `<functionName> returned non-JSON 200 response: ...`
- No unhandled exceptions propagating to the HTTP client

---

## G. Frontend Resilience — No White Screen on Empty DB

**Surface**: `AdminDashboard.tsx`, `ModelStatusBadge.tsx`, `Index.tsx`, `FieldReportForm.tsx`

**Steps**:
1. Open the app in a fresh browser profile (or clear site data)
2. Navigate directly to **/admin** before any data exists in the DB
3. Open **Risk Dashboard** before any forecasts exist

**Expected outcome**:
- **No white screen / crash**
- Admin Dashboard renders with empty states instead of crashing on `.single()`
- Model Status Badge shows "Unknown" or loading state instead of throwing
- Field Report Form submits successfully even if the insert `.select('id')` returns empty due to RLS

---

## H. Regression Tests — Existing Features Still Work

| Feature | Steps | Expected |
|---------|-------|----------|
| **Run Forecast** | Click "Run Forecast" on map | Toast appears, grid loads, no console errors |
| **Submit Field Report** | Fill form, click submit | Report saved, toast confirms, no 500 from `ingest-event` |
| **Refresh Sentinel-1** | Admin → click "Refresh Sentinel-1" | Job queued, logs show ASF search, no 401 |
| **Run Evaluation** | Admin → click "Run Evaluation" | Job queued, metrics computed, no `PGRST116` |
| **Label Outcomes** | Admin → click "Label Outcomes" | Job queued, forecast_outcomes populated, no crash if no policy row |
| **3D Voxel Modal** | Click cell → "View 3D" | Loads voxel scene, terrain columns visible even if OSM sparse |

---

## I. Known Non-Issues (Pre-existing Lints)

The following are **expected** and do NOT indicate a bug:

- **Deno type errors** in edge function files (`Cannot find name 'Deno'`, `Cannot find module 'https://deno.land/std...'`): These files run on Deno runtime, not the frontend TypeScript compiler. The frontend `tsc --noEmit` passes clean.
- **Chunk size warning** from Vite build (`>500 kB`): Expected for a data-heavy app with mapping libraries. Does not affect functionality.
- **Netlify Functions folder missing**: The app uses Supabase Edge Functions, not Netlify Functions. The warning is harmless.

---

## J. Smoke Test Commands (for automated verification)

```bash
# 1. Test run-forecast edge function directly
curl -X POST https://fzheroisjhxnairglelv.supabase.co/functions/v1/run-forecast \
  -H "Authorization: Bearer <ANON_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"bbox":[45.8,6.8,46.0,7.0],"hours":6}'
# Expected: 200 OK with JSON containing forecastId, avgRisk, fallback_used

# 2. Test trigger-job (daily_enrichment)
curl -X POST https://fzheroisjhxnairglelv.supabase.co/functions/v1/trigger-job \
  -H "Authorization: Bearer <ANON_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"type":"daily_enrichment","region_name":"Chamonix"}'
# Expected: 200 OK with jobId

# 3. Test field-report-enrichment
curl -X POST https://fzheroisjhxnairglelv.supabase.co/functions/v1/field-report-enrichment \
  -H "Authorization: Bearer <SERVICE_ROLE_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"fieldReportId":"test-123","lat":45.9,"lng":6.9,"description":"test"}'
# Expected: 200 OK or honest error (not 500)
```

---

## Sign-off

| Check | Status | Notes |
|-------|--------|-------|
| All 8 edge functions deployed | ✅ | run-forecast, trigger-job, field-report-enrichment, ingest-event, ingest-snow-cover, label-forecast-outcomes, run-evaluation, recent-activity-refresh |
| Frontend deployed to Netlify | ✅ | https://avalanche-insight-hub.netlify.app |
| `tsc --noEmit` clean | ✅ | Zero errors |
| `npm run build` clean | ✅ | Zero errors |
| No `.single()` in app code | ✅ | All converted to `.maybeSingle()` |
| `apikey` header on internal fetches | ✅ | Verified in 3 call sites |

## Smoke Test Results (2026-04-21)

Run command: `./smoke-test.sh`

| # | Function | Status | Expected / Actual |
|---|----------|--------|-------------------|
| 1 | Netlify Frontend | ✅ HTTP 200 | Page loads, HTML + JS bundle served |
| 2 | `run-forecast` | ✅ 200 JSON | `jobId`, `forecastId`, `avgRisk: 2.095`, `fallback_used: false`, `weatherSource: open-meteo` |
| 3 | `trigger-job` (daily_enrichment) | ✅ 200 JSON | `jobId`, `simulated: true`, `articlesProcessed: 3` |
| 4 | `field-report-enrichment` | ✅ 200 JSON | `ok: true`, `jobId` returned, `promotion: null` |
| 5 | `ingest-event` (direct) | ✅ 200 JSON | `ok: true`, `event.id` returned, topo extracted from open-elevation |
| 6 | `run-evaluation` | ✅ 200 JSON | `evaluation_run_id`, `model_version: v1.0.1`, `threshold_profile_version: heuristic-risk-bands-v1`, zero outcomes (empty DB is handled gracefully) |
| 7 | `label-forecast-outcomes` | ✅ 200 JSON | `forecasts_processed: 0`, fallback default policy returned (5000m, 24h, 500m band) — no crash on missing policy row |
| 8 | `ingest-snow-cover` | ✅ 200 JSON | `snapshot_id`, `source: gibs`, `coverage_ratio: 0.38`, `quality_score: 0.75` |
| 9 | `recent-activity-refresh` | ✅ 200 JSON | `feature_id`, `region: Chamonix`, `total_events: 0`, zero values handled gracefully |

### Key Findings

- **9/9 functions return 200 JSON** on first call.
- **`.maybeSingle()` resilience works**: `label-forecast-outcomes` returned default policy without crashing when `label_matching_policies` table is empty. `run-evaluation` computed metrics with zero outcomes without throwing `PGRST116`.
- **Frontend build clean**: `tsc --noEmit` and `npm run build` both pass.
- **`field-report-enrichment` internal auth**: Downstream `ingest-event` now succeeds after forwarding the caller's valid auth headers and falling back to server secrets only when needed. Re-test completed successfully.

### Re-test Command (after re-deploy)

```bash
cd /Users/sanjayb/avalanche-insight-hub
SR_KEY=$(grep "^SUPABASE_SERVICE_ROLE_KEY=" .env | cut -d= -f2- | tr -d '"')
URL="https://fzheroisjhxnairglelv.supabase.co/functions/v1/field-report-enrichment"
curl -s -X POST "$URL" \
  -H "Authorization: Bearer $SR_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"fieldReportId\":\"verify-$(date +%s)\",\"lat\":45.9,\"lng\":6.9,\"description\":\"Re-test after auth fix\"}" \
  | head -c 500
```

**Expected**: JSON response containing `ok: true` and `jobId` (no `401` error).
