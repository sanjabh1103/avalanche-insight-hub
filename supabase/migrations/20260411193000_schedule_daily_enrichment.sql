-- Schedule daily enrichment job at midnight UTC
-- This enables the self-improving Groundsource loop (Story #14)

-- First ensure pg_cron extension is enabled
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule the daily enrichment job
-- Runs at midnight UTC every day
SELECT cron.schedule(
  'daily-enrichment-job',      -- job name
  '0 0 * * *',                 -- cron expression: midnight UTC daily
  'SELECT net.http_post(
    url:=''https://cyjqvqwpdgluivjoxcfl.supabase.co/functions/v1/trigger-job'',
    headers:=jsonb_build_object(
      ''Content-Type'', ''application/json'',
      ''Authorization'', ''Bearer '' || COALESCE(current_setting(''app.settings.job_dispatch_token'', true), ''''),
      ''apikey'', COALESCE(current_setting(''app.settings.supabase_anon_key'', true), '''')
    ),
    body:=''{"type": "daily_enrichment"}''::jsonb
  )'
);

-- Verify the job was created
SELECT jobid, schedule, jobname, active 
FROM cron.job 
WHERE jobname = 'daily-enrichment-job';
