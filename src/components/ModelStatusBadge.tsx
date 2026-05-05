import { useState, useEffect, useCallback } from 'react';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';

interface ModelInfo {
  version: string;
  f1_score: number | null;
  pss_reported?: number | null;
  pss_gate_passed?: boolean | null;
  promotion_gate_passed?: boolean | null;
  shadow_mode_active?: boolean | null;
  active_model_type?: string | null;
  active_model_version?: string | null;
  drift_mode_state?: string | null;
  dynamic_model_candidate?: {
    dynamic_model_type?: string | null;
    dynamic_model_version?: string | null;
    blocked_gate?: string | null;
    ready_for_activation?: boolean | null;
  } | null;
  autonomous_evidence_summary?: {
    positive_count?: number | null;
    manual_positive_count?: number | null;
    autonomous_positive_count?: number | null;
    promoted_sar_volume?: {
      sar_unet_promoted_count?: number | null;
    } | null;
  } | null;
  last_inference: string | null;
  last_trained?: string | null;
  data_freshness_hours: number;
  feature_version?: string | null;
  calibration_profile_version?: string | null;
  threshold_profile_version?: string | null;
  capability_summary?: string | null;
  inference_backend?: string | null;
  latest_benchmark_summary?: {
    benchmark_kind?: string | null;
    total_seconds?: number | null;
    status?: string | null;
  } | null;
  snowpack_model_version?: string | null;
  stability_summary?: {
    classification?: string | null;
    seed_count?: number | null;
  } | null;
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
      .select('version, f1_score, pss_reported, pss_gate_passed, promotion_gate_passed, shadow_mode_active, active_model_type, active_model_version, drift_mode_state, dynamic_model_candidate, autonomous_evidence_summary, last_inference, last_trained, data_freshness_hours, feature_version, calibration_profile_version, threshold_profile_version, capability_summary, inference_backend, latest_benchmark_summary, snowpack_model_version, stability_summary')
      .order('last_inference', { ascending: false, nullsFirst: false })
      .order('last_trained', { ascending: false, nullsFirst: false })
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

  const activeModelLabel = status.active_model_type || status.feature_version || 'surrogate_rf_v1';
  const activeModelVersion = status.active_model_version || status.calibration_profile_version || 'n/a';
  const candidateModelLabel = status.dynamic_model_candidate?.dynamic_model_type || 'mts_lstm_v1';
  const candidateModelVersion = status.dynamic_model_candidate?.dynamic_model_version || 'n/a';
  const candidateGate = status.dynamic_model_candidate?.ready_for_activation
    ? 'ready'
    : status.dynamic_model_candidate?.blocked_gate || 'unavailable';
  const releaseEvidence = status.shadow_mode_active
    ? 'candidate shadow'
    : status.promotion_gate_passed
      ? 'promotion passed'
      : 'promotion hold';
  const freshnessLabel = typeof status.data_freshness_hours === 'number' && status.data_freshness_hours < 999
    ? `${status.data_freshness_hours.toFixed(0)}h`
    : 'sim';
  const evidence = status.autonomous_evidence_summary;
  const stabilityLabel = status.stability_summary?.classification || 'n/a';
  const stabilitySeedCount = status.stability_summary?.seed_count;
  const benchmarkKind = status.latest_benchmark_summary?.benchmark_kind || 'n/a';
  const benchmarkStatus = status.latest_benchmark_summary?.status || 'n/a';

  return (
    <div className="flex flex-col gap-1">
      <Badge variant="outline" className="gap-1.5 border-emerald-500/30 text-emerald-400 text-xs font-mono w-fit bg-emerald-500/5">
        <BrainCircuit className="h-3 w-3" />
        {status.version} • PSS {status.pss_reported?.toFixed(2) ?? '—'}
      </Badge>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Customer-serving scorer (active): {activeModelLabel} • Version: {activeModelVersion}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Dynamic scorer (candidate): {candidateModelLabel} • Version: {candidateModelVersion} • Gate: {candidateGate}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Last precomputed batch: {timeAgo(status.last_inference)} • Freshness: {freshnessLabel}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Release evidence: {releaseEvidence} • Backend: {status.inference_backend || 'edge_fallback'} • PSS gate: {status.pss_gate_passed ? 'pass' : 'hold'}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Confidence proxy: F1 {status.f1_score?.toFixed(2) ?? '—'} • Snowpack: {status.snowpack_model_version || 'edge-proxy'}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Evidence mix: auto {evidence?.autonomous_positive_count ?? 0}/{evidence?.positive_count ?? 0} • manual {evidence?.manual_positive_count ?? 0} • promoted SAR {evidence?.promoted_sar_volume?.sar_unet_promoted_count ?? 0}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Drift mode: {status.drift_mode_state || 'guarded_monitoring_only'} • Stability: {stabilityLabel}{typeof stabilitySeedCount === 'number' ? ` • ${stabilitySeedCount} seeds` : ''}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Benchmark: {benchmarkKind} • {benchmarkStatus} • {typeof status.latest_benchmark_summary?.total_seconds === 'number' ? `${status.latest_benchmark_summary.total_seconds.toFixed(1)}s` : 'n/a'}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5 leading-tight">
        Governance scope: operator evidence only; public promotion remains gated
      </span>
    </div>
  );
}
