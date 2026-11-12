import { describe, it, expect, beforeEach } from 'vitest';
import { GraphIndex } from '../../lib/knowledge-graph/graphIndex';
import type { KnowledgeGraph, GraphNode, GraphEdge } from '../../lib/knowledge-graph/graphData';

function makeNode(id: string, type: string, filePath?: string): GraphNode {
  return { id, name: id.split(':').pop() ?? id, type, filePath };
}

function makeEdge(source: string, target: string, type: string): GraphEdge {
  return { source, target, type, direction: 'forward', weight: 1 };
}

function makeGraph(nodes: GraphNode[], edges: GraphEdge[]): KnowledgeGraph {
  return {
    version: 'test',
    kind: 'structural',
    project: { name: 'test', languages: ['typescript'], frameworks: [], description: '' },
    nodes,
    edges,
    layers: [],
    tour: [],
  };
}

const fixture = makeGraph(
  [
    makeNode('file:a.ts', 'file', 'a.ts'),
    makeNode('function:a.ts:foo', 'function', 'a.ts'),
    makeNode('function:a.ts:bar', 'function', 'a.ts'),
    makeNode('class:a.ts:Baz', 'class', 'a.ts'),
    makeNode('file:b.ts', 'file', 'b.ts'),
    makeNode('function:b.ts:qux', 'function', 'b.ts'),
    makeNode('file:c_test.ts', 'file', 'c_test.ts'),
  ],
  [
    makeEdge('file:a.ts', 'function:a.ts:foo', 'contains'),
    makeEdge('file:a.ts', 'function:a.ts:bar', 'contains'),
    makeEdge('file:a.ts', 'class:a.ts:Baz', 'contains'),
    makeEdge('file:b.ts', 'function:b.ts:qux', 'contains'),
    makeEdge('function:a.ts:foo', 'function:b.ts:qux', 'calls'),
    makeEdge('function:b.ts:qux', 'function:a.ts:bar', 'calls'),
    makeEdge('function:a.ts:foo', 'file:b.ts', 'imports'),
    makeEdge('file:a.ts', 'file:c_test.ts', 'tested_by'),
  ],
);

describe('GraphIndex', () => {
  let index: GraphIndex;

  beforeEach(() => {
    index = new GraphIndex();
    index.rebuild(fixture, 'hash-1');
  });

  it('indexes all nodes by ID', () => {
    expect(index.nodeCount).toBe(7);
    expect(index.getNode('file:a.ts')?.name).toBe('a.ts');
    expect(index.getNode('nonexistent')).toBeUndefined();
  });

  it('groups nodes by type', () => {
    expect(index.getNodesByType('file')).toHaveLength(3);
    expect(index.getNodesByType('function')).toHaveLength(3);
    expect(index.getNodesByType('class')).toHaveLength(1);
    expect(index.getNodesByType('nonexistent')).toEqual([]);
  });

  it('groups edges by type', () => {
    expect(index.getEdgesByType('contains')).toHaveLength(4);
    expect(index.getEdgesByType('calls')).toHaveLength(2);
    expect(index.getEdgesByType('imports')).toHaveLength(1);
    expect(index.getEdgesByType('tested_by')).toHaveLength(1);
  });

  it('returns connected edges for a node', () => {
    const edges = index.getConnectedEdges('function:a.ts:foo');
    // foo has: contains (incoming from file:a.ts), calls (outgoing to qux), imports (outgoing to file:b.ts)
    expect(edges).toHaveLength(3);
  });

  it('returns neighbors for a node', () => {
    const neighbors = index.getNeighbors('function:a.ts:foo');
    const neighborIds = neighbors.map((n) => n.id).sort();
    expect(neighborIds).toEqual(['file:a.ts', 'file:b.ts', 'function:b.ts:qux']);
  });

  it('returns children (contains → target)', () => {
    const children = index.getChildren('file:a.ts');
    const childIds = children.map((n) => n.id).sort();
    expect(childIds).toEqual(['class:a.ts:Baz', 'function:a.ts:bar', 'function:a.ts:foo']);
  });

  it('returns callers (calls → source)', () => {
    const callers = index.getCallers('function:a.ts:bar');
    expect(callers).toHaveLength(1);
    expect(callers[0].id).toBe('function:b.ts:qux');
  });

  it('returns callees (calls → target)', () => {
    const callees = index.getCallees('function:a.ts:foo');
    expect(callees).toHaveLength(1);
    expect(callees[0].id).toBe('function:b.ts:qux');
  });

  it('returns importers (imports → source)', () => {
    const importers = index.getImporters('file:b.ts');
    expect(importers).toHaveLength(1);
    expect(importers[0].id).toBe('function:a.ts:foo');
  });

  it('returns testers (tested_by → target)', () => {
    const testers = index.getTesters('file:a.ts');
    expect(testers).toHaveLength(1);
    expect(testers[0].id).toBe('file:c_test.ts');
  });

  it('returns empty arrays for unknown nodes', () => {
    expect(index.getChildren('nonexistent')).toEqual([]);
    expect(index.getCallers('nonexistent')).toEqual([]);
    expect(index.getCallees('nonexistent')).toEqual([]);
    expect(index.getNeighbors('nonexistent')).toEqual([]);
    expect(index.getConnectedEdges('nonexistent')).toEqual([]);
  });

  it('tracks graph hash for invalidation', () => {
    expect(index.graphHash).toBe('hash-1');
    expect(index.needsRebuild('hash-1')).toBe(false);
    expect(index.needsRebuild('hash-2')).toBe(true);
    expect(index.needsRebuild(null)).toBe(true);
  });

  it('rebuilds with a new graph', () => {
    const newGraph = makeGraph([makeNode('file:new.ts', 'file', 'new.ts')], []);
    index.rebuild(newGraph, 'hash-2');
    expect(index.nodeCount).toBe(1);
    expect(index.getNode('file:a.ts')).toBeUndefined();
    expect(index.getNode('file:new.ts')).toBeDefined();
    expect(index.graphHash).toBe('hash-2');
  });

  it('handles edges to non-existent nodes gracefully', () => {
    const graphWithDanglingEdge = makeGraph(
      [makeNode('file:a.ts', 'file', 'a.ts')],
      [makeEdge('file:a.ts', 'nonexistent', 'contains')],
    );
    const idx = new GraphIndex();
    idx.rebuild(graphWithDanglingEdge, 'hash');
    const children = idx.getChildren('file:a.ts');
    // Edge exists but target node doesn't — should return empty
    expect(children).toEqual([]);
  });

  it('handles duplicate node IDs (last wins)', () => {
    const graphWithDup = makeGraph(
      [makeNode('file:dup.ts', 'file', 'first.ts'), makeNode('file:dup.ts', 'function', 'second.ts')],
      [],
    );
    const idx = new GraphIndex();
    idx.rebuild(graphWithDup, 'hash');
    expect(idx.nodeCount).toBe(1);
    expect(idx.getNode('file:dup.ts')?.type).toBe('function');
  });

  it('handles empty graph', () => {
    const idx = new GraphIndex();
    idx.rebuild(makeGraph([], []), 'hash');
    expect(idx.nodeCount).toBe(0);
    expect(idx.getNode('any')).toBeUndefined();
    expect(idx.getNodesByType('file')).toEqual([]);
  });

  it('produces results equivalent to linear scan (oracle test)', () => {
    // This test verifies that the index produces the same results as a direct array scan
    const linearScanChildren = fixture.edges
      .filter((e) => e.source === 'file:a.ts' && e.type === 'contains')
      .map((e) => fixture.nodes.find((n) => n.id === e.target))
      .filter((n): n is GraphNode => n !== undefined);
    const indexChildren = index.getChildren('file:a.ts');
    // Same length
    expect(indexChildren).toHaveLength(linearScanChildren.length);
    // Same IDs (order may differ, so sort)
    const indexIds = indexChildren.map((n) => n.id).sort();
    const linearIds = linearScanChildren.map((n) => n.id).sort();
    expect(indexIds).toEqual(linearIds);
  });

  // ===== Comprehensive equivalence tests for ALL query methods =====

  describe('equivalence with linear scan (oracle tests)', () => {
    // Helper: linear scan getNodeById
    const linearGetNodeById = (nodeId: string) => fixture.nodes.find((n) => n.id === nodeId);
    // Helper: linear scan getNodesByType
    const linearGetNodesByType = (type: string) => fixture.nodes.filter((n) => n.type === type);
    // Helper: linear scan getEdgesByType
    const linearGetEdgesByType = (type: string) => fixture.edges.filter((e) => e.type === type);
    // Helper: linear scan getConnectedEdges
    const linearGetConnectedEdges = (nodeId: string) =>
      fixture.edges.filter((e) => e.source === nodeId || e.target === nodeId);
    // Helper: linear scan getNeighbors
    const linearGetNeighbors = (nodeId: string) => {
      const ids = new Set<string>();
      for (const e of fixture.edges) {
        if (e.source === nodeId) ids.add(e.target);
        if (e.target === nodeId) ids.add(e.source);
      }
      return Array.from(ids)
        .map((id) => fixture.nodes.find((n) => n.id === id))
        .filter((n): n is GraphNode => n !== undefined);
    };
    // Helper: linear scan getCallers
    const linearGetCallers = (nodeId: string) =>
      fixture.edges
        .filter((e) => e.target === nodeId && e.type === 'calls')
        .map((e) => fixture.nodes.find((n) => n.id === e.source))
        .filter((n): n is GraphNode => n !== undefined);
    // Helper: linear scan getCallees
    const linearGetCallees = (nodeId: string) =>
      fixture.edges
        .filter((e) => e.source === nodeId && e.type === 'calls')
        .map((e) => fixture.nodes.find((n) => n.id === e.target))
        .filter((n): n is GraphNode => n !== undefined);
    // Helper: linear scan getImporters
    const linearGetImporters = (nodeId: string) =>
      fixture.edges
        .filter((e) => e.target === nodeId && e.type === 'imports')
        .map((e) => fixture.nodes.find((n) => n.id === e.source))
        .filter((n): n is GraphNode => n !== undefined);
    // Helper: linear scan getTesters
    const linearGetTesters = (nodeId: string) =>
      fixture.edges
        .filter((e) => e.source === nodeId && e.type === 'tested_by')
        .map((e) => fixture.nodes.find((n) => n.id === e.target))
        .filter((n): n is GraphNode => n !== undefined);

    const sortIds = (nodes: GraphNode[]) => nodes.map((n) => n.id).sort();
    const sortEdgeIds = (edges: GraphEdge[]) =>
      edges.map((e) => `${e.source}->${e.target}:${e.type}`).sort();

    // Test all nodes for equivalence
    const allNodeIds = fixture.nodes.map((n) => n.id);

    it('getNodeById matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(index.getNode(id)).toEqual(linearGetNodeById(id));
      }
      // Unknown node
      expect(index.getNode('nonexistent')).toBeUndefined();
      expect(linearGetNodeById('nonexistent')).toBeUndefined();
    });

    it('getNodesByType matches linear scan for all types', () => {
      const types = ['file', 'function', 'class', 'nonexistent'];
      for (const type of types) {
        expect(sortIds(index.getNodesByType(type))).toEqual(sortIds(linearGetNodesByType(type)));
      }
    });

    it('getEdgesByType matches linear scan for all types', () => {
      const types = ['contains', 'imports', 'calls', 'tested_by', 'nonexistent'];
      for (const type of types) {
        expect(sortEdgeIds(index.getEdgesByType(type))).toEqual(sortEdgeIds(linearGetEdgesByType(type)));
      }
    });

    it('getConnectedEdges matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortEdgeIds(index.getConnectedEdges(id))).toEqual(sortEdgeIds(linearGetConnectedEdges(id)));
      }
    });

    it('getNeighbors matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortIds(index.getNeighbors(id))).toEqual(sortIds(linearGetNeighbors(id)));
      }
    });

    it('getChildren matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortIds(index.getChildren(id))).toEqual(
          sortIds(
            fixture.edges
              .filter((e) => e.source === id && e.type === 'contains')
              .map((e) => fixture.nodes.find((n) => n.id === e.target))
              .filter((n): n is GraphNode => n !== undefined),
          ),
        );
      }
    });

    it('getCallers matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortIds(index.getCallers(id))).toEqual(sortIds(linearGetCallers(id)));
      }
    });

    it('getCallees matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortIds(index.getCallees(id))).toEqual(sortIds(linearGetCallees(id)));
      }
    });

    it('getImporters matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortIds(index.getImporters(id))).toEqual(sortIds(linearGetImporters(id)));
      }
    });

    it('getTesters matches linear scan for all nodes', () => {
      for (const id of allNodeIds) {
        expect(sortIds(index.getTesters(id))).toEqual(sortIds(linearGetTesters(id)));
      }
    });

    it('getLayerForNode matches linear scan', () => {
      const graphWithLayers: KnowledgeGraph = {
        ...fixture,
        layers: [
          { id: 'layer-1', name: 'Layer 1', description: '', nodeIds: ['file:a.ts', 'function:a.ts:foo'] },
          { id: 'layer-2', name: 'Layer 2', description: '', nodeIds: ['file:b.ts'] },
        ],
      };
      const idx = new GraphIndex();
      idx.rebuild(graphWithLayers, 'hash');
      // First layer wins for file:a.ts
      expect(idx.getLayerForNode('file:a.ts')?.id).toBe('layer-1');
      expect(idx.getLayerForNode('function:a.ts:foo')?.id).toBe('layer-1');
      expect(idx.getLayerForNode('file:b.ts')?.id).toBe('layer-2');
      // Non-layer node
      expect(idx.getLayerForNode('class:a.ts:Baz')).toBeUndefined();
    });

    it('getTourStepForNode matches linear scan', () => {
      const graphWithTour: KnowledgeGraph = {
        ...fixture,
        tour: [
          { order: 1, title: 'Step 1', description: '', nodeIds: ['file:a.ts'] },
          { order: 2, title: 'Step 2', description: '', nodeIds: ['function:a.ts:foo', 'file:b.ts'] },
        ],
      };
      const idx = new GraphIndex();
      idx.rebuild(graphWithTour, 'hash');
      expect(idx.getTourStepForNode('file:a.ts')?.order).toBe(1);
      expect(idx.getTourStepForNode('function:a.ts:foo')?.order).toBe(2);
      expect(idx.getTourStepForNode('file:b.ts')?.order).toBe(2);
      // Non-tour node
      expect(idx.getTourStepForNode('class:a.ts:Baz')).toBeUndefined();
    });
  });

  // ===== Snapshot invalidation tests =====

  describe('snapshot invalidation', () => {
    it('invalidates cache when graph hash changes', () => {
      expect(index.graphHash).toBe('hash-1');
      expect(index.needsRebuild('hash-1')).toBe(false);
      expect(index.needsRebuild('hash-2')).toBe(true);
    });

    it('invalidates cache when graph hash goes to null', () => {
      expect(index.needsRebuild(null)).toBe(true);
    });

    it('rebuild produces fresh results after invalidation', () => {
      const newGraph = makeGraph(
        [makeNode('file:new.ts', 'file', 'new.ts')],
        [makeEdge('file:new.ts', 'file:new.ts', 'contains')],
      );
      index.rebuild(newGraph, 'hash-2');
      expect(index.getNode('file:a.ts')).toBeUndefined();
      expect(index.getNode('file:new.ts')).toBeDefined();
      expect(index.graphHash).toBe('hash-2');
    });
  });
});
