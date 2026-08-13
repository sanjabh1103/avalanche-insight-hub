-- Bound stale forecast-run deletion so a backlog cannot become one large cron
-- transaction. This replaces the same-signature retention function introduced
-- by 20260810170000; the cron call remains cleanup_forecast_retention().

CREATE OR REPLACE FUNCTION public.cleanup_forecast_retention(
  p_cutoff interval DEFAULT interval '14 days',
  p_shap_batch integer DEFAULT 5000,
  p_grid_batch integer DEFAULT 500
)
RETURNS TABLE (
  shap_deleted bigint,
  grids_deleted bigint,
  runs_deleted bigint,
  database_bytes_after bigint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  deleted_shap bigint := 0;
  deleted_grids bigint := 0;
  deleted_runs bigint := 0;
BEGIN
  IF p_cutoff < interval '1 day' OR p_cutoff > interval '90 days' THEN
    RAISE EXCEPTION 'p_cutoff must be between 1 and 90 days';
  END IF;
  IF p_shap_batch < 1 OR p_shap_batch > 5000 THEN
    RAISE EXCEPTION 'p_shap_batch must be between 1 and 5000';
  END IF;
  IF p_grid_batch < 1 OR p_grid_batch > 500 THEN
    RAISE EXCEPTION 'p_grid_batch must be between 1 and 500';
  END IF;

  WITH eligible AS (
    SELECT s.id
    FROM public.forecast_shap_cache AS s
    JOIN public.forecast_grids AS g ON g.id = s.forecast_grid_id
    WHERE g.created_at < now() - p_cutoff
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_outcomes AS o
        WHERE o.forecast_grid_id = g.id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_runs AS r
        WHERE r.compatibility_forecast_grid_id = g.id
          AND (r.active OR r.publication_status IN ('published', 'ready'))
      )
    ORDER BY s.created_at, s.id
    LIMIT p_shap_batch
  )
  DELETE FROM public.forecast_shap_cache AS s
  WHERE s.id IN (SELECT id FROM eligible);
  GET DIAGNOSTICS deleted_shap = ROW_COUNT;

  WITH eligible AS (
    SELECT g.id
    FROM public.forecast_grids AS g
    WHERE g.created_at < now() - p_cutoff
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_shap_cache AS s
        WHERE s.forecast_grid_id = g.id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_outcomes AS o
        WHERE o.forecast_grid_id = g.id
      )
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_runs AS r
        WHERE r.compatibility_forecast_grid_id = g.id
          AND (r.active OR r.publication_status IN ('published', 'ready'))
      )
    ORDER BY g.created_at, g.id
    LIMIT p_grid_batch
  )
  DELETE FROM public.forecast_grids AS g
  WHERE g.id IN (SELECT id FROM eligible);
  GET DIAGNOSTICS deleted_grids = ROW_COUNT;

  WITH eligible_runs AS (
    SELECT r.id
    FROM public.forecast_runs AS r
    WHERE r.created_at < now() - p_cutoff
      AND r.active = FALSE
      AND r.status <> 'ready'
      AND r.publication_status NOT IN ('validated', 'published')
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_outcomes AS o
        WHERE o.forecast_grid_id = r.compatibility_forecast_grid_id
      )
    ORDER BY r.created_at, r.id
    LIMIT 500
  )
  DELETE FROM public.forecast_runs AS r
  WHERE r.id IN (SELECT id FROM eligible_runs);
  GET DIAGNOSTICS deleted_runs = ROW_COUNT;

  RETURN QUERY
  SELECT
    deleted_shap,
    deleted_grids,
    deleted_runs,
    pg_database_size(current_database())::bigint;
END;
$$;

COMMENT ON FUNCTION public.cleanup_forecast_retention(interval, integer, integer) IS
  'Deletes bounded stale SHAP/grid/run data in bounded batches while preserving active, ready, validated, published, and outcome-referenced evidence.';
