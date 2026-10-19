import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Info, Network, RefreshCw, Table, X } from 'lucide-react';

import {
  bundledGraphProvenance,
  fetchGraphProvenance,
  fetchGraphSnapshot,
  getNodeById,
  graphStats,
  isLoopbackHost,
  loadBundledGraph,
  setActiveGraph,
  type GraphSnapshotManifest,
  type GraphProvenance,
} from '@/lib/knowledge-graph/graphData';
import { AudienceDepthControls } from '@/components/knowledge-graph/AudienceDepthControls';
import type { AudienceId, DepthId } from '@/lib/knowledge-graph/audienceModel';
import {
  perspectives,
  getPerspective,
  filterGraph,
  type PerspectiveId,
} from '@/lib/knowledge-graph/perspectives';
import { KnowledgeGraphView } from '@/components/knowledge-graph/KnowledgeGraphView';
import { PerspectiveSwitcher } from '@/components/knowledge-graph/PerspectiveSwitcher';
import { NodeDetailPanel } from '@/components/knowledge-graph/NodeDetailPanel';
import { AccessibilityTableView } from '@/components/knowledge-graph/AccessibilityTableView';
import { computeProvenanceDecision } from '@/lib/knowledge-graph/provenanceDecision';
import KnowledgeGraphUnavailable from './KnowledgeGraphUnavailable';

type ViewMode = 'graph' | 'table';

export default function KnowledgeGraphPage() {
  const [activePerspective, setActivePerspective] = useState<PerspectiveId>('architecture');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
  const [showInfo, setShowInfo] = useState(false);
  const [provenance, setProvenance] = useState<GraphProvenance>(bundledGraphProvenance);
  const [snapshotManifest, setSnapshotManifest] = useState<GraphSnapshotManifest>({});
  const [activeAudience, setActiveAudience] = useState<AudienceId>('novice');
  const [activeDepth, setActiveDepth] = useState<DepthId>('briefing');
  // G6: AI mode state lifted here for persistence across node selections
  const [aiMode, setAiMode] = useState(false);

  useEffect(() => {
    let active = true;
    // FIX-5 (H-3): Load the bundled graph first (dev-only, async dynamic import).
    // Then fetch the live snapshot which may replace it.
    void loadBundledGraph().then(() =>
      Promise.all([fetchGraphProvenance(), fetchGraphSnapshot()]).then(([nextProvenance, snapshot]) => {
        if (!active) return;
        if (snapshot?.graph) setActiveGraph(snapshot.graph, snapshot.manifest?.graphSha256 ?? null);
        setSnapshotManifest(snapshot?.manifest || {});
        setProvenance(nextProvenance);
      }),
    );
    return () => {
      active = false;
    };
  }, []);

  // Reload: re-fetch provenance and snapshot without full page reload
  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleReload = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [nextProvenance, snapshot] = await Promise.all([fetchGraphProvenance(), fetchGraphSnapshot()]);
      if (snapshot?.graph) setActiveGraph(snapshot.graph, snapshot.manifest?.graphSha256 ?? null);
      setSnapshotManifest(snapshot?.manifest || {});
      setProvenance(nextProvenance);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  // Rebuild: trigger the local structural rebuild script via loopback API.
  // Does not spawn shell commands from browser JS — calls a loopback-only endpoint.
  const [isRebuilding, setIsRebuilding] = useState(false);
  const isRebuildingRef = useRef(false);
  const [rebuildStatus, setRebuildStatus] = useState<string | null>(null);
  const handleRebuild = useCallback(async () => {
    setIsRebuilding(true);
    isRebuildingRef.current = true;
    setRebuildStatus('initiated');
    try {
      const response = await fetch('/api/knowledge-graph/rebuild', { method: 'POST' });
      if (response.status === 202) {
        setRebuildStatus('running');
        // Poll status every 3 seconds until provenance changes
        const pollInterval = setInterval(async () => {
          try {
            const [nextProvenance, snapshot] = await Promise.all([fetchGraphProvenance(), fetchGraphSnapshot()]);
            if (snapshot?.graph) setActiveGraph(snapshot.graph, snapshot.manifest?.graphSha256 ?? null);
            setSnapshotManifest(snapshot?.manifest || {});
            setProvenance(nextProvenance);
            // Check if provenance has updated (graphHash changed or analyzedAt changed)
            if (nextProvenance.graphHash !== provenance.graphHash ||
                nextProvenance.graphAnalyzedAt !== provenance.graphAnalyzedAt) {
              setRebuildStatus('succeeded');
              clearInterval(pollInterval);
              setIsRebuilding(false);
              isRebuildingRef.current = false;
            }
          } catch {
            // Continue polling — rebuild may still be in progress
          }
        }, 3000);
        // Safety timeout: stop polling after 5 minutes
        setTimeout(() => {
          clearInterval(pollInterval);
          if (isRebuildingRef.current) {
            setRebuildStatus('timeout');
            setIsRebuilding(false);
            isRebuildingRef.current = false;
          }
        }, 300_000);
      } else if (response.status === 409) {
        setRebuildStatus('already-running');
        setIsRebuilding(false);
        isRebuildingRef.current = false;
      } else {
        setRebuildStatus('failed');
        setIsRebuilding(false);
        isRebuildingRef.current = false;
      }
    } catch {
      setRebuildStatus('failed');
      setIsRebuilding(false);
      isRebuildingRef.current = false;
    }
  }, [provenance.graphHash, provenance.graphAnalyzedAt]);

  const perspective = getPerspective(activePerspective);
  const graphRevision = provenance.graphHash || 'bundled';
  const { nodes: filteredNodes, edges: filteredEdges } = useMemo(
    () => {
      void graphRevision;
      return filterGraph(perspective);
    },
    [perspective, graphRevision],
  );

  const nodeCounts = useMemo(() => {
    void graphRevision;
    const counts = {} as Record<PerspectiveId, number>;
    for (const p of perspectives) {
      const { nodes } = filterGraph(p);
      counts[p.id] = nodes.length;
    }
    return counts;
  }, [graphRevision]);

  const selectedNode = selectedNodeId ? getNodeById(selectedNodeId) ?? null : null;
  const isLocalAccess = typeof window !== 'undefined' && isLoopbackHost(window.location.hostname);

  if (!isLocalAccess) {
    return <KnowledgeGraphUnavailable />;
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col overflow-hidden bg-background">
      <header className="flex-shrink-0 border-b border-border bg-card/30 backdrop-blur">
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold text-foreground">Code Knowledge Graph</h1>
              <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-300">
                Local only
              </span>
            </div>
            <p className="truncate text-xs text-muted-foreground">
              {graphStats.nodeCount} nodes · {graphStats.edgeCount} edges ·{' '}
              {graphStats.layerCount} layers · {graphStats.tourStepCount} tour steps
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-border p-0.5" role="group" aria-label="View mode">
              <button
                type="button"
                onClick={() => setViewMode('graph')}
                aria-pressed={viewMode === 'graph'}
                aria-label="Graph view"
                className={`rounded-md p-1.5 transition-colors ${
                  viewMode === 'graph'
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Network className="h-4 w-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('table')}
                aria-pressed={viewMode === 'table'}
                aria-label="Table view (accessible alternative)"
                className={`rounded-md p-1.5 transition-colors ${
                  viewMode === 'table'
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Table className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <button
              type="button"
              onClick={() => setShowInfo(!showInfo)}
              aria-pressed={showInfo}
              aria-label="About this graph"
              className={`rounded-md p-1.5 transition-colors ${
                showInfo
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Info className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="px-4 pb-3">
          <PerspectiveSwitcher
            activeId={activePerspective}
            onChange={setActivePerspective}
            nodeCounts={nodeCounts}
          />
          <AudienceDepthControls
            audience={activeAudience}
            depth={activeDepth}
            onAudienceChange={setActiveAudience}
            onDepthChange={setActiveDepth}
          />
          <p className="mt-2 text-xs text-muted-foreground">{perspective.description}</p>
        </div>

        <GraphProvenanceCard
          provenance={provenance}
          onReload={handleReload}
          isReloading={isRefreshing}
          onRebuild={handleRebuild}
          isRebuilding={isRebuilding}
          rebuildStatus={rebuildStatus}
        />
      </header>

      {showInfo && (
        <div className="flex-shrink-0 border-b border-border bg-primary/5 px-4 py-2 text-xs text-muted-foreground">
          <div className="flex items-start justify-between gap-2">
            <div>
              <strong className="text-foreground">About this graph:</strong>{' '}
              This local workspace displays an Understand snapshot and reads source snippets
              from the loopback development API. The snapshot may be stale; use the provenance
              card above before treating a relationship as current. Explanations are currently
              deterministic and are not forecast advice.
            </div>
            <button
              type="button"
              onClick={() => setShowInfo(false)}
              className="rounded-md p-1 text-muted-foreground hover:text-foreground"
              aria-label="Close info"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div
          id="knowledge-graph-panel"
          className="flex-1 overflow-hidden"
          role="tabpanel"
          aria-label={`${perspective.label} graph view`}
        >
          {viewMode === 'graph' ? (
            <KnowledgeGraphView
              nodes={filteredNodes}
              edges={filteredEdges}
              perspective={perspective}
              selectedNodeId={selectedNodeId}
              onNodeClick={setSelectedNodeId}
            />
          ) : (
            <AccessibilityTableView
              nodes={filteredNodes}
              edges={filteredEdges}
              perspective={perspective}
              selectedNodeId={selectedNodeId}
              onNodeClick={setSelectedNodeId}
            />
          )}
        </div>

        {selectedNode && (
          <div className="w-[420px] flex-shrink-0">
            <NodeDetailPanel
              node={selectedNode}
              perspective={activePerspective}
              audience={activeAudience}
              depth={activeDepth}
              snapshotId={snapshotManifest.snapshotId ?? null}
              graphHash={provenance.graphHash}
              graphFreshness={provenance.freshness}
              onClose={() => setSelectedNodeId(null)}
              aiMode={aiMode}
              onAiModeChange={setAiMode}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function GraphProvenanceCard({
  provenance,
  onReload,
  isReloading,
  onRebuild,
  isRebuilding,
  rebuildStatus,
}: {
  provenance: GraphProvenance;
  onReload: () => void;
  isReloading: boolean;
  onRebuild: () => void;
  isRebuilding: boolean;
  rebuildStatus: string | null;
}) {
  const { statusLabel, statusClass, staleReason, isStale, isDirty, changedSinceSnapshot } =
    computeProvenanceDecision(provenance);

  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/60 px-4 py-2 text-[10px] text-muted-foreground"
      role="status"
      aria-live="polite"
      aria-label={`Graph provenance: ${statusLabel}`}
    >
      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ${statusClass}`}>
        {(isStale || isDirty) && <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
        {statusLabel}
      </span>
      <span>Analyzed: {formatProvenanceDate(provenance.graphAnalyzedAt)}</span>
      <span>Graph commit: {shortCommit(provenance.graphCommit)}</span>
      <span>Checkout: {shortCommit(provenance.currentCommit)}</span>
      <span>Source: {provenance.source === 'local-api' ? 'local snapshot API' : 'bundled fallback'}</span>
      {isDirty && <span>Dirty entries: {provenance.worktreeStatusCount ?? 'unknown'}</span>}
      {changedSinceSnapshot && <span>Dirty context hash changed</span>}
      {provenance.semanticStatus && <span>Semantic: {provenance.semanticStatus}</span>}
      <span className="max-w-full truncate" title={provenance.detail}>{provenance.detail}</span>
      {staleReason && (
        <span className="font-medium text-amber-300" title={staleReason}>
          {staleReason}
        </span>
      )}
      {/* Reload snapshot — re-fetches the existing snapshot without rebuilding */}
      <button
        type="button"
        onClick={onReload}
        disabled={isReloading}
        aria-label="Reload graph snapshot"
        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
      >
        <RefreshCw className={`h-3 w-3 ${isReloading ? 'animate-spin' : ''}`} aria-hidden="true" />
        {isReloading ? 'Reloading...' : 'Reload snapshot'}
      </button>
      {/* Rebuild locally — triggers the structural refresh script via loopback API */}
      <button
        type="button"
        onClick={onRebuild}
        disabled={isRebuilding}
        aria-label="Rebuild graph locally"
        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
      >
        <RefreshCw className={`h-3 w-3 ${isRebuilding ? 'animate-spin' : ''}`} aria-hidden="true" />
        {isRebuilding ? `Rebuilding (${rebuildStatus})` : 'Rebuild locally'}
      </button>
      {rebuildStatus && rebuildStatus !== 'running' && rebuildStatus !== 'initiated' && (
        <span className="text-[10px] text-muted-foreground" aria-live="polite">
          Rebuild: {rebuildStatus}
        </span>
      )}
    </div>
  );
}

function formatProvenanceDate(value: string | null): string {
  if (!value) return 'unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'unknown' : date.toLocaleString();
}

function shortCommit(value: string | null): string {
  return value ? value.slice(0, 12) : 'unknown';
}
