ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS governance_version text,
  ADD COLUMN IF NOT EXISTS governed_at timestamptz;

COMMENT ON COLUMN public.avalanche_events.governance_version IS
  'Version tag for the governance formula that materialized label_confidence/training_weight.';

COMMENT ON COLUMN public.avalanche_events.governed_at IS
  'Timestamp when governance-derived fields were last materialized on the row.';

CREATE INDEX IF NOT EXISTS idx_avalanche_events_governance_version
  ON public.avalanche_events (governance_version, governed_at DESC);

DROP VIEW IF EXISTS public.avalanche_events_decayed;

CREATE VIEW public.avalanche_events_decayed AS
SELECT
  e.*,
  GREATEST(
    0.05,
    LEAST(
      1.0,
      COALESCE(e.label_confidence, e.confidence, 0.5) * EXP(
        -LN(2) * GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) / 30.0
      )
    )
  ) AS confidence_decayed,
  GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) AS age_days
FROM public.avalanche_events e;

COMMENT ON VIEW public.avalanche_events_decayed IS
  'Read-only projection of avalanche_events with an exponential 30-day half-life applied to label_confidence/confidence for training-time weighting.';
