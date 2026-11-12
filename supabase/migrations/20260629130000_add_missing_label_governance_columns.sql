-- Add missing label governance columns to avalanche_events.
-- These columns are referenced by training_dataset.py and exist in the edge
-- deployment schema (01-schema.sql) but were never migrated to the live
-- Supabase database. Without them, the infer job fails with:
--   column avalanche_events_decayed.label_source does not exist

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS label_source TEXT,
  ADD COLUMN IF NOT EXISTS review_basis TEXT,
  ADD COLUMN IF NOT EXISTS nowcast_ref TEXT,
  ADD COLUMN IF NOT EXISTS observer_ref TEXT,
  ADD COLUMN IF NOT EXISTS regime TEXT,
  ADD COLUMN IF NOT EXISTS timing TEXT;

COMMENT ON COLUMN public.avalanche_events.label_source IS
  'Provenance of the label itself (e.g. manual, sar_detection, seismic_event, field_report, synthetic_negative, synthetic_bootstrap).';
COMMENT ON COLUMN public.avalanche_events.review_basis IS
  'How the label was reviewed (e.g. unverified, terrain_sampling, synthetic, expert_verified).';
COMMENT ON COLUMN public.avalanche_events.nowcast_ref IS
  'Reference to a nowcast run that produced or influenced this event label.';
COMMENT ON COLUMN public.avalanche_events.observer_ref IS
  'Reference to the observer or sensor that generated this event.';
COMMENT ON COLUMN public.avalanche_events.regime IS
  'Avalanche regime classification (e.g. dry_loose, wet_loose, dry_slab, wet_slab, glide).';
COMMENT ON COLUMN public.avalanche_events.timing IS
  'Timing classification relative to storm cycle (e.g. storm, post_storm, persistent).';

-- Recreate the decayed view so new columns are visible to training code.
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
