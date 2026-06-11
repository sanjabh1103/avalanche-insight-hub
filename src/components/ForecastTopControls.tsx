import { type ReactNode } from 'react';
import { Menu, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import RegionSelector, { type Region } from '@/components/RegionSelector';
import ThemeToggle from '@/components/ThemeToggle';
import ForecastBulletinBadge from '@/components/ForecastBulletinBadge';
import type { ForecastBulletin } from '@/lib/forecastBulletins';

interface ForecastTopControlsProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  region: Region;
  handleRegionChange: (r: Region) => void;
  expertMode: boolean;
  setExpertMode: (expert: boolean) => void;
  forecastBulletin: ForecastBulletin | null;
  forecastAvailability: 'ready' | 'partial' | 'stale' | 'unavailable';
  timeOffset: number;
  setTimeOffset: (hour: number) => void;
  fallbackForecastStatus: ReactNode;
  isMobile: boolean;
  leftControlInset: string;
  rightControlInset: string;
  useWideTopControlLayout: boolean;
  actionControls: ReactNode;
  forecastSourceBadge: ReactNode;
}

export default function ForecastTopControls({
  sidebarOpen,
  setSidebarOpen,
  region,
  handleRegionChange,
  expertMode,
  setExpertMode,
  forecastBulletin,
  forecastAvailability,
  timeOffset,
  setTimeOffset,
  fallbackForecastStatus,
  isMobile,
  leftControlInset,
  rightControlInset,
  useWideTopControlLayout,
  actionControls,
  forecastSourceBadge,
}: ForecastTopControlsProps) {
  return (
    <div
      data-testid="top-control-zone"
      className="absolute top-4 left-4 right-4 z-50 pointer-events-none transition-all duration-300"
      style={{
        left: leftControlInset,
        right: rightControlInset,
      }}
    >
      <div className="flex flex-col gap-3">
        <div className="pointer-events-auto rounded-[1.35rem] border border-border/70 bg-card/70 px-3 py-3 shadow-2xl shadow-black/20 backdrop-blur-2xl">
          <div className={`grid gap-3 ${useWideTopControlLayout ? 'md:grid-cols-[minmax(0,18rem)_minmax(0,1fr)_minmax(0,16.5rem)]' : 'md:grid-cols-[minmax(0,1fr)_auto]'}`}>
            <div className="order-1 flex min-w-0 flex-wrap items-center gap-2 xl:flex-nowrap">
              {!sidebarOpen && (
                <Button
                  variant="outline"
                  size="icon"
                  className="h-11 w-11 glass-panel border-0 touch-manipulation rounded-2xl"
                  onClick={() => setSidebarOpen(true)}
                  aria-label="Open sidebar"
                >
                  <Menu className="h-5 w-5" />
                </Button>
              )}
              <div className="flex min-w-0 flex-1 items-center gap-2 glass-panel rounded-2xl px-3 py-2.5 shadow-sm">
                <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground pl-1 pr-1.5">Region</span>
                <RegionSelector value={region.name} onChange={handleRegionChange} />
              </div>
            </div>

            <div className={`order-2 flex min-w-0 flex-wrap items-center gap-2 md:justify-end ${useWideTopControlLayout ? 'xl:order-3 xl:max-w-[16.5rem] xl:justify-start xl:justify-self-end' : ''}`}>
              <div className="flex min-w-0 flex-1 items-center gap-2 glass-panel rounded-2xl px-3 py-2.5 shadow-sm md:flex-none">
                <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground pl-1 pr-1.5">Display</span>
                <ThemeToggle />
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex min-w-0 items-center gap-2 glass-panel rounded-2xl px-3 py-2.5 shadow-sm">
                    <Zap className={`h-3.5 w-3.5 ${expertMode ? 'text-amber-400' : 'text-muted-foreground'}`} />
                    <Label className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground cursor-pointer" htmlFor="expert-toggle">Expert</Label>
                    <Switch id="expert-toggle" checked={expertMode} onCheckedChange={setExpertMode} aria-label="Toggle Expert Mode" />
                  </div>
                </TooltipTrigger>
                <TooltipContent>Enable impact overlays, 72h forecast, hydrograph, and vector polygons</TooltipContent>
              </Tooltip>
            </div>

            <div className={`order-3 min-w-0 md:col-span-2 ${useWideTopControlLayout ? 'xl:order-2 xl:col-span-1' : ''}`}>
              {forecastBulletin ? (
                <ForecastBulletinBadge
                  bulletin={forecastBulletin}
                  stale={forecastAvailability === 'stale'}
                  timeOffset={timeOffset}
                  onSelectForecastHour={setTimeOffset}
                />
              ) : fallbackForecastStatus}
            </div>
          </div>
        </div>

        {!isMobile ? (
          <div data-testid="desktop-action-tray" className="pointer-events-auto flex flex-wrap items-center gap-2 rounded-[1.35rem] border border-border/70 bg-card/70 px-3 py-2.5 shadow-2xl shadow-black/20 backdrop-blur-2xl">
            {actionControls}
            {forecastSourceBadge ? <div className="ml-auto">{forecastSourceBadge}</div> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
