-- Track B forward migration: make event writes idempotent across crash retries.
--
-- The backfill control-plane chunk key prevents duplicate chunk rows, but it
-- cannot prevent duplicate avalanche_events when a process crashes after the
-- event insert and before the chunk is marked completed. This nullable column
-- leaves historical/non-backfill events unchanged while giving provenance
-- backfills a deterministic uniqueness key.

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS provenance_event_fingerprint TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_avalanche_events_backfill_fingerprint
  ON public.avalanche_events (backfill_run_id, provenance_event_fingerprint);

COMMENT ON COLUMN public.avalanche_events.provenance_event_fingerprint IS
  'Deterministic SHA-256 event identity for idempotent provenance backfill retries.';
