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
    url:=''https://rmzipvwqafrxhhuinggf.supabase.co/functions/v1/trigger-job'',
    headers:=''{"Content-Type": "application/json", "Authorization": "Bearer " || (SELECT anon_key FROM pgsodium.decrypt_auth_data())}''::jsonb,
    body:=''{"type": "daily_enrichment"}''::jsonb
  )'
);

-- Verify the job was created
SELECT jobid, schedule, jobname, active 
FROM cron.job 
WHERE jobname = 'daily-enrichment-job';
