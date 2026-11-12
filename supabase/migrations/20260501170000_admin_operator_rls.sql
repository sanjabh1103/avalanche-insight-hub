-- Admin/operator auth hardening for the publication and evaluation planes.
-- Keep public manifest-backed forecast delivery readable while restricting
-- operator-only timeline and evaluation tables to authenticated admins.

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE((auth.jwt() -> 'app_metadata' -> 'roles') ? 'admin', FALSE);
$$;

GRANT EXECUTE ON FUNCTION public.is_admin() TO anon, authenticated, service_role;

GRANT SELECT ON TABLE public.forecast_runs TO anon, authenticated;
GRANT SELECT ON TABLE public.forecast_runs TO service_role;
GRANT INSERT, UPDATE, DELETE ON TABLE public.forecast_runs TO service_role;

GRANT SELECT ON TABLE public.forecast_run_hours TO authenticated;
GRANT SELECT ON TABLE public.forecast_run_hours TO service_role;
GRANT INSERT, UPDATE, DELETE ON TABLE public.forecast_run_hours TO service_role;

GRANT SELECT ON TABLE public.forecast_publication_events TO authenticated;
GRANT SELECT ON TABLE public.forecast_publication_events TO service_role;
GRANT INSERT, UPDATE, DELETE ON TABLE public.forecast_publication_events TO service_role;

GRANT SELECT ON TABLE public.label_snapshots TO authenticated;
GRANT SELECT ON TABLE public.label_snapshots TO service_role;
GRANT INSERT, UPDATE, DELETE ON TABLE public.label_snapshots TO service_role;

GRANT SELECT ON TABLE public.hindcast_runs TO authenticated;
GRANT SELECT ON TABLE public.hindcast_runs TO service_role;
GRANT INSERT, UPDATE, DELETE ON TABLE public.hindcast_runs TO service_role;

GRANT SELECT ON TABLE public.calibration_reports TO authenticated;
GRANT SELECT ON TABLE public.calibration_reports TO service_role;
GRANT INSERT, UPDATE, DELETE ON TABLE public.calibration_reports TO service_role;

GRANT SELECT ON TABLE public.forecast_active_runs TO anon, authenticated;
GRANT SELECT ON TABLE public.forecast_active_runs TO service_role;

REVOKE ALL ON FUNCTION public.promote_forecast_run(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.promote_forecast_run(UUID) TO service_role;

DROP POLICY IF EXISTS "Anyone can view forecast runs" ON public.forecast_runs;
DROP POLICY IF EXISTS "Public can view forecast runs" ON public.forecast_runs;
CREATE POLICY "Public can view forecast runs"
  ON public.forecast_runs
  FOR SELECT
  TO anon, authenticated
  USING (true);

DROP POLICY IF EXISTS "Anyone can view forecast run hours" ON public.forecast_run_hours;
DROP POLICY IF EXISTS "Admins can view forecast run hours" ON public.forecast_run_hours;
CREATE POLICY "Admins can view forecast run hours"
  ON public.forecast_run_hours
  FOR SELECT
  TO authenticated
  USING (public.is_admin());

DROP POLICY IF EXISTS "Anyone can view forecast publication events" ON public.forecast_publication_events;
DROP POLICY IF EXISTS "Admins can view forecast publication events" ON public.forecast_publication_events;
CREATE POLICY "Admins can view forecast publication events"
  ON public.forecast_publication_events
  FOR SELECT
  TO authenticated
  USING (public.is_admin());

DROP POLICY IF EXISTS "Anyone can view label snapshots" ON public.label_snapshots;
DROP POLICY IF EXISTS "Admins can view label snapshots" ON public.label_snapshots;
CREATE POLICY "Admins can view label snapshots"
  ON public.label_snapshots
  FOR SELECT
  TO authenticated
  USING (public.is_admin());

DROP POLICY IF EXISTS "Anyone can view hindcast runs" ON public.hindcast_runs;
DROP POLICY IF EXISTS "Admins can view hindcast runs" ON public.hindcast_runs;
CREATE POLICY "Admins can view hindcast runs"
  ON public.hindcast_runs
  FOR SELECT
  TO authenticated
  USING (public.is_admin());

DROP POLICY IF EXISTS "Anyone can view calibration reports" ON public.calibration_reports;
DROP POLICY IF EXISTS "Admins can view calibration reports" ON public.calibration_reports;
CREATE POLICY "Admins can view calibration reports"
  ON public.calibration_reports
  FOR SELECT
  TO authenticated
  USING (public.is_admin());
