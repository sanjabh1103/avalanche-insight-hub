import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const GRID_SIZE = 20;
const OPEN_METEO_BASE = 'https://api.open-meteo.com/v1/forecast';

const PROBLEM_TYPES = ['Storm Slab', 'Wind Slab', 'Persistent Slab', 'Deep Persistent Slab', 'Wet Loose', 'Wet Slab', 'Cornice Fall', 'Glide Avalanche'];

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

function computeRisk(weather: WeatherData | null, hour: number, row: number, col: number, terrainElev: number, terrainSlope: number, terrainAspect: number) {
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
  const snowDepthAvg = weather ? weather.snow_depth.filter(v => v != null && v > 0).reduce((a, b) => a + b, 0) / Math.max(1, weather.snow_depth.filter(v => v != null && v > 0).length) : snowDepth;
  const snowpackProxy = weather ? Math.max(0, snowDepth * 0.02 + snowfall24h * 0.3 - Math.max(0, temp) * 0.2) : Math.max(0, snowfall24h * 0.4 - Math.max(0, temp) * 0.3);

  const weights = {
    snowfall_24h: 0.25,
    wind_loading: 0.20,
    slope: 0.18,
    elevation: 0.12,
    temp_gradient: 0.10,
    snowpack: 0.08,
    aspect_loading: 0.07,
  };

  const features = {
    snowfall_24h: Math.min(1, snowfall24h / 40),
    wind_loading: Math.min(1, windLoading / 50),
    slope: Math.min(1, terrainSlope / 55),
    elevation: Math.min(1, terrainElev / 4500),
    temp_gradient: Math.min(1, Math.max(0, (tempGradient + 10) / 20)),
    snowpack: Math.min(1, snowpackProxy / 20),
    aspect_loading: Math.abs(Math.sin(terrainAspect * Math.PI / 180)) * 0.5 + 0.25,
  };

  let rawScore = 0;
  const shapValues: Record<string, number> = {};
  for (const [key, weight] of Object.entries(weights)) {
    const val = features[key as keyof typeof features] * weight;
    rawScore += val;
    shapValues[key] = Number(val.toFixed(4));
  }

  rawScore = Math.max(0, Math.min(1, rawScore * 1.8));
  const riskScore = Math.max(1, Math.min(5, Math.round(rawScore * 5)));
  
  const hazard = 0.2 + rawScore * 0.7;
  const exposure = 0.3 + features.elevation * 0.5;
  const vulnerability = 0.1 + features.aspect_loading * 0.6;
  const problemIdx = Math.min(PROBLEM_TYPES.length - 1, Math.floor(rawScore * PROBLEM_TYPES.length));

  return { riskScore, hazard, exposure, vulnerability, rawScore, shapValues, problemType: PROBLEM_TYPES[problemIdx] };
}

function generateHourlyGrids(bbox: number[], weather: WeatherData | null, totalHours = 25) {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const latStep = (latMax - latMin) / GRID_SIZE;
  const lngStep = (lngMax - lngMin) / GRID_SIZE;
  
  const hourlyGrids: GridCell[][] = [];
  
  for (let hour = 0; hour < totalHours; hour++) {
    const cells: GridCell[] = [];
    for (let r = 0; r < GRID_SIZE; r++) {
      for (let c = 0; c < GRID_SIZE; c++) {
        const lat = latMin + r * latStep;
        const lng = lngMin + c * lngStep;
        
        const elevation = 2000 + (r / GRID_SIZE) * 2500 + Math.sin(c * 0.5) * 300;
        const slope = 20 + (r / GRID_SIZE) * 25 + Math.cos(c * 0.3) * 10;
        const aspect = (c / GRID_SIZE) * 360;
        
        const result = computeRisk(weather, hour, r, c, elevation, slope, aspect);
        
        cells.push({
          row: r, col: c, lat, lng,
          latEnd: lat + latStep, lngEnd: lng + lngStep,
          ...result,
        });
      }
    }
    hourlyGrids.push(cells);
  }
  
  return hourlyGrids;
}

function buildForecastMetadata(weather: WeatherData | null, hours: number, modelVersion: string): ForecastMetadata {
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

  const normalizedCompleteness = Math.max(0.1, Math.min(1, Number(inputCompletenessScore.toFixed(3))));
  const uncertaintyScore = Number((1 - normalizedCompleteness).toFixed(3));

  return {
    uncertaintyScore,
    uncertaintyReasons,
    inputCompletenessScore: normalizedCompleteness,
    labelSupportScore: 0,
    modelVersion,
    featureVersion: 'heuristic-weather-v1',
    dataSnapshotId: `${new Date().toISOString().slice(0, 13)}:00Z`,
    calibrationProfile: 'global-default-v1',
    thresholdProfile: 'heuristic-risk-bands-v1',
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

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { bbox, timeOffset = 0, regionName, hours = 24, hazard_type: hazardType = 'avalanche' } = await req.json();

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    const { data: modelStatus } = await supabase
      .from('model_status')
      .select('id, version')
      .eq('hazard_type', hazardType)
      .limit(1)
      .single();

    // Create job
    const { data: job, error: jobErr } = await supabase
      .from('compute_jobs')
      .insert({ type: 'forecast', status: 'running', bbox, time_offset: timeOffset, hazard_type: hazardType })
      .select('id')
      .single();
    if (jobErr) throw jobErr;

    // Fetch real weather for bbox center
    const centerLat = (bbox[0] + bbox[2]) / 2;
    const centerLng = (bbox[1] + bbox[3]) / 2;
    const weather = await fetchWeather(centerLat, centerLng);
    
    const hourlyGrids = generateHourlyGrids(bbox, weather, hours + 1);
    const currentCells = hourlyGrids[Math.min(timeOffset, hourlyGrids.length - 1)];
    const avgRisk = currentCells.reduce((s: number, c: GridCell) => s + c.riskScore, 0) / currentCells.length;
    const weatherSource = weather ? 'open-meteo' : 'simulation';
    const metadata = buildForecastMetadata(weather, hours, modelStatus?.version || 'v1.0.0-sim');

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
          uncertaintyScore: metadata.uncertaintyScore,
          modelVersion: metadata.modelVersion,
          calibrationProfile: metadata.calibrationProfile,
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
      data_sources: [weatherSource],
      calibration_profile: metadata.calibrationProfile,
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
