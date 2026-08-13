-- Persistent cache table for scene/tile and sensor history data.
-- Replaces in-process dict caches with content-addressed Postgres storage with TTL.
CREATE TABLE IF NOT EXISTS public.persistent_cache (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for efficient expired cleanup queries
CREATE INDEX IF NOT EXISTS idx_persistent_cache_expires_at
  ON public.persistent_cache (expires_at)
  WHERE expires_at IS NOT NULL;

-- RLS: service role can write, authenticated can read
ALTER TABLE public.persistent_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service role can write persistent cache"
  ON public.persistent_cache
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "authenticated can read persistent cache"
  ON public.persistent_cache
  FOR SELECT
  TO authenticated
  USING (true);
