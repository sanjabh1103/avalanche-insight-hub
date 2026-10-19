export const DENYLIST_PATTERNS = [
  'backend/common/verification_exit_gates.py',
  'backend/common/sar_acceptance_policy.py',
  'backend/common/label_governance.py',
  'backend/common/risk_math.py',
  'backend/train_model.py',
  'supabase/config.toml',
  'backend/reproduction/',
  'backend/common/snowpack_physics.py',
] as const;

export const ALLOWED_PERSPECTIVES = [
  'architecture',
  'ml-pipeline',
  'data-flow',
  'security-gates',
  'tests',
  'release-evidence',
] as const;

export const ALLOWED_AUDIENCES = [
  'novice',
  'ml_expert',
  'technical_customer',
] as const;

export const ALLOWED_DEPTHS = ['briefing', 'working', 'deep'] as const;

export const MAX_QUESTION_LENGTH = 2000;
export const MAX_CONTEXT_SIZE_KB = 10;

export interface ModelRequestContext {
  maxDepth?: number;
  includeSource?: boolean;
  audience?: string;
  depth?: string;
}

export interface ModelRequest {
  nodeId?: string;
  perspective?: string;
  question?: string;
  context?: ModelRequestContext;
}

export interface ValidatedModelRequest extends Omit<ModelRequest, 'perspective'> {
  perspective: string;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
  sanitized?: ValidatedModelRequest;
}

function decodeRepeated(value: string): string | null {
  let decoded = value;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) return decoded;
      decoded = next;
    } catch {
      return null;
    }
  }
  return decoded;
}

export function normalizePolicyPath(filePath: string): string | null {
  const decoded = decodeRepeated(filePath);
  if (decoded === null) return null;

  // FIX-9 (NEW-4): Reject null bytes — they can bypass substring/prefix checks.
  if (decoded.includes('\0')) return null;

  const segments: string[] = [];
  for (const segment of decoded.replace(/\\/g, '/').split('/')) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      if (segments.length > 0 && segments[segments.length - 1] !== '..') {
        segments.pop();
      } else {
        segments.push(segment);
      }
      continue;
    }
    segments.push(segment);
  }

  return segments.join('/').toLowerCase();
}

function normalizeReference(value: string): string | null {
  const decoded = decodeRepeated(value);
  return decoded === null ? null : decoded.replace(/\\/g, '/').toLowerCase();
}

export function isDenylisted(filePath: string): boolean {
  const normalized = normalizePolicyPath(filePath);
  if (normalized === null) return true;
  // FIX-4 (H-2): Use exact/prefix matching to align with vite-plugin-code-api.ts.
  // Substring matching was overly broad (fail-closed but inconsistent).
  // findDenylistViolations retains substring matching for content scanning.
  return DENYLIST_PATTERNS.some((pattern) => normalized === pattern || normalized.startsWith(pattern));
}

export function findDenylistViolations(value: string): string[] {
  const normalized = normalizeReference(value);
  if (normalized === null) return [...DENYLIST_PATTERNS];
  return DENYLIST_PATTERNS.filter((pattern) => normalized.includes(pattern));
}

// G3: Expanded secret patterns based on industry best practices.
// Sources: Red Hat prodsec-skills, litellm secret_redaction, trufflehog patterns.
const SECRET_PATTERNS = [
  /(?:password|passwd|pwd)\s*[:=]\s*["'][^"']{4,}["']/gi,
  /(?:api[_-]?key|apikey)\s*[:=]\s*["'][^"']{10,}["']/gi,
  /(?:secret|token)\s*[:=]\s*["'][^"']{10,}["']/gi,
  /sk-[a-zA-Z0-9]{20,}/g, // OpenAI
  /AIza[a-zA-Z0-9_-]{35}/g, // Google API key
  /AKIA[0-9A-Z]{16}/g, // AWS access key ID
  /-----BEGIN[A-Z ]*PRIVATE KEY-----/g, // PEM private key header
  /(?:postgresql|postgres|mysql|mongodb(?:\+srv)?|redis|amqp):\/\/[^\s"']{10,}/gi, // DB connection strings
  /eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}/g, // JWT tokens
  /ghp_[a-zA-Z0-9]{36}/g, // GitHub personal access token
  /gho_[a-zA-Z0-9]{36}/g, // GitHub OAuth token
];

export function validateRequest(body: unknown): ValidationResult {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return { valid: false, error: 'Request body must be an object' };
  }
  const req = body as Record<string, unknown>;

  if (req.nodeId !== undefined && req.nodeId !== null && typeof req.nodeId !== 'string') {
    return { valid: false, error: 'nodeId must be a string' };
  }
  if (req.question !== undefined && req.question !== null && typeof req.question !== 'string') {
    return { valid: false, error: 'question must be a string' };
  }

  const nodeId = typeof req.nodeId === 'string' ? req.nodeId : undefined;
  const question = typeof req.question === 'string' ? req.question : undefined;
  if (!nodeId?.trim() && !question?.trim()) {
    return { valid: false, error: 'Either nodeId or question is required' };
  }

  if (nodeId?.includes('\0')) {
    return { valid: false, error: 'nodeId contains null bytes' };
  }
  if (nodeId && nodeId.length > 200) {
    return { valid: false, error: 'nodeId must be less than 200 characters' };
  }

  if (req.perspective !== undefined && req.perspective !== null) {
    if (
      typeof req.perspective !== 'string' ||
      !ALLOWED_PERSPECTIVES.includes(req.perspective as typeof ALLOWED_PERSPECTIVES[number])
    ) {
      return {
        valid: false,
        error: `perspective must be one of: ${ALLOWED_PERSPECTIVES.join(', ')}`,
      };
    }
  }

  if (question?.includes('\0')) {
    return { valid: false, error: 'question contains null bytes' };
  }
  if (question && question.length > MAX_QUESTION_LENGTH) {
    return { valid: false, error: `question must be less than ${MAX_QUESTION_LENGTH} characters` };
  }

  let context: ModelRequestContext | undefined;
  if (req.context !== undefined && req.context !== null) {
    if (typeof req.context !== 'object' || Array.isArray(req.context)) {
      return { valid: false, error: 'context must be an object' };
    }
    const contextRecord = req.context as Record<string, unknown>;
    let contextStr: string;
    try {
      contextStr = JSON.stringify(contextRecord);
    } catch {
      return { valid: false, error: 'context must be JSON serializable' };
    }
    if (contextStr.length > MAX_CONTEXT_SIZE_KB * 1024) {
      return {
        valid: false,
        error: `context must be less than ${MAX_CONTEXT_SIZE_KB}KB when serialized`,
      };
    }

    if (
      contextRecord.maxDepth !== undefined &&
      (typeof contextRecord.maxDepth !== 'number' || !Number.isInteger(contextRecord.maxDepth) ||
        contextRecord.maxDepth < 0 || contextRecord.maxDepth > 5)
    ) {
      return { valid: false, error: 'context.maxDepth must be an integer between 0 and 5' };
    }
    if (
      contextRecord.includeSource !== undefined && typeof contextRecord.includeSource !== 'boolean'
    ) {
      return { valid: false, error: 'context.includeSource must be a boolean' };
    }
    if (
      contextRecord.audience !== undefined &&
      (typeof contextRecord.audience !== 'string' ||
        !ALLOWED_AUDIENCES.includes(contextRecord.audience as typeof ALLOWED_AUDIENCES[number]))
    ) {
      return {
        valid: false,
        error: `context.audience must be one of: ${ALLOWED_AUDIENCES.join(', ')}`,
      };
    }
    if (
      contextRecord.depth !== undefined &&
      (typeof contextRecord.depth !== 'string' ||
        !ALLOWED_DEPTHS.includes(contextRecord.depth as typeof ALLOWED_DEPTHS[number]))
    ) {
      return { valid: false, error: `context.depth must be one of: ${ALLOWED_DEPTHS.join(', ')}` };
    }

    context = {
      maxDepth: typeof contextRecord.maxDepth === 'number' ? contextRecord.maxDepth : undefined,
      includeSource: typeof contextRecord.includeSource === 'boolean'
        ? contextRecord.includeSource
        : undefined,
      audience: typeof contextRecord.audience === 'string' ? contextRecord.audience : undefined,
      depth: typeof contextRecord.depth === 'string' ? contextRecord.depth : undefined,
    };
  }

  return {
    valid: true,
    sanitized: {
      nodeId,
      perspective: typeof req.perspective === 'string' ? req.perspective : 'architecture',
      question,
      context,
    },
  };
}

export function filterOutput(
  content: string,
  filePath?: string,
): { filtered: string; redacted: boolean; denylistViolations: string[] } {
  const fileViolations = filePath ? findDenylistViolations(filePath) : [];
  if (filePath && (isDenylisted(filePath) || fileViolations.length > 0)) {
    return {
      filtered: '[CONTENT REDACTED - DENYLIST ZONE]',
      redacted: true,
      denylistViolations: fileViolations.length > 0 ? fileViolations : [filePath],
    };
  }

  let filtered = content;
  let redacted = false;
  for (const pattern of SECRET_PATTERNS) {
    pattern.lastIndex = 0;
    if (pattern.test(filtered)) {
      pattern.lastIndex = 0;
      filtered = filtered.replace(pattern, '[REDACTED]');
      redacted = true;
    }
  }

  const violations = findDenylistViolations(filtered);
  if (violations.length > 0) {
    return {
      filtered: '[REDACTED-PATH]',
      redacted: true,
      denylistViolations: violations,
    };
  }

  return { filtered, redacted, denylistViolations: [] };
}

export function sanitizeForPrompt(text: string): string {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$/g, '\\$')
    .replace(/<[^>]*>/g, '')
    .substring(0, 1000);
}

export function hasApprovedGraphContext(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  const snapshotId = candidate.snapshotId;
  const graphHash = candidate.graphHash;
  const evidenceRefs = candidate.evidenceRefs;
  return typeof snapshotId === 'string' && snapshotId.trim().length > 0 &&
    typeof graphHash === 'string' && /^[a-f0-9]{32,}$/i.test(graphHash) &&
    Array.isArray(evidenceRefs) && evidenceRefs.length > 0 &&
    evidenceRefs.every((ref) => typeof ref === 'string' && ref.trim().length > 0);
}

export function canInvokeModel(
  value: unknown,
  apiKey: string | undefined,
  endpointEnabled = false,
): boolean {
  return endpointEnabled && Boolean(apiKey) && hasApprovedGraphContext(value);
}

/**
 * Parse Gemini provider-reported usage metadata from the API response.
 * Returns authoritative token counts when available, or null if metadata
 * is missing/malformed (caller should fall back to character-based estimate).
 *
 * See: https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1beta1/GenerateContentResponse
 */
export interface GeminiUsageMetadata {
  promptTokenCount: number;
  candidatesTokenCount: number;
  totalTokenCount: number;
  thoughtsTokenCount?: number;
  cachedContentTokenCount?: number;
}

export interface ParsedGeminiUsage {
  inputTokens: number;
  outputTokens: number;
  thinkingTokens: number;
  cachedTokens: number;
  totalTokens: number;
  usageSource: 'provider';
}

/** Input for cost calculation — accepts both provider and estimate sources. */
export interface GeminiCostInput {
  inputTokens: number;
  outputTokens: number;
  thinkingTokens: number;
  cachedTokens: number;
  totalTokens: number;
  usageSource: 'provider' | 'estimate';
  modelName?: string;
}

/**
 * Model price catalog — per 1M tokens.
 * When a new model is added to GEMINI_MODEL_NAME, add its pricing here.
 * Prices sourced from Google's current standard paid-tier pricing page.
 * Historical entries are retained for interpreting older usage records, but
 * must not be selected for new requests after their shutdown date.
 * If a model is not found, the calculator falls back to Gemini 3.5 Flash pricing
 * and logs a warning so the operator can add the correct prices.
 */
interface ModelPricing {
  inputPerMillion: number;
  outputPerMillion: number;
  thinkingPerMillion: number;
  cachedPerMillion: number;
}

const MODEL_PRICE_CATALOG: Record<string, ModelPricing> = {
  'gemini-3.6-flash': {
    inputPerMillion: 1.50,
    outputPerMillion: 7.50,
    thinkingPerMillion: 7.50,
    cachedPerMillion: 0.15,
  },
  'gemini-3.5-flash': {
    inputPerMillion: 1.50,
    outputPerMillion: 9.00,
    thinkingPerMillion: 9.00,
    cachedPerMillion: 0.15,
  },
  'gemini-3.5-flash-lite': {
    inputPerMillion: 0.30,
    outputPerMillion: 2.50,
    thinkingPerMillion: 2.50,
    cachedPerMillion: 0.03,
  },
  'gemini-3.1-flash-lite': {
    inputPerMillion: 0.25,
    outputPerMillion: 1.50,
    thinkingPerMillion: 1.50,
    cachedPerMillion: 0.025,
  },
  'gemini-2.5-flash': {
    inputPerMillion: 0.30,
    outputPerMillion: 2.50,
    thinkingPerMillion: 2.50,
    cachedPerMillion: 0.03,
  },
  'gemini-2.5-flash-lite': {
    inputPerMillion: 0.10,
    outputPerMillion: 0.40,
    thinkingPerMillion: 0.40,
    cachedPerMillion: 0.01,
  },
  // Historical price retained for reading old usage records. Gemini 2.0
  // Flash was shut down on 2026-06-01 and must not be used for new requests.
  'gemini-2.0-flash': {
    inputPerMillion: 0.10,
    outputPerMillion: 0.40,
    thinkingPerMillion: 0.40,
    cachedPerMillion: 0.025,
  },
  'gemini-1.5-flash': {
    inputPerMillion: 0.075,
    outputPerMillion: 0.30,
    thinkingPerMillion: 0.30,
    cachedPerMillion: 0.01875,
  },
  'gemini-1.5-pro': {
    inputPerMillion: 1.25,
    outputPerMillion: 5.00,
    thinkingPerMillion: 5.00,
    cachedPerMillion: 0.3125,
  },
};

const DEFAULT_PRICING: ModelPricing = MODEL_PRICE_CATALOG['gemini-3.5-flash'];

export function parseGeminiUsageMetadata(
  payload: unknown,
): ParsedGeminiUsage | null {
  if (!payload || typeof payload !== 'object') return null;
  const usage = (payload as Record<string, unknown>)?.usageMetadata;
  if (!usage || typeof usage !== 'object') return null;
  const u = usage as Record<string, unknown>;
  if (typeof u.promptTokenCount !== 'number' || typeof u.candidatesTokenCount !== 'number') {
    return null;
  }
  if (typeof u.totalTokenCount !== 'number') {
    return null;
  }
  return {
    inputTokens: u.promptTokenCount,
    outputTokens: u.candidatesTokenCount,
    thinkingTokens: typeof u.thoughtsTokenCount === 'number' ? u.thoughtsTokenCount : 0,
    cachedTokens: typeof u.cachedContentTokenCount === 'number' ? u.cachedContentTokenCount : 0,
    totalTokens: u.totalTokenCount,
    usageSource: 'provider',
  };
}

/**
 * Calculate cost from parsed usage metadata.
 * Uses the model price catalog — if the model name is not found, falls back to
 * Gemini 3.5 Flash pricing and logs a warning.
 */
export function calculateGeminiCost(usage: GeminiCostInput): number {
  const modelName = usage.modelName || 'gemini-3.5-flash';
  const pricing = MODEL_PRICE_CATALOG[modelName];
  if (!pricing) {
    console.warn(
      `[knowledgeGraphModelPolicy] No price catalog entry for model "${modelName}". ` +
      `Falling back to Gemini 3.5 Flash pricing. Add the model to MODEL_PRICE_CATALOG.`,
    );
  }
  const p = pricing || DEFAULT_PRICING;
  // cachedContentTokenCount is a subset of promptTokenCount. Charge the
  // non-cached prompt tokens at the input rate and the cached subset at the
  // cache rate; do not double-charge cached tokens.
  const inputTokens = Math.max(usage.inputTokens, 0);
  const cachedTokens = Math.min(Math.max(usage.cachedTokens, 0), inputTokens);
  const outputTokens = Math.max(usage.outputTokens, 0);
  const thinkingTokens = Math.max(usage.thinkingTokens, 0);
  return (
    ((inputTokens - cachedTokens) / 1_000_000) * p.inputPerMillion +
    (outputTokens / 1_000_000) * p.outputPerMillion +
    (thinkingTokens / 1_000_000) * p.thinkingPerMillion +
    (cachedTokens / 1_000_000) * p.cachedPerMillion
  );
}

/** Get the pricing for a model (for display/logging). Returns default if not found. */
export function getModelPricing(modelName: string): ModelPricing {
  return MODEL_PRICE_CATALOG[modelName] || DEFAULT_PRICING;
}
