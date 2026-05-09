import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

import { handleRunForecast } from "./index.ts";

Deno.test("handleRunForecast returns fresh batch row without stale fallback", async () => {
  const response = await handleRunForecast(
    new Request("http://localhost", {
      method: "POST",
      body: JSON.stringify({ regionKey: "japanese_alps" }),
    }),
    {
      fetchFreshRun: async () => ({ data: null, error: null }),
      fetchLatestRun: async () => ({ data: null, error: null }),
      fetchFreshGrid: async () => ({
        data: {
          id: "fg-1",
          region_name: "Japanese Alps",
          region_key: "japanese_alps",
          forecast_date: "2026-05-01",
          horizon_hours: 72,
          weather_summary: { snow: "moderate" },
          model_metadata: { source: "rf" },
          status: "ready",
          created_at: "2026-05-01T03:00:00.000Z",
        },
        error: null,
      }),
      fetchLatestGrid: async () => ({ data: null, error: null }),
      getToday: () => "2026-05-01",
      getNow: () => new Date("2026-05-01T04:00:00.000Z"),
    },
  );

  assertEquals(response.status, 200);
  assertEquals(await response.json(), {
    ok: true,
    stale: false,
    status: "ready",
    mode: "batch_only",
    source: "forecast_grids",
    forecastRunId: null,
    forecastId: "fg-1",
    manifestPath: null,
    forecastBulletin: null,
    regionName: "Japanese Alps",
    regionKey: "japanese_alps",
    forecastDate: "2026-05-01",
    publishedAt: "2026-05-01T03:00:00.000Z",
    freshnessHours: 1,
    sameDayPublished: true,
    hours: 72,
    weatherSummary: { snow: "moderate" },
    modelMetadata: { source: "rf" },
    capability_summary: "batch-only forecast_grids",
  });
});

Deno.test("handleRunForecast returns fresh published run before legacy grid fallback", async () => {
  const response = await handleRunForecast(
    new Request("http://localhost", {
      method: "POST",
      body: JSON.stringify({ regionKey: "japanese_alps" }),
    }),
    {
      fetchFreshRun: async () => ({
        data: {
          id: "run-1",
          region_name: "Japanese Alps",
          region_key: "japanese_alps",
          forecast_date: "2026-05-01",
          horizon_hours: 72,
          manifest_storage_ref: "forecast-products/avalanche/japanese_alps/run-1/manifest.json",
          compatibility_forecast_grid_id: "fg-1",
          forecast_bulletins: {
            schema_version: "forecast-bulletin/v1",
            danger_level: 4,
            danger_label: "High",
            primary_problem: "wind_slab",
          },
          weather_summary: { snow: "fresh" },
          model_metadata: { source: "rf" },
          status: "ready",
          published_at: "2026-05-01T02:30:00.000Z",
        },
        error: null,
      }),
      fetchLatestRun: async () => ({ data: null, error: null }),
      fetchFreshGrid: async () => {
        throw new Error("legacy fallback should not be queried when a fresh run exists");
      },
      fetchLatestGrid: async () => ({ data: null, error: null }),
      getToday: () => "2026-05-01",
      getNow: () => new Date("2026-05-01T04:00:00.000Z"),
    },
  );

  assertEquals(response.status, 200);
  assertEquals(await response.json(), {
    ok: true,
    stale: false,
    status: "ready",
    mode: "batch_only",
    source: "forecast_runs",
    forecastRunId: "run-1",
    forecastId: "fg-1",
    manifestPath: "forecast-products/avalanche/japanese_alps/run-1/manifest.json",
    forecastBulletin: {
      schema_version: "forecast-bulletin/v1",
      danger_level: 4,
      danger_label: "High",
      primary_problem: "wind_slab",
    },
    regionName: "Japanese Alps",
    regionKey: "japanese_alps",
    forecastDate: "2026-05-01",
    publishedAt: "2026-05-01T02:30:00.000Z",
    freshnessHours: 1.5,
    sameDayPublished: true,
    hours: 72,
    weatherSummary: { snow: "fresh" },
    modelMetadata: { source: "rf" },
    capability_summary: "manifest-backed forecast_runs",
  });
});

Deno.test("handleRunForecast returns stale published run with forecast-runs capability summary", async () => {
  const response = await handleRunForecast(
    new Request("http://localhost", {
      method: "POST",
      body: JSON.stringify({ regionKey: "japanese_alps" }),
    }),
    {
      fetchFreshRun: async () => ({ data: null, error: null }),
      fetchLatestRun: async () => ({
        data: {
          id: "run-stale",
          region_name: "Japanese Alps",
          region_key: "japanese_alps",
          forecast_date: "2026-04-18",
          horizon_hours: 72,
          manifest_storage_ref: "forecast-products/avalanche/japanese_alps/run-stale/manifest.json",
          compatibility_forecast_grid_id: "fg-stale",
          forecast_bulletins: {
            schema_version: "forecast-bulletin/v1",
            danger_level: 3,
            danger_label: "Considerable",
            primary_problem: "new_snow",
          },
          weather_summary: { snow: "old" },
          model_metadata: { source: "rf" },
          status: "ready",
          published_at: "2026-04-18T02:30:00.000Z",
        },
        error: null,
      }),
      fetchFreshGrid: async () => ({ data: null, error: null }),
      fetchLatestGrid: async () => {
        throw new Error("legacy grid fallback should not be queried when a stale run exists");
      },
      getToday: () => "2026-05-01",
      getNow: () => new Date("2026-05-01T02:30:00.000Z"),
    },
  );

  assertEquals(response.status, 200);
  assertEquals(await response.json(), {
    ok: true,
    stale: true,
    status: "ready",
    mode: "batch_only",
    source: "forecast_runs",
    forecastRunId: "run-stale",
    forecastId: "fg-stale",
    manifestPath: "forecast-products/avalanche/japanese_alps/run-stale/manifest.json",
    forecastBulletin: {
      schema_version: "forecast-bulletin/v1",
      danger_level: 3,
      danger_label: "Considerable",
      primary_problem: "new_snow",
    },
    regionName: "Japanese Alps",
    regionKey: "japanese_alps",
    forecastDate: "2026-04-18",
    publishedAt: "2026-04-18T02:30:00.000Z",
    freshnessHours: 312,
    sameDayPublished: false,
    hours: 72,
    weatherSummary: { snow: "old" },
    modelMetadata: { source: "rf" },
    capability_summary: "manifest-backed forecast_runs",
    message: "No same-day batch is published yet; returning the latest published run.",
  });
});

Deno.test("handleRunForecast returns stale grid fallback instead of 500", async () => {
  const response = await handleRunForecast(
    new Request("http://localhost", {
      method: "POST",
      body: JSON.stringify({ regionKey: "japanese_alps" }),
    }),
    {
      fetchFreshRun: async () => ({ data: null, error: null }),
      fetchLatestRun: async () => ({ data: null, error: null }),
      fetchFreshGrid: async () => ({ data: null, error: null }),
      fetchLatestGrid: async () => ({
        data: {
          id: "fg-stale",
          region_name: "Japanese Alps",
          region_key: "japanese_alps",
          forecast_date: "2026-04-18",
          horizon_hours: 72,
          weather_summary: { snow: "old" },
          model_metadata: { source: "rf" },
          status: "ready",
        },
        error: null,
      }),
      getToday: () => "2026-05-01",
    },
  );

  const payload = await response.json();
  assertEquals(response.status, 200);
  assertEquals(payload.ok, true);
  assertEquals(payload.stale, true);
  assertEquals(
    payload.message,
    "No same-day grid is published yet; returning the latest published grid.",
  );
  assertEquals(payload.capability_summary, "batch-only forecast_grids");
});

Deno.test("handleRunForecast returns 404 when no rows exist", async () => {
  const response = await handleRunForecast(
    new Request("http://localhost", {
      method: "POST",
      body: JSON.stringify({ regionKey: "japanese_alps" }),
    }),
    {
      fetchFreshRun: async () => ({ data: null, error: null }),
      fetchLatestRun: async () => ({ data: null, error: null }),
      fetchFreshGrid: async () => ({ data: null, error: null }),
      fetchLatestGrid: async () => ({ data: null, error: null }),
      getToday: () => "2026-05-01",
    },
  );

  const payload = await response.json();
  assertEquals(response.status, 404);
  assertEquals(payload.ok, true);
  assertEquals(payload.status, "unavailable");
  assertEquals(payload.stale, true);
});
