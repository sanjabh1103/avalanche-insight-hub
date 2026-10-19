import { HandlerArgs } from "./types.ts";
import {
  invokeModalWorker,
  buildRuntimeCapabilitySnapshot,
  updateModelStatus,
  nextOptimizationRunAt,
} from "../utils.ts";

export async function handleModelOptimization({
  supabase,
  capabilities,
  hazardType,
  job,
}: HandlerArgs): Promise<Record<string, unknown>> {
  const { data: currentModel } = await supabase
    .from("model_status")
    .select("id, version, optimization_version, optimization_summary")
    .eq("hazard_type", hazardType)
    .limit(1)
    .maybeSingle();
  const currentOptimizationVersion =
    typeof currentModel?.optimization_version === "string" &&
      currentModel.optimization_version
      ? currentModel.optimization_version
      : "opt-edge-v0";
  const currentSummary = currentModel?.optimization_summary &&
      typeof currentModel.optimization_summary === "object"
    ? currentModel.optimization_summary as Record<string, unknown>
    : null;
  const currentSummaryOrigin = typeof currentSummary?.origin === "string"
    ? currentSummary.origin
    : null;
  const currentAbcEnabled = Boolean(currentSummary?.abc_enabled);
  const modalResult = await invokeModalWorker(capabilities, "optimize", {
    job_id: job.id,
    hazard_type: hazardType,
    current_version: currentModel?.version || "v1.0.0",
    current_optimization_version: currentOptimizationVersion,
  }, 20000);

  // P1.1: Precedence for the optimization summary we publish:
  //   1. Modal GPU result (when credentials present)
  //   2. Existing backend_abc result from train_model.py (when present)
  //   3. Hardcoded fallback (last resort)
  let optimizationSummary: Record<string, unknown>;
  let newOptimizationVersion = currentOptimizationVersion;
  if (
    modalResult?.feature_weights &&
    typeof modalResult.feature_weights === "object" &&
    !Array.isArray(modalResult.feature_weights)
  ) {
    newOptimizationVersion = `opt-gpu-${
      new Date().toISOString().slice(0, 10).replace(/-/g, "")
    }`;
    optimizationSummary = {
      optimization_version: newOptimizationVersion,
      feature_weights: modalResult.feature_weights,
      selected_features: Array.isArray(modalResult.selected_features)
        ? modalResult.selected_features
        : Object.keys(
          modalResult.feature_weights as Record<string, unknown>,
        ),
      class_balance_report: modalResult.class_balance_report &&
          typeof modalResult.class_balance_report === "object"
        ? modalResult.class_balance_report
        : { strategy: "kmeanssmote", false_negative_penalty: 4 },
      abc_enabled: true,
      runtime_mode: capabilities.mode,
      origin: "modal_gpu",
      generated_at: new Date().toISOString(),
    };
  } else if (currentSummaryOrigin === "backend_abc" && currentAbcEnabled) {
    // Backend ABC already published a tuned weight vector. Keep it but
    // refresh the timestamps so the admin dashboard shows recency.
    optimizationSummary = {
      ...currentSummary,
      runtime_mode: capabilities.mode,
      refreshed_at: new Date().toISOString(),
    };
    newOptimizationVersion =
      typeof currentSummary?.optimization_version === "string"
        ? currentSummary.optimization_version
        : currentOptimizationVersion;
  } else {
    newOptimizationVersion = `opt-edge-${
      new Date().toISOString().slice(0, 10).replace(/-/g, "")
    }`;
    optimizationSummary = {
      optimization_version: newOptimizationVersion,
      feature_weights: {
        snowfall_24h: 0.24,
        wind_loading: 0.19,
        slope: 0.17,
        elevation: 0.11,
        temp_gradient: 0.10,
        snowpack: 0.08,
        ram_hardness: 0.04,
        shear_strength: 0.04,
        settlement_rate: 0.03,
        aspect_loading: 0.07,
      },
      selected_features: [
        "snowfall_24h",
        "wind_loading",
        "slope",
        "elevation",
        "temp_gradient",
        "snowpack",
        "ram_hardness",
        "shear_strength",
        "settlement_rate",
        "aspect_loading",
      ],
      class_balance_report: {
        strategy: "edge-lite-resampling",
        false_negative_penalty: 4,
      },
      abc_enabled: false,
      runtime_mode: capabilities.mode,
      origin: "hardcoded_fallback",
      generated_at: new Date().toISOString(),
    };
  }

  await updateModelStatus(supabase, hazardType, {
    optimization_version: newOptimizationVersion,
    optimization_summary: optimizationSummary,
    capabilities: buildRuntimeCapabilitySnapshot(capabilities),
    inference_backend: capabilities.gpuEnabled ? "gpu" : "edge_fallback",
    next_optimization_run: nextOptimizationRunAt(),
  });

  return {
    previousOptimizationVersion: currentOptimizationVersion,
    optimizationVersion: newOptimizationVersion,
    runtimeMode: capabilities.mode,
    capabilitySummary: capabilities.summary,
    optimizationSummary,
  };
}
