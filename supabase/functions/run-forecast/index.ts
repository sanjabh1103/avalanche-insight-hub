import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const GRID_SIZE = 20;

function generateGrid(bbox: number[], timeOffset: number) {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const latStep = (latMax - latMin) / GRID_SIZE;
  const lngStep = (lngMax - lngMin) / GRID_SIZE;
  const cells: any[] = [];

  const stormCenterLat = latMin + (latMax - latMin) * (0.4 + 0.15 * Math.sin(timeOffset * 0.3));
  const stormCenterLng = lngMin + (lngMax - lngMin) * (0.5 + 0.2 * Math.cos(timeOffset * 0.2));
  const stormRadius = 0.8 + 0.3 * Math.sin(timeOffset * 0.15);

  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      const lat = latMin + r * latStep;
      const lng = lngMin + c * lngStep;
      const centerLat = lat + latStep / 2;
      const centerLng = lng + lngStep / 2;
      const dist = Math.sqrt((centerLat - stormCenterLat) ** 2 + (centerLng - stormCenterLng) ** 2);
      const elevFactor = 0.3 + 0.7 * (r / GRID_SIZE);
      const aspectFactor = 0.5 + 0.5 * Math.sin((c / GRID_SIZE) * Math.PI * 2);
      const stormInfluence = Math.max(0, 1 - dist / stormRadius);
      const baseRisk = stormInfluence * 0.6 + elevFactor * 0.25 + aspectFactor * 0.15;
      const timeVariation = 0.1 * Math.sin(timeOffset * 0.5 + r * 0.3 + c * 0.2);
      const rawRisk = Math.max(0, Math.min(1, baseRisk + timeVariation));
      const riskScore = Math.max(1, Math.min(5, Math.round(rawRisk * 5)));

      cells.push({
        row: r, col: c, lat, lng,
        latEnd: lat + latStep, lngEnd: lng + lngStep,
        riskScore,
        hazard: 0.2 + rawRisk * 0.7,
        exposure: 0.3 + elevFactor * 0.5,
        vulnerability: 0.1 + aspectFactor * 0.6,
        shapValues: {
          snowfall_24h: 0.15 + stormInfluence * 0.3,
          wind_speed: 0.1 + aspectFactor * 0.25,
          temperature: 0.05 + timeVariation * 0.2,
          elevation: elevFactor * 0.2,
          slope_angle: 0.12 + rawRisk * 0.1,
        },
      });
    }
  }
  return cells;
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

    const cells = generateGrid(bbox, timeOffset);
    const avgRisk = cells.reduce((s: number, c: any) => s + c.riskScore, 0) / cells.length;

    // Store forecast
    await supabase.from('forecasts').insert({
      job_id: job.id,
      bbox,
      risk_score: avgRisk,
      hazard: cells[0]?.hazard ?? 0,
      exposure: cells[0]?.exposure ?? 0,
      vulnerability: cells[0]?.vulnerability ?? 0,
      grid_data: cells,
      shap_values: cells[0]?.shapValues ?? {},
    });

    // Mark complete
    await supabase
      .from('compute_jobs')
      .update({ status: 'completed', result: { avgRisk, cellCount: cells.length } })
      .eq('id', job.id);

    return new Response(JSON.stringify({ jobId: job.id, avgRisk }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
