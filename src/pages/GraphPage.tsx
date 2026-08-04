import { useState, useEffect, useMemo } from 'react';
import {
  loadGraph,
  loadExplanations,
  loadGraphManifest,
  buildGraphIndex,
  type KnowledgeGraph,
  type GraphManifest,
  type GraphIndex,
} from '../lib/graphLoader';
import {
  getPerspective,
  filterGraph,
  type PerspectiveId,
} from '../lib/perspectives';
import GraphCanvas from '../components/GraphCanvas';
import SearchBar from '../components/SearchBar';
import FilterPanel from '../components/FilterPanel';
import NodeDetailPanel from '../components/NodeDetailPanel';
import TableView from '../components/TableView';
import ProvenanceCard from '../components/ProvenanceCard';

type ViewMode = 'graph' | 'table';

export default function GraphPage() {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [provenance, setProvenance] = useState<GraphManifest | null>(null);
  const [index, setIndex] = useState<GraphIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activePerspective, setActivePerspective] = useState<PerspectiveId>('architecture');
  const [nodeTypeFilter, setNodeTypeFilter] = useState<Set<string>>(new Set(['file', 'function', 'class']));
  const [languageFilter, setLanguageFilter] = useState<string | null>(null);
  const [edgeTypeFilter, setEdgeTypeFilter] = useState<Set<string>>(new Set());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('graph');

  // Load data
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [g, e, p] = await Promise.all([
          loadGraph(),
          loadExplanations(),
          loadGraphManifest(),
        ]);
        if (!active) return;
        setGraph(g);
        setExplanations(e);
        setProvenance(p);
        setIndex(buildGraphIndex(g));
        setLoading(false);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load graph data');
        setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  // Available languages
  const availableLanguages = useMemo(() => {
    if (!graph) return [];
    const langs = new Set<string>();
    for (const node of graph.nodes) {
      if (node.language) langs.add(node.language);
    }
    return Array.from(langs).sort();
  }, [graph]);

  // Available edge types
  const availableEdgeTypes = useMemo(() => {
    if (!graph) return [];
    const types = new Set<string>();
    for (const edge of graph.edges) {
      types.add(edge.type);
    }
    return Array.from(types).sort();
  }, [graph]);

  // Filtered nodes and edges
  const filtered = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    const perspective = getPerspective(activePerspective);
    const { nodes: perspNodes, edges: perspEdges } = filterGraph(graph.nodes, graph.edges, perspective);

    // Apply node type filter
    let resultNodes = perspNodes.filter((n) => nodeTypeFilter.has(n.type));

    // Apply language filter
    if (languageFilter) {
      resultNodes = resultNodes.filter((n) => n.language === languageFilter);
    }

    // Apply search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      resultNodes = resultNodes.filter((n) => {
        const haystack = [n.name, n.relativePath ?? '', n.type, ...(n.tags ?? [])].join(' ').toLowerCase();
        return haystack.includes(q);
      });
    }

    const nodeIds = new Set(resultNodes.map((n) => n.id));
    let resultEdges = perspEdges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

    // Apply edge type filter
    if (edgeTypeFilter.size > 0) {
      resultEdges = resultEdges.filter((e) => edgeTypeFilter.has(e.type));
    }

    return { nodes: resultNodes, edges: resultEdges };
  }, [graph, activePerspective, nodeTypeFilter, languageFilter, searchQuery, edgeTypeFilter]);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !index) return null;
    return index.nodeById.get(selectedNodeId) ?? null;
  }, [selectedNodeId, index]);

  if (loading) {
    return <div className="loading">Loading knowledge graph…</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  if (!graph || !index) {
    return <div className="error">Graph data not available</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ fontSize: '1.25rem' }}>Knowledge Graph</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setViewMode('graph')}
            style={{
              padding: '0.25rem 0.75rem',
              border: '1px solid var(--border)',
              borderRadius: '0.25rem',
              background: viewMode === 'graph' ? 'var(--accent)' : 'var(--bg-card)',
              color: viewMode === 'graph' ? 'var(--bg)' : 'var(--text)',
              cursor: 'pointer',
              fontSize: '0.85rem',
            }}
          >
            Graph View
          </button>
          <button
            onClick={() => setViewMode('table')}
            style={{
              padding: '0.25rem 0.75rem',
              border: '1px solid var(--border)',
              borderRadius: '0.25rem',
              background: viewMode === 'table' ? 'var(--accent)' : 'var(--bg-card)',
              color: viewMode === 'table' ? 'var(--bg)' : 'var(--text)',
              cursor: 'pointer',
              fontSize: '0.85rem',
            }}
          >
            Table View
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '1rem', flex: 1, minHeight: 0 }}>
        {/* Left sidebar */}
        <div style={{ width: '240px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
          <SearchBar onSearch={setSearchQuery} />
          <FilterPanel
            activePerspective={activePerspective}
            onPerspectiveChange={setActivePerspective}
            nodeTypeFilter={nodeTypeFilter}
            onNodeTypeChange={setNodeTypeFilter}
            languageFilter={languageFilter}
            onLanguageChange={setLanguageFilter}
            availableLanguages={availableLanguages}
            edgeTypeFilter={edgeTypeFilter}
            onEdgeTypeChange={setEdgeTypeFilter}
            availableEdgeTypes={availableEdgeTypes}
          />
          <ProvenanceCard manifest={provenance} />
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Showing {filtered.nodes.length} nodes, {filtered.edges.length} edges
          </div>
        </div>

        {/* Main content area */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: '1rem' }}>
          {viewMode === 'graph' ? (
            <div style={{ flex: 1, border: '1px solid var(--border)', borderRadius: '0.5rem', overflow: 'hidden', background: 'var(--bg-card)' }}>
              <GraphCanvas
                nodes={filtered.nodes}
                edges={filtered.edges}
                onNodeClick={setSelectedNodeId}
                selectedNodeId={selectedNodeId}
              />
            </div>
          ) : (
            <div style={{ flex: 1, border: '1px solid var(--border)', borderRadius: '0.5rem', overflow: 'hidden', background: 'var(--bg-card)' }}>
              <TableView nodes={filtered.nodes} onNodeClick={setSelectedNodeId} />
            </div>
          )}

          {/* Detail panel */}
          {selectedNode && (
            <div style={{ width: '320px', flexShrink: 0, overflowY: 'auto' }}>
              <NodeDetailPanel
                node={selectedNode}
                index={index}
                explanation={explanations[selectedNode.id] ?? null}
                onNodeClick={setSelectedNodeId}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
