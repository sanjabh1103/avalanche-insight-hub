import { useMemo } from 'react';
import { AlertTriangle, ShieldCheck, Activity, Gauge, TrendingDown, ClipboardList, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export interface VerificationDashboardData {
  coverage?: {
    total_cells?: number;
    cells_with_3plus_sources?: number;
    cells_with_baselines?: number;
    cells_with_anomaly_state?: number;
  };
  stale_cells?: {
    count?: number;
    top_stale?: Array<{ cell_id: string; max_freshness_hours: number }>;
  };
  disagreement?: {
    anomaly_count?: number;
    attribution_breakdown?: Record<string, number>;
  };
  source_health?: Array<{
    sensor: string;
    last_acquisition?: string;
    avg_latency_hours?: number;
    gap_count?: number;
  }>;
  model_drift?: {
    calibration_drift?: number;
    brier_trend?: number[];
  };
  review_backlog?: {
    pending_count?: number;
    oldest_pending_hours?: number;
    scientist_throughput?: number;
  };
}

interface ContinuousVerificationDashboardProps {
  data?: VerificationDashboardData;
  status?: 'available' | 'unavailable';
  unavailableReason?: string;
  truncatedTables?: string[];
}

function MetricCard({
  icon: Icon,
  title,
  value,
  subtitle,
  variant = 'default',
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  value: string | number;
  subtitle?: string;
  variant?: 'default' | 'warning' | 'danger' | 'success';
}) {
  const variantClass = {
    default: 'text-muted-foreground',
    warning: 'text-amber-400',
    danger: 'text-red-400',
    success: 'text-emerald-400',
  }[variant];

  return (
    <Card className="border-border/40">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Icon className="h-4 w-4" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${variantClass}`}>{value}</div>
        {subtitle && <div className="text-xs text-muted-foreground/60 mt-1">{subtitle}</div>}
      </CardContent>
    </Card>
  );
}

export default function ContinuousVerificationDashboard({ data, status = 'available', unavailableReason, truncatedTables }: ContinuousVerificationDashboardProps) {
  const coveragePct = useMemo(() => {
    if (!data?.coverage?.total_cells || data.coverage.total_cells === 0) return 0;
    return Math.round((data.coverage.cells_with_3plus_sources ?? 0) / data.coverage.total_cells * 100);
  }, [data?.coverage]);

  const baselinePct = useMemo(() => {
    if (!data?.coverage?.total_cells || data.coverage.total_cells === 0) return 0;
    return Math.round((data.coverage.cells_with_baselines ?? 0) / data.coverage.total_cells * 100);
  }, [data?.coverage]);

  if (status === 'unavailable') {
    return (
      <div className="p-6 space-y-4">
        <h2 className="text-xl font-bold">Continuous Verification Dashboard</h2>
        <p className="text-sm text-amber-300" role="status">
          Verification data unavailable: {unavailableReason ?? 'the database or source credentials are not available'}.
        </p>
        <p className="text-xs text-muted-foreground/50">
          No synthetic coverage is shown. Decision-support only; not an official avalanche warning.
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 space-y-4">
        <h2 className="text-xl font-bold">Continuous Verification Dashboard</h2>
        <p className="text-sm text-muted-foreground/60 italic">
          No verification data available. Run the verification pipeline to populate this dashboard.
        </p>
        <p className="text-xs text-muted-foreground/50">
          Decision-support only. Not an official avalanche warning.
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5" />
        <h2 className="text-xl font-bold">Continuous Verification Dashboard</h2>
      </div>

      {truncatedTables && truncatedTables.length > 0 && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="flex items-start gap-2 p-3">
            <AlertCircle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
            <div className="text-xs text-amber-300">
              <span className="font-semibold">Data may be incomplete.</span> The following tables returned the maximum row limit and may contain additional rows: {truncatedTables.join(', ')}. Coverage metrics may be understated.
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          icon={Activity}
          title="Coverage (≥3 sources)"
          value={`${coveragePct}%`}
          subtitle={`${data.coverage?.cells_with_3plus_sources ?? 0} / ${data.coverage?.total_cells ?? 0} cells`}
          variant={coveragePct >= 70 ? 'success' : coveragePct >= 40 ? 'warning' : 'danger'}
        />
        <MetricCard
          icon={Gauge}
          title="Baselines"
          value={`${baselinePct}%`}
          subtitle={`${data.coverage?.cells_with_baselines ?? 0} cells with baselines`}
          variant={baselinePct >= 70 ? 'success' : 'warning'}
        />
        <MetricCard
          icon={AlertTriangle}
          title="Stale Cells"
          value={data.stale_cells?.count ?? 0}
          subtitle={data.stale_cells?.count && data.stale_cells.count > 10 ? 'High stale count' : 'Within threshold'}
          variant={(data.stale_cells?.count ?? 0) > 10 ? 'danger' : 'success'}
        />
        <MetricCard
          icon={TrendingDown}
          title="Anomalies"
          value={data.disagreement?.anomaly_count ?? 0}
          subtitle="Current anomaly detections"
          variant={(data.disagreement?.anomaly_count ?? 0) > 5 ? 'warning' : 'default'}
        />
        <MetricCard
          icon={ClipboardList}
          title="Review Backlog"
          value={data.review_backlog?.pending_count ?? 0}
          subtitle={data.review_backlog?.oldest_pending_hours
            ? `Oldest: ${data.review_backlog.oldest_pending_hours.toFixed(0)}h`
            : 'No pending reviews'}
          variant={(data.review_backlog?.pending_count ?? 0) > 20 ? 'warning' : 'default'}
        />
        <MetricCard
          icon={Gauge}
          title="Calibration Drift"
          value={data.model_drift?.calibration_drift != null
            ? data.model_drift.calibration_drift.toFixed(3)
            : 'N/A'}
          subtitle={data.model_drift?.calibration_drift != null && data.model_drift.calibration_drift > 0.1
            ? 'Drift exceeds threshold' : 'Within bounds'}
          variant={data.model_drift?.calibration_drift != null && data.model_drift.calibration_drift > 0.1
            ? 'danger' : 'success'}
        />
      </div>

      {data.stale_cells?.top_stale && data.stale_cells.top_stale.length > 0 && (
        <Card className="border-border/40">
          <CardHeader>
            <CardTitle className="text-sm">Top Stale Cells</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {data.stale_cells.top_stale.slice(0, 10).map((cell, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="font-mono text-muted-foreground">{cell.cell_id}</span>
                  <Badge variant={cell.max_freshness_hours > 72 ? 'destructive' : 'secondary'}
                         className="text-[10px]">
                    {cell.max_freshness_hours.toFixed(1)}h
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {data.disagreement?.attribution_breakdown &&
        Object.keys(data.disagreement.attribution_breakdown).length > 0 && (
        <Card className="border-border/40">
          <CardHeader>
            <CardTitle className="text-sm">Attribution Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.disagreement.attribution_breakdown).map(([bucket, count]) => (
                <Badge key={bucket} variant="secondary" className="text-[10px]">
                  {bucket.replace(/_/g, ' ')}: {count}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {data.source_health && data.source_health.length > 0 && (
        <Card className="border-border/40">
          <CardHeader>
            <CardTitle className="text-sm">Source Health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {data.source_health.map((src) => (
                <div key={src.sensor} className="flex items-center justify-between text-xs">
                  <span className="font-medium text-muted-foreground">{src.sensor}</span>
                  <div className="flex gap-3">
                    <span className="text-muted-foreground/60">
                      latency: {src.avg_latency_hours?.toFixed(1) ?? 'N/A'}h
                    </span>
                    <span className={src.gap_count && src.gap_count > 3 ? 'text-red-400' : 'text-muted-foreground/60'}>
                      gaps: {src.gap_count ?? 0}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-xs italic text-muted-foreground/50">
        Decision-support only. Not an official avalanche warning. Always consult local avalanche forecasting services.
      </p>
    </div>
  );
}
