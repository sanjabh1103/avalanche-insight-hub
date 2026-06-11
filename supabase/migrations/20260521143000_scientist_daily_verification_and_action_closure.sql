-- Scientist co-working Tier B closure surfaces.
-- Daily verification records support paired scientist-vs-model comparison.
-- Action closure fields support a governed loop without automatic model promotion.

ALTER TABLE public.scientist_validation_actions
  ADD COLUMN IF NOT EXISTS resolution_notes text;

CREATE TABLE IF NOT EXISTS public.scientist_daily_verifications (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  reviewer_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  region_key text,
  region_name text,
  verification_date date NOT NULL,
  forecast_run_id uuid,
  forecast_grid_id uuid,
  forecast_hour integer,
  scientist_danger_level text NOT NULL,
  model_danger_level text NOT NULL,
  observed_outcome text NOT NULL DEFAULT 'unknown',
  official_avalanche_problem text,
  model_avalanche_problem text,
  confidence numeric NOT NULL DEFAULT 0.75,
  notes text,
  evidence_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT scientist_daily_verifications_danger_check CHECK (
    scientist_danger_level IN ('1', '2', '3', '4', '5', 'not_assessed')
    AND model_danger_level IN ('1', '2', '3', '4', '5', 'not_assessed')
  ),
  CONSTRAINT scientist_daily_verifications_outcome_check CHECK (
    observed_outcome IN ('event_observed', 'no_event_observed', 'unknown')
  ),
  CONSTRAINT scientist_daily_verifications_problem_check CHECK (
    (official_avalanche_problem IS NULL OR official_avalanche_problem IN (
      'new_snow',
      'wind_slab',
      'persistent_weak_layers',
      'wet_snow',
      'gliding_snow',
      'cornices',
      'no_distinct_problem',
      'not_assessed'
    ))
    AND
    (model_avalanche_problem IS NULL OR model_avalanche_problem IN (
      'new_snow',
      'wind_slab',
      'persistent_weak_layers',
      'wet_snow',
      'gliding_snow',
      'cornices',
      'no_distinct_problem',
      'not_assessed'
    ))
  ),
  CONSTRAINT scientist_daily_verifications_confidence_check CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS idx_scientist_daily_verifications_region_date
  ON public.scientist_daily_verifications (region_key, verification_date DESC);

CREATE INDEX IF NOT EXISTS idx_scientist_daily_verifications_reviewer
  ON public.scientist_daily_verifications (reviewer_id, created_at DESC);

ALTER TABLE public.scientist_daily_verifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Scientist or admin read daily verifications" ON public.scientist_daily_verifications;
CREATE POLICY "Scientist or admin read daily verifications"
  ON public.scientist_daily_verifications FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Scientist or admin insert daily verifications" ON public.scientist_daily_verifications;
CREATE POLICY "Scientist or admin insert daily verifications"
  ON public.scientist_daily_verifications FOR INSERT TO authenticated
  WITH CHECK (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role manage daily verifications" ON public.scientist_daily_verifications;
CREATE POLICY "Service role manage daily verifications"
  ON public.scientist_daily_verifications FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.scientist_daily_verifications IS
  'Paired scientist-vs-model daily verification records for Techel-style comparison. These records do not alter public scoring or model promotion automatically.';
