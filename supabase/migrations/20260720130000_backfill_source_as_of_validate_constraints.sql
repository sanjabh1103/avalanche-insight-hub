-- Backfill NULL source_as_of on ready/active rows and validate NOT VALID constraints.
--
-- The 20260718120000 migration added source_as_of and valid_window constraints as
-- NOT VALID, meaning existing rows were not checked. Live evidence shows 8 ready
-- runs with NULL source_as_of, violating the forecast_runs_source_as_of_not_null
-- constraint. This migration:
--   1. Backfills source_as_of for ready/active runs and grids using the best
--      available timestamp (published_at > created_at > now).
--   2. Backfills valid_from/valid_to for ready rows that lack them, using
--      forecast_date as the basis.
--   3. Validates all NOT VALID constraints so they enforce existing rows going
--      forward.
--
-- This migration is safe to re-run (idempotent). If validation fails on any
-- constraint, the migration will error and the offending rows must be
-- quarantined or corrected before re-running.

-- =========================================================================
-- 1. Backfill source_as_of on forecast_runs
-- =========================================================================

UPDATE public.forecast_runs
  SET source_as_of = COALESCE(published_at, created_at, now())
WHERE source_as_of IS NULL
  AND status NOT IN ('building', 'failed', 'superseded');

-- =========================================================================
-- 2. Backfill source_as_of on forecast_grids
-- =========================================================================

UPDATE public.forecast_grids
  SET source_as_of = COALESCE(created_at, now())
WHERE source_as_of IS NULL
  AND status NOT IN ('queued', 'running', 'failed', 'superseded');

-- =========================================================================
-- 3. Backfill valid_from/valid_to on ready runs that lack them
-- =========================================================================

-- For ready runs with NULL valid_from, use forecast_date at 06:00 UTC (issue_slot default)
UPDATE public.forecast_runs
  SET valid_from = (forecast_date::timestamp AT TIME ZONE 'UTC') + INTERVAL '6 hours'
WHERE valid_from IS NULL
  AND status = 'ready';

-- For ready runs with NULL valid_to, set valid_from + 24 hours (daily cadence default)
UPDATE public.forecast_runs
  SET valid_to = valid_from + (cadence_hours || ' hours')::INTERVAL
WHERE valid_to IS NULL
  AND status = 'ready'
  AND valid_from IS NOT NULL;

-- =========================================================================
-- 4. Backfill valid_from/valid_to on ready grids that lack them
-- =========================================================================

UPDATE public.forecast_grids
  SET valid_from = (forecast_date::timestamp AT TIME ZONE 'UTC') + INTERVAL '6 hours'
WHERE valid_from IS NULL
  AND status NOT IN ('queued', 'running', 'failed', 'superseded');

UPDATE public.forecast_grids
  SET valid_to = valid_from + (cadence_hours || ' hours')::INTERVAL
WHERE valid_to IS NULL
  AND status NOT IN ('queued', 'running', 'failed', 'superseded')
  AND valid_from IS NOT NULL;

-- =========================================================================
-- 5. Validate all NOT VALID constraints
-- =========================================================================

-- forecast_runs constraints
ALTER TABLE public.forecast_runs
  VALIDATE CONSTRAINT forecast_runs_cadence_hours_check;

ALTER TABLE public.forecast_runs
  VALIDATE CONSTRAINT forecast_runs_issue_slot_check;

ALTER TABLE public.forecast_runs
  VALIDATE CONSTRAINT forecast_runs_cadence_slot_consistency_check;

ALTER TABLE public.forecast_runs
  VALIDATE CONSTRAINT forecast_runs_valid_window_check;

ALTER TABLE public.forecast_runs
  VALIDATE CONSTRAINT forecast_runs_source_as_of_not_null;

-- forecast_grids constraints
ALTER TABLE public.forecast_grids
  VALIDATE CONSTRAINT forecast_grids_cadence_hours_check;

ALTER TABLE public.forecast_grids
  VALIDATE CONSTRAINT forecast_grids_issue_slot_check;

ALTER TABLE public.forecast_grids
  VALIDATE CONSTRAINT forecast_grids_cadence_slot_consistency_check;

ALTER TABLE public.forecast_grids
  VALIDATE CONSTRAINT forecast_grids_valid_window_check;

ALTER TABLE public.forecast_grids
  VALIDATE CONSTRAINT forecast_grids_source_as_of_not_null;

-- =========================================================================
-- 6. Verification query (run manually after applying)
-- =========================================================================

-- Confirm zero ready runs with NULL source_as_of:
--   SELECT count(*) FROM public.forecast_runs
--   WHERE status = 'ready' AND source_as_of IS NULL;
--
-- Confirm all constraints are validated:
--   SELECT conname, convalidated
--   FROM pg_constraint
--   WHERE conname LIKE 'forecast_%check' OR conname LIKE 'forecast_%not_null'
--   ORDER BY conname;
