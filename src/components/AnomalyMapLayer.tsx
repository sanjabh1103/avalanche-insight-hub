import { useMemo } from 'react';
import { AlertTriangle, Eye } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { type GridCell } from '@/lib/gridUtils';

interface AnomalyMapLayerProps {
  cells: GridCell[];
  visible: boolean;
  onToggle: () => void;
}

const ANOMALY_STATE_COLORS: Record<string, string> = {
  normal: 'bg-emerald-500/20 border-emerald-500/40',
  watch: 'bg-amber-500/20 border-amber-500/40',
  anomaly: 'bg-red-500/20 border-red-500/40',
  unverified: 'bg-slate-500/20 border-slate-500/40',
};

const ANOMALY_STATE_LABELS: Record<string, string> = {
  normal: 'Normal',
  watch: 'Watch',
  anomaly: 'Anomaly',
  unverified: 'Unverified',
};

const ATTRIBUTION_LABELS: Record<string, string> = {
  forcing_error: 'Forcing Error',
  sensing_gap: 'Sensing Gap',
  physics_model_bias: 'Physics Model Bias',
  terrain_transfer_error: 'Terrain Transfer Error',
  threshold_miscalibration: 'Threshold Miscalibration',
  unattributed: 'Unattributed',
};

export default function AnomalyMapLayer({ cells, visible, onToggle }: AnomalyMapLayerProps) {
  const anomalyStats = useMemo(() => {
    let anomalyCount = 0;
    let watchCount = 0;
    let normalCount = 0;
    let unverifiedCount = 0;
    const attributionBreakdown: Record<string, number> = {};

    for (const cell of cells) {
      const state = cell.verificationPacket?.anomaly_state ?? 'unverified';

      switch (state) {
        case 'anomaly':
          anomalyCount++;
          break;
        case 'watch':
          watchCount++;
          break;
        case 'normal':
          normalCount++;
          break;
        case 'unverified':
          unverifiedCount++;
          break;
      }

      const bucket = cell.verificationPacket?.attribution_bucket;
      if (bucket) {
        attributionBreakdown[bucket] = (attributionBreakdown[bucket] || 0) + 1;
      }
    }

    return { anomalyCount, watchCount, normalCount, unverifiedCount, attributionBreakdown };
  }, [cells]);

  const hasAnomalyData = anomalyStats.anomalyCount > 0 || anomalyStats.watchCount > 0 || anomalyStats.normalCount > 0 || anomalyStats.unverifiedCount > 0;

  if (!hasAnomalyData && !visible) {
    return null;
  }

  return (
    <div className="border border-border/70 bg-card/60 backdrop-blur-xl rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <AlertTriangle className="h-3 w-3 text-amber-500" />
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Anomaly Layer
          </span>
        </div>
        <button
          onClick={onToggle}
          className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          aria-label={visible ? 'Hide anomaly layer' : 'Show anomaly layer'}
        >
          {visible ? 'Hide' : 'Show'}
        </button>
      </div>

      {!hasAnomalyData && (
        <p className="text-[10px] italic text-muted-foreground">
          No anomaly data available for this run.
        </p>
      )}

      {hasAnomalyData && visible && (
        <>
          <div className="flex flex-wrap gap-1.5">
            {anomalyStats.anomalyCount > 0 && (
              <Badge variant="outline" className="text-[9px] border-red-500/40 bg-red-500/10">
                {anomalyStats.anomalyCount} Anomaly
              </Badge>
            )}
            {anomalyStats.watchCount > 0 && (
              <Badge variant="outline" className="text-[9px] border-amber-500/40 bg-amber-500/10">
                {anomalyStats.watchCount} Watch
              </Badge>
            )}
            {anomalyStats.normalCount > 0 && (
              <Badge variant="outline" className="text-[9px] border-emerald-500/40 bg-emerald-500/10">
                {anomalyStats.normalCount} Normal
              </Badge>
            )}
            {anomalyStats.unverifiedCount > 0 && (
              <Badge variant="outline" className="text-[9px] border-slate-500/40 bg-slate-500/10">
                {anomalyStats.unverifiedCount} Unverified
              </Badge>
            )}
          </div>

          {Object.keys(anomalyStats.attributionBreakdown).length > 0 && (
            <div className="space-y-1 pt-1 border-t border-border/40">
              <span className="text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                Attribution
              </span>
              {Object.entries(anomalyStats.attributionBreakdown).map(([bucket, count]) => (
                <div key={bucket} className="flex items-center justify-between text-[10px]">
                  <span className="text-muted-foreground">
                    {ATTRIBUTION_LABELS[bucket] || bucket}
                  </span>
                  <span className="font-mono text-muted-foreground/70">{count}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center gap-1 pt-1 border-t border-border/40">
            <Eye className="h-2.5 w-2.5 text-muted-foreground/50" />
            <span className="text-[8px] italic text-muted-foreground/60">
              Decision-support only. Not an official avalanche warning.
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export { ANOMALY_STATE_COLORS, ANOMALY_STATE_LABELS, ATTRIBUTION_LABELS };
