import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { RuntimeCapabilities } from "./handlers/types.ts";

export type RuntimeMode = "full" | "gpu_only" | "sar_only" | "edge_fallback";

export class RequestValidationError extends Error {
  status: number;

  constructor(message: string, status = 400) {
    super(message);
    this.name = "RequestValidationError";
    this.status = status;
  }
}

export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

// Reverse geocode using Nominatim (free, no API key)
export async function reverseGeocode(lat: number, lng: number): Promise<string> {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=10`,
      {
        headers: { "User-Agent": "AvalancheCompass/1.0" },
      },
    );
    if (!res.ok) return "";
    const data = await res.json();
    return data.address?.state || data.address?.county || data.name || "";
  } catch {
    return "";
  }
}

export {
  incrementGeminiUsage,
  isGeminiSpendCapExceeded,
} from "../_shared/auth.ts";


export async function invokeEdgeFunction(
  functionName: string,
  payload: Record<string, unknown>,
  authorizationHeader: string | null,
  apiKeyHeader: string | null,
) {
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const response = await fetch(`${supabaseUrl}/functions/v1/${functionName}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authorizationHeader ??
        `Bearer ${Deno.env.get("SUPABASE_ANON_KEY")!}`,
      apikey: apiKeyHeader ?? Deno.env.get("SUPABASE_ANON_KEY")!,
    },
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${functionName} failed (${response.status}): ${text}`);
  }

  if (!text) return {};
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    console.warn(
      `${functionName} returned non-JSON 200 response:`,
      text.slice(0, 200),
    );
    return {};
  }
}

export function flagEnabled(name: string, defaultValue = true) {
  const raw = Deno.env.get(name);
  if (raw == null) return defaultValue;
  return !["0", "false", "off", "no"].includes(raw.toLowerCase());
}

export function detectRuntimeCapabilities(): RuntimeCapabilities {
  const modalWorkerUrl = Deno.env.get("MODAL_WORKER_URL") ?? null;
  const modalWorkerToken = Deno.env.get("MODAL_WORKER_TOKEN") ??
    Deno.env.get("MODAL_API_TOKEN") ?? null;
  const sarCredentialsPresent = Boolean(
    Deno.env.get("EARTHDATA_USERNAME") && Deno.env.get("EARTHDATA_PASSWORD") ||
      Deno.env.get("ASF_API_TOKEN") ||
      Deno.env.get("ASF_USERNAME") && Deno.env.get("ASF_PASSWORD"),
  );
  const gpuCredentialsPresent = Boolean(
    modalWorkerUrl &&
      (modalWorkerToken || flagEnabled("MODAL_ALLOW_ANON", false)),
  );
  const sarEnabled = flagEnabled("FEATURE_SENTINEL_SAR", true) &&
    sarCredentialsPresent;
  const gpuEnabled = flagEnabled("FEATURE_GPU_WORKER", true) &&
    gpuCredentialsPresent;
  const mode: RuntimeMode = sarEnabled && gpuEnabled
    ? "full"
    : gpuEnabled
    ? "gpu_only"
    : sarEnabled
    ? "sar_only"
    : "edge_fallback";
  const summary = mode === "full"
    ? "Full SAR + GPU"
    : mode === "gpu_only"
    ? "GPU snowpack + Edge SAR fallback"
    : mode === "sar_only"
    ? "SAR enabled + Edge inference"
    : "Edge-only fallback";

  return {
    mode,
    summary,
    sarEnabled,
    gpuEnabled,
    sarCredentialsPresent,
    gpuCredentialsPresent,
    modalWorkerUrl,
    modalWorkerToken,
  };
}

export async function invokeModalWorker(
  capabilities: RuntimeCapabilities,
  endpoint: string,
  payload: Record<string, unknown>,
  timeoutMs = 15000,
) {
  if (!capabilities.gpuEnabled || !capabilities.modalWorkerUrl) {
    return null;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(
      `${capabilities.modalWorkerUrl.replace(/\/$/, "")}/${
        endpoint.replace(/^\//, "")
      }`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(capabilities.modalWorkerToken
            ? { Authorization: `Bearer ${capabilities.modalWorkerToken}` }
            : {}),
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      },
    );
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${endpoint} failed (${response.status}): ${text}`);
    }
    return text ? JSON.parse(text) as Record<string, unknown> : {};
  } catch (error) {
    console.warn(
      `Modal worker ${endpoint} fallback:`,
      (error as Error).message,
    );
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function invokeWorkerEndpoint(
  capabilities: RuntimeCapabilities,
  endpoint: string,
  aliases: string[],
  payload: Record<string, unknown>,
  timeoutMs = 15000,
) {
  for (const candidate of [endpoint, ...aliases]) {
    const result = await invokeModalWorker(
      capabilities,
      candidate,
      payload,
      timeoutMs,
    );
    if (result !== null) {
      return { endpoint: candidate, result };
    }
  }
  return null;
}

export function toNumber(value: unknown, fallback = 0) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function extractEvaluationManifest(body: Record<string, unknown>) {
  const inlineManifest = body.evaluation_manifest;
  if (
    inlineManifest && typeof inlineManifest === "object" &&
    !Array.isArray(inlineManifest)
  ) {
    return inlineManifest as Record<string, unknown>;
  }

  const rawManifest = body.evaluation_manifest_json;
  if (typeof rawManifest === "string" && rawManifest.trim()) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawManifest);
    } catch {
      throw new RequestValidationError(
        `evaluation_manifest_json is not valid JSON: ${
          String(rawManifest).slice(0, 200)
        }`,
      );
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new RequestValidationError(
        "evaluation_manifest_json must decode to a JSON object",
      );
    }
    return parsed as Record<string, unknown>;
  }

  return null;
}

export function incrementSemver(version: string | null | undefined) {
  const currentVersion = version || "v1.0.0";
  const versionMatch = currentVersion.match(/v(\d+)\.(\d+)\.(\d+)/);
  const major = versionMatch ? parseInt(versionMatch[1]) : 1;
  const minor = versionMatch ? parseInt(versionMatch[2]) : 0;
  const patch = versionMatch ? parseInt(versionMatch[3]) + 1 : 1;
  return `v${major}.${minor}.${patch}`;
}

export function normalizeAsfScenes(payload: unknown) {
  if (Array.isArray(payload)) return payload as Record<string, unknown>[];
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (Array.isArray(record.features)) {
      return record.features as Record<string, unknown>[];
    }
    if (Array.isArray(record.results)) {
      return record.results as Record<string, unknown>[];
    }
  }
  return [];
}

export function nextOptimizationRunAt() {
  const now = new Date();
  const next = new Date(now);
  next.setUTCDate(now.getUTCDate() + ((7 - now.getUTCDay()) % 7 || 7));
  next.setUTCHours(2, 0, 0, 0);
  return next.toISOString();
}

export function buildRuntimeCapabilitySnapshot(
  capabilities: RuntimeCapabilities,
) {
  return {
    mode: capabilities.mode,
    summary: capabilities.summary,
    runtime_mode: capabilities.mode,
    runtime_summary: capabilities.summary,
    sar_enabled: capabilities.sarEnabled,
    gpu_enabled: capabilities.gpuEnabled,
  };
}

export function parsePositiveInteger(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    if (Number.isFinite(parsed) && parsed > 0) {
      return Math.trunc(parsed);
    }
  }
  return null;
}

export function parseBooleanValue(value: unknown) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string" && value.trim()) {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    if (["0", "false", "no", "off"].includes(normalized)) return false;
  }
  return null;
}

export function buildForecastGridPrecomputePayload(
  body: Record<string, unknown>,
  jobId: string,
  hazardType: string,
) {
  const payload: Record<string, unknown> = {
    job_id: jobId,
    compute_job_id: jobId,
    hazard_type: hazardType,
    requested_by: "trigger-job",
    request_type: "forecast_grid_precompute",
    dataset_snapshot_id: "latest",
  };

  if (typeof body.artifact_dir === "string" && body.artifact_dir.trim()) {
    payload.artifact_dir = body.artifact_dir.trim();
  }

  if (typeof body.region_key === "string" && body.region_key.trim()) {
    payload.region_key = body.region_key.trim();
  }

  const forecastHours = parsePositiveInteger(body.forecast_hours);
  if (forecastHours !== null) {
    payload.forecast_hours = forecastHours;
  }

  const gridSize = parsePositiveInteger(body.grid_size);
  if (gridSize !== null) {
    payload.grid_size = gridSize;
  }

  const lifeboatMode = parseBooleanValue(body.lifeboat_mode);
  if (lifeboatMode === true) {
    payload.lifeboat_mode = true;
    payload.lifeboat_profile = typeof body.lifeboat_profile === "string" &&
        body.lifeboat_profile.trim()
      ? body.lifeboat_profile.trim()
      : "proof72";
  }

  for (const key of [
    "skip_tree_shap",
    "skip_shap_cache",
    "skip_runout_generation",
    "skip_compatibility_write",
    "emit_stage_metrics",
  ]) {
    const parsed = parseBooleanValue(body[key]);
    if (parsed !== null) {
      payload[key] = parsed;
    }
  }

  return payload;
}

export function computeJobStatusForResult(
  result: Record<string, unknown>,
): "running" | "completed" {
  const workerResult = result.workerResult as Record<string, unknown> | null | undefined;
  if (!workerResult || typeof workerResult !== "object") {
    return "completed";
  }
  const status = typeof workerResult.status === "string"
    ? workerResult.status.trim().toLowerCase()
    : "";
  const callId = typeof workerResult.call_id === "string" &&
      workerResult.call_id.trim()
    ? workerResult.call_id.trim()
    : typeof workerResult.modal_call_id === "string" &&
        workerResult.modal_call_id.trim()
    ? workerResult.modal_call_id.trim()
    : null;
  return status === "accepted" && Boolean(callId) ? "running" : "completed";
}

export function extractWorkerLinkage(
  workerResult: Record<string, unknown> | null | undefined,
  fallbackComputeJobId: string,
  requestedArtifactDir: unknown,
) {
  const normalizedArtifactDir = typeof requestedArtifactDir === "string" &&
      requestedArtifactDir.trim()
    ? requestedArtifactDir.trim()
    : null;
  const computeJobId =
    typeof workerResult?.compute_job_id === "string" &&
        workerResult.compute_job_id.trim()
      ? workerResult.compute_job_id.trim()
      : fallbackComputeJobId;
  const modalCallId =
    typeof workerResult?.modal_call_id === "string" &&
        workerResult.modal_call_id.trim()
      ? workerResult.modal_call_id.trim()
      : typeof workerResult?.call_id === "string" && workerResult.call_id.trim()
      ? workerResult.call_id.trim()
      : null;
  const artifactDir =
    typeof workerResult?.artifact_dir === "string" &&
        workerResult.artifact_dir.trim()
      ? workerResult.artifact_dir.trim()
      : normalizedArtifactDir;
  const forecastRunId =
    typeof workerResult?.forecast_run_id === "string" &&
        workerResult.forecast_run_id.trim()
      ? workerResult.forecast_run_id.trim()
      : null;
  return {
    compute_job_id: computeJobId,
    modal_call_id: modalCallId,
    artifact_dir: artifactDir,
    forecast_run_id: forecastRunId,
  };
}

export async function updateModelStatus(
  supabase: any,
  hazardType: string,
  patch: Record<string, unknown>,
) {
  const { data: modelStatus, error: findErr } = await supabase
    .from("model_status")
    .select("id")
    .eq("hazard_type", hazardType)
    .limit(1)
    .maybeSingle();

  if (findErr) {
    console.error("updateModelStatus find failed:", findErr);
    throw new Error(`Failed to find model_status: ${findErr.message}`);
  }

  if (modelStatus?.id) {
    const { error } = await supabase.from("model_status").update(patch).eq(
      "id",
      modelStatus.id,
    );
    if (error) {
      console.error("updateModelStatus update failed:", error);
      throw new Error(`Failed to update model_status: ${error.message}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  } else {
    console.warn(
      `updateModelStatus: no model_status row for hazard_type=${hazardType}; skipping update`,
    );
  }
}
