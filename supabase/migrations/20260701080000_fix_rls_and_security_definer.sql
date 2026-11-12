-- Fix 1: Enable RLS on seismic_events (policies already exist but RLS was never enabled)
ALTER TABLE public.seismic_events ENABLE ROW LEVEL SECURITY;

-- Fix 2: Recreate avalanche_events_decayed view with SECURITY INVOKER
-- The view was implicitly SECURITY DEFINER, which runs with the owner's
-- permissions instead of the caller's. SECURITY INVOKER is the correct
-- setting for a read-only projection that should respect the caller's RLS.
DROP VIEW IF EXISTS public.avalanche_events_decayed;

CREATE VIEW public.avalanche_events_decayed
WITH (security_invoker = true) AS
SELECT
  e.*,
  GREATEST(
    0.2,
    e.confidence * EXP(-LN(2) * EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / (30 * 86400.0))
  ) AS confidence_decayed,
  GREATEST(
    0.2,
    e.label_confidence * EXP(-LN(2) * EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / (30 * 86400.0))
  ) AS label_confidence_decayed,
  GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) AS age_days
FROM public.avalanche_events e;

COMMENT ON VIEW public.avalanche_events_decayed IS
  'Read-only projection of avalanche_events with an exponential 30-day half-life applied to label_confidence/confidence for training-time weighting.';

GRANT SELECT ON public.avalanche_events_decayed TO authenticated;
GRANT SELECT ON public.avalanche_events_decayed TO anon;
