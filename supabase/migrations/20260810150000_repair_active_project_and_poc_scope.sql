-- Additive repair for the restored active project.
-- Do not rewrite 20260731120000: it is already applied history and still
-- contains the retired eyyellmffzzujyssaayb target.

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

ALTER TABLE public.snowpack_runs
  ADD COLUMN IF NOT EXISTS ensemble_members INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS decision_record_sha256 TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'snowpack_runs_ensemble_members_positive'
      AND conrelid = 'public.snowpack_runs'::regclass
  ) THEN
    ALTER TABLE public.snowpack_runs
      ADD CONSTRAINT snowpack_runs_ensemble_members_positive
      CHECK (ensemble_members > 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'snowpack_runs_poc_scope_check'
      AND conrelid = 'public.snowpack_runs'::regclass
  ) THEN
    ALTER TABLE public.snowpack_runs
      ADD CONSTRAINT snowpack_runs_poc_scope_check
      CHECK (
        NOT poc_mode
        OR (
          region_key = 'pir_panjal_nw_himalaya'
          AND elevation_band = 'middle'
          AND horizon_hours = 48
          AND ensemble_members = 1
          AND decision_record_sha256 ~ '^[0-9a-fA-F]{64}$'
        )
      );
  END IF;
END;
$$;

DO $$
BEGIN
  IF private.get_supabase_url() <> 'https://eyyellmffzzujyssaayb.supabase.co' THEN
    RAISE EXCEPTION 'Supabase URL helper did not resolve to the canonical active project';
  END IF;
END;
$$;
