-- Autonomous label governance + SAR artifact contracts (2026-04-25)
--
-- This migration makes the "full pivot" storage layer explicit:
--   1. Weighted autonomous-label provenance on avalanche_events
--   2. SAR artifact metadata for masks / geometries / scene lineage
--   3. Recreated decay view so new columns are visible to training code

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS label_confidence double precision NOT NULL DEFAULT 0.5,
  ADD COLUMN IF NOT EXISTS training_weight double precision NOT NULL DEFAULT 1.0,
  ADD COLUMN IF NOT EXISTS source_model text,
  ADD COLUMN IF NOT EXISTS source_scene_ids text[] NOT NULL DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS geometry_type text,
  ADD COLUMN IF NOT EXISTS mask_asset_ref text;

COMMENT ON COLUMN public.avalanche_events.label_confidence IS
  'Confidence in the autonomous label itself (source/model quality), separate from event severity.';

COMMENT ON COLUMN public.avalanche_events.training_weight IS
  'Final training weight after combining source provenance, corroboration, and recency decay.';

COMMENT ON COLUMN public.avalanche_events.source_model IS
  'Model or detector that generated the event label, such as gemini-flash-latest or gee_threshold_baseline_v1.';

COMMENT ON COLUMN public.avalanche_events.source_scene_ids IS
  'Upstream remote-sensing scene identifiers used to derive the label.';

COMMENT ON COLUMN public.avalanche_events.geometry_type IS
  'Primary event geometry representation: point, polygon, mask, or mixed.';

COMMENT ON COLUMN public.avalanche_events.mask_asset_ref IS
  'Reference to the raster mask artifact backing the SAR detection when available.';

CREATE INDEX IF NOT EXISTS idx_avalanche_events_training_weight
  ON public.avalanche_events (training_eligible, training_weight DESC, timestamp DESC)
  WHERE training_eligible = TRUE;

CREATE INDEX IF NOT EXISTS idx_avalanche_events_source_model
  ON public.avalanche_events (source_model, timestamp DESC);

CREATE TABLE IF NOT EXISTS public.sar_detection_artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  avalanche_event_id uuid REFERENCES public.avalanche_events(id) ON DELETE CASCADE,
  region_key text NOT NULL,
  scene_time timestamptz,
  source_scene_ids text[] NOT NULL DEFAULT '{}'::text[],
  detection_geometry jsonb NOT NULL DEFAULT '{}'::jsonb,
  centroid_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_version text NOT NULL,
  confidence_score double precision NOT NULL DEFAULT 0.0,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  mask_asset_ref text,
  geometry_type text NOT NULL DEFAULT 'polygon',
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sar_detection_artifacts_event
  ON public.sar_detection_artifacts (avalanche_event_id);

CREATE INDEX IF NOT EXISTS idx_sar_detection_artifacts_region_time
  ON public.sar_detection_artifacts (region_key, scene_time DESC);

COMMENT ON TABLE public.sar_detection_artifacts IS
  'Artifact ledger for SAR detections, including source scenes, geometry payloads, raster mask refs, model version, and provenance.';

ALTER TABLE public.sar_detection_artifacts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'sar_detection_artifacts' AND policyname = 'sar_detection_artifacts_read'
  ) THEN
    CREATE POLICY sar_detection_artifacts_read
      ON public.sar_detection_artifacts
      FOR SELECT
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'sar_detection_artifacts' AND policyname = 'sar_detection_artifacts_service_write'
  ) THEN
    CREATE POLICY sar_detection_artifacts_service_write
      ON public.sar_detection_artifacts
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;

CREATE OR REPLACE VIEW public.avalanche_events_decayed AS
SELECT
  e.*,
  GREATEST(
    0.05,
    LEAST(
      1.0,
      COALESCE(e.label_confidence, e.confidence, 0.5) * EXP(
        -LN(2) * GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) / 14.0
      )
    )
  ) AS confidence_decayed,
  GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) AS age_days
FROM public.avalanche_events e;

COMMENT ON VIEW public.avalanche_events_decayed IS
  'Read-only projection of avalanche_events with an exponential 14-day half-life applied to label_confidence/confidence for training-time weighting.';
