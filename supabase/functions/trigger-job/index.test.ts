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
