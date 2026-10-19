-- Add issue_slot, cadence_hours, valid_from, valid_to, source_as_of
-- to forecast_grids and forecast_runs tables.
--
-- This migration is idempotent and backward-compatible:
-- - Existing rows are backfilled with issue_slot='06', cadence_hours=24
-- - The old unique constraint is replaced with one that includes issue_slot
-- - The promote_forecast_run() RPC is updated to scope supersession by issue_slot

-- =========================================================================
-- forecast_grids: add cadence columns
-- =========================================================================

ALTER TABLE public.forecast_grids
  ADD COLUMN IF NOT EXISTS issue_slot TEXT NOT NULL DEFAULT '06';

ALTER TABLE public.forecast_grids
  ADD COLUMN IF NOT EXISTS cadence_hours INTEGER NOT NULL DEFAULT 24;

ALTER TABLE public.forecast_grids
  ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ;

ALTER TABLE public.forecast_grids
  ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

ALTER TABLE public.forecast_grids
  ADD COLUMN IF NOT EXISTS source_as_of TIMESTAMPTZ;

-- Drop old unique constraint and replace with issue_slot-aware version
ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_unique_horizon;

DROP INDEX IF EXISTS public.forecast_grids_unique_active_idx;

CREATE UNIQUE INDEX IF NOT EXISTS forecast_grids_unique_active_slot_idx
  ON public.forecast_grids (hazard_type, region_key, forecast_date, horizon_hours, issue_slot)
  WHERE status IN ('queued', 'running', 'ready');

-- =========================================================================
-- forecast_runs: add cadence columns
-- =========================================================================

ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS issue_slot TEXT NOT NULL DEFAULT '06';

ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS cadence_hours INTEGER NOT NULL DEFAULT 24;

ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ;

ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS source_as_of TIMESTAMPTZ;

-- =========================================================================
-- Update promote_forecast_run() to scope supersession by issue_slot
-- =========================================================================

-- Drop the old active-run index that was unique by (hazard_type, region_key) only.
-- This prevented multiple active six-hour slots for the same region.
DROP INDEX IF EXISTS public.forecast_runs_active_region_idx;

-- Create new active-run index scoped by issue_slot.
-- This allows slots 00, 06, 12, 18 to all be active simultaneously
-- while still ensuring only one active run per (hazard, region, date, slot).
CREATE UNIQUE INDEX IF NOT EXISTS forecast_runs_active_slot_idx
  ON public.forecast_runs (hazard_type, region_key, forecast_date, issue_slot)
  WHERE active = TRUE;

-- Add CHECK constraints for cadence validity
ALTER TABLE public.forecast_runs
  DROP CONSTRAINT IF EXISTS forecast_runs_cadence_hours_check;
ALTER TABLE public.forecast_runs
  ADD CONSTRAINT forecast_runs_cadence_hours_check
  CHECK (cadence_hours IN (6, 24)) NOT VALID;

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_cadence_hours_check;
ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_cadence_hours_check
  CHECK (cadence_hours IN (6, 24)) NOT VALID;

-- G6: Add CHECK constraints for issue_slot, valid_window, and source_as_of
ALTER TABLE public.forecast_runs
  DROP CONSTRAINT IF EXISTS forecast_runs_issue_slot_check;
ALTER TABLE public.forecast_runs
  ADD CONSTRAINT forecast_runs_issue_slot_check
  CHECK (issue_slot IN ('00', '06', '12', '18')) NOT VALID;

ALTER TABLE public.forecast_runs
  DROP CONSTRAINT IF EXISTS forecast_runs_cadence_slot_consistency_check;
ALTER TABLE public.forecast_runs
  ADD CONSTRAINT forecast_runs_cadence_slot_consistency_check
  CHECK (
    (cadence_hours = 24 AND issue_slot = '06')
    OR (cadence_hours = 6 AND issue_slot IN ('00', '06', '12', '18'))
  ) NOT VALID;

ALTER TABLE public.forecast_runs
  DROP CONSTRAINT IF EXISTS forecast_runs_valid_window_check;
ALTER TABLE public.forecast_runs
  ADD CONSTRAINT forecast_runs_valid_window_check
  CHECK (
    (valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_to > valid_from)
    -- Legacy/building rows may be completed by the publication patch. Any
    -- new ready row must carry a complete valid window.
    OR status IN ('building', 'failed', 'superseded')
  ) NOT VALID;

ALTER TABLE public.forecast_runs
  DROP CONSTRAINT IF EXISTS forecast_runs_source_as_of_not_null;
ALTER TABLE public.forecast_runs
  ADD CONSTRAINT forecast_runs_source_as_of_not_null
  CHECK (source_as_of IS NOT NULL OR status IN ('building', 'failed', 'superseded')) NOT VALID;

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_issue_slot_check;
ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_issue_slot_check
  CHECK (issue_slot IN ('00', '06', '12', '18')) NOT VALID;

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_cadence_slot_consistency_check;
ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_cadence_slot_consistency_check
  CHECK (
    (cadence_hours = 24 AND issue_slot = '06')
    OR (cadence_hours = 6 AND issue_slot IN ('00', '06', '12', '18'))
  ) NOT VALID;

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_valid_window_check;
ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_valid_window_check
  CHECK (
    (valid_from IS NOT NULL AND valid_to IS NOT NULL AND valid_to > valid_from)
    -- queued/running rows may be filled by the governed persistence patch;
    -- ready/partial/stale rows require a complete window.
    OR status IN ('queued', 'running', 'failed', 'superseded')
  ) NOT VALID;

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_source_as_of_not_null;
ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_source_as_of_not_null
  CHECK (source_as_of IS NOT NULL OR status IN ('queued', 'running', 'failed', 'superseded')) NOT VALID;

CREATE OR REPLACE FUNCTION public.promote_forecast_run(p_forecast_run_id UUID)
RETURNS public.forecast_runs
LANGUAGE plpgsql
AS $$
DECLARE
  target_row public.forecast_runs%ROWTYPE;
BEGIN
  SELECT *
    INTO target_row
  FROM public.forecast_runs
  WHERE id = p_forecast_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'forecast_run % not found', p_forecast_run_id;
  END IF;

  -- Supersede only runs with the same region, hazard, date, AND issue_slot
  UPDATE public.forecast_runs
     SET active = FALSE,
         status = CASE WHEN id = p_forecast_run_id THEN status ELSE 'superseded' END
   WHERE hazard_type = target_row.hazard_type
     AND region_key = target_row.region_key
     AND forecast_date = target_row.forecast_date
     AND issue_slot = target_row.issue_slot
     AND active = TRUE
     AND id <> p_forecast_run_id;

  UPDATE public.forecast_runs
     SET active = TRUE,
         status = 'ready',
         publication_status = 'published',
         published_at = now()
   WHERE id = p_forecast_run_id
   RETURNING * INTO target_row;

  RETURN target_row;
END;
$$;

-- Re-grant permissions on updated function
REVOKE ALL ON FUNCTION public.promote_forecast_run(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.promote_forecast_run(UUID) TO service_role;
