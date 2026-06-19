import { motion, AnimatePresence } from 'framer-motion';
import { Mountain, X, BarChart3, Settings } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import ModelStatusBadge from '@/components/ModelStatusBadge';
import RiskDashboard from '@/components/RiskDashboard';
import type { GridCell } from '@/lib/gridUtils';

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
}

export default function ForecastSidebar({
  sidebarOpen,
  setSidebarOpen,
  isCompactViewport,
  selectedCell,
  weatherSummary,
  hasForecastData,
  forecastAvailability,
  forecastNotice,
}: ForecastSidebarProps) {
  return (
    <AnimatePresence>
      {sidebarOpen && (
        <motion.aside
          initial={{ x: -320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -320, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
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
                  <p className="text-[10px] uppercase tracking-[0.28em] text-muted-foreground">Noir control room</p>
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
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="mx-4 mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-border/70 bg-secondary/60 p-1">
              <Button
                type="button"
                className="h-11 justify-center gap-1.5 rounded-xl bg-emerald-500 text-[11px] font-semibold uppercase tracking-[0.18em] text-black hover:bg-emerald-400"
              >
                <BarChart3 className="h-3.5 w-3.5" />
                Dashboard
              </Button>
              <Button
                asChild
                variant="ghost"
                className="h-11 justify-center gap-1.5 rounded-xl text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:bg-white/5 hover:text-foreground"
              >
                <Link to="/admin" onClick={() => { if (isCompactViewport) setSidebarOpen(false); }}>
                  <Settings className="h-3.5 w-3.5" />
                  Admin
                </Link>
              </Button>
            </div>
            <div className="mt-0 flex-1 overflow-y-auto px-2 pb-3">
              <RiskDashboard
                cell={selectedCell}
                weatherSummary={weatherSummary}
                hasForecastData={hasForecastData}
                forecastAvailability={forecastAvailability}
                forecastNotice={forecastNotice}
              />
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
