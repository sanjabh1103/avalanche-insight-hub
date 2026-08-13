import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

import {
  buildForecastGridPrecomputePayload,
  computeJobStatusForResult,
  buildRuntimeCapabilitySnapshot,
} from "./index.ts";

Deno.test("buildForecastGridPrecomputePayload forwards artifact and tuning inputs", () => {
  const payload = buildForecastGridPrecomputePayload(
    {
      artifact_dir: " /artifacts/20260430T165417Z ",
      region_key: " japanese_alps ",
      forecast_hours: "72",
      grid_size: 20,
    },
    "job-123",
    "avalanche",
  );

  assertEquals(payload, {
    job_id: "job-123",
    compute_job_id: "job-123",
    hazard_type: "avalanche",
    requested_by: "trigger-job",
    request_type: "forecast_grid_precompute",
    dataset_snapshot_id: "latest",
    artifact_dir: "/artifacts/20260430T165417Z",
    region_key: "japanese_alps",
    forecast_hours: 72,
    grid_size: 20,
  });
});

Deno.test("buildForecastGridPrecomputePayload omits invalid optional values", () => {
  const payload = buildForecastGridPrecomputePayload(
    {
      artifact_dir: "   ",
      forecast_hours: "-5",
      grid_size: 0,
    },
    "job-123",
    "avalanche",
  );

  assertEquals(payload, {
    job_id: "job-123",
    compute_job_id: "job-123",
    hazard_type: "avalanche",
    requested_by: "trigger-job",
    request_type: "forecast_grid_precompute",
    dataset_snapshot_id: "latest",
  });
});

Deno.test("buildForecastGridPrecomputePayload defaults proof72 when lifeboat mode is enabled", () => {
  const payload = buildForecastGridPrecomputePayload(
    {
      region_key: "japanese_alps",
      lifeboat_mode: "true",
    },
    "job-123",
    "avalanche",
  );

  assertEquals(payload, {
    job_id: "job-123",
    compute_job_id: "job-123",
    hazard_type: "avalanche",
    requested_by: "trigger-job",
    request_type: "forecast_grid_precompute",
    dataset_snapshot_id: "latest",
    region_key: "japanese_alps",
    lifeboat_mode: true,
    lifeboat_profile: "proof72",
  });
});

Deno.test("buildForecastGridPrecomputePayload forwards explicit proof flags", () => {
  const payload = buildForecastGridPrecomputePayload(
    {
      region_key: "japanese_alps",
      lifeboat_mode: true,
      lifeboat_profile: "smoke24",
      skip_tree_shap: "1",
      skip_shap_cache: "true",
      skip_runout_generation: "yes",
      skip_compatibility_write: "on",
      emit_stage_metrics: "true",
    },
    "job-123",
    "avalanche",
  );

  assertEquals(payload, {
    job_id: "job-123",
    compute_job_id: "job-123",
    hazard_type: "avalanche",
    requested_by: "trigger-job",
    request_type: "forecast_grid_precompute",
    dataset_snapshot_id: "latest",
    region_key: "japanese_alps",
    lifeboat_mode: true,
    lifeboat_profile: "smoke24",
    skip_tree_shap: true,
    skip_shap_cache: true,
    skip_runout_generation: true,
    skip_compatibility_write: true,
    emit_stage_metrics: true,
  });
});

Deno.test("buildRuntimeCapabilitySnapshot keeps runtime details out of capability_summary", () => {
  const snapshot = buildRuntimeCapabilitySnapshot({
    mode: "gpu_only",
    summary: "GPU snowpack + Edge SAR fallback",
    sarEnabled: false,
    gpuEnabled: true,
    sarCredentialsPresent: false,
    gpuCredentialsPresent: true,
    modalWorkerUrl: "https://worker.example",
    modalWorkerToken: "secret",
  });

  assertEquals(snapshot.runtime_mode, "gpu_only");
  assertEquals(snapshot.runtime_summary, "GPU snowpack + Edge SAR fallback");
  assertEquals("capability_summary" in snapshot, false);
});

Deno.test("computeJobStatusForResult keeps accepted worker submissions running", () => {
  assertEquals(
    computeJobStatusForResult({
      workerResult: {
        status: "accepted",
        call_id: "fc-123",
      },
    }),
    "running",
  );
});

Deno.test("computeJobStatusForResult completes non-accepted results", () => {
  assertEquals(
    computeJobStatusForResult({
      workerResult: {
        status: "ok",
        call_id: "fc-123",
      },
    }),
    "completed",
  );
  assertEquals(computeJobStatusForResult({ simulated: true }), "completed");
});

Deno.test({
  name: "handleTriggerJob returns 401 when REQUIRE_JOB_AUTH is enabled and token is missing",
  sanitizeOps: false,
  sanitizeResources: false,
  async fn() {
    const oldRequireAuth = Deno.env.get("REQUIRE_JOB_AUTH");
    const oldJobToken = Deno.env.get("JOB_DISPATCH_TOKEN");
    const oldSupabaseUrl = Deno.env.get("SUPABASE_URL");
    const oldServiceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    Deno.env.set("REQUIRE_JOB_AUTH", "true");
    Deno.env.set("JOB_DISPATCH_TOKEN", "super-secret-token");
    Deno.env.set("SUPABASE_URL", "https://example.supabase.co");
    Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-key");

    try {
      const req = new Request("https://example.com/functions/v1/trigger-job", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ type: "daily_enrichment" }),
      });

      const { handleTriggerJob } = await import("./index.ts");
      const res = await handleTriggerJob(req);
      assertEquals(res.status, 401);

      const body = await res.json();
      assertEquals(body.error, "Missing authorization token");
    } finally {
      if (oldRequireAuth !== undefined) Deno.env.set("REQUIRE_JOB_AUTH", oldRequireAuth);
      else Deno.env.delete("REQUIRE_JOB_AUTH");

      if (oldJobToken !== undefined) Deno.env.set("JOB_DISPATCH_TOKEN", oldJobToken);
      else Deno.env.delete("JOB_DISPATCH_TOKEN");

      if (oldSupabaseUrl !== undefined) Deno.env.set("SUPABASE_URL", oldSupabaseUrl);
      else Deno.env.delete("SUPABASE_URL");

      if (oldServiceRoleKey !== undefined) Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", oldServiceRoleKey);
      else Deno.env.delete("SUPABASE_SERVICE_ROLE_KEY");
    }
  }
});

Deno.test({
  name: "handleTriggerJob accepts request when token matches JOB_DISPATCH_TOKEN",
  sanitizeOps: false,
  sanitizeResources: false,
  async fn() {
    const oldRequireAuth = Deno.env.get("REQUIRE_JOB_AUTH");
    const oldJobToken = Deno.env.get("JOB_DISPATCH_TOKEN");
    const oldSupabaseUrl = Deno.env.get("SUPABASE_URL");
    const oldServiceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    Deno.env.set("REQUIRE_JOB_AUTH", "true");
    Deno.env.set("JOB_DISPATCH_TOKEN", "super-secret-token");
    Deno.env.set("SUPABASE_URL", "https://example.supabase.co");
    Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-key");

    try {
      const req = new Request("https://example.com/functions/v1/trigger-job", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer super-secret-token",
        },
        // Send invalid type so it rejects with 400 instead of attempting DB operations.
        body: JSON.stringify({ type: "invalid_type" }),
      });

      const { handleTriggerJob } = await import("./index.ts");
      const res = await handleTriggerJob(req);
      assertEquals(res.status, 400);

      const body = await res.json();
      assertEquals(body.error, "Invalid job type");
    } finally {
      if (oldRequireAuth !== undefined) Deno.env.set("REQUIRE_JOB_AUTH", oldRequireAuth);
      else Deno.env.delete("REQUIRE_JOB_AUTH");

      if (oldJobToken !== undefined) Deno.env.set("JOB_DISPATCH_TOKEN", oldJobToken);
      else Deno.env.delete("JOB_DISPATCH_TOKEN");

      if (oldSupabaseUrl !== undefined) Deno.env.set("SUPABASE_URL", oldSupabaseUrl);
      else Deno.env.delete("SUPABASE_URL");

      if (oldServiceRoleKey !== undefined) Deno.env.set("SUPABASE_SERVICE_ROLE_KEY", oldServiceRoleKey);
      else Deno.env.delete("SUPABASE_SERVICE_ROLE_KEY");
    }
  }
});

