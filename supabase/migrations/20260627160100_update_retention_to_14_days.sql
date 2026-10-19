-- Update forecast retention from 30 days to 14 days to stay within
-- the Supabase free tier 1 GB storage limit (~70 MB/day × 14 = ~980 MB).

DO $$
DECLARE
  existing_job_id bigint;
BEGIN
  SELECT jobid
    INTO existing_job_id
  FROM cron.job
  WHERE jobname = 'forecast-retention-cleanup'
  LIMIT 1;

  IF existing_job_id IS NOT NULL THEN
    PERFORM cron.unschedule(existing_job_id);
  END IF;

  PERFORM cron.schedule(
    'forecast-retention-cleanup',
    '0 3 * * *',
    $job$
      DELETE FROM public.forecast_runs
      WHERE created_at < now() - interval '14 days'
        AND active = FALSE;
    $job$
  );
END $$;
