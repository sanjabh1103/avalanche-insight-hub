import { useEffect, useRef, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import type { RealtimePostgresChangesPayload, RealtimeChannel } from '@supabase/supabase-js';

// BUG-01 fix: State persistence key for hydrating before live fetch
const getCacheKey = (table: string) => `realtime-cache-${table}`;

export function useRealtimeSubscription<T extends Record<string, unknown>>(
  table: string,
  callback: (payload: RealtimePostgresChangesPayload<T>) => void,
  options?: {
    persistState?: boolean;
    onReconnect?: () => void;
  },
) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;
  const channelRef = useRef<RealtimeChannel | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isActiveRef = useRef(true);

  // Persist state helper
  const persistState = useCallback((payload: RealtimePostgresChangesPayload<T>) => {
    if (options?.persistState !== false) {
      try {
        localStorage.setItem(getCacheKey(table), JSON.stringify({
          payload,
          timestamp: Date.now(),
        }));
      } catch {
        // Ignore localStorage errors
      }
    }
  }, [table, options?.persistState]);

  // Subscribe function with exponential backoff
  const subscribe = useCallback(() => {
    if (!isActiveRef.current) return;

    // Clean up existing channel
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
      channelRef.current = null;
    }

    const channel = supabase
      .channel(`realtime-${table}-${Date.now()}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table },
        (payload) => {
          persistState(payload as RealtimePostgresChangesPayload<T>);
          callbackRef.current(payload as RealtimePostgresChangesPayload<T>);
        },
      )
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          reconnectAttemptsRef.current = 0;
          options?.onReconnect?.();
        } else if (status === 'CHANNEL_ERROR' || status === 'CLOSED') {
          // Exponential backoff retry
          if (isActiveRef.current) {
            const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
            reconnectAttemptsRef.current++;
            reconnectTimeoutRef.current = setTimeout(subscribe, delay);
          }
        }
      });

    channelRef.current = channel;
  }, [table, persistState, options?.onReconnect]);

  useEffect(() => {
    isActiveRef.current = true;

    // BUG-01 fix: Handle visibility change to reconnect when tab becomes visible
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && channelRef.current) {
        // Reconnect when tab becomes visible
        subscribe();
      }
    };

    // BUG-01 fix: Handle window focus for reconnection
    const handleFocus = () => {
      if (channelRef.current) {
        subscribe();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);

    // Initial subscribe
    subscribe();

    return () => {
      isActiveRef.current = false;
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
      }
    };
  }, [subscribe]);

  // BUG-01 fix: Hydrate from cache on mount
  useEffect(() => {
    if (options?.persistState !== false) {
      try {
        const cached = localStorage.getItem(getCacheKey(table));
        if (cached) {
          const { payload } = JSON.parse(cached);
          if (payload) {
            callbackRef.current(payload as RealtimePostgresChangesPayload<T>);
          }
        }
      } catch {
        // Ignore cache parse errors
      }
    }
  }, [table, options?.persistState]);
}

// BUG-01 fix: Helper to get cached state for initial hydration
export function getCachedRealtimeState<T>(table: string): T | null {
  try {
    const cached = localStorage.getItem(getCacheKey(table));
    if (cached) {
      const { payload, timestamp } = JSON.parse(cached);
      // Only use cache if less than 5 minutes old
      if (Date.now() - timestamp < 5 * 60 * 1000) {
        return payload?.new as T || null;
      }
    }
  } catch {
    // Ignore errors
  }
  return null;
}
