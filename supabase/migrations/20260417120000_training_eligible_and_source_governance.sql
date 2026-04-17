-- Phase 1 of Unified PRD v2.0
-- Story 21 (climate concept-drift + ground-truth integrity) + Edit 1 (source governance)

-- -------------------------------------------------------------------------
-- Story 21: training_eligible flag so Gemini-detected deposit-zone events
-- still render on the UI but do NOT poison the training set.
-- -------------------------------------------------------------------------

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS training_eligible BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS training_eligible_reason TEXT;

CREATE INDEX IF NOT EXISTS avalanche_events_training_eligible_idx
  ON public.avalanche_events (training_eligible)
  WHERE training_eligible = TRUE;

COMMENT ON COLUMN public.avalanche_events.training_eligible IS
  'Story 21: FALSE for deposit-zone or shadow-masked events so they render on UI but do not poison training.';

COMMENT ON COLUMN public.avalanche_events.training_eligible_reason IS
  'Audit trail for why training_eligible was flipped (e.g. gemini_deposit_zone, heuristic_deposit_zone, sar_shadow_mask).';

-- -------------------------------------------------------------------------
-- Edit 1: source column governance hardening.
-- Column already exists (TEXT, nullable) from the base schema.
-- Backfill NULL values -> 'manual', then enforce NOT NULL + allowed values.
-- -------------------------------------------------------------------------

UPDATE public.avalanche_events
SET source = 'manual'
WHERE source IS NULL;

ALTER TABLE public.avalanche_events
  ALTER COLUMN source SET DEFAULT 'manual';

ALTER TABLE public.avalanche_events
  ALTER COLUMN source SET NOT NULL;

ALTER TABLE public.avalanche_events
  DROP CONSTRAINT IF EXISTS avalanche_events_source_check;

-- Canonical + legacy values accepted to preserve existing pipelines.
-- Canonical (preferred for new code):
--   manual, field_report, gemini_news, gee_sar, sentinel_refresh, historical_import, admin, synthetic
-- Legacy (already in use by trigger-job and older ingest paths) kept for backward compatibility:
--   newsdata.io, Sentinel-1, sentinel-1-sar, rls-test
ALTER TABLE public.avalanche_events
  ADD CONSTRAINT avalanche_events_source_check
  CHECK (source IN (
    'manual',
    'field_report',
    'gemini_news',
    'gee_sar',
    'sentinel_refresh',
    'historical_import',
    'admin',
    'synthetic',
    'newsdata.io',
    'Sentinel-1',
    'sentinel-1-sar',
    'rls-test'
  ));

CREATE INDEX IF NOT EXISTS avalanche_events_source_training_idx
  ON public.avalanche_events (source, training_eligible);

COMMENT ON COLUMN public.avalanche_events.source IS
  'Provenance tag for data governance. Preferred canonical values: manual, field_report, gemini_news, gee_sar, sentinel_refresh, historical_import, admin, synthetic. Legacy values newsdata.io and Sentinel-1 remain valid for backward compatibility.';
