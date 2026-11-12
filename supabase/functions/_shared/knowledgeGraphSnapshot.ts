import { isDenylisted } from './knowledgeGraphModelPolicy.ts';

const MAX_RELATED_NODES = 50;
const MAX_SOURCE_REFERENCES = 50;

interface SnapshotNode {
  id: string;
  filePath?: string;
  sourceSha256?: string;
  [key: string]: unknown;
}

interface SnapshotEdge {
  source: string;
  target: string;
  type?: string;
  [key: string]: unknown;
}

export interface ServerOwnedGraphSnapshotEnvelope {
  graph: {
    nodes: SnapshotNode[];
    edges: SnapshotEdge[];
  };
  manifest: {
    snapshotId: string;
    graphSha256: string;
    nodeCount: number;
    edgeCount: number;
    worktreeDirty?: boolean;
    [key: string]: unknown;
  };
  hashVerified: boolean;
}

export interface ApprovedGraphContext {
  snapshotId: string;
  graphHash: string;
  evidenceRefs: string[];
  graphData: {
    snapshotId: string;
    graphHash: string;
    node: SnapshotNode | null;
    relatedNodes: SnapshotNode[];
    relatedEdges: SnapshotEdge[];
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isHash(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{32,}$/i.test(value);
}

function parseNode(value: unknown): SnapshotNode | null {
  if (!isRecord(value) || typeof value.id !== 'string' || !value.id.trim()) return null;
  if (value.filePath !== undefined && typeof value.filePath !== 'string') return null;
  if (value.sourceSha256 !== undefined && !isHash(value.sourceSha256)) return null;
  if (typeof value.filePath === 'string' && isDenylisted(value.filePath)) return null;
  return value as SnapshotNode;
}

function parseEdge(value: unknown, nodeIds: Set<string>): SnapshotEdge | null {
  if (!isRecord(value) || typeof value.source !== 'string' || typeof value.target !== 'string') {
    return null;
  }
  if (!nodeIds.has(value.source) || !nodeIds.has(value.target)) return null;
  return value as SnapshotEdge;
}

export function buildApprovedGraphContext(
  input: unknown,
  nodeId?: string,
): ApprovedGraphContext | null {
  if (!isRecord(input) || input.hashVerified !== true) return null;
  const graph = input.graph;
  const manifest = input.manifest;
  if (!isRecord(graph) || !isRecord(manifest) || manifest.worktreeDirty === true) return null;

  const snapshotId = manifest.snapshotId;
  const graphHash = manifest.graphSha256;
  const rawNodes = graph.nodes;
  const rawEdges = graph.edges;
  if (typeof snapshotId !== 'string' || !snapshotId.trim() || !isHash(graphHash)) return null;
  if (!Array.isArray(rawNodes) || !Array.isArray(rawEdges)) return null;
  if (manifest.nodeCount !== rawNodes.length || manifest.edgeCount !== rawEdges.length) return null;

  const nodes: SnapshotNode[] = [];
  const nodeIds = new Set<string>();
  for (const rawNode of rawNodes) {
    const node = parseNode(rawNode);
    if (!node || nodeIds.has(node.id)) return null;
    nodes.push(node);
    nodeIds.add(node.id);
  }

  const edges: SnapshotEdge[] = [];
  for (const rawEdge of rawEdges) {
    const edge = parseEdge(rawEdge, nodeIds);
    if (!edge) return null;
    edges.push(edge);
  }

  const selectedNode = nodeId ? nodes.find((node) => node.id === nodeId) ?? null : null;
  if (nodeId && !selectedNode) return null;

  const relatedEdges = selectedNode
    ? edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
      .slice(0, MAX_RELATED_NODES)
    : [];
  const relatedIds = new Set<string>();
  for (const edge of relatedEdges) {
    if (edge.source !== selectedNode?.id) relatedIds.add(edge.source);
    if (edge.target !== selectedNode?.id) relatedIds.add(edge.target);
  }
  const relatedNodes = nodes.filter((node) => relatedIds.has(node.id)).slice(0, MAX_RELATED_NODES);

  const evidenceRefs = [`snapshot:${snapshotId}#graph:${graphHash}`];
  if (selectedNode?.filePath) {
    evidenceRefs.push(
      selectedNode.sourceSha256
        ? `file:${selectedNode.filePath}#sha256:${selectedNode.sourceSha256}`
        : `file:${selectedNode.filePath}`,
    );
  }
  for (const node of relatedNodes) {
    if (node.filePath && evidenceRefs.length < MAX_SOURCE_REFERENCES) {
      evidenceRefs.push(
        node.sourceSha256
          ? `file:${node.filePath}#sha256:${node.sourceSha256}`
          : `file:${node.filePath}`,
      );
    }
  }

  return {
    snapshotId,
    graphHash,
    evidenceRefs: Array.from(new Set(evidenceRefs)).slice(0, MAX_SOURCE_REFERENCES),
    graphData: {
      snapshotId,
      graphHash,
      node: selectedNode,
      relatedNodes,
      relatedEdges,
    },
  };
}
