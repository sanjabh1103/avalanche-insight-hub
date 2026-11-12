ALTER TABLE public.forecast_grids
  ADD COLUMN IF NOT EXISTS hourly_grids JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.forecast_grids
  DROP CONSTRAINT IF EXISTS forecast_grids_status_check;

ALTER TABLE public.forecast_grids
  ADD CONSTRAINT forecast_grids_status_check
  CHECK (status IN ('queued', 'running', 'ready', 'partial', 'stale', 'failed', 'superseded'));

ALTER TABLE public.model_status
  ADD COLUMN IF NOT EXISTS pss_reported DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS pss_gate_passed BOOLEAN,
  ADD COLUMN IF NOT EXISTS promotion_gate_passed BOOLEAN,
  ADD COLUMN IF NOT EXISTS shadow_mode_active BOOLEAN,
  ADD COLUMN IF NOT EXISTS active_model_type TEXT,
  ADD COLUMN IF NOT EXISTS active_model_version TEXT;
