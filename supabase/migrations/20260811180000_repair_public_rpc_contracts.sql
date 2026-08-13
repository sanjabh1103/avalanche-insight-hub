-- Repair two pre-existing public RPC contracts exposed by local schema lint.
-- This migration preserves signatures and behavior while making the return
-- type and identifier resolution explicit for the live edge-function paths.

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
      e.elevation_m::double precision AS elevation_m,
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
    FROM public.avalanche_events AS e
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
  'Returns bbox- and time-window-filtered eligible events for the forecast outcome labeler.';

GRANT EXECUTE ON FUNCTION public.fetch_labeler_events(
  text,
  timestamptz,
  timestamptz,
  double precision,
  double precision,
  double precision,
  double precision,
  integer,
  integer
) TO service_role, authenticated, anon;

CREATE OR REPLACE FUNCTION public.promote_event_verification(
  p_event_id uuid,
  p_new_status text,
  p_promoter text,
  p_reason text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  previous_status text,
  new_status text,
  promoted_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
  current_status text;
  rank_current integer;
  rank_new integer;
BEGIN
  IF p_new_status NOT IN ('weak', 'verified', 'expert_verified') THEN
    RAISE EXCEPTION 'Invalid verification target: %', p_new_status;
  END IF;

  SELECT e.verification_status::text INTO current_status
  FROM public.avalanche_events AS e
  WHERE e.id = p_event_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Event % not found', p_event_id;
  END IF;

  rank_current := CASE COALESCE(current_status, 'unverified')
    WHEN 'expert_verified' THEN 3
    WHEN 'verified' THEN 2
    WHEN 'weak' THEN 1
    ELSE 0
  END;
  rank_new := CASE p_new_status
    WHEN 'expert_verified' THEN 3
    WHEN 'verified' THEN 2
    WHEN 'weak' THEN 1
  END;

  IF rank_new <= rank_current THEN
    RETURN QUERY SELECT p_event_id, current_status, current_status, NOW();
    RETURN;
  END IF;

  UPDATE public.avalanche_events AS e
  SET verification_status = p_new_status::public.verification_status,
      features = COALESCE(e.features, '{}'::jsonb) || jsonb_build_object(
        'verification_promotion', jsonb_build_object(
          'promoted_from', current_status,
          'promoted_to', p_new_status,
          'promoter', p_promoter,
          'reason', p_reason,
          'promoted_at', NOW()
        )
      )
  WHERE e.id = p_event_id;

  RETURN QUERY SELECT p_event_id, current_status, p_new_status, NOW();
END;
$$;

COMMENT ON FUNCTION public.promote_event_verification IS
  'Safely upgrades verification rank and records the promotion audit trail.';

GRANT EXECUTE ON FUNCTION public.promote_event_verification(
  uuid,
  text,
  text,
  text
) TO service_role;
