import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

type ForecastRequest = {
  regionName?: string;
  regionKey?: string;
};

type ForecastGridRow = {
  id: string;
  region_name: string;
  region_key: string;
  forecast_date: string;
  horizon_hours: number | null;
  weather_summary: unknown;
  model_metadata: unknown;
  status?: string | null;
  created_at?: string | null;
};

type ForecastRunRow = {
  id: string;
  region_name: string;
  region_key: string;
  forecast_date: string;
  horizon_hours: number | null;
  manifest_storage_ref: string | null;
  compatibility_forecast_grid_id: string | null;
  forecast_bulletins: unknown;
  weather_summary: unknown;
  model_metadata: unknown;
  status?: string | null;
  published_at?: string | null;
  created_at?: string | null;
};

type ForecastLookupParams = {
  regionName: string | null;
  regionKey: string | null;
  today: string;
};

type ForecastLookupResult = {
  data: ForecastGridRow | null;
  error: { message: string } | null;
};

type ForecastLookupDeps = {
  fetchFreshRun: (
    params: ForecastLookupParams,
  ) => Promise<{ data: ForecastRunRow | null; error: { message: string } | null }>;
  fetchLatestRun: (
    params: ForecastLookupParams,
  ) => Promise<{ data: ForecastRunRow | null; error: { message: string } | null }>;
  fetchFreshGrid: (
    params: ForecastLookupParams,
  ) => Promise<ForecastLookupResult>;
  fetchLatestGrid: (
    params: ForecastLookupParams,
  ) => Promise<ForecastLookupResult>;
  getToday?: () => string;
  getNow?: () => Date;
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function normalizeForecastBulletin(value: unknown): unknown | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return Object.keys(value as Record<string, unknown>).length > 0 ? value : null;
}

function freshnessHoursFrom(publishedAt: string | null | undefined, now: Date): number | null {
  if (!publishedAt) return null;
  const publishedMs = new Date(publishedAt).getTime();
  if (!Number.isFinite(publishedMs)) return null;
  return Math.max(0, (now.getTime() - publishedMs) / 3_600_000);
}

function buildFreshnessState(params: {
  forecastDate: string | null | undefined;
  today: string;
  status: string;
  publishedAt: string | null | undefined;
  now: Date;
}) {
  const freshnessHours = freshnessHoursFrom(params.publishedAt, params.now);
  const sameDayPublished =
    params.forecastDate === params.today &&
    params.status !== "stale" &&
    freshnessHours !== null &&
    freshnessHours <= 24;
  return {
    publishedAt: params.publishedAt ?? null,
    freshnessHours,
    sameDayPublished,
    stale: !sameDayPublished || params.status === "stale",
  };
}

function defaultDeps(): ForecastLookupDeps {
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
  );

  return {
    async fetchFreshRun({ regionName, regionKey, today }) {
      let query = supabase
        .from("forecast_active_runs")
        .select(
          "id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, published_at, created_at",
        )
        .eq("hazard_type", "avalanche")
        .eq("forecast_date", today)
        .order("published_at", { ascending: false })
        .limit(1);

      if (regionKey) query = query.eq("region_key", regionKey);
      if (regionName) query = query.eq("region_name", regionName);
      return await query.maybeSingle();
    },

    async fetchLatestRun({ regionName, regionKey }) {
      let query = supabase
        .from("forecast_active_runs")
        .select(
          "id, region_name, region_key, forecast_date, horizon_hours, manifest_storage_ref, compatibility_forecast_grid_id, forecast_bulletins, weather_summary, model_metadata, status, published_at, created_at",
        )
        .eq("hazard_type", "avalanche")
        .order("published_at", { ascending: false })
        .limit(1);

      if (regionKey) query = query.eq("region_key", regionKey);
      if (regionName) query = query.eq("region_name", regionName);
      return await query.maybeSingle();
    },

    async fetchFreshGrid({ regionName, regionKey, today }) {
      let query = supabase
        .from("forecast_grids")
        .select(
          "id, region_name, region_key, forecast_date, horizon_hours, weather_summary, model_metadata, status, created_at",
        )
        .eq("hazard_type", "avalanche")
        .eq("forecast_date", today)
        .order("created_at", { ascending: false })
        .limit(1);

      if (regionKey) query = query.eq("region_key", regionKey);
      if (regionName) query = query.eq("region_name", regionName);
      return await query.maybeSingle();
    },

    async fetchLatestGrid({ regionName, regionKey }) {
      let query = supabase
        .from("forecast_grids")
        .select(
          "id, region_name, region_key, forecast_date, horizon_hours, weather_summary, model_metadata, status, created_at",
        )
        .eq("hazard_type", "avalanche")
        .order("created_at", { ascending: false })
        .limit(1);

      if (regionKey) query = query.eq("region_key", regionKey);
      if (regionName) query = query.eq("region_name", regionName);
      return await query.maybeSingle();
    },

    getToday: () => new Date().toISOString().slice(0, 10),
  };
}

export async function handleRunForecast(
  req: Request,
  deps: ForecastLookupDeps = defaultDeps(),
) {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const body = await req.json().catch(() => ({})) as ForecastRequest;
    const regionName =
      typeof body.regionName === "string" && body.regionName.trim()
        ? body.regionName.trim()
        : null;
    const regionKey =
      typeof body.regionKey === "string" && body.regionKey.trim()
        ? body.regionKey.trim()
        : null;
    if (!regionName && !regionKey) {
      return jsonResponse(
        { error: "regionName or regionKey is required" },
        400,
      );
    }

    const today = deps.getToday?.() ?? new Date().toISOString().slice(0, 10);
    const now = deps.getNow?.() ?? new Date();
    const { data: freshRun, error: freshRunError } = await deps.fetchFreshRun({
      regionName,
      regionKey,
      today,
    });
    if (freshRunError) throw new Error(freshRunError.message);

    if (freshRun) {
      const runStatus = typeof freshRun.status === "string"
        ? freshRun.status
        : "ready";
      const freshness = buildFreshnessState({
        forecastDate: freshRun.forecast_date,
        today,
        status: runStatus,
        publishedAt: freshRun.published_at ?? freshRun.created_at ?? null,
        now,
      });
      return jsonResponse({
        ok: true,
        stale: freshness.stale,
        status: runStatus,
        mode: "batch_only",
        source: "forecast_runs",
        forecastRunId: freshRun.id,
        forecastId: freshRun.compatibility_forecast_grid_id,
        manifestPath: freshRun.manifest_storage_ref,
        forecastBulletin: normalizeForecastBulletin(freshRun.forecast_bulletins),
        regionName: freshRun.region_name,
        regionKey: freshRun.region_key,
        forecastDate: freshRun.forecast_date,
        publishedAt: freshness.publishedAt,
        freshnessHours: freshness.freshnessHours,
        sameDayPublished: freshness.sameDayPublished,
        hours: freshRun.horizon_hours,
        weatherSummary: freshRun.weather_summary,
        modelMetadata: freshRun.model_metadata,
        capability_summary: "manifest-backed forecast_runs",
      });
    }

    const { data: freshGrid, error: freshError } = await deps.fetchFreshGrid({
      regionName,
      regionKey,
      today,
    });
    if (freshError) throw new Error(freshError.message);

    if (freshGrid) {
      const gridStatus = typeof freshGrid.status === "string"
        ? freshGrid.status
        : "ready";
      const freshness = buildFreshnessState({
        forecastDate: freshGrid.forecast_date,
        today,
        status: gridStatus,
        publishedAt: freshGrid.created_at ?? null,
        now,
      });
      console.warn(`[run-forecast] Warning: Accessing deprecated legacy read path forecast_grids for regionKey=${regionKey}, regionName=${regionName}`);
      return jsonResponse({
        ok: true,
        stale: freshness.stale,
        status: gridStatus,
        mode: "batch_only",
        source: "forecast_grids",
        forecastRunId: null,
        forecastId: freshGrid.id,
        manifestPath: null,
        forecastBulletin: null,
        regionName: freshGrid.region_name,
        regionKey: freshGrid.region_key,
        forecastDate: freshGrid.forecast_date,
        publishedAt: freshness.publishedAt,
        freshnessHours: freshness.freshnessHours,
        sameDayPublished: freshness.sameDayPublished,
        hours: freshGrid.horizon_hours,
        weatherSummary: freshGrid.weather_summary,
        modelMetadata: freshGrid.model_metadata,
        capability_summary: "batch-only forecast_grids",
      });
    }

    const { data: latestRun, error: latestRunError } = await deps.fetchLatestRun(
      { regionName, regionKey, today },
    );
    if (latestRunError) throw new Error(latestRunError.message);

    if (latestRun) {
      const freshness = buildFreshnessState({
        forecastDate: latestRun.forecast_date,
        today,
        status: latestRun.status ?? "stale",
        publishedAt: latestRun.published_at ?? latestRun.created_at ?? null,
        now,
      });
      return jsonResponse({
        ok: true,
        stale: true,
        status: latestRun.status ?? "stale",
        mode: "batch_only",
        source: "forecast_runs",
        forecastRunId: latestRun.id,
        forecastId: latestRun.compatibility_forecast_grid_id,
        manifestPath: latestRun.manifest_storage_ref,
        forecastBulletin: normalizeForecastBulletin(latestRun.forecast_bulletins),
        regionName: latestRun.region_name,
        regionKey: latestRun.region_key,
        forecastDate: latestRun.forecast_date,
        publishedAt: freshness.publishedAt,
        freshnessHours: freshness.freshnessHours,
        sameDayPublished: false,
        hours: latestRun.horizon_hours,
        weatherSummary: latestRun.weather_summary,
        modelMetadata: latestRun.model_metadata,
        capability_summary: "manifest-backed forecast_runs",
        message: "No same-day batch is published yet; returning the latest published run.",
      }, 200);
    }

    const { data: latestGrid, error: latestError } = await deps.fetchLatestGrid(
      { regionName, regionKey, today },
    );
    if (latestError) throw new Error(latestError.message);
    const latestGridFreshness = buildFreshnessState({
      forecastDate: latestGrid?.forecast_date ?? null,
      today,
      status: latestGrid?.status ?? "stale",
      publishedAt: latestGrid?.created_at ?? null,
      now,
    });

    console.warn(`[run-forecast] Warning: Accessing deprecated legacy read path forecast_grids (latest/fallback) for regionKey=${regionKey}, regionName=${regionName}`);
    return jsonResponse({
      ok: true,
      stale: true,
      status: latestGrid?.status ?? (latestGrid ? "stale" : "unavailable"),
      mode: "batch_only",
      source: "forecast_grids",
      forecastRunId: null,
      forecastId: latestGrid?.id ?? null,
      manifestPath: null,
      forecastBulletin: null,
      regionName: latestGrid?.region_name ?? regionName,
      regionKey: latestGrid?.region_key ?? regionKey,
      forecastDate: latestGrid?.forecast_date ?? null,
      publishedAt: latestGridFreshness.publishedAt,
      freshnessHours: latestGridFreshness.freshnessHours,
      sameDayPublished: false,
      hours: latestGrid?.horizon_hours ?? null,
      weatherSummary: latestGrid?.weather_summary ?? null,
      modelMetadata: latestGrid?.model_metadata ?? null,
      capability_summary: "batch-only forecast_grids",
      message: latestGrid
        ? "No same-day grid is published yet; returning the latest published grid."
        : "No published forecast grid is available for this region.",
    }, latestGrid ? 200 : 404);
  } catch (error) {
    return jsonResponse({ error: (error as Error).message }, 500);
  }
}

if (import.meta.main) {
  serve((req) => handleRunForecast(req));
}
