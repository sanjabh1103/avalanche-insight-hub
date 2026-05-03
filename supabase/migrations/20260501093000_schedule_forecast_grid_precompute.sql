CREATE EXTENSION IF NOT EXISTS pg_cron;

DO $cron$
DECLARE
  existing_job_id bigint;
BEGIN
  SELECT jobid
  INTO existing_job_id
  FROM cron.job
  WHERE jobname = 'forecast-grid-precompute-job'
  LIMIT 1;

  IF existing_job_id IS NOT NULL THEN
    PERFORM cron.unschedule(existing_job_id);
  END IF;

  PERFORM cron.schedule(
    'forecast-grid-precompute-job',
    '30 1 * * *',
    $job$SELECT net.http_post(
      url := 'https://fzheroisjhxnairglelv.supabase.co/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6aGVyb2lzamh4bmFpcmdsZWx2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYxNjE2NzcsImV4cCI6MjA5MTczNzY3N30.7YlWuiewXG17g0eJeOjOFJWYunzBvE3b8Nx1YElZsWI',
        'apikey', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ6aGVyb2lzamh4bmFpcmdsZWx2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYxNjE2NzcsImV4cCI6MjA5MTczNzY3N30.7YlWuiewXG17g0eJeOjOFJWYunzBvE3b8Nx1YElZsWI'
      ),
      body := jsonb_build_object(
        'type', 'forecast_grid_precompute',
        'hazard_type', 'avalanche',
        'artifact_dir', '/artifacts/20260430T165417Z',
        'forecast_hours', 72,
        'grid_size', 20
      )
    )$job$
  );
END $cron$;

SELECT jobid, jobname, schedule, active
FROM cron.job
WHERE jobname = 'forecast-grid-precompute-job';
