-- P1.3: Verified-training promotion pipeline (2026-04-21)
-- Adds RPCs that let the field-report-enrichment function promote newly-created
-- events to verification_status='weak' when a corroborating SAR/news event
-- exists nearby within 48h, and lets an admin manually promote to 'verified'.

-- ---------------------------------------------------------------------------
-- 1. match_corroborating_event: returns the nearest SAR/news/gee_sar event
--    within the given spatial + temporal envelope, or NULL.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.match_corroborating_event(
  p_event_id uuid,
  p_lat double precision,
  p_lng double precision,
  p_timestamp timestamptz,
  p_radius_m integer DEFAULT 5000,
  p_window_hours integer DEFAULT 48
)
RETURNS TABLE (
  matched_event_id uuid,
  source text,
  distance_m double precision,
  hours_delta double precision
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    e.id AS matched_event_id,
    e.source::text AS source,
    extensions.ST_Distance(
      e.location::extensions.geography,
      extensions.ST_SetSRID(extensions.ST_MakePoint(p_lng, p_lat), 4326)::extensions.geography
    ) AS distance_m,
    EXTRACT(EPOCH FROM (e.timestamp - p_timestamp)) / 3600.0 AS hours_delta
  FROM public.avalanche_events e
  WHERE e.id <> p_event_id
    AND e.source::text IN ('gee_sar', 'sentinel1_gee', 'news_event', 'gemini_news_extraction')
    AND e.location IS NOT NULL
    AND e.timestamp BETWEEN p_timestamp - make_interval(hours => p_window_hours)
                        AND p_timestamp + make_interval(hours => p_window_hours)
    AND extensions.ST_DWithin(
      e.location::extensions.geography,
      extensions.ST_SetSRID(extensions.ST_MakePoint(p_lng, p_lat), 4326)::extensions.geography,
      p_radius_m
    )
  ORDER BY distance_m ASC, ABS(EXTRACT(EPOCH FROM (e.timestamp - p_timestamp))) ASC
  LIMIT 1;
$$;

COMMENT ON FUNCTION public.match_corroborating_event IS
  'P1.3: Returns the nearest SAR/news event within p_radius_m meters and p_window_hours hours of the target point. Used by field-report-enrichment to auto-promote matching reports to verification_status=weak.';

GRANT EXECUTE ON FUNCTION public.match_corroborating_event TO service_role, authenticated, anon;

-- ---------------------------------------------------------------------------
-- 2. promote_event_verification: safe UPSERT helper called by the
--    promote-report edge function. Accepts the target status + a promoter
--    user id (for audit), and refuses to downgrade verification rank.
-- ---------------------------------------------------------------------------

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

  SELECT verification_status::text INTO current_status
  FROM public.avalanche_events
  WHERE id = p_event_id
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
    -- No-op when target is not an upgrade.
    RETURN QUERY SELECT p_event_id, current_status, current_status, NOW();
    RETURN;
  END IF;

  UPDATE public.avalanche_events
  SET verification_status = p_new_status::public.verification_status,
      features = COALESCE(features, '{}'::jsonb) || jsonb_build_object(
        'verification_promotion', jsonb_build_object(
          'promoted_from', current_status,
          'promoted_to', p_new_status,
          'promoter', p_promoter,
          'reason', p_reason,
          'promoted_at', NOW()
        )
      )
  WHERE id = p_event_id;

  RETURN QUERY SELECT p_event_id, current_status, p_new_status, NOW();
END;
$$;

COMMENT ON FUNCTION public.promote_event_verification IS
  'P1.3: Safe verification-rank upgrade. Refuses downgrades and records a promotion audit trail inside features->verification_promotion.';

GRANT EXECUTE ON FUNCTION public.promote_event_verification TO service_role;
