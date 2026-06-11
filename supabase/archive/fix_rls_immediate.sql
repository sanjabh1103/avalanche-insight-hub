-- IMMEDIATE RLS FIX - Run this in Supabase Dashboard SQL Editor
-- Project: fzheroisjhxnairglelv (or qnymbecjgeaoxsfphrti if different)

-- =====================================================
-- FIX 1: Enable RLS on ALL tables (idempotent - safe to re-run)
-- =====================================================

-- avalanche_events
ALTER TABLE IF EXISTS public.avalanche_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view events" ON public.avalanche_events;
DROP POLICY IF EXISTS "Service role can manage events" ON public.avalanche_events;
CREATE POLICY "Anyone can view events" ON public.avalanche_events FOR SELECT USING (true);
CREATE POLICY "Service role can manage events" ON public.avalanche_events FOR ALL USING (auth.role() = 'service_role');

-- forecasts
ALTER TABLE IF EXISTS public.forecasts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view forecasts" ON public.forecasts;
DROP POLICY IF EXISTS "Service role can manage forecasts" ON public.forecasts;
CREATE POLICY "Anyone can view forecasts" ON public.forecasts FOR SELECT USING (true);
CREATE POLICY "Service role can manage forecasts" ON public.forecasts FOR ALL USING (auth.role() = 'service_role');

-- field_reports
ALTER TABLE IF EXISTS public.field_reports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can create reports" ON public.field_reports;
DROP POLICY IF EXISTS "Service role can manage reports" ON public.field_reports;
CREATE POLICY "Users can view their own reports" ON public.field_reports FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create reports" ON public.field_reports FOR INSERT WITH CHECK (user_id IS NULL OR auth.uid() = user_id);
CREATE POLICY "Service role can manage reports" ON public.field_reports FOR ALL USING (auth.role() = 'service_role');

-- compute_jobs
ALTER TABLE IF EXISTS public.compute_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view jobs" ON public.compute_jobs;
DROP POLICY IF EXISTS "Service role can manage jobs" ON public.compute_jobs;
CREATE POLICY "Anyone can view jobs" ON public.compute_jobs FOR SELECT USING (true);
CREATE POLICY "Service role can manage jobs" ON public.compute_jobs FOR ALL USING (auth.role() = 'service_role');

-- system_config
ALTER TABLE IF EXISTS public.system_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view config" ON public.system_config;
DROP POLICY IF EXISTS "Service role can manage config" ON public.system_config;
CREATE POLICY "Anyone can view config" ON public.system_config FOR SELECT USING (true);
CREATE POLICY "Service role can manage config" ON public.system_config FOR ALL USING (auth.role() = 'service_role');

-- model_status
ALTER TABLE IF EXISTS public.model_status ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view model status" ON public.model_status;
DROP POLICY IF EXISTS "Service role can manage model status" ON public.model_status;
CREATE POLICY "Anyone can view model status" ON public.model_status FOR SELECT USING (true);
CREATE POLICY "Service role can manage model status" ON public.model_status FOR ALL USING (auth.role() = 'service_role');

-- mountain_terrain
ALTER TABLE IF EXISTS public.mountain_terrain ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view terrain" ON public.mountain_terrain;
DROP POLICY IF EXISTS "Service role can manage terrain" ON public.mountain_terrain;
CREATE POLICY "Anyone can view terrain" ON public.mountain_terrain FOR SELECT USING (true);
CREATE POLICY "Service role can manage terrain" ON public.mountain_terrain FOR ALL USING (auth.role() = 'service_role');

-- =====================================================
-- FIX 2: Verify RLS is enabled (check output)
-- =====================================================
SELECT 
  schemaname,
  tablename,
  rowsecurity,
  forcerowsecurity
FROM pg_tables 
JOIN pg_class ON pg_class.relname = tablename
WHERE schemaname = 'public' 
AND pg_class.relrowsecurity = true;
