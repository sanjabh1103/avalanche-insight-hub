-- Harden public field-report submission.
--
-- Public clients now submit through the submit-field-report Edge Function, which
-- applies server-side IP-hash rate limiting before inserting with service-role
-- privileges. Raw anonymous table insert/select policies are removed here.

CREATE TABLE IF NOT EXISTS public.field_report_rate_limits (
  ip_hash text NOT NULL,
  hour_bucket timestamptz NOT NULL,
  request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ip_hash, hour_bucket)
);

ALTER TABLE public.field_report_rate_limits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role can manage field report rate limits"
  ON public.field_report_rate_limits;
CREATE POLICY "Service role can manage field report rate limits"
  ON public.field_report_rate_limits
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.field_report_rate_limits TO service_role;

CREATE OR REPLACE FUNCTION public.increment_field_report_rate_limit(
  p_ip_hash text,
  p_hour_bucket timestamptz,
  p_limit integer DEFAULT 5
)
RETURNS TABLE(request_count integer, allowed boolean)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_count integer;
BEGIN
  IF p_ip_hash IS NULL OR length(trim(p_ip_hash)) = 0 THEN
    RAISE EXCEPTION 'p_ip_hash is required';
  END IF;

  IF p_limit IS NULL OR p_limit < 1 THEN
    RAISE EXCEPTION 'p_limit must be >= 1';
  END IF;

  INSERT INTO public.field_report_rate_limits AS limits (
    ip_hash,
    hour_bucket,
    request_count,
    created_at,
    updated_at
  )
  VALUES (
    p_ip_hash,
    date_trunc('hour', p_hour_bucket),
    1,
    now(),
    now()
  )
  ON CONFLICT (ip_hash, hour_bucket)
  DO UPDATE SET
    request_count = limits.request_count + 1,
    updated_at = now()
  RETURNING limits.request_count INTO v_count;

  request_count := v_count;
  allowed := v_count <= p_limit;
  RETURN NEXT;
END;
$$;

REVOKE ALL ON FUNCTION public.increment_field_report_rate_limit(text, timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.increment_field_report_rate_limit(text, timestamptz, integer) FROM anon;
REVOKE ALL ON FUNCTION public.increment_field_report_rate_limit(text, timestamptz, integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.increment_field_report_rate_limit(text, timestamptz, integer) TO service_role;

ALTER TABLE public.field_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow anonymous insert" ON public.field_reports;
DROP POLICY IF EXISTS "Allow anonymous select" ON public.field_reports;
DROP POLICY IF EXISTS "Anyone can submit field reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can create reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can view own reports" ON public.field_reports;
DROP POLICY IF EXISTS "Users can view their own reports" ON public.field_reports;
DROP POLICY IF EXISTS "Authenticated users can view own reports" ON public.field_reports;
DROP POLICY IF EXISTS "Authenticated users can view own field reports" ON public.field_reports;
DROP POLICY IF EXISTS "Admins can view field reports" ON public.field_reports;
DROP POLICY IF EXISTS "Service role can manage reports" ON public.field_reports;

CREATE POLICY "Authenticated users can view own field reports"
  ON public.field_reports
  FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Admins can view field reports"
  ON public.field_reports
  FOR SELECT
  TO authenticated
  USING (public.is_admin());

CREATE POLICY "Service role can manage reports"
  ON public.field_reports
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT ON TABLE public.field_reports TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.field_reports TO service_role;
