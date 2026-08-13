-- Track B forward migration: remove public access from operational provenance
-- tables. Backfill control-plane rows are not a public application surface.

REVOKE ALL ON TABLE public.sar_provenance_backfill_runs
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.sar_provenance_backfill_chunks
  FROM PUBLIC, anon, authenticated;

GRANT ALL ON TABLE public.sar_provenance_backfill_runs TO service_role;
GRANT ALL ON TABLE public.sar_provenance_backfill_chunks TO service_role;

DROP POLICY IF EXISTS "Anyone can view sar provenance runs"
  ON public.sar_provenance_backfill_runs;
DROP POLICY IF EXISTS "Service role can manage sar provenance runs"
  ON public.sar_provenance_backfill_runs;
DROP POLICY IF EXISTS "Anyone can view sar provenance chunks"
  ON public.sar_provenance_backfill_chunks;
DROP POLICY IF EXISTS "Service role can manage sar provenance chunks"
  ON public.sar_provenance_backfill_chunks;

CREATE POLICY "Service role can manage sar provenance runs"
  ON public.sar_provenance_backfill_runs
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role can manage sar provenance chunks"
  ON public.sar_provenance_backfill_chunks
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);
