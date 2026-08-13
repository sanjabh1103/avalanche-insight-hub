-- Pachama-style immutable forecast evidence and reviewed shadow candidates.
-- This migration does not alter prediction thresholds, publication gates, or
-- snowpack physics. It creates a strictly shadow-only lane from a published
-- forecast case through reviewed, provenance-complete evidence.

ALTER TABLE public.scientist_validation_cases
  ADD COLUMN IF NOT EXISTS case_origin text NOT NULL DEFAULT 'manual';

ALTER TABLE public.scientist_validation_cases
  DROP CONSTRAINT IF EXISTS scientist_validation_cases_origin_check;
ALTER TABLE public.scientist_validation_cases
  ADD CONSTRAINT scientist_validation_cases_origin_check CHECK (
    case_origin IN ('manual', 'forecast_publication')
  );

ALTER TABLE public.scientist_validation_cases
  DROP CONSTRAINT IF EXISTS scientist_validation_cases_type_check;
ALTER TABLE public.scientist_validation_cases
  ADD CONSTRAINT scientist_validation_cases_type_check CHECK (
    case_type IN (
      'weak_layer',
      'runout',
      'false_positive',
      'false_negative',
      'masked_terrain',
      'sar_candidate',
      'model_gate',
      'verification_discrepancy'
    )
  );

CREATE OR REPLACE FUNCTION public.lock_scientist_validation_case_origin()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT'
    AND NEW.case_origin = 'forecast_publication'
    AND auth.role() <> 'service_role' THEN
    RAISE EXCEPTION 'forecast_publication cases may only be created by service role';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.case_origin IS DISTINCT FROM OLD.case_origin THEN
    RAISE EXCEPTION 'scientist_validation_cases.case_origin is immutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_lock_scientist_validation_case_origin
  ON public.scientist_validation_cases;
CREATE TRIGGER trg_lock_scientist_validation_case_origin
  BEFORE INSERT OR UPDATE ON public.scientist_validation_cases
  FOR EACH ROW
  EXECUTE FUNCTION public.lock_scientist_validation_case_origin();

CREATE TABLE IF NOT EXISTS public.reviewed_shadow_training_candidates (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  case_id uuid NOT NULL UNIQUE REFERENCES public.scientist_validation_cases(id) ON DELETE RESTRICT,
  forecast_run_id uuid NOT NULL REFERENCES public.forecast_runs(id) ON DELETE RESTRICT,
  region_key text NOT NULL,
  cell_row integer NOT NULL,
  cell_col integer NOT NULL,
  feature_snapshot_sha256 text NOT NULL CHECK (feature_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  evidence_replay_sha256 text NOT NULL CHECK (evidence_replay_sha256 ~ '^[0-9a-f]{64}$'),
  feature_snapshot jsonb NOT NULL CHECK (
    jsonb_typeof(feature_snapshot) = 'object'
    AND feature_snapshot <> '{}'::jsonb
  ),
  evidence_lineage jsonb NOT NULL CHECK (
    jsonb_typeof(evidence_lineage) = 'object'
    AND evidence_lineage <> '{}'::jsonb
  ),
  review_ids uuid[] NOT NULL,
  review_summary jsonb NOT NULL DEFAULT '[]'::jsonb,
  training_status text NOT NULL DEFAULT 'shadow_only' CHECK (training_status = 'shadow_only'),
  production_eligible boolean NOT NULL DEFAULT false CHECK (production_eligible = false),
  claim_boundary text NOT NULL DEFAULT 'reviewed_shadow_candidate_not_training_or_public_promotion',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reviewed_shadow_training_candidates_run
  ON public.reviewed_shadow_training_candidates (forecast_run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reviewed_shadow_training_candidates_region_cell
  ON public.reviewed_shadow_training_candidates (region_key, cell_row, cell_col, created_at DESC);

ALTER TABLE public.reviewed_shadow_training_candidates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Scientist or admin read reviewed shadow candidates"
  ON public.reviewed_shadow_training_candidates;
CREATE POLICY "Scientist or admin read reviewed shadow candidates"
  ON public.reviewed_shadow_training_candidates FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role insert reviewed shadow candidates"
  ON public.reviewed_shadow_training_candidates;
CREATE POLICY "Service role insert reviewed shadow candidates"
  ON public.reviewed_shadow_training_candidates FOR INSERT TO service_role
  WITH CHECK (true);

CREATE OR REPLACE FUNCTION public.reject_reviewed_shadow_training_candidate_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'reviewed_shadow_training_candidates is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_reviewed_shadow_training_candidates_append_only
  ON public.reviewed_shadow_training_candidates;
CREATE TRIGGER trg_reviewed_shadow_training_candidates_append_only
  BEFORE UPDATE OR DELETE ON public.reviewed_shadow_training_candidates
  FOR EACH ROW
  EXECUTE FUNCTION public.reject_reviewed_shadow_training_candidate_mutation();

COMMENT ON TABLE public.reviewed_shadow_training_candidates IS
  'Reviewed, provenance-complete feature and evidence snapshots for shadow-only research. Never trains or promotes a public forecast automatically.';
