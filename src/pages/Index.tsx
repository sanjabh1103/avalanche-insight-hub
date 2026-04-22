import { useState, useCallback, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mountain, AlertTriangle, Settings, BarChart3, Loader2, Menu, X, Zap } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
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
import VoxelNeighborhoodModal from '@/components/VoxelNeighborhoodModal';
import { forecastGridRowToHourlyGrids, generateForecastGrid, type ForecastGridRowRecord, type GridCell } from '@/lib/gridUtils';
import { loadShapForCell, type ShapResult } from '@/lib/shapLoader';
import { supabase } from '@/integrations/supabase/client';
import { useIsMobile } from '@/hooks/use-mobile';

type ForecastSource = 'precomputed' | 'forecast_api' | 'generated' | null;

export default function Index() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<'dashboard' | 'admin'>(location.pathname.startsWith('/admin') ? 'admin' : 'dashboard');
  const [region, setRegion] = useState<Region>(REGIONS[0]);
  const [timeOffset, setTimeOffset] = useState(0);
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [forecasting, setForecasting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [forecastId, setForecastId] = useState<string | undefined>();
  const [hourlyGrids, setHourlyGrids] = useState<GridCell[][] | null>(null);
  const [forecastSource, setForecastSource] = useState<ForecastSource>(null);
  const [shapResult, setShapResult] = useState<ShapResult | null>(null);
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
  const [show3DModal, setShow3DModal] = useState(false);
  const [playingTimeline, setPlayingTimeline] = useState(false);

  const maxHour = hourlyGrids ? hourlyGrids.length - 1 : (expertMode ? 71 : 24);

  useEffect(() => {
    const nextTab: 'dashboard' | 'admin' = location.pathname.startsWith('/admin') ? 'admin' : 'dashboard';
    setActiveTab((current) => (current === nextTab ? current : nextTab));
  }, [location.pathname]);

  const hydrateForecastGridRow = useCallback((row: ForecastGridRowRecord) => {
    const grids = forecastGridRowToHourlyGrids(row);
    setForecastId(row.id);
    setForecastSource('precomputed');
    setHourlyGrids(grids);
    const summary = row.weather_summary;
    if (summary && typeof summary === 'object' && !Array.isArray(summary)) {
      const maybeSummary = summary as Record<string, unknown>;
      if (typeof maybeSummary.snowfall_24h === 'string') {
        setWeatherSummary({
          snowfall_24h: String(maybeSummary.snowfall_24h),
          wind_speed: String(maybeSummary.wind_speed ?? '0'),
          temperature: String(maybeSummary.temperature ?? '0'),
          precipitation: String(maybeSummary.precipitation ?? '0'),
          snow_depth: String(maybeSummary.snow_depth ?? '0'),
        });
      }
    }
    return grids;
  }, []);

  const loadLatestForecastGrid = useCallback(async (regionName: string) => {
    const today = new Date().toISOString().slice(0, 10);
    const { data, error } = await supabase
      .from('forecast_grids')
      .select('id, region_name, region_key, forecast_date, horizon_hours, bbox, grid_geojson, runout_polygons, weather_summary, model_metadata, status, created_at')
      .eq('hazard_type', 'avalanche')
      .eq('region_name', regionName)
      .eq('forecast_date', today)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (error) throw error;
    return data as ForecastGridRowRecord | null;
  }, []);

  const historicalEvents = useMemo(() => {
    const merged = [...localEvents, ...remoteEvents];
    const deduped = new Map<string, AvalancheEvent>();
    merged.forEach((event) => deduped.set(event.id, event));
    return Array.from(deduped.values());
  }, [localEvents, remoteEvents]);

  // B8/B11 fix: Toggle expert mode — open sidebar when expert mode turns ON;
  // only RESET overlays when expert mode turns OFF (not just when sidebar closes).
  // Closing the sidebar (X button) does NOT reset expertMode or overlays.
  useEffect(() => {
    if (expertMode) {
      setExpertPanelOpen(true);
    } else {
      setExpertPanelOpen(false);
      // Only clear overlays when Expert Mode is actually turned OFF
      setShowHeatmap(false);
      setShowRoads(false);
      setShowInfra(false);
      setShowVectorPolygons(false);
    }
  }, [expertMode]);

  // BUG-08 fix: Always load events from DB for export functionality, not just when heatmap is on
  useEffect(() => {
    // BUG-08: Load events regardless of heatmap toggle so export always has data
    supabase
      .from('avalanche_events')
      .select('id, location, severity, confidence, description, source, event_type, timestamp, features')
      .limit(200)
      .then(({ data }) => {
        if (!data || data.length === 0) return;
        const parsed: AvalancheEvent[] = data.map((row) => {
          let lat = 0, lng = 0;
          const loc = row.location;
          if (typeof loc === 'string') {
            const m = loc.match(/POINT\(([-\d.]+)\s+([-\d.]+)\)/);
            if (m) { lng = parseFloat(m[1]); lat = parseFloat(m[2]); }
          } else if (loc && typeof loc === 'object') {
            const coords = (loc as { coordinates?: number[] }).coordinates;
            if (coords) { lng = coords[0]; lat = coords[1]; }
          }
          const features = row.features as Record<string, unknown> | null;
          return {
            id: String(row.id || ''),
            lat, lng,
            severity: Number(row.severity) || 3,
            confidence: Number(row.confidence) || 0.5,
            description: String(row.description || ''),
            source: String(row.source || 'unknown'),
            event_type: String(row.event_type || 'unknown'),
            timestamp: String(row.timestamp || ''),
            location_name: features?.location_name ? String(features.location_name) : '',
          };
        });
        setRemoteEvents(parsed);
        toast.info(`Loaded ${parsed.length} historical events for heatmap`);
      });
  }, [showHeatmap]);

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
            // Only show the generic toast for human-submitted field reports.
            // System jobs (Sentinel, NewsData, recent activity refresh) already have their own job toasts.
            if (String(newEvent.source || '').toLowerCase().includes('field_report')) {
              toast.info('New field report added to the map');
            }
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
    // B10 fix: Parse expert and 3d params from URL
    if (params.get('expert') === '1') setExpertMode(true);
    if (params.get('3d') === '1') setShow3DModal(true);

    const sharedForecast = params.get('forecast');
    const hourValue = hourParam ? parseInt(hourParam, 10) : 0;
    if (sharedForecast) {
      (async () => {
        const precomputed = await supabase.from('forecast_grids').select('id, region_name, region_key, forecast_date, horizon_hours, bbox, grid_geojson, runout_polygons, weather_summary, model_metadata, status, created_at').eq('id', sharedForecast).maybeSingle();
        if (precomputed.data) {
          const grids = hydrateForecastGridRow(precomputed.data as ForecastGridRowRecord);
          const cellParam = params.get('cell');
          if (cellParam) {
            const [row, col] = cellParam.split(',').map(Number);
            const safeHourIdx = Math.min(hourValue, grids.length - 1);
            const gridAtHour = grids[safeHourIdx];
            if (gridAtHour) {
              const cell = gridAtHour.find(c => c.row === row && c.col === col);
              if (cell) {
                setSelectedCell(cell);
                if (!isMobile) setSidebarOpen(true);
              }
            }
          }
          toast.success('Restored shared precomputed forecast view');
          return;
        }

        const legacy = await supabase.from('forecasts').select('hourly_grids, bbox').eq('id', sharedForecast).maybeSingle();
        if (legacy.data?.hourly_grids && Array.isArray(legacy.data.hourly_grids)) {
          setHourlyGrids(legacy.data.hourly_grids as unknown as GridCell[][]);
          setForecastId(sharedForecast);
          const cellParam = params.get('cell');
          if (cellParam) {
            const [row, col] = cellParam.split(',').map(Number);
            const safeHourIdx = Math.min(hourValue, (legacy.data.hourly_grids as unknown as GridCell[][]).length - 1);
            const grid = (legacy.data.hourly_grids as unknown as GridCell[][])[safeHourIdx];
            if (grid) {
              const cell = grid.find(c => c.row === row && c.col === col);
              if (cell) {
                setSelectedCell(cell);
                if (!isMobile) setSidebarOpen(true);
              }
            }
          }
          toast.success('Restored shared forecast view');
          setForecastSource('forecast_api');
        }
      })();
    }
  }, [hydrateForecastGridRow, isMobile]);

  const grid = useMemo(() => {
    if (hourlyGrids && hourlyGrids[timeOffset]) {
      return { cells: hourlyGrids[timeOffset], timestamp: new Date(Date.now() + timeOffset * 3600000).toISOString(), bbox: region.bbox };
    }
    return generateForecastGrid(region.bbox, timeOffset);
  }, [timeOffset, region.bbox, hourlyGrids]);

  const controlInset = !isMobile && (expertPanelOpen || sidebarOpen) ? 'calc(23rem + 1rem)' : '1rem';

  const handleCellClick = useCallback((cell: GridCell) => {
    setSelectedCell(cell);
    if (isMobile) setSidebarOpen(true);
  }, [isMobile]);

  const handleRegionChange = useCallback((r: Region) => {
    setRegion(r); setSelectedCell(null); setHourlyGrids(null); setForecastId(undefined); setForecastSource(null); setTimeOffset(0); setWeatherSummary(null);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const latest = await loadLatestForecastGrid(region.name);
        if (alive && latest) {
          hydrateForecastGridRow(latest);
        }
      } catch {
        // Keep the existing simulated fallback when no precomputed grid exists.
      }
    })();
    return () => { alive = false; };
  }, [region.name, hydrateForecastGridRow, loadLatestForecastGrid]);

  // P1.2: Load real TreeSHAP from forecast_shap_cache whenever the user
  // selects a different cell or a new grid is hydrated. The loader has its
  // own 30s in-memory cache so fast hover-click sequences don't hammer the
  // RPC, and returns null when the cache is cold — RiskDashboard then falls
  // back to the inline heuristic (honestly labeled).
  useEffect(() => {
    let alive = true;
    if (!selectedCell || !forecastId) {
      setShapResult(null);
      return () => { alive = false; };
    }
    loadShapForCell(forecastId, selectedCell.row, selectedCell.col, timeOffset).then((result) => {
      if (!alive) return;
      setShapResult(result);
    });
    return () => { alive = false; };
  }, [forecastId, selectedCell, timeOffset]);

  const runForecast = useCallback(async () => {
    setForecasting(true);
    setForecastSource(null);
    const hours = expertMode ? 72 : 24;
    try {
      toast.info(`Loading ${hours}h precomputed forecast...`);
      const latest = await loadLatestForecastGrid(region.name);
      if (latest) {
        hydrateForecastGridRow(latest);
        toast.success(`Loaded precomputed forecast for ${region.name}`);
        return;
      }
      toast.info('No precomputed forecast available yet — using legacy generator as fallback');
      const { data, error } = await supabase.functions.invoke('run-forecast', {
        body: { bbox: region.bbox, timeOffset, regionName: region.name, hours },
        headers: {
          Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_ANON_KEY ?? import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY}`,
        },
      });
      if (error) throw error;
      if (data?.forecastId) {
        setForecastId(data.forecastId);
        setForecastSource('forecast_api');
        setWeatherSummary(data?.weatherSummary || null);
        const { data: forecast } = await supabase.from('forecasts').select('hourly_grids').eq('id', data.forecastId).maybeSingle();
        if (forecast?.hourly_grids && Array.isArray(forecast.hourly_grids)) {
          setHourlyGrids(forecast.hourly_grids as unknown as GridCell[][]);
        } else {
          setForecastId(undefined);
          setForecastSource('generated');
          setHourlyGrids(Array.from({ length: hours }, (_, hour) => generateForecastGrid(region.bbox, hour).cells));
        }
      }
      const fallbackInfo = data?.fallback_used ? ' • Fallback: yes' : '';
      toast.success(`Forecast complete • Source: ${data?.weatherSource || 'simulation'} • Mode: ${data?.capability_summary || data?.mode || 'Edge-only fallback'}${fallbackInfo} • ${data?.hours || hours + 1} hours`);
      if (data?.weatherSummary) {
        toast.info(`Real weather: ${data.weatherSummary.snowfall_24h}cm snow, ${data.weatherSummary.wind_speed}km/h wind`);
      }
    } catch {
      setForecastId(undefined);
      setHourlyGrids(Array.from({ length: hours }, (_, hour) => generateForecastGrid(region.bbox, hour).cells));
      setForecastSource('generated');
      toast.success('Forecast generated (client simulation)');
    } finally {
      setForecasting(false);
    }
  }, [expertMode, hydrateForecastGridRow, loadLatestForecastGrid, region.bbox, region.name, timeOffset]);

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
  }, [forecasting, maxHour, runForecast]);

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background text-foreground">
      <DisclaimerBanner />

      <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_30%),radial-gradient(circle_at_80%_0%,_hsl(199_90%_60%_/_0.09),_transparent_22%)]" />

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
              className="w-[23rem] h-full flex flex-col border-r border-border/80 bg-card/90 backdrop-blur-2xl z-30 shrink-0 absolute md:relative left-0 top-0 bottom-0 shadow-2xl shadow-black/30"
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
                  <Button variant="ghost" size="icon" className="h-9 w-9 rounded-xl touch-manipulation text-muted-foreground hover:text-foreground hover:bg-white/5" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-4 rounded-2xl border border-emerald-500/15 bg-black/20 px-3 py-2.5">
                  <ModelStatusBadge />
                </div>
              </div>

              <Tabs
                value={activeTab}
                onValueChange={(value) => {
                  const nextTab = value === 'admin' ? 'admin' : 'dashboard';
                  setActiveTab(nextTab);
                  navigate(nextTab === 'admin' ? '/admin' : '/');
                }}
                className="flex-1 flex flex-col min-h-0"
              >
                <TabsList className="mx-4 mt-4 grid grid-cols-2 bg-secondary/60 border border-border/70 p-1 h-11 rounded-2xl">
                  <TabsTrigger value="dashboard" className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.18em] rounded-xl data-[state=active]:bg-emerald-500 data-[state=active]:text-black">
                    <BarChart3 className="h-3.5 w-3.5" /> Dashboard
                  </TabsTrigger>
                  <TabsTrigger value="admin" className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.18em] rounded-xl data-[state=active]:bg-emerald-500 data-[state=active]:text-black">
                    <Settings className="h-3.5 w-3.5" /> Admin
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="dashboard" className="flex-1 overflow-y-auto mt-0 px-2 pb-3">
                  <RiskDashboard cell={selectedCell} weatherSummary={weatherSummary} shapResult={shapResult} />
                </TabsContent>
                <TabsContent value="admin" className="flex-1 overflow-y-auto mt-0 px-2 pb-3">
                  <AdminDashboard />
                </TabsContent>
              </Tabs>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main Map Area */}
        <div className="flex-1 relative flex flex-col min-h-0">
          {/* Top Controls */}
          <div
            className="absolute top-4 left-4 right-4 z-50 pointer-events-none transition-all duration-300"
            style={{
              left: controlInset,
              right: controlInset,
            }}
          >
            <div className="flex flex-col gap-3">
              <div className="pointer-events-auto flex flex-col gap-3 rounded-[1.35rem] border border-border/70 bg-card/70 px-3 py-3 shadow-2xl shadow-black/20 backdrop-blur-2xl lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap items-center gap-2">
                  {!sidebarOpen && (
                    <Button variant="outline" size="icon" className="h-11 w-11 glass-panel border-0 touch-manipulation rounded-2xl" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
                      <Menu className="h-5 w-5" />
                    </Button>
                  )}
                  <div className="flex items-center gap-2 glass-panel rounded-2xl px-3 py-2.5 shadow-sm">
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground pl-1 pr-1.5">Region</span>
                    <RegionSelector value={region.name} onChange={handleRegionChange} />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                  <div className="flex items-center gap-2 glass-panel rounded-2xl px-3 py-2.5 shadow-sm">
                    <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground pl-1 pr-1.5">Display</span>
                    <ThemeToggle />
                  </div>
                  {/* Expert Mode Toggle */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center gap-2 glass-panel rounded-2xl px-3 py-2.5 shadow-sm">
                        <Zap className={`h-3.5 w-3.5 ${expertMode ? 'text-amber-400' : 'text-muted-foreground'}`} />
                        <Label className="text-[10px] font-mono uppercase tracking-[0.22em] text-muted-foreground cursor-pointer" htmlFor="expert-toggle">Expert</Label>
                        <Switch id="expert-toggle" checked={expertMode} onCheckedChange={setExpertMode} aria-label="Toggle Expert Mode" />
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>Enable impact overlays, 72h forecast, hydrograph, and vector polygons</TooltipContent>
                  </Tooltip>
                </div>
              </div>

              <div
                className="pointer-events-auto flex flex-wrap items-center gap-2 rounded-[1.35rem] border border-border/70 bg-card/70 px-3 py-2.5 shadow-2xl shadow-black/20 backdrop-blur-2xl"
                style={{
                  maxWidth: sidebarOpen && isMobile ? 'calc(100vw - 2rem)' : '100%',
                }}
              >
                <Button onClick={runForecast} disabled={forecasting} className="h-11 mr-1 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 bg-emerald-500 text-black hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 rounded-2xl touch-manipulation whitespace-nowrap px-4" aria-label="Run forecast">
                  {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
                  {isMobile ? 'FORECAST' : expertMode ? 'RUN 72H' : 'RUN 24H'}
                </Button>
                <ShareForecast forecastId={forecastId} region={region} hour={timeOffset} selectedCell={selectedCell} expertMode={expertMode} show3D={show3DModal} />
                <ExportForecast grid={grid} events={historicalEvents} regionName={region.name} hour={timeOffset} canExport={Boolean(forecastId)} />
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
                <Button variant="outline" className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 glass-panel border-0 text-foreground hover:text-foreground touch-manipulation rounded-2xl" onClick={() => setReportOpen(true)} aria-label="Submit field report">
                  <AlertTriangle className="h-4 w-4" />
                  {isMobile ? '' : 'REPORT'}
                </Button>
              </div>
            </div>
          </div>

          {/* Map */}
          <div className="flex-1 pt-[12.5rem] md:pt-[11.25rem] lg:pt-[10.5rem]">
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
          <div className="absolute bottom-24 right-4 z-10 hidden md:block">
            <RiskLegend />
          </div>

          {/* Data source indicator */}
          {hourlyGrids && (
            <div className="absolute top-[11rem] right-4 z-10 md:top-[8.75rem] lg:top-[7.5rem]">
              <span className="glass-panel rounded-full px-3 py-1 text-[10px] font-mono text-emerald-400">
                ● {forecastSource === 'precomputed'
                  ? 'PRECOMPUTED GRID'
                  : forecastSource === 'forecast_api'
                    ? 'FORECAST RUN'
                    : forecastSource === 'generated'
                      ? 'SIMULATED GRID'
                      : 'FORECAST DATA'} ({hourlyGrids.length}h)
              </span>
            </div>
          )}

          {/* Timeline Scrubber */}
          <div className="absolute bottom-4 left-4 right-4 z-10">
            <TimeSlider value={timeOffset} onChange={setTimeOffset} max={maxHour} playing={playingTimeline} onPlayToggle={setPlayingTimeline} />
          </div>
        </div>

        {/* Expert Mode Right Panel */}
        {/* B8 fix: closing the sidebar ONLY hides it — does NOT turn off Expert Mode or reset overlays */}
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
          onToggle3D={() => setShow3DModal(true)}
        />

        {/* 3D Voxel Modal */}
        {show3DModal && (
          <VoxelNeighborhoodModal
            open={show3DModal}
            onClose={() => setShow3DModal(false)}
            bbox={region.bbox}
            gridCells={grid.cells}
            hourlyGrids={hourlyGrids}
            timeOffset={timeOffset}
          />
        )}

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
