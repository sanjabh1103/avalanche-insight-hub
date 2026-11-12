-- =====================================================
-- FOUNDATION: extensions, enums, and core tables
-- =====================================================

-- Enable PostGIS and uuid generation support
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis SCHEMA extensions;

-- Enums
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'event_type'
  ) THEN
    CREATE TYPE public.event_type AS ENUM ('slab', 'loose', 'wet', 'glide', 'cornice', 'unknown');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'report_status'
  ) THEN
    CREATE TYPE public.report_status AS ENUM ('pending', 'verified', 'rejected');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'job_type'
  ) THEN
    CREATE TYPE public.job_type AS ENUM ('forecast', 'daily_enrichment', 'sentinel_refresh', 'fine_tune', 'static_precompute', 'field_report_enrichment');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type WHERE typnamespace = 'public'::regnamespace AND typname = 'job_status'
  ) THEN
    CREATE TYPE public.job_status AS ENUM ('pending', 'running', 'completed', 'failed');
  END IF;
END $$;

-- avalanche_events
CREATE TABLE IF NOT EXISTS public.avalanche_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  location extensions.geography(Point, 4326),
  source TEXT,
  description TEXT,
  severity INT CHECK (severity BETWEEN 1 AND 5),
  event_type public.event_type DEFAULT 'unknown',
  features JSONB DEFAULT '{}'::jsonb,
  confidence FLOAT DEFAULT 0,
  fusion_source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.avalanche_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view events" ON public.avalanche_events;
DROP POLICY IF EXISTS "Service role can manage events" ON public.avalanche_events;
CREATE POLICY "Anyone can view events" ON public.avalanche_events FOR SELECT USING (true);
CREATE POLICY "Service role can manage events" ON public.avalanche_events FOR ALL USING (auth.role() = 'service_role');

-- forecasts
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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.forecasts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view forecasts" ON public.forecasts;
DROP POLICY IF EXISTS "Service role can manage forecasts" ON public.forecasts;
CREATE POLICY "Anyone can view forecasts" ON public.forecasts FOR SELECT USING (true);
CREATE POLICY "Service role can manage forecasts" ON public.forecasts FOR ALL USING (auth.role() = 'service_role');

-- field_reports
CREATE TABLE IF NOT EXISTS public.field_reports (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
  location extensions.geography(Point, 4326),
  image_url TEXT,
  description TEXT,
  status public.report_status DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.field_reports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can create reports" ON public.field_reports;
DROP POLICY IF EXISTS "Service role can manage reports" ON public.field_reports;
CREATE POLICY "Users can view their own reports" ON public.field_reports FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create reports" ON public.field_reports FOR INSERT WITH CHECK (user_id IS NULL OR auth.uid() = user_id);
CREATE POLICY "Service role can manage reports" ON public.field_reports FOR ALL USING (auth.role() = 'service_role');

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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.compute_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view jobs" ON public.compute_jobs;
DROP POLICY IF EXISTS "Service role can manage jobs" ON public.compute_jobs;
CREATE POLICY "Anyone can view jobs" ON public.compute_jobs FOR SELECT USING (true);
CREATE POLICY "Service role can manage jobs" ON public.compute_jobs FOR ALL USING (auth.role() = 'service_role');

-- system_config
CREATE TABLE IF NOT EXISTS public.system_config (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  gemini_usage INT DEFAULT 0,
  gemini_spend_cap INT DEFAULT 1000,
  last_enrichment TIMESTAMPTZ
);

ALTER TABLE public.system_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view config" ON public.system_config;
DROP POLICY IF EXISTS "Service role can manage config" ON public.system_config;
CREATE POLICY "Anyone can view config" ON public.system_config FOR SELECT USING (true);
CREATE POLICY "Service role can manage config" ON public.system_config FOR ALL USING (auth.role() = 'service_role');

INSERT INTO public.system_config (gemini_usage, gemini_spend_cap) VALUES (0, 1000)
ON CONFLICT DO NOTHING;

-- model_status
CREATE TABLE IF NOT EXISTS public.model_status (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  version TEXT DEFAULT 'v1.0.0',
  last_trained TIMESTAMPTZ,
  f1_score FLOAT DEFAULT 0.0,
  next_run TIMESTAMPTZ
);

ALTER TABLE public.model_status ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view model status" ON public.model_status;
DROP POLICY IF EXISTS "Service role can manage model status" ON public.model_status;
CREATE POLICY "Anyone can view model status" ON public.model_status FOR SELECT USING (true);
CREATE POLICY "Service role can manage model status" ON public.model_status FOR ALL USING (auth.role() = 'service_role');

INSERT INTO public.model_status (version, f1_score) VALUES ('v1.0.0-sim', 0.847)
ON CONFLICT DO NOTHING;

-- mountain_terrain
CREATE TABLE IF NOT EXISTS public.mountain_terrain (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lat double precision NOT NULL,
  lng double precision NOT NULL,
  elevation double precision NOT NULL DEFAULT 0,
  slope_angle double precision NOT NULL DEFAULT 0,
  aspect double precision NOT NULL DEFAULT 0,
  tpi double precision NOT NULL DEFAULT 0,
  twi double precision NOT NULL DEFAULT 0,
  curvature double precision NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_mountain_terrain_coords ON public.mountain_terrain (lat, lng);

ALTER TABLE public.mountain_terrain ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view terrain" ON public.mountain_terrain;
DROP POLICY IF EXISTS "Service role can manage terrain" ON public.mountain_terrain;
CREATE POLICY "Anyone can view terrain" ON public.mountain_terrain FOR SELECT USING (true);
CREATE POLICY "Service role can manage terrain" ON public.mountain_terrain FOR ALL USING (auth.role() = 'service_role');

-- forecast analytics and support for cron jobs
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

CREATE TABLE public.forecast_analytics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  region_name text,
  bbox numeric[] DEFAULT '{}',
  weather_source text DEFAULT 'simulation',
  avg_risk double precision DEFAULT 0,
  cell_count integer DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.forecast_analytics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view analytics" ON public.forecast_analytics
  FOR SELECT TO public USING (true);

CREATE POLICY "Service role can manage analytics" ON public.forecast_analytics
  FOR ALL TO public USING (auth.role() = 'service_role'::text);

CREATE INDEX idx_forecast_analytics_created ON public.forecast_analytics (created_at DESC);

CREATE TABLE public.user_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  endpoint text NOT NULL,
  p256dh text NOT NULL,
  auth_key text NOT NULL,
  region_bbox numeric[] DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can subscribe to alerts"
  ON public.user_alerts FOR INSERT
  TO public
  WITH CHECK (true);

CREATE POLICY "Service role can manage alerts"
  ON public.user_alerts FOR ALL
  TO public
  USING (auth.role() = 'service_role');

-- Update trigger helper used by compute_jobs
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

CREATE TRIGGER update_compute_jobs_updated_at
  BEFORE UPDATE ON public.compute_jobs
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER PUBLICATION supabase_realtime ADD TABLE public.compute_jobs;
ALTER PUBLICATION supabase_realtime ADD TABLE public.forecasts;
ALTER PUBLICATION supabase_realtime ADD TABLE public.avalanche_events;

-- =====================================================
-- FROM THIS POINT ON: later slices and calibration layers
-- =====================================================
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
  ADD COLUMN IF NOT EXISTS event_geom extensions.geometry(Geometry, 4326),
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
-- Slice 2: Event and report quality schema
-- Extends avalanche_events and field_reports with verification, label-role, and review fields

-- Add geometry index for avalanche_events (supports polygon events when available)
CREATE INDEX IF NOT EXISTS idx_avalanche_events_event_geom 
  ON public.avalanche_events USING GIST (event_geom) 
  WHERE event_geom IS NOT NULL;

-- Add verification status enum if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typnamespace = 'public'::regnamespace 
      AND typname = 'verification_status'
  ) THEN
    CREATE TYPE public.verification_status AS ENUM (
      'unverified',
      'weak',
      'verified', 
      'expert_verified'
    );
  END IF;
END $$;

-- Add label role enum if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typnamespace = 'public'::regnamespace 
      AND typname = 'label_role'
  ) THEN
    CREATE TYPE public.label_role AS ENUM (
      'training_label',
      'display_only',
      'excluded'
    );
  END IF;
END $$;

-- Add review status enum for field_reports
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type 
    WHERE typnamespace = 'public'::regnamespace 
      AND typname = 'review_status'
  ) THEN
    CREATE TYPE public.review_status AS ENUM (
      'pending',
      'under_review',
      'approved',
      'rejected',
      'needs_info'
    );
  END IF;
END $$;

-- Extend field_reports with quality and review fields
ALTER TABLE public.field_reports
  ADD COLUMN IF NOT EXISTS review_status public.review_status NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS normalized_event_type text,
  ADD COLUMN IF NOT EXISTS normalized_severity text,
  ADD COLUMN IF NOT EXISTS trigger_type text,
  ADD COLUMN IF NOT EXISTS terrain_context text,
  ADD COLUMN IF NOT EXISTS aspect text,
  ADD COLUMN IF NOT EXISTS elevation_m integer,
  ADD COLUMN IF NOT EXISTS snow_description text,
  ADD COLUMN IF NOT EXISTS confidence double precision,
  ADD COLUMN IF NOT EXISTS location_precision_m double precision,
  ADD COLUMN IF NOT EXISTS reporter_reliability_score double precision,
  ADD COLUMN IF NOT EXISTS dedupe_group_id uuid,
  ADD COLUMN IF NOT EXISTS normalization_version text,
  ADD COLUMN IF NOT EXISTS training_eligible boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS reviewed_by uuid REFERENCES auth.users(id),
  ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;

-- Create index for review queue
CREATE INDEX IF NOT EXISTS idx_field_reports_review_status 
  ON public.field_reports (review_status, created_at) 
  WHERE review_status IN ('pending', 'needs_info');

-- Create index for deduplication lookups
CREATE INDEX IF NOT EXISTS idx_field_reports_dedupe 
  ON public.field_reports (dedupe_group_id) 
  WHERE dedupe_group_id IS NOT NULL;

-- Create index for training-eligible reports
CREATE INDEX IF NOT EXISTS idx_field_reports_training 
  ON public.field_reports (training_eligible, created_at) 
  WHERE training_eligible = true;

-- Add constraints to avalanche_events verification/label fields
-- Note: These use the text columns added in migration 20260414130000
-- We need to update the default values to use the new enums properly

-- Add check constraint for verification_status text values
ALTER TABLE public.avalanche_events 
  DROP CONSTRAINT IF EXISTS chk_verification_status;
ALTER TABLE public.avalanche_events 
  ADD CONSTRAINT chk_verification_status 
  CHECK (verification_status IN ('unverified', 'weak', 'verified', 'expert_verified'));

-- Add check constraint for label_role text values  
ALTER TABLE public.avalanche_events 
  DROP CONSTRAINT IF EXISTS chk_label_role;
ALTER TABLE public.avalanche_events 
  ADD CONSTRAINT chk_label_role 
  CHECK (label_role IN ('training_label', 'display_only', 'excluded'));

-- Add check constraint for field_reports review_status
ALTER TABLE public.field_reports 
  DROP CONSTRAINT IF EXISTS chk_review_status;
ALTER TABLE public.field_reports 
  ADD CONSTRAINT chk_review_status 
  CHECK (review_status IN ('pending', 'under_review', 'approved', 'rejected', 'needs_info'));

-- Index for event quality filtering
CREATE INDEX IF NOT EXISTS idx_avalanche_events_label_quality 
  ON public.avalanche_events (label_role, verification_status, timestamp DESC) 
  WHERE label_role = 'training_label';

-- Comments for documentation
COMMENT ON COLUMN public.avalanche_events.verification_status IS 'Quality tier of event verification: unverified < weak < verified < expert_verified';
COMMENT ON COLUMN public.avalanche_events.label_role IS 'How this event should be used: training_label for ML, display_only for UI, excluded from both';
COMMENT ON COLUMN public.avalanche_events.event_geom IS 'Optional full geometry (polygon/line). Location remains centroid point for compatibility';
COMMENT ON COLUMN public.field_reports.review_status IS 'Workflow state for human review of field reports';
COMMENT ON COLUMN public.field_reports.training_eligible IS 'Whether this report can be used as a training signal (requires confidence threshold + review)';
COMMENT ON COLUMN public.field_reports.dedupe_group_id IS 'Links reports believed to describe the same event';
-- Slice 3: Forecast outcome labeling and evaluation harness
-- Adds tables for labeling forecasts against outcomes and systematic evaluation

-- Forecast outcomes: the labeled result of each forecast cell/hour against verified events
CREATE TABLE IF NOT EXISTS public.forecast_outcomes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_id uuid NOT NULL REFERENCES public.forecasts(id) ON DELETE CASCADE,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- Cell identification
  cell_row integer NOT NULL,
  cell_col integer NOT NULL,
  forecast_hour integer NOT NULL,
  
  -- Forecast snapshot at labeling time
  predicted_risk_score integer NOT NULL,
  predicted_hazard double precision NOT NULL,
  
  -- Outcome window (when we look for verifying events)
  outcome_window_start timestamptz NOT NULL,
  outcome_window_end timestamptz NOT NULL,
  
  -- Outcome labels
  event_observed boolean NOT NULL DEFAULT false,
  severity_label text, -- 'none', 'minor', 'moderate', 'severe', 'extreme'
  
  -- Spatial matching
  distance_to_nearest_event_m double precision,
  nearest_event_id uuid REFERENCES public.avalanche_events(id),
  
  -- Quality
  label_confidence double precision NOT NULL DEFAULT 0.5,
  label_version text NOT NULL DEFAULT 'v1.0.0',
  
  -- Matching parameters used (for reproducibility)
  spatial_tolerance_m integer NOT NULL DEFAULT 5000,
  temporal_tolerance_hours integer NOT NULL DEFAULT 24,
  elevation_band_compatible boolean,
  
  -- Exclusions
  excluded_from_training boolean NOT NULL DEFAULT false,
  exclusion_reason text,
  
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Composite index for efficient forecast lookups
CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_forecast 
  ON public.forecast_outcomes (forecast_id, forecast_hour);

-- Index for training set generation
CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_training 
  ON public.forecast_outcomes (hazard_type, label_version, label_confidence, event_observed) 
  WHERE excluded_from_training = false AND label_confidence >= 0.7;

-- Index for outcome analysis by time
CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_window 
  ON public.forecast_outcomes (outcome_window_start, outcome_window_end);

-- Evaluation runs: systematic backtesting results
CREATE TABLE IF NOT EXISTS public.evaluation_runs (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- Scope
  run_name text NOT NULL,
  model_version text NOT NULL,
  label_version text NOT NULL,
  
  -- Time range evaluated
  eval_start_date timestamptz NOT NULL,
  eval_end_date timestamptz NOT NULL,
  
  -- Regions included
  regions_evaluated text[] NOT NULL DEFAULT '{}',
  
  -- Overall metrics (computed from slice metrics)
  overall_precision_risk3 double precision,
  overall_precision_risk4 double precision,
  overall_recall double precision,
  overall_false_alarm_rate double precision,
  overall_ece double precision, -- Expected Calibration Error
  overall_brier_score double precision,
  
  -- Thresholds used
  threshold_profile_version text NOT NULL,
  
  -- Status
  status text NOT NULL DEFAULT 'running', -- 'running', 'completed', 'failed'
  error_message text,
  
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

-- Index for model version comparisons
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_model 
  ON public.evaluation_runs (hazard_type, model_version, created_at DESC);

-- Evaluation metrics by slice (region, season, elevation band)
CREATE TABLE IF NOT EXISTS public.evaluation_metrics (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  evaluation_run_id uuid NOT NULL REFERENCES public.evaluation_runs(id) ON DELETE CASCADE,
  
  -- Slice dimensions
  slice_type text NOT NULL, -- 'region', 'season', 'elevation_band', 'aspect', 'overall'
  slice_value text NOT NULL, -- e.g., 'Himalayas', 'winter', '3000-4000m'
  
  -- Sample size
  total_forecasts integer NOT NULL,
  total_cells integer NOT NULL,
  observed_events integer NOT NULL,
  
  -- Metrics at risk >= 3 threshold
  precision_risk3 double precision,
  recall_risk3 double precision,
  f1_risk3 double precision,
  
  -- Metrics at risk >= 4 threshold  
  precision_risk4 double precision,
  recall_risk4 double precision,
  f1_risk4 double precision,
  
  -- Calibration
  ece double precision, -- Expected Calibration Error
  reliability_data jsonb, -- Binned reliability curve data
  
  -- False alarm analysis
  false_alarm_rate double precision,
  false_positives integer,
  true_positives integer,
  
  -- Risk distribution
  risk_distribution jsonb, -- {1: count, 2: count, ...}
  
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Index for slice comparisons
CREATE INDEX IF NOT EXISTS idx_evaluation_metrics_slice 
  ON public.evaluation_metrics (evaluation_run_id, slice_type, slice_value);

-- Model registry: track candidate and incumbent models
CREATE TABLE IF NOT EXISTS public.model_registry (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- Model identification
  model_version text NOT NULL UNIQUE,
  model_type text NOT NULL DEFAULT 'heuristic', -- 'heuristic', 'supervised', 'ensemble'
  
  -- Training context
  training_dataset_version text,
  training_run_id text,
  feature_version text NOT NULL,
  
  -- Performance at training time
  training_precision double precision,
  training_recall double precision,
  training_f1 double precision,
  
  -- Status
  status text NOT NULL DEFAULT 'candidate', -- 'candidate', 'challenger', 'incumbent', 'retired'
  
  -- Activation decision
  activated_at timestamptz,
  activated_by uuid REFERENCES auth.users(id),
  activation_evaluation_run_id uuid REFERENCES public.evaluation_runs(id),
  
  -- Rollback tracking
  retired_at timestamptz,
  retired_reason text,
  superseded_by_version text,
  
  -- Artifacts
  model_artifact_url text,
  feature_importance jsonb,
  
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Index for model status
CREATE INDEX IF NOT EXISTS idx_model_registry_status 
  ON public.model_registry (hazard_type, status, created_at DESC);

-- Active learning queue: uncertain cases needing review
CREATE TABLE IF NOT EXISTS public.active_learning_queue (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- The uncertain forecast
  forecast_id uuid NOT NULL REFERENCES public.forecasts(id),
  forecast_outcome_id uuid REFERENCES public.forecast_outcomes(id),
  
  -- Why it's in the queue
  reason text NOT NULL, -- 'high_uncertainty', 'prediction_conflict', 'sparse_labels', 'region_gaps'
  priority_score double precision NOT NULL DEFAULT 0.5,
  
  -- Context
  predicted_risk integer,
  uncertainty_score double precision,
  
  -- Review workflow
  review_status text NOT NULL DEFAULT 'pending', -- 'pending', 'assigned', 'resolved'
  assigned_to uuid REFERENCES auth.users(id),
  resolution text, -- 'verified_event', 'verified_nonevent', 'ambiguous', 'excluded'
  resolution_notes text,
  
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

-- Index for priority queue
CREATE INDEX IF NOT EXISTS idx_active_learning_queue 
  ON public.active_learning_queue (hazard_type, review_status, priority_score DESC) 
  WHERE review_status = 'pending';

-- Label matching policy: versioned parameters for how forecasts are matched to events
CREATE TABLE IF NOT EXISTS public.label_matching_policies (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  policy_version text NOT NULL UNIQUE,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- Spatial matching
  spatial_tolerance_m integer NOT NULL DEFAULT 5000,
  elevation_band_width_m integer NOT NULL DEFAULT 500,
  elevation_flexibility_m integer NOT NULL DEFAULT 300,
  
  -- Temporal matching
  temporal_tolerance_hours integer NOT NULL DEFAULT 24,
  lead_time_discount_factor double precision NOT NULL DEFAULT 0.8,
  
  -- Quality gates
  min_event_verification text NOT NULL DEFAULT 'weak', -- events below this are ignored
  min_forecast_confidence double precision NOT NULL DEFAULT 0.5,
  
  -- Exclusions
  exclude_manual_events boolean NOT NULL DEFAULT false,
  exclude_unverified_reports boolean NOT NULL DEFAULT true,
  
  -- Documentation
  description text,
  created_by uuid REFERENCES auth.users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- RLS policies
ALTER TABLE public.forecast_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evaluation_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.active_learning_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.label_matching_policies ENABLE ROW LEVEL SECURITY;

-- Public read access for outcomes
CREATE POLICY "Public read forecast_outcomes" 
  ON public.forecast_outcomes FOR SELECT TO public USING (true);

-- Admin-only for evaluation runs
CREATE POLICY "Admin full access evaluation_runs"
  ON public.evaluation_runs FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access evaluation_metrics"
  ON public.evaluation_metrics FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access model_registry"
  ON public.model_registry FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access active_learning_queue"
  ON public.active_learning_queue FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access label_matching_policies"
  ON public.label_matching_policies FOR ALL TO public 
  USING (auth.role() = 'service_role');

-- Insert default label matching policy
INSERT INTO public.label_matching_policies (policy_version, description)
VALUES ('v1.0.0', 'Initial default policy: 5km spatial, 24h temporal, weak+ events')
ON CONFLICT (policy_version) DO NOTHING;

-- Comments
COMMENT ON TABLE public.forecast_outcomes IS 'Labeled results of forecast cells matched against verified events';
COMMENT ON TABLE public.evaluation_runs IS 'Systematic backtesting runs comparing model performance';
COMMENT ON TABLE public.evaluation_metrics IS 'Performance metrics stratified by region, season, elevation';
COMMENT ON TABLE public.model_registry IS 'Versioned model artifacts with activation/rollback tracking';
COMMENT ON TABLE public.active_learning_queue IS 'Priority queue of uncertain forecasts needing human review';
COMMENT ON TABLE public.label_matching_policies IS 'Versioned parameters for forecast-to-event matching';
-- Slice 4: Feature enrichment schema
-- Snow-cover snapshots and recent-activity materialized features

-- Snow cover snapshots: lightweight summary features for forecast nudging
CREATE TABLE IF NOT EXISTS public.snow_cover_snapshots (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  
  -- Temporal
  captured_at timestamptz NOT NULL,
  valid_for_region text NOT NULL, -- region identifier or 'global'
  
  -- Spatial coverage
  bbox double precision[4] NOT NULL, -- [minLng, minLat, maxLng, maxLat]
  
  -- Summary statistics (not raw raster - that's the lightweight constraint)
  coverage_ratio double precision, -- 0-1 snow-covered fraction
  
  -- Elevation band breakdown
  elevation_band_stats jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Example: {
  --   "0-1000": {"coverage": 0.1, "source_pixels": 42},
  --   "1000-2000": {"coverage": 0.4, "source_pixels": 156},
  --   ...
  -- }
  
  -- Data lineage
  source text NOT NULL DEFAULT 'gibs', -- 'gibs', 'modis_nsidc', 'viirs', 'simulated'
  source_layer text, -- e.g., 'MODIS_Terra_L3_NDSI_Snow_Cover_Daily'
  source_url text,
  quality_score double precision, -- 0-1 confidence in this snapshot
  
  -- Processing metadata
  processing_version text NOT NULL DEFAULT 'v1.0.0',
  ingestion_job_id uuid REFERENCES public.compute_jobs(id),
  
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Index for region-time lookups
CREATE INDEX IF NOT EXISTS idx_snow_cover_snapshots_region_time 
  ON public.snow_cover_snapshots (valid_for_region, captured_at DESC);

-- Index for bbox queries (approximate via GiST on point centroid if needed later)
CREATE INDEX IF NOT EXISTS idx_snow_cover_snapshots_captured 
  ON public.snow_cover_snapshots (captured_at DESC) 
  WHERE source != 'simulated';

-- Recent activity features: materialized per-region summaries for fast forecast joins
CREATE TABLE IF NOT EXISTS public.recent_activity_features (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  
  -- Region/cell identification
  region_name text NOT NULL,
  cell_row integer, -- NULL for region-level summary
  cell_col integer, -- NULL for region-level summary
  
  -- Time window
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  window_days integer NOT NULL DEFAULT 7,
  
  -- Event counts (weighted by quality and recency)
  total_event_count integer NOT NULL DEFAULT 0,
  verified_event_count integer NOT NULL DEFAULT 0,
  training_eligible_count integer NOT NULL DEFAULT 0,
  
  -- Severity-weighted activity (recency-decayed)
  weighted_severity_sum double precision NOT NULL DEFAULT 0,
  max_severity_in_window integer,
  
  -- Spatial spread
  event_density_per_km2 double precision,
  unique_aspect_buckets text[],
  elevation_range_m jsonb, -- {min: 2000, max: 4500}
  
  -- Source breakdown
  sources jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Example: {"field_report": 3, "news_enrichment": 2, "sentinel": 0}
  
  -- Quality
  data_completeness_score double precision NOT NULL DEFAULT 1.0,
  
  -- Materialization metadata
  materialized_at timestamptz NOT NULL DEFAULT now(),
  materialization_job_id uuid REFERENCES public.compute_jobs(id),
  
  UNIQUE(region_name, cell_row, cell_col, window_start, window_end)
);

-- Index for forecast-time lookups
CREATE INDEX IF NOT EXISTS idx_recent_activity_features_lookup 
  ON public.recent_activity_features (region_name, window_end DESC, cell_row, cell_col);

-- Feature completeness audit: tracks what inputs were available for each forecast
CREATE TABLE IF NOT EXISTS public.feature_completeness_log (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_id uuid NOT NULL REFERENCES public.forecasts(id) ON DELETE CASCADE,
  
  -- Input availability (was this feature available?)
  weather_available boolean NOT NULL DEFAULT false,
  weather_source text,
  weather_freshness_hours integer,
  
  snow_cover_available boolean NOT NULL DEFAULT false,
  snow_cover_snapshot_id uuid REFERENCES public.snow_cover_snapshots(id),
  snow_cover_age_hours integer,
  
  recent_activity_available boolean NOT NULL DEFAULT false,
  recent_activity_feature_id uuid REFERENCES public.recent_activity_features(id),
  recent_activity_window_days integer,
  
  terrain_available boolean NOT NULL DEFAULT true, -- usually always available
  
  -- Completeness score (0-1)
  overall_completeness double precision NOT NULL,
  
  -- Missing feature flags
  missing_features text[] NOT NULL DEFAULT '{}',
  
  logged_at timestamptz NOT NULL DEFAULT now()
);

-- RLS policies
ALTER TABLE public.snow_cover_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recent_activity_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feature_completeness_log ENABLE ROW LEVEL SECURITY;

-- Public read access
CREATE POLICY "Public read snow_cover_snapshots" 
  ON public.snow_cover_snapshots FOR SELECT TO public USING (true);

CREATE POLICY "Public read recent_activity_features"
  ON public.recent_activity_features FOR SELECT TO public USING (true);

CREATE POLICY "Public read feature_completeness_log"
  ON public.feature_completeness_log FOR SELECT TO public USING (true);

-- Service role for writes
CREATE POLICY "Service role write snow_cover_snapshots"
  ON public.snow_cover_snapshots FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Service role write recent_activity_features"
  ON public.recent_activity_features FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Service role write feature_completeness_log"
  ON public.feature_completeness_log FOR ALL TO public 
  USING (auth.role() = 'service_role');

-- Comments
COMMENT ON TABLE public.snow_cover_snapshots IS 'Lightweight snow-cover summary features (not raw raster) for forecast nudging';
COMMENT ON TABLE public.recent_activity_features IS 'Pre-computed recent event activity by region/cell for fast forecast joins';
COMMENT ON TABLE public.feature_completeness_log IS 'Audit trail of which features were available for each forecast';

ALTER TABLE public.feature_completeness_log
  ALTER COLUMN forecast_id DROP NOT NULL;

ALTER TABLE public.feature_completeness_log
  ADD COLUMN IF NOT EXISTS forecast_grid_id uuid REFERENCES public.forecast_grids(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS forecast_run_id uuid REFERENCES public.forecast_runs(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_feature_completeness_log_forecast_grid_id
  ON public.feature_completeness_log (forecast_grid_id);

CREATE INDEX IF NOT EXISTS idx_feature_completeness_log_forecast_run_id
  ON public.feature_completeness_log (forecast_run_id);
-- Slice 5: Calibration and promotion controls
-- Regional calibration profiles and threshold profiles with activation workflow

-- Regional calibration profiles: per-region scoring adjustments
CREATE TABLE IF NOT EXISTS public.calibration_profiles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  profile_version text NOT NULL UNIQUE,
  
  -- Scope
  region_name text NOT NULL, -- 'Himalayas', 'Alps', 'Rockies', or 'global-default'
  season_window text, -- 'winter', 'spring', 'all' or NULL for year-round
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- Feature adjustments (multipliers applied to base model)
  feature_scalars jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Example: {
  --   "snowfall_24h": 1.2,    -- weight snowfall more in maritime climates
  --   "wind_loading": 0.9,    -- weight wind less in some terrain
  --   "elevation": 1.0
  -- }
  
  -- Uncertainty scaling
  uncertainty_base double precision NOT NULL DEFAULT 0.2,
  uncertainty_per_missing_feature double precision NOT NULL DEFAULT 0.15,
  
  -- Post-processing rules
  post_processing_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Example: {
  --   "min_elevation_for_risk4": 2500,
  --   "max_risk_in_low_slope": 3,
  --   "boost_recent_activity_window_hours": 48
  -- }
  
  -- Documentation
  description text,
  trained_on_evaluation_run_id uuid REFERENCES public.evaluation_runs(id),
  
  -- Status
  status text NOT NULL DEFAULT 'draft', -- 'draft', 'approved', 'active', 'retired'
  approved_by uuid REFERENCES auth.users(id),
  approved_at timestamptz,
  
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Index for active profile lookup
CREATE INDEX IF NOT EXISTS idx_calibration_profiles_active 
  ON public.calibration_profiles (hazard_type, region_name, season_window, status) 
  WHERE status = 'active';

-- Index for version history
CREATE INDEX IF NOT EXISTS idx_calibration_profiles_region 
  ON public.calibration_profiles (region_name, created_at DESC);

-- Threshold profiles: risk band mapping from raw scores
CREATE TABLE IF NOT EXISTS public.threshold_profiles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  profile_version text NOT NULL UNIQUE,
  
  -- Scope
  region_name text NOT NULL DEFAULT 'global',
  season_window text DEFAULT 'all',
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  
  -- Documentation
  description text,
  
  -- Threshold definitions (raw score 0-1 to risk 1-5)
  -- Using explicit columns for type safety and clarity
  risk_1_max double precision NOT NULL DEFAULT 0.20, -- score <= this = risk 1
  risk_2_max double precision NOT NULL DEFAULT 0.40,
  risk_3_max double precision NOT NULL DEFAULT 0.60,
  risk_4_max double precision NOT NULL DEFAULT 0.80,
  -- risk 5 is > risk_4_max
  
  -- Alert thresholds (when to flag as concerning)
  alert_threshold_risk integer NOT NULL DEFAULT 3, -- flag risk >= 3
  severe_alert_threshold_risk integer NOT NULL DEFAULT 4, -- flag risk >= 4
  
  -- Calibration method
  calibration_method text NOT NULL DEFAULT 'percentile', -- 'percentile', 'expert', 'optimization'
  
  -- Performance when these thresholds were set
  expected_precision_risk3 double precision,
  expected_recall_risk3 double precision,
  expected_false_alarm_rate double precision,
  
  -- Source evaluation
  derived_from_evaluation_run_id uuid REFERENCES public.evaluation_runs(id),
  
  -- Status workflow
  status text NOT NULL DEFAULT 'draft',
  approved_by uuid REFERENCES auth.users(id),
  approved_at timestamptz,
  
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Index for active thresholds
CREATE INDEX IF NOT EXISTS idx_threshold_profiles_active 
  ON public.threshold_profiles (hazard_type, region_name, season_window, status) 
  WHERE status = 'active';

-- Promotion audit log: track model/threshold promotions and rollbacks
CREATE TABLE IF NOT EXISTS public.promotion_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  
  -- What was promoted
  event_type text NOT NULL, -- 'model', 'calibration_profile', 'threshold_profile'
  previous_version text,
  new_version text NOT NULL,
  
  -- Scope
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  region_name text,
  
  -- Evidence
  evaluation_run_id uuid REFERENCES public.evaluation_runs(id),
  triggering_metrics jsonb NOT NULL, -- {precision: 0.72, recall: 0.68, ...}
  
  -- Decision
  decision text NOT NULL, -- 'promote', 'rollback', 'reject'
  decision_reason text,
  decided_by uuid REFERENCES auth.users(id),
  
  -- Automatic vs manual
  automatic boolean NOT NULL DEFAULT false,
  
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Index for audit trail
CREATE INDEX IF NOT EXISTS idx_promotion_events_audit 
  ON public.promotion_events (hazard_type, event_type, created_at DESC);

-- Rollback state: allows reverting to previous working configuration
CREATE TABLE IF NOT EXISTS public.rollback_state (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  
  -- Current active versions at time of snapshot
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  region_name text NOT NULL DEFAULT 'global',
  
  model_version text,
  calibration_profile_version text,
  threshold_profile_version text,
  
  -- Performance at snapshot time
  snapshot_metrics jsonb,
  
  -- Rollback triggers
  can_rollback_to boolean NOT NULL DEFAULT true,
  rolled_back_at timestamptz,
  rolled_back_by uuid REFERENCES auth.users(id),
  
  created_at timestamptz NOT NULL DEFAULT now()
);

-- RLS policies
ALTER TABLE public.calibration_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.threshold_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rollback_state ENABLE ROW LEVEL SECURITY;

-- Public read for active profiles
CREATE POLICY "Public read active calibration_profiles"
  ON public.calibration_profiles FOR SELECT TO public 
  USING (status = 'active');

CREATE POLICY "Public read active threshold_profiles"
  ON public.threshold_profiles FOR SELECT TO public 
  USING (status = 'active');

-- Admin access for all profile operations
CREATE POLICY "Admin full access calibration_profiles"
  ON public.calibration_profiles FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access threshold_profiles"
  ON public.threshold_profiles FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access promotion_events"
  ON public.promotion_events FOR ALL TO public 
  USING (auth.role() = 'service_role');

CREATE POLICY "Admin full access rollback_state"
  ON public.rollback_state FOR ALL TO public 
  USING (auth.role() = 'service_role');

-- Insert default global profiles
INSERT INTO public.calibration_profiles (
  profile_version, region_name, season_window, description, status
) VALUES (
  'global-default-v1', 'global', 'all', 
  'Initial global calibration with no regional adjustments', 
  'active'
)
ON CONFLICT (profile_version) DO NOTHING;

INSERT INTO public.threshold_profiles (
  profile_version, region_name, season_window, 
  risk_1_max, risk_2_max, risk_3_max, risk_4_max,
  description, status
) VALUES (
  'heuristic-risk-bands-v1', 'global', 'all',
  0.20, 0.40, 0.60, 0.80,
  'Initial heuristic thresholds: 20/40/60/80 percentiles',
  'active'
)
ON CONFLICT (profile_version) DO NOTHING;

-- Comments
COMMENT ON TABLE public.calibration_profiles IS 'Per-region feature weight and uncertainty adjustments';
COMMENT ON TABLE public.threshold_profiles IS 'Risk band thresholds and alert criteria';
COMMENT ON TABLE public.promotion_events IS 'Audit log of model/profile activations and rollbacks';
COMMENT ON TABLE public.rollback_state IS 'Snapshots of working configurations for emergency rollback';

-- Phase 0 evaluation contract hardening for MVP post-demo roadmap.
-- Persists slice metadata in forecast_outcomes and carries training
-- eligibility reasons through the labeler RPC for auditability.

ALTER TABLE public.forecast_outcomes
  ADD COLUMN IF NOT EXISTS cell_elevation_m double precision,
  ADD COLUMN IF NOT EXISTS sar_coverage_state text,
  ADD COLUMN IF NOT EXISTS dry_wet_domain text,
  ADD COLUMN IF NOT EXISTS problem_slug text,
  ADD COLUMN IF NOT EXISTS training_eligible_reason text;

CREATE INDEX IF NOT EXISTS idx_forecast_outcomes_eval_slice_fields
  ON public.forecast_outcomes (
    hazard_type,
    created_at DESC,
    sar_coverage_state,
    dry_wet_domain,
    problem_slug
  );

COMMENT ON COLUMN public.forecast_outcomes.cell_elevation_m IS
  'Persisted terrain elevation for the labeled forecast cell so evaluation slices do not infer elevation from grid row.';
COMMENT ON COLUMN public.forecast_outcomes.sar_coverage_state IS
  'Forecast-cell SAR coverage state propagated from coverage_flags for evaluation slices.';
COMMENT ON COLUMN public.forecast_outcomes.dry_wet_domain IS
  'Forecast-cell wet/dry domain from the avalanche problem classifier.';
COMMENT ON COLUMN public.forecast_outcomes.problem_slug IS
  'Forecast-cell avalanche problem slug from the problem classifier.';
COMMENT ON COLUMN public.forecast_outcomes.training_eligible_reason IS
  'Matched-event training eligibility reason preserved for evaluation and audits.';

DROP FUNCTION IF EXISTS public.fetch_labeler_events(
  text,
  timestamptz,
  timestamptz,
  double precision,
  double precision,
  double precision,
  double precision,
  integer,
  integer
);

CREATE OR REPLACE FUNCTION public.fetch_labeler_events(
  p_hazard_type text,
  p_window_start timestamptz,
  p_window_end timestamptz,
  p_bbox_min_lng double precision,
  p_bbox_min_lat double precision,
  p_bbox_max_lng double precision,
  p_bbox_max_lat double precision,
  p_min_verification_rank integer DEFAULT 0,
  p_limit integer DEFAULT 200
)
RETURNS TABLE (
  id uuid,
  "timestamp" timestamptz,
  severity integer,
  verification_status text,
  elevation_m double precision,
  label_role text,
  training_eligible_reason text,
  lng double precision,
  lat double precision
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  RETURN QUERY
  WITH ranked AS (
    SELECT
      e.id,
      e.timestamp,
      e.severity,
      e.verification_status::text AS verification_status,
      e.elevation_m,
      e.label_role::text AS label_role,
      e.training_eligible_reason,
      extensions.ST_X(e.location::extensions.geometry) AS lng,
      extensions.ST_Y(e.location::extensions.geometry) AS lat,
      CASE e.verification_status::text
        WHEN 'expert_verified' THEN 3
        WHEN 'verified' THEN 2
        WHEN 'weak' THEN 1
        ELSE 0
      END AS verification_rank
    FROM public.avalanche_events e
    WHERE e.hazard_type::text = p_hazard_type
      AND e.timestamp >= p_window_start
      AND e.timestamp <= p_window_end
      AND (e.label_role IS NULL OR e.label_role::text <> 'excluded')
      AND e.location IS NOT NULL
      AND extensions.ST_Intersects(
        e.location::extensions.geometry,
        extensions.ST_MakeEnvelope(
          p_bbox_min_lng,
          p_bbox_min_lat,
          p_bbox_max_lng,
          p_bbox_max_lat,
          4326
        )
      )
  )
  SELECT
    ranked.id,
    ranked.timestamp,
    ranked.severity,
    ranked.verification_status,
    ranked.elevation_m,
    ranked.label_role,
    ranked.training_eligible_reason,
    ranked.lng,
    ranked.lat
  FROM ranked
  WHERE ranked.verification_rank >= p_min_verification_rank
  ORDER BY ranked.timestamp DESC
  LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION public.fetch_labeler_events IS
  'Phase 0: bbox+time-window narrowed event fetch for forecast outcome labeler, including training_eligible_reason for audit slices.';

GRANT EXECUTE ON FUNCTION public.fetch_labeler_events TO service_role, authenticated, anon;

-- Candidate-vs-active control-plane state
ALTER TABLE public.model_status
  ADD COLUMN IF NOT EXISTS dynamic_model_candidate JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS autonomous_evidence_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS stability_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS drift_mode_state text,
  ADD COLUMN IF NOT EXISTS latest_benchmark_summary JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.forecast_runs
  ADD COLUMN IF NOT EXISTS forecast_bulletins JSONB NOT NULL DEFAULT '{}'::jsonb;

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
  published_at,
  created_at,
  updated_at,
  forecast_bulletins
FROM public.forecast_runs
WHERE active = TRUE
  AND status = 'ready'
  AND publication_status = 'published';
