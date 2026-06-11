import { useState, useCallback, useMemo, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import { useIsMobile } from '@/hooks/use-mobile';
import { REGIONS, type Region } from '@/components/RegionSelector';
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
  forecastGridRowUsesLegacyStaticPlayback,
  isCellUnavailable,
  normalizeGridCells,
  type ForecastGridRowRecord,
  type GridCell,
} from '@/lib/gridUtils';

export type ForecastSource = 'precomputed' | null;
export type ForecastAvailability = 'ready' | 'partial' | 'stale' | 'unavailable';

export type RunForecastResponse = {
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
  publishedAt?: string | null;
  freshnessHours?: number | null;
  sameDayPublished?: boolean;
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

export function useForecastState() {
  const isMobile = useIsMobile();
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
  
  const activeModelMetadata = useMemo(() => (
    activeForecastRow?.model_metadata && typeof activeForecastRow.model_metadata === 'object' && !Array.isArray(activeForecastRow.model_metadata)
      ? activeForecastRow.model_metadata as Record<string, unknown>
      : null
  ), [activeForecastRow]);

  const activeForecastRunId = typeof activeModelMetadata?.forecast_run_id === 'string'
    ? activeModelMetadata.forecast_run_id
    : activeForecastRow?.id ?? forecastId ?? null;

  const compatibilityForecastGridId = typeof activeModelMetadata?.compatibility_forecast_grid_id === 'string'
    ? activeModelMetadata.compatibility_forecast_grid_id
    : forecastId ?? null;

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
          ? 'Current-state batch artifact is partial. Some cells are unavailable in this run.'
          : 'Current-state view is using the latest published batch, but the publication is outside the freshness target.';
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
        published_at: response.publishedAt ?? null,
        freshness_hours: response.freshnessHours ?? null,
        same_day_published: response.sameDayPublished ?? false,
      },
      status: response.stale ? 'stale' : response.status,
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

  // Expert panel overlay synchronization
  useEffect(() => {
    if (expertMode) {
      setExpertPanelOpen(true);
    } else {
      setExpertPanelOpen(false);
      setShowHeatmap(false);
      setShowRoads(false);
      setShowInfra(false);
      setShowVectorPolygons(false);
    }
  }, [expertMode]);

  // Real-time events loading
  useEffect(() => {
    let cancelled = false;
    setEventsLoading(true);

    Promise.resolve(
      supabase
        .from('avalanche_events')
        .select('id, location, severity, confidence, label_confidence, verification_status, description, source, event_type, timestamp, features')
        .order('timestamp', { ascending: false })
        .limit(300)
    )
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

  // Real-time events subscription
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

  // Restore state from URL params
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const regionName = params.get('region');
    const hourParam = params.get('hour');
    const hourValue = hourParam ? parseInt(hourParam, 10) : 0;
    
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
    
    if (hourParam) {
      const h = parseInt(hourParam, 10);
      if (!isNaN(h) && h >= 0) setTimeOffset(h);
    }
    
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
              .select('id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, published_at, created_at')
              .eq('id', forecastKey)
              .maybeSingle();
            return (data as SharedForecastRunRecord | null) ?? null;
          },
          fetchRunByCompatibilityForecastGridId: async (forecastKey) => {
            const { data } = await supabase
              .from('forecast_runs')
              .select('id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, published_at, created_at')
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
            publishedAt: activeRun.published_at ?? null,
            freshnessHours: null,
            sameDayPublished: false,
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
          .select('id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, published_at, created_at')
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
            publishedAt: activeRun.data.published_at ?? null,
            freshnessHours: null,
            sameDayPublished: false,
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

  const handleCellClick = useCallback((cell: GridCell) => {
    if (isCellUnavailable(cell)) return;
    setSelectedCell(cell);
  }, []);

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

  // Fetch forecast logic on region change
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
          setUnavailableForecast(`No published forecast artifact is available for ${region.name} in the current hosted dataset.`);
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
      toast.info('Checking the latest published forecast batch...');
      const latest = await loadLatestForecastProduct(region.name);
      if (latest) {
        setArtifactHourRefs(latest.artifactHours);
        hydrateForecastGridRow(latest.row, {
          grids: latest.grids,
          notice: latest.notice,
          bulletin: latest.bulletin,
        });
        toast.success(`Loaded latest published forecast for ${region.name}`);
        return;
      }
      setUnavailableForecast(`No published forecast artifact is available for ${region.name} in the current hosted dataset.`);
      toast.error('No published forecast artifact is available yet.');
    } catch {
      setUnavailableForecast(`Failed to refresh the precomputed forecast for ${region.name}.`);
      toast.error('Failed to refresh the precomputed forecast.');
    } finally {
      setForecasting(false);
    }
  }, [fixtureKey, hydrateForecastGridRow, loadLatestForecastProduct, region.name, setUnavailableForecast]);

  return {
    isMobile,
    region,
    setRegion,
    timeOffset,
    setTimeOffset,
    selectedCell,
    setSelectedCell,
    reportOpen,
    setReportOpen,
    forecasting,
    setForecasting,
    sidebarOpen,
    setSidebarOpen,
    forecastId,
    hourlyGrids,
    activeForecastRow,
    artifactHourRefs,
    forecastSource,
    forecastAvailability,
    forecastNotice,
    forecastBulletin,
    showEvents,
    setShowEvents,
    events,
    setEvents,
    eventsLoading,
    weatherSummary,
    expertMode,
    setExpertMode,
    expertPanelOpen,
    setExpertPanelOpen,
    showHeatmap,
    setShowHeatmap,
    showRoads,
    setShowRoads,
    showInfra,
    setShowInfra,
    showVectorPolygons,
    setShowVectorPolygons,
    show3DModal,
    setShow3DModal,
    playingTimeline,
    setPlayingTimeline,
    maxHour,
    activeModelMetadata,
    activeForecastRunId,
    compatibilityForecastGridId,
    historicalEvents,
    regionEvents,
    grid,
    handleCellClick,
    handleRegionChange,
    runForecast,
  };
}
