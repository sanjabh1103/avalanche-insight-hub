
CREATE TABLE public.mountain_terrain (
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

CREATE POLICY "Anyone can view terrain" ON public.mountain_terrain FOR SELECT USING (true);
CREATE POLICY "Service role can manage terrain" ON public.mountain_terrain FOR ALL USING (auth.role() = 'service_role');

ALTER TABLE public.forecasts ADD COLUMN IF NOT EXISTS hourly_grids jsonb DEFAULT '[]'::jsonb;

ALTER TABLE public.model_status ADD COLUMN IF NOT EXISTS last_inference timestamptz;
ALTER TABLE public.model_status ADD COLUMN IF NOT EXISTS data_freshness_hours double precision DEFAULT 0;
