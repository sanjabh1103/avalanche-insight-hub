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
