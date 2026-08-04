import { describe, it, expect } from 'vitest';
import { buildGraphIndex, type KnowledgeGraph } from '../lib/graphLoader';

const mockGraph: KnowledgeGraph = {
  version: 'test',
  kind: 'test',
  project: { name: 'test', languages: ['typescript'], frameworks: [], description: 'test' },
  nodes: [
    { id: 'file:src/a.ts', name: 'a.ts', type: 'file', relativePath: 'src/a.ts', language: 'typescript' },
    { id: 'function:src/a.ts:foo', name: 'foo', type: 'function', relativePath: 'src/a.ts', language: 'typescript' },
    { id: 'class:src/a.ts:Bar', name: 'Bar', type: 'class', relativePath: 'src/a.ts', language: 'typescript' },
  ],
  edges: [
    { source: 'file:src/a.ts', target: 'function:src/a.ts:foo', type: 'contains' },
    { source: 'file:src/a.ts', target: 'class:src/a.ts:Bar', type: 'contains' },
    { source: 'function:src/a.ts:foo', target: 'class:src/a.ts:Bar', type: 'calls' },
  ],
  layers: [],
  tour: [],
};

describe('graphLoader', () => {
  it('builds graph index with node lookup', () => {
    const index = buildGraphIndex(mockGraph);
    expect(index.nodeById.size).toBe(3);
    expect(index.nodeById.get('file:src/a.ts')?.name).toBe('a.ts');
  });

  it('builds incoming/outgoing edge maps', () => {
    const index = buildGraphIndex(mockGraph);
    const outgoing = index.outgoingBySource.get('file:src/a.ts') ?? [];
    expect(outgoing.length).toBe(2);
    const incoming = index.incomingByTarget.get('class:src/a.ts:Bar') ?? [];
    expect(incoming.length).toBe(2);
  });

  it('handles empty graph', () => {
    const emptyGraph: KnowledgeGraph = {
      version: '', kind: '', project: { name: '', languages: [], frameworks: [], description: '' },
      nodes: [], edges: [], layers: [], tour: [],
    };
    const index = buildGraphIndex(emptyGraph);
    expect(index.nodeById.size).toBe(0);
  });
});
