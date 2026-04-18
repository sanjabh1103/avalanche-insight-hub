import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const GRID_SIZE = 20;
const OPEN_METEO_BASE = 'https://api.open-meteo.com/v1/forecast';

const PROBLEM_TYPES = ['Storm Slab', 'Wind Slab', 'Persistent Slab', 'Deep Persistent Slab', 'Wet Loose', 'Wet Slab', 'Cornice Fall', 'Glide Avalanche'];

type RuntimeMode = 'full' | 'gpu_only' | 'sar_only' | 'edge_fallback';

interface WeatherData {
  snowfall: number[];
  precipitation: number[];
  windspeed: number[];
  winddirection: number[];
  temperature: number[];
  snow_depth: number[];
}

interface GridCell {
  row: number;
  col: number;
  lat: number;
  lng: number;
  latEnd: number;
  lngEnd: number;
  riskScore: number;
  hazard: number;
  exposure: number;
  vulnerability: number;
  problemType: string;
  rawScore: number;
  shapValues: Record<string, number>;
  snowpackMetrics?: Record<string, number | string>;
  inferenceBackend?: string;
}

interface ForecastMetadata {
  uncertaintyScore: number;
  uncertaintyReasons: string[];
  inputCompletenessScore: number;
  labelSupportScore: number;
  modelVersion: string;
  featureVersion: string;
  dataSnapshotId: string;
  calibrationProfile: string;
  thresholdProfile: string;
  runtimeMode: RuntimeMode;
  inferenceBackend: string;
  capabilitySummary: string;
  capabilitySnapshot: Record<string, unknown>;
  snowpackModelVersion: string;
  optimizationVersion: string;
  dataSources: string[];
  generationMode: 'legacy_fallback' | 'gpu_remote' | 'edge_remote';
  fallbackUsed: boolean;
  fallbackReason: string | null;
}

interface RuntimeCapabilities {
  mode: RuntimeMode;
  summary: string;
  sarEnabled: boolean;
  gpuEnabled: boolean;
  sarCredentialsPresent: boolean;
  gpuCredentialsPresent: boolean;
  modalWorkerUrl: string | null;
  modalWorkerToken: string | null;
}

interface SnowpackSummary {
  ram_hardness: number;
  shear_strength: number;
  settlement_rate: number;
  confidence: number;
  source: string;
}

function flagEnabled(name: string, defaultValue = true) {
  const raw = Deno.env.get(name);
  if (raw == null) return defaultValue;
  return !['0', 'false', 'off', 'no'].includes(raw.toLowerCase());
}

function detectRuntimeCapabilities(): RuntimeCapabilities {
  const modalWorkerUrl = Deno.env.get('MODAL_WORKER_URL') ?? null;
  const modalWorkerToken = Deno.env.get('MODAL_WORKER_TOKEN') ?? Deno.env.get('MODAL_API_TOKEN') ?? null;
  const gpuFeatureEnabled = flagEnabled('FEATURE_GPU_WORKER', true);
  const sarFeatureEnabled = flagEnabled('FEATURE_SENTINEL_SAR', true);
  const sarCredentialsPresent = Boolean(
    Deno.env.get('EARTHDATA_USERNAME') && Deno.env.get('EARTHDATA_PASSWORD')
      || Deno.env.get('ASF_API_TOKEN')
      || Deno.env.get('ASF_USERNAME') && Deno.env.get('ASF_PASSWORD'),
  );
  const gpuCredentialsPresent = Boolean(modalWorkerUrl && (modalWorkerToken || flagEnabled('MODAL_ALLOW_ANON', false)));
  const sarEnabled = sarFeatureEnabled && sarCredentialsPresent;
  const gpuEnabled = gpuFeatureEnabled && gpuCredentialsPresent;
  const mode: RuntimeMode = sarEnabled && gpuEnabled
    ? 'full'
    : gpuEnabled
      ? 'gpu_only'
      : sarEnabled
        ? 'sar_only'
        : 'edge_fallback';
  const summary = mode === 'full'
    ? 'Full SAR + GPU'
    : mode === 'gpu_only'
      ? 'GPU snowpack + Edge SAR fallback'
      : mode === 'sar_only'
        ? 'SAR enabled + Edge inference'
        : 'Edge-only fallback';

  return {
    mode,
    summary,
    sarEnabled,
    gpuEnabled,
    sarCredentialsPresent,
    gpuCredentialsPresent,
    modalWorkerUrl,
    modalWorkerToken,
  };
}

async function invokeModalWorker(
  capabilities: RuntimeCapabilities,
  endpoint: string,
  payload: Record<string, unknown>,
  timeoutMs = 8000,
) {
  if (!capabilities.gpuEnabled || !capabilities.modalWorkerUrl) {
    return null;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${capabilities.modalWorkerUrl.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(capabilities.modalWorkerToken ? { Authorization: `Bearer ${capabilities.modalWorkerToken}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${endpoint} failed (${response.status}): ${text}`);
    }
    return text ? JSON.parse(text) as Record<string, unknown> : {};
  } catch (error) {
    console.warn(`Modal worker ${endpoint} fallback:`, (error as Error).message);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function toNumber(value: unknown, fallback = 0) {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function extractFeatureWeights(summary: unknown, mode: RuntimeMode) {
  const fallback = {
    snowfall_24h: 0.24,
    wind_loading: 0.19,
    slope: 0.17,
    elevation: 0.11,
    temp_gradient: 0.1,
    snowpack: 0.08,
    ram_hardness: mode === 'edge_fallback' ? 0.04 : 0.05,
    shear_strength: mode === 'edge_fallback' ? 0.04 : 0.05,
    settlement_rate: mode === 'edge_fallback' ? 0.03 : 0.04,
    aspect_loading: 0.07,
  };

  const weights = summary && typeof summary === 'object' && !Array.isArray(summary)
    ? (summary as Record<string, unknown>)
    : {};
  const featureWeights = weights.feature_weights;
  if (!featureWeights || typeof featureWeights !== 'object' || Array.isArray(featureWeights)) {
    return fallback;
  }

  return {
    snowfall_24h: toNumber((featureWeights as Record<string, unknown>).snowfall_24h, fallback.snowfall_24h),
    wind_loading: toNumber((featureWeights as Record<string, unknown>).wind_loading, fallback.wind_loading),
    slope: toNumber((featureWeights as Record<string, unknown>).slope, fallback.slope),
    elevation: toNumber((featureWeights as Record<string, unknown>).elevation, fallback.elevation),
    temp_gradient: toNumber((featureWeights as Record<string, unknown>).temp_gradient, fallback.temp_gradient),
    snowpack: toNumber((featureWeights as Record<string, unknown>).snowpack, fallback.snowpack),
    ram_hardness: toNumber((featureWeights as Record<string, unknown>).ram_hardness, fallback.ram_hardness),
    shear_strength: toNumber((featureWeights as Record<string, unknown>).shear_strength, fallback.shear_strength),
    settlement_rate: toNumber((featureWeights as Record<string, unknown>).settlement_rate, fallback.settlement_rate),
    aspect_loading: toNumber((featureWeights as Record<string, unknown>).aspect_loading, fallback.aspect_loading),
  };
}

function buildSnowpackSummary(
  weather: WeatherData | null,
  hour: number,
  row: number,
  col: number,
  terrainElev: number,
  terrainSlope: number,
  terrainAspect: number,
  remoteSummary?: Partial<SnowpackSummary> | null,
): SnowpackSummary {
  const maxH = weather ? weather.snowfall.length - 1 : 71;
  const h = Math.min(hour, maxH);
  const snowfall = weather?.snowfall[h] ?? (2 + Math.sin(hour * 0.5 + row * 0.3) * 3);
  const temp = weather?.temperature[h] ?? (-5 + Math.sin(hour * 0.4) * 8);
  const wind = weather?.windspeed[h] ?? (15 + Math.cos(hour * 0.3 + col * 0.2) * 10);
  const rawSnowDepth = weather?.snow_depth[h];
  const snowDepth = Number.isFinite(rawSnowDepth) && rawSnowDepth != null && rawSnowDepth > 0 ? rawSnowDepth : (50 + row * 5 + Math.cos(col * 0.3) * 10);
  const snowfall24h = weather ? weather.snowfall.slice(Math.max(0, h - 23), h + 1).reduce((a, b) => a + b, 0) : snowfall * Math.min(h + 1, 24) * 0.3;
  const baseRam = Math.max(0.1, Math.min(1, (snowDepth * 0.015 + snowfall24h * 0.04 + terrainSlope * 0.005) / 5));
  const baseShear = Math.max(0.1, Math.min(1, (terrainElev * 0.00012 + wind * 0.015 + Math.max(0, -temp) * 0.02) / 2));
  const baseSettlement = Math.max(0.05, Math.min(1, (Math.max(0, temp + 8) * 0.04 + Math.abs(Math.sin(terrainAspect * Math.PI / 180)) * 0.2 + row * 0.01) / 2));
  const ram_hardness = Number(((baseRam + toNumber(remoteSummary?.ram_hardness, baseRam)) / 2).toFixed(4));
  const shear_strength = Number(((baseShear + toNumber(remoteSummary?.shear_strength, baseShear)) / 2).toFixed(4));
  const settlement_rate = Number(((baseSettlement + toNumber(remoteSummary?.settlement_rate, baseSettlement)) / 2).toFixed(4));
  const confidence = Number(Math.max(0.2, Math.min(1, toNumber(remoteSummary?.confidence, 0.58))).toFixed(4));
  const source = typeof remoteSummary?.source === 'string' ? remoteSummary.source : 'edge_proxy';
  return { ram_hardness, shear_strength, settlement_rate, confidence, source };
}

function normalizeHourly(values: unknown, fallback = 0): number[] {
  if (!Array.isArray(values)) return [];
  return values.slice(0, 72).map((value) => {
    const numeric = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  });
}

async function fetchWeather(lat: number, lng: number): Promise<WeatherData | null> {
  try {
    const url = `${OPEN_METEO_BASE}?latitude=${lat}&longitude=${lng}&hourly=precipitation,rain,snowfall,snow_depth,windspeed_10m,winddirection_10m,temperature_2m&timezone=auto&forecast_days=3`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    const h = data.hourly;
    return {
      snowfall: normalizeHourly(h.snowfall),
      precipitation: normalizeHourly(h.precipitation),
      windspeed: normalizeHourly(h.windspeed_10m),
      winddirection: normalizeHourly(h.winddirection_10m),
      temperature: normalizeHourly(h.temperature_2m),
      snow_depth: normalizeHourly(h.snow_depth),
    };
  } catch {
    return null;
  }
}

function computeRisk(
  weather: WeatherData | null,
  hour: number,
  row: number,
  col: number,
  terrainElev: number,
  terrainSlope: number,
  terrainAspect: number,
  weights: Record<string, number>,
  snowpackSummary: SnowpackSummary,
  conservativeMode: boolean,
) {
  const maxH = weather ? weather.snowfall.length - 1 : 71;
  const h = Math.min(hour, maxH);
  
  const snowfall = weather?.snowfall[h] ?? (2 + Math.sin(hour * 0.5 + row * 0.3) * 3);
  const wind = weather?.windspeed[h] ?? (15 + Math.cos(hour * 0.3 + col * 0.2) * 10);
  const temp = weather?.temperature[h] ?? (-5 + Math.sin(hour * 0.4) * 8);
  const precip = weather?.precipitation[h] ?? (snowfall * 0.8);
  const windDir = weather?.winddirection[h] ?? (180 + col * 10);
  // snow_depth may be null from Open-Meteo for some regions — use terrain-based fallback
  const rawSnowDepth = weather?.snow_depth[h];
  const snowDepth = Number.isFinite(rawSnowDepth) && rawSnowDepth != null && rawSnowDepth > 0 ? rawSnowDepth : (50 + row * 5 + Math.cos(col * 0.3) * 10);

  const snowfall24h = weather ? weather.snowfall.slice(Math.max(0, h - 23), h + 1).reduce((a, b) => a + b, 0) : snowfall * Math.min(h + 1, 24) * 0.3;
  const windLoading = wind * Math.max(0, Math.cos((windDir - terrainAspect) * Math.PI / 180));
  const tempGradient = h > 0 && weather ? (weather.temperature[h] - weather.temperature[Math.max(0, h - 3)]) : temp * 0.1;
  const snowpackProxy = weather ? Math.max(0, snowDepth * 0.02 + snowfall24h * 0.3 - Math.max(0, temp) * 0.2) : Math.max(0, snowfall24h * 0.4 - Math.max(0, temp) * 0.3);

  const features = {
    snowfall_24h: Math.min(1, snowfall24h / 40),
    wind_loading: Math.min(1, windLoading / 50),
    slope: Math.min(1, terrainSlope / 55),
    elevation: Math.min(1, terrainElev / 4500),
    temp_gradient: Math.min(1, Math.max(0, (tempGradient + 10) / 20)),
    snowpack: Math.min(1, snowpackProxy / 20),
    ram_hardness: Math.min(1, snowpackSummary.ram_hardness),
    shear_strength: Math.min(1, snowpackSummary.shear_strength),
    settlement_rate: Math.min(1, snowpackSummary.settlement_rate),
    aspect_loading: Math.abs(Math.sin(terrainAspect * Math.PI / 180)) * 0.5 + 0.25,
  };

  let rawScore = 0;
  const shapValues: Record<string, number> = {};
  for (const [key, weight] of Object.entries(weights)) {
    const val = features[key as keyof typeof features] * weight;
    rawScore += val;
    shapValues[key] = Number(val.toFixed(4));
  }

  rawScore = Math.max(0, Math.min(1, rawScore * (conservativeMode ? 1.45 : 1.75)));
  const riskScore = Math.max(1, Math.min(5, Math.round(rawScore * 5)));
  
  const hazard = 0.2 + rawScore * 0.7;
  const exposure = 0.3 + features.elevation * 0.5;
  const vulnerability = 0.1 + features.aspect_loading * 0.6;
  const problemIdx = Math.min(PROBLEM_TYPES.length - 1, Math.floor(rawScore * PROBLEM_TYPES.length));

  return {
    riskScore,
    hazard,
    exposure,
    vulnerability,
    rawScore,
    shapValues,
    problemType: PROBLEM_TYPES[problemIdx],
    snowpackMetrics: {
      ram_hardness: snowpackSummary.ram_hardness,
      shear_strength: snowpackSummary.shear_strength,
      settlement_rate: snowpackSummary.settlement_rate,
      confidence: snowpackSummary.confidence,
      source: snowpackSummary.source,
    },
  };
}

function generateHourlyGrids(
  bbox: number[],
  weather: WeatherData | null,
  totalHours = 25,
  weights: Record<string, number>,
  conservativeMode: boolean,
  remoteSnowpackSummary?: Partial<SnowpackSummary> | null,
  inferenceBackend = 'edge_fallback',
) {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const latStep = (latMax - latMin) / GRID_SIZE;
  const lngStep = (lngMax - lngMin) / GRID_SIZE;
  
  const hourlyGrids: GridCell[][] = [];
  let snowpackAccumulator = {
    ram_hardness: 0,
    shear_strength: 0,
    settlement_rate: 0,
    confidence: 0,
    count: 0,
  };
  
  for (let hour = 0; hour < totalHours; hour++) {
    const cells: GridCell[] = [];
    for (let r = 0; r < GRID_SIZE; r++) {
      for (let c = 0; c < GRID_SIZE; c++) {
        const lat = latMin + r * latStep;
        const lng = lngMin + c * lngStep;
        
        const elevation = 2000 + (r / GRID_SIZE) * 2500 + Math.sin(c * 0.5) * 300;
        const slope = 20 + (r / GRID_SIZE) * 25 + Math.cos(c * 0.3) * 10;
        const aspect = (c / GRID_SIZE) * 360;
        const snowpackSummary = buildSnowpackSummary(weather, hour, r, c, elevation, slope, aspect, remoteSnowpackSummary);
        
        const result = computeRisk(weather, hour, r, c, elevation, slope, aspect, weights, snowpackSummary, conservativeMode);
        if (hour === 0) {
          snowpackAccumulator = {
            ram_hardness: snowpackAccumulator.ram_hardness + snowpackSummary.ram_hardness,
            shear_strength: snowpackAccumulator.shear_strength + snowpackSummary.shear_strength,
            settlement_rate: snowpackAccumulator.settlement_rate + snowpackSummary.settlement_rate,
            confidence: snowpackAccumulator.confidence + snowpackSummary.confidence,
            count: snowpackAccumulator.count + 1,
          };
        }
        
        cells.push({
          row: r, col: c, lat, lng,
          latEnd: lat + latStep, lngEnd: lng + lngStep,
          ...result,
          inferenceBackend,
        });
      }
    }
    hourlyGrids.push(cells);
  }
  
  const count = Math.max(1, snowpackAccumulator.count);
  return {
    hourlyGrids,
    snowpackMetrics: {
      ram_hardness: Number((snowpackAccumulator.ram_hardness / count).toFixed(4)),
      shear_strength: Number((snowpackAccumulator.shear_strength / count).toFixed(4)),
      settlement_rate: Number((snowpackAccumulator.settlement_rate / count).toFixed(4)),
      confidence: Number((snowpackAccumulator.confidence / count).toFixed(4)),
      source: typeof remoteSnowpackSummary?.source === 'string' ? remoteSnowpackSummary.source : 'edge_proxy',
    },
  };
}

function buildForecastMetadata(
  weather: WeatherData | null,
  hours: number,
  modelVersion: string,
  capabilities: RuntimeCapabilities,
  inferenceBackend: string,
  snowpackSource: string,
  optimizationVersion: string,
  snowpackModelVersion: string,
  fallbackUsed: boolean,
  fallbackReason: string | null,
): ForecastMetadata {
  const uncertaintyReasons: string[] = [];
  let inputCompletenessScore = 1;

  if (!weather) {
    uncertaintyReasons.push('weather_fallback_simulation');
    inputCompletenessScore -= 0.45;
  } else {
    const snowDepthValues = weather.snow_depth.filter((value) => Number.isFinite(value) && value > 0);
    if (snowDepthValues.length === 0) {
      uncertaintyReasons.push('snow_depth_missing');
      inputCompletenessScore -= 0.15;
    }

    const sparseSnowfall = weather.snowfall.filter((value) => Number.isFinite(value)).length < Math.min(24, hours);
    if (sparseSnowfall) {
      uncertaintyReasons.push('short_weather_window');
      inputCompletenessScore -= 0.1;
    }
  }

  if (hours > 24) {
    uncertaintyReasons.push('extended_lead_time');
    inputCompletenessScore -= 0.1;
  }

  if (!capabilities.gpuEnabled) {
    uncertaintyReasons.push('gpu_unavailable');
    inputCompletenessScore -= 0.05;
  }

  if (!capabilities.sarEnabled) {
    uncertaintyReasons.push('sar_unavailable');
    inputCompletenessScore -= 0.05;
  }

  const normalizedCompleteness = Math.max(0.1, Math.min(1, Number(inputCompletenessScore.toFixed(3))));
  const uncertaintyScore = Number((1 - normalizedCompleteness).toFixed(3));
  const featureVersion = capabilities.gpuEnabled ? 'dual-mode-himstrat-v1' : 'edge-weather-terrain-v2';
  const dataSources = [
    weather ? 'open-meteo' : 'simulation',
    snowpackSource,
    inferenceBackend === 'gpu' ? 'modal' : 'edge',
    fallbackUsed ? 'legacy_hourly_grids' : 'async_batch',
  ];

  return {
    uncertaintyScore,
    uncertaintyReasons,
    inputCompletenessScore: normalizedCompleteness,
    labelSupportScore: capabilities.sarEnabled ? 0.25 : 0.1,
    modelVersion,
    featureVersion,
    dataSnapshotId: `${new Date().toISOString().slice(0, 13)}:00Z`,
    calibrationProfile: 'global-default-v1',
    thresholdProfile: 'heuristic-risk-bands-v1',
    runtimeMode: capabilities.mode,
    inferenceBackend,
    capabilitySummary: capabilities.summary,
    capabilitySnapshot: {
      mode: capabilities.mode,
      summary: capabilities.summary,
      sar_enabled: capabilities.sarEnabled,
      gpu_enabled: capabilities.gpuEnabled,
      sar_credentials_present: capabilities.sarCredentialsPresent,
      gpu_credentials_present: capabilities.gpuCredentialsPresent,
    },
    snowpackModelVersion,
    optimizationVersion,
    dataSources,
    generationMode: fallbackUsed ? 'legacy_fallback' : (inferenceBackend === 'gpu' ? 'gpu_remote' : 'edge_remote'),
    fallbackUsed,
    fallbackReason,
  };
}

async function invokeEdgeFunction(functionName: string, body: Record<string, unknown>) {
  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const anonKey = Deno.env.get('SUPABASE_ANON_KEY')!;
  const response = await fetch(`${supabaseUrl}/functions/v1/${functionName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${anonKey}`,
      apikey: anonKey,
    },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${functionName} failed (${response.status}): ${text}`);
  }

  return text ? JSON.parse(text) as Record<string, unknown> : {};
}

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  let jobId: string | null = null;

  try {
    const { bbox, timeOffset = 0, regionName, hours = 24, hazard_type: hazardType = 'avalanche' } = await req.json();
    const capabilities = detectRuntimeCapabilities();

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    const { data: modelStatus } = await supabase
      .from('model_status')
      .select('id, version, optimization_version, optimization_summary, threshold_profile_version, calibration_profile_version')
      .eq('hazard_type', hazardType)
      .limit(1)
      .single();

    // Create job
    const { data: job, error: jobErr } = await supabase
      .from('compute_jobs')
      .insert({
        type: 'forecast',
        status: 'running',
        bbox,
        time_offset: timeOffset,
        hazard_type: hazardType,
        payload: {
          region_name: regionName || 'Unknown',
          requested_hours: hours,
          runtime_mode: capabilities.mode,
          capability_summary: capabilities.summary,
          fallback_used: true,
          fallback_reason: 'legacy_hourly_grid_generator',
          generation_mode: 'legacy_fallback',
        },
      })
      .select('id')
      .single();
    if (jobErr) throw jobErr;
    jobId = job.id;

    // Fetch real weather for bbox center
    const centerLat = (bbox[0] + bbox[2]) / 2;
    const centerLng = (bbox[1] + bbox[3]) / 2;
    const weather = await fetchWeather(centerLat, centerLng);
    const weatherSource = weather ? 'open-meteo' : 'simulation';
    const optimizationVersion = typeof modelStatus?.optimization_version === 'string' && modelStatus.optimization_version
      ? modelStatus.optimization_version
      : capabilities.gpuEnabled
        ? 'gpu-optimization-pending'
        : 'edge-lite-v1';
    const featureWeights = extractFeatureWeights(modelStatus?.optimization_summary, capabilities.mode);
    const remoteSnowpack = await invokeModalWorker(capabilities, 'simulate-snowpack', {
      hazard_type: hazardType,
      bbox,
      hours,
      region_name: regionName || 'Unknown',
      weather,
      runtime_mode: capabilities.mode,
      optimization_version: optimizationVersion,
    }, 6000);
    const remoteSnowpackSummary = remoteSnowpack?.summary && typeof remoteSnowpack.summary === 'object' && !Array.isArray(remoteSnowpack.summary)
      ? remoteSnowpack.summary as Partial<SnowpackSummary>
      : null;
    const localForecast = generateHourlyGrids(
      bbox,
      weather,
      hours + 1,
      featureWeights,
      capabilities.mode === 'edge_fallback',
      remoteSnowpackSummary,
      'edge_fallback',
    );
    let hourlyGrids = localForecast.hourlyGrids;
    let inferenceBackend = 'edge_fallback';
    let fallbackUsed = true;
    let fallbackReason: string | null = 'legacy_hourly_grid_generator';
    let snowpackMetrics = {
      ...localForecast.snowpackMetrics,
      source: remoteSnowpackSummary?.source || localForecast.snowpackMetrics.source,
    };
    let modelVersion = modelStatus?.version || 'v1.0.0-sim';
    let snowpackModelVersion = typeof remoteSnowpack?.model_version === 'string' && remoteSnowpack.model_version
      ? remoteSnowpack.model_version
      : capabilities.gpuEnabled
        ? 'him-strat-proxy-v1'
        : 'edge-him-strat-lite-v1';

    const remoteInference = await invokeModalWorker(capabilities, 'infer', {
      hazard_type: hazardType,
      bbox,
      hours,
      region_name: regionName || 'Unknown',
      weather,
      runtime_mode: capabilities.mode,
      model_version: modelVersion,
      optimization_version: optimizationVersion,
      snowpack_metrics: snowpackMetrics,
      fallback_hourly_grids: localForecast.hourlyGrids,
    }, 9000);
    const remoteHourlyGrids = remoteInference?.hourly_grids;
    if (Array.isArray(remoteHourlyGrids) && remoteHourlyGrids.every((hourGrid) => Array.isArray(hourGrid))) {
      hourlyGrids = remoteHourlyGrids as GridCell[][];
      inferenceBackend = 'gpu';
      fallbackUsed = false;
      fallbackReason = null;
      modelVersion = typeof remoteInference?.model_version === 'string' && remoteInference.model_version
        ? remoteInference.model_version
        : modelVersion;
      snowpackModelVersion = typeof remoteInference?.snowpack_model_version === 'string' && remoteInference.snowpack_model_version
        ? remoteInference.snowpack_model_version
        : snowpackModelVersion;
      if (remoteInference?.snowpack_metrics && typeof remoteInference.snowpack_metrics === 'object' && !Array.isArray(remoteInference.snowpack_metrics)) {
        snowpackMetrics = {
          ram_hardness: toNumber((remoteInference.snowpack_metrics as Record<string, unknown>).ram_hardness, snowpackMetrics.ram_hardness),
          shear_strength: toNumber((remoteInference.snowpack_metrics as Record<string, unknown>).shear_strength, snowpackMetrics.shear_strength),
          settlement_rate: toNumber((remoteInference.snowpack_metrics as Record<string, unknown>).settlement_rate, snowpackMetrics.settlement_rate),
          confidence: toNumber((remoteInference.snowpack_metrics as Record<string, unknown>).confidence, snowpackMetrics.confidence),
          source: typeof (remoteInference.snowpack_metrics as Record<string, unknown>).source === 'string'
            ? String((remoteInference.snowpack_metrics as Record<string, unknown>).source)
            : 'modal',
        };
      } else {
        snowpackMetrics = { ...snowpackMetrics, source: 'modal' };
      }
    }

    const currentCells = hourlyGrids[Math.min(timeOffset, hourlyGrids.length - 1)];
    const avgRisk = currentCells.reduce((s: number, c: GridCell) => s + c.riskScore, 0) / currentCells.length;
    const metadata = buildForecastMetadata(
      weather,
      hours,
      modelVersion,
      capabilities,
      inferenceBackend,
      snowpackMetrics.source,
      optimizationVersion,
      snowpackModelVersion,
      fallbackUsed,
      fallbackReason,
    );

    // Store forecast with hourly grids
    const { data: forecast } = await supabase.from('forecasts').insert({
      job_id: job.id,
      hazard_type: hazardType,
      bbox,
      risk_score: avgRisk,
      hazard: currentCells[0]?.hazard ?? 0,
      exposure: currentCells[0]?.exposure ?? 0,
      vulnerability: currentCells[0]?.vulnerability ?? 0,
      grid_data: currentCells,
      shap_values: currentCells[0]?.shapValues ?? {},
      hourly_grids: hourlyGrids,
      uncertainty_score: metadata.uncertaintyScore,
      uncertainty_reasons: metadata.uncertaintyReasons,
      input_completeness_score: metadata.inputCompletenessScore,
      label_support_score: metadata.labelSupportScore,
      model_version: metadata.modelVersion,
      feature_version: metadata.featureVersion,
      data_snapshot_id: metadata.dataSnapshotId,
      calibration_profile_version: metadata.calibrationProfile,
      threshold_profile_version: metadata.thresholdProfile,
      runtime_mode: metadata.runtimeMode,
      inference_backend: metadata.inferenceBackend,
      capability_snapshot: metadata.capabilitySnapshot,
      snowpack_metrics: snowpackMetrics,
      optimization_summary: {
        optimization_version: optimizationVersion,
        feature_weights: featureWeights,
      },
    }).select('id').single();

    // Update model status with last inference and data freshness
    const { data: ms } = await supabase
      .from('model_status')
      .select('id')
      .eq('hazard_type', hazardType)
      .limit(1)
      .single();
    if (ms?.id) {
      await supabase.from('model_status').update({
        last_inference: new Date().toISOString(),
        data_freshness_hours: weather ? 0 : 999,
        feature_version: metadata.featureVersion,
        calibration_profile_version: metadata.calibrationProfile,
        threshold_profile_version: metadata.thresholdProfile,
        inference_backend: metadata.inferenceBackend,
        capability_summary: metadata.capabilitySummary,
        capabilities: metadata.capabilitySnapshot,
        snowpack_model_version: metadata.snowpackModelVersion,
        optimization_version: metadata.optimizationVersion,
        snowpack_metrics: snowpackMetrics,
        optimization_summary: {
          optimization_version: optimizationVersion,
          feature_weights: featureWeights,
          runtime_mode: metadata.runtimeMode,
        },
        sar_pipeline_version: capabilities.sarEnabled ? 'sentinel1-change-detect-v1' : 'edge-sar-fallback-v1',
      }).eq('id', ms.id);
    }

    // Log analytics
    await supabase.from('forecast_analytics').insert({
      hazard_type: hazardType,
      region_name: regionName || 'Unknown',
      bbox,
      weather_source: weatherSource,
      avg_risk: avgRisk,
      cell_count: currentCells.length,
      avg_uncertainty: metadata.uncertaintyScore,
      model_version: metadata.modelVersion,
      calibration_profile_version: metadata.calibrationProfile,
      runtime_mode: metadata.runtimeMode,
      capability_snapshot: metadata.capabilitySnapshot,
    });

    const downstreamRefreshes = hazardType === 'avalanche'
      ? [
          invokeEdgeFunction('ingest-snow-cover', {
            hazard_type: hazardType,
            region_name: regionName || 'global',
            bbox,
            date: new Date().toISOString().split('T')[0],
          }),
          invokeEdgeFunction('recent-activity-refresh', {
            hazard_type: hazardType,
            region_name: regionName || 'global',
            window_days: 7,
            materialize_cells: false,
          }),
        ]
      : [];

    if (downstreamRefreshes.length > 0) {
      const settled = await Promise.allSettled(downstreamRefreshes);
      const failures = settled.filter((item) => item.status === 'rejected') as PromiseRejectedResult[];
      if (failures.length > 0) {
        console.warn('Downstream refresh failures:', failures.map((failure) => failure.reason));
      }
    }

    // Mark complete
    await supabase
      .from('compute_jobs')
      .update({
        status: 'completed',
        result: {
          avgRisk,
          cellCount: currentCells.length,
          weatherSource,
          fallbackUsed,
          fallbackReason,
          generationMode: metadata.generationMode,
          uncertaintyScore: metadata.uncertaintyScore,
          modelVersion: metadata.modelVersion,
          calibrationProfile: metadata.calibrationProfile,
          runtimeMode: metadata.runtimeMode,
          inferenceBackend: metadata.inferenceBackend,
          capabilitySummary: metadata.capabilitySummary,
          optimizationVersion: metadata.optimizationVersion,
          snowpackMetrics,
        },
      })
      .eq('id', job.id);

    // Extract weather summary for SHAP display (real values for all regions)
    const validSnowDepth = weather?.snow_depth.filter(v => Number.isFinite(v) && v > 0) || [];
    const weatherSummary = weather ? {
      snowfall_24h: weather.snowfall.slice(0, 24).reduce((a, b) => a + b, 0).toFixed(1),
      wind_speed: (weather.windspeed.slice(0, 24).reduce((a, b) => a + b, 0) / 24).toFixed(1),
      temperature: (weather.temperature.slice(0, 24).reduce((a, b) => a + b, 0) / 24).toFixed(1),
      precipitation: weather.precipitation.slice(0, 24).reduce((a, b) => a + b, 0).toFixed(1),
      snow_depth: validSnowDepth.length > 0
        ? (validSnowDepth.reduce((a, b) => a + b, 0) / validSnowDepth.length).toFixed(1)
        : '0',
    } : null;

    return new Response(JSON.stringify({ 
      jobId: job.id, 
      forecastId: forecast?.id,
      avgRisk,
      weatherSource,
      hours: hourlyGrids.length,
      weatherSummary,
      region: { lat: centerLat, lng: centerLng },
      hazard_type: hazardType,
      model_version: metadata.modelVersion,
      uncertainty_score: metadata.uncertaintyScore,
      data_sources: metadata.dataSources,
      fallback_used: fallbackUsed,
      fallback_reason: fallbackReason,
      generation_mode: metadata.generationMode,
      calibration_profile: metadata.calibrationProfile,
      mode: metadata.runtimeMode,
      capability_summary: metadata.capabilitySummary,
      inference_backend: metadata.inferenceBackend,
      snowpack_metrics: snowpackMetrics,
      optimization_version: metadata.optimizationVersion,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    if (jobId) {
      try {
        const supabase = createClient(
          Deno.env.get('SUPABASE_URL')!,
          Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
        );
        await supabase
          .from('compute_jobs')
          .update({ status: 'failed', error: (err as Error).message })
          .eq('id', jobId);
      } catch {
      }
    }
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
