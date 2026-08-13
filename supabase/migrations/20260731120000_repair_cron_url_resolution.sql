-- Repair the parameterized cron URL helper without rewriting the migration that
-- originally introduced it. The active project is the only permitted target.

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
    RAISE EXCEPTION 'app.settings.supabase_url must target the active Supabase project';
  END IF;

  RETURN configured_url;
END;
$$;

DO $$
BEGIN
  IF private.get_supabase_url() <> 'https://eyyellmffzzujyssaayb.supabase.co' THEN
    RAISE EXCEPTION 'Supabase URL helper did not resolve to the active project';
  END IF;
END;
$$;
