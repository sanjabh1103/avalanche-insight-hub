/**
 * In-memory graph index for O(1) node lookups and O(degree) adjacency queries.
 *
 * Replaces the O(N) linear scans in graphData.ts with snapshot-bound maps.
 * The index is rebuilt whenever the active graph changes (via `rebuildIndex`).
 * Arrays remain the source of truth for serialization and test oracle purposes.
 */

import type { GraphEdge, GraphLayer, GraphNode, GraphTourStep, KnowledgeGraph } from './graphData';

interface AdjacencyEntry {
  /** Edges where this node is the source */
  outgoing: GraphEdge[];
  /** Edges where this node is the target */
  incoming: GraphEdge[];
}

export class GraphIndex {
  private nodeById = new Map<string, GraphNode>();
  private nodesByType = new Map<string, GraphNode[]>();
  private edgesByType = new Map<string, GraphEdge[]>();
  private adjacency = new Map<string, AdjacencyEntry>();
  private layerByNodeId = new Map<string, GraphLayer>();
  private tourStepByNodeId = new Map<string, GraphTourStep>();
  private _graphHash: string | null = null;

  /** Build the index from a graph. Call whenever the active graph changes. */
  rebuild(graph: KnowledgeGraph, graphHash?: string | null): void {
    this.nodeById = new Map();
    this.nodesByType = new Map();
    this.edgesByType = new Map();
    this.adjacency = new Map();
    this.layerByNodeId = new Map();
    this.tourStepByNodeId = new Map();
    this._graphHash = graphHash ?? null;

    // Index nodes by ID and type
    for (const node of graph.nodes) {
      this.nodeById.set(node.id, node);
      const typed = this.nodesByType.get(node.type);
      if (typed) {
        typed.push(node);
      } else {
        this.nodesByType.set(node.type, [node]);
      }
      // Ensure adjacency entry exists for every node
      if (!this.adjacency.has(node.id)) {
        this.adjacency.set(node.id, { outgoing: [], incoming: [] });
      }
    }

    // Index edges by type and build adjacency lists
    for (const edge of graph.edges) {
      const typed = this.edgesByType.get(edge.type);
      if (typed) {
        typed.push(edge);
      } else {
        this.edgesByType.set(edge.type, [edge]);
      }

      // Build adjacency — only for nodes that exist in the graph
      const sourceEntry = this.adjacency.get(edge.source);
      if (sourceEntry) sourceEntry.outgoing.push(edge);
      const targetEntry = this.adjacency.get(edge.target);
      if (targetEntry) targetEntry.incoming.push(edge);
    }

    // Index layers by node ID — O(1) lookup instead of O(L) scan
    for (const layer of graph.layers) {
      for (const nodeId of layer.nodeIds) {
        // First layer wins (matches .find() behavior)
        if (!this.layerByNodeId.has(nodeId)) {
          this.layerByNodeId.set(nodeId, layer);
        }
      }
    }

    // Index tour steps by node ID — O(1) lookup instead of O(T) scan
    for (const step of graph.tour) {
      for (const nodeId of step.nodeIds) {
        // First tour step wins (matches .find() behavior)
        if (!this.tourStepByNodeId.has(nodeId)) {
          this.tourStepByNodeId.set(nodeId, step);
        }
      }
    }
  }

  /** O(1) node lookup by ID. */
  getNode(nodeId: string): GraphNode | undefined {
    return this.nodeById.get(nodeId);
  }

  /** O(1) node-type lookup. Returns the cached array (do not mutate). */
  getNodesByType(type: string): GraphNode[] {
    return this.nodesByType.get(type) ?? [];
  }

  /** O(1) edge-type lookup. Returns the cached array (do not mutate). */
  getEdgesByType(type: string): GraphEdge[] {
    return this.edgesByType.get(type) ?? [];
  }

  /** O(degree) connected edges for a node. */
  getConnectedEdges(nodeId: string): GraphEdge[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    return [...entry.outgoing, ...entry.incoming];
  }

  /** O(degree) neighbors of a node (both directions, all edge types). */
  getNeighbors(nodeId: string): GraphNode[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    const neighborIds = new Set<string>();
    for (const edge of entry.outgoing) neighborIds.add(edge.target);
    for (const edge of entry.incoming) neighborIds.add(edge.source);
    const result: GraphNode[] = [];
    for (const id of neighborIds) {
      const node = this.nodeById.get(id);
      if (node) result.push(node);
    }
    return result;
  }

  /** O(degree) children (outgoing 'contains' edges → target nodes). */
  getChildren(nodeId: string): GraphNode[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    const result: GraphNode[] = [];
    for (const edge of entry.outgoing) {
      if (edge.type === 'contains') {
        const node = this.nodeById.get(edge.target);
        if (node) result.push(node);
      }
    }
    return result;
  }

  /** O(degree) callers (incoming 'calls' edges → source nodes). */
  getCallers(nodeId: string): GraphNode[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    const result: GraphNode[] = [];
    for (const edge of entry.incoming) {
      if (edge.type === 'calls') {
        const node = this.nodeById.get(edge.source);
        if (node) result.push(node);
      }
    }
    return result;
  }

  /** O(degree) callees (outgoing 'calls' edges → target nodes). */
  getCallees(nodeId: string): GraphNode[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    const result: GraphNode[] = [];
    for (const edge of entry.outgoing) {
      if (edge.type === 'calls') {
        const node = this.nodeById.get(edge.target);
        if (node) result.push(node);
      }
    }
    return result;
  }

  /** O(degree) importers (incoming 'imports' edges → source nodes). */
  getImporters(nodeId: string): GraphNode[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    const result: GraphNode[] = [];
    for (const edge of entry.incoming) {
      if (edge.type === 'imports') {
        const node = this.nodeById.get(edge.source);
        if (node) result.push(node);
      }
    }
    return result;
  }

  /** O(degree) testers (outgoing 'tested_by' edges → target nodes). */
  getTesters(nodeId: string): GraphNode[] {
    const entry = this.adjacency.get(nodeId);
    if (!entry) return [];
    const result: GraphNode[] = [];
    for (const edge of entry.outgoing) {
      if (edge.type === 'tested_by') {
        const node = this.nodeById.get(edge.target);
        if (node) result.push(node);
      }
    }
    return result;
  }

  /** O(1) layer lookup by node ID. */
  getLayerForNode(nodeId: string): GraphLayer | undefined {
    return this.layerByNodeId.get(nodeId);
  }

  /** O(1) tour step lookup by node ID. */
  getTourStepForNode(nodeId: string): GraphTourStep | undefined {
    return this.tourStepByNodeId.get(nodeId);
  }

  /** Current graph hash (for invalidation checks). */
  get graphHash(): string | null {
    return this._graphHash;
  }

  /** Check if the index needs rebuilding for a new graph hash. */
  needsRebuild(graphHash: string | null): boolean {
    return this._graphHash !== graphHash;
  }

  /** Number of indexed nodes. */
  get nodeCount(): number {
    return this.nodeById.size;
  }

  /** Number of indexed edges. */
  get edgeCount(): number {
    let count = 0;
    for (const entry of this.adjacency.values()) {
      count += entry.outgoing.length;
    }
    return count;
  }
}

/** Singleton index instance shared across the app. */
export const graphIndex = new GraphIndex();
