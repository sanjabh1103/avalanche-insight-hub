import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Mountain, X, Snowflake } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ModelStatusBadge from '@/components/ModelStatusBadge';
import RiskDashboard from '@/components/RiskDashboard';
import { MultiHazardPanel } from '@/components/MultiHazardPanel';
import type { GridCell } from '@/lib/gridUtils';
import { FORECAST_MODE_LABELS, type ForecastMode } from '@/lib/constants';

interface ForecastSidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  isCompactViewport: boolean;
  selectedCell: GridCell | null;
  weatherSummary: {
    snowfall_24h: string;
    wind_speed: string;
    temperature: string;
    precipitation: string;
    snow_depth: string;
  } | null;
  hasForecastData: boolean;
  forecastAvailability: 'ready' | 'partial' | 'stale' | 'unavailable';
  forecastNotice: string | null;
  forecastMode?: ForecastMode;
  multiHazardEnabled?: boolean;
}

export default function ForecastSidebar({
  sidebarOpen,
  setSidebarOpen,
  selectedCell,
  weatherSummary,
  hasForecastData,
  forecastAvailability,
  forecastNotice,
  forecastMode = 'full',
  multiHazardEnabled = false,
}: ForecastSidebarProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <AnimatePresence>
      {sidebarOpen && (
        <motion.aside
          initial={prefersReducedMotion ? { opacity: 0 } : { x: -320, opacity: 0 }}
          animate={prefersReducedMotion ? { opacity: 1 } : { x: 0, opacity: 1 }}
          exit={prefersReducedMotion ? { opacity: 0 } : { x: -320, opacity: 0 }}
          transition={prefersReducedMotion ? { duration: 0.01 } : { type: 'spring', damping: 25, stiffness: 200 }}
          data-testid="sidebar-panel"
          className="h-full w-[min(23rem,calc(100vw-1rem))] max-w-[23rem] flex flex-col border-r border-border/80 bg-card/90 backdrop-blur-2xl z-30 shrink-0 absolute xl:relative left-0 top-0 bottom-0 shadow-2xl shadow-black/30"
        >
          <div className="p-5 border-b border-border/70 bg-secondary/20">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-500/10 border border-emerald-500/20 shadow-[0_0_24px_hsl(156_74%_45%_/_0.18)]">
                  <Mountain className="h-5 w-5 text-emerald-400" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h1 className="text-sm font-semibold tracking-[0.18em] uppercase text-foreground">Avalanche Hub</h1>
                  </div>
                  <p className="text-[11px] uppercase tracking-[0.28em] text-muted-foreground">Forecast Provenance &amp; Model Status</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 rounded-xl touch-manipulation text-muted-foreground hover:text-foreground hover:bg-white/5"
                onClick={() => setSidebarOpen(false)}
                aria-label="Close sidebar"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="mt-4 rounded-2xl border border-emerald-500/15 bg-black/20 px-3 py-2.5">
              <ModelStatusBadge />
            </div>
            {forecastMode !== 'full' && (
              <div className="mt-2 flex items-center gap-2 rounded-lg border border-sky-500/20 bg-sky-500/5 px-2.5 py-1.5" data-testid="forecast-mode-badge">
                <Snowflake className="h-3.5 w-3.5 text-sky-400" />
                <span className="text-[11px] font-medium text-sky-300">
                  {FORECAST_MODE_LABELS[forecastMode]}
                </span>
                {forecastMode === 'transfer' && (
                  <span className="text-[10px] text-muted-foreground">(Coming soon)</span>
                )}
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="mt-0 flex-1 overflow-y-auto px-2 pb-3">
              <RiskDashboard
                cell={selectedCell}
                weatherSummary={weatherSummary}
                hasForecastData={hasForecastData}
                forecastAvailability={forecastAvailability}
                forecastNotice={forecastNotice}
              />
              {multiHazardEnabled && selectedCell?.multiHazard && (
                <MultiHazardPanel
                  assessments={Object.fromEntries(
                    Object.entries(selectedCell.multiHazard.hazard_assessments).map(
                      ([key, val]) => [key, { ...val, hazard_type: key }],
                    ),
                  )}
                  dominantHazard={selectedCell.multiHazard.dominant_hazard}
                  compositeRisk={selectedCell.multiHazard.composite_risk}
                  compositeRiskLevel={selectedCell.multiHazard.composite_risk_level}
                  cellLat={selectedCell.lat}
                  cellLng={selectedCell.lng}
                />
              )}
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
