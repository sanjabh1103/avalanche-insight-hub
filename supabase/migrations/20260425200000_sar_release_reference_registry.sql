-- Authoritative held-out SAR release reference registry.
--
-- This registry locks the SAR promotion gate to a curated external truth set
-- instead of ad hoc manifest refs. Seed scripts populate draft rows first,
-- baseline materialization completes the items, and only then may one
-- authoritative set become active for the SAR release gate.

CREATE TABLE IF NOT EXISTS public.sar_release_reference_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  set_key text NOT NULL UNIQUE,
  source_name text NOT NULL DEFAULT 'snowslide_slf',
  source_version text NOT NULL,
  split_name text NOT NULL,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  purpose text NOT NULL DEFAULT 'sar_release_gate',
  authoritative boolean NOT NULL DEFAULT TRUE,
  status text NOT NULL DEFAULT 'draft',
  registry_asset_ref text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT NOW(),
  updated_at timestamptz NOT NULL DEFAULT NOW(),
  CONSTRAINT sar_release_reference_sets_source_name_check
    CHECK (source_name = 'snowslide_slf'),
  CONSTRAINT sar_release_reference_sets_purpose_check
    CHECK (purpose = 'sar_release_gate'),
  CONSTRAINT sar_release_reference_sets_status_check
    CHECK (status IN ('draft', 'active', 'retired'))
);

CREATE TABLE IF NOT EXISTS public.sar_release_reference_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_set_id uuid NOT NULL REFERENCES public.sar_release_reference_sets(id) ON DELETE CASCADE,
  external_scene_id text NOT NULL,
  region_key text NOT NULL,
  scene_time timestamptz,
  bbox jsonb NOT NULL DEFAULT '[]'::jsonb,
  stack_asset_ref text NOT NULL,
  truth_mask_asset_ref text NOT NULL,
  baseline_mask_asset_ref text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT NOW(),
  updated_at timestamptz NOT NULL DEFAULT NOW(),
  CONSTRAINT sar_release_reference_items_unique_scene
    UNIQUE (reference_set_id, external_scene_id),
  CONSTRAINT sar_release_reference_items_stack_asset_ref_check
    CHECK (length(btrim(stack_asset_ref)) > 0),
  CONSTRAINT sar_release_reference_items_truth_mask_asset_ref_check
    CHECK (length(btrim(truth_mask_asset_ref)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_sar_release_reference_sets_status
  ON public.sar_release_reference_sets (hazard_type, purpose, status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sar_release_reference_sets_active_authoritative
  ON public.sar_release_reference_sets (hazard_type, purpose)
  WHERE authoritative = TRUE AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_sar_release_reference_items_set_region_time
  ON public.sar_release_reference_items (reference_set_id, region_key, scene_time DESC);

COMMENT ON TABLE public.sar_release_reference_sets IS
  'Registry of authoritative external held-out SAR truth sets used to gate SAR promotion out of shadow mode.';

COMMENT ON TABLE public.sar_release_reference_items IS
  'Per-scene held-out SAR references: canonical input stack, authoritative truth mask, baseline mask, and scene metadata.';

ALTER TABLE public.sar_release_reference_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sar_release_reference_items ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'sar_release_reference_sets' AND policyname = 'sar_release_reference_sets_read'
  ) THEN
    CREATE POLICY sar_release_reference_sets_read
      ON public.sar_release_reference_sets
      FOR SELECT
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'sar_release_reference_sets' AND policyname = 'sar_release_reference_sets_service_write'
  ) THEN
    CREATE POLICY sar_release_reference_sets_service_write
      ON public.sar_release_reference_sets
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'sar_release_reference_items' AND policyname = 'sar_release_reference_items_read'
  ) THEN
    CREATE POLICY sar_release_reference_items_read
      ON public.sar_release_reference_items
      FOR SELECT
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'sar_release_reference_items' AND policyname = 'sar_release_reference_items_service_write'
  ) THEN
    CREATE POLICY sar_release_reference_items_service_write
      ON public.sar_release_reference_items
      FOR ALL
      TO service_role
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;
