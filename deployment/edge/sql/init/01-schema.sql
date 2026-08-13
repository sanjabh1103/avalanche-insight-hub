-- Edge Deployment Schema — Standalone PostgreSQL for air-gapped Partner HPC
-- No Supabase auth, no RLS, no storage buckets. Local filesystem only.
-- Derived from Supabase migrations, adapted for standalone Postgres + PostGIS.

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enums
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'verification_status') THEN
    CREATE TYPE public.verification_status AS ENUM ('unverified', 'weak', 'verified', 'expert_verified');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'label_role') THEN
    CREATE TYPE public.label_role AS ENUM ('training_label', 'display_only', 'excluded');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'review_status') THEN
    CREATE TYPE public.review_status AS ENUM ('pending', 'under_review', 'approved', 'rejected', 'needs_info');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'event_type') THEN
    CREATE TYPE public.event_type AS ENUM ('slab', 'loose', 'wet', 'glide', 'cornice', 'unknown');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'report_status') THEN
    CREATE TYPE public.report_status AS ENUM ('pending', 'verified', 'rejected');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'job_type') THEN
    CREATE TYPE public.job_type AS ENUM (
      'forecast', 'daily_enrichment', 'sentinel_refresh', 'fine_tune',
      'static_precompute', 'field_report_enrichment', 'ml_train',
      'forecast_grid_precompute', 'ingest_event',
      'snow_cover_refresh', 'recent_activity_refresh',
      'label_forecast_outcomes', 'run_evaluation',
      'retrain_avalanche_model', 'model_optimization',
      'evaluate_release'
    );
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'job_status') THEN
    CREATE TYPE public.job_status AS ENUM ('pending', 'running', 'completed', 'failed');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'hazard_type') THEN
    CREATE TYPE public.hazard_type AS ENUM ('avalanche');
  END IF;
END $$;

-- avalanche_events
CREATE TABLE IF NOT EXISTS public.avalanche_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  location geography(Point, 4326),
  lat DOUBLE PRECISION,
  lng DOUBLE PRECISION,
  source TEXT,
  description TEXT,
  severity INT CHECK (severity BETWEEN 1 AND 5),
  event_type public.event_type DEFAULT 'unknown',
  features JSONB DEFAULT '{}'::jsonb,
  confidence FLOAT DEFAULT 0,
  fusion_source TEXT,
  training_eligible BOOLEAN NOT NULL DEFAULT TRUE,
  training_eligible_reason TEXT,
  training_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  slope_angle_deg DOUBLE PRECISION,
  aspect_deg DOUBLE PRECISION,
  elevation_m DOUBLE PRECISION,
  topo_source TEXT,
  topo_resolution_m DOUBLE PRECISION,
  topo_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  label_source TEXT,
  label_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  source_model TEXT,
  source_scene_ids TEXT[] NOT NULL DEFAULT '{}'::text[],
  geometry_type TEXT,
  mask_asset_ref TEXT,
  detection_mode TEXT NOT NULL DEFAULT 'edge_fallback',
  detection_confidence DOUBLE PRECISION,
  satellite_scene_ids TEXT[] NOT NULL DEFAULT '{}'::text[],
  backscatter_delta_db DOUBLE PRECISION,
  verification_status TEXT NOT NULL DEFAULT 'unverified',
  label_role TEXT NOT NULL DEFAULT 'display_only',
  event_geom geography(Geometry, 4326),
  event_subtype TEXT,
  trigger_type TEXT,
  start_time TIMESTAMPTZ,
  end_time TIMESTAMPTZ,
  source_quality_score DOUBLE PRECISION,
  recent_activity_weight DOUBLE PRECISION,
  event_features JSONB NOT NULL DEFAULT '{}'::jsonb,
  governance_version TEXT,
  governed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_verification_status CHECK (verification_status IN ('unverified', 'weak', 'verified', 'expert_verified')),
  CONSTRAINT chk_label_role CHECK (label_role IN ('training_label', 'display_only', 'excluded'))
);

CREATE INDEX IF NOT EXISTS avalanche_events_source_idx ON public.avalanche_events (source);
CREATE INDEX IF NOT EXISTS avalanche_events_topo_source_idx ON public.avalanche_events (topo_source);
CREATE INDEX IF NOT EXISTS avalanche_events_slope_angle_idx ON public.avalanche_events (slope_angle_deg);
CREATE INDEX IF NOT EXISTS avalanche_events_hazard_idx ON public.avalanche_events (hazard_type);
CREATE INDEX IF NOT EXISTS avalanche_events_training_eligible_idx
  ON public.avalanche_events (training_eligible) WHERE training_eligible = TRUE;
CREATE INDEX IF NOT EXISTS avalanche_events_source_training_idx
  ON public.avalanche_events (source, training_eligible);
CREATE INDEX IF NOT EXISTS avalanche_events_detection_mode_idx
  ON public.avalanche_events (source, detection_mode, created_at DESC);
CREATE INDEX IF NOT EXISTS avalanche_events_label_quality_idx
  ON public.avalanche_events (label_role, verification_status, timestamp DESC)
  WHERE label_role = 'training_label';
CREATE INDEX IF NOT EXISTS avalanche_events_hazard_time_eligible_idx
  ON public.avalanche_events (hazard_type, timestamp DESC, training_eligible)
  WHERE label_role IS DISTINCT FROM 'excluded';
CREATE INDEX IF NOT EXISTS avalanche_events_governance_version_idx
  ON public.avalanche_events (governance_version, governed_at DESC);

-- forecasts (legacy table, kept for compatibility)
CREATE TABLE IF NOT EXISTS public.forecasts (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  bbox FLOAT8[4],
  risk_score FLOAT,
  hazard FLOAT,
  exposure FLOAT,
  vulnerability FLOAT,
  problem_type TEXT,
  shap_values JSONB DEFAULT '{}'::jsonb,
  grid_data JSONB DEFAULT '[]'::jsonb,
  hourly_grids JSONB DEFAULT '[]'::jsonb,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  runtime_mode TEXT NOT NULL DEFAULT 'edge_fallback',
  inference_backend TEXT NOT NULL DEFAULT 'edge_fallback',
  capability_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  snowpack_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  optimization_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- field_reports
CREATE TABLE IF NOT EXISTS public.field_reports (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id TEXT,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  location geography(Point, 4326),
  lat DOUBLE PRECISION,
  lng DOUBLE PRECISION,
  image_url TEXT,
  description TEXT,
  status public.report_status DEFAULT 'pending',
  review_status public.review_status NOT NULL DEFAULT 'pending',
  normalized_event_type TEXT,
  normalized_severity TEXT,
  trigger_type TEXT,
  reviewed_at TIMESTAMPTZ,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  client_report_id TEXT,
  training_eligible BOOLEAN NOT NULL DEFAULT TRUE,
  sync_status TEXT NOT NULL DEFAULT 'synced',
  submitted_offline BOOLEAN NOT NULL DEFAULT FALSE,
  synced_at TIMESTAMPTZ,
  sync_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_field_reports_client_report_id
  ON public.field_reports (client_report_id) WHERE client_report_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_field_reports_review_status
  ON public.field_reports (review_status, created_at)
  WHERE review_status IN ('pending', 'needs_info');

-- compute_jobs
CREATE TABLE IF NOT EXISTS public.compute_jobs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  type public.job_type NOT NULL,
  status public.job_status NOT NULL DEFAULT 'pending',
  bbox FLOAT8[4],
  time_offset INT DEFAULT 0,
  payload JSONB DEFAULT '{}'::jsonb,
  result JSONB DEFAULT '{}'::jsonb,
  error TEXT,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compute_jobs_hazard_type_created_at
  ON public.compute_jobs (hazard_type, created_at DESC);

-- system_config
CREATE TABLE IF NOT EXISTS public.system_config (
  id SERIAL PRIMARY KEY,
  gemini_usage INT DEFAULT 0,
  gemini_spend_cap INT DEFAULT 1000,
  last_enrichment TIMESTAMPTZ
);

INSERT INTO public.system_config (id, gemini_usage, gemini_spend_cap) VALUES (1, 0, 1000)
ON CONFLICT (id) DO NOTHING;

-- model_status
CREATE TABLE IF NOT EXISTS public.model_status (
  id SERIAL PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  version TEXT DEFAULT 'v1.0.0',
  last_trained TIMESTAMPTZ,
  last_inference TIMESTAMPTZ,
  f1_score FLOAT DEFAULT 0.0,
  next_run TIMESTAMPTZ,
  feature_version TEXT,
  calibration_profile_version TEXT,
  threshold_profile_version TEXT,
  active_model_type TEXT,
  active_model_version TEXT,
  pss_reported FLOAT,
  pss_gate_passed BOOLEAN,
  promotion_gate_passed BOOLEAN,
  dynamic_model_candidate JSONB DEFAULT '{}'::jsonb,
  stability_summary JSONB DEFAULT '{}'::jsonb,
  latest_benchmark_summary JSONB DEFAULT '{}'::jsonb,
  optimization_summary JSONB DEFAULT '{}'::jsonb,
  optimization_version TEXT,
  sar_pipeline_version TEXT,
  snowpack_metrics JSONB DEFAULT '{}'::jsonb,
  satellite_detection_stats JSONB DEFAULT '{}'::jsonb,
  snowpack_model_version TEXT,
  inference_backend TEXT NOT NULL DEFAULT 'edge_fallback',
  capability_summary TEXT NOT NULL DEFAULT 'Edge-only fallback',
  capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
  shadow_mode_active BOOLEAN,
  drift_mode_state TEXT,
  data_freshness_hours DOUBLE PRECISION DEFAULT 0,
  autonomous_evidence_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  next_optimization_run TIMESTAMPTZ
);

INSERT INTO public.model_status (id, hazard_type, version, f1_score) VALUES (1, 'avalanche', 'v1.0.0-sim', 0.847)
ON CONFLICT (id) DO NOTHING;

-- Reset sequence after explicit id insert
SELECT setval(pg_get_serial_sequence('public.model_status', 'id'), GREATEST(1, (SELECT MAX(id) FROM public.model_status)));
SELECT setval(pg_get_serial_sequence('public.system_config', 'id'), GREATEST(1, (SELECT MAX(id) FROM public.system_config)));

-- forecast_grids (precomputed batch artifacts)
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
  hourly_grids JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'ready',
  source_job_id UUID REFERENCES public.compute_jobs(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT forecast_grids_horizon_positive CHECK (horizon_hours > 0),
  CONSTRAINT forecast_grids_status_check CHECK (status IN ('queued', 'running', 'ready', 'partial', 'stale', 'failed', 'superseded')),
  CONSTRAINT forecast_grids_unique_horizon UNIQUE (hazard_type, region_key, forecast_date, horizon_hours)
);

CREATE UNIQUE INDEX IF NOT EXISTS forecast_grids_unique_active_idx
  ON public.forecast_grids (hazard_type, region_key, forecast_date, horizon_hours)
  WHERE status IN ('queued', 'running', 'ready');

CREATE INDEX IF NOT EXISTS forecast_grids_region_date_idx
  ON public.forecast_grids (hazard_type, region_key, forecast_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS forecast_grids_status_created_idx
  ON public.forecast_grids (status, created_at DESC);

-- forecast_runs (decomposed publication plane)
CREATE TABLE IF NOT EXISTS public.forecast_runs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  region_key TEXT NOT NULL,
  region_name TEXT NOT NULL,
  forecast_date DATE NOT NULL,
  issue_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  horizon_hours INTEGER NOT NULL,
  grid_size INTEGER NOT NULL,
  bbox FLOAT8[4] NOT NULL,
  status TEXT NOT NULL DEFAULT 'building',
  publication_status TEXT NOT NULL DEFAULT 'building',
  manifest_storage_ref TEXT,
  runout_storage_ref TEXT,
  compatibility_forecast_grid_id UUID REFERENCES public.forecast_grids(id) ON DELETE SET NULL,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  model_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  weather_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  forecast_bulletins JSONB NOT NULL DEFAULT '{}'::jsonb,
  published_at TIMESTAMPTZ,
  freshness_hours FLOAT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT forecast_runs_horizon_positive CHECK (horizon_hours > 0),
  CONSTRAINT forecast_runs_grid_positive CHECK (grid_size > 0),
  CONSTRAINT forecast_runs_status_check CHECK (status IN ('building', 'ready', 'failed', 'superseded')),
  CONSTRAINT forecast_runs_publication_status_check CHECK (publication_status IN ('building', 'artifacts_written', 'validated', 'published', 'failed'))
);

DROP INDEX IF EXISTS forecast_runs_active_idx;
CREATE UNIQUE INDEX IF NOT EXISTS forecast_runs_active_region_idx
  ON public.forecast_runs (hazard_type, region_key)
  WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS forecast_runs_region_date_idx
  ON public.forecast_runs (hazard_type, region_key, forecast_date DESC, created_at DESC);

-- forecast_run_hours (per-hour artifact metadata)
CREATE TABLE IF NOT EXISTS public.forecast_run_hours (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_run_id UUID NOT NULL REFERENCES public.forecast_runs(id) ON DELETE CASCADE,
  forecast_hour INTEGER NOT NULL,
  valid_time TIMESTAMPTZ NOT NULL,
  storage_ref TEXT NOT NULL,
  cell_count INTEGER NOT NULL DEFAULT 0,
  ready_cell_count INTEGER NOT NULL DEFAULT 0,
  stale_cell_count INTEGER NOT NULL DEFAULT 0,
  payload_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT forecast_run_hours_nonnegative CHECK (
    forecast_hour >= 0
    AND cell_count >= 0
    AND ready_cell_count >= 0
    AND stale_cell_count >= 0
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS forecast_run_hours_unique_idx
  ON public.forecast_run_hours (forecast_run_id, forecast_hour);

-- forecast_publication_events
CREATE TABLE IF NOT EXISTS public.forecast_publication_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_run_id UUID NOT NULL REFERENCES public.forecast_runs(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- forecast_active_runs view
CREATE OR REPLACE VIEW public.forecast_active_runs AS
SELECT
  id,
  hazard_type,
  region_key,
  region_name,
  forecast_date,
  issue_time,
  horizon_hours,
  grid_size,
  bbox,
  status,
  publication_status,
  manifest_storage_ref,
  runout_storage_ref,
  compatibility_forecast_grid_id,
  active,
  model_metadata,
  weather_summary,
  forecast_bulletins,
  published_at,
  freshness_hours,
  created_at,
  updated_at
FROM public.forecast_runs
WHERE active = TRUE
  AND status = 'ready'
  AND publication_status = 'published';

-- Update trigger for compute_jobs
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_compute_jobs_updated_at ON public.compute_jobs;
CREATE TRIGGER update_compute_jobs_updated_at
  BEFORE UPDATE ON public.compute_jobs
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Update trigger for forecast_grids
CREATE OR REPLACE FUNCTION public.set_forecast_grids_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_forecast_grids_updated_at ON public.forecast_grids;
CREATE TRIGGER set_forecast_grids_updated_at
  BEFORE UPDATE ON public.forecast_grids
  FOR EACH ROW EXECUTE FUNCTION public.set_forecast_grids_updated_at();

-- Update trigger for forecast_runs
CREATE OR REPLACE FUNCTION public.set_forecast_runs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_forecast_runs_updated_at ON public.forecast_runs;
CREATE TRIGGER set_forecast_runs_updated_at
  BEFORE UPDATE ON public.forecast_runs
  FOR EACH ROW EXECUTE FUNCTION public.set_forecast_runs_updated_at();

-- Promote forecast run function
CREATE OR REPLACE FUNCTION public.promote_forecast_run(p_forecast_run_id UUID)
RETURNS public.forecast_runs
LANGUAGE plpgsql
AS $$
DECLARE
  target_row public.forecast_runs%ROWTYPE;
BEGIN
  SELECT * INTO target_row
  FROM public.forecast_runs
  WHERE id = p_forecast_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'forecast_run % not found', p_forecast_run_id;
  END IF;

  UPDATE public.forecast_runs
     SET active = FALSE,
         status = CASE WHEN id = p_forecast_run_id THEN status ELSE 'superseded' END
   WHERE hazard_type = target_row.hazard_type
     AND region_key = target_row.region_key
     AND active = TRUE
     AND id <> p_forecast_run_id;

  UPDATE public.forecast_runs
     SET active = TRUE,
         status = 'ready',
         publication_status = 'published',
         published_at = now()
   WHERE id = p_forecast_run_id
   RETURNING * INTO target_row;

  RETURN target_row;
END;
$$;

-- avalanche_events_decayed view (used by backend/common/training_dataset.py)
CREATE OR REPLACE VIEW public.avalanche_events_decayed AS
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

-- forecast_outcomes (used by AdminDashboard)
CREATE TABLE IF NOT EXISTS public.forecast_outcomes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_id UUID NOT NULL REFERENCES public.forecasts(id) ON DELETE CASCADE,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  cell_row INTEGER NOT NULL,
  cell_col INTEGER NOT NULL,
  forecast_hour INTEGER NOT NULL,
  predicted_risk_score INTEGER NOT NULL,
  predicted_hazard DOUBLE PRECISION NOT NULL,
  outcome_window_start TIMESTAMPTZ NOT NULL,
  outcome_window_end TIMESTAMPTZ NOT NULL,
  event_observed BOOLEAN NOT NULL DEFAULT FALSE,
  severity_label TEXT,
  distance_to_nearest_event_m DOUBLE PRECISION,
  nearest_event_id UUID REFERENCES public.avalanche_events(id),
  label_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  label_version TEXT NOT NULL DEFAULT 'v1.0.0',
  spatial_tolerance_m INTEGER NOT NULL DEFAULT 5000,
  temporal_tolerance_hours INTEGER NOT NULL DEFAULT 24,
  elevation_band_compatible BOOLEAN,
  excluded_from_training BOOLEAN NOT NULL DEFAULT FALSE,
  exclusion_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_forecast
  ON public.forecast_outcomes (forecast_id, forecast_hour);
CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_training
  ON public.forecast_outcomes (hazard_type, label_version, label_confidence, event_observed)
  WHERE excluded_from_training = FALSE AND label_confidence >= 0.7;
CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_window
  ON public.forecast_outcomes (outcome_window_start, outcome_window_end);

-- evaluation_runs (used by AdminDashboard)
CREATE TABLE IF NOT EXISTS public.evaluation_runs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  run_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  label_version TEXT NOT NULL,
  eval_start_date TIMESTAMPTZ NOT NULL,
  eval_end_date TIMESTAMPTZ NOT NULL,
  regions_evaluated TEXT[] NOT NULL DEFAULT '{}'::text[],
  overall_precision_risk3 DOUBLE PRECISION,
  overall_precision_risk4 DOUBLE PRECISION,
  overall_recall DOUBLE PRECISION,
  overall_false_alarm_rate DOUBLE PRECISION,
  overall_ece DOUBLE PRECISION,
  overall_brier_score DOUBLE PRECISION,
  threshold_profile_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_model
  ON public.evaluation_runs (hazard_type, model_version, created_at DESC);

-- evaluation_metrics (used by AdminDashboard)
CREATE TABLE IF NOT EXISTS public.evaluation_metrics (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  evaluation_run_id UUID NOT NULL REFERENCES public.evaluation_runs(id) ON DELETE CASCADE,
  slice_type TEXT NOT NULL,
  slice_value TEXT NOT NULL,
  total_forecasts INTEGER NOT NULL,
  total_cells INTEGER NOT NULL,
  observed_events INTEGER NOT NULL,
  precision_risk3 DOUBLE PRECISION,
  recall_risk3 DOUBLE PRECISION,
  f1_risk3 DOUBLE PRECISION,
  precision_risk4 DOUBLE PRECISION,
  recall_risk4 DOUBLE PRECISION,
  f1_risk4 DOUBLE PRECISION,
  ece DOUBLE PRECISION,
  reliability_data JSONB,
  false_alarm_rate DOUBLE PRECISION,
  false_positives INTEGER,
  true_positives INTEGER,
  risk_distribution JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_metrics_slice
  ON public.evaluation_metrics (evaluation_run_id, slice_type, slice_value);

-- forecast_analytics (used by AdminDashboard)
CREATE TABLE IF NOT EXISTS public.forecast_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  region_name TEXT,
  bbox NUMERIC[] DEFAULT '{}',
  risk_score FLOAT,
  hazard FLOAT,
  exposure FLOAT,
  vulnerability FLOAT,
  problem_type TEXT,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  avg_uncertainty DOUBLE PRECISION,
  model_version TEXT,
  calibration_profile_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_forecast_analytics_region_time
  ON public.forecast_analytics (region_name, timestamp DESC);
