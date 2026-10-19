-- CAP release approval table — signed human approval before outbound alerts.
-- Requires authority identity, signature, release artifact reference, and audit event.
CREATE TABLE IF NOT EXISTS public.cap_release_approvals (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cap_alert_id TEXT NOT NULL,
  approver_id TEXT NOT NULL,
  approver_name TEXT NOT NULL,
  authority_org TEXT NOT NULL,
  approval_timestamp TIMESTAMPTZ,
  signature TEXT,
  release_artifact_ref TEXT,
  audit_event_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  rejection_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_cap_approval_alert_id
  ON public.cap_release_approvals (cap_alert_id);

CREATE INDEX IF NOT EXISTS idx_cap_approval_status
  ON public.cap_release_approvals (status);

-- RLS: admin only for all operations
ALTER TABLE public.cap_release_approvals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "admin can manage cap approvals"
  ON public.cap_release_approvals
  FOR ALL
  TO authenticated
  USING (public.is_admin())
  WITH CHECK (public.is_admin());
