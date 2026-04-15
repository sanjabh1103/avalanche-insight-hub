import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Zap, Satellite, BrainCircuit, Database, TrendingUp, CloudSnow, Activity, Tag, BarChart3, FileCheck, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';

type JobType = 'daily_enrichment' | 'sentinel_refresh' | 'fine_tune' | 'static_precompute' | 'snow_cover_refresh' | 'recent_activity_refresh' | 'label_forecast_outcomes' | 'run_evaluation' | 'retrain_avalanche_model' | 'field_report_enrichment';

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
  { type: 'static_precompute', label: 'Static Pre-Compute', icon: <Database className="h-4 w-4" />, description: 'Region pre-computation' },
];

export default function AdminDashboard() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [systemConfig, setSystemConfig] = useState<{ gemini_usage: number; gemini_spend_cap: number } | null>(null);
  const [modelStatus, setModelStatus] = useState<{ version: string; f1_score: number; feature_version?: string; calibration_profile_version?: string; threshold_profile_version?: string } | null>(null);
  const [analytics, setAnalytics] = useState<{ total: number; regions: AnalyticsRow[] }>({ total: 0, regions: [] });
  const [evaluationRuns, setEvaluationRuns] = useState<EvaluationRunRow[]>([]);
  const [evaluationMetrics, setEvaluationMetrics] = useState<EvaluationMetricRow[]>([]);
  const [forecastOutcomes, setForecastOutcomes] = useState<ForecastOutcomeRow[]>([]);
  const [fieldReports, setFieldReports] = useState<FieldReportRow[]>([]);
  const activeJobs = jobs.filter((job) => job.status === 'running').length;

  const loadData = useCallback(async () => {
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
    if (modelRes.data) setModelStatus(modelRes.data as unknown as { version: string; f1_score: number; feature_version?: string; calibration_profile_version?: string; threshold_profile_version?: string });
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
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useRealtimeSubscription('compute_jobs', () => { loadData(); });
  useRealtimeSubscription('evaluation_runs', () => { loadData(); });
  useRealtimeSubscription('evaluation_metrics', () => { loadData(); });
  useRealtimeSubscription('forecast_outcomes', () => { loadData(); });
  useRealtimeSubscription('field_reports', () => { loadData(); });

  const triggerJob = async (type: JobType) => {
    setRunning(type);
    try {
      // Build job payload based on type
      const payload: Record<string, unknown> = { type, hazard_type: 'avalanche' };

      // Add bbox for jobs that need spatial context
      if (['sentinel_refresh', 'snow_cover_refresh'].includes(type)) {
        payload.bbox = [38.5, -107.5, 40.5, -105.5]; // Colorado Rockies, [latMin, lngMin, latMax, lngMax]
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

  return (
    <div className="space-y-3 p-3">
      {/* System Controls */}
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">System Controls</CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {JOB_BUTTONS.map((btn) => (
              <Button
                key={btn.type}
                variant="outline"
                size="sm"
                className="text-xs h-auto py-2 justify-start gap-2"
                disabled={running !== null}
                onClick={() => triggerJob(btn.type)}
                title={btn.description}
              >
                {running === btn.type ? <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" /> : <span className="shrink-0">{btn.icon}</span>}
                <span className="truncate">{btn.label}</span>
              </Button>
            ))}
          </div>
          <div className="text-[10px] text-muted-foreground mt-2">
            New: Snow Cover, Activity, Labeling, Evaluation for avalanche accuracy roadmap
          </div>
        </CardContent>
      </Card>

      <Card className="border-0 bg-secondary/50">
        <CardContent className="p-3 flex items-center justify-between">
          <div>
            <div className="text-xs text-muted-foreground uppercase tracking-wider">Active Jobs</div>
            <div className="text-[10px] text-muted-foreground mt-1">Realtime count of running compute jobs</div>
          </div>
          <Badge className="bg-amber-500/20 text-amber-300 border-0 font-mono text-xs">
            {activeJobs}
          </Badge>
        </CardContent>
      </Card>

      {/* Forecast Analytics */}
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <TrendingUp className="h-3 w-3" />
            Forecast Analytics
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1">
          <div className="flex items-baseline gap-1 mb-2">
            <span className="text-lg font-mono font-bold text-foreground">{analytics.total}</span>
            <span className="text-xs text-muted-foreground">total runs</span>
          </div>
          {analytics.regions.length > 0 && (
            <div className="space-y-1">
              {analytics.regions.map(r => (
                <div key={r.region_name} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground truncate">{r.region_name}</span>
                  <span className="font-mono text-foreground">{r.count}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Evaluation + Outcomes */}
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <BarChart3 className="h-3 w-3" />
            Evaluation Runs
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-2">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Forecast Outcomes</div>
          <div className="flex items-baseline gap-1">
            <span className="text-lg font-mono font-bold text-foreground">{forecastOutcomes.length}</span>
            <span className="text-xs text-muted-foreground">recent labels</span>
          </div>
          {forecastOutcomes.length > 0 ? (
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {forecastOutcomes.map((outcome) => (
                <div key={outcome.id} className="flex items-center justify-between text-[10px] gap-2 border-b border-border/50 last:border-0 pb-1">
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
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground pt-1">Latest Evaluation</div>
          {evaluationRuns.length > 0 ? (
            <div className="space-y-1.5">
              <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[10px]">
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
              <div className="space-y-1.5">
                {evaluationRuns.slice(1, 3).map((run) => (
                  <div key={run.id} className="flex items-center justify-between text-[10px]">
                    <span className="text-muted-foreground truncate">{run.run_name} • {run.model_version}</span>
                    <Badge className={`border-0 ${statusColor(run.status)}`}>{run.status}</Badge>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">No evaluation runs yet</div>
          )}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground pt-1">Slice Metrics</div>
          {evaluationMetrics.length > 0 ? (
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {evaluationMetrics.slice(0, 4).map((metric) => (
                <div key={metric.id} className="flex items-center justify-between gap-2 text-[10px] border-b border-border/50 last:border-0 pb-1">
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
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <FileCheck className="h-3 w-3" />
            Field Reports
          </CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1 space-y-1.5">
          {fieldReports.length === 0 ? (
            <div className="text-xs text-muted-foreground">No recent field reports</div>
          ) : (
            fieldReports.map((report) => (
              <div key={report.id} className="flex items-start justify-between gap-2 text-[10px] border-b border-border/50 last:border-0 pb-1">
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
        <Card className="border-0 bg-secondary/50">
          <CardContent className="p-3">
            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Gemini API Usage (Enrichment Only)</div>
            <div className="flex items-baseline gap-1">
              <span className="text-lg font-mono font-bold text-foreground">{systemConfig.gemini_usage}</span>
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
        <Card className="border-0 bg-secondary/50">
          <CardContent className="p-3">
            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Model Status</div>
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-sm text-foreground">{modelStatus.version}</span>
              <Badge className="bg-green-500/20 text-green-400 border-0 font-mono text-xs">
                F1: {modelStatus.f1_score.toFixed(3)}
              </Badge>
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
          </CardContent>
        </Card>
      )}

      {/* Job History */}
      <Card className="border-0 bg-secondary/50">
        <CardHeader className="p-3 pb-1">
          <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Recent Jobs</CardTitle>
        </CardHeader>
        <CardContent className="p-3 pt-1">
          {jobs.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">No jobs yet</div>
          ) : (
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {jobs.map((job) => (
                <div key={job.id} className="flex items-center justify-between text-xs py-1.5 border-b border-border/50 last:border-0">
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
