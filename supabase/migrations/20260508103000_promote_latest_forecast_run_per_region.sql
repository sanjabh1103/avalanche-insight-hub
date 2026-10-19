-- MVP readiness hardening: only one active published run should represent a
-- hazard/region at a time. Older dates remain queryable, but they should not
-- stay active after a newer run is promoted.

WITH ranked_active_runs AS (
  SELECT
    id,
    row_number() OVER (
      PARTITION BY hazard_type, region_key
      ORDER BY published_at DESC NULLS LAST, created_at DESC
    ) AS active_rank
  FROM public.forecast_runs
  WHERE active = TRUE
)
UPDATE public.forecast_runs AS forecast_run
   SET active = FALSE,
       status = CASE
         WHEN forecast_run.status = 'ready' THEN 'superseded'
         ELSE forecast_run.status
       END
  FROM ranked_active_runs
 WHERE forecast_run.id = ranked_active_runs.id
   AND ranked_active_runs.active_rank > 1;

DROP INDEX IF EXISTS forecast_runs_active_idx;

CREATE UNIQUE INDEX IF NOT EXISTS forecast_runs_active_region_idx
  ON public.forecast_runs (hazard_type, region_key)
  WHERE active = TRUE;

CREATE OR REPLACE FUNCTION public.promote_forecast_run(p_forecast_run_id UUID)
RETURNS public.forecast_runs
LANGUAGE plpgsql
AS $$
DECLARE
  target_row public.forecast_runs%ROWTYPE;
BEGIN
  SELECT *
    INTO target_row
  FROM public.forecast_runs
  WHERE id = p_forecast_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'forecast_run % not found', p_forecast_run_id;
  END IF;

  UPDATE public.forecast_runs
     SET active = FALSE,
         status = CASE
           WHEN id = p_forecast_run_id THEN status
           WHEN status = 'ready' THEN 'superseded'
           ELSE status
         END
   WHERE hazard_type = target_row.hazard_type
     AND region_key = target_row.region_key
     AND active = TRUE
     AND id <> p_forecast_run_id;

  UPDATE public.forecast_runs
     SET active = TRUE,
         status = 'ready',
         publication_status = 'published',
         published_at = now()
   WHERE id = p_forecast_run_id
   RETURNING * INTO target_row;

  RETURN target_row;
END;
$$;
