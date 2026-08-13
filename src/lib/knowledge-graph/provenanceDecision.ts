/**
 * Provenance card decision logic — extracted for testability.
 *
 * These functions compute the status label, CSS class, and stale reason
 * from a GraphProvenance object. They are used by the GraphProvenanceCard
 * component in KnowledgeGraphPage.tsx.
 */

import type { GraphProvenance } from './graphData';

export interface ProvenanceDecision {
  statusLabel: string;
  statusClass: string;
  staleReason: string | null;
  isStale: boolean;
  isCurrent: boolean;
  isDirty: boolean;
  changedSinceSnapshot: boolean;
}

/**
 * Compute the provenance status label, CSS class, and stale reason.
 * This is the single source of truth for provenance card display logic.
 */
export function computeProvenanceDecision(provenance: GraphProvenance): ProvenanceDecision {
  const isStale = provenance.freshness === 'stale';
  const isCurrent = provenance.freshness === 'current';
  const isDirty = provenance.worktreeDirty === true;
  const changedSinceSnapshot = provenance.worktreeChangedSinceSnapshot === true;

  const statusLabel = isStale
    ? 'Stale snapshot'
    : changedSinceSnapshot
      ? 'Snapshot context changed'
      : isCurrent && isDirty
        ? 'Commit current / dirty tree'
        : isCurrent
          ? 'Current snapshot'
          : 'Freshness unknown';

  const statusClass = isStale || isDirty || changedSinceSnapshot
    ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
    : isCurrent
      ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
      : 'border-border bg-muted/40 text-muted-foreground';

  const staleReason = isStale
    ? 'Graph was built from an older commit. Run `bash scripts/refresh_knowledge_graph_structural.sh` to rebuild.'
    : changedSinceSnapshot
      ? 'Worktree has changed since the snapshot was taken. Rebuild to reflect current code.'
      : isCurrent && isDirty
        ? 'Commit matches but worktree has uncommitted changes. AI mode is blocked until clean.'
        : null;

  return { statusLabel, statusClass, staleReason, isStale, isCurrent, isDirty, changedSinceSnapshot };
}
