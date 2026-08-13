-- Stuck job cleanup: UPDATE existing stuck jobs and schedule periodic cleanup.
-- This must be in a separate migration from the ALTER TYPE ADD VALUE because
-- PostgreSQL does not allow using a new enum value in the same transaction.

-- Timeout stuck compute_jobs that have been "running" for more than 1 hour.
UPDATE public.compute_jobs
SET status = 'timeout',
    error = COALESCE(error, '') || 'Auto-timeout: job exceeded 1 hour in running state.',
    updated_at = now()
WHERE status = 'running'
  AND type = 'forecast_grid_precompute'
  AND created_at < now() - interval '1 hour';

-- Schedule a periodic cleanup that auto-times-out any compute_job
-- stuck in "running" for more than 1 hour. Runs every 30 minutes.
-- pg_cron extension already exists from earlier migrations.

DO $cron$
DECLARE
  existing_job_id bigint;
BEGIN
  SELECT jobid
    INTO existing_job_id
  FROM cron.job
  WHERE jobname = 'stuck-job-cleanup'
  LIMIT 1;

  IF existing_job_id IS NOT NULL THEN
    PERFORM cron.unschedule(existing_job_id);
  END IF;

  PERFORM cron.schedule(
    'stuck-job-cleanup',
    '*/30 * * * *',
    $job$UPDATE public.compute_jobs
      SET status = 'timeout',
          error = COALESCE(error, '') || 'Auto-timeout: job exceeded 1 hour in running state.',
          updated_at = now()
      WHERE status = 'running'
        AND created_at < now() - interval '1 hour'$job$
  );
END $cron$;
