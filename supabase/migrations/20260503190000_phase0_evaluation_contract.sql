-- Phase 0 evaluation contract hardening for MVP post-demo roadmap.
-- Persists slice metadata in forecast_outcomes and carries training
-- eligibility reasons through the labeler RPC for auditability.

ALTER TABLE public.forecast_outcomes
  ADD COLUMN IF NOT EXISTS cell_elevation_m double precision,
  ADD COLUMN IF NOT EXISTS sar_coverage_state text,
  ADD COLUMN IF NOT EXISTS dry_wet_domain text,
  ADD COLUMN IF NOT EXISTS problem_slug text,
  ADD COLUMN IF NOT EXISTS training_eligible_reason text;

CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_eval_slice_fields
  ON public.forecast_outcomes (
    hazard_type,
    created_at DESC,
    sar_coverage_state,
    dry_wet_domain,
    problem_slug
  );

COMMENT ON COLUMN public.forecast_outcomes.cell_elevation_m IS
  'Persisted terrain elevation for the labeled forecast cell so evaluation slices do not infer elevation from grid row.';
COMMENT ON COLUMN public.forecast_outcomes.sar_coverage_state IS
  'Forecast-cell SAR coverage state propagated from coverage_flags for evaluation slices.';
COMMENT ON COLUMN public.forecast_outcomes.dry_wet_domain IS
  'Forecast-cell wet/dry domain from the avalanche problem classifier.';
COMMENT ON COLUMN public.forecast_outcomes.problem_slug IS
  'Forecast-cell avalanche problem slug from the problem classifier.';
COMMENT ON COLUMN public.forecast_outcomes.training_eligible_reason IS
  'Matched-event training eligibility reason preserved for evaluation and audits.';

DROP FUNCTION IF EXISTS public.fetch_labeler_events(
  text,
  timestamptz,
  timestamptz,
  double precision,
  double precision,
  double precision,
  double precision,
  integer,
  integer
);

CREATE OR REPLACE FUNCTION public.fetch_labeler_events(
  p_hazard_type text,
  p_window_start timestamptz,
  p_window_end timestamptz,
  p_bbox_min_lng double precision,
  p_bbox_min_lat double precision,
  p_bbox_max_lng double precision,
  p_bbox_max_lat double precision,
  p_min_verification_rank integer DEFAULT 0,
  p_limit integer DEFAULT 200
)
RETURNS TABLE (
  id uuid,
  "timestamp" timestamptz,
  severity integer,
  verification_status text,
  elevation_m double precision,
  label_role text,
  training_eligible_reason text,
  lng double precision,
  lat double precision
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  RETURN QUERY
  WITH ranked AS (
    SELECT
      e.id,
      e.timestamp,
      e.severity,
      e.verification_status::text AS verification_status,
      e.elevation_m,
      e.label_role::text AS label_role,
      e.training_eligible_reason,
      extensions.ST_X(e.location::extensions.geometry) AS lng,
      extensions.ST_Y(e.location::extensions.geometry) AS lat,
      CASE e.verification_status::text
        WHEN 'expert_verified' THEN 3
        WHEN 'verified' THEN 2
        WHEN 'weak' THEN 1
        ELSE 0
      END AS verification_rank
    FROM public.avalanche_events e
    WHERE e.hazard_type::text = p_hazard_type
      AND e.timestamp >= p_window_start
      AND e.timestamp <= p_window_end
      AND (e.label_role IS NULL OR e.label_role::text <> 'excluded')
      AND e.location IS NOT NULL
      AND extensions.ST_Intersects(
        e.location::extensions.geometry,
        extensions.ST_MakeEnvelope(
          p_bbox_min_lng,
          p_bbox_min_lat,
          p_bbox_max_lng,
          p_bbox_max_lat,
          4326
        )
      )
  )
  SELECT
    ranked.id,
    ranked.timestamp,
    ranked.severity,
    ranked.verification_status,
    ranked.elevation_m,
    ranked.label_role,
    ranked.training_eligible_reason,
    ranked.lng,
    ranked.lat
  FROM ranked
  WHERE ranked.verification_rank >= p_min_verification_rank
  ORDER BY ranked.timestamp DESC
  LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION public.fetch_labeler_events IS
  'Phase 0: bbox+time-window narrowed event fetch for forecast outcome labeler, including training_eligible_reason for audit slices.';

GRANT EXECUTE ON FUNCTION public.fetch_labeler_events TO service_role, authenticated, anon;
