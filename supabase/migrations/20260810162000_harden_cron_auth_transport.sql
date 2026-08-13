-- Route pg_cron requests through the Supabase gateway-safe authentication
-- contract. The gateway receives a valid anon JWT in Authorization, while
-- the narrow private dispatch token travels in x-job-token and is checked by
-- authorizeJobRequest inside the function.

CREATE SCHEMA IF NOT EXISTS private;

CREATE OR REPLACE FUNCTION private.get_supabase_url()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $$
DECLARE
  configured_url text := nullif(btrim(current_setting('app.settings.supabase_url', true)), '');
  expected_url CONSTANT text := 'https://eyyellmffzzujyssaayb.supabase.co';
BEGIN
  IF configured_url IS NULL THEN
    RETURN expected_url;
  END IF;

  configured_url := regexp_replace(configured_url, '/+$', '');
  IF configured_url <> expected_url THEN
    RAISE EXCEPTION 'app.settings.supabase_url must target the canonical active Supabase project';
  END IF;
  RETURN configured_url;
END;
$$;

CREATE OR REPLACE FUNCTION private.get_job_dispatch_token()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private, vault
AS $$
DECLARE
  configured_token text := nullif(btrim(current_setting('app.settings.job_dispatch_token', true)), '');
  vault_token text;
BEGIN
  IF configured_token IS NOT NULL THEN
    RETURN configured_token;
  END IF;

  SELECT decrypted_secret
    INTO vault_token
    FROM vault.decrypted_secrets
   WHERE name = 'job_dispatch_token'
   LIMIT 1;

  IF nullif(btrim(vault_token), '') IS NULL THEN
    RAISE EXCEPTION 'Missing job dispatch token. Set app.settings.job_dispatch_token or vault secret job_dispatch_token.';
  END IF;
  RETURN vault_token;
END;
$$;

CREATE OR REPLACE FUNCTION private.get_supabase_apikey()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private, vault
AS $$
DECLARE
  vault_key text;
  configured_key text := nullif(btrim(current_setting('app.settings.supabase_anon_key', true)), '');
BEGIN
  SELECT decrypted_secret
    INTO vault_key
    FROM vault.decrypted_secrets
   WHERE name = 'anon_key'
   LIMIT 1;

  IF nullif(btrim(vault_key), '') IS NOT NULL THEN
    RETURN vault_key;
  END IF;
  IF configured_key IS NOT NULL THEN
    RETURN configured_key;
  END IF;
  RAISE EXCEPTION 'Missing Supabase anon key. Set vault secret anon_key or app.settings.supabase_anon_key.';
END;
$$;

CREATE OR REPLACE FUNCTION private.cron_http_headers()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $$
DECLARE
  anon_key text := private.get_supabase_apikey();
BEGIN
  RETURN jsonb_build_object(
    'Content-Type', 'application/json',
    'Authorization', 'Bearer ' || anon_key,
    'apikey', anon_key,
    'x-job-token', private.get_job_dispatch_token()
  );
END;
$$;

REVOKE ALL ON FUNCTION private.get_supabase_url() FROM PUBLIC;
REVOKE ALL ON FUNCTION private.get_job_dispatch_token() FROM PUBLIC;
REVOKE ALL ON FUNCTION private.get_supabase_apikey() FROM PUBLIC;
REVOKE ALL ON FUNCTION private.cron_http_headers() FROM PUBLIC;

DO $cron$
BEGIN
  IF private.get_supabase_url() <> 'https://eyyellmffzzujyssaayb.supabase.co' THEN
    RAISE EXCEPTION 'Supabase URL helper did not resolve to the canonical active project';
  END IF;

  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'daily-enrichment-job') THEN
    PERFORM cron.unschedule('daily-enrichment-job');
  END IF;
  PERFORM cron.schedule(
    'daily-enrichment-job',
    '0 0 * * *',
    $job$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := private.cron_http_headers(),
      body := jsonb_build_object('type', 'daily_enrichment')
    )$job$
  );

  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'snow-cover-refresh-job') THEN
    PERFORM cron.unschedule('snow-cover-refresh-job');
  END IF;
  PERFORM cron.schedule(
    'snow-cover-refresh-job',
    '30 0 * * *',
    $job$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := private.cron_http_headers(),
      body := jsonb_build_object('type', 'snow_cover_refresh', 'hazard_type', 'avalanche')
    )$job$
  );

  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'recent-activity-refresh-job') THEN
    PERFORM cron.unschedule('recent-activity-refresh-job');
  END IF;
  PERFORM cron.schedule(
    'recent-activity-refresh-job',
    '0 1 * * *',
    $job$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := private.cron_http_headers(),
      body := jsonb_build_object('type', 'recent_activity_refresh', 'hazard_type', 'avalanche')
    )$job$
  );

  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'forecast-grid-precompute-job') THEN
    PERFORM cron.unschedule('forecast-grid-precompute-job');
  END IF;
  PERFORM cron.schedule(
    'forecast-grid-precompute-job',
    '30 1 * * *',
    $job$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := private.cron_http_headers(),
      body := jsonb_build_object(
        'type', 'forecast_grid_precompute',
        'hazard_type', 'avalanche',
        'artifact_dir', '/artifacts/20260430T165417Z',
        'forecast_hours', 72,
        'grid_size', 20
      )
    )$job$
  );

  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'weekly-model-optimization-job') THEN
    PERFORM cron.unschedule('weekly-model-optimization-job');
  END IF;
  PERFORM cron.schedule(
    'weekly-model-optimization-job',
    '0 2 * * 0',
    $job$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := private.cron_http_headers(),
      body := jsonb_build_object('type', 'model_optimization', 'hazard_type', 'avalanche')
    )$job$
  );

  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'weekly-evaluation-job') THEN
    PERFORM cron.unschedule('weekly-evaluation-job');
  END IF;
  PERFORM cron.schedule(
    'weekly-evaluation-job',
    '0 3 * * 0',
    $job$SELECT net.http_post(
      url := private.get_supabase_url() || '/functions/v1/trigger-job',
      headers := private.cron_http_headers(),
      body := jsonb_build_object('type', 'run_evaluation', 'hazard_type', 'avalanche')
    )$job$
  );
END;
$cron$;
