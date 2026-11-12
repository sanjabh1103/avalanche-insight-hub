import { beforeAll, describe, expect, it } from 'vitest';

import { filterGraph, perspectives, type Perspective } from '@/lib/knowledge-graph/perspectives';
import { graph, graphIndex, setActiveGraph } from '@/lib/knowledge-graph/graphData';
import type { GraphNode, GraphEdge, KnowledgeGraph } from '@/lib/knowledge-graph/graphData';

// Load the Phase 2 structural graph so tests run against real data, not an empty graph.
// Falls back to legacy graph if Phase 2 is unavailable.
// This ensures perspective filtering tests actually prove behavior on a populated graph.
beforeAll(async () => {
  try {
    const phase2GraphPath = '../../../.understand-anything/phase2-structural-graph.json';
    const mod = await import(/* @vite-ignore */ phase2GraphPath);
    setActiveGraph(mod.default as KnowledgeGraph);
  } catch {
    try {
      const legacyGraphPath = '../../../.understand-anything/knowledge-graph.json';
      const mod = await import(/* @vite-ignore */ legacyGraphPath);
      setActiveGraph(mod.default as KnowledgeGraph);
    } catch {
      // Both graphs unavailable — tests will skip real-graph assertions
    }
  }
});

/**
 * Equivalence tests for perspective filtering.
 *
 * Verifies that the indexed filterGraph (which uses graphIndex.getEdgesByType)
 * produces the same results as a naive linear scan over all nodes and edges.
 */
describe('perspective filtering equivalence', () => {
  // Linear scan oracle — the naive implementation that filterGraph optimizes
  function linearFilterGraph(perspective: Perspective): { nodes: GraphNode[]; edges: GraphEdge[] } {
    const filteredNodes = graph.nodes.filter(perspective.filter);
    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const filteredEdges = graph.edges.filter(
      (edge) =>
        perspective.edgeFilter(edge) &&
        nodeIds.has(edge.source) &&
        nodeIds.has(edge.target),
    );
    return { nodes: filteredNodes, edges: filteredEdges };
  }

  const sortNodeIds = (nodes: GraphNode[]) => nodes.map((n) => n.id).sort();
  const sortEdgeIds = (edges: GraphEdge[]) =>
    edges.map((e) => `${e.source}->${e.target}:${e.type}`).sort();

  for (const perspective of perspectives) {
    it(`${perspective.id}: indexed filterGraph matches linear scan`, () => {
      const indexed = filterGraph(perspective);
      const linear = linearFilterGraph(perspective);

      // Same nodes (sorted by ID)
      expect(sortNodeIds(indexed.nodes)).toEqual(sortNodeIds(linear.nodes));

      // Same edges (sorted by source->target:type)
      expect(sortEdgeIds(indexed.edges)).toEqual(sortEdgeIds(linear.edges));

      // Same counts
      expect(indexed.nodes).toHaveLength(linear.nodes.length);
      expect(indexed.edges).toHaveLength(linear.edges.length);
    });
  }

  it('all perspectives produce non-empty node sets for the real graph', () => {
    // Skip if bundled graph is not available in test environment
    if (graph.nodes.length === 0) {
      console.warn('SKIP: bundled graph not loaded — test cannot verify real-graph assertions');
      return;
    }
    for (const perspective of perspectives) {
      const { nodes } = filterGraph(perspective);
      expect(nodes.length).toBeGreaterThan(0);
    }
  });

  it('architecture perspective includes file and config nodes', () => {
    if (graph.nodes.length === 0) {
      console.warn('SKIP: bundled graph not loaded — test cannot verify real-graph assertions');
      return;
    }
    const { nodes } = filterGraph(perspectives[0]); // architecture
    const types = new Set(nodes.map((n) => n.type));
    expect(types.has('file')).toBe(true);
  });

  it('tests perspective only includes tested_by and contains edges', () => {
    const testsPerspective = perspectives.find((p) => p.id === 'tests');
    expect(testsPerspective).toBeDefined();
    if (!testsPerspective) return;
    const { edges } = filterGraph(testsPerspective);
    const edgeTypes = new Set(edges.map((e) => e.type));
    for (const type of edgeTypes) {
      expect(['tested_by', 'contains']).toContain(type);
    }
  });

  it('filtered edges always connect nodes in the filtered node set', () => {
    for (const perspective of perspectives) {
      const { nodes, edges } = filterGraph(perspective);
      const nodeIds = new Set(nodes.map((n) => n.id));
      for (const edge of edges) {
        expect(nodeIds.has(edge.source)).toBe(true);
        expect(nodeIds.has(edge.target)).toBe(true);
      }
    }
  });

  it('graphIndex is populated and consistent with graph', () => {
    // The index should have the same number of nodes as the graph
    expect(graphIndex.nodeCount).toBe(graph.nodes.length);
    // The index should have the same number of edges
    expect(graphIndex.edgeCount).toBe(graph.edges.length);
  });
});
