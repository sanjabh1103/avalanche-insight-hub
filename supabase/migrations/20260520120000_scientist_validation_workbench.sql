-- Scientist-owned validation workbench.
-- This layer records review cases and scientist/operator judgements without
-- turning those judgements into production promotion automatically.

CREATE TABLE IF NOT EXISTS public.scientist_validation_cases (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  case_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  priority integer NOT NULL DEFAULT 3,
  region_key text,
  region_name text,
  forecast_run_id uuid REFERENCES public.forecast_runs(id) ON DELETE SET NULL,
  forecast_grid_id uuid,
  forecast_hour integer,
  cell_row integer,
  cell_col integer,
  title text NOT NULL,
  summary text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  cell_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  gate_key text,
  claim_boundary text NOT NULL DEFAULT 'decision_support_validation',
  assigned_to uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  CONSTRAINT scientist_validation_cases_type_check CHECK (
    case_type IN (
      'weak_layer',
      'runout',
      'false_positive',
      'false_negative',
      'masked_terrain',
      'sar_candidate',
      'model_gate'
    )
  ),
  CONSTRAINT scientist_validation_cases_status_check CHECK (
    status IN ('pending', 'in_review', 'reviewed', 'blocked', 'accepted_limitation')
  ),
  CONSTRAINT scientist_validation_cases_priority_check CHECK (priority BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_scientist_validation_cases_queue
  ON public.scientist_validation_cases (status, priority DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scientist_validation_cases_forecast_run
  ON public.scientist_validation_cases (forecast_run_id, forecast_hour, cell_row, cell_col);

CREATE TABLE IF NOT EXISTS public.scientist_validation_reviews (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  case_id uuid NOT NULL REFERENCES public.scientist_validation_cases(id) ON DELETE CASCADE,
  reviewer_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  verdict text NOT NULL,
  confidence double precision NOT NULL DEFAULT 0.5,
  notes text,
  failure_mode text,
  weak_layer_class text,
  runout_verdict text,
  claim_impact text NOT NULL DEFAULT 'no_change',
  evidence_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT scientist_validation_reviews_verdict_check CHECK (
    verdict IN ('accepted', 'rejected', 'needs_info', 'accepted_limitation', 'blocked')
  ),
  CONSTRAINT scientist_validation_reviews_confidence_check CHECK (confidence >= 0 AND confidence <= 1),
  CONSTRAINT scientist_validation_reviews_claim_impact_check CHECK (
    claim_impact IN ('no_change', 'downgrade', 'block', 'promote_candidate')
  )
);

CREATE INDEX IF NOT EXISTS idx_scientist_validation_reviews_case
  ON public.scientist_validation_reviews (case_id, created_at DESC);

ALTER TABLE public.scientist_validation_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scientist_validation_reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated read validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Authenticated read validation cases"
  ON public.scientist_validation_cases FOR SELECT TO authenticated
  USING (true);

DROP POLICY IF EXISTS "Authenticated insert validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Authenticated insert validation cases"
  ON public.scientist_validation_cases FOR INSERT TO authenticated
  WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated update validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Authenticated update validation cases"
  ON public.scientist_validation_cases FOR UPDATE TO authenticated
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "Service role manage validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Service role manage validation cases"
  ON public.scientist_validation_cases FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read validation reviews" ON public.scientist_validation_reviews;
CREATE POLICY "Authenticated read validation reviews"
  ON public.scientist_validation_reviews FOR SELECT TO authenticated
  USING (true);

DROP POLICY IF EXISTS "Authenticated insert validation reviews" ON public.scientist_validation_reviews;
CREATE POLICY "Authenticated insert validation reviews"
  ON public.scientist_validation_reviews FOR INSERT TO authenticated
  WITH CHECK (true);

DROP POLICY IF EXISTS "Service role manage validation reviews" ON public.scientist_validation_reviews;
CREATE POLICY "Service role manage validation reviews"
  ON public.scientist_validation_reviews FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

DROP TRIGGER IF EXISTS update_scientist_validation_cases_updated_at ON public.scientist_validation_cases;
CREATE TRIGGER update_scientist_validation_cases_updated_at
  BEFORE UPDATE ON public.scientist_validation_cases
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

COMMENT ON TABLE public.scientist_validation_cases IS
  'Scientist/operator review cases for weak-layer, runout, false-positive, false-negative, SAR, and model-gate validation. These records do not auto-promote public claims.';
COMMENT ON TABLE public.scientist_validation_reviews IS
  'Human validation judgements linked to scientist_validation_cases. Verdicts inform claim boundaries and promotion review, but are not production promotion by themselves.';
