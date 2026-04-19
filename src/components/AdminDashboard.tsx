import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Zap, Satellite, BrainCircuit, Database, TrendingUp, CloudSnow, Activity, Tag, BarChart3, FileCheck, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { supabase, SUPABASE_ANON_KEY } from '@/integrations/supabase/client';
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
  selected_features?: string[];
  class_balance_report?: Record<string, unknown>;
  abc_enabled?: boolean;
  runtime_mode?: string;
}

interface SatelliteDetectionStats {
  last_refresh_at?: string;
  scenes_found?: number;
  detections_inserted?: number;
  mode?: string;
  fallback_used?: boolean;
}

interface JobRow {
  id: string;
  type: string;
  status: string;
  created_at: string;
  error: string | null;
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
  review_status: string;
  training_eligible: boolean;
}

interface ModelStatusRow {
  version: string;
  f1_score: number;
  feature_version?: string;
  calibration_profile_version?: string;
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
  const activeJobs = jobs.filter((job) => job.status === 'running').length;
  
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
      ] = await Promise.all([
        supabase.from('compute_jobs').select('*').order('created_at', { ascending: false }).limit(10),
        supabase.from('system_config').select('*').limit(1).single(),
        supabase.from('model_status').select('*').limit(1).single(),
        supabase.from('forecast_analytics').select('*').order('created_at', { ascending: false }).limit(100),
        supabase.from('evaluation_runs').select('*').order('created_at', { ascending: false }).limit(5),
        supabase.from('evaluation_metrics').select('*').order('created_at', { ascending: false }).limit(10),
        supabase.from('forecast_outcomes').select('*').order('created_at', { ascending: false }).limit(5),
        supabase.from('field_reports').select('id, created_at, description, review_status, training_eligible').order('created_at', { ascending: false }).limit(5),
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
        headers: {
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        },
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
      toast.success(successMessages[type] || `${type.replace(/_/g, ' ')} completed successfully`);
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
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const capabilityMode = modelStatus?.capability_summary || modelStatus?.capabilities?.summary || 'Edge-only fallback';
  const optimizationSummary = modelStatus?.optimization_summary;
  const snowpackMetrics = modelStatus?.snowpack_metrics;
  const satelliteStats = modelStatus?.satellite_detection_stats;

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
              <div className="text-[10px] text-muted-foreground mt-0.5">Dual-mode runtime capability and fallback state</div>
            </div>
            <Badge className="bg-sky-500/15 text-sky-300 border-0 font-mono text-[10px] rounded-full">
              {modelStatus?.inference_backend === 'gpu' ? 'GPU' : 'EDGE'}
            </Badge>
          </div>
          <div className="text-sm font-mono text-foreground">{capabilityMode}</div>
          <div className="text-[10px] text-muted-foreground">
            SAR: {modelStatus?.capabilities?.sar_enabled ? 'on' : 'fallback'} • GPU: {modelStatus?.capabilities?.gpu_enabled ? 'on' : 'fallback'}
          </div>
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
            <div className="text-muted-foreground">ABC enabled</div>
            <div className="font-mono text-right text-foreground">{optimizationSummary?.abc_enabled ? 'yes' : 'no'}</div>
            <div className="text-muted-foreground">Balance strategy</div>
            <div className="font-mono text-right text-foreground">{String(optimizationSummary?.class_balance_report?.strategy || 'n/a')}</div>
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
            Snowpack Metrics
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
          <div className="font-mono text-right text-foreground">{satelliteStats?.fallback_used ? 'yes' : 'no'}</div>
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
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardContent className="p-2.5">
            <div className="text-xs text-muted-foreground uppercase tracking-[0.24em] mb-1.5">Model Status</div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-mono text-sm text-foreground">{modelStatus.version}</span>
              <Badge className="bg-emerald-500/15 text-emerald-400 border-0 font-mono text-xs rounded-full">
                F1: {modelStatus.f1_score.toFixed(3)}
              </Badge>
            </div>
            <div className="text-[10px] text-muted-foreground">
              Mode: {capabilityMode}
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
          </CardContent>
        </Card>
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
