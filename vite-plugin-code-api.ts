import type { Plugin } from 'vite';
import { createHmac } from 'crypto';
import { createHash } from 'crypto';
import { execFileSync, spawn } from 'child_process';
import { readFileSync, realpathSync, statSync } from 'fs';
import { resolve, relative } from 'path';
import type { IncomingMessage, ServerResponse } from 'http';

/**
 * Vite dev-server plugin that exposes safe, loopback-only local knowledge APIs.
 *
 * Phase 2 endpoints:
 *  - /api/knowledge-graph/status: freshness and provenance summary
 *  - /api/knowledge-graph/snapshot: validated structural graph + manifest
 *  - /api/knowledge-graph/node?id=...: bounded selected-node retrieval packet
 *  - /api/code: bounded source snippets from graph-derived allowlisted files
 *
 * The browser never starts the Understand command. Refresh remains an
 * operator-controlled workflow, and semantic summaries remain explicit when
 * the external model refresh is unavailable.
 */

const ROOT = realpathSync(process.cwd());
const GRAPH_PATH = resolve(ROOT, '.understand-anything/phase2-structural-graph.json');
const MANIFEST_PATH = resolve(ROOT, '.understand-anything/phase2-structural-manifest.json');

const ALLOWED_PREFIXES = [
  'backend/', 'src/', 'docs/', 'supabase/functions/', 'tests/',
  'config/', 'scripts/',
];

// Denylist zones from AGENTS.md — these files/directories must NEVER appear
// in the graph, source API, or node packets. This is a CRITICAL security boundary.
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

const BLOCKED_EXTENSIONS = new Set([
  '.env', '.env.local', '.env.production', '.env.development',
  '.key', '.pem', '.p12', '.pfx', '.crt', '.cer',
  '.gitignore', '.DS_Store', '.sqlite', '.sqlite3', '.db',
  '.bin', '.pt', '.pth', '.onnx', '.npz', '.npy',
  '.tif', '.tiff', '.zip', '.tar', '.gz', '.mp3', '.mp4',
]);

const BLOCKED_DIR_SEGMENTS = new Set([
  '.git', 'node_modules', '.venv', 'dist', '__pycache__',
  '.understand-anything', '.phase-loop', '.pytest_cache',
  '.fastembed_cache', '.lovable', '.netlify', '.windsurf',
  '.playwright-mcp', '.uv_cache', '.fable5', '.devin',
]);

const MAX_BYTES = 256 * 1024;
const MAX_LINES = 200;
const MAX_NODE_PACKET_EDGES = 200;
const RATE_LIMIT = 60;
const RATE_WINDOW_MS = 60_000;
const requestWindows = new Map<string, { startedAt: number; count: number }>();
let graphPathCache: { mtimeMs: number; paths: Set<string> } | null = null;

interface StructuralGraph {
  nodes?: Array<Record<string, unknown>>;
  edges?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

interface StructuralManifest {
  graphSha256?: string;
  analyzedCommit?: string;
  analyzedAt?: string;
  semanticStatus?: string;
  status?: string;
  worktreeDirty?: boolean;
  worktreeStatusCount?: number;
  worktreeStatusSha256?: string;
  nodeCount?: number;
  edgeCount?: number;
  sourceFileCount?: number;
  sourceHashes?: Array<Record<string, unknown>>;
  verification?: Record<string, unknown>;
  warnings?: string[];
  [key: string]: unknown;
}

export function isLoopbackAddress(address: string | undefined): boolean {
  const normalized = (address || '').replace(/^::ffff:/, '');
  return normalized === '127.0.0.1' || normalized === '::1' || normalized === 'localhost';
}

// HIGH-1: Prevent loopback spoofing via proxy headers.
// Only trust X-Forwarded-For if VITE_TRUST_PROXY is explicitly set.
function getRemoteAddress(request: IncomingMessage): string {
  if (process.env.VITE_TRUST_PROXY === 'true') {
    const forwarded = request.headers['x-forwarded-for'];
    if (typeof forwarded === 'string') {
      const first = forwarded.split(',')[0].trim();
      if (first) return first;
    }
    const realIp = request.headers['x-real-ip'];
    if (typeof realIp === 'string' && realIp.trim()) return realIp.trim();
  }
  return request.socket.remoteAddress || 'unknown';
}

// HIGH-2: Prevent prototype pollution from parsed JSON.
function safeJsonParse(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text);
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const record = parsed as Record<string, unknown>;
    // Strip prototype pollution vectors
    const safe: Record<string, unknown> = {};
    for (const key of Object.keys(record)) {
      if (key !== '__proto__' && key !== 'constructor' && key !== 'prototype') {
        safe[key] = record[key];
      }
    }
    return safe;
  }
  return parsed as Record<string, unknown>;
}

function isDenylisted(relPath: string): boolean {
  const normalized = relPath.replace(/\\/g, '/').toLowerCase();
  return DENYLIST_PATTERNS.some((pattern) => {
    const p = pattern.toLowerCase();
    return normalized === p || normalized.startsWith(p);
  });
}

function isBlocked(relPath: string): boolean {
  if (isDenylisted(relPath)) return true;
  const lower = relPath.toLowerCase();
  for (const ext of BLOCKED_EXTENSIONS) {
    if (lower.endsWith(ext)) return true;
  }
  if (lower.includes('.env.') && !lower.endsWith('.env.example')) return true;
  return relPath.split('/').some((segment) => BLOCKED_DIR_SEGMENTS.has(segment));
}

function isAllowedPrefix(relPath: string): boolean {
  return ALLOWED_PREFIXES.some((prefix) => relPath.startsWith(prefix));
}

function readStructuralGraph(): StructuralGraph | null {
  try {
    return safeJsonParse(readFileSync(GRAPH_PATH, 'utf-8')) as unknown as StructuralGraph;
  } catch {
    return null;
  }
}

function readStructuralManifest(): StructuralManifest | null {
  try {
    const rawText = readFileSync(MANIFEST_PATH, 'utf-8');
    const manifest = safeJsonParse(rawText) as unknown as StructuralManifest;
    // HIGH-3: Validate manifest HMAC if present
    if (manifest.manifestHmac) {
      const secret = process.env.KG_MANIFEST_HMAC_SECRET;
      if (!secret) {
        console.warn('[code-api] KG_MANIFEST_HMAC_SECRET not set — using local-dev default. Set this secret in production.');
      }
      const effectiveSecret = secret || 'local-dev-default-secret';
      // Reconstruct manifest without manifestHmac, matching Python's
      // json.dumps(manifest_for_hmac, indent=2, sort_keys=True) + "\n"
      const { manifestHmac, ...rest } = manifest;
      const sortedKeys = Object.keys(rest as Record<string, unknown>).sort();
      const reconstructedObj: Record<string, unknown> = {};
      for (const key of sortedKeys) {
        reconstructedObj[key] = (rest as Record<string, unknown>)[key];
      }
      // Match Python json.dumps(indent=2, sort_keys=True) formatting
      const reconstructedText = pythonJsonDumps(reconstructedObj, 2) + '\n';
      const expectedHmac = createHmac('sha256', effectiveSecret)
        .update(reconstructedText)
        .digest('hex');
      if (expectedHmac !== manifestHmac) {
        console.warn('[code-api] Manifest HMAC mismatch — manifest may be tampered');
        return null;
      }
    }
    return manifest;
  } catch {
    return null;
  }
}

// Match Python's json.dumps(obj, indent=2, sort_keys=True) output format.
// Python uses ": " as key-value separator and ",\n" + indent for item separation.
function pythonJsonDumps(obj: unknown, indent: number): string {
  return pythonJsonDumpsInner(obj, indent, 0);
}

function pythonJsonDumpsInner(obj: unknown, indent: number, depth: number): string {
  const pad = ' '.repeat(indent * depth);
  const childPad = ' '.repeat(indent * (depth + 1));
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'boolean') return obj ? 'true' : 'false';
  if (typeof obj === 'number') return JSON.stringify(obj);
  if (typeof obj === 'string') return JSON.stringify(obj);
  if (Array.isArray(obj)) {
    if (obj.length === 0) return '[]';
    const items = obj.map((item) => childPad + pythonJsonDumpsInner(item, indent, depth + 1));
    return '[\n' + items.join(',\n') + '\n' + pad + ']';
  }
  if (typeof obj === 'object') {
    const record = obj as Record<string, unknown>;
    const keys = Object.keys(record).sort();
    if (keys.length === 0) return '{}';
    const items = keys.map((k) => childPad + JSON.stringify(k) + ': ' + pythonJsonDumpsInner(record[k], indent, depth + 1));
    return '{\n' + items.join(',\n') + '\n' + pad + '}';
  }
  return JSON.stringify(obj);
}

function graphIncludedPaths(): Set<string> {
  try {
    const mtimeMs = statSync(GRAPH_PATH).mtimeMs;
    if (graphPathCache?.mtimeMs === mtimeMs) return graphPathCache.paths;
    const graph = readStructuralGraph();
    const paths = new Set<string>();
    for (const node of graph?.nodes || []) {
      if (typeof node.filePath === 'string' && !isDenylisted(node.filePath)) paths.add(node.filePath);
    }
    graphPathCache = { mtimeMs, paths };
    return paths;
  } catch {
    return new Set();
  }
}

export function safeResolvePath(relPath: string): string | null {
  if (
    !relPath
    || relPath.includes('\0')
    || relPath.includes('..')
    || relPath.includes('\\')
    || relPath.startsWith('/')
    || /^[a-zA-Z]:/.test(relPath)
    || isBlocked(relPath)
    || !isAllowedPrefix(relPath)
  ) {
    return null;
  }

  try {
    const candidate = resolve(ROOT, relPath);
    const canonical = realpathSync(candidate);
    const canonicalRelative = relative(ROOT, canonical).replace(/\\/g, '/');
    if (canonicalRelative.startsWith('..') || canonicalRelative.includes('..')) return null;
    if (!isAllowedPrefix(canonicalRelative) || isBlocked(canonicalRelative)) return null;
    const allowedPaths = graphIncludedPaths();
    if (allowedPaths.size > 0 && !allowedPaths.has(canonicalRelative)) return null;
    return canonical;
  } catch {
    return null;
  }
}

function withinRequestBudget(key: string): boolean {
  const now = Date.now();
  const current = requestWindows.get(key);
  if (!current || now - current.startedAt >= RATE_WINDOW_MS) {
    requestWindows.set(key, { startedAt: now, count: 1 });
    return true;
  }
  if (current.count >= RATE_LIMIT) return false;
  current.count += 1;
  return true;
}

function json(res: ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(JSON.stringify(payload));
}

function readSnippet(
  absPath: string,
  startLine: number,
  lineCount: number,
): { content: string; endLine: number; truncated: boolean } | null {
  let stats: ReturnType<typeof statSync>;
  try {
    stats = statSync(absPath);
  } catch {
    return null;
  }
  if (!stats.isFile() || stats.size > MAX_BYTES) return null;

  const content = readFileSync(absPath, 'utf-8');
  const lines = content.split('\n');
  const start = Math.max(1, Math.min(startLine, lines.length));
  const count = Math.min(MAX_LINES, Math.max(1, lineCount));
  const end = Math.min(start + count - 1, lines.length);
  return {
    content: lines.slice(start - 1, end).join('\n'),
    endLine: end,
    truncated: end < lines.length,
  };
}

function gitOutput(...args: string[]): string {
  try {
    return execFileSync('git', args, {
      cwd: ROOT,
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 1500,
    }).toString();
  } catch {
    return '';
  }
}

function currentCommit(): string | null {
  return gitOutput('rev-parse', 'HEAD').trim() || null;
}

function graphStatus(): Record<string, unknown> {
  const manifest = readStructuralManifest();
  const graph = readStructuralGraph();
  if (!manifest || !graph) throw new Error('Phase 2 structural snapshot is unavailable');
  const graphCommit = typeof manifest.analyzedCommit === 'string' ? manifest.analyzedCommit : null;
  const liveCommit = currentCommit();
  const currentStatus = gitOutput('status', '--short', '--untracked-files=all');
  const currentStatusSha256 = createHash('sha256').update(currentStatus).digest('hex');
  const worktreeDirty = Boolean(currentStatus.trim());
  const worktreeChangedSinceSnapshot = Boolean(
    manifest.worktreeStatusSha256 && manifest.worktreeStatusSha256 !== currentStatusSha256,
  );
  const freshness = graphCommit && liveCommit
    ? graphCommit === liveCommit ? 'current' : 'stale'
    : 'unknown';
  const semanticStatus = manifest.semanticStatus || 'unknown';
  const detail = freshness === 'stale'
    ? 'Graph snapshot commit does not match the current checkout.'
    : worktreeChangedSinceSnapshot
      ? 'The checkout changed after this snapshot; uncommitted/untracked changes are not authoritative.'
      : freshness === 'current' && worktreeDirty
        ? 'Graph snapshot commit matches, but the checkout is dirty; uncommitted/untracked changes are not authoritative.'
        : freshness === 'current' && semanticStatus !== 'complete'
          ? 'Structural snapshot matches the checkout; semantic summaries are unavailable.'
          : freshness === 'current'
            ? 'Graph snapshot commit matches the current checkout.'
            : 'Graph freshness could not be established.';
  return {
    source: 'local-api',
    freshness,
    graphHash: manifest.graphSha256 || createHash('sha256').update(JSON.stringify(graph)).digest('hex'),
    graphAnalyzedAt: manifest.analyzedAt || null,
    graphCommit,
    currentCommit: liveCommit,
    nodeCount: manifest.nodeCount || graph.nodes?.length || 0,
    edgeCount: manifest.edgeCount || graph.edges?.length || 0,
    semanticStatus,
    worktreeDirty,
    worktreeStatusCount: currentStatus.split('\n').filter(Boolean).length,
    snapshotWorktreeStatusSha256: manifest.worktreeStatusSha256 || null,
    currentWorktreeStatusSha256: currentStatusSha256,
    worktreeChangedSinceSnapshot,
    detail,
  };
}

function snapshotPayload(): { graph: StructuralGraph; manifest: StructuralManifest } {
  const graph = readStructuralGraph();
  const manifest = readStructuralManifest();
  if (!graph || !manifest) throw new Error('Phase 2 structural snapshot is unavailable');
  return { graph, manifest };
}

// Cached node-by-ID map for the current snapshot (rebuilt on graph file change)
type GraphNodeRecord = Record<string, unknown>;
let cachedNodeMap: Map<string, GraphNodeRecord> | null = null;
let cachedNodeMapKey: string | null = null;

function getNodeMap(): Map<string, GraphNodeRecord> {
  // Key by graph file mtime+size so rebuilds invalidate the cache even if
  // the builder emits the same snapshotId. Falls back to graph hash if present.
  let cacheKey: string;
  try {
    const stat = statSync(GRAPH_PATH);
    cacheKey = `${stat.mtimeMs}:${stat.size}`;
  } catch {
    // File not readable — use manifest snapshotId as fallback
    const manifest = readStructuralManifest();
    cacheKey = typeof manifest?.snapshotId === 'string' ? manifest.snapshotId : 'none';
  }
  // Also incorporate manifest graphSha256 if available for extra safety
  const manifest = readStructuralManifest();
  if (typeof manifest?.graphSha256 === 'string') {
    cacheKey += `:${manifest.graphSha256}`;
  }
  if (cachedNodeMap && cachedNodeMapKey === cacheKey) return cachedNodeMap;
  const g = readStructuralGraph();
  const nodes = g?.nodes || [];
  cachedNodeMap = new Map();
  for (const node of nodes) {
    const id = String(node.id);
    cachedNodeMap.set(id, node);
  }
  cachedNodeMapKey = cacheKey;
  return cachedNodeMap;
}

export function nodePacket(nodeId: string): Record<string, unknown> | null {
  const { graph, manifest } = snapshotPayload();
  const edges = graph.edges || [];
  const nodeMap = getNodeMap();
  const node = nodeMap.get(nodeId);
  if (!node) return null;
  // Denylist enforcement: block requests for denylist zone nodes
  if (typeof node.filePath === 'string' && isDenylisted(node.filePath)) return null;
  // O(E) single pass — filter edges connected to this node, checking denylist via node map
  const connectedEdges: GraphNodeRecord[] = [];
  for (const edge of edges) {
    const source = String(edge.source);
    const target = String(edge.target);
    if (source !== nodeId && target !== nodeId) continue;
    const sourceNode = nodeMap.get(source);
    const targetNode = nodeMap.get(target);
    if (sourceNode && typeof sourceNode.filePath === 'string' && isDenylisted(sourceNode.filePath)) continue;
    if (targetNode && typeof targetNode.filePath === 'string' && isDenylisted(targetNode.filePath)) continue;
    connectedEdges.push(edge);
    if (connectedEdges.length >= MAX_NODE_PACKET_EDGES) break;
  }
  const relatedEdges = connectedEdges;
  const relatedIds = new Set<string>();
  let totalConnectedCount = 0;
  for (const edge of edges) {
    const source = String(edge.source);
    const target = String(edge.target);
    if (source !== nodeId && target !== nodeId) continue;
    totalConnectedCount++;
    relatedIds.add(source);
    relatedIds.add(target);
  }
  for (const edge of relatedEdges) {
    relatedIds.add(String(edge.source));
    relatedIds.add(String(edge.target));
  }
  // Filter related nodes to exclude denylist zones — use node map instead of linear scan
  const relatedNodes: GraphNodeRecord[] = [];
  for (const candidateId of relatedIds) {
    const candidate = nodeMap.get(candidateId);
    if (!candidate) continue;
    if (typeof candidate.filePath === 'string' && isDenylisted(candidate.filePath)) continue;
    relatedNodes.push(candidate);
  }
  const sourceHash = typeof node.filePath === 'string'
    ? (manifest.sourceHashes || []).find((item) => item.path === node.filePath)?.sha256 || null
    : null;
  return {
    node,
    relatedNodes,
    relatedEdges,
    sourceHash,
    provenance: graphStatus(),
    truncated: totalConnectedCount > relatedEdges.length,
  };
}

function requireLoopback(request: IncomingMessage, response: ServerResponse): boolean {
  if (!isLoopbackAddress(getRemoteAddress(request))) {
    json(response, 403, { error: 'Knowledge APIs are restricted to loopback development access' });
    return false;
  }
  const rateKey = getRemoteAddress(request);
  if (!withinRequestBudget(rateKey)) {
    json(response, 429, { error: 'Knowledge API request limit exceeded' });
    return false;
  }
  return true;
}

export function codeApiPlugin(): Plugin {
  return {
    name: 'safe-code-api',
    configureServer(server) {
      server.middlewares.use('/api/knowledge-graph/status', (req, res) => {
        if (!requireLoopback(req, res)) return;
        if (req.method !== 'GET') {
          json(res, 405, { error: 'Method not allowed' });
          return;
        }
        try {
          json(res, 200, { provenance: graphStatus() });
        } catch {
          json(res, 503, { error: 'Graph provenance is unavailable' });
        }
      });

      server.middlewares.use('/api/knowledge-graph/snapshot', (req, res) => {
        if (!requireLoopback(req, res)) return;
        if (req.method !== 'GET') {
          json(res, 405, { error: 'Method not allowed' });
          return;
        }
        try {
          json(res, 200, snapshotPayload());
        } catch {
          json(res, 503, { error: 'Graph snapshot is unavailable' });
        }
      });

      // Rebuild endpoint — triggers the structural refresh script.
      // Loopback-only. Returns immediately with status; rebuild runs async.
      // The client polls /status to detect completion.
      let rebuildInProgress = false;
      server.middlewares.use('/api/knowledge-graph/rebuild', (req, res) => {
        if (!requireLoopback(req, res)) return;
        if (req.method !== 'POST') {
          json(res, 405, { error: 'Method not allowed' });
          return;
        }
        if (rebuildInProgress) {
          json(res, 409, { error: 'Rebuild already in progress', status: 'running' });
          return;
        }
        rebuildInProgress = true;
        const scriptPath = resolve(ROOT, 'scripts/refresh_knowledge_graph_structural.sh');
        const child = spawn('bash', [scriptPath], {
          cwd: ROOT,
          stdio: 'ignore',
          detached: false,
        });
        child.on('exit', (code) => {
          rebuildInProgress = false;
          console.log(`[code-api] Structural rebuild exited with code ${code}`);
        });
        child.on('error', (err) => {
          rebuildInProgress = false;
          console.error('[code-api] Structural rebuild failed:', err.message);
        });
        json(res, 202, { status: 'started', message: 'Rebuild initiated. Poll /status for completion.' });
      });

      server.middlewares.use('/api/knowledge-graph/node', (req, res) => {
        if (!requireLoopback(req, res)) return;
        if (req.method !== 'GET') {
          json(res, 405, { error: 'Method not allowed' });
          return;
        }
        const url = new URL(req.url || '', 'http://localhost');
        const nodeId = url.searchParams.get('id') || '';
        if (!nodeId || nodeId.length > 512 || nodeId.includes('\0')) {
          json(res, 400, { error: 'A valid node id is required' });
          return;
        }
        try {
          const packet = nodePacket(nodeId);
          if (!packet) {
            json(res, 404, { error: 'Node not found in structural snapshot' });
            return;
          }
          json(res, 200, packet);
        } catch {
          json(res, 503, { error: 'Node retrieval packet is unavailable' });
        }
      });

      server.middlewares.use('/api/code', (req, res) => {
        if (!requireLoopback(req, res)) return;
        if (req.method !== 'GET') {
          json(res, 405, { error: 'Method not allowed' });
          return;
        }

        const url = new URL(req.url || '', 'http://localhost');
        const relPath = url.searchParams.get('path') || '';
        const parsedStart = Number.parseInt(url.searchParams.get('start') || '1', 10);
        const parsedCount = Number.parseInt(url.searchParams.get('lines') || '50', 10);
        const startLine = Number.isFinite(parsedStart) ? parsedStart : 1;
        const lineCount = Number.isFinite(parsedCount) ? parsedCount : 50;
        const absPath = safeResolvePath(relPath);
        if (!absPath) {
          json(res, 403, { error: 'Access denied: path is blocked or outside the graph-derived allowlist' });
          return;
        }

        const result = readSnippet(absPath, startLine, lineCount);
        if (!result) {
          json(res, 404, { error: 'File not found, binary, or too large' });
          return;
        }

        json(res, 200, {
          snippet: {
            path: relPath,
            startLine: Math.max(1, startLine),
            endLine: result.endLine,
            content: result.content,
            truncated: result.truncated,
          },
        });
      });
    },
  };
}
