import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { copyFileSync, mkdirSync, writeFileSync, rmSync, existsSync } from 'fs';
import { resolve } from 'path';

// The vite plugin reads from fixed paths relative to the project root.
// We test the nodePacket function by writing a test graph to the expected path
// and then restoring the original after tests.

const GRAPH_PATH = resolve(process.cwd(), '.understand-anything/phase2-structural-graph.json');
const MANIFEST_PATH = resolve(process.cwd(), '.understand-anything/phase2-structural-manifest.json');
const BACKUP_GRAPH = GRAPH_PATH + '.test-backup';
const BACKUP_MANIFEST = MANIFEST_PATH + '.test-backup';

const testGraph = {
  nodes: [
    { id: 'file:src/a.ts', name: 'a.ts', type: 'file', filePath: 'src/a.ts' },
    { id: 'function:src/a.ts:foo', name: 'foo', type: 'function', filePath: 'src/a.ts' },
    { id: 'function:src/a.ts:bar', name: 'bar', type: 'function', filePath: 'src/a.ts' },
    { id: 'file:src/b.ts', name: 'b.ts', type: 'file', filePath: 'src/b.ts' },
    { id: 'function:src/b.ts:baz', name: 'baz', type: 'function', filePath: 'src/b.ts' },
    { id: 'file:src/secret.ts', name: 'secret.ts', type: 'file', filePath: 'backend/common/risk_math.py' },
  ],
  edges: [
    { source: 'file:src/a.ts', target: 'function:src/a.ts:foo', type: 'contains', direction: 'forward', weight: 1 },
    { source: 'file:src/a.ts', target: 'function:src/a.ts:bar', type: 'contains', direction: 'forward', weight: 1 },
    { source: 'function:src/a.ts:foo', target: 'function:src/b.ts:baz', type: 'calls', direction: 'forward', weight: 1 },
    { source: 'file:src/a.ts', target: 'file:src/b.ts', type: 'imports', direction: 'forward', weight: 1 },
    { source: 'file:src/a.ts', target: 'file:src/secret.ts', type: 'imports', direction: 'forward', weight: 1 },
    { source: 'function:src/a.ts:foo', target: 'function:src/a.ts:bar', type: 'tested_by', direction: 'forward', weight: 1 },
  ],
};

const testManifest = {
  snapshotId: 'test-snapshot-001',
  analyzedCommit: 'abc123',
  graphSha256: 'test-hash-001',
  analyzedAt: '2026-08-01T00:00:00Z',
  sourceHashes: [
    { path: 'src/a.ts', sha256: 'hash-a' },
    { path: 'src/b.ts', sha256: 'hash-b' },
  ],
};

describe('vite-plugin-code-api nodePacket', () => {
  beforeEach(() => {
    // Backup existing files if they exist
    if (existsSync(GRAPH_PATH)) {
      copyFileSync(GRAPH_PATH, BACKUP_GRAPH);
    }
    if (existsSync(MANIFEST_PATH)) {
      copyFileSync(MANIFEST_PATH, BACKUP_MANIFEST);
    }
    // Write test fixtures
    mkdirSync(resolve(process.cwd(), '.understand-anything'), { recursive: true });
    writeFileSync(GRAPH_PATH, JSON.stringify(testGraph));
    writeFileSync(MANIFEST_PATH, JSON.stringify(testManifest));
  });

  afterEach(() => {
    // Restore originals or remove test files
    if (existsSync(BACKUP_GRAPH)) {
      copyFileSync(BACKUP_GRAPH, GRAPH_PATH);
      rmSync(BACKUP_GRAPH);
    } else if (existsSync(GRAPH_PATH)) {
      rmSync(GRAPH_PATH);
    }
    if (existsSync(BACKUP_MANIFEST)) {
      copyFileSync(BACKUP_MANIFEST, MANIFEST_PATH);
      rmSync(BACKUP_MANIFEST);
    } else if (existsSync(MANIFEST_PATH)) {
      rmSync(MANIFEST_PATH);
    }
  });

  it('returns node packet with correct node data', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:src/a.ts');
    expect(packet).not.toBeNull();
    expect(packet?.node).toBeDefined();
    expect((packet?.node as Record<string, unknown>).id).toBe('file:src/a.ts');
  });

  it('returns connected edges for the requested node', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:src/a.ts');
    const edges = packet?.relatedEdges as Array<Record<string, unknown>>;
    expect(edges).toBeDefined();
    expect(edges.length).toBeGreaterThan(0);
    // Should include contains, imports edges
    const edgeTypes = edges.map((e) => e.type);
    expect(edgeTypes).toContain('contains');
    expect(edgeTypes).toContain('imports');
  });

  it('returns related nodes connected to the requested node', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:src/a.ts');
    const relatedNodes = packet?.relatedNodes as Array<Record<string, unknown>>;
    expect(relatedNodes).toBeDefined();
    expect(relatedNodes.length).toBeGreaterThan(0);
    // Should include functions foo and bar, and file b.ts
    const relatedIds = relatedNodes.map((n) => n.id);
    expect(relatedIds).toContain('function:src/a.ts:foo');
    expect(relatedIds).toContain('function:src/a.ts:bar');
    expect(relatedIds).toContain('file:src/b.ts');
  });

  it('filters out denylisted nodes from related nodes', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:src/a.ts');
    const relatedNodes = packet?.relatedNodes as Array<Record<string, unknown>>;
    const relatedIds = relatedNodes.map((n) => n.id);
    // The denylisted node (file:src/secret.ts with filePath backend/common/risk_math.py)
    // should NOT appear in related nodes
    expect(relatedIds).not.toContain('file:src/secret.ts');
  });

  it('returns null for non-existent node', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:nonexistent.ts');
    expect(packet).toBeNull();
  });

  it('returns null for denylisted node', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    // file:src/secret.ts has filePath backend/common/risk_math.py which is denylisted
    const packet = nodePacket('file:src/secret.ts');
    expect(packet).toBeNull();
  });

  it('includes source hash for file nodes', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:src/a.ts');
    expect(packet?.sourceHash).toBe('hash-a');
  });

  it('includes provenance in the packet', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    const packet = nodePacket('file:src/a.ts');
    expect(packet?.provenance).toBeDefined();
  });

  it('cache invalidation: returns updated data after graph file changes', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    // First call — caches the node map
    const packet1 = nodePacket('file:src/a.ts');
    expect(packet1).not.toBeNull();

    // Update the graph file with a new node
    const updatedGraph = {
      ...testGraph,
      nodes: [...testGraph.nodes, { id: 'file:src/c.ts', name: 'c.ts', type: 'file', filePath: 'src/c.ts' }],
    };
    writeFileSync(GRAPH_PATH, JSON.stringify(updatedGraph));

    // Wait a moment for mtime to change
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Second call — cache should be invalidated by mtime change
    const packet2 = nodePacket('file:src/c.ts');
    expect(packet2).not.toBeNull();
    expect((packet2?.node as Record<string, unknown>).id).toBe('file:src/c.ts');
  });

  it('handles nodes with no connections gracefully', async () => {
    const { nodePacket } = await import('../../../vite-plugin-code-api');
    // Add an isolated node to the graph
    const updatedGraph = {
      ...testGraph,
      nodes: [...testGraph.nodes, { id: 'file:src/isolated.ts', name: 'isolated.ts', type: 'file', filePath: 'src/isolated.ts' }],
    };
    writeFileSync(GRAPH_PATH, JSON.stringify(updatedGraph));
    await new Promise((resolve) => setTimeout(resolve, 50));

    const packet = nodePacket('file:src/isolated.ts');
    expect(packet).not.toBeNull();
    expect((packet?.relatedEdges as unknown[])).toHaveLength(0);
    expect((packet?.relatedNodes as unknown[])).toHaveLength(0);
  });
});
