-- pgTAP contract checks for the reviewed shadow-training boundary.
-- These checks intentionally prove schema/function presence only. The
-- candidate fixture matrix remains in backend/tests and the live RLS suite;
-- neither path can promote a model or change public risk.
BEGIN;

SELECT plan(5);

SELECT ok(
  to_regclass('public.reviewed_shadow_training_candidates') IS NOT NULL,
  'reviewed shadow candidate table exists'
);

SELECT ok(
  to_regclass('public.scientist_validation_cases') IS NOT NULL,
  'scientist validation case table exists'
);

SELECT ok(
  to_regprocedure('public.materialize_reviewed_shadow_training_candidate()') IS NOT NULL,
  'reviewed shadow materialization function exists'
);

SELECT ok(
  EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgrelid = 'public.reviewed_shadow_training_candidates'::regclass
      AND tgname = 'trg_reviewed_shadow_training_candidates_append_only'
      AND NOT tgisinternal
  ),
  'reviewed shadow candidates are append-only'
);

SELECT ok(
  EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'reviewed_shadow_training_candidates'
      AND policyname = 'Scientist or admin read reviewed shadow candidates'
  ),
  'candidate reads are governed by the scientist/admin policy'
);

SELECT * FROM finish();
ROLLBACK;
