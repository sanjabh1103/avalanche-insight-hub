import { HandlerArgs } from "./types.ts";
import {
  invokeWorkerEndpoint,
  buildForecastGridPrecomputePayload,
  extractWorkerLinkage,
  RequestValidationError,
} from "../utils.ts";

export async function handleRetrainAvalancheModel({
  capabilities,
  hazardType,
  job,
}: HandlerArgs): Promise<Record<string, unknown>> {
  const workerInvocation = await invokeWorkerEndpoint(
    capabilities,
    "train-mtslstm",
    ["train"],
    {
      job_id: job.id,
      hazard_type: hazardType,
      requested_by: "trigger-job",
      request_type: "retrain_avalanche_model",
      dataset_snapshot_id: "latest",
      epochs: 50,
      early_stopping: true,
      minimum_epochs_before_early_stopping: 10,
      patience_early_stopping: 7,
      shadow_mode: true,
      promotion_rule: "strict_pss_gt_rf_and_brier_lte_rf",
      sar_release_gate_passed: false,
    },
    20000,
  );
  return {
    simulated: !workerInvocation,
    hazard_type: hazardType,
    training_status: workerInvocation ? "submitted" : "queued",
    runtimeMode: capabilities.mode,
    workerEndpoint: workerInvocation?.endpoint || null,
    workerResult: workerInvocation?.result || null,
  };
}

export async function handleForecastGridPrecompute({
  body,
  capabilities,
  hazardType,
  job,
}: HandlerArgs): Promise<Record<string, unknown>> {
  const workerInvocation = await invokeWorkerEndpoint(
    capabilities,
    "infer-mtslstm",
    [],
    buildForecastGridPrecomputePayload(body, job.id, hazardType),
    20000,
  );
  const workerLinkage = extractWorkerLinkage(
    workerInvocation?.result || null,
    job.id,
    body.artifact_dir,
  );
  return {
    simulated: !workerInvocation,
    hazard_type: hazardType,
    forecast_grid_status: workerInvocation ? "submitted" : "queued",
    runtimeMode: capabilities.mode,
    workerEndpoint: workerInvocation?.endpoint || null,
    workerResult: workerInvocation?.result || null,
    ...workerLinkage,
  };
}

export async function handleEvaluateRelease({
  body,
  capabilities,
  hazardType,
  job,
  evaluateReleaseContext,
}: HandlerArgs): Promise<Record<string, unknown>> {
  const evaluationManifest = evaluateReleaseContext?.evaluationManifest ?? null;
  const referenceSetKey = evaluateReleaseContext?.referenceSetKey ?? null;
  if (!evaluationManifest && !referenceSetKey) {
    throw new RequestValidationError(
      "evaluate_release requires reference_set_key or evaluation_manifest_json/evaluation_manifest",
    );
  }
  const workerPayload: Record<string, unknown> = evaluationManifest
    ? { ...evaluationManifest }
    : { reference_set_key: referenceSetKey };
  if (
    typeof body.prediction_model_version === "string" &&
    body.prediction_model_version.trim()
  ) {
    workerPayload.prediction_model_version = body.prediction_model_version.trim();
  }
  const workerInvocation = await invokeWorkerEndpoint(
    capabilities,
    "evaluate-release",
    [],
    {
      ...workerPayload,
      job_id: job.id,
      hazard_type: hazardType,
      requested_by: "trigger-job",
      request_type: "evaluate_release",
      release_target: "sar_unet",
    },
    20000,
  );
  return {
    simulated: !workerInvocation,
    hazard_type: hazardType,
    evaluation_status: workerInvocation ? "submitted" : "queued",
    runtimeMode: capabilities.mode,
    workerEndpoint: workerInvocation?.endpoint || null,
    workerResult: workerInvocation?.result || null,
  };
}

export async function handleMlTrain({
  capabilities,
  hazardType,
  job,
}: HandlerArgs): Promise<Record<string, unknown>> {
  const workerInvocation = await invokeWorkerEndpoint(
    capabilities,
    "train-mtslstm",
    ["train"],
    {
      job_id: job.id,
      hazard_type: hazardType,
      requested_by: "trigger-job",
      request_type: "ml_train",
      dataset_snapshot_id: "latest",
      epochs: 50,
      early_stopping: true,
      minimum_epochs_before_early_stopping: 10,
      patience_early_stopping: 7,
      shadow_mode: true,
      promotion_rule: "strict_pss_gt_rf_and_brier_lte_rf",
      sar_release_gate_passed: false,
    },
    20000,
  );
  return {
    simulated: !workerInvocation,
    hazard_type: hazardType,
    training_status: workerInvocation ? "submitted" : "queued",
    runtimeMode: capabilities.mode,
    workerEndpoint: workerInvocation?.endpoint || null,
    workerResult: workerInvocation?.result || null,
  };
}
