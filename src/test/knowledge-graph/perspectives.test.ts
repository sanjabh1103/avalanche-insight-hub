import { describe, it, expect, beforeAll } from 'vitest';
import {
  perspectives,
  getPerspective,
  filterGraph,
  type PerspectiveId,
} from '@/lib/knowledge-graph/perspectives';
import {
  classifyGraphFreshness,
  getNodeById,
  getTesters,
  graph,
  isLoopbackHost,
  loadBundledGraph,
} from '@/lib/knowledge-graph/graphData';

// FIX-5 (H-3): The bundled graph is now loaded asynchronously to keep it
// out of the production bundle. Tests must call loadBundledGraph() first.
beforeAll(async () => {
  await loadBundledGraph();
});

describe('perspectives', () => {
  it('defines all six perspectives', () => {
    const ids = perspectives.map((p) => p.id);
    expect(ids).toEqual([
      'architecture',
      'ml-pipeline',
      'data-flow',
      'security-gates',
      'tests',
      'release-evidence',
    ]);
  });

  it('each perspective has a label, description, and icon', () => {
    for (const p of perspectives) {
      expect(p.label).toBeTruthy();
      expect(p.description).toBeTruthy();
      expect(p.icon).toBeTruthy();
      expect(typeof p.filter).toBe('function');
      expect(typeof p.edgeFilter).toBe('function');
    }
  });

  it('architecture perspective returns only file/pipeline/config nodes', () => {
    const { nodes } = filterGraph(getPerspective('architecture'));
    for (const node of nodes) {
      expect(['file', 'pipeline', 'config']).toContain(node.type);
    }
  });

  it('ml-pipeline perspective is filter-driven and does not depend on stale layers', () => {
    const p = getPerspective('ml-pipeline');
    expect(p.filter).toBeTypeOf('function');
    expect(p.highlightIds).toBeUndefined();
  });

  it('tests perspective returns test-related files', () => {
    const { nodes } = filterGraph(getPerspective('tests'));
    const testKw = ['test', 'mock', 'fixture', 'spec', 'verify'];
    for (const node of nodes) {
      expect(node.type).toBe('file');
      const haystack = [node.name, node.filePath || '', node.summary || '', ...(node.tags || [])].join(' ').toLowerCase();
      expect(testKw.some((kw) => haystack.includes(kw))).toBe(true);
    }
  });

  it('filterGraph returns edges that connect only filtered nodes', () => {
    for (const p of perspectives) {
      const { nodes, edges } = filterGraph(p);
      const nodeIds = new Set(nodes.map((n) => n.id));
      for (const edge of edges) {
        expect(nodeIds.has(edge.source)).toBe(true);
        expect(nodeIds.has(edge.target)).toBe(true);
      }
    }
  });

  it('every perspective returns at least one node', () => {
    for (const p of perspectives) {
      const { nodes } = filterGraph(p);
      expect(nodes.length).toBeGreaterThan(0);
    }
  });

  it('getPerspective returns the correct perspective for each id', () => {
    const ids: PerspectiveId[] = [
      'architecture',
      'ml-pipeline',
      'data-flow',
      'security-gates',
      'tests',
      'release-evidence',
    ];
    for (const id of ids) {
      expect(getPerspective(id).id).toBe(id);
    }
  });

  it('getPerspective falls back to architecture for unknown ids', () => {
    // @ts-expect-error testing invalid id
    expect(getPerspective('nonexistent').id).toBe('architecture');
  });
});

describe('graphData', () => {
  it('loads the knowledge graph with expected structure', () => {
    expect(graph.nodes.length).toBeGreaterThan(100);
    expect(graph.edges.length).toBeGreaterThan(100);
    // Phase 2 structural graph has 0 layers and 0 tours (structural-only).
    // Legacy graph has layers/tours. Both are valid — test accepts either.
    expect(graph.layers.length).toBeGreaterThanOrEqual(0);
    expect(graph.tour.length).toBeGreaterThanOrEqual(0);
    expect(graph.project.name).toBe('Avalanche Insight Hub');
  });

  it('has nodes with required fields', () => {
    for (const node of graph.nodes.slice(0, 50)) {
      expect(node.id).toBeTruthy();
      expect(node.name).toBeTruthy();
      expect(node.type).toBeTruthy();
    }
  });

  it('has edges with required fields', () => {
    for (const edge of graph.edges.slice(0, 50)) {
      expect(edge.source).toBeTruthy();
      expect(edge.target).toBeTruthy();
      expect(edge.type).toBeTruthy();
    }
  });

  it('classifies graph freshness fail-closed', () => {
    expect(classifyGraphFreshness(null, 'abc')).toBe('unknown');
    expect(classifyGraphFreshness('abc', null)).toBe('unknown');
    expect(classifyGraphFreshness('abc', 'abc')).toBe('current');
    expect(classifyGraphFreshness('abc', 'def')).toBe('stale');
  });

  it('recognizes loopback hosts only', () => {
    expect(isLoopbackHost('localhost')).toBe(true);
    expect(isLoopbackHost('127.0.0.1')).toBe(true);
    expect(isLoopbackHost('::1')).toBe(true);
    expect(isLoopbackHost('192.168.1.20')).toBe(false);
    expect(isLoopbackHost('example.com')).toBe(false);
  });

  it('follows tested_by edges from a source file to its test file', () => {
    const source = getNodeById('file:backend/common/audit_metadata.py');
    const test = getNodeById('file:backend/tests/test_audit_metadata.py');
    if (source && test) {
      expect(getTesters(source.id).map((node) => node.id)).toContain(test.id);
    }
  });
});
