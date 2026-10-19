-- Track B forward migration: make one artifact ledger row correspond to one
-- avalanche event. This is the artifact half of crash-safe backfill retries.

CREATE UNIQUE INDEX IF NOT EXISTS idx_sar_detection_artifacts_event_unique
  ON public.sar_detection_artifacts (avalanche_event_id);
