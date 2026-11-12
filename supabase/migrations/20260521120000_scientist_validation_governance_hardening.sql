-- Scientist validation governance hardening.
-- Adds structured review fields, two-reviewer tracking, and a non-automating
-- action ledger. Reviews inform follow-up work; they do not promote models or
-- alter production scoring.

ALTER TABLE public.scientist_validation_cases
  ADD COLUMN IF NOT EXISTS requires_two_reviewers boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS disagreement_count integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS signoff_scope text NOT NULL DEFAULT 'single_case_review';

UPDATE public.scientist_validation_cases
SET requires_two_reviewers = true
WHERE priority >= 5;

ALTER TABLE public.scientist_validation_reviews
  ADD COLUMN IF NOT EXISTS official_avalanche_problem text,
  ADD COLUMN IF NOT EXISTS label_quality_verdict text,
  ADD COLUMN IF NOT EXISTS model_error_verdict text,
  ADD COLUMN IF NOT EXISTS terrain_sar_ambiguity text,
  ADD COLUMN IF NOT EXISTS evidence_needed_next text,
  ADD COLUMN IF NOT EXISTS confidence_rationale text;

ALTER TABLE public.scientist_validation_reviews
  DROP CONSTRAINT IF EXISTS scientist_validation_reviews_official_problem_check;
ALTER TABLE public.scientist_validation_reviews
  ADD CONSTRAINT scientist_validation_reviews_official_problem_check CHECK (
    official_avalanche_problem IS NULL OR official_avalanche_problem IN (
      'new_snow',
      'wind_slab',
      'persistent_weak_layers',
      'wet_snow',
      'gliding_snow',
      'cornices',
      'no_distinct_problem',
      'not_assessed'
    )
  );

ALTER TABLE public.scientist_validation_reviews
  DROP CONSTRAINT IF EXISTS scientist_validation_reviews_label_quality_check;
ALTER TABLE public.scientist_validation_reviews
  ADD CONSTRAINT scientist_validation_reviews_label_quality_check CHECK (
    label_quality_verdict IS NULL OR label_quality_verdict IN (
      'label_reliable',
      'label_underreported',
      'label_overreported',
      'location_or_time_uncertain',
      'source_conflict',
      'not_assessed'
    )
  );

ALTER TABLE public.scientist_validation_reviews
  DROP CONSTRAINT IF EXISTS scientist_validation_reviews_model_error_check;
ALTER TABLE public.scientist_validation_reviews
  ADD CONSTRAINT scientist_validation_reviews_model_error_check CHECK (
    model_error_verdict IS NULL OR model_error_verdict IN (
      'model_plausible',
      'model_false_positive',
      'model_false_negative',
      'model_miscalibrated',
      'insufficient_evidence',
      'not_assessed'
    )
  );

ALTER TABLE public.scientist_validation_reviews
  DROP CONSTRAINT IF EXISTS scientist_validation_reviews_terrain_sar_check;
ALTER TABLE public.scientist_validation_reviews
  ADD CONSTRAINT scientist_validation_reviews_terrain_sar_check CHECK (
    terrain_sar_ambiguity IS NULL OR terrain_sar_ambiguity IN (
      'none',
      'terrain_context_required',
      'sar_layover_or_shadow',
      'registration_or_projection_issue',
      'runout_path_uncertain',
      'not_assessed'
    )
  );

ALTER TABLE public.scientist_validation_reviews
  DROP CONSTRAINT IF EXISTS scientist_validation_reviews_evidence_next_check;
ALTER TABLE public.scientist_validation_reviews
  ADD CONSTRAINT scientist_validation_reviews_evidence_next_check CHECK (
    evidence_needed_next IS NULL OR evidence_needed_next IN (
      'none',
      'field_observation',
      'snowpit_or_weak_layer_profile',
      'sar_or_optical_review',
      'historical_event_lookup',
      'benchmark_slice',
      'partner_data_request',
      'not_assessed'
    )
  );

CREATE TABLE IF NOT EXISTS public.scientist_validation_actions (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  case_id uuid NOT NULL REFERENCES public.scientist_validation_cases(id) ON DELETE CASCADE,
  review_id uuid REFERENCES public.scientist_validation_reviews(id) ON DELETE SET NULL,
  action_type text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  priority integer NOT NULL DEFAULT 3,
  summary text NOT NULL,
  owner_role text NOT NULL DEFAULT 'operator',
  evidence_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  CONSTRAINT scientist_validation_actions_type_check CHECK (
    action_type IN (
      'claim_downgrade',
      'claim_block',
      'data_remediation',
      'label_remediation',
      'benchmark_slice',
      'model_gap_candidate',
      'reviewer_disagreement',
      'evidence_request'
    )
  ),
  CONSTRAINT scientist_validation_actions_status_check CHECK (
    status IN ('open', 'in_progress', 'resolved', 'rejected')
  ),
  CONSTRAINT scientist_validation_actions_priority_check CHECK (priority BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_scientist_validation_actions_case
  ON public.scientist_validation_actions (case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scientist_validation_actions_queue
  ON public.scientist_validation_actions (status, priority DESC, created_at DESC)
  WHERE status IN ('open', 'in_progress');

CREATE OR REPLACE FUNCTION public.is_scientist_or_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE((auth.jwt() -> 'app_metadata' -> 'roles') ?| ARRAY['admin', 'scientist'], FALSE);
$$;

GRANT EXECUTE ON FUNCTION public.is_scientist_or_admin() TO anon, authenticated, service_role;

ALTER TABLE public.scientist_validation_actions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Authenticated read validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Scientist or admin read validation cases"
  ON public.scientist_validation_cases FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Authenticated insert validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Scientist or admin insert validation cases"
  ON public.scientist_validation_cases FOR INSERT TO authenticated
  WITH CHECK (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Authenticated update validation cases" ON public.scientist_validation_cases;
CREATE POLICY "Scientist or admin update validation cases"
  ON public.scientist_validation_cases FOR UPDATE TO authenticated
  USING (public.is_scientist_or_admin())
  WITH CHECK (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Authenticated read validation reviews" ON public.scientist_validation_reviews;
CREATE POLICY "Scientist or admin read validation reviews"
  ON public.scientist_validation_reviews FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Authenticated insert validation reviews" ON public.scientist_validation_reviews;
CREATE POLICY "Scientist or admin insert validation reviews"
  ON public.scientist_validation_reviews FOR INSERT TO authenticated
  WITH CHECK (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Scientist or admin read validation actions" ON public.scientist_validation_actions;
CREATE POLICY "Scientist or admin read validation actions"
  ON public.scientist_validation_actions FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Scientist or admin insert validation actions" ON public.scientist_validation_actions;
CREATE POLICY "Scientist or admin insert validation actions"
  ON public.scientist_validation_actions FOR INSERT TO authenticated
  WITH CHECK (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Scientist or admin update validation actions" ON public.scientist_validation_actions;
CREATE POLICY "Scientist or admin update validation actions"
  ON public.scientist_validation_actions FOR UPDATE TO authenticated
  USING (public.is_scientist_or_admin())
  WITH CHECK (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role manage validation actions" ON public.scientist_validation_actions;
CREATE POLICY "Service role manage validation actions"
  ON public.scientist_validation_actions FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.scientist_validation_actions IS
  'Follow-up actions produced by scientist reviews. These records queue claim, data, label, benchmark, or model-gap work without automatically retraining or promoting public scoring.';
