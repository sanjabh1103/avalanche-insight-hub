**Avalanche Insight Hub (Avalanche Compass) – Product Requirements Document (PRD)**

 
**Status:** Ready for Windsurf IDE comparison (envisaged vs implemented)  
**Purpose of this PRD:** This is the single source-of-truth checklist for Windsurf to audit the GitHub repo (https://github.com/sanjabh1103/avalanche-insight-hub) against the complete vision developed across our entire conversation. Every feature, user story, and outcome below was explicitly defined or refined in the chat (Groundsource adaptation, real Open-Meteo ensemble, self-improving loop, Flood Hub parity, etc.).

### 1. Vision & Objectives
**Vision**  
Avalanche Insight Hub is the world’s first open-source, Groundsource-style AI avalanche early-warning system. It mirrors Google Flood Hub exactly but for avalanches: Gemini extracts real events from global news + user field reports to build a live dataset, then runs 24-hour-ahead ensemble forecasts on a dynamic risk grid, empowering backcountry users, mountain communities, and agencies in monitored *and* data-sparse regions (Himalayas, Andes, etc.).

**Core Objectives** (directly from conversation)
- Provide **24-hour ahead, region-aware avalanche risk forecasts** using real weather + terrain + snowpack proxies.
- Create a **self-improving closed-loop system** (field reports → Gemini enrichment → daily pg_cron → fine-tune).
- Deliver **Flood Hub-level UX** (interactive map grid, timeline playback, SHAP explanations, shareable public links).
- Achieve usable accuracy even in zero-monitoring countries while matching human forecaster quality where bulletins exist.
- Include strong safety disclaimers and explainability (SHAP) so users understand *why* a slope is risky.

**Success Definition**  
A deployed web app where any user can select a mountain range, run a forecast, see a colored risk grid evolve over 24 hours, submit a field report that immediately improves the dataset, and share the exact view publicly — all with zero external R&D after launch.

### 2. Target Users & Personas
- **Backcountry skiers / snowboarders** – quick risk check before a tour.
- **Mountain guides / ski resorts** – slope-scale decisions.
- **Local communities / villages in Himalayas/Andes** – road/trail closures.
- **Civil defense / rescue teams** – regional overview + export.
- **Researchers / citizen scientists** – contribute reports + view analytics.

### 3. Key Features (High-Level)
- Interactive Leaflet map with 20×20 risk grid (1–5 EAWS scale + problem type).
- Real 24h Open-Meteo + terrain ensemble inference with hourly timeline playback.
- SHAP explanations per cell.
- Gemini-powered Groundsource extraction from news + field reports.
- Events layer with confidence-colored markers.
- Field report modal (GPS/manual + AI classification).
- Admin panel with job triggers + model status badge.
- Export CSV/JSON + shareable public links with full state.
- Mobile-responsive + permanent disclaimer banner.
- pg_cron daily enrichment + realtime subscriptions.

### 4. Top 15 User Stories (Prioritized by Impact)
Each story includes **Acceptance Criteria** for Windsurf to verify.

1. **As a backcountry user**, I want to select a mountain region (preset or bbox) so I can get a localized 24h forecast.  
   *AC:* 9+ presets (Himalayas, Alps, Rockies, etc.), map flies to center/zoom, forecast button triggers real Open-Meteo + ensemble inference.

2. **As a backcountry user**, I want to see a color-coded 20×20 risk grid on the map so I can visually assess danger at a glance.  
   *AC:* Grid uses EAWS 1–5 colors + problem type, remains visible/aligned on zoom, cells clickable for details.

3. **As a backcountry user**, I want a 24h timeline scrubber/playback so I can see how risk evolves hour-by-hour.  
   *AC:* Colors + SHAP update live from `hourly_grids` JSONB, works on mobile touch.

4. **As a backcountry user**, I want SHAP explanations for every cell so I understand *why* a slope is risky.  
   *AC:* Bar chart shows top features (slope, new_snow_24h, wind_drift, etc.) with real Open-Meteo values globally (not just US).

5. **As any user**, I want to submit a field report (description + GPS/manual coords) so my observation improves the global dataset.  
   *AC:* Modal opens from topbar REPORT button, Gemini classifies → PostGIS dedup → marker appears in Events layer within seconds.

6. **As any user**, I want to toggle the historical Events layer so I can see recent avalanches.  
   *AC:* Confidence-colored CircleMarkers with popups (location, date, danger, summary).

7. **As an admin/power user**, I want one-click job triggers (enrichment, Sentinel-1, fine-tune, precompute) so I can maintain the system.  
   *AC:* Toasts, ACTIVE JOBS counter, Recent Jobs log with realtime updates.

8. **As any user**, I want a Model Status badge so I know the system is current.  
   *AC:* Shows version, last inference time, data freshness, F1 score.

9. **As any user**, I want to export current forecast + events as CSV/JSON so I can analyze or share offline.  
   *AC:* Visible Export button in top nav, downloads full dataset.

10. **As any user**, I want to share a forecast link so colleagues or rescue teams see the exact same view.  
    *AC:* Button copies URL with query params (region, bbox, hour, selected cell); incognito link restores identical grid + timeline.

11. **As a global user in sparse regions**, I want forecasts that work worldwide so I am not limited to monitored Alps/US.  
    *AC:* Real Open-Meteo weather feeds *all* regions (snowfall/wind/snow_depth visible in SHAP for Nepal/Andes/etc.).

12. **As a mobile user**, I want full responsive design so I can check risk on the mountain.  
    *AC:* Hamburger menu, large touch targets, SHAP panel accessible, timeline works on touch.

13. **As any user**, I want a permanent safety disclaimer so I never treat the app as official.  
    *AC:* Red banner always visible, non-dismissible, references EAWS and official centers.

14. **As a system maintainer**, I want daily automatic enrichment via pg_cron so the Groundsource dataset grows without manual effort.  
    *AC:* Midnight UTC job runs Gemini + NewsData.io → new events added.

15. **As a researcher/user**, I want realtime job status and analytics so I can monitor system health.  
    *AC:* Admin panel shows forecast analytics table, Gemini usage, compute_jobs realtime updates.

### 5. Non-Functional Requirements
- **Performance**: Forecast <15s for typical region; grid renders smoothly on zoom.
- **Reliability**: Realtime subscriptions for jobs/events; graceful fallback if edge function fails.
- **Security**: RLS policies; public read-only for shared links; no sensitive data in client.
- **Accessibility**: WCAG AA, high-contrast danger colors, keyboard navigation.
- **Scalability**: Works globally on free-tier Supabase; edge functions handle concurrent users.
- **Explainability & Safety**: Every forecast includes SHAP; strong disclaimers on every screen.
- **Tech Stack Fidelity**: React/TS + Supabase (PostGIS, Edge Functions, pg_cron, realtime) + Lovable-generated code.

### 6. Success Metrics & Expected Outcomes
**Primary Outcomes (what the app must deliver)**
- Users receive **usable 24h avalanche risk information** in regions with zero traditional monitoring.
- Field reports + news automatically enrich the dataset → model improves over time (closed-loop Groundsource).
- A single shareable link lets anyone see the exact same risk view (Flood Hub parity).
- Early warnings enable avoidance → measurable reduction in exposure (even 12–24h notice saves lives per conversation impact estimates).

**Quantitative Metrics** (for Windsurf to track)
- 100% of top 15 user stories implemented with AC met.
- Forecast grid updates correctly for all presets (including non-US weather features).
- Events layer shows new reports within 10s.
- Share links restore full state.
- No console errors during full flow.
- Mobile UX fully usable.

**Qualitative Outcomes**
- The app feels like Google Flood Hub but for avalanches.
- It is the first personal, self-sustaining, open-source avalanche AI system.
- Safety-first: disclaimers + explainability prevent misuse.

### 7. Out of Scope (Explicitly Excluded)
- Official certification as a replacement for national avalanche centers.
- Real-time SAR/Sentinel-1 image processing (placeholder only).
- Paid features or monetization.
- Native mobile app (web-only with PWA potential).

**How to Use This PRD in Windsurf**  
1. Open the repo.  
2. Compare every user story’s AC against the live code/UI.  
3. Flag any gap → create issue or fix.  
4. Once all 15 stories + non-functional items are green → the app fully realizes the vision from our entire conversation.

 