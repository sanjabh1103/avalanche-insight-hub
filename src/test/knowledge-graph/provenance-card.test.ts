import { describe, expect, it } from 'vitest';

import { computeProvenanceDecision } from '@/lib/knowledge-graph/provenanceDecision';
import type { GraphProvenance } from '@/lib/knowledge-graph/graphData';

function makeProvenance(overrides: Partial<GraphProvenance> = {}): GraphProvenance {
  return {
    source: 'local-api',
    freshness: 'current',
    graphHash: 'abc123',
    graphAnalyzedAt: '2026-08-01T00:00:00Z',
    graphCommit: 'abcdef123456',
    currentCommit: 'abcdef123456',
    nodeCount: 4689,
    edgeCount: 7534,
    detail: 'Graph is current',
    ...overrides,
  };
}

describe('computeProvenanceDecision', () => {
  it('returns "Stale snapshot" when freshness is stale', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'stale',
      graphCommit: 'old123',
      currentCommit: 'new456',
    }));
    expect(result.statusLabel).toBe('Stale snapshot');
    expect(result.isStale).toBe(true);
    expect(result.statusClass).toContain('amber');
  });

  it('returns "Snapshot context changed" when worktree changed since snapshot', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeChangedSinceSnapshot: true,
    }));
    expect(result.statusLabel).toBe('Snapshot context changed');
    expect(result.changedSinceSnapshot).toBe(true);
    expect(result.statusClass).toContain('amber');
  });

  it('returns "Commit current / dirty tree" when current but dirty', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeDirty: true,
    }));
    expect(result.statusLabel).toBe('Commit current / dirty tree');
    expect(result.isDirty).toBe(true);
    expect(result.statusClass).toContain('amber');
  });

  it('returns "Current snapshot" when current and clean', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeDirty: false,
      worktreeChangedSinceSnapshot: false,
    }));
    expect(result.statusLabel).toBe('Current snapshot');
    expect(result.isCurrent).toBe(true);
    expect(result.statusClass).toContain('emerald');
  });

  it('returns "Freshness unknown" for unknown freshness', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'unknown',
    }));
    expect(result.statusLabel).toBe('Freshness unknown');
    expect(result.statusClass).toContain('muted');
  });

  it('provides stale reason with rebuild command when stale', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'stale',
    }));
    expect(result.staleReason).not.toBeNull();
    expect(result.staleReason).toContain('refresh_knowledge_graph_structural.sh');
  });

  it('provides stale reason mentioning rebuild when worktree changed', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeChangedSinceSnapshot: true,
    }));
    expect(result.staleReason).not.toBeNull();
    expect(result.staleReason).toContain('Rebuild to reflect current code');
  });

  it('provides stale reason mentioning AI mode blocked when dirty', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeDirty: true,
    }));
    expect(result.staleReason).not.toBeNull();
    expect(result.staleReason).toContain('AI mode is blocked until clean');
  });

  it('returns null stale reason when current and clean', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeDirty: false,
      worktreeChangedSinceSnapshot: false,
    }));
    expect(result.staleReason).toBeNull();
  });

  it('stale takes priority over changedSinceSnapshot and dirty', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'stale',
      worktreeDirty: true,
      worktreeChangedSinceSnapshot: true,
    }));
    expect(result.statusLabel).toBe('Stale snapshot');
    expect(result.staleReason).toContain('refresh_knowledge_graph_structural.sh');
  });

  it('changedSinceSnapshot takes priority over dirty', () => {
    const result = computeProvenanceDecision(makeProvenance({
      freshness: 'current',
      worktreeDirty: true,
      worktreeChangedSinceSnapshot: true,
    }));
    expect(result.statusLabel).toBe('Snapshot context changed');
  });
});
