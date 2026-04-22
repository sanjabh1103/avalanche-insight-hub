import { useState, useEffect, useCallback } from 'react';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';

interface ModelInfo {
  version: string;
  f1_score: number;
  last_inference: string | null;
  data_freshness_hours: number;
  feature_version?: string | null;
  calibration_profile_version?: string | null;
  threshold_profile_version?: string | null;
  capability_summary?: string | null;
  inference_backend?: string | null;
  snowpack_model_version?: string | null;
  last_inference_iso?: string | null;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function ModelStatusBadge() {
  const [status, setStatus] = useState<ModelInfo | null>(null);

  const loadStatus = useCallback(async () => {
    const { data } = await supabase
      .from('model_status')
      .select('version, f1_score, last_inference, data_freshness_hours, feature_version, calibration_profile_version, threshold_profile_version, capability_summary, inference_backend, snowpack_model_version')
      .limit(1)
      .maybeSingle();
    if (data) setStatus(data as unknown as ModelInfo);
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  // BUG-04 fix: Realtime sync with model_status table + polling fallback
  useRealtimeSubscription('model_status', () => { loadStatus(); }, { persistState: true, onReconnect: () => loadStatus() });

  // BUG-04 fix: 30s polling fallback to ensure badge updates even if realtime drops
  useEffect(() => {
    const interval = setInterval(() => {
      loadStatus();
    }, 30000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  // BUG-04 fix: Refresh on window focus/visibility change
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadStatus();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [loadStatus]);

  if (!status) return null;

  return (
    <div className="flex flex-col gap-1">
      <Badge variant="outline" className="gap-1.5 border-emerald-500/30 text-emerald-400 text-xs font-mono w-fit bg-emerald-500/5">
        <BrainCircuit className="h-3 w-3" />
        {status.version} • F1 {status.f1_score?.toFixed(2) ?? '—'}
      </Badge>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Feature: {status.feature_version || 'n/a'} • Calibration: {status.calibration_profile_version || 'n/a'}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Last inference: {timeAgo(status.last_inference)} • Freshness: {status.data_freshness_hours < 999 ? `${status.data_freshness_hours.toFixed(0)}h` : 'sim'}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Mode: {status.capability_summary || 'Edge-only fallback'} • Backend: {status.inference_backend || 'edge_fallback'}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        SAR + Snowpack Simulation + KMeansSMOTE + ABC • Snowpack: {status.snowpack_model_version || 'edge-proxy'}
      </span>
    </div>
  );
}
