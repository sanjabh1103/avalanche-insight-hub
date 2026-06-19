CREATE EXTENSION IF NOT EXISTS pg_cron;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_enum
    WHERE enumtypid = 'public.job_type'::regtype
      AND enumlabel = 'model_optimization'
  ) THEN
    ALTER TYPE public.job_type ADD VALUE 'model_optimization';
  END IF;
END $$;

ALTER TABLE public.avalanche_events
  ADD COLUMN IF NOT EXISTS detection_mode text NOT NULL DEFAULT 'edge_fallback',
  ADD COLUMN IF NOT EXISTS detection_confidence double precision,
  ADD COLUMN IF NOT EXISTS satellite_scene_ids text[] NOT NULL DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS backscatter_delta_db double precision,
  ADD COLUMN IF NOT EXISTS coherence_drop double precision,
  ADD COLUMN IF NOT EXISTS sar_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.forecasts
  ADD COLUMN IF NOT EXISTS runtime_mode text NOT NULL DEFAULT 'edge_fallback',
  ADD COLUMN IF NOT EXISTS inference_backend text NOT NULL DEFAULT 'edge_fallback',
  ADD COLUMN IF NOT EXISTS capability_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS snowpack_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS optimization_summary jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.forecast_analytics
  ADD COLUMN IF NOT EXISTS runtime_mode text NOT NULL DEFAULT 'edge_fallback',
  ADD COLUMN IF NOT EXISTS capability_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE public.model_status
  ADD COLUMN IF NOT EXISTS snowpack_model_version text,
  ADD COLUMN IF NOT EXISTS optimization_version text,
  ADD COLUMN IF NOT EXISTS sar_pipeline_version text,
  ADD COLUMN IF NOT EXISTS inference_backend text NOT NULL DEFAULT 'edge_fallback',
  ADD COLUMN IF NOT EXISTS capability_summary text NOT NULL DEFAULT 'Edge-only fallback',
  ADD COLUMN IF NOT EXISTS capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS snowpack_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS satellite_detection_stats jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS optimization_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS next_optimization_run timestamptz;

ALTER TABLE public.field_reports
  ADD COLUMN IF NOT EXISTS client_report_id text,
  ADD COLUMN IF NOT EXISTS sync_status text NOT NULL DEFAULT 'synced',
  ADD COLUMN IF NOT EXISTS submitted_offline boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS synced_at timestamptz,
  ADD COLUMN IF NOT EXISTS sync_error text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_field_reports_client_report_id
  ON public.field_reports (client_report_id)
  WHERE client_report_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_compute_jobs_type_created_at
  ON public.compute_jobs (type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_avalanche_events_detection_mode
  ON public.avalanche_events (source, detection_mode, created_at DESC);

COMMENT ON COLUMN public.forecasts.runtime_mode IS 'Runtime mode used for the forecast: full, gpu_only, sar_only, or edge_fallback';
COMMENT ON COLUMN public.forecasts.inference_backend IS 'Forecast inference backend: gpu or edge_fallback';
COMMENT ON COLUMN public.model_status.capability_summary IS 'Human-readable active capability mode for status badges and admin';
COMMENT ON COLUMN public.model_status.capabilities IS 'Structured capability flags and runtime metadata';
COMMENT ON COLUMN public.model_status.optimization_summary IS 'Latest active optimization summary used by forecasts';
COMMENT ON COLUMN public.model_status.satellite_detection_stats IS 'Latest Sentinel-1 refresh stats for admin reporting';
COMMENT ON COLUMN public.field_reports.client_report_id IS 'Client-generated idempotency key for offline-first field report sync';
COMMENT ON COLUMN public.field_reports.sync_status IS 'Field report sync state for queued/offline submissions';

DO $cron$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM cron.job
    WHERE jobname = 'weekly-model-optimization-job'
  ) THEN
    PERFORM cron.schedule(
      'weekly-model-optimization-job',
      '0 2 * * 0',
      $job$SELECT net.http_post(
        url := 'https://cyjqvqwpdgluivjoxcfl.supabase.co/functions/v1/trigger-job',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || COALESCE(current_setting('app.settings.job_dispatch_token', true), ''),
          'apikey', COALESCE(current_setting('app.settings.supabase_anon_key', true), '')
        ),
        body := jsonb_build_object('type', 'model_optimization', 'hazard_type', 'avalanche')
      )$job$
    );
  END IF;
END $cron$;
