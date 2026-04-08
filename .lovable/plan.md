

# Avalanche Hub -- Full Migration Plan

## Overview

Migrate a Firebase/Express avalanche risk prediction app to Lovable's React + Supabase stack. The original has: a Leaflet map with 20x20 risk grid, timeline playback, field reports, admin dashboard with job controls, daily NewsData.io enrichment via Gemini, and simulated XGBoost/LSTM inference. All server-side logic (Express + node-cron) moves to Supabase Edge Functions.

## Architecture

```text
ORIGINAL                          LOVABLE TARGET
---------                         --------------
Express server.ts                 Supabase Edge Functions
Firebase Firestore                Supabase Postgres (PostGIS)
Firebase Auth                     Supabase Auth (Google OAuth)
Firebase Storage                  Supabase Storage
node-cron (daily/weekly)          pg_cron or scheduled Edge Functions
Firestore onSnapshot              Supabase Realtime subscriptions
computeService.ts                 Edge Function: run-forecast
geminiService.ts                  Edge Function: gemini-extract
```

## Step 1: Enable Lovable Cloud + Database Schema

Create Supabase tables via migration:

- **avalanche_events** -- id, timestamp, location (PostGIS geography Point), source, description, severity (1-5), type (enum), features (jsonb), confidence, fusion_source, created_at
- **forecasts** -- id, job_id, timestamp, bbox (float8[4]), risk_score, hazard, exposure, vulnerability, problem_type, shap_values (jsonb), grid_data (jsonb), created_at
- **field_reports** -- id, user_id (FK auth.users), timestamp, location (geography Point), image_url, description, status (enum), created_at
- **compute_jobs** -- id, type (enum), status (enum), bbox (float8[4]), time_offset int, payload (jsonb), result (jsonb), error text, created_at, updated_at
- **system_config** -- id, gemini_usage int, gemini_spend_cap int, last_enrichment timestamptz
- **model_status** -- id, version text, last_trained timestamptz, f1_score float, next_run timestamptz
- **non_event_baselines** -- id, timestamp, location (geography Point), features (jsonb), created_at

Enable PostGIS extension. Add RLS policies: public read on events/forecasts, authenticated write on field_reports, service-role only on compute_jobs/system_config/model_status.

## Step 2: Build the Frontend (Single-Page App)

Recreate all components in the existing Lovable project, replacing Firebase imports with Supabase client:

**src/pages/Index.tsx** -- Main app layout with:
- Sidebar with tabs (Dashboard / Admin), auth buttons, model status badge
- Full-screen Leaflet map (react-leaflet) with 20x20 colored risk grid rectangles
- Floating action buttons: RUN 24H FORECAST, REPORT AVALANCHE
- Risk legend overlay (1-5 scale with colors)
- Field report modal
- Timeline scrubber at bottom

**Components to create:**
- `AvalancheMap.tsx` -- Leaflet MapContainer, TileLayer (CartoDB dark), Rectangle grid tiles colored by risk score, event markers, click-to-select-region
- `RiskDashboard.tsx` -- Risk score display, SHAP values bar chart (recharts), hazard/exposure/vulnerability gauges, JSON export button
- `TimeSlider.tsx` -- Playback controls (play/pause/reset), range slider 0-24h
- `FieldReportForm.tsx` -- GPS auto-detect with manual fallback, image upload to Supabase Storage, description textarea, submit via edge function
- `AdminDashboard.tsx` -- 4 trigger buttons (Run Enrichment, Refresh Sentinel-1, Fine-Tune Model, Static Pre-Compute), job history table with real-time status, system config cards (Gemini usage, spend cap), model status
- `ModelStatusBadge.tsx` -- Real-time badge showing model version and F1 score

**Realtime subscriptions** replace Firestore onSnapshot:
- Subscribe to `compute_jobs` for job status updates
- Subscribe to `avalanche_events` for new events
- Subscribe to `forecasts` for forecast results

## Step 3: Supabase Edge Functions

### `run-forecast`
Replaces `/api/forecast`. Accepts `{bbox, time}`, creates a compute_job row, runs the simulated inference (20x20 grid generation with storm physics), stores forecast, updates job status. Returns job ID.

### `submit-field-report`
Replaces `/api/field-report`. Validates auth, inserts field_report, creates compute_job for enrichment, triggers Gemini extraction.

### `daily-enrichment`
Replaces the midnight cron job. Fetches from NewsData.io API, passes articles through Gemini extraction, inserts avalanche_events with confidence scoring and Sentinel-1 fusion flag. Updates system_config usage stats. Invocable manually from admin panel.

### `trigger-job`
Generic admin endpoint for: `sentinel_refresh`, `fine_tune`, `static_precompute`, `daily_enrichment`. Each runs the simulated logic from computeService.ts and updates job/model status.

### `gemini-extract`
Shared extraction logic using Gemini API (via `GEMINI_API_KEY` secret). Structured JSON output for avalanche event extraction.

## Step 4: Secrets Setup

Request user to add:
- `GEMINI_API_KEY` -- Google AI Studio API key
- `NEWSDATA_API_KEY` -- NewsData.io API key

## Step 5: Styling -- Google Flood Hub Aesthetic

- Dark theme (slate-900/zinc-900 backgrounds) with red/amber/green risk colors
- CartoDB dark_all tile layer for the map
- Glass-morphism panels with backdrop-blur
- Monospace data readouts, smooth animations via framer-motion
- Responsive: sidebar collapses to bottom sheet on mobile
- Sonner toasts for all job status updates

## Step 6: Dependencies to Add

- `leaflet`, `react-leaflet`, `@types/leaflet` -- Map
- `recharts` -- Charts in dashboard
- `framer-motion` -- Animations

## Implementation Order

1. Database migration + enable PostGIS
2. Types and Supabase client setup
3. Core UI: Map + TimeSlider + RiskDashboard + layout
4. Edge Functions: run-forecast, trigger-job
5. Admin Dashboard + realtime subscriptions
6. Field Report form + edge function
7. Daily enrichment edge function (Gemini + NewsData.io)
8. Styling polish to match Flood Hub aesthetic
9. Secrets setup for API keys

## Technical Notes

- The inference is simulated (no real ONNX model) -- kept as-is from original
- Sentinel-1 refresh is a placeholder -- kept as simulated
- PostGIS enables future real spatial queries (ST_DWithin, etc.)
- All Firebase imports completely removed; no firebase dependency
- The 20x20 grid generation logic from computeService.ts moves server-side into the run-forecast edge function

