-- Add unique constraint to prevent duplicate gemini_news articles
-- and add retention cleanup function for Supabase free-tier sustainability

-- 1. Add a generated column for news_article_id so we can index it
ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS news_article_id TEXT
  GENERATED ALWAYS AS (
    COALESCE(
      (topo_profile->'metadata'->>'news_article_id'),
      ''
    )
  ) STORED;

-- 2. Unique constraint: one gemini_news row per article_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_avalanche_events_gemini_news_article_id
  ON public.avalanche_events (source, news_article_id)
  WHERE source = 'gemini_news' AND news_article_id <> '';

-- 3. Retention function: delete oldest gemini_news rows beyond budget
CREATE OR REPLACE FUNCTION public.cleanup_gemini_news_rows(
  p_row_budget INT DEFAULT 500
) RETURNS INT AS $$
DECLARE
  v_deleted INT;
BEGIN
  WITH to_delete AS (
    SELECT id FROM public.avalanche_events
    WHERE source = 'gemini_news'
    ORDER BY created_at DESC
    OFFSET p_row_budget
  )
  DELETE FROM public.avalanche_events
  WHERE id IN (SELECT id FROM to_delete);
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  RETURN v_deleted;
END;
$$ LANGUAGE plpgsql SECURITY INVOKER;

COMMENT ON FUNCTION public.cleanup_gemini_news_rows IS
  'Deletes oldest gemini_news display-only rows beyond the budget. Call after news ingest runs.';
