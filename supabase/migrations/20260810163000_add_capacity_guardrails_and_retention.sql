-- Free-tier capacity guardrails and bounded forecast retention.
--
-- Supabase's database read-only threshold is lower than the 1 GiB Storage
-- allowance, so operators need both measurements. The cleanup function is
-- deliberately bounded and never removes active/published grids or grids
-- referenced by labelled outcomes.

CREATE OR REPLACE FUNCTION public.get_capacity_snapshot()
RETURNS TABLE (
  database_bytes bigint,
  database_limit_bytes bigint,
  storage_bytes bigint,
  storage_limit_bytes bigint,
  database_status text,
  storage_status text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public, storage
AS $$
WITH storage_totals AS (
  SELECT COALESCE(
    SUM(
      CASE
        WHEN (metadata->>'size') ~ '^[0-9]+$' THEN (metadata->>'size')::bigint
        ELSE 0
      END
    ),
    0
  )::bigint AS bytes
  FROM storage.objects
), measured AS (
  SELECT
    pg_database_size(current_database())::bigint AS db_bytes,
    storage_totals.bytes AS object_bytes
  FROM storage_totals
)
SELECT
  db_bytes,
  524288000::bigint,
  object_bytes,
  1073741824::bigint,
  CASE
    WHEN db_bytes >= 471859200 THEN 'emergency'
    WHEN db_bytes >= 445644800 THEN 'blocked'
    WHEN db_bytes >= 367001600 THEN 'warning'
    ELSE 'ok'
  END,
  CASE
    WHEN object_bytes >= 996147200 THEN 'emergency'
    WHEN object_bytes >= 858993459 THEN 'warning'
    ELSE 'ok'
  END
FROM measured;
$$;

COMMENT ON FUNCTION public.get_capacity_snapshot() IS
  'Returns database and Storage usage with conservative free-tier guardrail statuses.';

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

  -- Delete only grids whose SHAP rows are fully drained in this invocation.
  -- This keeps each cron invocation bounded even if a single grid is large.
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

  DELETE FROM public.forecast_runs
  WHERE created_at < now() - p_cutoff
    AND active = FALSE;
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
  'Deletes bounded stale SHAP/grid data while preserving active, published, and outcome-referenced evidence.';

REVOKE ALL ON FUNCTION public.get_capacity_snapshot() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cleanup_forecast_retention(interval, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.get_capacity_snapshot() TO service_role;
GRANT EXECUTE ON FUNCTION public.cleanup_forecast_retention(interval, integer, integer) TO service_role;

DO $cron$
BEGIN
  IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'forecast-retention-cleanup') THEN
    PERFORM cron.unschedule('forecast-retention-cleanup');
  END IF;
  PERFORM cron.schedule(
    'forecast-retention-cleanup',
    '0 3 * * *',
    $job$SELECT public.cleanup_forecast_retention()$job$
  );
END;
$cron$;
