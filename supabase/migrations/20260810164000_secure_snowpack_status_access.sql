-- Keep internal POC metadata private while exposing only a safe status
-- projection to the public web app. The raw table contains errors, storage
-- object refs, image identifiers, and GitHub links that are not public API.

ALTER TABLE public.snowpack_runs
  ADD COLUMN IF NOT EXISTS github_run_id bigint;

DROP POLICY IF EXISTS "Anyone can view snowpack runs" ON public.snowpack_runs;

CREATE OR REPLACE FUNCTION public.list_snowpack_run_status(
  p_region_key text DEFAULT NULL,
  p_verified_only boolean DEFAULT FALSE,
  p_limit integer DEFAULT 10
)
RETURNS TABLE (
  run_id text,
  status text,
  region_key text,
  elevation_band text,
  horizon_hours integer,
  ensemble_members integer,
  poc_mode boolean,
  producer_gate_passed boolean,
  consumer_gate_passed boolean,
  created_at timestamptz,
  updated_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF p_limit < 1 OR p_limit > 50 THEN
    RAISE EXCEPTION 'p_limit must be between 1 and 50';
  END IF;
  IF p_region_key IS NOT NULL AND p_region_key <> 'pir_panjal_nw_himalaya' THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    r.run_id,
    r.status,
    r.region_key,
    r.elevation_band,
    r.horizon_hours,
    r.ensemble_members,
    r.poc_mode,
    r.producer_gate_passed,
    r.consumer_gate_passed,
    r.created_at,
    r.updated_at
  FROM public.snowpack_runs AS r
  WHERE r.poc_mode
    AND r.region_key = 'pir_panjal_nw_himalaya'
    AND (NOT p_verified_only OR (
      r.status = 'verified'
      AND r.producer_gate_passed
      AND r.consumer_gate_passed
    ))
  ORDER BY r.created_at DESC
  LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_snowpack_run_status(p_run_id text)
RETURNS TABLE (
  run_id text,
  status text,
  region_key text,
  elevation_band text,
  horizon_hours integer,
  ensemble_members integer,
  poc_mode boolean,
  producer_gate_passed boolean,
  consumer_gate_passed boolean,
  created_at timestamptz,
  updated_at timestamptz
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT
    r.run_id,
    r.status,
    r.region_key,
    r.elevation_band,
    r.horizon_hours,
    r.ensemble_members,
    r.poc_mode,
    r.producer_gate_passed,
    r.consumer_gate_passed,
    r.created_at,
    r.updated_at
  FROM public.snowpack_runs AS r
  WHERE r.run_id = p_run_id
    AND r.poc_mode
    AND r.region_key = 'pir_panjal_nw_himalaya';
$$;

REVOKE ALL ON FUNCTION public.list_snowpack_run_status(text, boolean, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_snowpack_run_status(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.list_snowpack_run_status(text, boolean, integer) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_snowpack_run_status(text) TO anon, authenticated, service_role;
