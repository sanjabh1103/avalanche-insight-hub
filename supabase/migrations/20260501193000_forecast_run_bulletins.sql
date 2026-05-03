ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS forecast_bulletins JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE OR REPLACE VIEW public.forecast_active_runs AS
SELECT
  id,
  hazard_type,
  region_key,
  region_name,
  forecast_date,
  issue_time,
  horizon_hours,
  grid_size,
  bbox,
  status,
  publication_status,
  manifest_storage_ref,
  runout_storage_ref,
  compatibility_forecast_grid_id,
  active,
  model_metadata,
  weather_summary,
  published_at,
  created_at,
  updated_at,
  forecast_bulletins
FROM public.forecast_runs
WHERE active = TRUE
  AND status = 'ready'
  AND publication_status = 'published';
