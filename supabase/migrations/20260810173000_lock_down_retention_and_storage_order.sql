-- Lock down capacity/retention helpers and keep database cleanup behind the
-- Storage deletion boundary.  The Storage worker and pg_cron run at the same
-- time; if the database job wins the race, retaining rows until their storage
-- references disappear prevents an orphaned-object cleanup from losing its
-- inventory.

REVOKE ALL ON FUNCTION public.get_capacity_snapshot() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.cleanup_stale_snowpack_runs() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.cleanup_forecast_retention(interval, integer, integer) FROM PUBLIC, anon, authenticated;

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

  PERFORM public.cleanup_stale_snowpack_runs();

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
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_runs AS r
        WHERE r.compatibility_forecast_grid_id = g.id
          AND EXISTS (
            SELECT 1
            FROM storage.objects AS o
            WHERE o.bucket_id || '/' || o.name IN (
              SELECT h.storage_ref
              FROM public.forecast_run_hours AS h
              WHERE h.forecast_run_id = r.id
                AND h.storage_ref IS NOT NULL
              UNION ALL
              SELECT r.manifest_storage_ref
              WHERE r.manifest_storage_ref IS NOT NULL
              UNION ALL
              SELECT r.runout_storage_ref
              WHERE r.runout_storage_ref IS NOT NULL
            )
          )
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
      AND NOT EXISTS (
        SELECT 1
        FROM public.forecast_runs AS r
        WHERE r.compatibility_forecast_grid_id = g.id
          AND EXISTS (
            SELECT 1
            FROM storage.objects AS o
            WHERE o.bucket_id || '/' || o.name IN (
              SELECT h.storage_ref
              FROM public.forecast_run_hours AS h
              WHERE h.forecast_run_id = r.id
                AND h.storage_ref IS NOT NULL
              UNION ALL
              SELECT r.manifest_storage_ref
              WHERE r.manifest_storage_ref IS NOT NULL
              UNION ALL
              SELECT r.runout_storage_ref
              WHERE r.runout_storage_ref IS NOT NULL
            )
          )
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
      AND NOT EXISTS (
        SELECT 1
        FROM storage.objects AS o
        WHERE o.bucket_id || '/' || o.name IN (
          SELECT h.storage_ref
          FROM public.forecast_run_hours AS h
          WHERE h.forecast_run_id = r.id
            AND h.storage_ref IS NOT NULL
          UNION ALL
          SELECT r.manifest_storage_ref
          WHERE r.manifest_storage_ref IS NOT NULL
          UNION ALL
          SELECT r.runout_storage_ref
          WHERE r.runout_storage_ref IS NOT NULL
        )
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
  'Deletes bounded stale data while preserving published evidence and rows whose Storage references remain.';

GRANT EXECUTE ON FUNCTION public.get_capacity_snapshot() TO service_role;
GRANT EXECUTE ON FUNCTION public.cleanup_stale_snowpack_runs() TO service_role;
GRANT EXECUTE ON FUNCTION public.cleanup_forecast_retention(interval, integer, integer) TO service_role;
