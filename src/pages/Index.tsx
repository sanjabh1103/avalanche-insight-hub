import { Suspense, lazy } from 'react';
import { useForecastState } from '@/hooks/useForecastState';
import { useMediaQuery } from '@/hooks/use-mobile';
import ForecastSidebar from '@/components/ForecastSidebar';
import ForecastTopControls from '@/components/ForecastTopControls';
import ForecastActionControls from '@/components/ForecastActionControls';
import { MapSurfaceFallback, ExpertPanelFallback, ModalFallback } from '@/components/ForecastFallbacks';
import DataLatencyBanner from '@/components/DataLatencyBanner';
import DisclaimerBanner from '@/components/DisclaimerBanner';
import RiskLegend from '@/components/RiskLegend';
import TimeSlider from '@/components/TimeSlider';
import {
  forecastGridRowToRunoutPolygons,
  forecastGridRowToSarGeometries,
} from '@/lib/gridUtils';
import { mergeAvalancheEvents } from '@/lib/avalancheEvents';

const LazyAvalancheMap = lazy(() => import('@/components/AvalancheMap'));
const LazyFieldReportForm = lazy(() => import('@/components/FieldReportForm'));
const LazyExpertModePanel = lazy(() => import('@/components/ExpertModePanel'));
const LazyVoxelNeighborhoodModal = lazy(() => import('@/components/VoxelNeighborhoodModal'));

export default function Index() {
  const state = useForecastState();
  const isCompactViewport = useMediaQuery('(max-width: 1279px)');

  const leftControlInset = !isCompactViewport && state.sidebarOpen ? 'calc(23rem + 1rem)' : '1rem';
  const rightControlInset = !isCompactViewport && state.expertPanelOpen ? 'calc(23rem + 1rem)' : '1rem';
  const useWideTopControlLayout = !isCompactViewport && !state.sidebarOpen && !state.expertPanelOpen;

  const fallbackForecastStatus = state.hourlyGrids && !state.forecastBulletin ? (
    <div
      data-testid="forecast-publication-status"
      className="flex min-w-0 w-full flex-1 flex-col gap-1 rounded-2xl border border-border/70 bg-black/20 px-3 py-3 shadow-sm"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
          state.forecastAvailability === 'ready'
            ? 'bg-emerald-500/20 text-emerald-200'
            : state.forecastAvailability === 'partial'
              ? 'bg-amber-500/20 text-amber-200'
              : 'bg-slate-500/20 text-slate-200'
        }`}>
          {state.forecastAvailability === 'ready' ? 'Current Published Forecast' : `${state.forecastAvailability} Published Forecast`}
        </span>
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          {state.activeForecastRow?.forecast_date ?? 'date unavailable'} • {state.hourlyGrids.length}h
        </span>
      </div>
      <div className="text-xs text-foreground">
        {state.forecastNotice || 'Same-day publication proof is available; structured bulletin content is not present for this proof artifact.'}
      </div>
    </div>
  ) : null;

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background text-foreground">
      <DisclaimerBanner />
      {state.hourlyGrids && (
        <div className="px-4 py-1 z-50">
          <DataLatencyBanner
            lastForecastDate={state.activeForecastRow?.forecast_date ?? null}
            publishedAt={(state.activeForecastRow as Record<string, unknown> | null)?.published_at as string | null}
          />
        </div>
      )}

      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_30%),radial-gradient(circle_at_80%_0%,_hsl(199_90%_60%_/_0.09),_transparent_22%)]" />

      <div className="flex-1 flex overflow-hidden relative">
        {/* Mobile overlay */}
        {isCompactViewport && state.sidebarOpen && (
          <div className="absolute inset-0 bg-black/50 z-20" onClick={() => state.setSidebarOpen(false)} />
        )}

        {/* Left Sidebar */}
        <ForecastSidebar
          sidebarOpen={state.sidebarOpen}
          setSidebarOpen={state.setSidebarOpen}
          isCompactViewport={isCompactViewport}
          selectedCell={state.selectedCell}
          weatherSummary={state.weatherSummary}
          hasForecastData={Boolean(state.hourlyGrids && state.grid.cells.length > 0)}
          forecastAvailability={state.forecastAvailability}
          forecastNotice={state.forecastNotice}
        />

        {/* Main Map Area */}
        <div className="flex-1 relative flex flex-col min-h-0">
          {/* Top Controls */}
          <ForecastTopControls
            sidebarOpen={state.sidebarOpen}
            setSidebarOpen={state.setSidebarOpen}
            region={state.region}
            handleRegionChange={state.handleRegionChange}
            expertMode={state.expertMode}
            setExpertMode={state.setExpertMode}
            forecastBulletin={state.forecastBulletin}
            forecastAvailability={state.forecastAvailability}
            timeOffset={state.timeOffset}
            setTimeOffset={state.setTimeOffset}
            fallbackForecastStatus={fallbackForecastStatus}
            isMobile={state.isMobile}
            leftControlInset={leftControlInset}
            rightControlInset={rightControlInset}
            useWideTopControlLayout={useWideTopControlLayout}
            actionControls={
              <ForecastActionControls
                isMobile={false}
                runForecast={state.runForecast}
                forecasting={state.forecasting}
                setReportOpen={state.setReportOpen}
                forecastId={state.forecastId}
                region={state.region}
                timeOffset={state.timeOffset}
                selectedCell={state.selectedCell}
                expertMode={state.expertMode}
                show3D={state.show3DModal}
                grid={state.grid}
                regionEvents={state.regionEvents}
                eventsLoading={state.eventsLoading}
                showEvents={state.showEvents}
                setShowEvents={state.setShowEvents}
                hourlyGrids={state.hourlyGrids}
                forecastAvailability={state.forecastAvailability}
                forecastSource={state.forecastSource}
              />
            }
            forecastSourceBadge={
              state.hourlyGrids ? (
                <span data-testid="forecast-data-badge" className={`inline-flex items-center rounded-full px-3 py-1 text-[10px] font-mono ${
                  state.forecastAvailability === 'ready'
                    ? 'glass-panel text-emerald-400'
                    : state.forecastAvailability === 'partial'
                      ? 'glass-panel text-amber-300'
                      : 'glass-panel text-rose-300'
                }`}>
                  ● {state.forecastSource === 'precomputed' ? `PRECOMPUTED BATCH • ${state.forecastAvailability.toUpperCase()}` : 'FORECAST DATA'} ({state.hourlyGrids.length}h)
                </span>
              ) : null
            }
          />

          {/* Map */}
          <div className={`flex-1 ${state.isMobile ? 'pt-[15.75rem]' : isCompactViewport ? 'pt-[14.5rem] lg:pt-[12.5rem]' : 'pt-[10.5rem]'}`}>
            <Suspense fallback={<MapSurfaceFallback />}>
              <LazyAvalancheMap
                cells={state.grid.cells}
                selectedCell={state.selectedCell}
                onCellClick={state.handleCellClick}
                center={state.region.center}
                zoom={state.region.zoom}
                historicalEvents={state.historicalEvents}
                heatmapEvents={state.regionEvents}
                showHeatmap={state.expertMode && state.showHeatmap}
                showRoads={state.expertMode && state.showRoads}
                showInfra={state.expertMode && state.showInfra}
                showVectorPolygons={state.expertMode && state.showVectorPolygons}
                runoutPolygons={state.activeForecastRow ? forecastGridRowToRunoutPolygons(state.activeForecastRow) : []}
                sarEventGeometries={state.activeForecastRow ? forecastGridRowToSarGeometries(state.activeForecastRow) : []}
                bbox={state.region.bbox}
              />
            </Suspense>
            {!state.hourlyGrids && (
              <div className="pointer-events-none absolute inset-x-4 top-4 z-20 flex justify-center">
                <div className="max-w-xl rounded-2xl border border-amber-500/25 bg-black/65 px-4 py-3 text-center shadow-2xl shadow-black/25 backdrop-blur-xl">
                  <div className="text-[10px] uppercase tracking-[0.24em] text-amber-300">Published Forecast Not Loaded</div>
                  <div className="mt-1 text-sm text-foreground">
                    {state.forecastNotice || `No published forecast artifact is available for ${state.region.name} in the current hosted dataset.`}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          {!state.isMobile ? (
            <>
              <div className="absolute bottom-24 right-4 z-10 hidden md:block">
                <RiskLegend />
              </div>

              <div className="absolute bottom-4 left-4 right-4 z-10">
                <TimeSlider value={state.timeOffset} onChange={state.setTimeOffset} max={state.maxHour} playing={state.playingTimeline} onPlayToggle={state.setPlayingTimeline} />
              </div>
            </>
          ) : (
            <div className="absolute bottom-4 left-4 right-4 z-10 flex flex-col gap-3">
              <ForecastActionControls
                isMobile={true}
                runForecast={state.runForecast}
                forecasting={state.forecasting}
                setReportOpen={state.setReportOpen}
                forecastId={state.forecastId}
                region={state.region}
                timeOffset={state.timeOffset}
                selectedCell={state.selectedCell}
                expertMode={state.expertMode}
                show3D={state.show3DModal}
                grid={state.grid}
                regionEvents={state.regionEvents}
                eventsLoading={state.eventsLoading}
                showEvents={state.showEvents}
                setShowEvents={state.setShowEvents}
                hourlyGrids={state.hourlyGrids}
                forecastAvailability={state.forecastAvailability}
                forecastSource={state.forecastSource}
              />
              <RiskLegend compact className="pointer-events-auto" />
              <TimeSlider className="pointer-events-auto" value={state.timeOffset} onChange={state.setTimeOffset} max={state.maxHour} playing={state.playingTimeline} onPlayToggle={state.setPlayingTimeline} />
            </div>
          )}
        </div>

        {/* Expert Mode Right Panel */}
        {state.expertPanelOpen && (
          <Suspense fallback={<ExpertPanelFallback />}>
            <LazyExpertModePanel
              open={state.expertPanelOpen}
              onClose={() => state.setExpertPanelOpen(false)}
              showHeatmap={state.showHeatmap}
              onToggleHeatmap={state.setShowHeatmap}
              showRoads={state.showRoads}
              onToggleRoads={state.setShowRoads}
              showInfra={state.showInfra}
              onToggleInfra={state.setShowInfra}
              showVectorPolygons={state.showVectorPolygons}
              onToggleVectorPolygons={state.setShowVectorPolygons}
              hourlyGrids={state.hourlyGrids}
              selectedCell={state.selectedCell}
              regionBbox={state.region.bbox}
              regionKey={state.activeForecastRow?.region_key ?? state.region.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}
              regionName={state.region.name}
              forecastRunId={state.activeForecastRunId}
              forecastGridId={state.compatibilityForecastGridId}
              forecastHour={state.timeOffset}
              modelMetadata={state.activeModelMetadata}
              onToggle3D={() => state.setShow3DModal(true)}
            />
          </Suspense>
        )}

        {/* 3D Voxel Modal */}
        {state.show3DModal && (
          <Suspense fallback={<ModalFallback label="Loading 3D neighborhood" />}>
            <LazyVoxelNeighborhoodModal
              open={state.show3DModal}
              onClose={() => state.setShow3DModal(false)}
              bbox={state.region.bbox}
              gridCells={state.grid.cells}
              hourlyGrids={state.hourlyGrids}
              timeOffset={state.timeOffset}
            />
          </Suspense>
        )}

        {/* Field Report Modal */}
        {state.reportOpen && (
          <Suspense fallback={<ModalFallback label="Loading field report form" />}>
            <LazyFieldReportForm
              open={state.reportOpen}
              onClose={() => state.setReportOpen(false)}
              onSubmitted={(event) => {
                state.setEvents((current) => mergeAvalancheEvents(current, event));
                state.setShowEvents(true);
              }}
              regionCenter={state.region.center}
              regionBbox={state.region.bbox}
              regionName={state.region.name}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}
