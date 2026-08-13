-- Phase 3: Knowledge graph model endpoint — audit, rate limits, quotas, and cache.
--
-- Supports the supabase/functions/knowledge-graph-model edge function.
-- All tables use RLS so only the service role (edge function) can read/write.
-- Audit logs are append-only for authenticated users (scientist/admin can view their own).

-- ============================================================================
-- 1. Audit log — every model endpoint request is recorded
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.model_endpoint_audit (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  user_email TEXT,
  user_role TEXT,
  request_id TEXT NOT NULL,
  endpoint TEXT NOT NULL DEFAULT 'knowledge-graph-model',
  request_body JSONB,
  response_status INTEGER,
  response_body_preview TEXT,
  model_tokens_used INTEGER,
  model_cost_usd NUMERIC(10, 6),
  denylist_violation BOOLEAN DEFAULT FALSE,
  rate_limit_exceeded BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_endpoint_audit_user_id
  ON public.model_endpoint_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_model_endpoint_audit_created_at
  ON public.model_endpoint_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_endpoint_audit_user_created
  ON public.model_endpoint_audit(user_id, created_at DESC);

ALTER TABLE public.model_endpoint_audit ENABLE ROW LEVEL SECURITY;

-- Scientists and admins can view their own audit entries
CREATE POLICY "Users can view own model endpoint audit"
  ON public.model_endpoint_audit FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- Only service role can insert (edge function uses service role key)
CREATE POLICY "Service role can insert model endpoint audit"
  ON public.model_endpoint_audit FOR INSERT TO service_role
  WITH CHECK (true);

-- ============================================================================
-- 2. Rate limits — per-user sliding window
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.model_endpoint_rate_limits (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  request_count INTEGER NOT NULL DEFAULT 0,
  window_start TIMESTAMPTZ NOT NULL DEFAULT now(),
  window_duration_seconds INTEGER NOT NULL DEFAULT 3600, -- 1 hour
  max_requests INTEGER NOT NULL DEFAULT 50
);

ALTER TABLE public.model_endpoint_rate_limits ENABLE ROW LEVEL SECURITY;

-- Users can view their own rate limit state
CREATE POLICY "Users can view own rate limits"
  ON public.model_endpoint_rate_limits FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- Only service role can modify
CREATE POLICY "Service role can modify rate limits"
  ON public.model_endpoint_rate_limits FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ============================================================================
-- 3. Quotas — per-user token and cost quotas (monthly)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.model_endpoint_quotas (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  tokens_used INTEGER NOT NULL DEFAULT 0,
  tokens_limit INTEGER NOT NULL DEFAULT 100000, -- 100K tokens/month
  cost_used_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
  cost_limit_usd NUMERIC(10, 6) NOT NULL DEFAULT 10.00, -- $10/month
  period_start TIMESTAMPTZ NOT NULL DEFAULT now(),
  period_duration_days INTEGER NOT NULL DEFAULT 30
);

ALTER TABLE public.model_endpoint_quotas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own quotas"
  ON public.model_endpoint_quotas FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Service role can modify quotas"
  ON public.model_endpoint_quotas FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ============================================================================
-- 4. Cache — response caching with TTL
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.model_endpoint_cache (
  cache_key TEXT PRIMARY KEY,
  request_hash TEXT NOT NULL,
  response_jsonb JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 0,
  last_hit_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_model_endpoint_cache_expires_at
  ON public.model_endpoint_cache(expires_at);

ALTER TABLE public.model_endpoint_cache ENABLE ROW LEVEL SECURITY;

-- Only service role can access cache
CREATE POLICY "Service role can manage cache"
  ON public.model_endpoint_cache FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ============================================================================
-- 5. RPC: check_rate_limit(p_user_id) — atomic sliding window check
-- ============================================================================
-- Returns JSON: { "allowed": boolean, "request_count": integer, "max_requests": integer }
--   allowed = true  -> request is within rate limit, counter incremented
--   allowed = false -> rate limit exceeded, counter NOT incremented
CREATE OR REPLACE FUNCTION public.check_model_rate_limit(p_user_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_window_start TIMESTAMPTZ;
  v_request_count INTEGER;
  v_max_requests INTEGER;
  v_window_seconds INTEGER;
  v_allowed BOOLEAN := false;
BEGIN
  SELECT window_start, request_count, max_requests, window_duration_seconds
    INTO v_window_start, v_request_count, v_max_requests, v_window_seconds
  FROM public.model_endpoint_rate_limits
  WHERE user_id = p_user_id
  FOR UPDATE;

  IF NOT FOUND THEN
    -- First request: create row with count=1
    INSERT INTO public.model_endpoint_rate_limits (user_id, request_count, window_start)
    VALUES (p_user_id, 1, now());
    v_allowed := true;
    v_request_count := 1;
  ELSIF now() > v_window_start + (v_window_seconds || ' seconds')::INTERVAL THEN
    -- Window expired: reset
    UPDATE public.model_endpoint_rate_limits
      SET request_count = 1, window_start = now()
    WHERE user_id = p_user_id;
    v_allowed := true;
    v_request_count := 1;
  ELSIF v_request_count < v_max_requests THEN
    -- Within window and under limit: increment
    UPDATE public.model_endpoint_rate_limits
      SET request_count = request_count + 1
    WHERE user_id = p_user_id;
    v_allowed := true;
    v_request_count := v_request_count + 1;
  ELSE
    -- Rate limit exceeded
    v_allowed := false;
  END IF;

  RETURN jsonb_build_object(
    'allowed', v_allowed,
    'request_count', v_request_count,
    'max_requests', COALESCE(v_max_requests, 50)
  );
END;
$$;

-- This RPC is called only by the service-role edge function. Public grants
-- would let a caller mutate another user's rate-limit row by supplying an
-- arbitrary p_user_id.
REVOKE ALL ON FUNCTION public.check_model_rate_limit(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.check_model_rate_limit(UUID) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_model_rate_limit(UUID) TO service_role;

-- ============================================================================
-- 6. RPC: reserve_model_usage(p_user_id, p_tokens, p_cost) — atomic quota check
-- ============================================================================
-- Returns JSON: { "reserved": boolean, "tokens_used": integer, "tokens_limit": integer, "cost_used_usd": numeric, "cost_limit_usd": numeric }
--   reserved = true  -> quota available, usage incremented
--   reserved = false -> quota exceeded, usage NOT incremented
CREATE OR REPLACE FUNCTION public.reserve_model_usage(
  p_user_id UUID,
  p_tokens INTEGER,
  p_cost_usd NUMERIC
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_tokens_used INTEGER;
  v_tokens_limit INTEGER;
  v_cost_used NUMERIC(10,6);
  v_cost_limit NUMERIC(10,6);
  v_period_start TIMESTAMPTZ;
  v_period_days INTEGER;
  v_reserved BOOLEAN := false;
BEGIN
  SELECT tokens_used, tokens_limit, cost_used_usd, cost_limit_usd, period_start, period_duration_days
    INTO v_tokens_used, v_tokens_limit, v_cost_used, v_cost_limit, v_period_start, v_period_days
  FROM public.model_endpoint_quotas
  WHERE user_id = p_user_id
  FOR UPDATE;

  IF NOT FOUND THEN
    -- First usage: create row and reserve
    INSERT INTO public.model_endpoint_quotas (user_id, tokens_used, cost_used_usd, period_start)
    VALUES (p_user_id, p_tokens, p_cost_usd, now());
    v_reserved := true;
    v_tokens_used := p_tokens;
    v_cost_used := p_cost_usd;
  ELSIF now() > v_period_start + (v_period_days || ' days')::INTERVAL THEN
    -- Period expired: reset
    UPDATE public.model_endpoint_quotas
      SET tokens_used = p_tokens, cost_used_usd = p_cost_usd, period_start = now()
    WHERE user_id = p_user_id;
    v_reserved := true;
    v_tokens_used := p_tokens;
    v_cost_used := p_cost_usd;
  ELSIF v_tokens_used + p_tokens <= v_tokens_limit AND v_cost_used + p_cost_usd <= v_cost_limit THEN
    -- Within quota: increment
    UPDATE public.model_endpoint_quotas
      SET tokens_used = tokens_used + p_tokens,
          cost_used_usd = cost_used_usd + p_cost_usd
    WHERE user_id = p_user_id;
    v_reserved := true;
    v_tokens_used := v_tokens_used + p_tokens;
    v_cost_used := v_cost_used + p_cost_usd;
  ELSE
    -- Quota exceeded
    v_reserved := false;
  END IF;

  RETURN jsonb_build_object(
    'reserved', v_reserved,
    'tokens_used', v_tokens_used,
    'tokens_limit', COALESCE(v_tokens_limit, 100000),
    'cost_used_usd', v_cost_used,
    'cost_limit_usd', COALESCE(v_cost_limit, 10.00)
  );
END;
$$;

REVOKE ALL ON FUNCTION public.reserve_model_usage(UUID, INTEGER, NUMERIC) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reserve_model_usage(UUID, INTEGER, NUMERIC) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_model_usage(UUID, INTEGER, NUMERIC) TO service_role;

-- ============================================================================
-- 7. RPC: cleanup_expired_model_cache() — periodic cache cleanup
-- ============================================================================
CREATE OR REPLACE FUNCTION public.cleanup_expired_model_cache()
RETURNS INTEGER
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  WITH deleted AS (
    DELETE FROM public.model_endpoint_cache WHERE expires_at < now() RETURNING 1
  )
  SELECT count(*)::INTEGER FROM deleted;
$$;

REVOKE ALL ON FUNCTION public.cleanup_expired_model_cache() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cleanup_expired_model_cache() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_expired_model_cache() TO service_role;
