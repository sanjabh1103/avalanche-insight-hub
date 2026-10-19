import { describe, it, expect } from 'vitest';
import { getPerspective, filterGraph, perspectives, type PerspectiveId } from '../lib/perspectives';
import type { GraphNode, GraphEdge } from '../lib/graphLoader';

const mockNodes: GraphNode[] = [
  { id: 'file:src/app.ts', name: 'app.ts', type: 'file', relativePath: 'src/app.ts', language: 'typescript' },
  { id: 'function:backend/train_model.py:train', name: 'train', type: 'function', relativePath: 'backend/train_model.py', language: 'python', tags: ['model', 'train'] },
  { id: 'function:backend/tests/test_foo.py:test_foo', name: 'test_foo', type: 'function', relativePath: 'backend/tests/test_foo.py', language: 'python', tags: ['test'] },
  { id: 'class:src/SecurityGate.ts:SecurityGate', name: 'SecurityGate', type: 'class', relativePath: 'src/SecurityGate.ts', language: 'typescript', tags: ['security', 'gate'] },
];

const mockEdges: GraphEdge[] = [
  { source: 'file:src/app.ts', target: 'class:src/SecurityGate.ts:SecurityGate', type: 'contains' },
];

describe('perspectives', () => {
  it('returns all perspectives', () => {
    expect(perspectives.length).toBeGreaterThanOrEqual(7);
  });

  it('getPerspective returns correct perspective', () => {
    const p = getPerspective('ml-pipeline');
    expect(p.id).toBe('ml-pipeline');
  });

  it('getPerspective falls back to first for unknown id', () => {
    const p = getPerspective('nonexistent' as PerspectiveId);
    expect(p.id).toBe('all');
  });

  it('all perspective includes all nodes', () => {
    const p = getPerspective('all');
    const { nodes } = filterGraph(mockNodes, mockEdges, p);
    expect(nodes.length).toBe(4);
  });

  it('tests perspective filters to test nodes', () => {
    const p = getPerspective('tests');
    const { nodes } = filterGraph(mockNodes, mockEdges, p);
    expect(nodes.some((n) => n.name === 'test_foo')).toBe(true);
    expect(nodes.some((n) => n.name === 'app.ts')).toBe(false);
  });

  it('ml-pipeline perspective filters to ML nodes', () => {
    const p = getPerspective('ml-pipeline');
    const { nodes } = filterGraph(mockNodes, mockEdges, p);
    expect(nodes.some((n) => n.name === 'train')).toBe(true);
  });

  it('security-gates perspective filters to security nodes', () => {
    const p = getPerspective('security-gates');
    const { nodes } = filterGraph(mockNodes, mockEdges, p);
    expect(nodes.some((n) => n.name === 'SecurityGate')).toBe(true);
  });
});
