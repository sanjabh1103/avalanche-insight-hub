// Client-side API for the knowledge-graph-model edge function.
// Calls the Supabase Edge Function to get model-generated explanations.

import { supabase } from '@/integrations/supabase/client';

export interface ModelExplanationRequest {
  nodeId?: string;
  perspective?: string;
  question?: string;
  context?: {
    maxDepth?: number;
    includeSource?: boolean;
    audience?: string;
    depth?: string;
  };
}

export interface ModelExplanationResponse {
  requestId: string;
  timestamp: string;
  userRole: string;
  explanation: {
    nodeId?: string;
    nodeName?: string;
    perspective: string;
    audience: string;
    depth: string;
    summary: string;
    sections: Array<{
      heading: string;
      body: string;
      claimCategory: 'fact' | 'inference' | 'stale' | 'blocked';
    }>;
  };
  provenance: {
    graphHash: string | null;
    freshness: 'current' | 'stale' | 'unknown';
    worktreeDirty: boolean;
  };
  modelUsage: {
    provider: string;
    model: string;
    tokensUsed: number;
    costUsd: number;
  };
  security: {
    denylistViolations: string[];
    secretsRedacted: boolean;
    rateLimitRemaining: number;
  };
}

export interface ModelExplanationError {
  error: string;
  retryAfter?: number;
}

// G9: 30-second timeout to prevent indefinite loading state.
const FETCH_TIMEOUT_MS = 30_000;

export async function fetchModelExplanation(
  request: ModelExplanationRequest,
): Promise<ModelExplanationResponse | ModelExplanationError> {
  const fetchPromise = supabase.functions.invoke('knowledge-graph-model', {
    method: 'POST',
    body: request,
  });

  const timeoutPromise = new Promise<never>((_, reject) => {
    setTimeout(() => reject(new Error('Request timeout after 30 seconds')), FETCH_TIMEOUT_MS);
  });

  let result;
  try {
    result = await Promise.race([fetchPromise, timeoutPromise]);
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Request timeout' };
  }

  const { data, error } = result;

  if (error) {
    return { error: error.message || 'Failed to call model endpoint' };
  }

  return data as ModelExplanationResponse;
}

export function isModelError(
  response: ModelExplanationResponse | ModelExplanationError,
): response is ModelExplanationError {
  return 'error' in response;
}
