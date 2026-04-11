# Avalanche Insight Hub (Avalanche Compass)

**Open-source AI avalanche early-warning system inspired by Google Flood Hub.**

**Live:** https://avalanche-compass.lovable.app/

**Status:** Production Ready (v1.0)

Avalanche Insight Hub delivers 24-hour-ahead, region-aware avalanche risk forecasts using real weather + terrain ensemble inference. The self-improving Groundsource loop (field reports → Gemini enrichment → daily pg_cron) continuously enhances the dataset. Works globally, including data-sparse regions like the Himalayas and Andes.

**Safety First:** Permanent disclaimer on every screen. Use only as an additional tool alongside official bulletins and local knowledge.

## Key Features

- **24h Region-Aware Forecasts** — 1–5 EAWS scale + problem type for 8 mountain ranges
- **Real Open-Meteo Weather** — Live snowfall, wind, temperature for *all* regions (not just US)
- **SHAP Explainability** — Feature importance for every grid cell
- **Self-Improving Groundsource Loop** — Field reports → realtime Events layer → daily Gemini enrichment
- **Full-State Share Links** — Share exact region/hour/cell/grid with rescuers/guides
- **Export CSV/JSON** — Download forecast + events for offline analysis
- **Mobile-Responsive** — Full functionality on phones and tablets

**Tech Stack:** React + TypeScript + Supabase (PostGIS, Edge Functions, realtime, pg_cron) + Open-Meteo + Gemini

## Quick Start (Lovable Cloud)

The app is already deployed at [avalanche-compass.lovable.app](https://avalanche-compass.lovable.app/).

To activate daily enrichment (self-improving loop):
1. Go to your Supabase dashboard → SQL Editor
2. Run the migration: `supabase/migrations/20260411193000_schedule_daily_enrichment.sql`
3. Verify: `SELECT * FROM cron.job;`

## Prerequisites (Local Development)

- Node.js 20+
- Supabase CLI
- Docker running locally if you want the full local Supabase stack

## Local Development

### Option 1: Full local Supabase replica

Use this when you want the closest match to production and the ability to work offline.

1. Copy the example env file:

   ```bash
   cp .env.local.example .env.local
   ```

2. Install dependencies:

   ```bash
   npm install
   ```

3. Start Supabase locally:

   ```bash
   supabase start
   ```

4. If you need to serve Edge Functions locally, run:

   ```bash
   supabase functions serve --env-file .env.local
   ```

5. Start the Vite dev server:

   ```bash
   npm run dev
   ```

### Option 2: Cloud-linked development

Use this if you want to edit in Windsurf immediately and point the app at the hosted Supabase project.

1. Copy the example env file:

   ```bash
   cp .env.local.example .env.local
   ```

2. Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` to the hosted project values.

3. Install dependencies:

   ```bash
   npm install
   ```

4. Start the dev server:

   ```bash
   npm run dev
   ```

## Supabase Layout

- `supabase/config.toml` - local Supabase configuration
- `supabase/migrations/` - schema and policy migrations
- `supabase/functions/` - Edge Functions

## Notes

- The browser client now fails fast with a clear error if the required `VITE_SUPABASE_*` env vars are missing.
- Field report submissions now validate coordinates before writing GeoJSON/WKT-compatible geometry values.

## QA Checklist

Use this after starting the app with `npm run dev`.

### Supabase / Data

- Open `supabase/verify_schema.sql` in the Supabase SQL Editor and confirm:
  - `postgis` and `pgcrypto` are installed
  - the expected enums exist
  - the seven public tables exist
  - RLS is enabled on all public tables
  - the expected policies are present
  - `system_config` and `model_status` each have at least one row

- Trigger a forecast from the UI and confirm:
  - the run button enters a loading state
  - a row appears in `compute_jobs`
  - a row appears in `forecasts`
  - the map updates to show hourly data if the Edge Function succeeds

- Open the Admin tab and confirm:
  - recent jobs load
  - the model status badge shows a version and F1 score
  - the Gemini usage card renders

- Open the Report dialog and confirm:
  - latitude and longitude auto-fill when geolocation is allowed
  - invalid coordinates are rejected before submit
  - a successful submit creates a row in `field_reports`

### UI / Runtime

- Confirm the page loads without a blank screen.
- Confirm the sidebar can collapse and reopen.
- Confirm the region selector changes the map bounds.
- Confirm the time slider changes the active hourly view.
- Confirm the realtime-driven admin job list refreshes without console errors.
- Confirm `npm run dev` on your machine keeps the app reachable at `http://localhost:8080/`.

### What Good Looks Like

- No red console errors on initial load.
- Forecast actions work whether the data source is real weather or simulation fallback.
- Supabase queries respect RLS:
  - public tables are readable
  - `field_reports` is restricted to the logged-in user
  - service-role-only actions stay behind Edge Functions
