-- Add location_name support to avalanche_events for richer popups (BUG-05/06)
-- The features JSONB column already exists and can store location_name
-- This migration ensures the column has a GIN index for fast lookups

-- Add GIN index on features for location_name queries
CREATE INDEX IF NOT EXISTS idx_avalanche_events_features 
ON public.avalanche_events USING gin (features);

-- Add comment documenting the features.location_name convention
COMMENT ON COLUMN public.avalanche_events.features IS 
'JSONB metadata including location_name, extracted_by, etc. location_name is set by Gemini enrichment for news events.';
