-- Parameterize cron-migration JWTs and Supabase URLs
-- This migration removes hardcoded keys and URLs from pg_cron jobs (Remediation Task 1.5)

-- Create private schema if it doesn't exist (Supabase standard for helper functions)
CREATE SCHEMA IF NOT EXISTS private;

-- Helper function to retrieve the Supabase URL dynamically
CREATE OR REPLACE FUNCTION private.get_supabase_url()
RETURNS text AS $$
DECLARE
  val text;
BEGIN
  -- Try to get from custom database settings first
  val := current_setting('app.settings.supabase_url', true);
  IF val IS NOT NULL AND val <> '' THEN
    RETURN val;
  END IF;
  
  -- Fallback to the current production URL
  RETURN 'https://eyyellmffzzujyssaayb.supabase.co';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Helper function to retrieve the Job Dispatch Token dynamically
CREATE OR REPLACE FUNCTION private.get_job_dispatch_token()
RETURNS text AS $$
DECLARE
  val text;
BEGIN
  -- 1. Try to get custom dispatch token setting
  val := current_setting('app.settings.job_dispatch_token', true);
  IF val IS NOT NULL AND val <> '' THEN
    RETURN val;
  END IF;

  -- 2. Fallback to the dedicated dispatch token from Vault.
  -- Do not fall back to service_role or anon here: cron should have the
  -- narrow job token, and missing configuration should fail closed.
  SELECT decrypted_secret INTO val
  FROM vault.decrypted_secrets
  WHERE name = 'job_dispatch_token'
  LIMIT 1;

  IF val IS NOT NULL AND val <> '' THEN
    RETURN val;
  END IF;

  RAISE EXCEPTION 'Missing job dispatch token. Set app.settings.job_dispatch_token or vault secret job_dispatch_token.';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Helper function to retrieve the API key dynamically for routing
CREATE OR REPLACE FUNCTION private.get_supabase_apikey()
RETURNS text AS $$
DECLARE
  val text;
BEGIN
  -- 1. Try to get anon_key from Vault
  SELECT decrypted_secret INTO val
  FROM vault.decrypted_secrets
  WHERE name = 'anon_key'
  LIMIT 1;
  IF val IS NOT NULL AND val <> '' THEN
    RETURN val;
  END IF;

  -- 2. Fallback to database setting.
  val := current_setting('app.settings.supabase_anon_key', true);
  IF val IS NOT NULL AND val <> '' THEN
    RETURN val;
  END IF;

  RAISE EXCEPTION 'Missing Supabase anon key. Set vault secret anon_key or app.settings.supabase_anon_key.';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Re-schedule all pg_cron jobs using parameterized functions
DO $cron$
BEGIN
  -- 1. daily-enrichment-job
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'daily-enrichment-job') THEN
    PERFORM cron.unschedule('daily-enrichment-job');
  END IF;
  
  PERFORM cron.schedule(
    'daily-enrichment-job',
    '0 0 * * *',
    $$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || private.get_job_dispatch_token(),
        'apikey', private.get_supabase_apikey()
      ),
      body := jsonb_build_object('type', 'daily_enrichment')
    )$$
  );

  -- 2. snow-cover-refresh-job
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'snow-cover-refresh-job') THEN
    PERFORM cron.unschedule('snow-cover-refresh-job');
  END IF;

  PERFORM cron.schedule(
    'snow-cover-refresh-job',
    '30 0 * * *',
    $$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || private.get_job_dispatch_token(),
        'apikey', private.get_supabase_apikey()
      ),
      body := jsonb_build_object('type', 'snow_cover_refresh', 'hazard_type', 'avalanche')
    )$$
  );

  -- 3. recent-activity-refresh-job
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'recent-activity-refresh-job') THEN
    PERFORM cron.unschedule('recent-activity-refresh-job');
  END IF;

  PERFORM cron.schedule(
    'recent-activity-refresh-job',
    '0 1 * * *',
    $$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || private.get_job_dispatch_token(),
        'apikey', private.get_supabase_apikey()
      ),
      body := jsonb_build_object('type', 'recent_activity_refresh', 'hazard_type', 'avalanche')
    )$$
  );

  -- 4. weekly-evaluation-job
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'weekly-evaluation-job') THEN
    PERFORM cron.unschedule('weekly-evaluation-job');
  END IF;

  PERFORM cron.schedule(
    'weekly-evaluation-job',
    '0 3 * * 0',
    $$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || private.get_job_dispatch_token(),
        'apikey', private.get_supabase_apikey()
      ),
      body := jsonb_build_object('type', 'run_evaluation', 'hazard_type', 'avalanche')
    )$$
  );

  -- 5. forecast-grid-precompute-job
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'forecast-grid-precompute-job') THEN
    PERFORM cron.unschedule('forecast-grid-precompute-job');
  END IF;

  PERFORM cron.schedule(
    'forecast-grid-precompute-job',
    '30 1 * * *',
    $$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || private.get_job_dispatch_token(),
        'apikey', private.get_supabase_apikey()
      ),
      body := jsonb_build_object(
        'type', 'forecast_grid_precompute',
        'hazard_type', 'avalanche',
        'artifact_dir', '/artifacts/20260430T165417Z',
        'forecast_hours', 72,
        'grid_size', 20
      )
    )$$
  );

  -- 6. weekly-model-optimization-job
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'weekly-model-optimization-job') THEN
    PERFORM cron.unschedule('weekly-model-optimization-job');
  END IF;

  PERFORM cron.schedule(
    'weekly-model-optimization-job',
    '0 2 * * 0',
    $$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || private.get_job_dispatch_token(),
        'apikey', private.get_supabase_apikey()
      ),
      body := jsonb_build_object('type', 'model_optimization', 'hazard_type', 'avalanche')
    )$$
  );

END $cron$;
