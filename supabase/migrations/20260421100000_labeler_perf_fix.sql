-- P0.1: Fix label-forecast-outcomes statement timeout (2026-04-21)
-- Root cause: the labeler fetches events in a time window then post-filters by
-- haversine distance for every cell (400 cells x N events per forecast).
-- Without a GIST index on avalanche_events.location, the bbox pre-filter we
-- add in the edge function falls back to a sequential scan.
--
-- This migration is additive and idempotent.

-- ---------------------------------------------------------------------------
-- 1. Spatial index on avalanche_events.location (GIST on geography type).
--    Supports ST_DWithin / ST_Intersects bbox narrowing in the labeler.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_avalanche_events_location_gist
  ON public.avalanche_events USING GIST (location)
  WHERE location IS NOT NULL;

COMMENT ON INDEX public.idx_avalanche_events_location_gist IS
  'GIST index on geography(Point,4326) location column; supports bbox narrowing for the forecast outcome labeler.';

-- ---------------------------------------------------------------------------
-- 2. Covering btree for the labeler hot path:
--    (hazard_type, timestamp, training_eligible) matches the common
--    "events in window that are eligible for labeling" query shape.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_avalanche_events_hazard_time_eligible
  ON public.avalanche_events (hazard_type, timestamp DESC, training_eligible)
  WHERE label_role IS DISTINCT FROM 'excluded';

-- ---------------------------------------------------------------------------
-- 3. RPC that the edge function calls instead of a raw REST query.
--    The RPC runs the bbox narrowing inside Postgres so the network payload
--    shrinks to the handful of matching events instead of every event in the
--    time window. Returns events as JSON rows.
-- ---------------------------------------------------------------------------

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
    ranked.lng,
    ranked.lat
  FROM ranked
  WHERE ranked.verification_rank >= p_min_verification_rank
  ORDER BY ranked.timestamp DESC
  LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION public.fetch_labeler_events IS
  'P0.1: Bbox+time-window narrowed event fetch for forecast outcome labeler. Returns up to p_limit eligible events with decoded lng/lat.';

GRANT EXECUTE ON FUNCTION public.fetch_labeler_events TO service_role, authenticated, anon;
