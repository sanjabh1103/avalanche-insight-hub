-- Forecast retention cleanup: deletes non-active forecast runs and their
-- associated rows/objects older than FORECAST_RETENTION_DAYS (default 30).
--
-- This migration adds a pg_cron job that runs daily at 03:00 UTC to:
--   1. Delete forecast_run_hours for non-active runs older than retention
--   2. Delete forecast_publication_events for non-active runs older than retention
--   3. Delete forecast_runs rows older than retention that are NOT active
--
-- Active runs (one per region/hazard/date) are always preserved regardless
-- of age, as enforced by the promote_forecast_run() function.
--
-- Storage object cleanup is handled separately by the Python script
-- backend/scripts/cleanup_old_storage.py, which is scheduled via GitHub Actions.

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Grant pg_cron access to service_role (required for Supabase)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'service_role'
  ) THEN
    RETURN;
  END IF;
END
$$;

-- Schedule the retention cleanup job
DO $$
DECLARE
  existing_job_id BIGINT;
BEGIN
  -- Unschedule any existing version of this job
  SELECT jobid
    INTO existing_job_id
  FROM cron.job
  WHERE jobname = 'forecast-retention-cleanup'
  LIMIT 1;

  IF existing_job_id IS NOT NULL THEN
    PERFORM cron.unschedule(existing_job_id);
  END IF;

  -- Schedule daily at 03:00 UTC
  -- Deletes non-active forecast runs older than 30 days.
  -- CASCADE on forecast_run_hours and forecast_publication_events handles child rows.
  PERFORM cron.schedule(
    'forecast-retention-cleanup',
    '0 3 * * *',
    $job$
      DELETE FROM public.forecast_runs
      WHERE created_at < now() - interval '30 days'
        AND active = FALSE;
    $job$
  );
END
$$;

-- Add a comment documenting the retention policy
COMMENT ON FUNCTION public.promote_forecast_run IS 'Ensures only one active run per hazard_type/region_key/forecast_date. Active runs are never deleted by the retention cleanup job.';
