export interface GraphNode {
  id: string;
  name: string;
  type: string;
  relativePath?: string;
  language?: string | null;
  summary?: string | null;
  tags?: string[];
  lineCount?: number | null;
  sourceHash?: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  direction?: string | null;
  weight?: number | null;
}

export interface GraphLayer {
  id: string;
  name: string;
  description: string;
  nodeIds: string[];
}

export interface KnowledgeGraph {
  version: string;
  kind: string;
  project: {
    name: string;
    languages: string[];
    frameworks: string[];
    description: string;
  };
  nodes: GraphNode[];
  edges: GraphEdge[];
  layers: GraphLayer[];
  tour: unknown[];
}

export interface GraphManifest {
  schemaVersion: string;
  exportStatus: 'approved' | 'preview_only' | 'blocked';
  contentHash: string;
  fileSha256: string;
  fileSizeBytes: number;
  nodeCount: number;
  edgeCount: number;
  sourceGraphSha256: string;
  sourceManifestSha256: string;
  sourceCommit: string;
  analyzedAt: string;
  worktreeDirty: boolean;
  exportedAt: string;
  license: string;
  attribution: string;
  disclaimer: string;
  validTime: string;
  nodeFields: string[];
  edgeFields: string[];
  projectFields: string[];
  piiRedactionsApplied: number;
  forbiddenContentFindings: number;
  danglingEdges: number;
  denylistViolations: number;
  unknownFieldRejections: number;
  contentApproval?: 'APPROVED_PUBLIC_CONTENT';
}

export interface GraphIndex {
  nodeById: Map<string, GraphNode>;
  incomingByTarget: Map<string, GraphEdge[]>;
  outgoingBySource: Map<string, GraphEdge[]>;
}

export function buildGraphIndex(graph: KnowledgeGraph): GraphIndex {
  const nodeById = new Map<string, GraphNode>();
  for (const node of graph.nodes) {
    nodeById.set(node.id, node);
  }
  const incomingByTarget = new Map<string, GraphEdge[]>();
  const outgoingBySource = new Map<string, GraphEdge[]>();
  for (const edge of graph.edges) {
    const out = outgoingBySource.get(edge.source) ?? [];
    out.push(edge);
    outgoingBySource.set(edge.source, out);
    const inc = incomingByTarget.get(edge.target) ?? [];
    inc.push(edge);
    incomingByTarget.set(edge.target, inc);
  }
  return { nodeById, incomingByTarget, outgoingBySource };
}

export async function loadGraph(): Promise<KnowledgeGraph> {
  const response = await fetch('/data/code-graph.json');
  if (!response.ok) throw new Error(`Failed to load graph: ${response.status}`);
  return response.json();
}

export async function loadExplanations(): Promise<Record<string, string>> {
  const response = await fetch('/data/explanations.json');
  if (!response.ok) throw new Error(`Failed to load explanations: ${response.status}`);
  return response.json();
}

export async function loadGraphManifest(): Promise<GraphManifest> {
  const response = await fetch('/data/code-graph-manifest.json');
  if (!response.ok) throw new Error(`Failed to load manifest: ${response.status}`);
  return response.json();
}

export function getNodeById(index: GraphIndex, id: string): GraphNode | undefined {
  return index.nodeById.get(id);
}

export function getIncomingEdges(index: GraphIndex, id: string): GraphEdge[] {
  return index.incomingByTarget.get(id) ?? [];
}

export function getOutgoingEdges(index: GraphIndex, id: string): GraphEdge[] {
  return index.outgoingBySource.get(id) ?? [];
}
