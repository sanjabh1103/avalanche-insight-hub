import { Loader2, Mountain, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ShareForecast from '@/components/ShareForecast';
import ExportForecast from '@/components/ExportForecast';
import HistoricalEventsToggle from '@/components/HistoricalEventsToggle';
import type { Region } from '@/components/RegionSelector';
import type { GridCell } from '@/lib/gridUtils';
import type { AvalancheEvent } from '@/lib/avalancheEvents';

interface ForecastActionControlsProps {
  isMobile: boolean;
  runForecast: () => Promise<void>;
  forecasting: boolean;
  setReportOpen: (open: boolean) => void;
  forecastId: string | undefined;
  region: Region;
  timeOffset: number;
  selectedCell: GridCell | null;
  expertMode: boolean;
  show3D: boolean;
  grid: { cells: GridCell[]; timestamp: string; bbox: [number, number, number, number] };
  regionEvents: AvalancheEvent[];
  eventsLoading: boolean;
  showEvents: boolean;
  setShowEvents: (show: boolean | ((prev: boolean) => boolean)) => void;
  hourlyGrids: Array<GridCell[] | null> | null;
  forecastAvailability: 'ready' | 'partial' | 'stale' | 'unavailable';
  forecastSource: 'precomputed' | null;
  loadedHoursCount: number;
  totalHoursHorizon: number;
  gridSize: number | null | undefined;
}

export default function ForecastActionControls({
  isMobile,
  runForecast,
  forecasting,
  setReportOpen,
  forecastId,
  region,
  timeOffset,
  selectedCell,
  expertMode,
  show3D,
  grid,
  regionEvents,
  eventsLoading,
  showEvents,
  setShowEvents,
  hourlyGrids,
  forecastAvailability,
  forecastSource,
  loadedHoursCount,
  totalHoursHorizon,
  gridSize,
}: ForecastActionControlsProps) {
  const forecastSourceBadge = hourlyGrids ? (
    <span
      data-testid="forecast-data-badge"
      className={`inline-flex items-center rounded-full px-3 py-1 text-[10px] font-mono ${
        forecastAvailability === 'ready'
          ? 'glass-panel text-emerald-400'
          : forecastAvailability === 'partial'
            ? 'glass-panel text-amber-300'
            : 'glass-panel text-rose-300'
      }`}
    >
      ● {forecastSource === 'precomputed' ? `PRECOMPUTED BATCH • ${forecastAvailability.toUpperCase()}` : 'FORECAST DATA'} • {gridSize ?? 20}×{gridSize ?? 20} • {loadedHoursCount}/{totalHoursHorizon}h
    </span>
  ) : null;

  if (isMobile) {
    return (
      <div
        data-testid="mobile-action-tray"
        className="pointer-events-auto rounded-[1.35rem] border border-border/70 bg-card/70 px-3 py-2.5 shadow-2xl shadow-black/20 backdrop-blur-2xl"
      >
        <div className="grid grid-cols-2 gap-2">
          <Button
            onClick={runForecast}
            disabled={forecasting}
            className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 bg-emerald-500 text-black hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 rounded-2xl touch-manipulation px-4"
            aria-label="Refresh latest published forecast batch"
          >
            {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
            Refresh batch
          </Button>
          <Button
            variant="outline"
            className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 glass-panel border-0 text-foreground hover:text-foreground touch-manipulation rounded-2xl px-4"
            onClick={() => setReportOpen(true)}
            aria-label="Submit field report"
          >
            <AlertTriangle className="h-4 w-4" />
            Report
          </Button>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <ShareForecast
            className="justify-center"
            forecastId={forecastId}
            region={region}
            hour={timeOffset}
            selectedCell={selectedCell}
            expertMode={expertMode}
            show3D={show3D}
          />
          <HistoricalEventsToggle
            className="justify-center"
            visible={showEvents}
            loading={eventsLoading}
            onToggle={() => setShowEvents((current) => !current)}
          />
        </div>
        <ExportForecast
          className="mt-2 w-full"
          buttonClassName="flex-1 justify-center"
          grid={grid}
          events={regionEvents}
          regionName={region.name}
          hour={timeOffset}
          canExport={Boolean(forecastId && grid.cells.length > 0)}
        />
        {forecastSourceBadge ? <div className="mt-2">{forecastSourceBadge}</div> : null}
      </div>
    );
  }

  return (
    <>
      <Button
        onClick={runForecast}
        disabled={forecasting}
        className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 bg-emerald-500 text-black hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 rounded-2xl touch-manipulation whitespace-nowrap px-4"
        aria-label="Refresh latest published forecast batch"
      >
        {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
        Refresh batch
      </Button>
      <Button
        variant="outline"
        className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 glass-panel border-0 text-foreground hover:text-foreground touch-manipulation rounded-2xl px-4"
        onClick={() => setReportOpen(true)}
        aria-label="Submit field report"
      >
        <AlertTriangle className="h-4 w-4" />
        Report
      </Button>
      <ShareForecast
        className="justify-center sm:justify-start"
        forecastId={forecastId}
        region={region}
        hour={timeOffset}
        selectedCell={selectedCell}
        expertMode={expertMode}
        show3D={show3D}
      />
      <ExportForecast
        className="w-full flex-wrap sm:w-auto sm:flex-nowrap"
        buttonClassName="flex-1 justify-center sm:flex-none"
        grid={grid}
        events={regionEvents}
        regionName={region.name}
        hour={timeOffset}
        canExport={Boolean(forecastId && grid.cells.length > 0)}
      />
      <HistoricalEventsToggle
        className="justify-center sm:justify-start"
        visible={showEvents}
        loading={eventsLoading}
        onToggle={() => setShowEvents((current) => !current)}
      />
      {forecastSourceBadge ? <div className="ml-auto">{forecastSourceBadge}</div> : null}
    </>
  );
}
