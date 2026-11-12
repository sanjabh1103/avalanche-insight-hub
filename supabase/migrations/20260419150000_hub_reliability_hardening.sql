-- Hub reliability hardening (2026-04-19)
-- Addresses 5 runtime defects identified in the live-probe gap analysis:
--   1. label-forecast-outcomes statement timeout (missing indexes on avalanche_events + forecast_outcomes)
--   2. forecast_outcomes.forecast_source column referenced by probes / future code but not present
--   4. per-report confidence decay view
--   5. forecast_shap_cache table for offline TreeSHAP results
--
-- This migration is additive and idempotent.

-- ---------------------------------------------------------------------------
-- 1. Indexes to eliminate the label-forecast-outcomes statement timeout.
-- ---------------------------------------------------------------------------

-- Events fetched per forecast window are narrowed by (hazard_type, timestamp, label_role).
CREATE INDEX IF NOT EXISTS idx_avalanche_events_hazard_timestamp
  ON public.avalanche_events (hazard_type, timestamp DESC)
  WHERE label_role IS DISTINCT FROM 'excluded';

CREATE INDEX IF NOT EXISTS idx_avalanche_events_timestamp_brin
  ON public.avalanche_events USING BRIN (timestamp);

-- The labeler frequently asks "do outcomes already exist for this forecast?".
-- Supplements the partial index added in 20260418110000_forecast_grid_outcomes_bridge.sql.
CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_forecast_legacy
  ON public.forecast_outcomes (forecast_id, forecast_hour)
  WHERE forecast_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_hazard_created
  ON public.forecast_outcomes (hazard_type, created_at DESC);

-- ---------------------------------------------------------------------------
-- 2. forecast_outcomes.forecast_source generated column.
--    Gives callers a stable column to filter/index on ('async' | 'legacy').
-- ---------------------------------------------------------------------------

ALTER TABLE public.forecast_outcomes
  ADD COLUMN IF NOT EXISTS forecast_source text
    GENERATED ALWAYS AS (
      CASE
        WHEN forecast_grid_id IS NOT NULL THEN 'async'
        WHEN forecast_id IS NOT NULL THEN 'legacy'
        ELSE 'unknown'
      END
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_source_created
  ON public.forecast_outcomes (forecast_source, created_at DESC);

COMMENT ON COLUMN public.forecast_outcomes.forecast_source IS
  'Derived source classification: async (forecast_grid_id set), legacy (forecast_id set), or unknown.';

-- ---------------------------------------------------------------------------
-- 4. Per-report confidence decay view.
--    Applies an exponential half-life of 14 days to unverified / weak reports
--    so stale citizen data does not dominate model training weights.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.avalanche_events_decayed AS
SELECT
  e.*,
  GREATEST(
    0.05,
    LEAST(
      1.0,
      COALESCE(e.confidence, 0.5) * EXP(
        -LN(2) * GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) / 14.0
      )
    )
  ) AS confidence_decayed,
  GREATEST(0, EXTRACT(EPOCH FROM (NOW() - e.timestamp)) / 86400.0) AS age_days
FROM public.avalanche_events e;

COMMENT ON VIEW public.avalanche_events_decayed IS
  'Read-only projection of avalanche_events with an exponential 14-day half-life applied to confidence. Training code should prefer this view for weighting citizen reports.';

-- ---------------------------------------------------------------------------
-- 5. forecast_shap_cache table for offline TreeSHAP results.
--    Keeps heavy SHAP computation out of the edge path and lets the UI show
--    real contributions instead of the client-side heuristic fallback.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.forecast_shap_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  forecast_grid_id uuid NOT NULL REFERENCES public.forecast_grids(id) ON DELETE CASCADE,
  cell_row smallint NOT NULL,
  cell_col smallint NOT NULL,
  forecast_hour smallint NOT NULL DEFAULT 0,
  model_version text NOT NULL,
  top_features jsonb NOT NULL,
  shap_values jsonb NOT NULL,
  base_value double precision,
  dominant_driver text,
  created_at timestamptz NOT NULL DEFAULT NOW(),
  UNIQUE (forecast_grid_id, cell_row, cell_col, forecast_hour, model_version)
);

CREATE INDEX IF NOT EXISTS idx_forecast_shap_cache_lookup
  ON public.forecast_shap_cache (forecast_grid_id, forecast_hour, cell_row, cell_col);

COMMENT ON TABLE public.forecast_shap_cache IS
  'Offline TreeSHAP results keyed by forecast_grid cell. Populated by backend/daily_inference.py; read by shap-explainer and UI.';

ALTER TABLE public.forecast_shap_cache ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'forecast_shap_cache' AND policyname = 'forecast_shap_cache_read'
  ) THEN
    CREATE POLICY forecast_shap_cache_read
      ON public.forecast_shap_cache
      FOR SELECT
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'forecast_shap_cache' AND policyname = 'forecast_shap_cache_service_write'
  ) THEN
    CREATE POLICY forecast_shap_cache_service_write
      ON public.forecast_shap_cache
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;
