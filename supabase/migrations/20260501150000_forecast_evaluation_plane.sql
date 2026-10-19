-- Phase 2 foundation: label snapshots, hindcast runs, and calibration reports.

CREATE TABLE IF NOT EXISTS public.label_snapshots (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  snapshot_id TEXT NOT NULL UNIQUE,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  dataset_snapshot_id TEXT NOT NULL,
  name TEXT,
  source_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_composition JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence_decay_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
  coverage_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  region_coverage JSONB NOT NULL DEFAULT '[]'::jsonb,
  season_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
  provenance_notes TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT label_snapshots_status_check CHECK (status IN ('draft', 'active', 'archived'))
);

CREATE INDEX IF NOT EXISTS label_snapshots_dataset_idx
  ON public.label_snapshots (dataset_snapshot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.hindcast_runs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  run_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  label_snapshot_id UUID NOT NULL REFERENCES public.label_snapshots(id) ON DELETE RESTRICT,
  dataset_snapshot_id TEXT NOT NULL,
  calibration_profile_version TEXT,
  source_composition JSONB NOT NULL DEFAULT '{}'::jsonb,
  region_coverage JSONB NOT NULL DEFAULT '[]'::jsonb,
  region_keys TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  forecast_horizons INTEGER[] NOT NULL DEFAULT ARRAY[]::INTEGER[],
  eval_window_start DATE NOT NULL,
  eval_window_end DATE NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  summary_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  artifact_manifest_ref TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT hindcast_runs_status_check CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  CONSTRAINT hindcast_runs_window_check CHECK (eval_window_end >= eval_window_start)
);

CREATE INDEX IF NOT EXISTS hindcast_runs_model_idx
  ON public.hindcast_runs (model_version, created_at DESC);

CREATE INDEX IF NOT EXISTS hindcast_runs_label_snapshot_idx
  ON public.hindcast_runs (label_snapshot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.calibration_reports (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  hindcast_run_id UUID NOT NULL REFERENCES public.hindcast_runs(id) ON DELETE CASCADE,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  model_version TEXT NOT NULL,
  label_snapshot_id UUID NOT NULL REFERENCES public.label_snapshots(id) ON DELETE RESTRICT,
  dataset_snapshot_id TEXT NOT NULL,
  calibration_profile_version TEXT,
  region_key TEXT,
  season_window TEXT,
  forecast_horizon INTEGER,
  calibration_method TEXT NOT NULL DEFAULT 'isotonic',
  metric_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  reliability_curve JSONB NOT NULL DEFAULT '[]'::jsonb,
  uncertainty_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
  artifact_ref TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT calibration_reports_horizon_check CHECK (forecast_horizon IS NULL OR forecast_horizon >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS calibration_reports_slice_idx
  ON public.calibration_reports (
    hindcast_run_id,
    COALESCE(region_key, ''),
    COALESCE(season_window, ''),
    COALESCE(forecast_horizon, -1)
  );

CREATE OR REPLACE FUNCTION public.set_phase2_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_label_snapshots_updated_at ON public.label_snapshots;
CREATE TRIGGER set_label_snapshots_updated_at
BEFORE UPDATE ON public.label_snapshots
FOR EACH ROW
EXECUTE FUNCTION public.set_phase2_updated_at();

DROP TRIGGER IF EXISTS set_hindcast_runs_updated_at ON public.hindcast_runs;
CREATE TRIGGER set_hindcast_runs_updated_at
BEFORE UPDATE ON public.hindcast_runs
FOR EACH ROW
EXECUTE FUNCTION public.set_phase2_updated_at();

DROP TRIGGER IF EXISTS set_calibration_reports_updated_at ON public.calibration_reports;
CREATE TRIGGER set_calibration_reports_updated_at
BEFORE UPDATE ON public.calibration_reports
FOR EACH ROW
EXECUTE FUNCTION public.set_phase2_updated_at();

ALTER TABLE public.label_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hindcast_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calibration_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view label snapshots" ON public.label_snapshots;
DROP POLICY IF EXISTS "Service role can manage label snapshots" ON public.label_snapshots;
CREATE POLICY "Anyone can view label snapshots" ON public.label_snapshots FOR SELECT USING (true);
CREATE POLICY "Service role can manage label snapshots" ON public.label_snapshots FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Anyone can view hindcast runs" ON public.hindcast_runs;
DROP POLICY IF EXISTS "Service role can manage hindcast runs" ON public.hindcast_runs;
CREATE POLICY "Anyone can view hindcast runs" ON public.hindcast_runs FOR SELECT USING (true);
CREATE POLICY "Service role can manage hindcast runs" ON public.hindcast_runs FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Anyone can view calibration reports" ON public.calibration_reports;
DROP POLICY IF EXISTS "Service role can manage calibration reports" ON public.calibration_reports;
CREATE POLICY "Anyone can view calibration reports" ON public.calibration_reports FOR SELECT USING (true);
CREATE POLICY "Service role can manage calibration reports" ON public.calibration_reports FOR ALL USING (auth.role() = 'service_role');
