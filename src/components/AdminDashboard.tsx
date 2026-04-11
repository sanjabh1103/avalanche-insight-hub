import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Zap, Satellite, BrainCircuit, Database, TrendingUp } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';

type JobType = 'daily_enrichment' | 'sentinel_refresh' | 'fine_tune' | 'static_precompute';

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

const JOB_BUTTONS: { type: JobType; label: string; icon: React.ReactNode }[] = [
  { type: 'daily_enrichment', label: 'Run Enrichment', icon: <Zap className="h-4 w-4" /> },
  { type: 'sentinel_refresh', label: 'Refresh Sentinel-1', icon: <Satellite className="h-4 w-4" /> },
  { type: 'fine_tune', label: 'Fine-Tune Model', icon: <BrainCircuit className="h-4 w-4" /> },
  { type: 'static_precompute', label: 'Static Pre-Compute', icon: <Database className="h-4 w-4" /> },
];

export default function AdminDashboard() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [systemConfig, setSystemConfig] = useState<{ gemini_usage: number; gemini_spend_cap: number } | null>(null);
  const [modelStatus, setModelStatus] = useState<{ version: string; f1_score: number } | null>(null);
  const [analytics, setAnalytics] = useState<{ total: number; regions: AnalyticsRow[] }>({ total: 0, regions: [] });

  const loadData = useCallback(async () => {
    const [jobsRes, configRes, modelRes, analyticsRes] = await Promise.all([
      supabase.from('compute_jobs').select('*').order('created_at', { ascending: false }).limit(10),
      supabase.from('system_config').select('*').limit(1).single(),
      supabase.from('model_status').select('*').limit(1).single(),
      supabase.from('forecast_analytics').select('*').order('created_at', { ascending: false }).limit(100),
    ]);
    if (jobsRes.data) setJobs(jobsRes.data as unknown as JobRow[]);
    if (configRes.data) setSystemConfig(configRes.data as unknown as { gemini_usage: number; gemini_spend_cap: number });
    if (modelRes.data) setModelStatus(modelRes.data as unknown as { version: string; f1_score: number });
    if (analyticsRes.data) {
      const rows = analyticsRes.data as unknown as { region_name: string }[];
      const regionMap = new Map<string, number>();
      rows.forEach(r => regionMap.set(r.region_name || 'Unknown', (regionMap.get(r.region_name || 'Unknown') || 0) + 1));
      const regions = Array.from(regionMap.entries()).map(([region_name, count]) => ({ region_name, count })).sort((a, b) => b.count - a.count);
      setAnalytics({ total: rows.length, regions: regions.slice(0, 5) });
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useRealtimeSubscription('compute_jobs', () => { loadData(); });

  const triggerJob = async (type: JobType) => {
    setRunning(type);
    try {
      const { data, error } = await supabase.functions.invoke('trigger-job', {
        body: { type },
      });
      if (error) throw error;
      toast.success(`${type.replace(/_/g, ' ')} triggered successfully`);
      loadData();
    } catch (err: any) {
      toast.error(err.message || 'Job trigger failed');
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
        <CardContent className="p-3 pt-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {JOB_BUTTONS.map((btn) => (
            <Button
              key={btn.type}
              variant="outline"
              size="sm"
              className="text-xs h-10 justify-start gap-2"
              disabled={running !== null}
              onClick={() => triggerJob(btn.type)}
            >
              {running === btn.type ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : btn.icon}
              {btn.label}
            </Button>
          ))}
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
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm text-foreground">{modelStatus.version}</span>
              <Badge className="bg-green-500/20 text-green-400 border-0 font-mono text-xs">
                F1: {modelStatus.f1_score.toFixed(3)}
              </Badge>
            </div>
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
