-- Create the private bucket used for operator-approved knowledge-graph
-- snapshots. The model endpoint reads these objects with service_role only;
-- no public or authenticated storage read policy is intended.

INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'knowledge-graph-snapshots',
  'knowledge-graph-snapshots',
  FALSE,
  52428800,
  ARRAY['application/json']
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Storage RLS policies are intentionally absent. The service_role key used by
-- the Edge Function bypasses storage RLS; client roles must not read snapshots.
