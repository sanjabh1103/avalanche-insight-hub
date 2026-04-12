import { useEffect, useRef } from 'react';
import { supabase } from '@/integrations/supabase/client';
import type { RealtimePostgresChangesPayload } from '@supabase/supabase-js';

export function useRealtimeSubscription<T extends Record<string, unknown>>(
  table: string,
  callback: (payload: RealtimePostgresChangesPayload<T>) => void,
) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    const channel = supabase
      .channel(`realtime-${table}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table },
        (payload) => callbackRef.current(payload as RealtimePostgresChangesPayload<T>),
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [table]);
}
