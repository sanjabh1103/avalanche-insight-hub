# forecast_grids Sunset Plan (Legacy Read-Path Deprecation)

This document formalizes the deprecation timeline, migration steps, and verification strategies to sunset the legacy forecast read-path (`forecast_grids` database table) in favor of the manifest-backed, production-grade `forecast_active_runs` pipeline.

## 1. Executive Summary
The Avalanche Insight Hub initially stored precomputed forecast cells directly in the PostgreSQL table `forecast_grids`. To support high-resolution multi-hazard forecasting, this table has been replaced with `forecast_active_runs`, which references rich forecast manifests stored in object storage (e.g. Supabase Storage buckets). 
To clean up database bloat, simplify API contracts, and eliminate dual-path logic, we are deprecating the legacy `forecast_grids` read-path.

---

## 2. Migration Timeline

```mermaid
gantt
    title forecast_grids Sunset Timeline
    dateFormat  YYYY-MM-DD
    section Phases
    Phase 1: Telemetry & Warnings (Current)    :active, p1, 2026-06-11, 14d
    Phase 2: Frontend Client Verification       : p2, after p1, 10d
    Phase 3: Database Shadow Period             : p3, after p2, 14d
    Phase 4: Table Dropping & Code Cleanup     : p4, after p3, 7d
```

| Phase | Milestone | Start Date | End Date | Description / Acceptance Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | Telemetry & Warnings | 2026-06-11 | 2026-06-25 | Deploy edge-function telemetry warnings to log any access to `forecast_grids` in production. |
| **Phase 2** | Client verification | 2026-06-25 | 2026-07-05 | Confirm all active client codebases (web app, partner integrations) request forecasts via the manifest-backed `forecast_runs` format. |
| **Phase 3** | Shadow Period | 2026-07-05 | 2026-07-19 | Keep the table intact but confirm zero telemetry warning occurrences in production logs over 14 consecutive days. |
| **Phase 4** | Complete Sunset | 2026-07-19 | 2026-07-26 | Execute migration script to drop the `forecast_grids` table, remove legacy read paths in `run-forecast` edge function, and delete frontend fallback shims. |

---

## 3. Telemetry Signatures
Telemetry warning logs have been integrated into [run-forecast/index.ts](file:///Users/sanjayb/avalanche-insight-hub/supabase/functions/run-forecast/index.ts). Operations engineers can monitor these signatures via the Supabase Edge Function Log Viewer or external log forwarders:

1. **Standard Legacy Grid Access**:
   `[run-forecast] Warning: Accessing deprecated legacy read path forecast_grids for regionKey=<key>, regionName=<name>`
   *Trigger*: A client requested a forecast for which no `forecast_active_runs` exists, falling back to a same-day grid.

2. **Fallback Legacy Grid Access**:
   `[run-forecast] Warning: Accessing deprecated legacy read path forecast_grids (latest/fallback) for regionKey=<key>, regionName=<name>`
   *Trigger*: No active run exists, and the function returned the latest historical grid.

---

## 4. Verification Checklists

### Pre-Sunset Checks (Phase 2 & 3)
- [ ] Query Supabase Edge Function logs for the `Warning: Accessing deprecated legacy read path forecast_grids` string.
- [ ] Confirm no external partner data pipelines are pushing directly to the `forecast_grids` table.
- [ ] Audit frontend components [gridUtils.ts](file:///Users/sanjayb/avalanche-insight-hub/src/lib/gridUtils.ts) to verify they use the manifest reader by default.

### Sunset Execution Checks (Phase 4)
- [ ] Run migration script dropping `forecast_grids` table.
- [ ] Remove `fetchFreshGrid` and `fetchLatestGrid` from `supabase/functions/run-forecast/index.ts`.
- [ ] Remove `forecast_grids` references in `.planning/` directories and documentation.
