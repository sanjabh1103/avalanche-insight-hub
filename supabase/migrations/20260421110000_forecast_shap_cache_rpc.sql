-- P1.2: Single-row RPC for the forecast_shap_cache UI lookup (2026-04-21)
-- The frontend fetches real TreeSHAP contributions per selected cell; an RPC
-- avoids N+1 REST queries and lets us expose a stable contract even if the
-- underlying table evolves.

CREATE OR REPLACE FUNCTION public.get_shap_for_cell(
  p_forecast_grid_id uuid,
  p_cell_row smallint,
  p_cell_col smallint,
  p_forecast_hour smallint DEFAULT 0
)
RETURNS TABLE (
  forecast_grid_id uuid,
  cell_row smallint,
  cell_col smallint,
  forecast_hour smallint,
  model_version text,
  top_features jsonb,
  shap_values jsonb,
  base_value double precision,
  dominant_driver text,
  created_at timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    forecast_grid_id,
    cell_row,
    cell_col,
    forecast_hour,
    model_version,
    top_features,
    shap_values,
    base_value,
    dominant_driver,
    created_at
  FROM public.forecast_shap_cache
  WHERE forecast_grid_id = p_forecast_grid_id
    AND cell_row = p_cell_row
    AND cell_col = p_cell_col
    AND forecast_hour = p_forecast_hour
  ORDER BY created_at DESC
  LIMIT 1;
$$;

COMMENT ON FUNCTION public.get_shap_for_cell IS
  'P1.2: UI-facing lookup for the latest TreeSHAP contribution row for a specific forecast_grid cell.';

GRANT EXECUTE ON FUNCTION public.get_shap_for_cell TO service_role, authenticated, anon;
