-- Wave 1 publication plane: decomposed forecast runs + artifact metadata.

INSERT INTO storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
VALUES (
  'forecast-products',
  'forecast-products',
  TRUE,
  104857600,
  ARRAY['application/json', 'application/gzip', 'application/octet-stream']
)
ON CONFLICT (id) DO UPDATE SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

CREATE TABLE IF NOT EXISTS public.forecast_runs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  hazard_type public.hazard_type NOT NULL DEFAULT 'avalanche',
  region_key TEXT NOT NULL,
  region_name TEXT NOT NULL,
  forecast_date DATE NOT NULL,
  issue_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  horizon_hours INTEGER NOT NULL,
  grid_size INTEGER NOT NULL,
  bbox FLOAT8[4] NOT NULL,
  status TEXT NOT NULL DEFAULT 'building',
  publication_status TEXT NOT NULL DEFAULT 'building',
  manifest_storage_ref TEXT,
  runout_storage_ref TEXT,
  compatibility_forecast_grid_id UUID REFERENCES public.forecast_grids(id) ON DELETE SET NULL,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  model_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  weather_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT forecast_runs_horizon_positive CHECK (horizon_hours > 0),
  CONSTRAINT forecast_runs_grid_positive CHECK (grid_size > 0),
  CONSTRAINT forecast_runs_status_check CHECK (status IN ('building', 'ready', 'failed', 'superseded')),
  CONSTRAINT forecast_runs_publication_status_check CHECK (publication_status IN ('building', 'artifacts_written', 'validated', 'published', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS forecast_runs_active_idx
  ON public.forecast_runs (hazard_type, region_key, forecast_date)
  WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS forecast_runs_region_date_idx
  ON public.forecast_runs (hazard_type, region_key, forecast_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS public.forecast_run_hours (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_run_id UUID NOT NULL REFERENCES public.forecast_runs(id) ON DELETE CASCADE,
  forecast_hour INTEGER NOT NULL,
  valid_time TIMESTAMPTZ NOT NULL,
  storage_ref TEXT NOT NULL,
  cell_count INTEGER NOT NULL DEFAULT 0,
  ready_cell_count INTEGER NOT NULL DEFAULT 0,
  stale_cell_count INTEGER NOT NULL DEFAULT 0,
  payload_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT forecast_run_hours_nonnegative CHECK (
    forecast_hour >= 0
    AND cell_count >= 0
    AND ready_cell_count >= 0
    AND stale_cell_count >= 0
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS forecast_run_hours_unique_idx
  ON public.forecast_run_hours (forecast_run_id, forecast_hour);

CREATE TABLE IF NOT EXISTS public.forecast_publication_events (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  forecast_run_id UUID NOT NULL REFERENCES public.forecast_runs(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW public.forecast_active_runs AS
SELECT
  id,
  hazard_type,
  region_key,
  region_name,
  forecast_date,
  issue_time,
  horizon_hours,
  grid_size,
  bbox,
  status,
  publication_status,
  manifest_storage_ref,
  runout_storage_ref,
  compatibility_forecast_grid_id,
  active,
  model_metadata,
  weather_summary,
  published_at,
  created_at,
  updated_at
FROM public.forecast_runs
WHERE active = TRUE
  AND status = 'ready'
  AND publication_status = 'published';

ALTER TABLE public.forecast_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forecast_run_hours ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forecast_publication_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view forecast runs" ON public.forecast_runs;
DROP POLICY IF EXISTS "Service role can manage forecast runs" ON public.forecast_runs;
CREATE POLICY "Anyone can view forecast runs" ON public.forecast_runs FOR SELECT USING (true);
CREATE POLICY "Service role can manage forecast runs" ON public.forecast_runs FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Anyone can view forecast run hours" ON public.forecast_run_hours;
DROP POLICY IF EXISTS "Service role can manage forecast run hours" ON public.forecast_run_hours;
CREATE POLICY "Anyone can view forecast run hours" ON public.forecast_run_hours FOR SELECT USING (true);
CREATE POLICY "Service role can manage forecast run hours" ON public.forecast_run_hours FOR ALL USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Anyone can view forecast publication events" ON public.forecast_publication_events;
DROP POLICY IF EXISTS "Service role can manage forecast publication events" ON public.forecast_publication_events;
CREATE POLICY "Anyone can view forecast publication events" ON public.forecast_publication_events FOR SELECT USING (true);
CREATE POLICY "Service role can manage forecast publication events" ON public.forecast_publication_events FOR ALL USING (auth.role() = 'service_role');

CREATE OR REPLACE FUNCTION public.set_forecast_runs_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_forecast_runs_updated_at ON public.forecast_runs;
CREATE TRIGGER set_forecast_runs_updated_at
BEFORE UPDATE ON public.forecast_runs
FOR EACH ROW
EXECUTE FUNCTION public.set_forecast_runs_updated_at();

CREATE OR REPLACE FUNCTION public.promote_forecast_run(p_forecast_run_id UUID)
RETURNS public.forecast_runs
LANGUAGE plpgsql
AS $$
DECLARE
  target_row public.forecast_runs%ROWTYPE;
BEGIN
  SELECT *
    INTO target_row
  FROM public.forecast_runs
  WHERE id = p_forecast_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'forecast_run % not found', p_forecast_run_id;
  END IF;

  UPDATE public.forecast_runs
     SET active = FALSE,
         status = CASE WHEN id = p_forecast_run_id THEN status ELSE 'superseded' END
   WHERE hazard_type = target_row.hazard_type
     AND region_key = target_row.region_key
     AND forecast_date = target_row.forecast_date
     AND active = TRUE
     AND id <> p_forecast_run_id;

  UPDATE public.forecast_runs
     SET active = TRUE,
         status = 'ready',
         publication_status = 'published',
         published_at = now()
   WHERE id = p_forecast_run_id
   RETURNING * INTO target_row;

  RETURN target_row;
END;
$$;
