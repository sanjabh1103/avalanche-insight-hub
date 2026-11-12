-- Add unique constraint on sar_provenance_backfill_chunks for idempotent retries.
-- This ensures that re-running a chunk (after a crash) does not create duplicate
-- chunk records. The upsert in provenance_backfill.py uses this constraint.
-- P0-04 fix: Resume/idempotency safety.

-- Drop any existing index first (in case it was created manually)
DROP INDEX IF EXISTS idx_sar_provenance_chunks_unique_window;

-- Create unique index on (run_id, region_key, window_start)
CREATE UNIQUE INDEX IF NOT EXISTS idx_sar_provenance_chunks_unique_window
  ON public.sar_provenance_backfill_chunks (run_id, region_key, window_start);
