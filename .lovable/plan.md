

# Avalanche Hub -- Production Finalization Plan

## Fix First: Runtime Error

The minified "r is not a function" error likely comes from a react-leaflet or recharts rendering issue. Will investigate and fix during implementation.

## Step 1: Add Secrets

Store these as edge function secrets (NOT in codebase since they're private):
- `GEMINI_API_KEY` 
- `NEWSDATA_API_KEY`
- `OPEN_METEO_BASE_URL` (public, can go in edge function code directly as a constant)

## Step 2: Database Schema Updates

**New table: `mountain_terrain`** -- pre-populated terrain proxy data for grid cells:
- id, lat, lng, elevation, slope_angle, aspect, tpi, twi, curvature
- Used by run-forecast to pull static terrain features per cell

**Alter `forecasts` table** -- add `hourly_grids` (jsonb) column to store 24 hourly grid snapshots for timeline playback from real forecast data.

**Alter `model_status` table** -- add `last_inference` (timestamptz) and `data_freshness_hours` (float) columns for enhanced badge.

Enable realtime on `forecasts` table for live updates.

## Step 3: Enhanced `run-forecast` Edge Function

Replace the pure simulation with a hybrid approach:
1. Fetch real weather from Open-Meteo API (precipitation, snowfall, wind, temperature) for bbox center
2. Pull terrain features from `mountain_terrain` table (or use computed proxies if table is empty)
3. Compute avalanche-specific features: wind-loading rate, temperature gradient, snowpack proxy
4. Run a TypeScript XGBoost-style ensemble (weighted feature scoring) that outputs danger level 1-5, problem type, probability, and SHAP values per cell
5. Generate 24 hourly grid snapshots stored in `forecasts.hourly_grids`
6. Update `model_status` with last_inference timestamp and data freshness

## Step 4: Enhanced `trigger-job` Edge Function

**Sentinel-1 integration**: When `sentinel_refresh` is triggered:
- Call ASF Vertex Search API (free, no auth needed for search) to find recent Sentinel-1 GRD scenes over current bbox
- Generate placeholder avalanche detection polygons based on scene metadata
- Insert detected events into `avalanche_events` table

**Daily enrichment**: Uses existing GEMINI_API_KEY and NEWSDATA_API_KEY secrets (already wired).

## Step 5: Frontend Enhancements

### New Components
- **`RegionSelector.tsx`** -- Dropdown with presets (Himalayas, Alps, Rockies, Andes, Cascades, Scandinavia) + current bbox display. Changing region updates DEFAULT_BBOX and re-runs forecast.
- **`DisclaimerBanner.tsx`** -- Fixed top banner: "Experimental AI system -- not for life-critical decisions. Use official avalanche centers where available."
- **`ShareForecast.tsx`** -- Button that copies a public forecast link (using forecast ID + public RLS read policy already in place)

### Modified Components
- **`Index.tsx`** -- Add region selector in top controls, disclaimer banner, share button. Load hourly forecast data from Supabase when available, fall back to client simulation. Pass hourly data to TimeSlider/Map for real-data playback.
- **`AvalancheMap.tsx`** -- Mobile touch improvements, responsive sizing
- **`TimeSlider.tsx`** -- Touch-friendly controls, larger hit targets on mobile
- **`ModelStatusBadge.tsx`** -- Show "Model v0.3 | Last inference: 5m ago | Data freshness: 2h"
- **`AdminDashboard.tsx`** -- Add loading spinners per button, success/error toasts with details
- **`RiskDashboard.tsx`** -- Show real vs simulated data indicator

### Layout Changes
- Sidebar collapses fully on mobile (< 768px), accessible via hamburger menu
- Timeline scrubber gets larger touch targets
- Map controls repositioned for mobile

## Step 6: Populate Terrain Data

Insert seed terrain data for the default Colorado Rockies bbox into `mountain_terrain` using computed elevation/slope proxies (since we can't fetch real DEM data in a migration). The run-forecast function will use these values.

## Implementation Order

1. Add secrets (GEMINI_API_KEY, NEWSDATA_API_KEY)
2. Database migration (mountain_terrain table, forecasts + model_status alterations)
3. Seed terrain data
4. Rewrite `run-forecast` with Open-Meteo + ML ensemble
5. Update `trigger-job` with ASF Sentinel-1 search
6. Build RegionSelector, DisclaimerBanner, ShareForecast components
7. Update Index.tsx with new layout, real data loading, mobile responsiveness
8. Update ModelStatusBadge, AdminDashboard with enhanced displays
9. Fix runtime error
10. Deploy and test all edge functions

## Technical Notes

- Open-Meteo is free, no API key needed -- just HTTP GET
- ASF Vertex search API is free for scene discovery (no download needed for metadata)
- The ML "model" is a weighted feature ensemble in TypeScript -- no ONNX runtime needed (Deno edge functions don't support ONNX natively)
- Timeline playback switches between real hourly forecast data (when available) and client-side simulation (fallback)
- All existing functionality preserved: field reports, Gemini enrichment, realtime subscriptions

