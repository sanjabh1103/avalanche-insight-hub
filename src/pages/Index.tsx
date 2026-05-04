import { Suspense, lazy, useState, useCallback, useMemo, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mountain, AlertTriangle, Settings, BarChart3, Loader2, Menu, X, Zap } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { toast } from 'sonner';
import RiskDashboard from '@/components/RiskDashboard';
import TimeSlider from '@/components/TimeSlider';
import ModelStatusBadge from '@/components/ModelStatusBadge';
import RiskLegend from '@/components/RiskLegend';
import ForecastBulletinBadge from '@/components/ForecastBulletinBadge';
import RegionSelector, { REGIONS, type Region } from '@/components/RegionSelector';
import DisclaimerBanner from '@/components/DisclaimerBanner';
import ShareForecast from '@/components/ShareForecast';
import ExportForecast from '@/components/ExportForecast';
import ThemeToggle from '@/components/ThemeToggle';
import HistoricalEventsToggle from '@/components/HistoricalEventsToggle';
import {
  filterAvalancheEventsByBbox,
  mergeAvalancheEvents,
  parseAvalancheEventRow,
  removeAvalancheEvent,
  type AvalancheEvent,
} from '@/lib/avalancheEvents';
import {
    loadForecastHourPayload,
    loadForecastManifest,
    loadForecastRunouts,
    type ForecastArtifactHour,
    type ForecastArtifactManifest,
} from '@/lib/forecastArtifacts';
import { resolveSharedForecast, type SharedForecastRunRecord } from '@/lib/forecastRestore';
import { normalizeForecastBulletin, type ForecastBulletin } from '@/lib/forecastBulletins';
import {
    forecastGridRowToHourlyGrids,
    forecastGridRowToRunoutPolygons,
    forecastGridRowToSarGeometries,
    forecastGridRowUsesLegacyStaticPlayback,
    isCellUnavailable,
    normalizeGridCells,
    type ForecastGridRowRecord,
    type GridCell,
} from '@/lib/gridUtils';
import { supabase } from '@/integrations/supabase/client';
import { useIsMobile, useMediaQuery } from '@/hooks/use-mobile';

type ForecastSource = 'precomputed' | null;
type ForecastAvailability = 'ready' | 'partial' | 'stale' | 'unavailable';

type RunForecastResponse = {
  ok: boolean;
  stale: boolean;
  status: string;
  source: 'forecast_runs' | 'forecast_grids';
  forecastRunId?: string | null;
  forecastId?: string | null;
  manifestPath?: string | null;
  forecastBulletin?: ForecastBulletin | null;
  regionName: string | null;
  regionKey: string | null;
  forecastDate: string | null;
  hours: number | null;
  weatherSummary: unknown;
  modelMetadata: unknown;
  message?: string | null;
};

const DEV_PUBLIC_MASK_FIXTURE_KEY = 'public-mask-smoke';

function buildPublicMaskSmokeFixture(): {
  region: Region;
  row: ForecastGridRowRecord;
  grids: Array<GridCell[] | null>;
  bulletin: ForecastBulletin | null;
} {
  const region = REGIONS.find((candidate) => candidate.name === 'Colorado Rockies') ?? REGIONS[0];
  const bbox: [number, number, number, number] = [39.4, -106.5, 39.6, -106.3];
  const gridSize = 20;
  const rawHour0Cells = [
    {
      row: 0,
      col: 0,
      lat: 39.4,
      lng: -106.5,
      latEnd: null,
      lngEnd: null,
      lat_end: 39.41,
      lng_end: -106.49,
      risk_score: 0,
      terrain_fused_risk_score: 4,
      probability: 0.62,
      apt_eligible: true,
      apt_profile: 'apt_30_50_v1',
      public_eligible: false,
      public_mask_reasons: ['warm_low_elevation_no_snow_support'],
      public_mask_profile: {
        profile: 'apt_then_snow_elevation_public_eligible_v1',
        stage_a: 'apt_30_50_v1',
        stage_b: 'snow_elevation_proxy_v1',
      },
      snow_elevation_eligible: false,
      snow_elevation_profile: 'snow_elevation_proxy_v1',
      snow_elevation_mask_reason: 'warm_low_elevation_no_snow_support',
      snow_relevance_score: 0.08,
      snow_relevance_basis: ['hard_negative_warm_low_elevation_no_snow_support'],
      rain_on_snow_proxy: false,
      wet_snow_eligible: false,
      problem_type: 'Wet Snow',
      problem_slug: 'wet_snow',
      hazard: 0.62,
      exposure: 0.29,
      vulnerability: 0.22,
      shap_values: {},
      terrain_inputs: {
        elevation_m: 1820,
        slope_angle_deg: 35.2,
      },
    },
    {
      row: 0,
      col: 1,
      lat: 39.4,
      lng: -106.49,
      latEnd: null,
      lngEnd: null,
      lat_end: 39.41,
      lng_end: -106.48,
      risk_score: 3,
      probability: 0.58,
      apt_eligible: true,
      public_eligible: true,
      problem_type: 'Wind Slab',
      problem_slug: 'wind_slab',
      hazard: 0.58,
      exposure: 0.31,
      vulnerability: 0.24,
      shap_values: {},
      terrain_inputs: {
        elevation_m: 2450,
        slope_angle_deg: 37.6,
      },
    },
    {
      row: 1,
      col: 0,
      lat: 39.41,
      lng: -106.5,
      latEnd: null,
      lngEnd: null,
      lat_end: 39.42,
      lng_end: -106.49,
      risk_score: 0,
      terrain_fused_risk_score: 2,
      apt_eligible: false,
      apt_mask_reason: 'slope_outside_30_to_50_deg',
      problem_type: 'No Distinct Avalanche Problem',
      problem_slug: 'no_distinct_avalanche_problem',
      hazard: 0.12,
      exposure: 0.1,
      vulnerability: 0.08,
      shap_values: {},
      terrain_inputs: {
        elevation_m: 2100,
        slope_angle_deg: 18.5,
      },
    },
  ];
  const hour0 = normalizeGridCells(rawHour0Cells, {
    bbox,
    gridSize,
    warnContext: 'fixture:public-mask-smoke:hour-0',
  });
  const bulletin = normalizeForecastBulletin({
    schema_version: 'forecast-bulletin/v1',
    standard: 'EAWS-style experimental',
    danger_level: 3,
    danger_label: 'Considerable',
    primary_problem: 'wind_slab',
    problems: ['wind_slab', 'wet_snow'],
    critical_elevations: { min_m: 2200, max_m: 3000, band_step_m: 200 },
    critical_aspects: ['NW', 'N', 'NE'],
    coverage: 'ready',
    issue_window_policy: 'daypart_v1',
    primary_window: 'day_1_morning',
    primary_window_policy: 'first_available_current_or_future_daypart_v1',
    peak_window: {
      window: 'day_1_afternoon',
      danger_level: 4,
      danger_label: 'High',
      primary_problem: 'wet_snow',
      forecast_hours: [12, 13, 14],
      local_start: '2026-05-02T12:00:00-06:00',
      local_end: '2026-05-02T18:00:00-06:00',
      selected_forecast_hour: 12,
      selected_hour_local_start: '2026-05-02T12:00:00-06:00',
      selected_hour_local_end: '2026-05-02T13:00:00-06:00',
    },
    dayparts: [
      {
        window: 'day_1_night',
        day_index: 1,
        daypart: 'night',
        danger_level: 2,
        danger_label: 'Moderate',
        primary_problem: 'no_distinct_avalanche_problem',
        selected_forecast_hour: 0,
      },
      {
        window: 'day_1_morning',
        day_index: 1,
        daypart: 'morning',
        danger_level: 3,
        danger_label: 'Considerable',
        primary_problem: 'wind_slab',
        selected_forecast_hour: 6,
      },
      {
        window: 'day_1_afternoon',
        day_index: 1,
        daypart: 'afternoon',
        danger_level: 4,
        danger_label: 'High',
        primary_problem: 'wet_snow',
        selected_forecast_hour: 12,
      },
      {
        window: 'day_1_evening',
        day_index: 1,
        daypart: 'evening',
        danger_level: 3,
        danger_label: 'Considerable',
        primary_problem: 'wind_slab',
        selected_forecast_hour: 18,
      },
    ],
    double_map: false,
    aggregation_notes: ['fixture_public_mask_smoke'],
    public_mask_profile: {
      profile: 'apt_then_snow_elevation_public_eligible_v1',
      stage_a: 'apt_30_50_v1',
      stage_b: 'snow_elevation_proxy_v1',
    },
    frequency_threshold_profile: 'local_grid_share_heuristic_v2',
    derived_from: {
      aggregation: 'highest_regional_level_by_cumulative_frequency',
      source_field: 'risk_score',
      base_metric: 'probability_risk_score',
      terrain_filter_profile: 'apt_30_50_v1',
      frequency_basis: 'cumulative_ge_threshold',
      frequency_class: 'some',
      ready_cell_count: 3,
      eligible_cell_count: 2,
      max_danger_cell_count: 1,
      selected_level_cell_count: 1,
      selected_level_cell_share: 0.33,
      problem_counts: { wind_slab: 1, wet_snow: 1 },
    },
  });
  const row: ForecastGridRowRecord = {
    id: 'dev-fixture-public-mask-smoke',
    region_name: region.name,
    region_key: 'dev_public_mask_smoke',
    forecast_date: '2026-05-02',
    horizon_hours: 24,
    bbox,
    grid_size: gridSize,
    grid_geojson: hour0,
    hourly_grids: [hour0],
    runout_polygons: [],
    weather_summary: {
      snowfall_24h: '4 cm',
      wind_speed: '18 km/h',
      temperature: '1 C',
      precipitation: '6 mm',
      snow_depth: '22 cm',
    },
    model_metadata: {
      fixture: true,
      artifact_source: DEV_PUBLIC_MASK_FIXTURE_KEY,
    },
    status: 'ready',
    created_at: '2026-05-02T00:00:00Z',
  };
  return {
    region: {
      ...region,
      bbox,
      center: [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
      zoom: 11,
    },
    row,
    grids: [hour0],
    bulletin,
  };
}

const LazyAvalancheMap = lazy(() => import('@/components/AvalancheMap'));
const LazyFieldReportForm = lazy(() => import('@/components/FieldReportForm'));
const LazyExpertModePanel = lazy(() => import('@/components/ExpertModePanel'));
const LazyVoxelNeighborhoodModal = lazy(() => import('@/components/VoxelNeighborhoodModal'));

function ShellLoadingNotice({
  label,
  className = '',
}: {
  label: string;
  className?: string;
}) {
  return (
    <div className={`rounded-[1.35rem] border border-border/70 bg-card/70 px-4 py-3 shadow-2xl shadow-black/20 backdrop-blur-2xl ${className}`}>
      <div className="flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
        <span>{label}</span>
      </div>
    </div>
  );
}

function MapSurfaceFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_28%),linear-gradient(180deg,hsl(224_28%_8%),hsl(224_24%_6%))] px-4">
      <ShellLoadingNotice label="Loading map surface" className="w-full max-w-sm text-center" />
    </div>
  );
}

function ExpertPanelFallback() {
  return (
    <div className="fixed right-0 top-0 bottom-0 z-40 flex h-full w-[min(23rem,calc(100vw-0.75rem))] flex-col border-l border-border/80 bg-card/95 p-4 shadow-2xl shadow-black/40 backdrop-blur-2xl md:absolute">
      <ShellLoadingNotice label="Loading expert panel" />
    </div>
  );
}

function ModalFallback({ label }: { label: string }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
      <ShellLoadingNotice label={label} className="w-full max-w-md" />
    </div>
  );
}

export default function Index() {
  const isMobile = useIsMobile();
  const isCompactViewport = useMediaQuery('(max-width: 1279px)');
  const location = useLocation();
  const [region, setRegion] = useState<Region>(REGIONS[0]);
  const [timeOffset, setTimeOffset] = useState(0);
  const [selectedCell, setSelectedCell] = useState<GridCell | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [forecasting, setForecasting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [forecastId, setForecastId] = useState<string | undefined>();
  const [hourlyGrids, setHourlyGrids] = useState<Array<GridCell[] | null> | null>(null);
  const [activeForecastRow, setActiveForecastRow] = useState<ForecastGridRowRecord | null>(null);
  const [artifactHourRefs, setArtifactHourRefs] = useState<ForecastArtifactHour[] | null>(null);
  const [forecastSource, setForecastSource] = useState<ForecastSource>(null);
  const [forecastAvailability, setForecastAvailability] = useState<ForecastAvailability>('unavailable');
  const [forecastNotice, setForecastNotice] = useState<string | null>(null);
  const [forecastBulletin, setForecastBulletin] = useState<ForecastBulletin | null>(null);
  const [showEvents, setShowEvents] = useState(false);
  const [events, setEvents] = useState<AvalancheEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
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
  const fixtureKey = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return import.meta.env.DEV ? params.get('fixture') : null;
  }, [location.search]);

  const maxHour = hourlyGrids ? hourlyGrids.length - 1 : 0;

  const hydrateForecastGridRow = useCallback((
    row: ForecastGridRowRecord,
    options?: {
      grids?: Array<GridCell[] | null>;
      notice?: string | null;
      bulletin?: ForecastBulletin | null;
    },
  ) => {
    const grids = options?.grids ?? forecastGridRowToHourlyGrids(row);
    const legacyStaticPlayback = options?.grids
      ? false
      : forecastGridRowUsesLegacyStaticPlayback(row);
    setActiveForecastRow(row);
    setForecastId(row.id);
    setForecastSource('precomputed');
    setTimeOffset(0);
    setPlayingTimeline(false);
    const nextAvailability: ForecastAvailability = row.status === 'ready'
      ? 'ready'
      : row.status === 'partial'
        ? 'partial'
        : 'stale';
    setForecastAvailability(nextAvailability);
    const baseNotice =
      nextAvailability === 'ready'
        ? null
        : nextAvailability === 'partial'
          ? 'Using a partial precomputed forecast artifact. Some cells are unavailable in this batch run.'
          : 'Using a stale precomputed forecast artifact. Freshness is below the current target.';
    const noticeParts = [
      baseNotice,
      options?.notice ?? null,
      legacyStaticPlayback
        ? 'Legacy batch artifact: only the hour-0 grid is available, so playback is static.'
        : null,
    ].filter(Boolean);
    setForecastNotice(noticeParts.length > 0 ? noticeParts.join(' ') : null);
    setForecastBulletin(options?.bulletin ?? null);
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

  const setUnavailableForecast = useCallback((message: string) => {
    setActiveForecastRow(null);
    setForecastId(undefined);
    setForecastSource(null);
    setForecastAvailability('unavailable');
    setForecastNotice(message);
    setHourlyGrids(null);
    setSelectedCell(null);
    setTimeOffset(0);
    setPlayingTimeline(false);
    setWeatherSummary(null);
    setArtifactHourRefs(null);
    setForecastBulletin(null);
  }, []);

  const callRunForecast = useCallback(async (regionName: string): Promise<RunForecastResponse> => {
    const { data, error } = await supabase.functions.invoke('run-forecast', {
      body: { regionName },
    });
    if (error) throw error;
    return data as RunForecastResponse;
  }, []);

  const buildRowFromManifest = useCallback(async (
    response: RunForecastResponse,
    manifest: ForecastArtifactManifest,
  ): Promise<{ row: ForecastGridRowRecord; grids: Array<GridCell[] | null> }> => {
    const firstHour = manifest.hours[0];
    const firstPayload = firstHour
      ? await loadForecastHourPayload(firstHour.storageRef)
      : { cells: [] as unknown[] };
    const firstGrid = normalizeGridCells(firstPayload.cells, {
      bbox: manifest.bbox,
      gridSize: manifest.gridSize,
      warnContext: `forecast-artifact:${manifest.forecastRunId}:hour-0`,
    });
    const runouts = manifest.runoutStorageRef
      ? (await loadForecastRunouts(manifest.runoutStorageRef)).runout_polygons
      : [];
    const preallocated: Array<GridCell[] | null> = Array.from({ length: manifest.horizonHours }, (_, idx) => (
      idx === 0 ? firstGrid : null
    ));
    const row: ForecastGridRowRecord = {
      id: String(response.forecastRunId || manifest.forecastRunId || response.forecastId),
      region_name: manifest.regionName,
      region_key: manifest.regionKey,
      forecast_date: manifest.forecastDate,
      horizon_hours: manifest.horizonHours,
      bbox: manifest.bbox,
      grid_size: manifest.gridSize,
      grid_geojson: firstGrid,
      hourly_grids: preallocated,
      runout_polygons: runouts,
      weather_summary: manifest.weatherSummary,
      model_metadata: {
        ...manifest.modelMetadata,
        forecast_run_id: manifest.forecastRunId,
        manifest_storage_ref: response.manifestPath,
        runout_storage_ref: manifest.runoutStorageRef,
        compatibility_forecast_grid_id: response.forecastId,
      },
      status: response.status,
      created_at: manifest.issueTime,
    };
    return {
      row,
      grids: preallocated,
    };
  }, []);

  const loadLatestForecastProduct = useCallback(async (regionName: string) => {
    const response = await callRunForecast(regionName);
    if (!response.ok) return null;
    if (response.source === 'forecast_runs' && response.manifestPath) {
      const manifest = await loadForecastManifest(response.manifestPath);
      const { row, grids } = await buildRowFromManifest(response, manifest);
      return {
        row,
        grids,
        source: response.source,
        notice: response.message ?? null,
        artifactHours: manifest.hours,
        bulletin: normalizeForecastBulletin(response.forecastBulletin ?? manifest.forecastBulletin ?? null),
      };
    }
    if (response.forecastId) {
      const { data, error } = await supabase
        .from('forecast_grids')
        .select('id, region_name, region_key, forecast_date, horizon_hours, bbox, grid_geojson, hourly_grids, runout_polygons, weather_summary, model_metadata, status, created_at')
        .eq('id', response.forecastId)
        .maybeSingle();
      if (error) throw error;
      if (data) {
        return {
          row: data as ForecastGridRowRecord,
          grids: forecastGridRowToHourlyGrids(data as ForecastGridRowRecord),
          source: response.source,
          notice: response.message ?? null,
          artifactHours: null,
          bulletin: null,
        };
      }
    }
    return null;
  }, [buildRowFromManifest, callRunForecast]);

  const regionEvents = useMemo(
    () => filterAvalancheEventsByBbox(events, region.bbox),
    [events, region.bbox],
  );
  const historicalEvents = useMemo(
    () => (showEvents ? regionEvents : []),
    [regionEvents, showEvents],
  );

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

  useEffect(() => {
    let cancelled = false;
    setEventsLoading(true);

    supabase
      .from('avalanche_events')
      .select('id, location, severity, confidence, label_confidence, verification_status, description, source, event_type, timestamp, features')
      .order('timestamp', { ascending: false })
      .limit(300)
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          console.warn('Failed to load avalanche events:', error.message);
          return;
        }
        const parsed = (data ?? [])
          .map((row) => parseAvalancheEventRow(row as Record<string, unknown>))
          .filter((row): row is AvalancheEvent => row !== null);
        setEvents((current) => mergeAvalancheEvents(current, parsed));
      })
      .finally(() => {
        if (!cancelled) {
          setEventsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const channel = supabase
      .channel('avalanche-events-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'avalanche_events' },
        (payload) => {
          if (payload.eventType === 'DELETE') {
            const deletedId = String((payload.old as Record<string, unknown> | null)?.id ?? '');
            if (deletedId) {
              setEvents((current) => removeAvalancheEvent(current, deletedId));
            }
            return;
          }

          const nextEvent = parseAvalancheEventRow(payload.new as Record<string, unknown>);
          if (!nextEvent) return;

          setEvents((current) => mergeAvalancheEvents(current, nextEvent));
          if (payload.eventType === 'INSERT' && nextEvent.source.toLowerCase().includes('field_report') && showEvents) {
              toast.info('New field report added to the map');
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
    const params = new URLSearchParams(location.search);
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
    const hourValue = hourParam ? parseInt(hourParam, 10) : 0;
    // B10 fix: Parse expert and 3d params from URL
    if (params.get('expert') === '1') setExpertMode(true);
    if (params.get('3d') === '1') setShow3DModal(true);
    if (fixtureKey === DEV_PUBLIC_MASK_FIXTURE_KEY) {
      const fixture = buildPublicMaskSmokeFixture();
      setRegion(fixture.region);
      setArtifactHourRefs(null);
      const safeHourIdx = Math.max(0, Math.min(hourValue, fixture.grids.length - 1));
      hydrateForecastGridRow(fixture.row, {
        grids: fixture.grids,
        notice: 'Dev fixture loaded for snow/elevation public-mask smoke testing.',
        bulletin: fixture.bulletin,
      });
      setTimeOffset(safeHourIdx);
      const cellParam = params.get('cell');
      if (cellParam) {
        const [rowIndex, colIndex] = cellParam.split(',').map(Number);
        const gridAtHour = fixture.grids[safeHourIdx];
        if (gridAtHour) {
          const cell = gridAtHour.find((candidate) => candidate.row === rowIndex && candidate.col === colIndex);
          if (cell && !isCellUnavailable(cell)) {
            setSelectedCell(cell);
            if (!isMobile) setSidebarOpen(true);
          }
        }
      }
      toast.success('Loaded public-mask smoke fixture');
      return;
    }

    const sharedForecast = params.get('forecast');
    if (sharedForecast) {
      (async () => {
        const resolution = await resolveSharedForecast(sharedForecast, {
          fetchRunById: async (forecastKey) => {
            const { data } = await supabase
              .from('forecast_runs')
              .select('id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, created_at')
              .eq('id', forecastKey)
              .maybeSingle();
            return (data as SharedForecastRunRecord | null) ?? null;
          },
          fetchRunByCompatibilityForecastGridId: async (forecastKey) => {
            const { data } = await supabase
              .from('forecast_runs')
              .select('id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, created_at')
              .eq('compatibility_forecast_grid_id', forecastKey)
              .order('created_at', { ascending: false })
              .limit(1)
              .maybeSingle();
            return (data as SharedForecastRunRecord | null) ?? null;
          },
          fetchGridById: async (forecastKey) => {
            const { data } = await supabase
              .from('forecast_grids')
              .select('id, region_name, region_key, forecast_date, horizon_hours, bbox, grid_geojson, hourly_grids, runout_polygons, weather_summary, model_metadata, status, created_at')
              .eq('id', forecastKey)
              .maybeSingle();
            return (data as ForecastGridRowRecord | null) ?? null;
          },
        });
        if (resolution.source === 'forecast_runs') {
          const activeRun = resolution.run;
          const response: RunForecastResponse = {
            ok: true,
            stale: activeRun.status === 'stale',
            status: activeRun.status ?? 'ready',
            source: 'forecast_runs',
            forecastRunId: activeRun.id,
            forecastId: activeRun.compatibility_forecast_grid_id,
            manifestPath: activeRun.manifest_storage_ref,
            forecastBulletin: normalizeForecastBulletin(activeRun.forecast_bulletins),
            regionName: activeRun.region_name,
            regionKey: activeRun.region_key,
            forecastDate: activeRun.forecast_date,
            hours: activeRun.horizon_hours,
            weatherSummary: activeRun.weather_summary,
            modelMetadata: activeRun.model_metadata,
          };
          const manifest = await loadForecastManifest(activeRun.manifest_storage_ref!);
          const { row, grids } = await buildRowFromManifest(response, manifest);
          setArtifactHourRefs(manifest.hours);
          hydrateForecastGridRow(row, {
            grids,
            bulletin: normalizeForecastBulletin(response.forecastBulletin ?? manifest.forecastBulletin ?? null),
          });
          const safeHourIdx = Math.max(0, Math.min(hourValue, grids.length - 1));
          setTimeOffset(safeHourIdx);
          const cellParam = params.get('cell');
          if (cellParam) {
            const [rowIndex, colIndex] = cellParam.split(',').map(Number);
            const gridAtHour = grids[safeHourIdx];
            if (gridAtHour) {
              const cell = gridAtHour.find(c => c.row === rowIndex && c.col === colIndex);
              if (cell && !isCellUnavailable(cell)) {
                setSelectedCell(cell);
                if (!isMobile) setSidebarOpen(true);
              }
            }
          }
          toast.success(
            resolution.resolvedBy === 'compatibility_forecast_grid_id'
              ? 'Restored shared published forecast view via compatibility link'
              : 'Restored shared published forecast view',
          );
          return;
        }
        if (resolution.source === 'forecast_grids') {
          setArtifactHourRefs(null);
          const grids = hydrateForecastGridRow(resolution.grid);
          const safeHourIdx = Math.max(0, Math.min(hourValue, grids.length - 1));
          setTimeOffset(safeHourIdx);
          const cellParam = params.get('cell');
          if (cellParam) {
            const [row, col] = cellParam.split(',').map(Number);
            const gridAtHour = grids[safeHourIdx];
            if (gridAtHour) {
              const cell = gridAtHour.find(c => c.row === row && c.col === col);
              if (cell && !isCellUnavailable(cell)) {
                setSelectedCell(cell);
                if (!isMobile) setSidebarOpen(true);
              }
            }
          }
          toast.success('Restored shared legacy forecast grid view');
          return;
        }
        const activeRun = await supabase
          .from('forecast_runs')
          .select('id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, created_at')
          .eq('id', sharedForecast)
          .maybeSingle();
        if (activeRun.data?.manifest_storage_ref) {
          const response: RunForecastResponse = {
            ok: true,
            stale: activeRun.data.status === 'stale',
            status: activeRun.data.status ?? 'ready',
            source: 'forecast_runs',
            forecastRunId: activeRun.data.id,
            forecastId: activeRun.data.compatibility_forecast_grid_id,
            manifestPath: activeRun.data.manifest_storage_ref,
            forecastBulletin: normalizeForecastBulletin(activeRun.data.forecast_bulletins),
            regionName: activeRun.data.region_name,
            regionKey: activeRun.data.region_key,
            forecastDate: activeRun.data.forecast_date,
            hours: activeRun.data.horizon_hours,
            weatherSummary: activeRun.data.weather_summary,
            modelMetadata: activeRun.data.model_metadata,
          };
          const manifest = await loadForecastManifest(activeRun.data.manifest_storage_ref);
          const { row, grids } = await buildRowFromManifest(response, manifest);
          setArtifactHourRefs(manifest.hours);
          hydrateForecastGridRow(row, {
            grids,
            bulletin: normalizeForecastBulletin(response.forecastBulletin ?? manifest.forecastBulletin ?? null),
          });
          const safeHourIdx = Math.max(0, Math.min(hourValue, grids.length - 1));
          setTimeOffset(safeHourIdx);
          const cellParam = params.get('cell');
          if (cellParam) {
            const [rowIndex, colIndex] = cellParam.split(',').map(Number);
            const gridAtHour = grids[safeHourIdx];
            if (gridAtHour) {
              const cell = gridAtHour.find(c => c.row === rowIndex && c.col === colIndex);
              if (cell && !isCellUnavailable(cell)) {
                setSelectedCell(cell);
                if (!isMobile) setSidebarOpen(true);
              }
            }
          }
          toast.success('Restored shared published forecast view');
          return;
        }
        setUnavailableForecast('This shared forecast is not available in the authoritative precomputed batch artifact.');
      })();
    }
  }, [buildRowFromManifest, fixtureKey, hydrateForecastGridRow, isMobile, location.search, setUnavailableForecast]);

  const grid = useMemo(() => {
    const cells = hourlyGrids?.[timeOffset];
    if (hourlyGrids && Array.isArray(cells)) {
      const baseTimestamp = activeForecastRow?.created_at ?? `${activeForecastRow?.forecast_date ?? new Date().toISOString()}T00:00:00Z`;
      return {
        cells,
        timestamp: new Date(new Date(baseTimestamp).getTime() + timeOffset * 3600000).toISOString(),
        bbox: (activeForecastRow?.bbox as [number, number, number, number] | undefined) ?? region.bbox,
      };
    }
    return { cells: [], timestamp: new Date().toISOString(), bbox: region.bbox };
  }, [activeForecastRow?.bbox, activeForecastRow?.created_at, activeForecastRow?.forecast_date, timeOffset, region.bbox, hourlyGrids]);

  const leftControlInset = !isCompactViewport && sidebarOpen ? 'calc(23rem + 1rem)' : '1rem';
  const rightControlInset = !isCompactViewport && expertPanelOpen ? 'calc(23rem + 1rem)' : '1rem';
  const useWideTopControlLayout = !isCompactViewport && !sidebarOpen && !expertPanelOpen;

  const handleCellClick = useCallback((cell: GridCell) => {
    if (isCellUnavailable(cell)) return;
    setSelectedCell(cell);
    if (isCompactViewport) setSidebarOpen(true);
  }, [isCompactViewport]);

  const handleRegionChange = useCallback((r: Region) => {
    setRegion(r);
    setSelectedCell(null);
    setHourlyGrids(null);
    setActiveForecastRow(null);
    setForecastId(undefined);
    setForecastSource(null);
    setForecastAvailability('unavailable');
    setForecastNotice(null);
    setForecastBulletin(null);
    setTimeOffset(0);
    setWeatherSummary(null);
    setArtifactHourRefs(null);
  }, []);

  useEffect(() => {
    if (fixtureKey) return;
    let alive = true;
    (async () => {
      try {
        const latest = await loadLatestForecastProduct(region.name);
        if (alive && latest) {
          setArtifactHourRefs(latest.artifactHours);
          hydrateForecastGridRow(latest.row, {
            grids: latest.grids,
            notice: latest.notice,
            bulletin: latest.bulletin,
          });
        } else if (alive) {
          setUnavailableForecast(`No fresh precomputed forecast is available for ${region.name}.`);
        }
      } catch {
        if (alive) {
          setUnavailableForecast(`Failed to load the latest precomputed forecast for ${region.name}.`);
        }
      }
    })();
    return () => { alive = false; };
  }, [fixtureKey, region.name, hydrateForecastGridRow, loadLatestForecastProduct, setUnavailableForecast]);

  const runForecast = useCallback(async () => {
    if (fixtureKey) {
      toast.info('Dev fixture is active. Remove the fixture query parameter to refresh a live forecast.');
      return;
    }
    setForecasting(true);
    setForecastSource(null);
    try {
      toast.info('Refreshing precomputed forecast...');
      const latest = await loadLatestForecastProduct(region.name);
      if (latest) {
        setArtifactHourRefs(latest.artifactHours);
        hydrateForecastGridRow(latest.row, {
          grids: latest.grids,
          notice: latest.notice,
          bulletin: latest.bulletin,
        });
        toast.success(`Loaded precomputed forecast for ${region.name}`);
        return;
      }
      setUnavailableForecast(`No fresh precomputed forecast is available for ${region.name}.`);
      toast.error('No fresh precomputed forecast is available yet.');
    } catch {
      setUnavailableForecast(`Failed to refresh the precomputed forecast for ${region.name}.`);
      toast.error('Failed to refresh the precomputed forecast.');
    } finally {
      setForecasting(false);
    }
  }, [fixtureKey, hydrateForecastGridRow, loadLatestForecastProduct, region.name, setUnavailableForecast]);

  const actionControls = (
    <>
      <Button onClick={runForecast} disabled={forecasting} className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 bg-emerald-500 text-black hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 rounded-2xl touch-manipulation whitespace-nowrap px-4" aria-label="Refresh precomputed forecast">
        {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
        {isMobile ? 'Refresh Batch' : 'Refresh batch'}
      </Button>
      <Button variant="outline" className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 glass-panel border-0 text-foreground hover:text-foreground touch-manipulation rounded-2xl px-4" onClick={() => setReportOpen(true)} aria-label="Submit field report">
        <AlertTriangle className="h-4 w-4" />
        Report
      </Button>
      <ShareForecast className="justify-center sm:justify-start" forecastId={forecastId} region={region} hour={timeOffset} selectedCell={selectedCell} expertMode={expertMode} show3D={show3DModal} />
      <ExportForecast
        className="w-full flex-wrap sm:w-auto sm:flex-nowrap"
        buttonClassName="flex-1 justify-center sm:flex-none"
        grid={grid}
        events={regionEvents}
        regionName={region.name}
        hour={timeOffset}
        canExport={Boolean(forecastId)}
      />
      <HistoricalEventsToggle
        className="justify-center sm:justify-start"
        visible={showEvents}
        loading={eventsLoading}
        onToggle={() => setShowEvents((current) => !current)}
      />
    </>
  );

  const forecastSourceBadge = hourlyGrids ? (
    <span data-testid="forecast-data-badge" className={`inline-flex items-center rounded-full px-3 py-1 text-[10px] font-mono ${
      forecastAvailability === 'ready'
        ? 'glass-panel text-emerald-400'
        : forecastAvailability === 'partial'
          ? 'glass-panel text-amber-300'
          : 'glass-panel text-rose-300'
    }`}>
      ● {forecastSource === 'precomputed' ? `PRECOMPUTED BATCH • ${forecastAvailability.toUpperCase()}` : 'FORECAST DATA'} ({hourlyGrids.length}h)
    </span>
  ) : null;

  useEffect(() => {
    if (!artifactHourRefs || !hourlyGrids || Array.isArray(hourlyGrids[timeOffset])) {
      return;
    }
    const hourRef = artifactHourRefs.find((hour) => hour.forecastHour === timeOffset);
    if (!hourRef) return;
    let alive = true;
    (async () => {
      try {
        const payload = await loadForecastHourPayload(hourRef.storageRef);
        if (!alive) return;
        setHourlyGrids((current) => {
          if (!current || Array.isArray(current[timeOffset])) {
            return current;
          }
          const next = [...current];
          next[timeOffset] = normalizeGridCells(payload.cells, {
            bbox: activeForecastRow?.bbox ?? region.bbox,
            gridSize: activeForecastRow?.grid_size,
            warnContext: `forecast-artifact:${activeForecastRow?.id ?? forecastId ?? 'unknown'}:hour-${timeOffset}`,
          });
          return next;
        });
      } catch {
        if (alive) {
          toast.error(`Failed to load forecast hour ${timeOffset} for ${region.name}.`);
        }
      }
    })();
    return () => { alive = false; };
  }, [activeForecastRow, artifactHourRefs, forecastId, hourlyGrids, region.bbox, region.name, timeOffset]);

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
        {isCompactViewport && sidebarOpen && (
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
                  <Button variant="ghost" size="icon" className="h-9 w-9 rounded-xl touch-manipulation text-muted-foreground hover:text-foreground hover:bg-white/5" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-4 rounded-2xl border border-emerald-500/15 bg-black/20 px-3 py-2.5">
                  <ModelStatusBadge />
                </div>
              </div>

              <div className="flex min-h-0 flex-1 flex-col">
                <div className="mx-4 mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-border/70 bg-secondary/60 p-1">
                  <Button type="button" className="h-11 justify-center gap-1.5 rounded-xl bg-emerald-500 text-[11px] font-semibold uppercase tracking-[0.18em] text-black hover:bg-emerald-400">
                    <BarChart3 className="h-3.5 w-3.5" />
                    Dashboard
                  </Button>
                  <Button asChild variant="ghost" className="h-11 justify-center gap-1.5 rounded-xl text-[11px] uppercase tracking-[0.18em] text-muted-foreground hover:bg-white/5 hover:text-foreground">
                    <Link to="/admin" onClick={() => { if (isCompactViewport) setSidebarOpen(false); }}>
                      <Settings className="h-3.5 w-3.5" />
                      Admin
                    </Link>
                  </Button>
                </div>
                <div className="mt-0 flex-1 overflow-y-auto px-2 pb-3">
                  <RiskDashboard cell={selectedCell} weatherSummary={weatherSummary} />
                </div>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main Map Area */}
        <div className="flex-1 relative flex flex-col min-h-0">
          {/* Top Controls */}
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
                    <Button variant="outline" size="icon" className="h-11 w-11 glass-panel border-0 touch-manipulation rounded-2xl" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
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
                    <ForecastBulletinBadge
                      bulletin={forecastBulletin}
                      stale={forecastAvailability === 'stale'}
                      timeOffset={timeOffset}
                      onSelectForecastHour={setTimeOffset}
                    />
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

          {/* Map */}
          <div className={`flex-1 ${isMobile ? 'pt-[15.75rem]' : isCompactViewport ? 'pt-[14.5rem] lg:pt-[12.5rem]' : 'pt-[10.5rem]'}`}>
            <Suspense fallback={<MapSurfaceFallback />}>
              <LazyAvalancheMap
                cells={grid.cells}
                selectedCell={selectedCell}
                onCellClick={handleCellClick}
                center={region.center}
                zoom={region.zoom}
                historicalEvents={historicalEvents}
                heatmapEvents={regionEvents}
                showHeatmap={expertMode && showHeatmap}
                showRoads={expertMode && showRoads}
                showInfra={expertMode && showInfra}
                showVectorPolygons={expertMode && showVectorPolygons}
                runoutPolygons={activeForecastRow ? forecastGridRowToRunoutPolygons(activeForecastRow) : []}
                sarEventGeometries={activeForecastRow ? forecastGridRowToSarGeometries(activeForecastRow) : []}
                bbox={region.bbox}
              />
            </Suspense>
            {!hourlyGrids && (
              <div className="pointer-events-none absolute inset-x-4 top-4 z-20 flex justify-center">
                <div className="max-w-xl rounded-2xl border border-amber-500/25 bg-black/65 px-4 py-3 text-center shadow-2xl shadow-black/25 backdrop-blur-xl">
                  <div className="text-[10px] uppercase tracking-[0.24em] text-amber-300">Precomputed Forecast Unavailable</div>
                  <div className="mt-1 text-sm text-foreground">
                    {forecastNotice || `No fresh precomputed forecast is available for ${region.name}.`}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          {!isMobile ? (
            <>
              <div className="absolute bottom-24 right-4 z-10 hidden md:block">
                <RiskLegend />
              </div>

              <div className="absolute bottom-4 left-4 right-4 z-10">
                <TimeSlider value={timeOffset} onChange={setTimeOffset} max={maxHour} playing={playingTimeline} onPlayToggle={setPlayingTimeline} />
              </div>
            </>
          ) : (
            <div className="absolute bottom-4 left-4 right-4 z-10 flex flex-col gap-3">
              <div data-testid="mobile-action-tray" className="pointer-events-auto rounded-[1.35rem] border border-border/70 bg-card/70 px-3 py-2.5 shadow-2xl shadow-black/20 backdrop-blur-2xl">
                <div className="grid grid-cols-2 gap-2">
                  <Button onClick={runForecast} disabled={forecasting} className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 bg-emerald-500 text-black hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 rounded-2xl touch-manipulation px-4" aria-label="Refresh precomputed forecast">
                    {forecasting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mountain className="h-4 w-4" />}
                    Refresh batch
                  </Button>
                  <Button variant="outline" className="h-11 text-[11px] uppercase tracking-[0.18em] font-semibold gap-2 glass-panel border-0 text-foreground hover:text-foreground touch-manipulation rounded-2xl px-4" onClick={() => setReportOpen(true)} aria-label="Submit field report">
                    <AlertTriangle className="h-4 w-4" />
                    Report
                  </Button>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <ShareForecast className="justify-center" forecastId={forecastId} region={region} hour={timeOffset} selectedCell={selectedCell} expertMode={expertMode} show3D={show3DModal} />
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
                  canExport={Boolean(forecastId)}
                />
                {forecastSourceBadge ? <div className="mt-2">{forecastSourceBadge}</div> : null}
              </div>
              <RiskLegend compact className="pointer-events-auto" />
              <TimeSlider className="pointer-events-auto" value={timeOffset} onChange={setTimeOffset} max={maxHour} playing={playingTimeline} onPlayToggle={setPlayingTimeline} />
            </div>
          )}
        </div>

        {/* Expert Mode Right Panel */}
        {/* B8 fix: closing the sidebar ONLY hides it — does NOT turn off Expert Mode or reset overlays */}
        {expertPanelOpen && (
          <Suspense fallback={<ExpertPanelFallback />}>
            <LazyExpertModePanel
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
          </Suspense>
        )}

        {/* 3D Voxel Modal */}
        {show3DModal && (
          <Suspense fallback={<ModalFallback label="Loading 3D neighborhood" />}>
            <LazyVoxelNeighborhoodModal
              open={show3DModal}
              onClose={() => setShow3DModal(false)}
              bbox={region.bbox}
              gridCells={grid.cells}
              hourlyGrids={hourlyGrids}
              timeOffset={timeOffset}
            />
          </Suspense>
        )}

        {/* Field Report Modal */}
        {reportOpen && (
          <Suspense fallback={<ModalFallback label="Loading field report form" />}>
            <LazyFieldReportForm
              open={reportOpen}
              onClose={() => setReportOpen(false)}
              onSubmitted={(event) => {
                setEvents((current) => mergeAvalancheEvents(current, event));
                setShowEvents(true);
              }}
              regionCenter={region.center}
              regionBbox={region.bbox}
              regionName={region.name}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}
