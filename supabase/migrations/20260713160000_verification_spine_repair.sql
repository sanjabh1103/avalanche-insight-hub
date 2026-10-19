-- Evidence-Gated Verification Spine repair.
-- Additive migration: observations are immutable evidence; derived baselines
-- and review queue rows remain separate compatibility surfaces.

CREATE TABLE IF NOT EXISTS public.verification_observations (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  region_key TEXT NOT NULL,
  cell_id TEXT NOT NULL,
  sensor TEXT NOT NULL,
  variable TEXT NOT NULL,
  value DOUBLE PRECISION,
  unit TEXT NOT NULL,
  uncertainty DOUBLE PRECISION,
  acquisition_time TIMESTAMPTZ NOT NULL,
  freshness_hours DOUBLE PRECISION,
  quality_state TEXT NOT NULL DEFAULT 'unverified' CHECK (quality_state IN (
    'unverified', 'provisional', 'verified', 'rejected', 'missing'
  )),
  lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
  synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT verification_observations_uncertainty_check CHECK (
    uncertainty IS NULL OR uncertainty >= 0
  ),
  CONSTRAINT verification_observations_freshness_check CHECK (
    freshness_hours IS NULL OR freshness_hours >= 0
  )
);

ALTER TABLE public.verification_observations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Scientist or admin read verification observations"
  ON public.verification_observations;
CREATE POLICY "Scientist or admin read verification observations"
  ON public.verification_observations FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role insert verification observations"
  ON public.verification_observations;
CREATE POLICY "Service role insert verification observations"
  ON public.verification_observations FOR INSERT TO service_role
  WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_verification_observations_region_cell_time
  ON public.verification_observations (region_key, cell_id, acquisition_time DESC);
CREATE INDEX IF NOT EXISTS idx_verification_observations_sensor_variable_time
  ON public.verification_observations (sensor, variable, acquisition_time DESC);

CREATE OR REPLACE FUNCTION public.reject_verification_observation_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'verification_observations is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_verification_observations_append_only
  ON public.verification_observations;
CREATE TRIGGER trg_verification_observations_append_only
  BEFORE UPDATE OR DELETE ON public.verification_observations
  FOR EACH ROW
  EXECUTE FUNCTION public.reject_verification_observation_mutation();

COMMENT ON TABLE public.verification_observations IS
  'Immutable sensor evidence for replayable verification baselines. Never use synthetic or provisional rows as official warnings.';

ALTER TABLE public.verification_review_queue
  ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS priority_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS uncertainty_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS anomaly_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS sparsity_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS verification_basis TEXT,
  ADD COLUMN IF NOT EXISTS sam_preannotation_ref TEXT,
  ADD COLUMN IF NOT EXISTS vae_reconstruction_error DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Fail closed if historical duplicates would make the requested conflict key
-- ambiguous. No rows are deleted by this migration.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.verification_review_queue
    GROUP BY region_key, cell_id
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'verification_review_queue contains duplicate (region_key, cell_id) rows; reconcile them before enabling the conflict key';
  END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_verification_review_queue_region_cell
  ON public.verification_review_queue (region_key, cell_id);

DROP POLICY IF EXISTS "Anyone can view verification review queue"
  ON public.verification_review_queue;
DROP POLICY IF EXISTS "Scientist or admin read verification review queue"
  ON public.verification_review_queue;
CREATE POLICY "Scientist or admin read verification review queue"
  ON public.verification_review_queue FOR SELECT TO authenticated
  USING (public.is_scientist_or_admin());

DROP POLICY IF EXISTS "Service role can manage verification review queue"
  ON public.verification_review_queue;
CREATE POLICY "Service role can manage verification review queue"
  ON public.verification_review_queue FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.verification_review_queue IS
  'Scientist-only active-learning queue. Service role writes are keyed by (region_key, cell_id); public/anonymous reads are blocked.';
