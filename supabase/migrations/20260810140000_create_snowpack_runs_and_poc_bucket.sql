-- Phase 2: snowpack_runs table + poc-artifacts storage bucket.
--
-- This migration creates the control-plane table that tracks SNOWPACK POC
-- execution runs triggered via Edge Functions and executed on GitHub Actions.
--
-- The table is written to by:
--   1. Edge Function trigger-poc-snowpack (INSERT with status='queued')
--   2. GitHub Actions workflow (PATCH status transitions via REST API)
--   3. Frontend (SELECT for status polling)
--
-- Pattern follows forecast_runs (20260501123000) and model-artifacts bucket
-- (20260627150000).

-- ──────────────────────────────────────────────────────────────────────────
-- Storage bucket for POC artifacts (private — service_role only)
-- ──────────────────────────────────────────────────────────────────────────
INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'poc-artifacts',
  'poc-artifacts',
  FALSE,
  104857600,  -- 100 MB per file
  ARRAY['application/octet-stream', 'application/json', 'application/gzip', 'text/plain']
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- ──────────────────────────────────────────────────────────────────────────
-- snowpack_runs table
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.snowpack_runs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'building', 'running', 'completed', 'failed', 'verified')),
  region_key TEXT NOT NULL,
  elevation_band TEXT NOT NULL,
  horizon_hours INTEGER NOT NULL CHECK (horizon_hours > 0),
  poc_mode BOOLEAN NOT NULL DEFAULT FALSE,
  toolchain_manifest_id TEXT,
  image_id TEXT,
  image_archive_sha256 TEXT,
  bundle_storage_ref TEXT,
  manifest_storage_ref TEXT,
  producer_gate_passed BOOLEAN NOT NULL DEFAULT FALSE,
  consumer_gate_passed BOOLEAN NOT NULL DEFAULT FALSE,
  error TEXT,
  github_run_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS snowpack_runs_status_idx
  ON public.snowpack_runs (status);
CREATE INDEX IF NOT EXISTS snowpack_runs_region_created_idx
  ON public.snowpack_runs (region_key, created_at DESC);
CREATE INDEX IF NOT EXISTS snowpack_runs_poc_mode_idx
  ON public.snowpack_runs (poc_mode) WHERE poc_mode = TRUE;

-- ──────────────────────────────────────────────────────────────────────────
-- RLS policies (same pattern as forecast_runs)
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE public.snowpack_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view snowpack runs" ON public.snowpack_runs;
DROP POLICY IF EXISTS "Service role can manage snowpack runs" ON public.snowpack_runs;
CREATE POLICY "Anyone can view snowpack runs" ON public.snowpack_runs
  FOR SELECT USING (true);
CREATE POLICY "Service role can manage snowpack runs" ON public.snowpack_runs
  FOR ALL USING (auth.role() = 'service_role');

-- ──────────────────────────────────────────────────────────────────────────
-- updated_at trigger (same pattern as forecast_runs)
-- ──────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_snowpack_runs_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_snowpack_runs_updated_at ON public.snowpack_runs;
CREATE TRIGGER set_snowpack_runs_updated_at
BEFORE UPDATE ON public.snowpack_runs
FOR EACH ROW
EXECUTE FUNCTION public.set_snowpack_runs_updated_at();

-- ──────────────────────────────────────────────────────────────────────────
-- Cleanup: stale runs older than 30 days in non-terminal status
-- ──────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.cleanup_stale_snowpack_runs()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE public.snowpack_runs
    SET status = 'failed', error = 'Stale run — no status update within 30 days'
    WHERE status NOT IN ('completed', 'failed', 'verified')
      AND created_at < now() - INTERVAL '30 days';
END;
$$;
