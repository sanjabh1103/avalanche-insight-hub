import { useState, useEffect, useCallback } from 'react';
import type { Database } from '@/integrations/supabase/types';

type SnowpackRun = Database['public']['Functions']['list_snowpack_run_status']['Returns'][number];

const POLL_INTERVAL_MS = 5000;
const MAX_POLL_DURATION_MS = 30 * 60 * 1000; // 30 minutes

export interface UseSnowpackRunsOptions {
  regionKey?: string;
  pocModeOnly?: boolean;
  verifiedOnly?: boolean;
  enabled?: boolean;
  limit?: number;
}

export function useSnowpackRuns(options: UseSnowpackRunsOptions = {}) {
  const { regionKey, pocModeOnly = false, verifiedOnly = false, enabled = true, limit = 10 } = options;
  const [runs, setRuns] = useState<SnowpackRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    const { supabase } = await import('@/integrations/supabase/client');
    const { data, error: fetchError } = await supabase.rpc('list_snowpack_run_status', {
      p_region_key: pocModeOnly ? (regionKey ?? null) : null,
      p_verified_only: verifiedOnly,
      p_limit: limit,
    });

    if (fetchError) {
      setError(fetchError.message);
    } else {
      setRuns(data ?? []);
      setError(null);
    }
    setLoading(false);
  }, [regionKey, pocModeOnly, verifiedOnly, limit]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    fetchRuns();
  }, [enabled, fetchRuns]);

  return { runs, loading, error, refetch: fetchRuns };
}

export function useSnowpackRunStatus(runId: string | null) {
  const [run, setRun] = useState<SnowpackRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      return;
    }

    let cancelled = false;
    const startTime = Date.now();

    const poll = async () => {
      if (cancelled) return;

      const { supabase } = await import('@/integrations/supabase/client');
      const { data, error: fetchError } = await supabase.rpc('get_snowpack_run_status', {
        p_run_id: runId,
      });

      if (cancelled) return;

      if (fetchError) {
        setError(fetchError.message);
        setLoading(false);
        return;
      }

      const currentRun = data?.[0] ?? null;
      if (!currentRun) {
        setError('SNOWPACK run not found');
        setLoading(false);
        return;
      }
      setRun(currentRun);
      setError(null);

      const isTerminal = currentRun.status === 'completed' || currentRun.status === 'failed' || currentRun.status === 'verified';
      const elapsed = Date.now() - startTime;

      if (isTerminal || elapsed > MAX_POLL_DURATION_MS) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setTimeout(poll, POLL_INTERVAL_MS);
    };

    setLoading(true);
    poll();

    return () => {
      cancelled = true;
    };
  }, [runId]);

  return { run, loading, error };
}
