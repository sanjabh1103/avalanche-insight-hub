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
  const hasData = typeof shear === 'number' || typeof settle === 'number';

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
        {!hasData ? (
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
            {proxy?.season_start && (
              <div className="text-[10px] text-muted-foreground space-y-0.5">
                <div>{SNOWPACK_PROXY_LIMITATION}.</div>
                <div>
                  Season start: <span className="font-mono">{proxy.season_start}</span>
                  {proxy.method ? <span className="ml-2">· method: {proxy.method}</span> : null}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
