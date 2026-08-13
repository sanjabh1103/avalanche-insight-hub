-- Create the model-artifacts storage bucket.
-- This private bucket stores vetted recovery model artifacts (model.joblib,
-- training_metrics.json, feature_schema.json) that the inference workflow
-- restores when no cached training artifact is available from GitHub Actions.
-- The bucket is referenced in .github/workflows/ml_pipeline.yml but was
-- never created by a migration, causing the restore step to fail silently.

INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'model-artifacts',
  'model-artifacts',
  FALSE,
  524288000,
  ARRAY['application/octet-stream', 'application/json', 'application/gzip']
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Note: Storage RLS policies are managed at the Supabase platform level.
-- The service_role key bypasses RLS, so the GitHub Actions workflow can
-- read/write model-artifacts without explicit RLS policies.
