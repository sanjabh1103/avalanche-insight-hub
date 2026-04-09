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
}

async function fetchWeather(lat: number, lng: number): Promise<WeatherData | null> {
  try {
    const url = `${OPEN_METEO_BASE}?latitude=${lat}&longitude=${lng}&hourly=precipitation,rain,snowfall,windspeed_10m,winddirection_10m,temperature_2m&timezone=auto&forecast_days=2`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    const h = data.hourly;
    return {
      snowfall: h.snowfall?.slice(0, 24) || [],
      precipitation: h.precipitation?.slice(0, 24) || [],
      windspeed: h.windspeed_10m?.slice(0, 24) || [],
      winddirection: h.winddirection_10m?.slice(0, 24) || [],
      temperature: h.temperature_2m?.slice(0, 24) || [],
    };
  } catch {
    return null;
  }
}

function computeRisk(weather: WeatherData | null, hour: number, row: number, col: number, terrainElev: number, terrainSlope: number, terrainAspect: number) {
  const h = Math.min(hour, 23);
  
  // Weather features (real or proxy)
  const snowfall = weather?.snowfall[h] ?? (2 + Math.sin(hour * 0.5 + row * 0.3) * 3);
  const wind = weather?.windspeed[h] ?? (15 + Math.cos(hour * 0.3 + col * 0.2) * 10);
  const temp = weather?.temperature[h] ?? (-5 + Math.sin(hour * 0.4) * 8);
  const precip = weather?.precipitation[h] ?? (snowfall * 0.8);
  const windDir = weather?.winddirection[h] ?? (180 + col * 10);

  // Avalanche-specific features
  const snowfall24h = weather ? weather.snowfall.slice(0, h + 1).reduce((a, b) => a + b, 0) : snowfall * (h + 1) * 0.3;
  const windLoading = wind * Math.max(0, Math.cos((windDir - terrainAspect) * Math.PI / 180));
  const tempGradient = h > 0 && weather ? (weather.temperature[h] - weather.temperature[Math.max(0, h - 3)]) : temp * 0.1;
  const snowpackProxy = Math.max(0, snowfall24h * 0.4 - Math.max(0, temp) * 0.3);

  // XGBoost-style weighted ensemble
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

function generateHourlyGrids(bbox: number[], weather: WeatherData | null) {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const latStep = (latMax - latMin) / GRID_SIZE;
  const lngStep = (lngMax - lngMin) / GRID_SIZE;
  
  const hourlyGrids: any[][] = [];
  
  for (let hour = 0; hour <= 24; hour++) {
    const cells: any[] = [];
    for (let r = 0; r < GRID_SIZE; r++) {
      for (let c = 0; c < GRID_SIZE; c++) {
        const lat = latMin + r * latStep;
        const lng = lngMin + c * lngStep;
        
        // Terrain proxies
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

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { bbox, timeOffset = 0 } = await req.json();
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
    );

    // Create job
    const { data: job, error: jobErr } = await supabase
      .from('compute_jobs')
      .insert({ type: 'forecast', status: 'running', bbox, time_offset: timeOffset })
      .select('id')
      .single();
    if (jobErr) throw jobErr;

    // Fetch real weather for bbox center
    const centerLat = (bbox[0] + bbox[2]) / 2;
    const centerLng = (bbox[1] + bbox[3]) / 2;
    const weather = await fetchWeather(centerLat, centerLng);
    
    const hourlyGrids = generateHourlyGrids(bbox, weather);
    const currentCells = hourlyGrids[Math.min(timeOffset, 24)];
    const avgRisk = currentCells.reduce((s: number, c: any) => s + c.riskScore, 0) / currentCells.length;

    // Store forecast with hourly grids
    const { data: forecast } = await supabase.from('forecasts').insert({
      job_id: job.id,
      bbox,
      risk_score: avgRisk,
      hazard: currentCells[0]?.hazard ?? 0,
      exposure: currentCells[0]?.exposure ?? 0,
      vulnerability: currentCells[0]?.vulnerability ?? 0,
      grid_data: currentCells,
      shap_values: currentCells[0]?.shapValues ?? {},
      hourly_grids: hourlyGrids,
    }).select('id').single();

    // Update model status
    await supabase.from('model_status').update({
      last_inference: new Date().toISOString(),
      data_freshness_hours: weather ? 0 : 999,
    }).not('id', 'is', null);

    // Mark complete
    await supabase
      .from('compute_jobs')
      .update({ status: 'completed', result: { avgRisk, cellCount: currentCells.length, weatherSource: weather ? 'open-meteo' : 'simulation' } })
      .eq('id', job.id);

    return new Response(JSON.stringify({ 
      jobId: job.id, 
      forecastId: forecast?.id,
      avgRisk,
      weatherSource: weather ? 'open-meteo' : 'simulation',
      hours: hourlyGrids.length,
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
