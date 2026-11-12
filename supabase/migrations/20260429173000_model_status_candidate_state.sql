ALTER TABLE public.model_status
  ADD COLUMN IF NOT EXISTS dynamic_model_candidate JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS autonomous_evidence_summary JSONB NOT NULL DEFAULT '{}'::jsonb;
