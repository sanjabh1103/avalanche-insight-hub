-- Bridge async forecast_grids into forecast_outcomes without breaking legacy forecasts.

ALTER TABLE public.forecast_outcomes
  ALTER COLUMN forecast_id DROP NOT NULL;

ALTER TABLE public.forecast_outcomes
  ADD COLUMN IF NOT EXISTS forecast_grid_id uuid REFERENCES public.forecast_grids(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_forecast_grid
  ON public.forecast_outcomes (forecast_grid_id, forecast_hour)
  WHERE forecast_grid_id IS NOT NULL;

COMMENT ON COLUMN public.forecast_outcomes.forecast_grid_id IS
  'Nullable bridge to async forecast_grids rows. Legacy forecast_id remains for backwards compatibility.';
