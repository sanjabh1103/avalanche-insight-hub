-- ============================================================================
-- HOSTED SUPABASE SQL APPLY SCRIPT - Avalanche Insight Hub
-- Run this in Supabase Dashboard → SQL Editor → New Query → Paste → Run
-- ============================================================================

-- =============================================================================
-- STEP 1: Verify Extensions (PostGIS, pg_cron, pg_net, pgcrypto)
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS postgis SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- STEP 2: Fix field_reports RLS for Anonymous Submit (BUG-003)
-- =============================================================================
-- The critical fix: allow anonymous users to submit field reports
-- This enables the Groundsource loop

-- Drop restrictive policies
DROP POLICY IF EXISTS "Users can create reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can view their own reports" ON public.field_reports;

-- Allow ANYONE to insert field reports (anon + authenticated)
CREATE POLICY "Allow anonymous insert" 
  ON public.field_reports 
  FOR INSERT 
  TO anon, authenticated
  WITH CHECK (true);

-- Allow authenticated users to view their own reports
CREATE POLICY "Users can view own reports" 
  ON public.field_reports 
  FOR SELECT 
  TO authenticated 
  USING (auth.uid() = user_id);

-- Allow anonymous users to view ALL reports (for map display)
CREATE POLICY "Allow anonymous select" 
  ON public.field_reports 
  FOR SELECT 
  TO anon 
  USING (true);

-- Service role can manage all reports
DROP POLICY IF EXISTS "Service role can manage reports" ON public.field_reports;
CREATE POLICY "Service role can manage reports" 
  ON public.field_reports 
  FOR ALL 
  USING (auth.role() = 'service_role');

-- =============================================================================
-- STEP 3: Add Coordinate Constraint (if not exists)
-- =============================================================================
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conname = 'field_reports_location_valid_range'
  ) THEN
    ALTER TABLE public.field_reports 
    ADD CONSTRAINT field_reports_location_valid_range 
    CHECK (
      (location IS NULL) OR (
        ST_Y(location::geometry) BETWEEN -90 AND 90 
        AND ST_X(location::geometry) BETWEEN -180 AND 180
      )
    );
  END IF;
END $$;

-- =============================================================================
-- STEP 4: Schedule Daily Enrichment Job (if not exists)
-- =============================================================================
DO $$
BEGIN
  -- Check if job exists, if not create it
  IF NOT EXISTS (
    SELECT 1 FROM cron.job WHERE jobname = 'daily-enrichment-job'
  ) THEN
    PERFORM cron.schedule(
      'daily-enrichment-job',
      '0 0 * * *',
      'SELECT net.http_post(
        url:=''https://rmzipvwqafrxhhuinggf.supabase.co/functions/v1/trigger-job'',
        headers:=''{"Content-Type": "application/json"}''::jsonb,
        body:=''{"type": "daily_enrichment"}''::jsonb
      )'
    );
  END IF;
END $$;

-- =============================================================================
-- STEP 5: Ensure avalanche_events has proper SELECT policy for anon
-- =============================================================================
DROP POLICY IF EXISTS "Anyone can view events" ON public.avalanche_events;
CREATE POLICY "Anyone can view events" 
  ON public.avalanche_events 
  FOR SELECT 
  USING (true);

-- =============================================================================
-- VERIFICATION QUERIES (Run these to confirm fixes)
-- =============================================================================

-- Verify field_reports RLS policies
SELECT 'FIELD_REPORTS POLICIES' AS check_type;
SELECT 
  policyname,
  permissive,
  roles::text,
  cmd,
  with_check::text
FROM pg_policies 
WHERE tablename = 'field_reports'
ORDER BY policyname;

-- Verify coordinate constraint exists
SELECT 'COORDINATE CONSTRAINT' AS check_type;
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint 
WHERE conrelid = 'field_reports'::regclass 
AND conname = 'field_reports_location_valid_range';

-- Verify daily enrichment job
SELECT 'DAILY ENRICHMENT JOB' AS check_type;
SELECT jobid, schedule, jobname, active, username
FROM cron.job 
WHERE jobname = 'daily-enrichment-job';

-- Verify extensions
SELECT 'EXTENSIONS' AS check_type;
SELECT extname, extversion FROM pg_extension 
WHERE extname IN ('postgis', 'pg_cron', 'pg_net', 'pgcrypto');

-- Test: Count current field_reports
SELECT 'CURRENT FIELD REPORTS COUNT' AS check_type;
SELECT COUNT(*) AS field_reports_count FROM public.field_reports;

-- =============================================================================
-- SUCCESS INDICATORS:
-- - field_reports policies: "Allow anonymous insert" and "Allow anonymous select" visible
-- - Constraint: field_reports_location_valid_range exists
-- - cron.job: daily-enrichment-job with schedule "0 0 * * *" and active = true
-- - Extensions: postgis, pg_cron, pg_net all present
-- =============================================================================
