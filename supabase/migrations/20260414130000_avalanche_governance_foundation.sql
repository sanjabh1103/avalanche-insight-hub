DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type
    WHERE typnamespace = 'public'::regnamespace
      AND typname = 'hazard_type'
  ) THEN
    CREATE TYPE public.hazard_type AS ENUM ('avalanche');
  END IF;
END $$;

ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'snow_cover_refresh';
ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'recent_activity_refresh';
ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'label_forecast_outcomes';
ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'run_evaluation';
ALTER TYPE public.job_type ADD VALUE IF NOT EXISTS 'retrain_avalanche_model';

ALTER TABLE public.forecasts
  ADD COLUMN IF NOT EXISTS hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  ADD COLUMN IF NOT EXISTS uncertainty_score double precision,
  ADD COLUMN IF NOT EXISTS uncertainty_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS input_completeness_score double precision,
  ADD COLUMN IF NOT EXISTS label_support_score double precision,
  ADD COLUMN IF NOT EXISTS model_version text,
  ADD COLUMN IF NOT EXISTS feature_version text,
  ADD COLUMN IF NOT EXISTS data_snapshot_id text,
  ADD COLUMN IF NOT EXISTS calibration_profile_version text,
  ADD COLUMN IF NOT EXISTS threshold_profile_version text;

ALTER TABLE public.forecast_analytics
  ADD COLUMN IF NOT EXISTS hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  ADD COLUMN IF NOT EXISTS avg_uncertainty double precision,
  ADD COLUMN IF NOT EXISTS model_version text,
  ADD COLUMN IF NOT EXISTS calibration_profile_version text;

ALTER TABLE public.compute_jobs
  ADD COLUMN IF NOT EXISTS hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche';

ALTER TABLE public.model_status
  ADD COLUMN IF NOT EXISTS hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  ADD COLUMN IF NOT EXISTS feature_version text,
  ADD COLUMN IF NOT EXISTS calibration_profile_version text,
  ADD COLUMN IF NOT EXISTS threshold_profile_version text;

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  ADD COLUMN IF NOT EXISTS event_geom geometry(Geometry, 4326),
  ADD COLUMN IF NOT EXISTS event_subtype text,
  ADD COLUMN IF NOT EXISTS trigger_type text,
  ADD COLUMN IF NOT EXISTS size_scale text,
  ADD COLUMN IF NOT EXISTS elevation_m integer,
  ADD COLUMN IF NOT EXISTS aspect_bucket text,
  ADD COLUMN IF NOT EXISTS slope_band text,
  ADD COLUMN IF NOT EXISTS start_time timestamptz,
  ADD COLUMN IF NOT EXISTS end_time timestamptz,
  ADD COLUMN IF NOT EXISTS source_quality_score double precision,
  ADD COLUMN IF NOT EXISTS verification_status text NOT NULL DEFAULT 'unverified',
  ADD COLUMN IF NOT EXISTS label_role text NOT NULL DEFAULT 'display_only',
  ADD COLUMN IF NOT EXISTS recent_activity_weight double precision,
  ADD COLUMN IF NOT EXISTS event_features jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.field_reports
  ADD COLUMN IF NOT EXISTS hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche';

CREATE INDEX IF NOT EXISTS idx_forecasts_hazard_type_created_at
  ON public.forecasts (hazard_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_compute_jobs_hazard_type_created_at
  ON public.compute_jobs (hazard_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_avalanche_events_hazard_type_timestamp
  ON public.avalanche_events (hazard_type, timestamp DESC);
