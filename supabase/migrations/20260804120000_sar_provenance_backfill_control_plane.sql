-- SAR Provenance Backfill Control Plane
-- Creates run and chunk tracking tables for reproducible, resumable SAR backfill operations.
-- Track B — Open-source provenance and label evidence.
--
-- These tables track backfill runs (one per execution) and chunks (one per region/window pair).
-- Every event inserted by a backfill run references its backfill_run_id for audit and rollback.

CREATE TABLE IF NOT EXISTS public.sar_provenance_backfill_runs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending',
  start_date TIMESTAMPTZ NOT NULL,
  end_date TIMESTAMPTZ NOT NULL,
  chunk_days INT NOT NULL DEFAULT 7,
  regions TEXT[] NOT NULL DEFAULT '{}'::text[],
  algorithm_version TEXT,
  code_sha TEXT,
  dependency_hash TEXT,
  extractor_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  total_chunks INT NOT NULL DEFAULT 0,
  completed_chunks INT NOT NULL DEFAULT 0,
  failed_chunks INT NOT NULL DEFAULT 0,
  total_detections INT NOT NULL DEFAULT 0,
  total_inserted INT NOT NULL DEFAULT 0,
  total_eligible INT NOT NULL DEFAULT 0,
  total_lineage_rows INT NOT NULL DEFAULT 0,
  total_artifact_rows INT NOT NULL DEFAULT 0,
  lineage_failures INT NOT NULL DEFAULT 0,
  artifact_failures INT NOT NULL DEFAULT 0,
  error_details JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT valid_run_status CHECK (
    status IN ('pending', 'running', 'completed', 'partial_failed', 'failed', 'rolled_back')
  )
);

ALTER TABLE public.sar_provenance_backfill_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view sar provenance runs" ON public.sar_provenance_backfill_runs;
DROP POLICY IF EXISTS "Service role can manage sar provenance runs" ON public.sar_provenance_backfill_runs;
CREATE POLICY "Anyone can view sar provenance runs" ON public.sar_provenance_backfill_runs FOR SELECT USING (true);
CREATE POLICY "Service role can manage sar provenance runs" ON public.sar_provenance_backfill_runs FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_sar_provenance_runs_status
  ON public.sar_provenance_backfill_runs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sar_provenance_runs_run_id
  ON public.sar_provenance_backfill_runs (run_id);


CREATE TABLE IF NOT EXISTS public.sar_provenance_backfill_chunks (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES public.sar_provenance_backfill_runs(run_id) ON DELETE CASCADE,
  region_key TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  scene_count INT NOT NULL DEFAULT 0,
  detection_count INT NOT NULL DEFAULT 0,
  inserted_count INT NOT NULL DEFAULT 0,
  eligible_count INT NOT NULL DEFAULT 0,
  lineage_persisted BOOLEAN NOT NULL DEFAULT FALSE,
  artifacts_persisted BOOLEAN NOT NULL DEFAULT FALSE,
  scene_ids TEXT[] NOT NULL DEFAULT '{}'::text[],
  scene_lineage_hash TEXT,
  event_fingerprints TEXT[] NOT NULL DEFAULT '{}'::text[],
  error TEXT,
  retry_count INT NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT valid_chunk_status CHECK (
    status IN ('pending', 'running', 'completed', 'failed', 'skipped')
  ),
  CONSTRAINT valid_chunk_window CHECK (window_end > window_start)
);

ALTER TABLE public.sar_provenance_backfill_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view sar provenance chunks" ON public.sar_provenance_backfill_chunks;
DROP POLICY IF EXISTS "Service role can manage sar provenance chunks" ON public.sar_provenance_backfill_chunks;
CREATE POLICY "Anyone can view sar provenance chunks" ON public.sar_provenance_backfill_chunks FOR SELECT USING (true);
CREATE POLICY "Service role can manage sar provenance chunks" ON public.sar_provenance_backfill_chunks FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_sar_provenance_chunks_run_region
  ON public.sar_provenance_backfill_chunks (run_id, region_key, window_start);
CREATE INDEX IF NOT EXISTS idx_sar_provenance_chunks_status
  ON public.sar_provenance_backfill_chunks (status);
CREATE INDEX IF NOT EXISTS idx_sar_provenance_chunks_fingerprints
  ON public.sar_provenance_backfill_chunks USING GIN (event_fingerprints);


-- Add backfill_run_id column to avalanche_events for cohort tracking.
-- This allows events to be grouped by their originating backfill run for audit and rollback.
ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS backfill_run_id TEXT;

CREATE INDEX IF NOT EXISTS idx_avalanche_events_backfill_run_id
  ON public.avalanche_events (backfill_run_id)
  WHERE backfill_run_id IS NOT NULL;
