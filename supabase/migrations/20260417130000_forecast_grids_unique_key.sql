-- Unified PRD v2.0 Phase 1 operator rollout fix:
-- daily_inference.py upserts forecast_grids with
--   on_conflict=hazard_type,region_key,forecast_date,horizon_hours
-- but the table was created without a matching UNIQUE constraint, so the
-- PostgREST upsert returns 42P10. Add the constraint idempotently.

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_unique_horizon;

ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_unique_horizon
  UNIQUE (hazard_type, region_key, forecast_date, horizon_hours);
