export interface RuntimeCapabilities {
  mode: "full" | "gpu_only" | "sar_only" | "edge_fallback";
  summary: string;
  sarEnabled: boolean;
  gpuEnabled: boolean;
  sarCredentialsPresent: boolean;
  gpuCredentialsPresent: boolean;
  modalWorkerUrl: string | null;
  modalWorkerToken: string | null;
}

export interface HandlerArgs {
  supabase: any;
  body: Record<string, any>;
  capabilities: RuntimeCapabilities;
  hazardType: string;
  bbox: number[] | null;
  job: { id: string };
  callerAuthorization: string | null;
  callerApiKey: string | null;
  evaluateReleaseContext: {
    evaluationManifest: Record<string, unknown> | null;
    referenceSetKey: string | null;
    adminAudit: Record<string, unknown> | null;
  } | null;
}

export type JobHandler = (args: HandlerArgs) => Promise<Record<string, unknown>>;
