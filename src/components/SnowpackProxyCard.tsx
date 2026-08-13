import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Snowflake, HelpCircle } from 'lucide-react';
import type { GridCell } from '@/lib/gridUtils';
import {
  SNOWPACK_PROXY_LIMITATION,
  SNOWPACK_PROXY_TITLE,
  SNOWPACK_PROXY_TOOLTIP,
} from '@/lib/snowpackProxyCopy';

interface Props {
  selectedCell: GridCell | null;
}

// Story 20: Class-II proxy visibility. HIM-STRAT seasonal proxies are calculated
// in daily_inference.py from cumulative weather since winter start (~Nov 1) and
// surfaced per-cell under grid_geojson[n].snowpack_proxy. This card renders the
// two numbers the Expert Mode UI is contractually required to display.

function shearStrengthClass(value: number): { label: string; tone: string } {
  if (value < 3) return { label: 'Weak', tone: 'text-red-400' };
  if (value < 5) return { label: 'Moderate', tone: 'text-amber-300' };
  return { label: 'Strong', tone: 'text-emerald-300' };
}

function settlementLabel(value: number): string {
  if (value < 0.25) return 'Fresh / loose';
  if (value < 0.55) return 'Partially settled';
  if (value < 0.8) return 'Settled';
  return 'Highly consolidated';
}

export default function SnowpackProxyCard({ selectedCell }: Props) {
  const proxy = selectedCell?.snowpackProxy;
  const shear = proxy?.estimated_shear_strength;
  const settle = proxy?.snow_settlement_index;
  const hasScalarData = typeof shear === 'number' || typeof settle === 'number';
  const hasProvenance = Boolean(
    proxy?.season_start || proxy?.method || proxy?.source_class || proxy?.source ||
    typeof proxy?.uncertainty === 'number' || proxy?.quality_flags?.length || proxy?.run_id ||
    proxy?.execution_status || proxy?.track || proxy?.approval_state || proxy?.forecast_cycle ||
    typeof proxy?.lead_time_h === 'number' || typeof proxy?.profile_available === 'boolean' ||
    proxy?.episode_state || proxy?.stale_reason || typeof proxy?.official_warning_eligible === 'boolean',
  );
  const hasDisplayData = hasScalarData || hasProvenance;

  return (
    <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="text-xs uppercase tracking-[0.24em] text-muted-foreground flex items-center gap-1.5">
          <Snowflake className="h-3 w-3" /> {SNOWPACK_PROXY_TITLE}
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex items-center text-muted-foreground/80"><HelpCircle className="h-3 w-3" /></span>
            </TooltipTrigger>
            <TooltipContent side="left" className="text-xs max-w-xs">
              {SNOWPACK_PROXY_TOOLTIP}
            </TooltipContent>
          </Tooltip>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-2 space-y-3">
        {!hasDisplayData ? (
          <p className="text-xs text-muted-foreground italic">
            Snowpack proxy unavailable for this cell. Run the daily inference job to populate the seasonal-memory estimate.
          </p>
        ) : (
          <>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground">
                <span>Shear Strength Proxy Index</span>
                {typeof shear === 'number' && (
                  <span className={`font-mono ${shearStrengthClass(shear).tone}`}>{shearStrengthClass(shear).label}</span>
                )}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-lg text-foreground">
                  {typeof shear === 'number' ? shear.toFixed(2) : '—'}
                </span>
                <span className="text-[10px] text-muted-foreground">normalized index</span>
              </div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground">
                <span>Snow Settlement Index</span>
                {typeof settle === 'number' && (
                  <span className="font-mono text-sky-300">{settlementLabel(settle)}</span>
                )}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-lg text-foreground">
                  {typeof settle === 'number' ? settle.toFixed(2) : '—'}
                </span>
                <span className="text-[10px] text-muted-foreground">0 = fresh · 1 = fully consolidated</span>
              </div>
            </div>
            {hasProvenance && (
              <div className="text-[10px] text-muted-foreground space-y-0.5">
                <div>{SNOWPACK_PROXY_LIMITATION}.</div>
                {proxy.season_start && (
                  <div>
                    Season start: <span className="font-mono">{proxy.season_start}</span>
                    {proxy.method ? <span className="ml-2">· method: {proxy.method}</span> : null}
                  </div>
                )}
                {!proxy.season_start && proxy.method && (
                  <div>
                    Method: <span className="font-mono">{proxy.method}</span>
                  </div>
                )}
                {/* Phase 12: provenance/uncertainty display (backward-compatible) */}
                {proxy.source_class && (
                  <div>
                    Source class: <span className="font-mono text-amber-300/80">{proxy.source_class}</span>
                    {proxy.source ? <span className="ml-1">· {proxy.source}</span> : null}
                  </div>
                )}
                {typeof proxy.uncertainty === 'number' && (
                  <div>
                    Uncertainty: <span className="font-mono text-amber-300/80">{(proxy.uncertainty * 100).toFixed(0)}%</span>
                  </div>
                )}
                {proxy.quality_flags && proxy.quality_flags.length > 0 && (
                  <div>
                    Quality flags: <span className="font-mono">{proxy.quality_flags.join(', ')}</span>
                  </div>
                )}
                {proxy.run_id && (
                  <div>
                    Run ID: <span className="font-mono">{proxy.run_id}</span>
                  </div>
                )}
                {proxy.execution_status && (
                  <div>
                    Execution status: <span className="font-mono text-sky-300/90">{proxy.execution_status}</span>
                  </div>
                )}
                {proxy.track && (
                  <div>
                    Track: <span className="font-mono">{proxy.track}</span>
                    {proxy.approval_state ? <span className="ml-1">· approval: {proxy.approval_state}</span> : null}
                  </div>
                )}
                {proxy.forecast_cycle && (
                  <div>
                    Forecast cycle: <span className="font-mono">{proxy.forecast_cycle}</span>
                    {typeof proxy.lead_time_h === 'number' ? <span className="ml-1">· lead: {proxy.lead_time_h}h</span> : null}
                  </div>
                )}
                {typeof proxy.profile_available === 'boolean' && (
                  <div>Profile available: <span className="font-mono">{proxy.profile_available ? 'yes' : 'no'}</span></div>
                )}
                {proxy.episode_state && (
                  <div>Episode state: <span className="font-mono">{proxy.episode_state}</span></div>
                )}
                {proxy.stale_reason && (
                  <div>Stale/partial reason: <span className="font-mono">{proxy.stale_reason}</span></div>
                )}
                {typeof proxy.official_warning_eligible === 'boolean' && (
                  <div data-testid="snowpack-official-warning-eligibility">
                    Official-warning eligible: <span className="font-mono">{proxy.official_warning_eligible ? 'yes' : 'no'}</span>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
