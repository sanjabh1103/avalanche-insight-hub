import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { authorizeJobRequest } from "../_shared/auth.ts";

import {
  corsHeaders,
  detectRuntimeCapabilities,
  invokeEdgeFunction,
  RequestValidationError,
  extractEvaluationManifest,
} from "./utils.ts";

// Import Handlers
import { handleDailyEnrichment } from "./handlers/daily_enrichment.ts";
import { handleSentinelRefresh } from "./handlers/sentinel_refresh.ts";
import { handleFineTune } from "./handlers/fine_tune.ts";
import { handleModelOptimization } from "./handlers/model_optimization.ts";
import {
  handleStaticPrecompute,
  handleFieldReportEnrichment,
  handleIngestEvent,
} from "./handlers/simple_jobs.ts";
import {
  handleRetrainAvalancheModel,
  handleForecastGridPrecompute,
  handleEvaluateRelease,
  handleMlTrain,
} from "./handlers/evaluation_and_training.ts";
import { HandlerArgs, JobHandler } from "./handlers/types.ts";

// Re-export utility functions tested by Deno unit tests
export {
  buildForecastGridPrecomputePayload,
  computeJobStatusForResult,
  buildRuntimeCapabilitySnapshot,
} from "./utils.ts";

export async function handleTriggerJob(req: Request) {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const callerAuthorization = req.headers.get("authorization");
  const callerApiKey = req.headers.get("apikey");

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  let jobId: string | null = null;

  try {
    const body = await req.json();
    const { type, bbox, hazard_type: hazardType = "avalanche" } = body;
    const capabilities = detectRuntimeCapabilities();

    const authResult = await authorizeJobRequest(type, req, supabase);
    if (!authResult.authorized) {
      return new Response(JSON.stringify({ error: authResult.error }), {
        status: authResult.status || 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const evaluateReleaseContext = type === "evaluate_release"
      ? {
          evaluationManifest: extractEvaluationManifest(body),
          referenceSetKey: typeof body.reference_set_key === "string" && body.reference_set_key.trim()
            ? body.reference_set_key.trim()
            : null,
          adminAudit: authResult.audit ?? null,
        }
      : null;

    const validTypes = [
      "daily_enrichment",
      "sentinel_refresh",
      "fine_tune",
      "static_precompute",
      "field_report_enrichment",
      "ingest_event",
      "retrain_avalanche_model",
      "forecast_grid_precompute",
      "evaluate_release",
      "ml_train",
      "model_optimization",
      "snow_cover_refresh",
      "recent_activity_refresh",
      "label_forecast_outcomes",
      "run_evaluation",
    ];

    if (!validTypes.includes(type)) {
      return new Response(JSON.stringify({ error: "Invalid job type" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if (hazardType !== "avalanche") {
      return new Response(
        JSON.stringify({
          error: "Only avalanche jobs are currently supported",
        }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    const delegatedJobTypes = new Set([
      "snow_cover_refresh",
      "recent_activity_refresh",
      "label_forecast_outcomes",
      "run_evaluation",
    ]);

    if (delegatedJobTypes.has(type)) {
      const delegatedPayload: Record<string, unknown> = {
        hazard_type: hazardType,
      };
      if (type === "snow_cover_refresh") {
        delegatedPayload.region_name = "global";
        delegatedPayload.bbox = bbox || [-180, -90, 180, 90];
        delegatedPayload.date = new Date().toISOString().split("T")[0];
      } else if (type === "recent_activity_refresh") {
        delegatedPayload.region_name = "global";
        delegatedPayload.window_days = 7;
        delegatedPayload.materialize_cells = false;
      } else if (type === "label_forecast_outcomes") {
        delegatedPayload.days_back = 30;
      } else if (type === "run_evaluation") {
        delegatedPayload.days_back = 30;
      }

      let result: Record<string, unknown>;
      try {
        result = await invokeEdgeFunction(
          type === "recent_activity_refresh"
            ? "recent-activity-refresh"
            : type === "label_forecast_outcomes"
            ? "label-forecast-outcomes"
            : type === "run_evaluation"
            ? "run-evaluation"
            : "ingest-snow-cover",
          delegatedPayload,
          callerAuthorization,
          callerApiKey,
        );
      } catch (delegatedErr) {
        return new Response(
          JSON.stringify({ error: (delegatedErr as Error).message }),
          {
            status: 502,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          },
        );
      }

      return new Response(JSON.stringify(result), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Standard local jobs:
    const { data: job, error: jobErr } = await supabase
      .from("compute_jobs")
      .insert({
        type,
        status: "running",
        hazard_type: hazardType,
        bbox: bbox || null,
        payload: {
          runtime_mode: capabilities.mode,
          capability_summary: capabilities.summary,
          sar_enabled: capabilities.sarEnabled,
          gpu_enabled: capabilities.gpuEnabled,
          ...(type === "evaluate_release"
            ? {
              release_gate: {
                gate_source: evaluateReleaseContext?.evaluationManifest
                  ? "admin_manifest"
                  : "reference_set_key",
                reference_set_key: evaluateReleaseContext?.referenceSetKey ??
                  null,
                prediction_model_version:
                  typeof body.prediction_model_version === "string" &&
                    body.prediction_model_version.trim()
                    ? body.prediction_model_version.trim()
                    : null,
                admin_audit: evaluateReleaseContext?.adminAudit ?? null,
              },
            }
            : {}),
        },
      })
      .select("id")
      .maybeSingle();

    if (jobErr) throw jobErr;
    if (!job?.id) throw new Error("Failed to create compute_job row");
    jobId = job.id;

    // Dispatch to registered handlers
    const registry: Record<string, JobHandler> = {
      daily_enrichment: handleDailyEnrichment,
      sentinel_refresh: handleSentinelRefresh,
      fine_tune: handleFineTune,
      static_precompute: handleStaticPrecompute,
      field_report_enrichment: handleFieldReportEnrichment,
      ingest_event: handleIngestEvent,
      retrain_avalanche_model: handleRetrainAvalancheModel,
      forecast_grid_precompute: handleForecastGridPrecompute,
      evaluate_release: handleEvaluateRelease,
      ml_train: handleMlTrain,
      model_optimization: handleModelOptimization,
    };

    const handler = registry[type];
    if (!handler) {
      throw new Error(`No handler registered for job type: ${type}`);
    }

    const handlerArgs: HandlerArgs = {
      supabase,
      body,
      capabilities,
      hazardType,
      bbox: bbox || null,
      job: { id: job.id },
      callerAuthorization,
      callerApiKey,
      evaluateReleaseContext,
    };

    const result = await handler(handlerArgs);
    const computeJobStatusForResult = (await import("./utils.ts")).computeJobStatusForResult;

    await supabase
      .from("compute_jobs")
      .update({ status: computeJobStatusForResult(result), result, error: null })
      .eq("id", jobId);

    return new Response(JSON.stringify({ jobId: job.id, result }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });

  } catch (err) {
    const statusCode = typeof (err as { status?: unknown }).status === "number"
      ? Number((err as { status: number }).status)
      : 500;
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (supabaseUrl && serviceRoleKey && jobId) {
      try {
        const supabase = createClient(supabaseUrl, serviceRoleKey);
        await supabase
          .from("compute_jobs")
          .update({ status: "failed", error: (err as Error).message })
          .eq("id", jobId);
      } catch {
        // ignore best-effort cleanup errors
      }
    }
    return new Response(JSON.stringify({ error: (err as Error).message }), {
      status: statusCode,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
}

if (import.meta.main) {
  serve(handleTriggerJob);
}
