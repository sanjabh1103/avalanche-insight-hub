/**
 * Load and query the Understand Anything knowledge graph.
 *
 * Local development starts with the bundled graph as a safe fallback, then
 * replaces it with the loopback snapshot endpoint when a validated Phase 2
 * structural snapshot is available. Production does not load this page.
 *
 * FIX-5 (H-3): The bundled graph is loaded via a dev-only dynamic import to
 * prevent it from being included in the production JS bundle. The static
 * import was replaced because Vite cannot tree-shake dynamic imports gated
 * by import.meta.env.DEV, so the graph JSON stays out of production builds.
 */

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  filePath?: string;
  summary?: string;
  tags?: string[];
  complexity?: string;
  language?: string;
  startLine?: number;
  endLine?: number;
  sourceSha256?: string;
  [key: string]: unknown;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  direction?: string;
  weight?: number;
  lineNumber?: number;
}

export interface GraphLayer {
  id: string;
  name: string;
  description: string;
  nodeIds: string[];
}

export interface GraphTourStep {
  order: number;
  title: string;
  description: string;
  nodeIds: string[];
  languageLesson?: string;
}

export interface KnowledgeGraph {
  version: string;
  kind: string;
  project: {
    name: string;
    languages: string[];
    frameworks: string[];
    description: string;
    analyzedAt?: string;
    gitCommitHash?: string;
  };
  nodes: GraphNode[];
  edges: GraphEdge[];
  layers: GraphLayer[];
  tour: GraphTourStep[];
  provenance?: Record<string, unknown>;
}

export interface GraphSnapshotManifest {
  schemaVersion?: string;
  snapshotId?: string;
  status?: string;
  semanticStatus?: string;
  analyzedAt?: string;
  analyzedCommit?: string;
  worktreeDirty?: boolean;
  worktreeStatusCount?: number;
  worktreeStatusSha256?: string;
  graphPath?: string;
  graphSha256?: string;
  nodeCount?: number;
  edgeCount?: number;
  sourceFileCount?: number;
  sourceHashes?: Array<{ path: string; sha256: string; size_bytes: number }>;
  includedPrefixes?: string[];
  excludedPrefixes?: string[];
  filteredByIgnore?: number;
  verification?: Record<string, unknown>;
  warnings?: string[];
  [key: string]: unknown;
}

export interface GraphSnapshotResponse {
  graph: KnowledgeGraph;
  manifest: GraphSnapshotManifest;
}

export interface NodeRetrievalPacket {
  node: GraphNode;
  relatedNodes: GraphNode[];
  relatedEdges: GraphEdge[];
  sourceHash: string | null;
  provenance: GraphProvenance;
  truncated: boolean;
}

export type GraphFreshness = 'current' | 'stale' | 'unknown';

export interface GraphProvenance {
  source: 'bundled' | 'local-api';
  freshness: GraphFreshness;
  graphHash: string | null;
  graphAnalyzedAt: string | null;
  graphCommit: string | null;
  currentCommit: string | null;
  nodeCount: number;
  edgeCount: number;
  semanticStatus?: string | null;
  worktreeDirty?: boolean;
  worktreeStatusCount?: number;
  snapshotWorktreeStatusSha256?: string | null;
  currentWorktreeStatusSha256?: string | null;
  worktreeChangedSinceSnapshot?: boolean;
  detail: string;
}

// FIX-5 (H-3): Start with an empty graph. The bundled graph is loaded
// asynchronously by loadBundledGraph() only in dev mode (see below).
// This prevents the JSON from being included in the production JS bundle.
const emptyGraph: KnowledgeGraph = {
  version: '',
  kind: '',
  project: { name: '', languages: [], frameworks: [], description: '' },
  nodes: [],
  edges: [],
  layers: [],
  tour: [],
};

export let graph: KnowledgeGraph = emptyGraph;

import { graphIndex } from './graphIndex';
export { graphIndex };

// Dev-only: dynamically import the bundled graph JSON as a fallback.
// In production, this function is a no-op — the JSON is never imported.
// Tries the local Phase 2 structural graph first, then falls back to the
// legacy local knowledge-graph.json. Both snapshots are optional generated
// files and are intentionally not required for a clean checkout or production.
export async function loadBundledGraph(): Promise<void> {
  if (!import.meta.env.DEV) return;
  // Try Phase 2 structural graph first (current, 4,916 nodes)
  try {
    const phase2GraphPath = '../../../.understand-anything/phase2-structural-graph.json';
    const mod = await import(/* @vite-ignore */ phase2GraphPath);
    setActiveGraph(mod.default as KnowledgeGraph);
    bundledGraphProvenance.graphAnalyzedAt = graph.project.analyzedAt ?? null;
    bundledGraphProvenance.graphCommit = graph.project.gitCommitHash ?? null;
    bundledGraphProvenance.nodeCount = graphStats.nodeCount;
    bundledGraphProvenance.edgeCount = graphStats.edgeCount;
    return;
  } catch {
    // Phase 2 graph unavailable — try legacy fallback
  }
  // Fall back to legacy knowledge-graph.json (older, 2,045 nodes)
  try {
    const legacyGraphPath = '../../../.understand-anything/knowledge-graph.json';
    const mod = await import(/* @vite-ignore */ legacyGraphPath);
    setActiveGraph(mod.default as KnowledgeGraph);
    bundledGraphProvenance.graphAnalyzedAt = graph.project.analyzedAt ?? null;
    bundledGraphProvenance.graphCommit = graph.project.gitCommitHash ?? null;
    bundledGraphProvenance.nodeCount = graphStats.nodeCount;
    bundledGraphProvenance.edgeCount = graphStats.edgeCount;
  } catch {
    // Both graphs unavailable — keep empty graph; snapshot endpoint will fill in.
  }
}

function buildGraphStats(value: KnowledgeGraph) {
  // Use type-based counting via a single pass instead of multiple filter scans
  const typeCounts: Record<string, number> = {};
  for (const node of value.nodes) {
    typeCounts[node.type] = (typeCounts[node.type] ?? 0) + 1;
  }
  return {
    nodeCount: value.nodes.length,
    edgeCount: value.edges.length,
    layerCount: value.layers.length,
    tourStepCount: value.tour.length,
    fileTypeCount: typeCounts['file'] ?? 0,
    functionTypeCount: typeCounts['function'] ?? 0,
    classTypeCount: typeCounts['class'] ?? 0,
    pipelineTypeCount: typeCounts['pipeline'] ?? 0,
  } as const;
}

export let graphStats = buildGraphStats(graph);

// FIX-5 (H-3): bundledGraphProvenance starts with empty values because
// the bundled graph is loaded asynchronously by loadBundledGraph().
// loadBundledGraph() updates these fields after loading the JSON.
export const bundledGraphProvenance: GraphProvenance = {
  source: 'bundled',
  freshness: 'unknown',
  graphHash: null,
  graphAnalyzedAt: null,
  graphCommit: null,
  currentCommit: null,
  nodeCount: 0,
  edgeCount: 0,
  semanticStatus: 'historical_bundled_snapshot',
  detail: 'Bundled snapshot; live graph status has not been verified.',
};

export function setActiveGraph(nextGraph: KnowledgeGraph, graphHash?: string | null): void {
  graph = nextGraph;
  graphStats = buildGraphStats(nextGraph);
  // Rebuild the in-memory index for O(1) lookups
  graphIndex.rebuild(nextGraph, graphHash ?? null);
}

export function classifyGraphFreshness(
  graphCommit: string | null | undefined,
  currentCommit: string | null | undefined,
): GraphFreshness {
  if (!graphCommit || !currentCommit) return 'unknown';
  return graphCommit === currentCommit ? 'current' : 'stale';
}

export function isLoopbackHost(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return normalized === 'localhost'
    || normalized === '127.0.0.1'
    || normalized === '::1'
    || normalized === '[::1]';
}

export async function fetchGraphSnapshot(): Promise<GraphSnapshotResponse | null> {
  try {
    const response = await fetch('/api/knowledge-graph/snapshot', { cache: 'no-store' });
    if (!response.ok) return null;
    const payload = await response.json() as Partial<GraphSnapshotResponse>;
    if (!payload.graph || !Array.isArray(payload.graph.nodes) || !Array.isArray(payload.graph.edges)) {
      return null;
    }
    return {
      graph: {
        ...payload.graph,
        layers: Array.isArray(payload.graph.layers) ? payload.graph.layers : [],
        tour: Array.isArray(payload.graph.tour) ? payload.graph.tour : [],
      },
      manifest: payload.manifest || {},
    };
  } catch {
    return null;
  }
}

export async function fetchNodeRetrievalPacket(nodeId: string): Promise<NodeRetrievalPacket | null> {
  if (!nodeId || nodeId.length > 512 || nodeId.includes('\0')) return null;
  try {
    const params = new URLSearchParams({ id: nodeId });
    const response = await fetch(`/api/knowledge-graph/node?${params.toString()}`, { cache: 'no-store' });
    if (!response.ok) return null;
    return await response.json() as NodeRetrievalPacket;
  } catch {
    return null;
  }
}

export async function fetchGraphProvenance(): Promise<GraphProvenance> {
  try {
    const response = await fetch('/api/knowledge-graph/status', { cache: 'no-store' });
    if (!response.ok) {
      return { ...bundledGraphProvenance, detail: 'Live graph status is unavailable.' };
    }
    const payload = await response.json() as { provenance?: GraphProvenance };
    if (!payload.provenance) {
      return { ...bundledGraphProvenance, detail: 'Live graph status was malformed.' };
    }
    return payload.provenance;
  } catch {
    return { ...bundledGraphProvenance, detail: 'Live graph status is unavailable.' };
  }
}

export function getNodeById(nodeId: string): GraphNode | undefined {
  return graphIndex.getNode(nodeId);
}

export function getNodesByType(type: string): GraphNode[] {
  return graphIndex.getNodesByType(type);
}

export function getEdgesByType(type: string): GraphEdge[] {
  return graphIndex.getEdgesByType(type);
}

export function getConnectedEdges(nodeId: string): GraphEdge[] {
  return graphIndex.getConnectedEdges(nodeId);
}

export function getNeighbors(nodeId: string): GraphNode[] {
  return graphIndex.getNeighbors(nodeId);
}

export function getChildren(nodeId: string): GraphNode[] {
  return graphIndex.getChildren(nodeId);
}

export function getCallers(nodeId: string): GraphNode[] {
  return graphIndex.getCallers(nodeId);
}

export function getCallees(nodeId: string): GraphNode[] {
  return graphIndex.getCallees(nodeId);
}

export function getImporters(nodeId: string): GraphNode[] {
  return graphIndex.getImporters(nodeId);
}

export function getTesters(nodeId: string): GraphNode[] {
  // The Understand graph uses source=source file, target=test file for tested_by.
  return graphIndex.getTesters(nodeId);
}

export function getLayerForNode(nodeId: string): GraphLayer | undefined {
  return graphIndex.getLayerForNode(nodeId);
}

export function getTourStepForNode(nodeId: string): GraphTourStep | undefined {
  return graphIndex.getTourStepForNode(nodeId);
}
