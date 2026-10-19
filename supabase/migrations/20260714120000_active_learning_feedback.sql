-- Active learning feedback table — versioned scientist decisions.
-- Stores feedback from scientist validation decisions as versioned labels
-- that feed into drift signals and retraining candidate selection.
CREATE TABLE IF NOT EXISTS public.active_learning_feedback (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  queue_row_id TEXT,
  cell_id TEXT NOT NULL,
  region_key TEXT NOT NULL,
  scientist_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('confirmed', 'anomaly', 'false_positive', 'needs_observation')),
  label_value FLOAT,
  notes TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for drift computation queries
CREATE INDEX IF NOT EXISTS idx_al_feedback_region_cell
  ON public.active_learning_feedback (region_key, cell_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_al_feedback_scientist
  ON public.active_learning_feedback (scientist_id, created_at DESC);

-- RLS: scientist/admin can write and read
ALTER TABLE public.active_learning_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "scientist can insert feedback"
  ON public.active_learning_feedback
  FOR INSERT
  TO authenticated
  WITH CHECK (public.is_scientist_or_admin());

CREATE POLICY "scientist can read feedback"
  ON public.active_learning_feedback
  FOR SELECT
  TO authenticated
  USING (public.is_scientist_or_admin());
