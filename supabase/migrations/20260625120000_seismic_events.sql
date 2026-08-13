-- F1: Seismic Cascade Integrator — seismic_events table for earthquake persistence
-- Stores USGS earthquake events for Himalayan regions. Used by daily_inference.py
-- to apply post-tremor risk amplification based on Shekhar et al. 2026 temporal windows.

CREATE TABLE IF NOT EXISTS public.seismic_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  usgs_id TEXT UNIQUE NOT NULL,
  magnitude DECIMAL NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  location extensions.geography(Point, 4326),
  depth_km DECIMAL,
  place TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE POLICY "Public read access for seismic events"
  ON public.seismic_events FOR SELECT USING (true);

CREATE POLICY "Service role can manage seismic events"
  ON public.seismic_events FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_seismic_events_timestamp
  ON public.seismic_events (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_seismic_events_magnitude
  ON public.seismic_events (magnitude DESC);
