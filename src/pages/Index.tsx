import { useState, useCallback, useMemo, useEffect, lazy, Suspense } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mountain, AlertTriangle, Settings, BarChart3, Loader2, Menu, X, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { toast } from 'sonner';
import AvalancheMap from '@/components/AvalancheMap';
import RiskDashboard from '@/components/RiskDashboard';
import TimeSlider from '@/components/TimeSlider';
import AdminDashboard from '@/components/AdminDashboard';
import FieldReportForm from '@/components/FieldReportForm';
import ModelStatusBadge from '@/components/ModelStatusBadge';
import RiskLegend from '@/components/RiskLegend';
import RegionSelector, { REGIONS, type Region } from '@/components/RegionSelector';
import DisclaimerBanner from '@/components/DisclaimerBanner';
import ShareForecast from '@/components/ShareForecast';
import ExportForecast from '@/components/ExportForecast';
import ThemeToggle from '@/components/ThemeToggle';
import HistoricalEventsToggle, { type AvalancheEvent } from '@/components/HistoricalEventsToggle';
import ExpertModePanel from '@/components/ExpertModePanel';
import { generateForecastGrid, type GridCell } from '@/lib/gridUtils';
import { supabase } from '@/integrations/supabase/client';
import { useIsMobile } from '@/hooks/use-mobile';

export default function Index() {
  const isMobile = useIsMobile();
  const [region, setRegion] = useState<Region>(REGIONS[0]);
  const [timeOffset, setTimeOffset] = useState(0);
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [forecasting, setForecasting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [forecastId, setForecastId] = useState<string | undefined>();
  const [hourlyGrids, setHourlyGrids] = useState<GridCell[][] | null>(null);
  const [showEvents, setShowEvents] = useState(false);
  const [remoteEvents, setRemoteEvents] = useState<AvalancheEvent[]>([]);
  const [localEvents, setLocalEvents] = useState<AvalancheEvent[]>([]);
  const [weatherSummary, setWeatherSummary] = useState<{ snowfall_24h: string; wind_speed: string; temperature: string; precipitation: string; snow_depth: string } | null>(null);

  // Expert mode state
  const [expertMode, setExpertMode] = useState(false);
  const [expertPanelOpen, setExpertPanelOpen] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showRoads, setShowRoads] = useState(false);
  const [showInfra, setShowInfra] = useState(false);
  const [showVectorPolygons, setShowVectorPolygons] = useState(false);
  const [playingTimeline, setPlayingTimeline] = useState(false);

  const maxHour = hourlyGrids ? hourlyGrids.length - 1 : (expertMode ? 71 : 24);

  const historicalEvents = useMemo(() => {
    const merged = [...localEvents, ...remoteEvents];
    const deduped = new Map<string, AvalancheEvent>();
    merged.forEach((event) => deduped.set(event.id, event));
    return Array.from(deduped.values());
  }, [localEvents, remoteEvents]);

  // Toggle expert mode
  useEffect(() => {
    if (expertMode) setExpertPanelOpen(true);
    else { setExpertPanelOpen(false); setShowHeatmap(false); setShowRoads(false); setShowInfra(false); setShowVectorPolygons(false); }
  }, [expertMode]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'r' || e.key === 'R') { e.preventDefault(); if (!forecasting) runForecast(); }
      if (e.key === ' ') { e.preventDefault(); setPlayingTimeline(p => !p); }
      if (e.key === 'ArrowRight') { e.preventDefault(); setTimeOffset(t => Math.min(t + 1, maxHour)); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); setTimeOffset(t => Math.max(t - 1, 0)); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [forecasting, maxHour]);

  // Realtime subscription for avalanche_events
  useEffect(() => {
    if (!showEvents) return;
    const channel = supabase
      .channel('avalanche-events-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'avalanche_events' },
        (payload) => {
          if (payload.eventType === 'INSERT') {
            const newEvent = payload.new as Record<string, unknown>;

            // Parse location
            let lat = 0, lng = 0;
            const location = newEvent.location;
            if (typeof location === 'string') {
              const m = location.match(/POINT\(([-\d.]+)\s+([-\d.]+)\)/);
              if (m) { lng = parseFloat(m[1]); lat = parseFloat(m[2]); }
            } else if (location && typeof location === 'object') {
              const coords = (location as { coordinates?: number[] }).coordinates;
              if (coords) { lng = coords[0]; lat = coords[1]; }
            }

            // Extract location_name from features JSONB
            const features = newEvent.features as Record<string, unknown> | null;
            const locationName = features?.location_name ? String(features.location_name) : '';

            const event: AvalancheEvent = {
              id: String(newEvent.id || ''),
              lat,
              lng,
              severity: Number(newEvent.severity) || 3,
              confidence: Number(newEvent.confidence) || 0.5,
              description: String(newEvent.description || ''),
              source: String(newEvent.source || 'unknown'),
              event_type: String(newEvent.event_type || 'unknown'),
              timestamp: String(newEvent.timestamp || ''),
              location_name: locationName,
            };

            setRemoteEvents((prev) => [event, ...prev]);
            toast.info('New avalanche event detected on map');
          }
        }
      )
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [showEvents]);

  // Auto-open sidebar on desktop
  useEffect(() => {
    if (isMobile === false) setSidebarOpen(true);
  }, [isMobile]);

  // Load shared forecast from URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const regionName = params.get('region');
    if (regionName) {
      const foundRegion = REGIONS.find(r => r.name === regionName);
      if (foundRegion) setRegion(foundRegion);
      else {
        const bboxParam = params.get('bbox');
        if (bboxParam) {
          const bbox = bboxParam.split(',').map(Number) as [number, number, number, number];
          if (bbox.length === 4 && bbox.every(n => !isNaN(n))) {
            setRegion({ name: regionName, bbox, center: [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], zoom: 9 });
          }
        }
      }
    }
    const hourParam = params.get('hour');
    if (hourParam) { const h = parseInt(hourParam, 10); if (!isNaN(h) && h >= 0) setTimeOffset(h); }
    if (params.get('expert') === '1') setExpertMode(true);

    const sharedForecast = params.get('forecast');
    const hourValue = hourParam ? parseInt(hourParam, 10) : 0;
    if (sharedForecast) {
      supabase.from('forecasts').select('hourly_grids, bbox').eq('id', sharedForecast).single().then(({ data }) => {
        if (data?.hourly_grids && Array.isArray(data.hourly_grids)) {
          setHourlyGrids(data.hourly_grids as unknown as GridCell[][]);
          setForecastId(sharedForecast);
          const cellParam = params.get('cell');
          if (cellParam) {
            const [row, col] = cellParam.split(',').map(Number);
            const safeHourIdx = Math.min(hourValue, (data.hourly_grids as unknown as GridCell[][]).length - 1);
            const grid = (data.hourly_grids as unknown as GridCell[][])[safeHourIdx];
            if (grid) {
              const cell = grid.find(c => c.row === row && c.col === col);
              if (cell) {
                setSelectedCell(cell);
                if (!isMobile) setSidebarOpen(true);
              }
            }
          }
          toast.success('Restored shared forecast view');
        }
      });
    }
  }, []);

  const grid = useMemo(() => {
    if (hourlyGrids && hourlyGrids[timeOffset]) {
      return { cells: hourlyGrids[timeOffset], timestamp: new Date(Date.now() + timeOffset * 3600000).toISOString(), bbox: region.bbox };
    }
    return generateForecastGrid(region.bbox, timeOffset);
  }, [timeOffset, region.bbox, hourlyGrids]);

  const handleCellClick = useCallback((cell: GridCell) => {
    setSelectedCell(cell);
    if (isMobile) setSidebarOpen(true);
  }, [isMobile]);

  const handleRegionChange = useCallback((r: Region) => {
    setRegion(r); setSelectedCell(null); setHourlyGrids(null); setForecastId(undefined); setTimeOffset(0);
  }, []);

  const runForecast = async () => {
    setForecasting(true);
    const hours = expertMode ? 72 : 24;
    toast.info(`Running ${hours}h forecast with real weather data...`);
    try {
      const { data, error } = await supabase.functions.invoke('run-forecast', {
        body: { bbox: region.bbox, timeOffset, regionName: region.name, hours },
      });
      if (error) throw error;
      if (data?.forecastId) {
        setForecastId(data.forecastId);
        setWeatherSummary(data?.weatherSummary || null);
        const { data: forecast } = await supabase.from('forecasts').select('hourly_grids').eq('id', data.forecastId).single();
        if (forecast?.hourly_grids && Array.isArray(forecast.hourly_grids)) {
          setHourlyGrids(forecast.hourly_grids as unknown as GridCell[][]);
        }
      }
      toast.success(`Forecast complete • Source: ${data?.weatherSource || 'simulation'} • ${data?.hours || hours + 1} hours`);
      if (data?.weatherSummary) {
        toast.info(`Real weather: ${data.weatherSummary.snowfall_24h}cm snow, ${data.weatherSummary.wind_speed}km/h wind`);
      }
    } catch {
      toast.success('Forecast generated (client simulation)');
    } finally {
      setForecasting(false);
    }
  };

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background">
      <DisclaimerBanner />

      <div className="flex-1 flex overflow-hidden relative">
        {/* Mobile overlay */}
        {isMobile && sidebarOpen && (
          <div className="absolute inset-0 bg-black/50 z-20" onClick={() => setSidebarOpen(false)} />
        )}

        {/* Left Sidebar */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.aside
              initial={{ x: -320, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -320, opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="w-80 h-full flex flex-col border-r border-border bg-card z-30 shrink-0 absolute md:relative left-0 top-0 bottom-0 shadow-xl"
            >
              <div className="p-4 border-b border-border bg-card/70 backdrop-blur-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Mountain className="h-6 w-6 text-primary" />
                    <div>
                      <h1 className="text-sm font-semibold text-foreground">Avalanche Hub</h1>
                      <p className="text-[10px] text-muted-foreground">Risk Intelligence Platform</p>
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" className="h-8 w-8 touch-manipulation" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-3">
                  <ModelStatusBadge />
                </div>
              </div>

              <Tabs defaultValue="dashboard" className="flex-1 flex flex-col min-h-0">
                <TabsList className="mx-3 mt-3 bg-secondary">
                  <TabsTrigger value="dashboard" className="flex items-center gap-1.5 text-xs">
                    <BarChart3 className="h-3.5 w-3.5" /> Dashboard
                  </TabsTrigger>
                  <TabsTrigger value="admin" className="flex items-center gap-1.5 text-xs">
                    <Settings className="h-3.5 w-3.5" /> Admin
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="dashboard" className="flex-1 overflow-y-auto mt-0">
                  <RiskDashboard cell={selectedCell} weatherSummary={weatherSummary} />
                </TabsContent>
                <TabsContent value="admin" className="flex-1 overflow-y-auto mt-0">
                  <AdminDashboard />
                </TabsContent>
              </Tabs>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main Map Area */}
        <div className="flex-1 relative flex flex-col min-h-0">
          {/* Top Controls */}
          <div className="absolute top-3 left-3 z-50 flex flex-col gap-2 max-w-[calc(100vw-140px)]">
            {!sidebarOpen && (
              <Button variant="outline" size="icon" className="h-10 w-10 glass-panel border-0 touch-manipulation" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
                <Menu className="h-5 w-5" />
              </Button>
            )}
            <div className="flex items-center gap-2 glass-panel rounded-xl px-2 py-2 shadow-sm relative z-50">
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground pl-1 pr-1.5">Region</span>
              <RegionSelector value={region.name} onChange={handleRegionChange} />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-2 glass-panel rounded-xl px-2 py-2 shadow-sm">
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground pl-1 pr-1.5">Display</span>
                <ThemeToggle />
              </div>
              {/* Expert Mode Toggle */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2 glass-panel rounded-xl px-3 py-2 shadow-sm">
                    <Zap className={`h-3.5 w-3.5 ${expertMode ? 'text-amber-400' : 'text-muted-foreground'}`} />
                    <Label className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground cursor-pointer" htmlFor="expert-toggle">Expert</Label>
                    <Switch id="expert-toggle" checked={expertMode} onCheckedChange={setExpertMode} aria-label="Toggle Expert Mode" />
                  </div>
                </TooltipTrigger>
                <TooltipContent>Enable impact overlays, 72h forecast, hydrograph, and vector polygons</TooltipContent>
              </Tooltip>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="absolute top-3 right-3 z-10 flex items-center gap-2 flex-wrap justify-end">
            <Button onClick={runForecast} disabled={forecasting} className="h-10 mr-1 text-xs font-semibold gap-2 bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg touch-manipulation" aria-label="Run forecast">
              {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
              {isMobile ? 'FORECAST' : expertMode ? 'RUN 72H FORECAST' : 'RUN 24H FORECAST'}
            </Button>
            <ShareForecast forecastId={forecastId} region={region} hour={timeOffset} selectedCell={selectedCell} expertMode={expertMode} />
            <ExportForecast grid={grid} events={historicalEvents} regionName={region.name} hour={timeOffset} />
            <HistoricalEventsToggle
              visible={showEvents}
              onToggle={() => {
                setShowEvents((current) => {
                  const next = !current;
                  if (!next) { setRemoteEvents([]); setLocalEvents([]); }
                  return next;
                });
              }}
              onEventsLoaded={setRemoteEvents}
              bbox={region.bbox}
            />
            <Button variant="outline" className="h-10 text-xs font-semibold gap-2 glass-panel border-0 text-destructive hover:text-destructive touch-manipulation" onClick={() => setReportOpen(true)} aria-label="Submit field report">
              <AlertTriangle className="h-4 w-4" />
              {isMobile ? '' : 'REPORT'}
            </Button>
          </div>

          {/* Map */}
          <div className="flex-1">
            <AvalancheMap
              cells={grid.cells}
              selectedCell={selectedCell}
              onCellClick={handleCellClick}
              center={region.center}
              zoom={region.zoom}
              historicalEvents={historicalEvents}
              showHeatmap={expertMode && showHeatmap}
              showRoads={expertMode && showRoads}
              showInfra={expertMode && showInfra}
              showVectorPolygons={expertMode && showVectorPolygons}
              bbox={region.bbox}
            />
          </div>

          {/* Legend */}
          <div className="absolute bottom-20 right-3 z-10 hidden md:block">
            <RiskLegend />
          </div>

          {/* Data source indicator */}
          {hourlyGrids && (
            <div className="absolute top-16 right-3 z-10">
              <span className="glass-panel rounded-full px-3 py-1 text-[10px] font-mono text-green-400">
                ● LIVE DATA ({hourlyGrids.length}h)
              </span>
            </div>
          )}

          {/* Timeline Scrubber */}
          <div className="absolute bottom-3 left-3 right-3 z-10">
            <TimeSlider value={timeOffset} onChange={setTimeOffset} max={maxHour} playing={playingTimeline} onPlayToggle={setPlayingTimeline} />
          </div>
        </div>

        {/* Expert Mode Right Panel */}
        <ExpertModePanel
          open={expertPanelOpen}
          onClose={() => setExpertPanelOpen(false)}
          showHeatmap={showHeatmap}
          onToggleHeatmap={setShowHeatmap}
          showRoads={showRoads}
          onToggleRoads={setShowRoads}
          showInfra={showInfra}
          onToggleInfra={setShowInfra}
          showVectorPolygons={showVectorPolygons}
          onToggleVectorPolygons={setShowVectorPolygons}
          hourlyGrids={hourlyGrids}
          selectedCell={selectedCell}
          regionBbox={region.bbox}
        />

        {/* Field Report Modal */}
        <FieldReportForm
          open={reportOpen}
          onClose={() => setReportOpen(false)}
          onSubmitted={(event) => {
            setLocalEvents((prev) => [event, ...prev]);
            setShowEvents(true);
          }}
          regionCenter={region.center}
        />
      </div>
    </div>
  );
}
