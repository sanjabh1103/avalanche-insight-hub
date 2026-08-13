-- Quick RLS status check - Run this in Lovable SQL Editor
SELECT 
  tablename,
  CASE WHEN pg_class.relrowsecurity THEN '✅ ENABLED' ELSE '❌ DISABLED' END as rls_status
FROM pg_tables 
JOIN pg_class ON pg_class.relname = tablename
WHERE schemaname = 'public' 
AND tablename IN ('avalanche_events', 'forecasts', 'field_reports', 'compute_jobs', 'system_config', 'model_status', 'mountain_terrain')
ORDER BY tablename;
