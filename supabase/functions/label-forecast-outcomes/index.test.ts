import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";

import { handleLabelForecastOutcomes } from "./index.ts";

// Set mock environment variables for testing
Deno.env.set("SUPABASE_URL", "https://fzheroisjhxnairglelv.supabase.co");
Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key");
Deno.env.set("REQUIRE_JOB_AUTH", "false");

type LabelDeps = NonNullable<Parameters<typeof handleLabelForecastOutcomes>[1]>;

function buildDeps(overrides: Partial<LabelDeps> = {}) {
  const createdJobs: Array<{ hazardType: string; forecastId?: string; daysBack: number }> = [];
  const completedJobs: Array<{ jobId: string; result: Record<string, unknown> }> = [];
  const failedJobs: string[] = [];
  const insertedBatches: Record<string, unknown>[][] = [];
  const rpcCalls: Record<string, unknown>[] = [];
  const fallbackCalls: Record<string, unknown>[] = [];
  const existingOutcomeChecks: Record<string, unknown>[] = [];
  const policy = {
    spatial_tolerance_m: 5000,
    temporal_tolerance_hours: 24,
    elevation_band_width_m: 500,
    elevation_flexibility_m: 300,
    min_event_verification: "weak",
  };

  const deps: LabelDeps = {
    supabase: {},
    async createJob(params) {
      createdJobs.push(params);
      return { id: `job-${createdJobs.length}` };
    },
    async completeJob(jobId, result) {
      completedJobs.push({ jobId, result });
    },
    async failRunningJob(errorMessage) {
      failedJobs.push(errorMessage);
    },
    async fetchLabelPolicy() {
      return policy;
    },
    async fetchForecastSources() {
      return [];
    },
    async fetchExistingOutcome(forecast) {
      existingOutcomeChecks.push(forecast as unknown as Record<string, unknown>);
      return false;
    },
    async fetchEligibleEventsRpc(params) {
      rpcCalls.push(params as unknown as Record<string, unknown>);
      return { events: [], error: null };
    },
    async fetchEligibleEventsFallback(params) {
      fallbackCalls.push(params as unknown as Record<string, unknown>);
      return [];
    },
    async insertForecastOutcomeBatch(outcomes) {
      insertedBatches.push(outcomes);
    },
    async runWithTimeout(work) {
      return await work();
    },
    ...overrides,
  };

  return {
    deps,
    createdJobs,
    completedJobs,
    failedJobs,
    insertedBatches,
    rpcCalls,
    fallbackCalls,
    existingOutcomeChecks,
    policy,
  };
}

function makeRequest(body: Record<string, unknown>) {
  return new Request("http://localhost", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

Deno.test("handleLabelForecastOutcomes rejects unsupported hazard types without creating a job", async () => {
  const harness = buildDeps();

  const response = await handleLabelForecastOutcomes(
    makeRequest({ hazard_type: "landslide" }),
    harness.deps,
  );

  assertEquals(response.status, 400);
  assertEquals(await response.json(), { error: "Only avalanche supported" });
  assertEquals(harness.createdJobs.length, 0);
  assertEquals(harness.completedJobs.length, 0);
  assertEquals(harness.failedJobs.length, 0);
});

Deno.test("handleLabelForecastOutcomes completes early when no forecasts are found", async () => {
  const harness = buildDeps();

  const response = await handleLabelForecastOutcomes(
    makeRequest({ days_back: 3, hazard_type: "avalanche" }),
    harness.deps,
  );

  const payload = await response.json();
  assertEquals(response.status, 200);
  assertEquals(harness.createdJobs.length, 1);
  assertEquals(harness.createdJobs[0], {
    hazardType: "avalanche",
    forecastId: undefined,
    daysBack: 3,
  });
  assertEquals(harness.completedJobs.length, 1);
  assertEquals(payload, {
    forecasts_processed: 0,
    total_outcomes_labeled: 0,
    forecasts_skipped: 0,
    labeling_policy: harness.policy,
    note: "No matching forecasts found in window. Completed with 0 labels.",
  });
  assertEquals(harness.completedJobs[0].result, payload);
});

Deno.test("handleLabelForecastOutcomes labels a forecast-grid from RPC events and preserves evaluation metadata", async () => {
  const harness = buildDeps({
    async fetchForecastSources() {
      return [{
        source_type: "forecast_grid",
        id: "fg-1",
        created_at: "2026-05-01T00:00:00Z",
        bbox: [27.9, 86.7, 28.1, 86.9],
        hourly_grids: [[{
          row: 0,
          col: 1,
          lat: 28.0,
          lng: 86.8,
          riskScore: 4,
          hazard: 0.77,
          terrain_inputs: { elevation_m: 3125 },
          coverage_flags: { sar_coverage_state: "low_coverage" },
          dry_wet_domain: "wet",
          problem_slug: "wet_snow",
        }]],
      }];
    },
    async fetchEligibleEventsRpc(params) {
      harness.rpcCalls.push(params as unknown as Record<string, unknown>);
      return {
        events: [{
          id: "evt-1",
          timestamp: "2026-05-01T06:00:00Z",
          severity: 4,
          verification_status: "verified",
          elevation_m: 3150,
          label_role: "core",
          training_eligible_reason: "sar_low_coverage_weak_training",
          location: "POINT(86.8 28.0)",
        }],
        error: null,
      };
    },
  });

  const response = await handleLabelForecastOutcomes(
    makeRequest({ hazard_type: "avalanche" }),
    harness.deps,
  );

  const payload = await response.json();
  assertEquals(response.status, 200);
  assertEquals(payload, {
    forecasts_processed: 1,
    total_outcomes_labeled: 1,
    forecasts_skipped: 0,
    labeling_policy: harness.policy,
  });
  assertEquals(harness.rpcCalls.length, 1);
  assertEquals(harness.fallbackCalls.length, 0);
  assertEquals(harness.insertedBatches.length, 1);
  assertEquals(harness.insertedBatches[0].length, 1);
  assertEquals(harness.completedJobs.length, 1);
  const inserted = harness.insertedBatches[0][0];
  assertEquals(inserted.forecast_grid_id, "fg-1");
  assertEquals(inserted.forecast_id, null);
  assertEquals(inserted.cell_elevation_m, 3125);
  assertEquals(inserted.sar_coverage_state, "low_coverage");
  assertEquals(inserted.dry_wet_domain, "wet");
  assertEquals(inserted.problem_slug, "wet_snow");
  assertEquals(inserted.training_eligible_reason, "sar_low_coverage_weak_training");
  assertEquals(inserted.nearest_event_id, "evt-1");
  assertEquals(inserted.event_observed, true);
});

Deno.test("handleLabelForecastOutcomes falls back to REST events when RPC is unavailable", async () => {
  const harness = buildDeps({
    async fetchForecastSources() {
      return [{
        source_type: "forecast",
        id: "forecast-1",
        created_at: "2026-05-01T00:00:00Z",
        bbox: [27.9, 86.7, 28.1, 86.9],
        hourly_grids: [[{
          row: 2,
          col: 3,
          lat: 28.0,
          lng: 86.8,
          risk_score: 3,
          hazard: 0.51,
          terrain_inputs: { elevation_m: 2900 },
          coverage_flags: { sar_coverage_state: "full_coverage" },
          dry_wet_domain: "dry",
          problem_slug: "wind_slab",
        }]],
      }];
    },
    async fetchEligibleEventsRpc(params) {
      harness.rpcCalls.push(params as unknown as Record<string, unknown>);
      return { events: [], error: new Error("rpc unavailable") };
    },
    async fetchEligibleEventsFallback(params) {
      harness.fallbackCalls.push(params as unknown as Record<string, unknown>);
      return [{
        id: "evt-rest-1",
        timestamp: "2026-05-01T03:00:00Z",
        severity: 3,
        verification_status: "weak",
        elevation_m: 2890,
        label_role: "core",
        training_eligible_reason: null,
        location: "POINT(86.8 28.0)",
      }];
    },
  });

  const response = await handleLabelForecastOutcomes(
    makeRequest({ hazard_type: "avalanche" }),
    harness.deps,
  );

  const payload = await response.json();
  assertEquals(response.status, 200);
  assertEquals(payload.total_outcomes_labeled, 1);
  assertEquals(harness.rpcCalls.length, 1);
  assertEquals(harness.fallbackCalls.length, 1);
  assertEquals(harness.insertedBatches.length, 1);
  assertEquals(harness.insertedBatches[0][0].forecast_id, "forecast-1");
  assertEquals(harness.insertedBatches[0][0].nearest_event_id, "evt-rest-1");
});

Deno.test("handleLabelForecastOutcomes returns partial success when timeout fires after some inserts", async () => {
  const harness = buildDeps({
    async fetchForecastSources() {
      return [{
        source_type: "forecast_grid",
        id: "fg-timeout",
        created_at: "2026-05-01T00:00:00Z",
        bbox: [27.9, 86.7, 28.1, 86.9],
        hourly_grids: [[{
          row: 1,
          col: 1,
          lat: 28.0,
          lng: 86.8,
          riskScore: 5,
          hazard: 0.91,
          terrain_inputs: { elevation_m: 3200 },
          coverage_flags: { sar_coverage_state: "low_coverage" },
          dry_wet_domain: "wet",
          problem_slug: "wet_snow",
        }]],
      }];
    },
    async fetchEligibleEventsRpc() {
      return {
        events: [{
          id: "evt-timeout",
          timestamp: "2026-05-01T02:00:00Z",
          severity: 4,
          verification_status: "verified",
          elevation_m: 3220,
          label_role: "core",
          training_eligible_reason: "sar_low_coverage_weak_training",
          location: "POINT(86.8 28.0)",
        }],
        error: null,
      };
    },
    async runWithTimeout(work, _timeoutMs, timeoutMessage) {
      await work();
      throw new Error(timeoutMessage);
    },
  });

  const response = await handleLabelForecastOutcomes(
    makeRequest({ hazard_type: "avalanche" }),
    harness.deps,
  );

  const payload = await response.json();
  assertEquals(response.status, 200);
  assertEquals(payload.total_outcomes_labeled, 1);
  assertEquals(
    payload.warning,
    "Labeling timed out after 60s — partial results saved",
  );
  assertEquals(harness.insertedBatches.length, 1);
  assertEquals(harness.completedJobs.length, 1);
  assertEquals(
    harness.completedJobs[0].result.warning,
    "Labeling timed out after 60s — partial results saved",
  );
});

Deno.test("handleLabelForecastOutcomes fails the running job on unexpected errors after job creation", async () => {
  const harness = buildDeps({
    async fetchForecastSources() {
      throw new Error("boom");
    },
  });

  const response = await handleLabelForecastOutcomes(
    makeRequest({ hazard_type: "avalanche" }),
    harness.deps,
  );

  assertEquals(response.status, 500);
  assertEquals(await response.json(), { error: "boom" });
  assertEquals(harness.createdJobs.length, 1);
  assertEquals(harness.completedJobs.length, 0);
  assertEquals(harness.failedJobs, ["boom"]);
  assertEquals(harness.insertedBatches.length, 0);
  assertExists(harness.createdJobs[0]);
});
