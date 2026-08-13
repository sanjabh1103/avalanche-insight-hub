-- Tighten RLS on verification_baselines and verification_anomalies.
-- The original migration (20260704120000) created "Anyone can view" policies
-- with USING (true), making these tables publicly readable. This migration
-- replaces them with scientist-or-admin-only SELECT policies, consistent with
-- verification_observations and verification_review_queue.

-- ── verification_baselines ──

DROP POLICY IF EXISTS "Anyone can view verification baselines"
  ON public.verification_baselines;
DROP POLICY IF EXISTS "Scientist or admin read verification baselines"
  ON public.verification_baselines;
CREATE POLICY "Scientist or admin read verification baselines"
  ON public.verification_baselines FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role can manage verification baselines"
  ON public.verification_baselines;
CREATE POLICY "Service role can manage verification baselines"
  ON public.verification_baselines FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.verification_baselines IS
  'Scientist-only verification baselines. Public/anonymous reads are blocked.';

-- ── verification_anomalies ──

DROP POLICY IF EXISTS "Anyone can view verification anomalies"
  ON public.verification_anomalies;
DROP POLICY IF EXISTS "Scientist or admin read verification anomalies"
  ON public.verification_anomalies;
CREATE POLICY "Scientist or admin read verification anomalies"
  ON public.verification_anomalies FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role can manage verification anomalies"
  ON public.verification_anomalies;
CREATE POLICY "Service role can manage verification anomalies"
  ON public.verification_anomalies FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.verification_anomalies IS
  'Scientist-only verification anomalies. Public/anonymous reads are blocked.';
