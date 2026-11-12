import { HandlerArgs } from "./types.ts";
import { invokeEdgeFunction } from "../utils.ts";

export async function handleStaticPrecompute(_args: HandlerArgs): Promise<Record<string, unknown>> {
  return { simulated: true, regionsComputed: 12 };
}

export async function handleFieldReportEnrichment(_args: HandlerArgs): Promise<Record<string, unknown>> {
  return { simulated: true, createdEvent: false };
}

export async function handleIngestEvent({
  body,
  callerAuthorization,
  callerApiKey,
}: HandlerArgs): Promise<Record<string, unknown>> {
  return await invokeEdgeFunction(
    "ingest-event",
    body,
    callerAuthorization,
    callerApiKey,
  );
}
