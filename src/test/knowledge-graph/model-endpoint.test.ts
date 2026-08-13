// Tests for the knowledge-graph-model edge function security controls.
// These tests validate the pure functions (denylist, validation, output filtering)
// without requiring a live Supabase instance or Gemini API key.

import { describe, expect, it } from 'vitest';

// Denylist patterns (must match the edge function)
const DENYLIST_PATTERNS = [
  'backend/common/verification_exit_gates.py',
  'backend/common/sar_acceptance_policy.py',
  'backend/common/label_governance.py',
  'backend/common/risk_math.py',
  'backend/train_model.py',
  'supabase/config.toml',
  'backend/reproduction/',
  'backend/common/snowpack_physics.py',
];

function isDenylisted(filePath: string): boolean {
  const normalized = filePath.replace(/\\/g, '/').toLowerCase();
  return DENYLIST_PATTERNS.some((p) => {
    const pattern = p.toLowerCase();
    return normalized === pattern || normalized.startsWith(pattern);
  });
}

const ALLOWED_PERSPECTIVES = [
  'architecture',
  'ml-pipeline',
  'data-flow',
  'security-gates',
  'tests',
  'release-evidence',
];

const MAX_QUESTION_LENGTH = 2000;
const MAX_CONTEXT_SIZE_KB = 10;

interface ModelRequest {
  nodeId?: string;
  perspective?: string;
  question?: string;
  context?: Record<string, unknown>;
}

function validateRequest(body: unknown): { valid: boolean; error?: string; sanitized?: ModelRequest } {
  if (!body || typeof body !== 'object') {
    return { valid: false, error: 'Request body must be an object' };
  }
  const req = body as Record<string, unknown>;

  if (!req.nodeId && !req.question) {
    return { valid: false, error: 'Either nodeId or question is required' };
  }

  if (req.nodeId !== undefined && req.nodeId !== null) {
    if (typeof req.nodeId !== 'string') {
      return { valid: false, error: 'nodeId must be a string' };
    }
    if (req.nodeId.includes('\0')) {
      return { valid: false, error: 'nodeId contains null bytes' };
    }
    if (req.nodeId.length > 200) {
      return { valid: false, error: 'nodeId must be less than 200 characters' };
    }
  }

  if (req.perspective !== undefined && req.perspective !== null) {
    if (typeof req.perspective !== 'string' || !ALLOWED_PERSPECTIVES.includes(req.perspective)) {
      return { valid: false, error: `perspective must be one of: ${ALLOWED_PERSPECTIVES.join(', ')}` };
    }
  }

  if (req.question !== undefined && req.question !== null) {
    if (typeof req.question !== 'string') {
      return { valid: false, error: 'question must be a string' };
    }
    if (req.question.includes('\0')) {
      return { valid: false, error: 'question contains null bytes' };
    }
    if (req.question.length > MAX_QUESTION_LENGTH) {
      return { valid: false, error: `question must be less than ${MAX_QUESTION_LENGTH} characters` };
    }
  }

  if (req.context !== undefined && req.context !== null) {
    if (typeof req.context !== 'object' || Array.isArray(req.context)) {
      return { valid: false, error: 'context must be an object' };
    }
    const contextStr = JSON.stringify(req.context);
    if (contextStr.length > MAX_CONTEXT_SIZE_KB * 1024) {
      return { valid: false, error: `context must be less than ${MAX_CONTEXT_SIZE_KB}KB when serialized` };
    }
  }

  return {
    valid: true,
    sanitized: {
      nodeId: typeof req.nodeId === 'string' ? req.nodeId : undefined,
      perspective: typeof req.perspective === 'string' ? req.perspective : 'architecture',
      question: typeof req.question === 'string' ? req.question : undefined,
      context: req.context as ModelRequest['context'],
    },
  };
}

const SECRET_PATTERNS = [
  /(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]/gi,
  /(?:api[_-]?key|apikey)\s*[:=]\s*['"][^'"]{10,}['"]/gi,
  /(?:secret|token)\s*[:=]\s*['"][^'"]{10,}['"]/gi,
  /sk-[a-zA-Z0-9]{20,}/g,
  /AIza[a-zA-Z0-9_-]{35}/g,
];

function filterOutput(content: string, filePath?: string): { filtered: string; redacted: boolean; denylistViolations: string[] } {
  const violations: string[] = [];

  if (filePath && isDenylisted(filePath)) {
    violations.push(filePath);
    return {
      filtered: '[CONTENT REDACTED - DENYLIST ZONE]',
      redacted: true,
      denylistViolations: violations,
    };
  }

  let filtered = content;
  let redacted = false;
  for (const pattern of SECRET_PATTERNS) {
    if (pattern.test(filtered)) {
      filtered = filtered.replace(pattern, '[REDACTED]');
      redacted = true;
    }
  }

  for (const pattern of DENYLIST_PATTERNS) {
    if (filtered.toLowerCase().includes(pattern.toLowerCase())) {
      const regex = new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      filtered = filtered.replace(regex, '[REDACTED-PATH]');
      redacted = true;
      violations.push(pattern);
    }
  }

  return { filtered, redacted, denylistViolations: violations };
}

function sanitizeForPrompt(text: string): string {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$/g, '\\$')
    .replace(/<[^>]*>/g, '')
    .substring(0, 1000);
}

// ============================================================================
// TESTS
// ============================================================================

describe('denylist enforcement', () => {
  it('blocks all 8 AGENTS.md denylist zones', () => {
    expect(isDenylisted('backend/common/verification_exit_gates.py')).toBe(true);
    expect(isDenylisted('backend/common/sar_acceptance_policy.py')).toBe(true);
    expect(isDenylisted('backend/common/label_governance.py')).toBe(true);
    expect(isDenylisted('backend/common/risk_math.py')).toBe(true);
    expect(isDenylisted('backend/train_model.py')).toBe(true);
    expect(isDenylisted('supabase/config.toml')).toBe(true);
    expect(isDenylisted('backend/common/snowpack_physics.py')).toBe(true);
  });

  it('blocks denylist directory and all files within it', () => {
    expect(isDenylisted('backend/reproduction/')).toBe(true);
    expect(isDenylisted('backend/reproduction/run_all.py')).toBe(true);
    expect(isDenylisted('backend/reproduction/subdir/file.py')).toBe(true);
    expect(isDenylisted('backend/reproduction/swiss_ravafcast/evaluate.py')).toBe(true);
  });

  it('is case-insensitive', () => {
    expect(isDenylisted('BACKEND/COMMON/RISK_MATH.PY')).toBe(true);
    expect(isDenylisted('Backend/Common/Risk_Math.py')).toBe(true);
  });

  it('handles Windows-style path separators', () => {
    expect(isDenylisted('backend\\common\\risk_math.py')).toBe(true);
    expect(isDenylisted('backend\\reproduction\\file.py')).toBe(true);
  });

  it('does not block non-denylist files', () => {
    expect(isDenylisted('backend/common/features.py')).toBe(false);
    expect(isDenylisted('src/App.tsx')).toBe(false);
    expect(isDenylisted('backend/tests/test_risk_math.py')).toBe(false);
    expect(isDenylisted('backend/common/utils.py')).toBe(false);
  });
});

describe('request validation', () => {
  it('requires either nodeId or question', () => {
    expect(validateRequest({}).valid).toBe(false);
    expect(validateRequest({ nodeId: 'test' }).valid).toBe(true);
    expect(validateRequest({ question: 'test' }).valid).toBe(true);
    expect(validateRequest({ nodeId: 'test', question: 'test' }).valid).toBe(true);
  });

  it('rejects non-string nodeId', () => {
    expect(validateRequest({ nodeId: 123 }).valid).toBe(false);
    expect(validateRequest({ nodeId: true }).valid).toBe(false);
    expect(validateRequest({ nodeId: [] }).valid).toBe(false);
  });

  it('rejects nodeId with null bytes', () => {
    expect(validateRequest({ nodeId: 'test\0malicious' }).valid).toBe(false);
  });

  it('rejects nodeId longer than 200 chars', () => {
    expect(validateRequest({ nodeId: 'a'.repeat(201) }).valid).toBe(false);
    expect(validateRequest({ nodeId: 'a'.repeat(200) }).valid).toBe(true);
  });

  it('validates perspective against allowlist', () => {
    expect(validateRequest({ nodeId: 'test', perspective: 'architecture' }).valid).toBe(true);
    expect(validateRequest({ nodeId: 'test', perspective: 'ml-pipeline' }).valid).toBe(true);
    expect(validateRequest({ nodeId: 'test', perspective: 'invalid' }).valid).toBe(false);
  });

  it('rejects question with null bytes', () => {
    expect(validateRequest({ question: 'test\0inject' }).valid).toBe(false);
  });

  it('rejects question longer than 2000 chars', () => {
    expect(validateRequest({ question: 'a'.repeat(2001) }).valid).toBe(false);
    expect(validateRequest({ question: 'a'.repeat(2000) }).valid).toBe(true);
  });

  it('rejects context larger than 10KB', () => {
    const largeContext = { data: 'a'.repeat(11 * 1024) };
    expect(validateRequest({ nodeId: 'test', context: largeContext }).valid).toBe(false);
  });

  it('rejects non-object context', () => {
    expect(validateRequest({ nodeId: 'test', context: 'string' }).valid).toBe(false);
    expect(validateRequest({ nodeId: 'test', context: [1, 2] }).valid).toBe(false);
  });

  it('rejects non-object body', () => {
    expect(validateRequest('string').valid).toBe(false);
    expect(validateRequest(123).valid).toBe(false);
    expect(validateRequest(null).valid).toBe(false);
    expect(validateRequest(undefined).valid).toBe(false);
  });

  it('sanitizes request with defaults', () => {
    const result = validateRequest({ nodeId: 'test' });
    expect(result.valid).toBe(true);
    expect(result.sanitized?.perspective).toBe('architecture');
  });
});

describe('output filtering', () => {
  it('redacts denylist zone content', () => {
    const result = filterOutput('some content', 'backend/common/risk_math.py');
    expect(result.filtered).toBe('[CONTENT REDACTED - DENYLIST ZONE]');
    expect(result.redacted).toBe(true);
    expect(result.denylistViolations).toContain('backend/common/risk_math.py');
  });

  it('redacts secrets from output', () => {
    const result = filterOutput('password = "secret123" and api_key = "sk-abc123def456ghi789jkl012mno345pqr"');
    expect(result.redacted).toBe(true);
    expect(result.filtered).not.toContain('secret123');
    expect(result.filtered).toContain('[REDACTED]');
  });

  it('redacts OpenAI-style keys', () => {
    const result = filterOutput('The key is sk-abcdefghijklmnopqrstuvwxyz1234567890');
    expect(result.redacted).toBe(true);
    expect(result.filtered).not.toContain('sk-abcdefghijklmnopqrstuvwxyz1234567890');
  });

  it('redacts Google API keys', () => {
    const result = filterOutput('Google key: AIzaSyA1234567890_-bcdefghijklmnopqrstuv');
    expect(result.redacted).toBe(true);
    expect(result.filtered).not.toContain('AIzaSyA1234567890_-bcdefghijklmnopqrstuv');
  });

  it('redacts denylist file paths from output', () => {
    const result = filterOutput('The risk math is in backend/common/risk_math.py');
    expect(result.redacted).toBe(true);
    expect(result.filtered).not.toContain('backend/common/risk_math.py');
    expect(result.filtered).toContain('[REDACTED-PATH]');
    expect(result.denylistViolations).toContain('backend/common/risk_math.py');
  });

  it('does not redact clean content', () => {
    const result = filterOutput('This is a normal explanation of the code architecture.');
    expect(result.redacted).toBe(false);
    expect(result.denylistViolations).toHaveLength(0);
  });
});

describe('prompt sanitization', () => {
  it('escapes backticks', () => {
    const result = sanitizeForPrompt('code with `backticks`');
    expect(result).toContain('\\`backticks\\`');
  });

  it('escapes dollar signs', () => {
    const result = sanitizeForPrompt('costs $100 and $200');
    expect(result).toContain('\\$100');
  });

  it('strips HTML-like tags', () => {
    const result = sanitizeForPrompt("text with <script>alert('xss')</script> tags");
    expect(result).not.toContain('<script>');
    expect(result).not.toContain('</script>');
  });

  it('limits length to 1000 chars', () => {
    const result = sanitizeForPrompt('a'.repeat(2000));
    expect(result.length).toBe(1000);
  });
});
