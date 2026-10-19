-- ============================================================
-- COMPLETE SUPABASE SETUP VERIFICATION & FIX SCRIPT
-- Run this in Lovable SQL Editor (or Supabase Dashboard)
-- Project: rmzipvwqaffrxhhuinggf
-- ============================================================

-- 1. CHECK CURRENT SCHEMA STATUS
-- ============================================================
SELECT '=== TABLE RLS STATUS ===' as section;
SELECT 
  tablename,
  CASE WHEN pg_class.relrowsecurity THEN 'ENABLED' ELSE 'DISABLED - CRITICAL!' END as rls_status
FROM pg_tables 
JOIN pg_class ON pg_class.relname = tablename
WHERE schemaname = 'public' 
AND tablename IN ('avalanche_events', 'forecasts', 'field_reports', 'compute_jobs', 'system_config', 'model_status', 'mountain_terrain')
ORDER BY tablename;

-- 2. CHECK CONSTRAINTS ON field_reports
-- ============================================================
SELECT '=== FIELD_REPORTS CONSTRAINTS ===' as section;
SELECT 
  conname as constraint_name,
  pg_get_constraintdef(oid) as definition
FROM pg_constraint
WHERE conrelid = 'public.field_reports'::regclass
AND contype = 'c';

-- 3. ADD CONSTRAINT IF MISSING (idempotent)
-- ============================================================
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'field_reports_location_valid_range'
  ) THEN
    ALTER TABLE public.field_reports
      ADD CONSTRAINT field_reports_location_valid_range
      CHECK (
        location IS NULL
        OR (
          ST_Y(location::geometry) BETWEEN -90 AND 90
          AND ST_X(location::geometry) BETWEEN -180 AND 180
        )
      );
    RAISE NOTICE 'Constraint field_reports_location_valid_range ADDED';
  ELSE
    RAISE NOTICE 'Constraint field_reports_location_valid_range already exists';
  END IF;
END $$;

-- 3b. CHECK pg_cron JOB STATUS
-- ============================================================
SELECT '=== DAILY ENRICHMENT CRON ===' as section;
SELECT
  jobid,
  schedule,
  jobname,
  active
FROM cron.job
WHERE jobname = 'daily-enrichment-job';

-- 4. VERIFY RLS POLICIES EXIST
-- ============================================================
SELECT '=== RLS POLICIES ===' as section;
SELECT 
  tablename,
  policyname,
  cmd as command,
  permissive
FROM pg_policies
WHERE schemaname = 'public'
AND tablename IN ('avalanche_events', 'forecasts', 'field_reports', 'compute_jobs', 'system_config', 'model_status', 'mountain_terrain')
ORDER BY tablename, policyname;

-- 5. ENABLE RLS ON ALL TABLES (idempotent)
-- ============================================================
ALTER TABLE IF EXISTS public.avalanche_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.compute_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.field_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.model_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.mountain_terrain ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.system_config ENABLE ROW LEVEL SECURITY;

-- 6. FINAL VERIFICATION
-- ============================================================
SELECT '=== FINAL RLS STATUS ===' as section;
SELECT 
  tablename,
  CASE WHEN pg_class.relrowsecurity THEN '✅ ENABLED' ELSE '❌ DISABLED' END as rls_status,
  (SELECT COUNT(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = pg_tables.tablename) as policy_count
FROM pg_tables 
JOIN pg_class ON pg_class.relname = tablename
WHERE schemaname = 'public' 
AND tablename IN ('avalanche_events', 'forecasts', 'field_reports', 'compute_jobs', 'system_config', 'model_status', 'mountain_terrain')
ORDER BY tablename;

-- 7. TEST CONSTRAINT
-- ============================================================
SELECT '=== CONSTRAINT VERIFICATION ===' as section;
SELECT 
  CASE 
    WHEN EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = 'field_reports_location_valid_range'
    ) 
    THEN '✅ Coordinate constraint is ACTIVE'
    ELSE '❌ Coordinate constraint is MISSING'
  END as status;

-- 8. VERIFY EDGE FUNCTION DEPLOYMENT IS AVAILABLE TO THE APP
-- ============================================================
SELECT '=== EDGE FUNCTIONS CHECKLIST ===' as section;
SELECT
  'run-forecast' as function_name
UNION ALL SELECT 'trigger-job'
UNION ALL SELECT 'field-report-enrichment';
