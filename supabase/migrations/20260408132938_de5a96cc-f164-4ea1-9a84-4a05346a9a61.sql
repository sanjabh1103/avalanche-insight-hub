
-- Enable PostGIS
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

-- Insert default config row
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

-- Insert default model status
INSERT INTO public.model_status (version, f1_score) VALUES ('v1.0.0-sim', 0.847)
ON CONFLICT DO NOTHING;

-- Enable realtime for key tables
ALTER PUBLICATION supabase_realtime ADD TABLE public.compute_jobs;
ALTER PUBLICATION supabase_realtime ADD TABLE public.forecasts;
ALTER PUBLICATION supabase_realtime ADD TABLE public.avalanche_events;

-- Update trigger for compute_jobs
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
