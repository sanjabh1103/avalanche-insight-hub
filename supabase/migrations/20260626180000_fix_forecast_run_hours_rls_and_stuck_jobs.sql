-- Fix 1: Restore anon SELECT on forecast_run_hours so the public/anon key
-- can read hourly forecast data. Migration 20260501170000 replaced the anon
-- policy with an admin-only policy, making the table invisible to public
-- queries even though the service role inserts rows successfully.

-- Re-grant SELECT to anon (matching the forecast_runs pattern)
GRANT SELECT ON TABLE public.forecast_run_hours TO anon;

-- Replace the admin-only SELECT policy with a public-read policy
DROP POLICY IF EXISTS "Admins can view forecast run hours" ON public.forecast_run_hours;
DROP POLICY IF EXISTS "Anyone can view forecast run hours" ON public.forecast_run_hours;
CREATE POLICY "Anyone can view forecast run hours"
  ON public.forecast_run_hours
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- Keep the service_role management policy (already exists from earlier migration)
DROP POLICY IF EXISTS "Service role can manage forecast run hours" ON public.forecast_run_hours;
CREATE POLICY "Service role can manage forecast run hours"
  ON public.forecast_run_hours
  FOR ALL
  TO service_role
  USING (auth.role() = 'service_role');

-- Fix 2: Add 'timeout' to job_status enum for stuck compute_jobs.
-- PostgreSQL requires ALTER TYPE ADD VALUE to commit before the new value
-- can be used in any DML statement. The UPDATE and pg_cron schedule are
-- in migration 20260626180100_stuck_job_cleanup_schedule.sql.
ALTER TYPE public.job_status ADD VALUE IF NOT EXISTS 'timeout';
