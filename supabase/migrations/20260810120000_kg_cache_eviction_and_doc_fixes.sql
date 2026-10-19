-- G7: Fix rate limit comment (was "sliding window", actually fixed window).
-- G8: Add cache size limit + LRU eviction function.
-- G15: Document quota reset is day-based (30-day period), not calendar month.
--
-- These are documentation and operational improvements, not schema changes.
-- The existing rate limit and quota implementations are adequate for the
-- current scale (50 req/hour, $10/month per user). This migration adds:
-- 1. A cache eviction function to prevent unbounded growth
-- 2. A last_hit_at column for LRU tracking
-- 3. Updated comments reflecting actual implementation

-- ============================================================================
-- G8: Add last_hit_at column for LRU tracking
-- ============================================================================
ALTER TABLE public.model_endpoint_cache
  ADD COLUMN IF NOT EXISTS last_hit_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ============================================================================
-- G8: LRU eviction function — evicts least-recently-used entries when cache
-- exceeds max_entries. Called after each cache write.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.evict_lru_cache_entries(
  p_max_entries INTEGER DEFAULT 10000
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_current_count INTEGER;
  v_evicted INTEGER;
BEGIN
  SELECT COUNT(*) INTO v_current_count FROM public.model_endpoint_cache;

  IF v_current_count <= p_max_entries THEN
    RETURN 0;
  END IF;

  -- Delete oldest entries by last_hit_at until under limit
  DELETE FROM public.model_endpoint_cache
  WHERE cache_key IN (
    SELECT cache_key
    FROM public.model_endpoint_cache
    ORDER BY last_hit_at ASC
    LIMIT (v_current_count - p_max_entries)
  );

  GET DIAGNOSTICS v_evicted = ROW_COUNT;
  RETURN v_evicted;
END;
$$;

REVOKE ALL ON FUNCTION public.evict_lru_cache_entries(INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evict_lru_cache_entries(INTEGER) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.evict_lru_cache_entries(INTEGER) TO service_role;

-- ============================================================================
-- G8: Update hit_at on cache reads (called by edge function after cache hit)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.touch_cache_entry(
  p_cache_key TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE public.model_endpoint_cache
  SET last_hit_at = now(), hit_count = hit_count + 1
  WHERE cache_key = p_cache_key;
END;
$$;

REVOKE ALL ON FUNCTION public.touch_cache_entry(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.touch_cache_entry(TEXT) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.touch_cache_entry(TEXT) TO service_role;

-- ============================================================================
-- G7/G15: Update comments on existing tables to reflect actual implementation
-- ============================================================================
COMMENT ON TABLE public.model_endpoint_rate_limits IS
  'Per-user fixed-window rate limits for the knowledge-graph-model edge function. '
  'Window resets completely when expired (not a sliding window). Default: 50 requests per hour.';

COMMENT ON TABLE public.model_endpoint_quotas IS
  'Per-user token and cost quotas for the knowledge-graph-model edge function. '
  'Period is day-based (default 30 days from first request), NOT calendar-month aligned. '
  'Reset occurs when period_start + period_duration_days < now().';
