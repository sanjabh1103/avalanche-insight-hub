-- Schedule Avalanche Compass foundation jobs with non-overlapping windows
-- Snow cover refresh and recent activity refresh run after the midnight enrichment job.
-- Weekly evaluation runs later on Sunday to avoid colliding with the daily jobs.

CREATE EXTENSION IF NOT EXISTS pg_cron;

DO $cron$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM cron.job
    WHERE jobname = 'snow-cover-refresh-job'
  ) THEN
    PERFORM cron.schedule(
      'snow-cover-refresh-job',
      '30 0 * * *',
      $job$SELECT net.http_post(
        url := 'https://cyjqvqwpdgluivjoxcfl.supabase.co/functions/v1/trigger-job',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || COALESCE(current_setting('app.settings.job_dispatch_token', true), ''),
          'apikey', COALESCE(current_setting('app.settings.supabase_anon_key', true), '')
        ),
        body := jsonb_build_object('type', 'snow_cover_refresh', 'hazard_type', 'avalanche')
      )$job$
    );
  END IF;
END $cron$;

DO $cron$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM cron.job
    WHERE jobname = 'recent-activity-refresh-job'
  ) THEN
    PERFORM cron.schedule(
      'recent-activity-refresh-job',
      '0 1 * * *',
      $job$SELECT net.http_post(
        url := 'https://cyjqvqwpdgluivjoxcfl.supabase.co/functions/v1/trigger-job',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || COALESCE(current_setting('app.settings.job_dispatch_token', true), ''),
          'apikey', COALESCE(current_setting('app.settings.supabase_anon_key', true), '')
        ),
        body := jsonb_build_object('type', 'recent_activity_refresh', 'hazard_type', 'avalanche')
      )$job$
    );
  END IF;
END $cron$;

DO $cron$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM cron.job
    WHERE jobname = 'weekly-evaluation-job'
  ) THEN
    PERFORM cron.schedule(
      'weekly-evaluation-job',
      '0 3 * * 0',
      $job$SELECT net.http_post(
        url := 'https://cyjqvqwpdgluivjoxcfl.supabase.co/functions/v1/trigger-job',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || COALESCE(current_setting('app.settings.job_dispatch_token', true), ''),
          'apikey', COALESCE(current_setting('app.settings.supabase_anon_key', true), '')
        ),
        body := jsonb_build_object('type', 'run_evaluation', 'hazard_type', 'avalanche')
      )$job$
    );
  END IF;
END $cron$;

SELECT jobid, jobname, schedule, active
FROM cron.job
WHERE jobname IN (
  'snow-cover-refresh-job',
  'recent-activity-refresh-job',
  'weekly-evaluation-job'
)
ORDER BY jobname;
