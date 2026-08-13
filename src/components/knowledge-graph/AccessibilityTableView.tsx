import { Fragment, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Search } from 'lucide-react';

import type { GraphEdge, GraphNode } from '@/lib/knowledge-graph/graphData';
import type { Perspective } from '@/lib/knowledge-graph/perspectives';

interface AccessibilityTableViewProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  perspective: Perspective;
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
}

interface RelatedEdge extends GraphEdge {
  direction: 'outgoing' | 'incoming';
}

export function AccessibilityTableView({
  nodes,
  edges,
  perspective,
  selectedNodeId,
  onNodeClick,
}: AccessibilityTableViewProps) {
  const [search, setSearch] = useState('');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const filteredNodes = useMemo(() => {
    if (!search.trim()) return nodes;
    const q = search.toLowerCase();
    return nodes.filter((node) =>
      [node.name, node.filePath || '', node.summary || '', ...(node.tags || [])]
        .join(' ')
        .toLowerCase()
        .includes(q),
    );
  }, [nodes, search]);

  const edgesByNode = useMemo(() => {
    const map = new Map<string, RelatedEdge[]>();
    for (const edge of edges) {
      const outgoing = map.get(edge.source) || [];
      outgoing.push({ ...edge, direction: 'outgoing' });
      map.set(edge.source, outgoing);
      const incoming = map.get(edge.target) || [];
      incoming.push({ ...edge, direction: 'incoming' });
      map.set(edge.target, incoming);
    }
    return map;
  }, [edges]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const node of nodes) map.set(node.id, node);
    return map;
  }, [nodes]);

  const toggleRow = (id: string) => {
    setExpandedRows((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border p-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <label htmlFor="knowledge-graph-search" className="sr-only">Search graph nodes</label>
          <input
            id="knowledge-graph-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={`Search ${nodes.length} nodes...`}
            aria-label="Search graph nodes"
            className="w-full rounded-lg border border-border bg-card/50 py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm" aria-label={`${perspective.label} graph data table`}>
          <caption className="sr-only">
            {perspective.label} perspective: {filteredNodes.length} nodes and {edges.length} relationships.
            Select a node name to open its explanation.
          </caption>
          <thead className="sticky top-0 bg-card/90 backdrop-blur">
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th scope="col" className="px-3 py-2">Name</th>
              <th scope="col" className="px-3 py-2">Type</th>
              <th scope="col" className="px-3 py-2">Path</th>
              <th scope="col" className="px-3 py-2">Relationships</th>
            </tr>
          </thead>
          <tbody>
            {filteredNodes.map((node) => {
              const nodeEdges = edgesByNode.get(node.id) || [];
              const isExpanded = expandedRows.has(node.id);
              const isSelected = node.id === selectedNodeId;
              return (
                <Fragment key={node.id}>
                  <tr
                    aria-selected={isSelected}
                    className={`border-b border-border/50 transition-colors ${
                      isSelected ? 'bg-primary/10' : 'hover:bg-muted/30'
                    }`}
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5">
                        {nodeEdges.length > 0 && (
                          <button
                            type="button"
                            onClick={() => toggleRow(node.id)}
                            className="min-h-7 min-w-7 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
                            aria-label={isExpanded ? `Collapse relationships for ${node.name}` : `Expand relationships for ${node.name}`}
                            aria-expanded={isExpanded}
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-3 w-3" aria-hidden="true" />
                            ) : (
                              <ChevronRight className="h-3 w-3" aria-hidden="true" />
                            )}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => onNodeClick(node.id)}
                          className="min-h-8 rounded px-1 text-left font-medium text-foreground underline-offset-2 hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
                          aria-current={isSelected ? 'true' : undefined}
                        >
                          {node.name}
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                        {node.type}
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-3 py-2 text-xs text-muted-foreground">
                      {node.filePath || '—'}
                    </td>
                    <td className="px-3 py-2 text-xs tabular-nums text-muted-foreground">
                      {nodeEdges.length}
                    </td>
                  </tr>
                  {isExpanded && nodeEdges.length > 0 && (
                    <tr className="border-b border-border/30 bg-muted/10">
                      <td colSpan={4} className="px-6 py-2">
                        <ul className="space-y-1 text-xs text-muted-foreground" aria-label={`Relationships for ${node.name}`}>
                          {nodeEdges.map((edge) => {
                            const relatedId = edge.direction === 'outgoing' ? edge.target : edge.source;
                            const related = nodeMap.get(relatedId);
                            return (
                              <li key={`${edge.direction}-${edge.type}-${edge.source}-${edge.target}`}>
                                <span className="rounded bg-muted px-1 text-[10px] uppercase">
                                  {edge.type}
                                </span>{' '}
                                <span>{edge.direction === 'outgoing' ? 'to' : 'from'}</span>{' '}
                                <button
                                  type="button"
                                  onClick={() => onNodeClick(relatedId)}
                                  className="font-medium text-foreground underline-offset-2 hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
                                >
                                  {related?.name || relatedId}
                                </button>
                                {related?.filePath && (
                                  <span className="ml-1 text-muted-foreground/60">({related.filePath})</span>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {filteredNodes.length === 0 && (
          <div className="p-6 text-center text-sm text-muted-foreground" role="status">
            No nodes match “{search}”.
          </div>
        )}
      </div>
    </div>
  );
}
