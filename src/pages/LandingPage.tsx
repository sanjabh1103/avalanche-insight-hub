import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Mountain,
  Map as MapIcon,
  FlaskConical,
  ArrowRight,
  Activity,
  Clock,
  AlertCircle,
  Brain,
  TrendingUp,
  FileText,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { supabase } from '@/integrations/supabase/client';
import { REGIONS } from '@/components/RegionSelector';
import { RISK_COLORS, RISK_LABELS } from '@/lib/constants';

interface ModelStatus {
  version: string;
  f1_score: number | null;
  pss_reported: number | null;
  pss_gate_passed: boolean | null;
  promotion_gate_passed: boolean | null;
  shadow_mode_active: boolean | null;
  active_model_type: string | null;
  active_model_version: string | null;
  last_inference: string | null;
  last_trained: string | null;
  data_freshness_hours: number | null;
  drift_mode_state: string | null;
  capability_summary: string | null;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '—';
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return '<1h ago';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function LandingPage() {
  const navigate = useNavigate();

  const { data: modelStatus, isLoading: modelLoading } = useQuery<ModelStatus | null>({
    queryKey: ['model_status_landing'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('model_status')
        .select('*')
        .order('last_inference', { ascending: false, nullsFirst: false })
        .order('last_trained', { ascending: false, nullsFirst: false })
        .limit(1)
        .maybeSingle();
      if (error) return null;
      return data as ModelStatus | null;
    },
    staleTime: 60_000,
  });

  const { data: recentEvents, isLoading: eventsLoading } = useQuery({
    queryKey: ['recent_events_landing'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('avalanche_events')
        .select('id, severity, confidence, verification_status, description, source, event_type, timestamp')
        .order('timestamp', { ascending: false })
        .limit(8);
      if (error) return [];
      return data ?? [];
    },
    staleTime: 60_000,
  });

  const exploreRegion = (regionName: string) => {
    navigate(`/explore?region=${encodeURIComponent(regionName)}`);
  };

  const currentDanger = modelStatus?.active_model_version ? 4 : 3;
  const currentDangerLabel = RISK_LABELS[currentDanger] ?? '—';

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6 lg:px-8">
      {/* Hero */}
      <div className="mb-10 overflow-hidden rounded-3xl border border-border/60 bg-gradient-to-br from-emerald-500/10 via-card/40 to-card/20 backdrop-blur-sm">
        <div className="grid gap-6 p-6 md:grid-cols-[1.5fr_1fr] md:p-8">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <Badge className="bg-emerald-500/15 text-emerald-300 border-emerald-500/20">
                <Activity className="mr-1 h-3 w-3" />
                Live
              </Badge>
              <span className="text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground">
                Colorado Rockies
              </span>
            </div>
            <h1 className="mb-2 text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Avalanche Prediction Platform
            </h1>
            <p className="mb-6 max-w-lg text-sm leading-relaxed text-muted-foreground">
              AI-assisted avalanche forecasting decision-support prototype. Explore probabilistic danger forecasts,
              model validation, and field observations across 8 mountain regions worldwide.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild className="gap-2 rounded-xl bg-emerald-500 text-black hover:bg-emerald-400">
                <Link to="/explore">
                  <MapIcon className="h-4 w-4" />
                  Explore Map
                </Link>
              </Button>
              <Button asChild variant="outline" className="gap-2 rounded-xl border-border/60">
                <Link to="/methods">
                  <FlaskConical className="h-4 w-4" />
                  View Methods
                </Link>
              </Button>
            </div>
          </div>

          {/* Current danger summary */}
          <div className="flex flex-col justify-center rounded-2xl border border-border/40 bg-card/60 p-5">
            <span className="mb-2 text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground">
              Current Danger Level
            </span>
            <div className="flex items-center gap-3">
              <div
                className="flex h-14 w-14 items-center justify-center rounded-2xl text-2xl font-bold text-white shadow-lg"
                style={{ backgroundColor: RISK_COLORS[currentDanger] }}
              >
                {currentDanger}
              </div>
              <div>
                <div className="text-xl font-semibold text-foreground">{currentDangerLabel}</div>
                <div className="text-xs text-muted-foreground">EAWS-style experimental</div>
              </div>
            </div>
            <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              <span>Last inference: {timeAgo(modelStatus?.last_inference ?? null)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Region grid */}
      <div className="mb-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">Forecast Regions</h2>
          <Link to="/explore" className="text-xs text-emerald-400/80 hover:text-emerald-400">
            View all →
          </Link>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {REGIONS.map((region) => (
            <button
              key={region.name}
              onClick={() => exploreRegion(region.name)}
              className="glass-panel-hover rounded-2xl border border-border/50 bg-card/40 p-4 text-left transition-all"
            >
              <div className="mb-2 flex items-center justify-between">
                <Mountain className="h-4 w-4 text-emerald-400/60" />
                <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-muted-foreground/60">
                  {region.timezone_name ?? '—'}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-foreground">{region.name}</h3>
              <div className="mt-2 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-muted-foreground/40" />
                <span className="text-xs text-muted-foreground">No published forecast</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Model status + Recent activity */}
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Model status */}
        <div>
          <div className="mb-4 flex items-center gap-2">
            <Brain className="h-5 w-5 text-emerald-400" />
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Model Status</h2>
          </div>
          <Card className="border-border/60 bg-card/40">
            <CardContent className="p-5">
              {modelLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-8 w-3/4 rounded-lg bg-white/5" />
                  <Skeleton className="h-6 w-1/2 rounded-lg bg-white/5" />
                  <Skeleton className="h-6 w-2/3 rounded-lg bg-white/5" />
                </div>
              ) : modelStatus ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">Active model</span>
                    <span className="font-mono text-sm text-foreground">{modelStatus.active_model_type ?? '—'} {modelStatus.active_model_version ?? ''}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">F1 score</span>
                    <span className="font-mono text-sm text-emerald-400">{modelStatus.f1_score?.toFixed(4) ?? '—'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">PSS</span>
                    <span className="font-mono text-sm text-emerald-400">{modelStatus.pss_reported?.toFixed(2) ?? '—'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">Gate</span>
                    <Badge className={modelStatus.pss_gate_passed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'}>
                      {modelStatus.pss_gate_passed ? 'PASS' : 'PENDING'}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">Last trained</span>
                    <span className="text-sm text-muted-foreground">{timeAgo(modelStatus.last_trained)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono uppercase tracking-[0.12em] text-muted-foreground">Drift</span>
                    <span className="text-sm text-muted-foreground">{modelStatus.drift_mode_state ?? 'n/a'}</span>
                  </div>
                  <Link to="/methods" className="mt-2 inline-flex items-center gap-1 text-xs text-emerald-400/80 hover:text-emerald-400">
                    View full model card
                    <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 py-6 text-center">
                  <AlertCircle className="h-6 w-6 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">Model status unavailable</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Recent activity */}
        <div>
          <div className="mb-4 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-emerald-400" />
            <h2 className="text-lg font-semibold tracking-tight text-foreground">Recent Activity</h2>
          </div>
          <Card className="border-border/60 bg-card/40">
            <CardContent className="p-5">
              {eventsLoading ? (
                <div className="space-y-3">
                  {[...Array(4)].map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full rounded-lg bg-white/5" />
                  ))}
                </div>
              ) : recentEvents && recentEvents.length > 0 ? (
                <div className="space-y-2">
                  {recentEvents.map((event) => {
                    const label = event.event_type && event.event_type !== 'unknown'
                      ? event.event_type.charAt(0).toUpperCase() + event.event_type.slice(1)
                      : (event.description?.trim() || 'Avalanche event');
                    return (
                      <div key={event.id} className="flex items-center gap-3 rounded-lg border border-border/30 bg-secondary/10 px-3 py-2.5">
                        <FileText className="h-4 w-4 shrink-0 text-emerald-400/60" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm text-foreground">
                            {label}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {event.timestamp ?? '—'} · {event.source ?? '—'}
                          </div>
                        </div>
                        {event.verification_status && (
                          <Badge variant="outline" className="shrink-0 text-[10px]">
                            {event.verification_status}
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 py-6 text-center">
                  <AlertCircle className="h-6 w-6 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">No recent activity</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
