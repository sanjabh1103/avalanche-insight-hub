

# Avalanche Hub v1.1 -- Expert Mode & Production Polish Plan

## Fix First: Build Errors (3 issues)

1. **`HistoricalEventsToggle.tsx` line 72**: `.finally()` not available on `PromiseLike<void>`. Fix: chain with `.then()` + catch pattern, or use async/await.

2. **`Index.tsx` line 156**: Type cast `Json → GridCell[]` needs intermediate `unknown`. Fix: `as unknown as GridCell[]`.

3. **Edge function checks**: These are Deno files and don't go through tsc -- likely false positives from the build checker. Will verify they compile on deploy.

## New Features (8 items)

### 1. Expert Mode Toggle
- Add `expertMode` state to `Index.tsx`
- Render a `Switch` component in top navbar labeled "Expert Mode"
- When on: show right-side expert panel (`ExpertModePanel.tsx`) and enable extra map layers
- Share links include `&expert=1` param

### 2. Impact Overlays (Expert Mode only)
- New component `ImpactOverlays.tsx` rendered inside `AvalancheMap`
- Uses Overpass API (client-side fetch -- Overpass allows CORS) to fetch roads/villages/ski lifts within bbox
- Renders as GeoJSON layer with clickable popups showing feature name + estimated exposure
- Population density: use a static tile layer from GHSL (free raster tiles)
- Each overlay toggled independently via checkboxes in ExpertModePanel

### 3. Historical Activity Heatmap
- Add `leaflet.heat` dependency
- New toggle in map controls: "Activity Heatmap"
- Fetches all `avalanche_events` and renders as heatmap layer
- Intensity = count weighted by recency (newer = hotter)
- Gradient: green (old) → red (recent)

### 4. Extended 72h Forecast + Hydrograph
- Update `run-forecast` edge function: change `forecast_days=2` → `forecast_days=3`, generate 73 hourly grids (0-72)
- Update `TimeSlider` max prop: 24 → 72 (when 72h data available)
- New component `HydrographChart.tsx`: Recharts line chart showing 72h risk + weather evolution for selected cell
- Shown in expert panel or below SHAP chart when cell is selected

### 5. Vector Polygons Option
- In Expert Mode: toggle to convert high-risk cells (>3) from rectangles to Turf.js-generated polygons
- Add `@turf/turf` dependency
- Smooths cell boundaries for more natural slope-path visualization

### 6. Web Push Alerts (Simplified)
- New table `user_alerts` (id, endpoint, keys, region_bbox, created_at)
- In Expert Mode sidebar: "Subscribe to Alerts" button
- Uses Web Push API (requestPermission + subscribe)
- Stores PushSubscription in `user_alerts` table
- Actual push sending is a future enhancement (stub the trigger)

### 7. Polish & Accessibility
- Dark basemap toggle already exists via ThemeToggle; ensure CartoDB Dark Voyager is used in dark mode (already done)
- Add keyboard shortcuts: R = Run Forecast, Space = Play/Pause, ← → = scrub timeline
- Add ARIA labels to all interactive elements (buttons, sliders, toggles)
- PWA: Add `manifest.json` with icons + `display: standalone` for installability (NO service worker per project guidelines)
- Mobile: Expert sidebar slides from right, collapses gracefully

### 8. UI/UX Consistency
- All new toggles get Tooltip wrappers
- Loading states for overlay fetches
- Disclaimer banner preserved everywhere

## New Files
- `src/components/ExpertModePanel.tsx` -- Right sidebar with expert controls
- `src/components/ImpactOverlays.tsx` -- Overpass + GHSL layers for map
- `src/components/HydrographChart.tsx` -- 72h risk/weather line chart
- `src/components/ActivityHeatmap.tsx` -- Leaflet.heat layer component
- `public/manifest.json` -- PWA manifest for installability

## Modified Files
- `src/pages/Index.tsx` -- Expert mode state, keyboard shortcuts, 72h support, right panel
- `src/components/AvalancheMap.tsx` -- Accept new layer props (heatmap, impact, vector polygons)
- `src/components/TimeSlider.tsx` -- Dynamic max (24/72), ARIA labels
- `src/components/RiskDashboard.tsx` -- Show hydrograph when expert mode
- `src/components/HistoricalEventsToggle.tsx` -- Fix `.finally()` TS error
- `supabase/functions/run-forecast/index.ts` -- 72h support
- `index.html` -- Link manifest.json
- `package.json` -- Add `leaflet.heat`, `@turf/turf`, `@types/leaflet.heat`

## Database Changes
- New table: `user_alerts` (id uuid, endpoint text, p256dh text, auth_key text, region_bbox numeric[], created_at timestamptz) with RLS
- No changes to existing tables

## Implementation Order
1. Fix 3 build errors
2. Database migration (user_alerts)
3. Update run-forecast for 72h
4. Create ExpertModePanel, ImpactOverlays, ActivityHeatmap, HydrographChart
5. Update Index.tsx with expert mode, keyboard shortcuts, right panel
6. Update AvalancheMap with new layers
7. Add PWA manifest
8. Deploy and test

## Performance Notes
- Overpass API queries are bounded by bbox and cached client-side
- Heatmap uses canvas rendering (leaflet.heat) -- performant for 1000+ points
- 72h forecast generates 73×400=29,200 cells total in JSONB -- within Supabase limits
- Turf.js polygon conversion only runs on high-risk cells (typically <30% of grid)

