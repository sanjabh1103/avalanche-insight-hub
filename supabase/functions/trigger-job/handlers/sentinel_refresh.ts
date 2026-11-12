import { HandlerArgs } from "./types.ts";
import {
  normalizeAsfScenes,
  invokeWorkerEndpoint,
  toNumber,
  buildRuntimeCapabilitySnapshot,
  updateModelStatus,
} from "../utils.ts";

export async function handleSentinelRefresh({
  supabase,
  body,
  capabilities,
  hazardType,
  bbox,
  job,
}: HandlerArgs): Promise<Record<string, unknown>> {
  const searchBbox = bbox || [38.5, -107.5, 40.5, -105.5];
  try {
    const asfUrl =
      `https://api.daac.asf.alaska.edu/services/search/param?platform=Sentinel-1&processingLevel=GRD_HD&bbox=${
        searchBbox[1]
      },${searchBbox[0]},${searchBbox[3]},${searchBbox[2]}&start=${
        new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0]
      }&end=${
        new Date().toISOString().split("T")[0]
      }&output=json&maxResults=5`;
    const asfRes = await fetch(asfUrl);

    if (asfRes.ok) {
      const scenes = normalizeAsfScenes(await asfRes.json());
      const sceneCount = scenes.length;
      let detectionsPreviewed = 0;
      let detectionsPersisted = 0;
      let workerEndpoint: string | null = null;
      let workerResult: Record<string, unknown> | null = null;
      let fallbackUsed = true;

      if (
        sceneCount > 1 && capabilities.sarEnabled && capabilities.gpuEnabled
      ) {
        const workerInvocation = await invokeWorkerEndpoint(
          capabilities,
          "sar-segment",
          ["sar-detect"],
          {
            job_id: job.id,
            hazard_type: hazardType,
            bbox: searchBbox,
            scenes,
            shadow_mode: true,
            persist_events: true,
            training_eligible: false,
            training_eligible_reason: "sar_unet_shadow_mode",
          },
          20000,
        );
        if (workerInvocation?.result) {
          workerEndpoint = workerInvocation.endpoint;
          workerResult = workerInvocation.result;
          detectionsPreviewed = Array.isArray(workerResult.detections)
            ? workerResult.detections.length
            : 0;
          detectionsPersisted = Math.max(
            0,
            Math.round(toNumber(workerResult.persisted_events, 0)),
          );
          fallbackUsed = false;
        }
      }

      const maskAssetRefs =
        workerResult && Array.isArray(workerResult.mask_asset_refs)
          ? workerResult.mask_asset_refs.filter((item): item is string =>
            typeof item === "string"
          )
          : [];
      const satelliteStats = {
        last_refresh_at: new Date().toISOString(),
        scenes_found: sceneCount,
        detections_previewed: detectionsPreviewed,
        detections_persisted: detectionsPersisted,
        mode: capabilities.mode,
        worker_endpoint: workerEndpoint,
        shadow_mode: workerResult?.shadow_mode !== false,
        mask_asset_refs: maskAssetRefs.slice(0, 10),
        fallback_used: fallbackUsed,
      };
      await updateModelStatus(supabase, hazardType, {
        capabilities: buildRuntimeCapabilitySnapshot(capabilities),
        sar_pipeline_version: workerEndpoint
          ? String(workerResult?.model_version || "sar_unet_shadow_v1")
          : capabilities.sarEnabled
          ? "sentinel_refresh_preview_only_v1"
          : "edge-sar-fallback-v1",
        satellite_detection_stats: satelliteStats,
      });

      return {
        scenesFound: sceneCount,
        source: "ASF Vertex",
        detectionsPreviewed,
        detectionsPersisted,
        detections: workerResult?.detections || [],
        maskAssetRefs,
        runtimeMode: capabilities.mode,
        capabilitySummary: capabilities.summary,
        workerEndpoint,
        shadowMode: workerResult?.shadow_mode !== false,
        fallbackUsed,
      };
    } else {
      return {
        message: "ASF API returned non-OK, using conservative fallback",
        scenesFound: 0,
        runtimeMode: capabilities.mode,
        fallbackUsed: true,
      };
    }
  } catch (e) {
    return {
      message: `ASF fetch failed: ${(e as Error).message}`,
      runtimeMode: capabilities.mode,
      fallbackUsed: true,
    };
  }
}
