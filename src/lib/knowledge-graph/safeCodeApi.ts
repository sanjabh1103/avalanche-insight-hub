/**
 * Safe local codebase API client.
 *
 * In development, a Vite middleware plugin (vite-plugin-code-api.ts)
 * exposes `/api/code/*` endpoints that read files from an allowlisted
 * set of directories. In production builds, the live API is unavailable
 * and all calls return a structured "unavailable" response so the UI
 * can degrade gracefully to the bundled graph data.
 *
 * Security boundaries:
 *  - Only allowlisted root directories are readable (backend/, src/, docs/, supabase/functions/)
 *  - Path traversal is rejected (no .., no absolute paths, no null bytes)
 *  - File size limit: 256 KiB per read
 *  - Line range limit: max 200 lines per request
 *  - Blocked extensions: .env, .key, .pem, .p12, .gitignore, .DS_Store
 *  - Blocked directories: .git/, node_modules/, .venv/, dist/, __pycache__/
 */

export interface CodeSnippet {
  path: string;
  startLine: number;
  endLine: number;
  content: string;
  truncated: boolean;
}

export interface CodeApiResponse {
  available: boolean;
  snippet?: CodeSnippet;
  error?: string;
}

const BLOCKED_EXTENSIONS = new Set([
  '.env', '.env.local', '.env.production', '.env.development',
  '.key', '.pem', '.p12', '.pfx', '.crt', '.cer',
  '.gitignore', '.DS_Store', '.sqlite', '.sqlite3', '.db',
  '.bin', '.pt', '.pth', '.onnx', '.npz', '.npy',
  '.tif', '.tiff', '.zip', '.tar', '.gz', '.mp3', '.mp4',
]);

const BLOCKED_DIR_PREFIXES = [
  '.git/', 'node_modules/', '.venv/', 'dist/', '__pycache__/',
  '.understand-anything/', '.phase-loop/', '.pytest_cache/',
  '.fastembed_cache/', '.lovable/', '.netlify/', '.windsurf/',
  '.playwright-mcp/', '.uv_cache/', '.fable5/', '.devin/',
];

const ALLOWED_PREFIXES = [
  'backend/', 'src/', 'docs/', 'supabase/functions/', 'tests/',
  'config/', 'scripts/',
];

const MAX_BYTES = 256 * 1024;
const MAX_LINES = 200;

function isBlockedPath(relativePath: string): boolean {
  const normalized = relativePath.replace(/^\.\//, '');
  for (const prefix of BLOCKED_DIR_PREFIXES) {
    if (normalized.startsWith(prefix) || normalized.includes('/' + prefix)) {
      return true;
    }
  }
  const lower = normalized.toLowerCase();
  for (const ext of BLOCKED_EXTENSIONS) {
    if (lower.endsWith(ext)) return true;
  }
  if (lower.includes('.env.') && !lower.endsWith('.env.example')) return true;
  return false;
}

function isAllowedPath(relativePath: string): boolean {
  const normalized = relativePath.replace(/^\.\//, '');
  return ALLOWED_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

function validatePath(relativePath: string): { valid: boolean; reason?: string } {
  if (!relativePath || typeof relativePath !== 'string') {
    return { valid: false, reason: 'Path is required' };
  }
  if (relativePath.includes('\0')) {
    return { valid: false, reason: 'Null bytes are not allowed' };
  }
  if (relativePath.startsWith('/') || /^[a-zA-Z]:/.test(relativePath)) {
    return { valid: false, reason: 'Absolute paths are not allowed' };
  }
  if (relativePath.includes('..')) {
    return { valid: false, reason: 'Path traversal is not allowed' };
  }
  if (isBlockedPath(relativePath)) {
    return { valid: false, reason: 'Path is blocked by security policy' };
  }
  if (!isAllowedPath(relativePath)) {
    return { valid: false, reason: 'Path is outside allowlisted directories' };
  }
  return { valid: true };
}

export function validateCodePath(relativePath: string): { valid: boolean; reason?: string } {
  return validatePath(relativePath);
}

export async function fetchCodeSnippet(
  relativePath: string,
  startLine = 1,
  lineCount = MAX_LINES,
): Promise<CodeApiResponse> {
  const validation = validatePath(relativePath);
  if (!validation.valid) {
    return { available: false, error: validation.reason };
  }

  const clampedStart = Math.max(1, Math.floor(startLine));
  const clampedCount = Math.min(MAX_LINES, Math.max(1, Math.floor(lineCount)));
  const params = new URLSearchParams({
    path: relativePath,
    start: String(clampedStart),
    lines: String(clampedCount),
  });

  try {
    const response = await fetch(`/api/code?${params.toString()}`);
    if (response.status === 404) {
      return { available: false, error: 'Live code API is not available in this build' };
    }
    if (response.status === 403) {
      const body = await response.json().catch(() => ({}));
      return { available: false, error: body.error || 'Access denied' };
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      return { available: false, error: body.error || `HTTP ${response.status}` };
    }
    const data = await response.json();
    return { available: true, snippet: data.snippet };
  } catch {
    return { available: false, error: 'Network error or dev server not running' };
  }
}

export const CODE_API_LIMITS = {
  MAX_BYTES,
  MAX_LINES,
  ALLOWED_PREFIXES,
  BLOCKED_EXTENSIONS: Array.from(BLOCKED_EXTENSIONS),
  BLOCKED_DIR_PREFIXES,
} as const;
