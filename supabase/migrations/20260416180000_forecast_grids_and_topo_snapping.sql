-- Async ML backend foundation: precomputed forecast grids + topo-aware ingestion

CREATE EXTENSION IF NOT EXISTS postgis;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'job_type'
  ) THEN
    CREATE TYPE public.job_type AS ENUM ('forecast', 'daily_enrichment', 'sentinel_refresh', 'fine_tune', 'static_precompute', 'field_report_enrichment');
  END IF;
END $$;

ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'ml_train';
ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'forecast_grid_precompute';
ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'ingest_event';

CREATE TABLE IF NOT EXISTS public.forecast_grids (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  region_key TEXT NOT NULL,
  region_name TEXT NOT NULL,
  forecast_date DATE NOT NULL,
  horizon_hours INTEGER NOT NULL DEFAULT 24,
  bbox FLOAT8[4] NOT NULL,
  grid_geojson JSONB NOT NULL DEFAULT '[]'::jsonb,
  runout_polygons JSONB NOT NULL DEFAULT '[]'::jsonb,
  weather_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  model_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'ready',
  source_job_id UUID REFERENCES public.compute_jobs(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT forecast_grids_horizon_positive CHECK (horizon_hours > 0),
  CONSTRAINT forecast_grids_status_check CHECK (status IN ('queued', 'running', 'ready', 'failed', 'superseded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS forecast_grids_unique_active_idx
  ON public.forecast_grids (hazard_type, region_key, forecast_date, horizon_hours)
  WHERE status IN ('queued', 'running', 'ready');

CREATE INDEX IF NOT EXISTS forecast_grids_region_date_idx
  ON public.forecast_grids (hazard_type, region_key, forecast_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS forecast_grids_status_created_idx
  ON public.forecast_grids (status, created_at DESC);

ALTER TABLE public.forecast_grids ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view forecast grids" ON public.forecast_grids;
DROP POLICY IF EXISTS "Service role can manage forecast grids" ON public.forecast_grids;
CREATE POLICY "Anyone can view forecast grids" ON public.forecast_grids FOR SELECT USING (true);
CREATE POLICY "Service role can manage forecast grids" ON public.forecast_grids FOR ALL USING (auth.role() = 'service_role');

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'avalanche_events' AND column_name = 'slope_angle_deg'
  ) THEN
    RAISE NOTICE 'avalanche_events topo columns already exist';
  ELSE
    ALTER TABLE public.avalanche_events ADD COLUMN slope_angle_deg DOUBLE PRECISION;
    ALTER TABLE public.avalanche_events ADD COLUMN aspect_deg DOUBLE PRECISION;
    ALTER TABLE public.avalanche_events ADD COLUMN topo_source TEXT;
    ALTER TABLE public.avalanche_events ADD COLUMN topo_resolution_m DOUBLE PRECISION;
    ALTER TABLE public.avalanche_events ADD COLUMN topo_profile JSONB NOT NULL DEFAULT '{}'::jsonb;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS avalanche_events_topo_source_idx
  ON public.avalanche_events (topo_source);

CREATE INDEX IF NOT EXISTS avalanche_events_slope_angle_idx
  ON public.avalanche_events (slope_angle_deg);

CREATE OR REPLACE FUNCTION public.set_forecast_grids_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_forecast_grids_updated_at ON public.forecast_grids;
CREATE TRIGGER set_forecast_grids_updated_at
BEFORE UPDATE ON public.forecast_grids
FOR EACH ROW
EXECUTE FUNCTION public.set_forecast_grids_updated_at();
