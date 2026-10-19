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
