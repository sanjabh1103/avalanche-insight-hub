-- Wave A: Continuous verification spine tables.
-- Adds narrow, additive tables for verification baselines, anomalies,
-- remote sensing scenes, and review queue. RLS-enabled, read-only public.

CREATE TABLE IF NOT EXISTS public.verification_baselines (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  region_key TEXT NOT NULL,
  cell_id TEXT NOT NULL,
  sensor TEXT NOT NULL,
  "window" TEXT NOT NULL CHECK ("window" IN ('30d', '90d', 'seasonal')),
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  control_cell_ids TEXT[] NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (region_key, cell_id, sensor, "window")
);

ALTER TABLE public.verification_baselines ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view verification baselines" ON public.verification_baselines;
DROP POLICY IF EXISTS "Service role can manage verification baselines" ON public.verification_baselines;
CREATE POLICY "Anyone can view verification baselines" ON public.verification_baselines FOR SELECT USING (true);
CREATE POLICY "Service role can manage verification baselines" ON public.verification_baselines FOR ALL USING (auth.role() = 'service_role');

CREATE OR REPLACE FUNCTION public.set_verification_baselines_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_verification_baselines_updated_at ON public.verification_baselines;
CREATE TRIGGER trg_verification_baselines_updated_at
  BEFORE UPDATE ON public.verification_baselines
  FOR EACH ROW
  EXECUTE FUNCTION public.set_verification_baselines_updated_at();


CREATE TABLE IF NOT EXISTS public.verification_anomalies (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  region_key TEXT NOT NULL,
  run_id TEXT,
  cell_id TEXT NOT NULL,
  discrepancy_type TEXT NOT NULL CHECK (discrepancy_type IN (
    'sar_loading_optical_bare',
    'optical_snow_sar_dry',
    'weather_snow_no_snowcover',
    'rapid_loading_anomaly',
    'rapid_melt_anomaly'
  )),
  severity FLOAT NOT NULL DEFAULT 0.0,
  zscore FLOAT,
  sources JSONB NOT NULL DEFAULT '[]'::jsonb,
  attribution_bucket TEXT NOT NULL DEFAULT 'unattributed' CHECK (attribution_bucket IN (
    'forcing_error',
    'sensing_gap',
    'physics_model_bias',
    'terrain_transfer_error',
    'threshold_miscalibration',
    'unattributed'
  )),
  attribution_confidence FLOAT NOT NULL DEFAULT 0.0,
  review_state TEXT NOT NULL DEFAULT 'pending' CHECK (review_state IN (
    'pending', 'reviewed', 'dismissed', 'promoted'
  )),
  reviewer_id UUID,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.verification_anomalies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view verification anomalies" ON public.verification_anomalies;
DROP POLICY IF EXISTS "Service role can manage verification anomalies" ON public.verification_anomalies;
CREATE POLICY "Anyone can view verification anomalies" ON public.verification_anomalies FOR SELECT USING (true);
CREATE POLICY "Service role can manage verification anomalies" ON public.verification_anomalies FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_verification_anomalies_region_cell
  ON public.verification_anomalies (region_key, cell_id);
CREATE INDEX IF NOT EXISTS idx_verification_anomalies_review_state
  ON public.verification_anomalies (review_state);


CREATE TABLE IF NOT EXISTS public.remote_sensing_scenes (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  region_key TEXT NOT NULL,
  sensor TEXT NOT NULL,
  scene_id TEXT NOT NULL,
  orbit TEXT,
  acquisition_time TIMESTAMPTZ,
  cloud_cover FLOAT,
  coverage_state TEXT,
  eecu_cost FLOAT,
  task_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (region_key, sensor, scene_id)
);

ALTER TABLE public.remote_sensing_scenes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view remote sensing scenes" ON public.remote_sensing_scenes;
DROP POLICY IF EXISTS "Service role can manage remote sensing scenes" ON public.remote_sensing_scenes;
CREATE POLICY "Anyone can view remote sensing scenes" ON public.remote_sensing_scenes FOR SELECT USING (true);
CREATE POLICY "Service role can manage remote sensing scenes" ON public.remote_sensing_scenes FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_remote_sensing_scenes_region_sensor
  ON public.remote_sensing_scenes (region_key, sensor, acquisition_time DESC);


CREATE TABLE IF NOT EXISTS public.verification_review_queue (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  region_key TEXT NOT NULL,
  cell_id TEXT NOT NULL,
  anomaly_id UUID REFERENCES public.verification_anomalies(id) ON DELETE CASCADE,
  priority FLOAT NOT NULL DEFAULT 0.0,
  review_state TEXT NOT NULL DEFAULT 'pending' CHECK (review_state IN (
    'pending', 'assigned', 'completed', 'skipped'
  )),
  assigned_to UUID,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.verification_review_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view verification review queue" ON public.verification_review_queue;
DROP POLICY IF EXISTS "Service role can manage verification review queue" ON public.verification_review_queue;
CREATE POLICY "Anyone can view verification review queue" ON public.verification_review_queue FOR SELECT USING (true);
CREATE POLICY "Service role can manage verification review queue" ON public.verification_review_queue FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_verification_review_queue_state_priority
  ON public.verification_review_queue (review_state, priority DESC);

CREATE OR REPLACE FUNCTION public.set_verification_review_queue_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_verification_review_queue_updated_at ON public.verification_review_queue;
CREATE TRIGGER trg_verification_review_queue_updated_at
  BEFORE UPDATE ON public.verification_review_queue
  FOR EACH ROW
  EXECUTE FUNCTION public.set_verification_review_queue_updated_at();
