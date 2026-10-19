ALTER TABLE public.feature_completeness_log
  ALTER COLUMN forecast_id DROP NOT NULL;

ALTER TABLE public.feature_completeness_log
  ADD COLUMN IF NOT EXISTS forecast_grid_id uuid REFERENCES public.forecast_grids(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS forecast_run_id uuid REFERENCES public.forecast_runs(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_feature_completeness_log_forecast_grid_id
  ON public.feature_completeness_log (forecast_grid_id);

CREATE INDEX IF NOT EXISTS idx_feature_completeness_log_forecast_run_id
  ON public.feature_completeness_log (forecast_run_id);

ALTER TABLE public.model_status
  ADD COLUMN IF NOT EXISTS stability_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS drift_mode_state text,
  ADD COLUMN IF NOT EXISTS latest_benchmark_summary jsonb NOT NULL DEFAULT '{}'::jsonb;
