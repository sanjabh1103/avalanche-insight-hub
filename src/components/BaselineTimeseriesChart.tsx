import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BaselineTimeseriesPoint {
  date: string;
  p25?: number | null;
  p50?: number | null;
  p75?: number | null;
  observed?: number | null;
  residual_zscore?: number | null;
  anomaly_state?: string;
  freshness_hours?: number | null;
  sensor?: string;
}

interface BaselineTimeseriesChartProps {
  points: BaselineTimeseriesPoint[];
  sensor?: string;
  defaultExpanded?: boolean;
}

const ANOMALY_BG: Record<string, string> = {
  anomaly: 'fill-red-500/10',
  watch: 'fill-amber-500/10',
  normal: 'fill-emerald-500/5',
  unverified: 'fill-slate-500/5',
};

const CHART_WIDTH = 280;
const CHART_HEIGHT = 100;
const PADDING = { top: 8, right: 8, bottom: 16, left: 28 };

export default function BaselineTimeseriesChart({
  points,
  sensor,
  defaultExpanded = false,
}: BaselineTimeseriesChartProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const chartData = useMemo(() => {
    if (!points || points.length === 0) return null;

    const allValues = points.flatMap(p => [
      p.p25, p.p50, p.p75, p.observed,
    ].filter((v): v is number => v != null && typeof v === 'number'));

    if (allValues.length === 0) return null;

    const minVal = Math.min(...allValues);
    const maxVal = Math.max(...allValues);
    const range = maxVal - minVal || 1;
    const padRange = range * 0.1;
    const yMin = minVal - padRange;
    const yMax = maxVal + padRange;
    const yRange = yMax - yMin || 1;

    const plotW = CHART_WIDTH - PADDING.left - PADDING.right;
    const plotH = CHART_HEIGHT - PADDING.top - PADDING.bottom;

    const n = points.length;
    const xScale = (i: number) => PADDING.left + (n > 1 ? (i / (n - 1)) * plotW : plotW / 2);
    const yScale = (v: number) => PADDING.top + plotH - ((v - yMin) / yRange) * plotH;

    const p25Path = points
      .filter(p => p.p25 != null)
      .map((p, _i) => {
        const idx = points.indexOf(p);
        return `${xScale(idx)},${yScale(p.p25!)}`;
      }).join(' L ');

    const p75Path = points
      .filter(p => p.p75 != null)
      .map((p, _i) => {
        const idx = points.indexOf(p);
        return `${xScale(idx)},${yScale(p.p75!)}`;
      }).join(' L ');

    const p50Path = points
      .filter(p => p.p50 != null)
      .map((p, _i) => {
        const idx = points.indexOf(p);
        return `${xScale(idx)},${yScale(p.p50!)}`;
      }).join(' L ');

    const observedDots = points
      .filter(p => p.observed != null)
      .map((p, _i) => {
        const idx = points.indexOf(p);
        return { cx: xScale(idx), cy: yScale(p.observed!), state: p.anomaly_state ?? 'unverified' };
      });

    const bandPath = points
      .filter(p => p.p25 != null && p.p75 != null)
      .map((p, _i) => {
        const idx = points.indexOf(p);
        return `${xScale(idx)},${yScale(p.p25!)}`;
      }).join(' L ');

    const bandPathReverse = points
      .filter(p => p.p25 != null && p.p75 != null)
      .reverse()
      .map((p) => {
        const idx = points.indexOf(p);
        return `${xScale(idx)},${yScale(p.p75!)}`;
      }).join(' L ');

    return {
      p25Path, p75Path, p50Path, observedDots,
      bandPath: bandPath && bandPathReverse ? `M ${bandPath} L ${bandPathReverse} Z` : '',
      yMin, yMax, xScale, yScale, plotW, plotH,
    };
  }, [points]);

  return (
    <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground space-y-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1.5 font-semibold uppercase tracking-[0.18em] text-left"
        aria-expanded={expanded}
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <TrendingUp className="h-3 w-3" />
        Baseline History{sensor ? ` — ${sensor}` : ''}
      </button>

      {!expanded && (
        <p className="text-[9px] text-muted-foreground/60 italic pl-5">
          {points.length} data point{points.length !== 1 ? 's' : ''} available — click to expand
        </p>
      )}

      {expanded && (
        <>
          {!chartData ? (
            <p className="text-[9px] text-muted-foreground/60 italic pl-5">
              No baseline time-series data available for this cell.
            </p>
          ) : (
            <div className="pl-3 space-y-1">
              <svg
                width={CHART_WIDTH}
                height={CHART_HEIGHT}
                viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                className="overflow-visible"
                role="img"
                aria-label="Baseline time-series chart"
              >
                {points.map((p, i) => {
                  const x = chartData.xScale(i);
                  const state = p.anomaly_state ?? 'unverified';
                  return (
                    <rect
                      key={`bg-${i}`}
                      x={x - (chartData.plotW / Math.max(points.length, 1)) / 2}
                      y={PADDING.top}
                      width={chartData.plotW / Math.max(points.length, 1)}
                      height={chartData.plotH}
                      className={ANOMALY_BG[state] || ANOMALY_BG.unverified}
                    />
                  );
                })}

                {chartData.bandPath && (
                  <path d={chartData.bandPath} className="fill-emerald-500/10 stroke-none" />
                )}

                {chartData.p50Path && (
                  <path
                    d={`M ${chartData.p50Path}`}
                    className="fill-none stroke-emerald-400/60"
                    strokeWidth={1}
                  />
                )}

                {chartData.p25Path && (
                  <path
                    d={`M ${chartData.p25Path}`}
                    className="fill-none stroke-emerald-400/30"
                    strokeWidth={0.5}
                    strokeDasharray="2,2"
                  />
                )}

                {chartData.p75Path && (
                  <path
                    d={`M ${chartData.p75Path}`}
                    className="fill-none stroke-emerald-400/30"
                    strokeWidth={0.5}
                    strokeDasharray="2,2"
                  />
                )}

                {chartData.observedDots.map((dot, i) => (
                  <circle
                    key={`obs-${i}`}
                    cx={dot.cx}
                    cy={dot.cy}
                    r={2}
                    className={
                      dot.state === 'anomaly' ? 'fill-red-400'
                      : dot.state === 'watch' ? 'fill-amber-400'
                      : dot.state === 'normal' ? 'fill-emerald-400'
                      : 'fill-slate-400'
                    }
                  />
                ))}

                <line
                  x1={PADDING.left}
                  y1={CHART_HEIGHT - PADDING.bottom}
                  x2={CHART_WIDTH - PADDING.right}
                  y2={CHART_HEIGHT - PADDING.bottom}
                  className="stroke-border/40"
                  strokeWidth={0.5}
                />
                <line
                  x1={PADDING.left}
                  y1={PADDING.top}
                  x2={PADDING.left}
                  y2={CHART_HEIGHT - PADDING.bottom}
                  className="stroke-border/40"
                  strokeWidth={0.5}
                />

                <text x={PADDING.left - 2} y={PADDING.top + 4} textAnchor="end" className="fill-muted-foreground/50 text-[7px]">
                  {chartData.yMax.toFixed(1)}
                </text>
                <text x={PADDING.left - 2} y={CHART_HEIGHT - PADDING.bottom} textAnchor="end" className="fill-muted-foreground/50 text-[7px]">
                  {chartData.yMin.toFixed(1)}
                </text>

                {points.length > 0 && (
                  <text x={PADDING.left} y={CHART_HEIGHT - 3} className="fill-muted-foreground/50 text-[7px]">
                    {points[0].date}
                  </text>
                )}
                {points.length > 1 && (
                  <text x={CHART_WIDTH - PADDING.right} y={CHART_HEIGHT - 3} textAnchor="end" className="fill-muted-foreground/50 text-[7px]">
                    {points[points.length - 1].date}
                  </text>
                )}
              </svg>

              <div className="flex flex-wrap gap-2 text-[8px] text-muted-foreground/60">
                <span className="flex items-center gap-0.5">
                  <span className="inline-block w-2 h-0.5 bg-emerald-400/60" /> p50
                </span>
                <span className="flex items-center gap-0.5">
                  <span className="inline-block w-2 h-0.5 bg-emerald-400/30 border-t border-dashed" /> p25/p75
                </span>
                <span className="flex items-center gap-0.5">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-400" /> observed
                </span>
              </div>

              <p className="text-[8px] italic text-muted-foreground/50">
                Decision-support only. Not an official avalanche warning.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
