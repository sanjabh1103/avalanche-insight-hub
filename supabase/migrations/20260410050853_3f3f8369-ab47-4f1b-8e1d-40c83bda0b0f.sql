
-- Enable extensions for scheduled jobs
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- Analytics table for tracking forecast runs and region usage
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

-- Index for time-based queries
CREATE INDEX idx_forecast_analytics_created ON public.forecast_analytics (created_at DESC);
