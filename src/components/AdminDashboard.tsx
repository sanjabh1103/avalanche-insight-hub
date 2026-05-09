import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Zap, Satellite, BrainCircuit, Database, TrendingUp, CloudSnow, Activity, Tag, BarChart3, FileCheck, RefreshCw, Check, Minus } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';
import { DEFAULT_BBOX } from '@/lib/constants';

type JobType = 'daily_enrichment' | 'sentinel_refresh' | 'fine_tune' | 'static_precompute' | 'snow_cover_refresh' | 'recent_activity_refresh' | 'label_forecast_outcomes' | 'run_evaluation' | 'retrain_avalanche_model' | 'field_report_enrichment' | 'model_optimization';

// BUG-01 fix: Cache keys for state persistence
const CACHE_KEYS = {
  jobs: 'admin-jobs-cache',
  modelStatus: 'admin-model-status-cache',
  fieldReports: 'admin-field-reports-cache',
};

interface CapabilityMap {
  mode?: string;
  summary?: string;
  sar_enabled?: boolean;
  gpu_enabled?: boolean;
}

interface SnowpackMetrics {
  ram_hardness?: number;
  shear_strength?: number;
  settlement_rate?: number;
  confidence?: number;
  source?: string;
}

interface OptimizationSummary {
  optimization_version?: string;
  feature_weights?: Record<string, number>;
  selected_features?: string[];
  class_balance_report?: Record<string, unknown>;
  abc_enabled?: boolean;
  runtime_mode?: string;
  origin?: string;
}

interface SatelliteDetectionStats {
  last_refresh_at?: string;
  scenes_found?: number;
  detections_inserted?: number;
  mode?: string;
  fallback_used?: boolean;
}

interface DynamicModelCandidate {
  dynamic_model_type?: string | null;
  dynamic_model_version?: string | null;
  blocked_gate?: string | null;
  ready_for_activation?: boolean | null;
}

interface AutonomousEvidenceSummary {
  positive_count?: number | null;
  manual_positive_count?: number | null;
  autonomous_positive_count?: number | null;
  promoted_sar_volume?: {
    sar_unet_promoted_count?: number | null;
    sar_unet_promoted_region_count?: number | null;
  } | null;
}

interface SourceHealthSummary {
  support_status?: string | null;
  overall_completeness?: number | null;
  weather_freshness_hours?: number | null;
  sar_coverage_mode?: string | null;
  snowpack_proxy_available?: boolean | null;
  missing_features?: string[] | null;
}

interface DecisionProvenanceSummary {
  threshold_profile?: string | null;
  threshold_profile_origin?: string | null;
  dominant_mapping?: string | null;
  frequency_threshold_profile?: string | null;
  aggregation_policy?: string | null;
  calibration_method?: string | null;
  selected_feature_count?: number | null;
}

interface StabilitySummary {
  classification?: string | null;
  seed_count?: number | null;
  pss_std?: number | null;
  threshold_drift?: number | null;
  selected_feature_overlap_mean?: number | null;
}

interface BenchmarkSummary {
  benchmark_kind?: string | null;
  status?: string | null;
  total_seconds?: number | null;
  phase_breakdown_seconds?: Record<string, number> | null;
}

interface JobRow {
  id: string;
  type: string;
  status: string;
  created_at: string;
  error: string | null;
  result: Record<string, unknown> | null;
}

interface AnalyticsRow {
  region_name: string;
  count: number;
}

interface EvaluationRunRow {
  id: string;
  run_name: string;
  status: string;
  created_at: string;
  model_version: string;
  label_version: string;
  overall_brier_score: number | null;
  overall_precision_risk4: number | null;
  overall_precision_risk3: number | null;
  overall_recall: number | null;
  overall_ece: number | null;
  overall_false_alarm_rate: number | null;
}

interface ForecastOutcomeRow {
  id: string;
  forecast_id: string;
  hazard_type: string;
  forecast_hour: number;
  cell_row: number;
  cell_col: number;
  event_observed: boolean;
  severity_label: string | null;
  label_confidence: number;
  created_at: string;
}

interface EvaluationMetricRow {
  id: string;
  slice_type: string;
  slice_value: string;
  precision_risk3: number | null;
  recall_risk3: number | null;
  ece: number | null;
  false_alarm_rate: number | null;
  total_forecasts: number;
  observed_events: number;
  created_at: string;
}

interface FieldReportRow {
  id: string;
  created_at: string;
  description: string | null;
  client_report_id?: string | null;
  review_status: string;
  training_eligible: boolean;
}

interface GroundsourceEventRow {
  id: string;
  timestamp: string;
  description: string | null;
  source: string;
  label_confidence: number | null;
  training_weight: number | null;
  verification_status?: string | null;
  features: Record<string, unknown> | null;
}

interface ForecastRunRow {
  id: string;
  region_key: string;
  region_name: string;
  forecast_date: string;
  status: string;
  publication_status: string;
  active: boolean;
  manifest_storage_ref: string | null;
  compatibility_forecast_grid_id: string | null;
  published_at: string | null;
  created_at: string;
  model_metadata: Record<string, unknown> | null;
}

interface ForecastRunHourRow {
  forecast_run_id: string;
  forecast_hour: number;
  ready_cell_count: number;
  stale_cell_count: number;
}

interface ForecastPublicationEventRow {
  id: string;
  forecast_run_id: string;
  stage: string;
  status: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}

interface ModelStatusRow {
  version: string;
  f1_score: number | null;
  pss_reported?: number | null;
  pss_gate_passed?: boolean | null;
  promotion_gate_passed?: boolean | null;
  shadow_mode_active?: boolean | null;
  active_model_type?: string | null;
  active_model_version?: string | null;
  drift_mode_state?: string | null;
  dynamic_model_candidate?: DynamicModelCandidate | null;
  autonomous_evidence_summary?: AutonomousEvidenceSummary | null;
  feature_version?: string;
  calibration_profile_version?: string;
  latest_benchmark_summary?: BenchmarkSummary | null;
  threshold_profile_version?: string;
  capability_summary?: string;
  inference_backend?: string;
  snowpack_model_version?: string;
  optimization_version?: string;
  next_optimization_run?: string | null;
  capabilities?: CapabilityMap | null;
  optimization_summary?: OptimizationSummary | null;
  satellite_detection_stats?: SatelliteDetectionStats | null;
  snowpack_metrics?: SnowpackMetrics | null;
  stability_summary?: StabilitySummary | null;
  last_trained?: string | null;
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : 'n/a';
}

function formatSeconds(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}s` : 'n/a';
}

const JOB_BUTTONS: { type: JobType; label: string; icon: React.ReactNode; description?: string }[] = [
  { type: 'daily_enrichment', label: 'Run Enrichment', icon: <Zap className="h-4 w-4" />, description: 'News + Gemini event extraction' },
  { type: 'sentinel_refresh', label: 'Refresh Sentinel-1', icon: <Satellite className="h-4 w-4" />, description: 'ASF metadata search' },
  { type: 'snow_cover_refresh', label: 'Snow Cover', icon: <CloudSnow className="h-4 w-4" />, description: 'NASA GIBS snow summary' },
  { type: 'recent_activity_refresh', label: 'Recent Activity', icon: <Activity className="h-4 w-4" />, description: 'Materialize event summaries' },
  { type: 'label_forecast_outcomes', label: 'Label Outcomes', icon: <Tag className="h-4 w-4" />, description: 'Match forecasts to events' },
  { type: 'run_evaluation', label: 'Run Evaluation', icon: <BarChart3 className="h-4 w-4" />, description: 'Compute metrics by slice' },
  { type: 'field_report_enrichment', label: 'Normalize Reports', icon: <FileCheck className="h-4 w-4" />, description: 'Process field reports' },
  { type: 'retrain_avalanche_model', label: 'Retrain Model', icon: <RefreshCw className="h-4 w-4" />, description: 'External training trigger' },
  { type: 'fine_tune', label: 'Fine-Tune Model', icon: <BrainCircuit className="h-4 w-4" />, description: 'Simulated F1 improvement' },
  { type: 'model_optimization', label: 'Optimize Model', icon: <BrainCircuit className="h-4 w-4" />, description: 'KMeansSMOTE + SVM-RFE + ABC' },
  { type: 'static_precompute', label: 'Static Pre-Compute', icon: <Database className="h-4 w-4" />, description: 'Region pre-computation' },
];

export default function AdminDashboard() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [systemConfig, setSystemConfig] = useState<{ gemini_usage: number; gemini_spend_cap: number } | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatusRow | null>(null);
  const [analytics, setAnalytics] = useState<{ total: number; regions: AnalyticsRow[] }>({ total: 0, regions: [] });
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRunRow[]>([]);
  const [evaluationMetrics, setEvaluationMetrics] = useState<EvaluationMetricRow[]>([]);
  const [forecastOutcomes, setForecastOutcomes] = useState<ForecastOutcomeRow[]>([]);
  const [fieldReports, setFieldReports] = useState<FieldReportRow[]>([]);
  const [groundsourceEvents, setGroundsourceEvents] = useState<GroundsourceEventRow[]>([]);
  const [forecastRuns, setForecastRuns] = useState<ForecastRunRow[]>([]);
  const [forecastRunHours, setForecastRunHours] = useState<ForecastRunHourRow[]>([]);
  const [forecastPublicationEvents, setForecastPublicationEvents] = useState<ForecastPublicationEventRow[]>([]);
  const activeJobs = jobs.filter((job) => job.status === 'running').length;
  const latestFineTuneJob = jobs.find((job) => job.type === 'fine_tune');
  const latestFineTuneResult = latestFineTuneJob?.result as { publish_skipped?: string } | null | undefined;
  const syntheticBootstrapSkipped = latestFineTuneResult?.publish_skipped === 'synthetic_bootstrap';

  const forecastHourStats = useMemo(() => {
    const stats = new Map<string, { hourCount: number; readyCells: number; staleCells: number; maxHour: number }>();
    forecastRunHours.forEach((hour) => {
      const existing = stats.get(hour.forecast_run_id) ?? { hourCount: 0, readyCells: 0, staleCells: 0, maxHour: -1 };
      existing.hourCount += 1;
      existing.readyCells += hour.ready_cell_count ?? 0;
      existing.staleCells += hour.stale_cell_count ?? 0;
      existing.maxHour = Math.max(existing.maxHour, hour.forecast_hour ?? -1);
      stats.set(hour.forecast_run_id, existing);
    });
    return stats;
  }, [forecastRunHours]);

  const publicationEventsByRun = useMemo(() => {
    const events = new Map<string, ForecastPublicationEventRow[]>();
    forecastPublicationEvents.forEach((event) => {
      const existing = events.get(event.forecast_run_id) ?? [];
      existing.push(event);
      existing.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      events.set(event.forecast_run_id, existing);
    });
    return events;
  }, [forecastPublicationEvents]);

  // CRASH-FIX: Prevent concurrent data loading that causes ERR_INSUFFICIENT_RESOURCES
  const isLoadingRef = useRef(false);
  const loadDataTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // CRASH-FIX: Debounced loadData with concurrency protection
  const loadData = useCallback(async () => {
    // Prevent concurrent calls that cause ERR_INSUFFICIENT_RESOURCES
    if (isLoadingRef.current) {
      return;
    }

    isLoadingRef.current = true;

    try {
      const [
        jobsRes,
        configRes,
        modelRes,
        analyticsRes,
        evaluationRunsRes,
        evaluationMetricsRes,
        outcomesRes,
        reportsRes,
        groundsourceEventsRes,
        forecastRunsRes,
        forecastRunHoursRes,
        forecastPublicationEventsRes,
      ] = await Promise.all([
        supabase.from('compute_jobs').select('*').order('created_at', { ascending: false }).limit(10),
        supabase.from('system_config').select('*').limit(1).maybeSingle(),
        supabase
          .from('model_status')
          .select('*')
          .order('last_inference', { ascending: false, nullsFirst: false })
          .order('last_trained', { ascending: false, nullsFirst: false })
          .limit(1)
          .maybeSingle(),
        supabase.from('forecast_analytics').select('*').order('created_at', { ascending: false }).limit(100),
        supabase.from('evaluation_runs').select('*').order('created_at', { ascending: false }).limit(5),
        supabase.from('evaluation_metrics').select('*').order('created_at', { ascending: false }).limit(10),
        supabase.from('forecast_outcomes').select('*').order('created_at', { ascending: false }).limit(5),
        supabase.from('field_reports').select('id, created_at, client_report_id, description, review_status, training_eligible').order('created_at', { ascending: false }).limit(5),
        supabase
          .from('avalanche_events')
          .select('id, timestamp, description, source, label_confidence, training_weight, verification_status, features')
          .eq('source', 'field_report')
          .order('timestamp', { ascending: false })
          .limit(5),
        supabase
          .from('forecast_runs')
          .select('id, region_key, region_name, forecast_date, status, publication_status, active, manifest_storage_ref, compatibility_forecast_grid_id, published_at, created_at, model_metadata')
          .order('created_at', { ascending: false })
          .limit(6),
        supabase
          .from('forecast_run_hours')
          .select('forecast_run_id, forecast_hour, ready_cell_count, stale_cell_count, created_at')
          .order('created_at', { ascending: false })
          .limit(432),
        supabase
          .from('forecast_publication_events')
          .select('id, forecast_run_id, stage, status, detail, created_at')
          .order('created_at', { ascending: false })
          .limit(40),
      ]);
      if (jobsRes.data) setJobs(jobsRes.data as unknown as JobRow[]);
      if (configRes.data) setSystemConfig(configRes.data as unknown as { gemini_usage: number; gemini_spend_cap: number });
      if (modelRes.data) setModelStatus(modelRes.data as unknown as ModelStatusRow);
      if (analyticsRes.data) {
        const rows = analyticsRes.data as unknown as { region_name: string }[];
        const regionMap = new Map<string, number>();
        rows.forEach(r => regionMap.set(r.region_name || 'Unknown', (regionMap.get(r.region_name || 'Unknown') || 0) + 1));
        const regions = Array.from(regionMap.entries()).map(([region_name, count]) => ({ region_name, count })).sort((a, b) => b.count - a.count);
        setAnalytics({ total: rows.length, regions: regions.slice(0, 5) });
      }
      if (evaluationRunsRes.data) setEvaluationRuns(evaluationRunsRes.data as unknown as EvaluationRunRow[]);
      if (evaluationMetricsRes.data) setEvaluationMetrics(evaluationMetricsRes.data as unknown as EvaluationMetricRow[]);
      if (outcomesRes.data) setForecastOutcomes(outcomesRes.data as unknown as ForecastOutcomeRow[]);
      if (reportsRes.data) setFieldReports(reportsRes.data as unknown as FieldReportRow[]);
      if (groundsourceEventsRes.data) setGroundsourceEvents(groundsourceEventsRes.data as unknown as GroundsourceEventRow[]);
      if (forecastRunsRes.data) setForecastRuns(forecastRunsRes.data as unknown as ForecastRunRow[]);
      if (forecastRunHoursRes.data) setForecastRunHours(forecastRunHoursRes.data as unknown as ForecastRunHourRow[]);
      if (forecastPublicationEventsRes.data) {
        setForecastPublicationEvents(forecastPublicationEventsRes.data as unknown as ForecastPublicationEventRow[]);
      }
    } finally {
      isLoadingRef.current = false;
    }
  }, []);

  // CRASH-FIX: Debounced wrapper for realtime callbacks
  const debouncedLoadData = useCallback(() => {
    if (loadDataTimeoutRef.current) {
      clearTimeout(loadDataTimeoutRef.current);
    }
    loadDataTimeoutRef.current = setTimeout(() => {
      loadData();
    }, 500); // 500ms debounce
  }, [loadData]);

  useEffect(() => {
    loadData();

    // Cleanup timeout on unmount
    return () => {
      if (loadDataTimeoutRef.current) {
        clearTimeout(loadDataTimeoutRef.current);
      }
    };
  }, [loadData]);

  // CRASH-FIX: Use debounced loadData for realtime subscriptions to prevent request storms
  useRealtimeSubscription('compute_jobs', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('evaluation_runs', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('evaluation_metrics', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('forecast_outcomes', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('forecasts', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('field_reports', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('avalanche_events', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });
  useRealtimeSubscription('model_status', () => { debouncedLoadData(); }, { persistState: true, onReconnect: () => debouncedLoadData() });

  const triggerJob = async (type: JobType) => {
    setRunning(type);
    try {
      // Build job payload based on type
      const payload: Record<string, unknown> = { type, hazard_type: 'avalanche' };

      // Add bbox for jobs that need spatial context
      if (['sentinel_refresh', 'snow_cover_refresh'].includes(type)) {
        payload.bbox = DEFAULT_BBOX;
      }

      const { data, error } = await supabase.functions.invoke('trigger-job', {
        body: payload,
      });
      if (error) throw error;

      // B7/B8/B14 fix: Specific success messages for each job type
      const successMessages: Record<JobType, string> = {
        daily_enrichment: 'Daily enrichment started - news and event extraction running',
        sentinel_refresh: 'Sentinel-1 refresh triggered successfully',
        snow_cover_refresh: 'Snow cover refresh started - NASA GIBS data ingestion running',
        recent_activity_refresh: 'Recent activity refresh started - materializing event summaries',
        label_forecast_outcomes: 'Labeling forecast outcomes - matching predictions to observed events',
        run_evaluation: 'Evaluation run started - computing precision, recall, and calibration metrics',
        field_report_enrichment: 'Field report enrichment started - normalizing submissions',
        retrain_avalanche_model: 'Model retraining queued - external training pipeline triggered',
        fine_tune: 'Fine-tuning complete - model version incremented with improved F1 score',
        model_optimization: 'Optimization started - dual-mode feature selection and weighting in progress',
        static_precompute: 'Static pre-computation started - caching regional forecasts',
      };
      if (type === 'fine_tune' && data?.result?.publish_skipped === 'synthetic_bootstrap') {
        toast.warning('Fine-tune skipped: synthetic bootstrap model was not overwritten');
      } else {
        toast.success(successMessages[type] || `${type.replace(/_/g, ' ')} completed successfully`);
      }
      loadData();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Job trigger failed');
    } finally {
      setRunning(null);
    }
  };

  const statusColor = (s: string) => {
    switch (s) {
      case 'completed': return 'bg-green-500/20 text-green-400';
      case 'running': return 'bg-yellow-500/20 text-yellow-400';
      case 'failed': return 'bg-red-500/20 text-red-400';
      case 'pending': return 'bg-amber-500/15 text-amber-300';
      case 'under_review': return 'bg-sky-500/15 text-sky-300';
      case 'approved': return 'bg-emerald-500/15 text-emerald-400';
      case 'rejected': return 'bg-red-500/20 text-red-400';
      case 'needs_info': return 'bg-violet-500/15 text-violet-300';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const publicationStatusColor = (status: string) => {
    switch (status) {
      case 'published':
      case 'ready':
      case 'ok':
        return 'bg-emerald-500/15 text-emerald-400';
      case 'validated':
      case 'artifacts_written':
      case 'building':
      case 'pending':
        return 'bg-sky-500/15 text-sky-300';
      case 'failed':
      case 'error':
        return 'bg-red-500/20 text-red-400';
      case 'superseded':
        return 'bg-amber-500/15 text-amber-300';
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

  const asRecord = (value: unknown): Record<string, unknown> | null => (
    value !== null && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null
  );

  const latestForecastMetadata = asRecord(forecastRuns[0]?.model_metadata);
  const latestSourceHealth = asRecord(latestForecastMetadata?.source_health) as SourceHealthSummary | null;
  const latestDecisionProvenance = asRecord(latestForecastMetadata?.decision_provenance) as DecisionProvenanceSummary | null;
  const latestGovernanceScope = asRecord(latestForecastMetadata?.governance_scope);
  const capabilityMode = modelStatus?.capability_summary || modelStatus?.capabilities?.summary || 'Edge-only fallback';
  const activeModelLabel = modelStatus?.active_model_type || modelStatus?.feature_version || 'surrogate_rf_v1';
  const activeModelVersion = modelStatus?.active_model_version || modelStatus?.calibration_profile_version || 'n/a';
  const candidateModelLabel = modelStatus?.dynamic_model_candidate?.dynamic_model_type || 'mts_lstm_v1';
  const candidateModelVersion = modelStatus?.dynamic_model_candidate?.dynamic_model_version || 'n/a';
  const candidateGate = modelStatus?.dynamic_model_candidate?.ready_for_activation
    ? 'ready'
    : modelStatus?.dynamic_model_candidate?.blocked_gate || 'unavailable';
  const releaseEvidence = modelStatus?.shadow_mode_active
    ? 'candidate shadow'
    : modelStatus?.promotion_gate_passed
      ? 'promotion passed'
      : 'promotion hold';
  const optimizationSummary = modelStatus?.optimization_summary;
  const abcEnabled = optimizationSummary?.abc_enabled;
  const snowpackMetrics = modelStatus?.snowpack_metrics;
  const satelliteStats = modelStatus?.satellite_detection_stats;
  const evidenceSummary = modelStatus?.autonomous_evidence_summary;
  const stabilitySummary = modelStatus?.stability_summary;
  const latestBenchmarkSummary = modelStatus?.latest_benchmark_summary;
  const extractLocationName = (features: Record<string, unknown> | null) => (
    typeof features?.location_name === 'string' && features.location_name.trim().length > 0
      ? features.location_name.trim()
      : 'Unknown'
  );
  const fieldReportEventsByReportId = useMemo(() => {
    const mapping = new Map<string, GroundsourceEventRow>();
    groundsourceEvents.forEach((event) => {
      const fieldReportId = typeof event.features?.field_report_id === 'string'
        ? event.features.field_report_id
        : null;
      const clientReportId = typeof event.features?.client_report_id === 'string'
        ? event.features.client_report_id
        : null;
      if (fieldReportId) {
        mapping.set(fieldReportId, event);
      }
      if (clientReportId && !mapping.has(clientReportId)) {
        mapping.set(clientReportId, event);
      }
    });
    return mapping;
  }, [groundsourceEvents]);

  return (
    <div className="space-y-2 p-2.5 md:p-3">
      {/* System Controls */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl shadow-lg shadow-black/20">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground">System Controls</CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {JOB_BUTTONS.map((btn) => (
              <Button
                key={btn.type}
                variant="outline"
                size="sm"
                className="text-xs h-auto min-h-[2.25rem] py-1.5 justify-start gap-2 rounded-2xl border-border/70 bg-black/10 hover:bg-white/5"
                disabled={running !== null}
                onClick={() => triggerJob(btn.type)}
                title={btn.description}
              >
                {running === btn.type ? <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" /> : <span className="shrink-0">{btn.icon}</span>}
                <span className="truncate">{btn.label}</span>
              </Button>
            ))}
          </div>
          <div className="text-[10px] text-muted-foreground mt-1">
            Mode-aware controls for Sentinel, snowpack, optimization, and evaluation
          </div>
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="p-2.5 flex items-center justify-between gap-2">
          <div>
            <div className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Active Jobs</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">Realtime count of running compute jobs</div>
          </div>
          <Badge className="bg-amber-500/15 text-amber-300 border-0 font-mono text-xs rounded-full">
            {activeJobs}
          </Badge>
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardContent className="p-2.5 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-[0.24em]">Current Mode</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Precomputed delivery with gated scorer promotion</div>
            </div>
            <Badge className="bg-sky-500/15 text-sky-300 border-0 font-mono text-[10px] rounded-full">
              {modelStatus?.inference_backend || 'batch_async'}
            </Badge>
          </div>
            <div className="text-sm font-mono text-foreground">{capabilityMode}</div>
            <div className="text-[10px] text-muted-foreground">
              Customer-serving scorer (active): {activeModelLabel} • Release evidence: {releaseEvidence}
            </div>
            <div className="text-[10px] text-muted-foreground">
              Dynamic scorer (candidate): {candidateModelLabel} • Gate: {candidateGate}
            </div>
            <div className="text-[10px] text-muted-foreground">
              Authoritative SAR: artifact-gated • Whitebox runout: artifact-gated
            </div>
            <div className="text-[10px] text-muted-foreground">
              Current-state interpretation: governance evidence and benchmark traces for gated promotion review.
            </div>
          </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <Database className="h-3 w-3" />
            Forecast Publication
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5 space-y-1.5">
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <div>
              <div className="text-muted-foreground">Recent runs</div>
              <div className="font-mono text-foreground">{forecastRuns.length}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Active recent</div>
              <div className="font-mono text-foreground">{forecastRuns.filter((run) => run.active).length}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Published</div>
              <div className="font-mono text-foreground">
                {forecastRuns.filter((run) => run.publication_status === 'published').length}
              </div>
            </div>
          </div>
          {forecastRuns.length > 0 ? (
            <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
              {forecastRuns.map((run) => {
                const metadata = asRecord(run.model_metadata);
                const sourceHealth = asRecord(metadata?.source_health) as SourceHealthSummary | null;
                const decisionProvenance = asRecord(metadata?.decision_provenance) as DecisionProvenanceSummary | null;
                const compatibilityWriteStatus = typeof metadata?.compatibility_write_status === 'string'
                  ? metadata.compatibility_write_status
                  : null;
                const treeShapStatus = typeof metadata?.tree_shap_status === 'string'
                  ? metadata.tree_shap_status
                  : 'unknown';
                const hourStats = forecastHourStats.get(run.id);
                const timeline = publicationEventsByRun.get(run.id) ?? [];
                const timelineStages = timeline.slice(-4).map((event) => event.stage);
                const manifestReady = Boolean(run.manifest_storage_ref);
                const compatibilityState = run.compatibility_forecast_grid_id
                  ? 'attached'
                  : compatibilityWriteStatus === 'failed'
                    ? 'failed'
                    : 'optional';

                return (
                  <div key={run.id} className="rounded-lg border border-border/60 bg-black/10 px-2 py-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[11px] font-mono text-foreground truncate">
                          {run.region_name} • {run.forecast_date}
                        </div>
                        <div className="text-[10px] text-muted-foreground truncate">
                          {run.id} • {run.published_at ? new Date(run.published_at).toLocaleString() : new Date(run.created_at).toLocaleString()}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-1 shrink-0">
                        {run.active && (
                          <Badge className="bg-emerald-500/15 text-emerald-400 border-0 text-[9px] rounded-full">active</Badge>
                        )}
                        <Badge className={`border-0 text-[9px] rounded-full ${publicationStatusColor(run.status)}`}>{run.status}</Badge>
                        <Badge className={`border-0 text-[9px] rounded-full ${publicationStatusColor(run.publication_status)}`}>{run.publication_status}</Badge>
                      </div>
                    </div>
                    <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
                      <div className="text-muted-foreground">Run ID</div>
                      <div className="font-mono text-right text-foreground break-all">{run.id}</div>
                      <div className="text-muted-foreground">Manifest</div>
                      <div className="font-mono text-right text-foreground">{manifestReady ? 'present' : 'missing'}</div>
                      <div className="text-muted-foreground">Hour artifacts</div>
                      <div className="font-mono text-right text-foreground">
                        {hourStats ? `${hourStats.hourCount} / ${hourStats.maxHour + 1}` : '0'}
                      </div>
                      <div className="text-muted-foreground">Ready / stale cells</div>
                      <div className="font-mono text-right text-foreground">
                        {hourStats ? `${hourStats.readyCells} / ${hourStats.staleCells}` : '0 / 0'}
                      </div>
                      <div className="text-muted-foreground">Legacy grid link</div>
                      <div className={`font-mono text-right ${compatibilityState === 'failed' ? 'text-red-400' : 'text-foreground'}`}>
                        {compatibilityState}
                      </div>
                      <div className="text-muted-foreground">Explainability</div>
                      <div className="font-mono text-right text-foreground">{treeShapStatus}</div>
                      <div className="text-muted-foreground">Source health</div>
                      <div className="font-mono text-right text-foreground">{sourceHealth?.support_status || 'unknown'}</div>
                      <div className="text-muted-foreground">Decision path</div>
                      <div className="font-mono text-right text-foreground">{decisionProvenance?.dominant_mapping || 'n/a'}</div>
                    </div>
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      Stages: {timelineStages.length > 0 ? timelineStages.join(' -> ') : 'no publication events yet'}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">No staged forecast runs visible yet</div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Source Health</CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
          <div className="text-muted-foreground">Support status</div>
          <div className="font-mono text-right text-foreground">{latestSourceHealth?.support_status || 'n/a'}</div>
          <div className="text-muted-foreground">Completeness</div>
          <div className="font-mono text-right text-foreground">{formatPercent(latestSourceHealth?.overall_completeness)}</div>
          <div className="text-muted-foreground">Weather freshness</div>
          <div className="font-mono text-right text-foreground">
            {typeof latestSourceHealth?.weather_freshness_hours === 'number'
              ? `${latestSourceHealth.weather_freshness_hours.toFixed(0)}h`
              : 'n/a'}
          </div>
          <div className="text-muted-foreground">SAR coverage mode</div>
          <div className="font-mono text-right text-foreground">{latestSourceHealth?.sar_coverage_mode || 'n/a'}</div>
          <div className="text-muted-foreground">Snowpack proxy</div>
          <div className="font-mono text-right text-foreground">
            {latestSourceHealth?.snowpack_proxy_available === true ? 'available' : latestSourceHealth ? 'missing' : 'n/a'}
          </div>
          <div className="text-muted-foreground">Missing inputs</div>
          <div className="font-mono text-right text-foreground">
            {latestSourceHealth?.missing_features?.length ? latestSourceHealth.missing_features.join(', ') : 'none'}
          </div>
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Decision Provenance</CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
          <div className="text-muted-foreground">Threshold profile</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.threshold_profile || 'n/a'}</div>
          <div className="text-muted-foreground">Profile origin</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.threshold_profile_origin || 'n/a'}</div>
          <div className="text-muted-foreground">Dominant mapping</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.dominant_mapping || 'n/a'}</div>
          <div className="text-muted-foreground">Frequency policy</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.frequency_threshold_profile || 'n/a'}</div>
          <div className="text-muted-foreground">Aggregation policy</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.aggregation_policy || 'n/a'}</div>
          <div className="text-muted-foreground">Calibration method</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.calibration_method || 'n/a'}</div>
          <div className="text-muted-foreground">Selected features</div>
          <div className="font-mono text-right text-foreground">{latestDecisionProvenance?.selected_feature_count ?? 'n/a'}</div>
        </CardContent>
      </Card>

      {/* Forecast Analytics */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <TrendingUp className="h-3 w-3" />
            Forecast Analytics
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5">
          <div className="flex items-baseline gap-1 mb-1">
            <span className="text-base font-mono font-bold text-foreground">{analytics.total}</span>
            <span className="text-xs text-muted-foreground">total runs</span>
          </div>
          {analytics.regions.length > 0 && (
            <div className="space-y-0.5 max-h-20 overflow-y-auto pr-1">
              {analytics.regions.map(r => (
                <div key={r.region_name} className="flex items-center justify-between gap-2 text-[11px] py-1 border-b border-border/40 last:border-0">
                  <span className="text-muted-foreground truncate">{r.region_name}</span>
                  <span className="font-mono text-foreground">{r.count}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <BrainCircuit className="h-3 w-3" />
            Optimization Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5 space-y-1">
          <div className="text-[10px] text-muted-foreground">Version</div>
          <div className="font-mono text-sm text-foreground">{modelStatus?.optimization_version || optimizationSummary?.optimization_version || 'n/a'}</div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
            <div className="text-muted-foreground">Selected features</div>
            <div className="font-mono text-right text-foreground">{optimizationSummary?.selected_features?.length ?? 0}</div>
            <div className="text-muted-foreground">ABC:</div>
            <div className={`flex items-center justify-end gap-1 font-mono text-right ${abcEnabled === true ? 'text-emerald-400' : 'text-muted-foreground'}`}>
              {abcEnabled === true ? <Check className="h-3 w-3 shrink-0" /> : <Minus className="h-3 w-3 shrink-0" />}
              <span>{abcEnabled === true ? 'enabled' : abcEnabled === false ? 'disabled' : '—'}</span>
            </div>
            <div className="text-muted-foreground">Balance strategy</div>
            <div className="font-mono text-right text-foreground">{String(optimizationSummary?.class_balance_report?.strategy || 'n/a')}</div>
          </div>
          <div className="text-[10px] text-muted-foreground">
            LSTM/PINN refs: TRAIN_LSTM_HEAD • USE_LSTM_HEAD • LSTM_BLEND_WEIGHT • PINN_LAMBDA
          </div>
          <div className="text-[10px] text-muted-foreground">
            Next optimization: {modelStatus?.next_optimization_run ? new Date(modelStatus.next_optimization_run).toLocaleString() : 'not scheduled'}
          </div>
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <CloudSnow className="h-3 w-3" />
            Snowpack Proxy Metrics
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
          <div className="text-muted-foreground">RAM hardness</div>
          <div className="font-mono text-right text-foreground">{snowpackMetrics?.ram_hardness?.toFixed(3) ?? 'n/a'}</div>
          <div className="text-muted-foreground">Shear strength</div>
          <div className="font-mono text-right text-foreground">{snowpackMetrics?.shear_strength?.toFixed(3) ?? 'n/a'}</div>
          <div className="text-muted-foreground">Settlement</div>
          <div className="font-mono text-right text-foreground">{snowpackMetrics?.settlement_rate?.toFixed(3) ?? 'n/a'}</div>
          <div className="text-muted-foreground">Confidence</div>
          <div className="font-mono text-right text-foreground">{snowpackMetrics?.confidence?.toFixed(2) ?? 'n/a'}</div>
          <div className="text-muted-foreground">Source</div>
          <div className="font-mono text-right text-foreground">{snowpackMetrics?.source || 'n/a'}</div>
          <div className="col-span-2 text-muted-foreground pt-1">
            Proxy-based seasonal-memory estimates only; not direct field measurements or full SNOWPACK-class thermodynamics.
          </div>
        </CardContent>
      </Card>

      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <Satellite className="h-3 w-3" />
            Satellite Detection Stats
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
          <div className="text-muted-foreground">Scenes found</div>
          <div className="font-mono text-right text-foreground">{satelliteStats?.scenes_found ?? 0}</div>
          <div className="text-muted-foreground">Detections</div>
          <div className="font-mono text-right text-foreground">{satelliteStats?.detections_inserted ?? 0}</div>
          <div className="text-muted-foreground">Mode</div>
          <div className="font-mono text-right text-foreground">{satelliteStats?.mode || modelStatus?.capabilities?.mode || 'edge_fallback'}</div>
          <div className="text-muted-foreground">Fallback used</div>
          <div className="font-mono text-right text-foreground">
            {satelliteStats?.fallback_used ? (
              <Badge className="bg-amber-500/15 text-amber-300 border-0 font-mono text-[9px] rounded-full px-1.5 py-0.5">yes</Badge>
            ) : (
              'no'
            )}
          </div>
          <div className="text-muted-foreground">Last refresh</div>
          <div className="font-mono text-right text-foreground">{satelliteStats?.last_refresh_at ? new Date(satelliteStats.last_refresh_at).toLocaleString() : 'never'}</div>
        </CardContent>
      </Card>

      {/* Evaluation + Outcomes */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <BarChart3 className="h-3 w-3" />
            Evaluation Runs
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1 space-y-1.25">
          <div className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Forecast Outcomes</div>
          <div className="flex items-baseline gap-1">
            <span className="text-base font-mono font-bold text-foreground">{forecastOutcomes.length}</span>
            <span className="text-xs text-muted-foreground">recent labels</span>
          </div>
          {forecastOutcomes.length > 0 ? (
            <div className="space-y-1 max-h-24 overflow-y-auto pr-1">
              {forecastOutcomes.map((outcome) => (
                <div key={outcome.id} className="flex items-center justify-between text-[10px] gap-2 border-b border-border/50 last:border-0 pb-0.5">
                  <div className="min-w-0">
                    <div className="font-mono text-muted-foreground truncate">
                      h{outcome.forecast_hour} • r{outcome.cell_row} c{outcome.cell_col}
                    </div>
                    <div className="text-muted-foreground truncate">
                      {outcome.hazard_type} • {outcome.severity_label || 'none'}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Badge className={outcome.event_observed ? 'bg-green-500/20 text-green-400 border-0' : 'bg-muted text-muted-foreground border-0'}>
                      {outcome.event_observed ? 'OBS' : 'NO EVT'}
                    </Badge>
                    <span className="font-mono text-foreground">{outcome.label_confidence.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">No labeled outcomes yet</div>
          )}
          <div className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground pt-0.5">Latest Evaluation</div>
          {evaluationRuns.length > 0 ? (
            <div className="space-y-1">
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
                <div className="text-muted-foreground">Prec @ risk4</div>
                <div className="font-mono text-foreground text-right">
                  {evaluationRuns[0].overall_precision_risk4?.toFixed(2) ?? 'n/a'}
                </div>
                <div className="text-muted-foreground">Prec @ risk3</div>
                <div className="font-mono text-foreground text-right">
                  {evaluationRuns[0].overall_precision_risk3?.toFixed(2) ?? 'n/a'}
                </div>
                <div className="text-muted-foreground">Recall</div>
                <div className="font-mono text-foreground text-right">
                  {evaluationRuns[0].overall_recall?.toFixed(2) ?? 'n/a'}
                </div>
                <div className="text-muted-foreground">ECE</div>
                <div className="font-mono text-foreground text-right">
                  {evaluationRuns[0].overall_ece?.toFixed(3) ?? 'n/a'}
                </div>
                <div className="text-muted-foreground">False alarm</div>
                <div className="font-mono text-foreground text-right">
                  {evaluationRuns[0].overall_false_alarm_rate?.toFixed(2) ?? 'n/a'}
                </div>
                <div className="text-muted-foreground">Brier</div>
                <div className="font-mono text-foreground text-right">
                  {evaluationRuns[0].overall_brier_score?.toFixed(3) ?? 'n/a'}
                </div>
              </div>
              <div className="text-[10px] text-muted-foreground">
                Latest run: {evaluationRuns[0].run_name} • {evaluationRuns[0].model_version}
              </div>
              <div className="space-y-1 max-h-20 overflow-y-auto pr-1">
                {evaluationRuns.slice(1, 3).map((run) => (
                  <div key={run.id} className="flex items-center justify-between text-[10px] gap-2 py-1 border-b border-border/40 last:border-0">
                    <span className="text-muted-foreground truncate">{run.run_name} • {run.model_version}</span>
                    <Badge className={`border-0 ${statusColor(run.status)}`}>{run.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">No evaluation runs yet</div>
          )}
          <div className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground pt-0.5">Slice Metrics</div>
          {evaluationMetrics.length > 0 ? (
            <div className="space-y-1 max-h-28 overflow-y-auto">
              {evaluationMetrics.slice(0, 4).map((metric) => (
                <div key={metric.id} className="flex items-center justify-between gap-2 text-[10px] border-b border-border/50 last:border-0 pb-0.5">
                  <div className="min-w-0">
                    <div className="font-mono text-muted-foreground truncate">
                      {metric.slice_type}: {metric.slice_value}
                    </div>
                    <div className="text-muted-foreground truncate">
                      {metric.total_forecasts} forecasts • {metric.observed_events} observed
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-mono text-foreground">P3 {metric.precision_risk3?.toFixed(2) ?? 'n/a'}</span>
                    <span className="font-mono text-foreground">R3 {metric.recall_risk3?.toFixed(2) ?? 'n/a'}</span>
                    <span className="font-mono text-foreground">ECE {metric.ece?.toFixed(3) ?? 'n/a'}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">No slice metrics yet</div>
          )}
        </CardContent>
      </Card>

      {/* Field Reports */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <FileCheck className="h-3 w-3" />
            Recent Groundsource Events
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1 space-y-1 max-h-60 overflow-y-auto pr-1">
          {groundsourceEvents.length === 0 ? (
            <div className="text-xs text-muted-foreground">No recent governed field-report events</div>
          ) : (
            groundsourceEvents.map((event) => (
              <div key={event.id} className="rounded-lg border border-border/50 bg-black/10 px-2 py-1.5 text-[10px]">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-mono text-muted-foreground truncate">
                      {new Date(event.timestamp).toLocaleString()} • {extractLocationName(asRecord(event.features))}
                    </div>
                    <div className="line-clamp-2 text-muted-foreground">
                      {event.description || 'No description'}
                    </div>
                  </div>
                  <Badge className="bg-sky-500/15 text-sky-300 border-0 text-[9px] rounded-full shrink-0">
                    {event.source}
                  </Badge>
                </div>
                <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
                  <div className="text-muted-foreground">label_confidence</div>
                  <div className="font-mono text-right text-foreground">
                    {typeof event.label_confidence === 'number' ? event.label_confidence.toFixed(2) : 'n/a'}
                  </div>
                  <div className="text-muted-foreground">training_weight</div>
                  <div className="font-mono text-right text-foreground">
                    {typeof event.training_weight === 'number' ? event.training_weight.toFixed(3) : 'n/a'}
                  </div>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Field Reports */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
            <FileCheck className="h-3 w-3" />
            Field Reports
          </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1 space-y-1 max-h-56 overflow-y-auto pr-1">
          {fieldReports.length === 0 ? (
            <div className="text-xs text-muted-foreground">No recent field reports</div>
          ) : (
            fieldReports.map((report) => (
              <div key={report.id} className="flex items-start justify-between gap-2 text-[10px] border-b border-border/50 last:border-0 pb-0.5">
                <div className="min-w-0">
                  <div className="font-mono text-muted-foreground truncate">{new Date(report.created_at).toLocaleString()}</div>
                  <div className="text-muted-foreground line-clamp-2">{report.description || 'No description'}</div>
                  {(() => {
                    const linkedEvent = fieldReportEventsByReportId.get(report.id)
                      ?? (report.client_report_id ? fieldReportEventsByReportId.get(report.client_report_id) : undefined);
                    if (!linkedEvent) return null;
                    return (
                      <div className="mt-1 text-[9px] text-muted-foreground">
                        Event: {linkedEvent.verification_status || 'unverified'} • {linkedEvent.id}
                      </div>
                    );
                  })()}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <Badge className={`border-0 ${statusColor(report.review_status || 'pending')}`}>{report.review_status || 'pending'}</Badge>
                  <span className="text-[9px] text-muted-foreground font-mono">
                    {report.training_eligible ? 'TRAINING OK' : 'REVIEW ONLY'}
                  </span>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* System Config */}
      {systemConfig && (
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardContent className="p-2.5">
            <div className="text-xs text-muted-foreground uppercase tracking-[0.24em] mb-1.5">Gemini API Usage (Enrichment Only)</div>
            <div className="flex items-baseline gap-1">
              <span className="text-base font-mono font-bold text-foreground">{systemConfig.gemini_usage}</span>
              <span className="text-xs text-muted-foreground">/ {systemConfig.gemini_spend_cap} calls</span>
            </div>
            <div className="text-[10px] text-muted-foreground mt-1">Forecasts use Open-Meteo (free). Gemini only counts during daily enrichment.</div>
            <div className="mt-2 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all"
                style={{ width: `${Math.min(100, (systemConfig.gemini_usage / systemConfig.gemini_spend_cap) * 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Model Status */}
      {modelStatus && (
        <>
          <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
            <CardContent className="p-2.5">
              <div className="text-xs text-muted-foreground uppercase tracking-[0.24em] mb-1.5">Model Status</div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono text-sm text-foreground">{modelStatus.version}</span>
                <Badge className="bg-emerald-500/15 text-emerald-400 border-0 font-mono text-xs rounded-full">
                  PSS: {modelStatus.pss_reported?.toFixed(3) ?? '—'}
                </Badge>
              </div>
              <div className="text-[10px] text-muted-foreground">
                Capability summary: {capabilityMode}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Customer-serving scorer (active): {activeModelLabel} • Version: {activeModelVersion}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Dynamic scorer (candidate): {candidateModelLabel} • Version: {candidateModelVersion} • Gate: {candidateGate}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Current-state interpretation: operator evidence for gated candidate review; activation and authority standing require promotion proof.
              </div>
              <div className="text-[10px] text-muted-foreground">
                Promotion gate: {modelStatus.promotion_gate_passed ? 'pass' : 'hold'} • PSS gate: {modelStatus.pss_gate_passed ? 'pass' : 'hold'}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Authoritative SAR: unavailable until an active held-out artifact exists
              </div>
              <div className="text-[10px] text-muted-foreground">
                Whitebox runout: exploratory until `runout_physics_smoke.json` passes
              </div>
              <div className="text-[10px] text-muted-foreground">
                Evidence volume: auto {evidenceSummary?.autonomous_positive_count ?? 0}/{evidenceSummary?.positive_count ?? 0} • manual {evidenceSummary?.manual_positive_count ?? 0} • promoted SAR {evidenceSummary?.promoted_sar_volume?.sar_unet_promoted_count ?? 0}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Latest benchmark: {latestBenchmarkSummary?.benchmark_kind || 'n/a'} • {latestBenchmarkSummary?.status || 'n/a'} • {formatSeconds(latestBenchmarkSummary?.total_seconds)}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Drift mode: {modelStatus.drift_mode_state || 'n/a'} • Stability class: {stabilitySummary?.classification || 'n/a'} • Seeds: {stabilitySummary?.seed_count ?? 'n/a'}
              </div>
              {modelStatus.feature_version && (
                <div className="text-[10px] text-muted-foreground">
                  Feature: {modelStatus.feature_version}
                </div>
              )}
              {modelStatus.calibration_profile_version && (
                <div className="text-[10px] text-muted-foreground">
                  Calibration: {modelStatus.calibration_profile_version}
                </div>
              )}
              {modelStatus.threshold_profile_version && (
                <div className="text-[10px] text-muted-foreground">
                  Thresholds: {modelStatus.threshold_profile_version}
                </div>
              )}
              {modelStatus.snowpack_model_version && (
                <div className="text-[10px] text-muted-foreground">
                  Snowpack: {modelStatus.snowpack_model_version}
                </div>
              )}
              <div className="text-[10px] text-muted-foreground">
                Confidence proxy: F1 {modelStatus.f1_score?.toFixed(3) ?? '—'} • Backend: {modelStatus.inference_backend || 'batch_async'}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Governance scope: internal lineage/evaluation only; public claims remain gated until release artifacts pass.
              </div>
              <div className="text-[10px] text-muted-foreground">
                External interoperability: {String(latestGovernanceScope?.external_interoperability || 'not_implemented').replace(/_/g, ' ')}
              </div>
              <div className="text-[10px] text-muted-foreground">
                Operator/public split: admin observability stays richer than customer-facing products by design
              </div>
              {(!modelStatus.last_trained || modelStatus.version?.includes('-sim') || syntheticBootstrapSkipped || !optimizationSummary || optimizationSummary?.origin === 'hardcoded_fallback') && (
                <div className="mt-1.5 rounded-md bg-amber-500/10 border border-amber-500/30 px-2 py-1">
                  <span className="text-[10px] font-mono text-amber-300 uppercase tracking-wider">SYNTHETIC BOOTSTRAP</span>
                  <div className="text-[10px] text-amber-200/70 mt-0.5">
                    {syntheticBootstrapSkipped
                      ? 'Latest fine-tune was skipped, so the bootstrap model remains active.'
                      : 'Model was never trained. Run Model Optimization to replace with real weights.'}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
            <CardHeader className="p-2 pb-1">
              <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Model Stability</CardTitle>
            </CardHeader>
            <CardContent className="p-2 pt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px]">
              <div className="text-muted-foreground">Drift mode</div>
              <div className="font-mono text-right text-foreground">{modelStatus.drift_mode_state || 'n/a'}</div>
              <div className="text-muted-foreground">Stability class</div>
              <div className="font-mono text-right text-foreground">{stabilitySummary?.classification || 'n/a'}</div>
              <div className="text-muted-foreground">Seed count</div>
              <div className="font-mono text-right text-foreground">{stabilitySummary?.seed_count ?? 'n/a'}</div>
              <div className="text-muted-foreground">PSS std</div>
              <div className="font-mono text-right text-foreground">
                {typeof stabilitySummary?.pss_std === 'number' ? stabilitySummary.pss_std.toFixed(3) : 'n/a'}
              </div>
              <div className="text-muted-foreground">Threshold drift</div>
              <div className="font-mono text-right text-foreground">
                {typeof stabilitySummary?.threshold_drift === 'number' ? stabilitySummary.threshold_drift.toFixed(3) : 'n/a'}
              </div>
              <div className="text-muted-foreground">Feature overlap</div>
              <div className="font-mono text-right text-foreground">{formatPercent(stabilitySummary?.selected_feature_overlap_mean)}</div>
              <div className="text-muted-foreground">Latest benchmark</div>
              <div className="font-mono text-right text-foreground">
                {latestBenchmarkSummary?.benchmark_kind || 'n/a'} • {formatSeconds(latestBenchmarkSummary?.total_seconds)}
              </div>
              <div className="text-muted-foreground">Benchmark status</div>
              <div className="font-mono text-right text-foreground">{latestBenchmarkSummary?.status || 'n/a'}</div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Job History */}
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader className="p-2 pb-1">
          <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Recent Jobs</CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-1">
          {jobs.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">No jobs yet</div>
          ) : (
            <div className="space-y-0.5 max-h-36 overflow-y-auto pr-1">
              {jobs.map((job) => (
                <div key={job.id} className="flex items-center justify-between text-xs py-1 border-b border-border/50 last:border-0 gap-2">
                  <span className="font-mono text-muted-foreground">{job.type.replace(/_/g, ' ')}</span>
                  <Badge variant="outline" className={`text-[10px] border-0 ${statusColor(job.status)}`}>
                    {job.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
