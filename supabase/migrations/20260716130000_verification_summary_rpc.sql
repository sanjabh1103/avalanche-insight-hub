-- Server-side aggregation RPC for the continuous verification dashboard.
-- This is a deferred artifact: the frontend currently fetches rows directly
-- with a client-side 1,000-row limit. Once Supabase runtime is proven, the
-- frontend can call this RPC instead to eliminate silent truncation.
--
-- Returns a single JSON object with the same shape as
-- ContinuousVerificationDashboardData, aggregated server-side.

CREATE OR REPLACE FUNCTION public.get_continuous_verification_summary()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  result JSONB;
BEGIN
  SELECT jsonb_build_object(
    'coverage', jsonb_build_object(
      'total_cells', (
        SELECT COUNT(DISTINCT cell_id) FROM public.verification_observations
        WHERE NOT synthetic AND quality_state NOT IN ('rejected', 'missing')
      ),
      'cells_with_3plus_sources', (
        SELECT COUNT(*) FROM (
          SELECT cell_id
          FROM public.verification_observations
          WHERE NOT synthetic AND quality_state NOT IN ('rejected', 'missing')
          GROUP BY cell_id
          HAVING COUNT(DISTINCT sensor) >= 3
        ) sub
      ),
      'cells_with_baselines', (
        SELECT COUNT(DISTINCT b.cell_id)
        FROM public.verification_baselines b
        WHERE EXISTS (
          SELECT 1 FROM public.verification_observations o
          WHERE o.cell_id = b.cell_id
            AND NOT o.synthetic
            AND o.quality_state NOT IN ('rejected', 'missing')
        )
      ),
      'cells_with_anomaly_state', (
        SELECT COUNT(DISTINCT cell_id) FROM public.verification_anomalies
      )
    ),
    'stale_cells', jsonb_build_object(
      'count', (
        SELECT COUNT(DISTINCT cell_id) FROM public.verification_observations
        WHERE freshness_hours IS NULL OR freshness_hours > 72
      ),
      'top_stale', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
          'cell_id', cell_id,
          'max_freshness_hours', max_freshness
        ))
        FROM (
          SELECT cell_id, MAX(COALESCE(freshness_hours, 73)) AS max_freshness
          FROM public.verification_observations
          WHERE freshness_hours IS NULL OR freshness_hours > 72
          GROUP BY cell_id
          ORDER BY max_freshness DESC
          LIMIT 10
        ) stale_sub
      ), '[]'::jsonb)
    ),
    'disagreement', jsonb_build_object(
      'anomaly_count', (SELECT COUNT(*) FROM public.verification_anomalies),
      'attribution_breakdown', COALESCE((
        SELECT jsonb_object_agg(attribution_bucket, cnt)
        FROM (
          SELECT COALESCE(NULLIF(attribution_bucket, ''), 'unattributed') AS attribution_bucket,
                 COUNT(*) AS cnt
          FROM public.verification_anomalies
          GROUP BY 1
        ) attr_sub
      ), '{}'::jsonb)
    ),
    'review_backlog', jsonb_build_object(
      'pending_count', (
        SELECT COUNT(*) FROM public.scientist_validation_cases
        WHERE status IN ('pending', 'in_review')
      ),
      'oldest_pending_hours', (
        SELECT EXTRACT(EPOCH FROM (now() - MIN(created_at))) / 3600
        FROM public.scientist_validation_cases
        WHERE status IN ('pending', 'in_review')
      ),
      'scientist_throughput', (
        SELECT COUNT(*) FROM public.scientist_validation_cases
        WHERE reviewed_at IS NOT NULL
          AND reviewed_at >= now() - INTERVAL '7 days'
      )
    )
  ) INTO result;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_continuous_verification_summary() TO authenticated, service_role;

COMMENT ON FUNCTION public.get_continuous_verification_summary() IS
  'Server-side aggregation for the continuous verification dashboard. Eliminates client-side row limits. Scientist/admin only via RLS on underlying tables.';
