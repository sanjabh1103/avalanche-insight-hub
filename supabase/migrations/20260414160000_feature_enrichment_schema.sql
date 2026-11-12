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
