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
