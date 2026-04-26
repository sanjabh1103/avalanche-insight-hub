import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

type ForecastRequest = {
  regionName?: string;
  regionKey?: string;
};

serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
    );

    const body = await req.json().catch(() => ({})) as ForecastRequest;
    const regionName = typeof body.regionName === "string" && body.regionName.trim() ? body.regionName.trim() : null;
    const regionKey = typeof body.regionKey === "string" && body.regionKey.trim() ? body.regionKey.trim() : null;
    if (!regionName && !regionKey) {
      return new Response(JSON.stringify({ error: "regionName or regionKey is required" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const today = new Date().toISOString().slice(0, 10);
    let query = supabase
      .from("forecast_grids")
      .select("id, region_name, region_key, forecast_date, horizon_hours, weather_summary, model_metadata, status, created_at")
      .eq("hazard_type", "avalanche")
      .eq("forecast_date", today)
      .order("created_at", { ascending: false })
      .limit(1);

    if (regionKey) query = query.eq("region_key", regionKey);
    if (regionName) query = query.eq("region_name", regionName);

    const { data: freshGrid, error: freshError } = await query.maybeSingle();
    if (freshError) throw freshError;

    if (freshGrid) {
      return new Response(JSON.stringify({
        ok: true,
        stale: false,
        status: "ready",
        mode: "batch_only",
        source: "forecast_grids",
        forecastId: freshGrid.id,
        regionName: freshGrid.region_name,
        regionKey: freshGrid.region_key,
        forecastDate: freshGrid.forecast_date,
        hours: freshGrid.horizon_hours,
        weatherSummary: freshGrid.weather_summary,
        modelMetadata: freshGrid.model_metadata,
        capability_summary: "batch-only forecast_grids",
      }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    let staleQuery = supabase
      .from("forecast_grids")
      .select("id, region_name, region_key, forecast_date, horizon_hours, weather_summary, model_metadata, status, created_at")
      .eq("hazard_type", "avalanche")
      .order("created_at", { ascending: false })
      .limit(1);
    if (regionKey) staleQuery = staleQuery.eq("region_key", regionKey);
    if (regionName) staleQuery = staleQuery.eq("region_name", regionName);
    const { data: latestGrid, error: latestError } = await staleQuery.maybeSingle();
    if (latestError) throw latestError;

    return new Response(JSON.stringify({
      ok: true,
      stale: true,
      status: latestGrid ? "stale" : "unavailable",
      mode: "batch_only",
      source: "forecast_grids",
      forecastId: latestGrid?.id ?? null,
      regionName: latestGrid?.region_name ?? regionName,
      regionKey: latestGrid?.region_key ?? regionKey,
      forecastDate: latestGrid?.forecast_date ?? null,
      hours: latestGrid?.horizon_hours ?? null,
      weatherSummary: latestGrid?.weather_summary ?? null,
      modelMetadata: latestGrid?.model_metadata ?? null,
      capability_summary: "batch-only forecast_grids",
      message: latestGrid
        ? "No fresh precomputed grid is available for today."
        : "No precomputed forecast grid is available for this region.",
    }), {
      status: latestGrid ? 200 : 404,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
