import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeMouseHandler,
  type OnNodeDrag,
  BackgroundVariant,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';

import type { GraphNode, GraphEdge } from '@/lib/knowledge-graph/graphData';
import type { Perspective } from '@/lib/knowledge-graph/perspectives';

interface KnowledgeGraphViewProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  perspective: Perspective;
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
}

const NODE_COLORS: Record<string, string> = {
  file: '#3b82f6',
  function: '#10b981',
  class: '#f59e0b',
  pipeline: '#8b5cf6',
  config: '#6b7280',
  document: '#ec4899',
};

// Shape icons for accessibility — encodes node type via icon, not just color (WCAG)
const NODE_ICONS: Record<string, string> = {
  file: '📄',
  function: '⚡',
  class: '🔷',
  pipeline: '🔗',
  config: '⚙️',
  document: '📋',
};

const NODE_TYPE_LABELS: Record<string, string> = {
  file: 'File',
  function: 'Function',
  class: 'Class',
  pipeline: 'Pipeline',
  config: 'Config',
  document: 'Document',
};

const EDGE_COLORS: Record<string, string> = {
  contains: '#475569',
  imports: '#0ea5e9',
  calls: '#f97316',
  tested_by: '#22c55e',
};

const EDGE_TYPES_LIST = ['contains', 'imports', 'calls', 'tested_by'] as const;
type EdgeFilterType = typeof EDGE_TYPES_LIST[number];

function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  direction: 'TB' | 'LR' = 'TB',
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, ranksep: 80, nodesep: 40, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 220;
  const nodeHeight = 60;

  for (const node of nodes) {
    g.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const rfNodes: Node[] = nodes.map((node) => {
    const pos = g.node(node.id);
    return {
      id: node.id,
      type: 'codeNode',
      position: { x: pos?.x ?? 0, y: pos?.y ?? 0 },
      data: {
        label: node.name,
        nodeType: node.type,
        filePath: node.filePath,
        originalNode: node,
      },
    };
  });

  const rfEdges: Edge[] = edges.map((edge, i) => ({
    id: `e-${i}-${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    animated: edge.type === 'calls',
    style: { stroke: EDGE_COLORS[edge.type] || '#64748b', strokeWidth: 1.5 },
    data: { edgeType: edge.type },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

// Memoized CodeNode — prevents re-render of all nodes when only selection changes
const CodeNode = memo(function CodeNode({ data }: { data: { label: string; nodeType: string; filePath?: string } }) {
  const color = NODE_COLORS[data.nodeType] || '#64748b';
  const icon = NODE_ICONS[data.nodeType] || '❓';
  const typeLabel = NODE_TYPE_LABELS[data.nodeType] || data.nodeType;
  return (
    <div
      className="rounded-lg border bg-card px-3 py-2 text-xs shadow-md transition-colors hover:border-primary/50"
      style={{ borderColor: `${color}40`, width: 200 }}
      role="button"
      tabIndex={0}
      aria-label={`${typeLabel}: ${data.label}${data.filePath ? ` in ${data.filePath}` : ''}`}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-sm" aria-hidden="true">{icon}</span>
        <div className="h-2 w-2 shrink-0 rounded-sm" style={{ background: color }} aria-hidden="true" />
        <span className="truncate font-medium text-foreground">{data.label}</span>
      </div>
      {data.filePath && (
        <div className="mt-1 truncate text-[10px] text-muted-foreground">{data.filePath}</div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  );
});

const nodeTypes: NodeTypes = { codeNode: CodeNode };

export function KnowledgeGraphView({
  nodes,
  edges,
  perspective,
  selectedNodeId,
  onNodeClick,
}: KnowledgeGraphViewProps) {
  // Edge-type filter state — all enabled by default
  const [enabledEdgeTypes, setEnabledEdgeTypes] = useState<Set<EdgeFilterType>>(
    () => new Set(EDGE_TYPES_LIST),
  );

  // Filter edges by enabled types before layout
  const filteredEdges = useMemo(() => {
    return edges.filter((e) => enabledEdgeTypes.has(e.type as EdgeFilterType));
  }, [edges, enabledEdgeTypes]);

  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(
    () => layoutGraph(nodes, filteredEdges, 'TB'),
    [nodes, filteredEdges],
  );

  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState(layoutedEdges);

  useEffect(() => {
    setRfNodes(layoutedNodes);
    setRfEdges(layoutedEdges);
  }, [layoutedNodes, layoutedEdges, setRfNodes, setRfEdges]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      onNodeClick(node.id);
    },
    [onNodeClick],
  );

  const handleNodeDragStop: OnNodeDrag = useCallback(() => {}, []);

  const highlightIds = perspective.highlightIds;

  const styledNodes = useMemo(() => {
    return rfNodes.map((node) => {
      const isHighlighted = highlightIds?.has(node.id);
      const isSelected = node.id === selectedNodeId;
      return {
        ...node,
        selected: isSelected,
        style: {
          ...node.style,
          opacity: highlightIds && !isHighlighted ? 0.35 : 1,
          border: isSelected ? '2px solid #0ea5e9' : undefined,
        },
      };
    });
  }, [rfNodes, highlightIds, selectedNodeId]);

  const toggleEdgeType = useCallback((type: EdgeFilterType) => {
    setEnabledEdgeTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  return (
    <div
      className="relative h-full w-full"
      aria-label="Code knowledge graph visualization"
      aria-describedby="graph-description"
    >
      <span id="graph-description" className="sr-only">
        Interactive graph showing {nodes.length} nodes and {filteredEdges.length} edges.
        Use arrow keys to navigate between nodes. Press Enter to select a node.
      </span>
      {/* Edge-type filter controls */}
      <div className="absolute right-2 top-12 z-10 flex flex-col gap-1 rounded-md border bg-card/90 p-2 text-xs backdrop-blur">
        <span className="mb-1 font-medium text-foreground">Edge Types</span>
        {EDGE_TYPES_LIST.map((type) => (
          <label key={type} className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={enabledEdgeTypes.has(type)}
              onChange={() => toggleEdgeType(type)}
              className="h-3 w-3"
            />
            <span
              className="inline-block h-2 w-3 rounded-sm"
              style={{ background: EDGE_COLORS[type] }}
              aria-hidden="true"
            />
            <span className="text-muted-foreground">{type}</span>
          </label>
        ))}
      </div>
      <ReactFlow
        nodes={styledNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeDragStop={handleNodeDragStop}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
        minZoom={0.1}
        maxZoom={3}
        proOptions={{ hideAttribution: true }}
        nodesFocusable
        edgesFocusable
        nodesConnectable={false}
        nodesDraggable={false}
        deleteKeyCode={null}
        ariaLabelConfig={{
          'node.a11yDescription.default': 'Press Enter or Space to select this code node.',
          'edge.a11yDescription.default': 'Press Enter or Space to select this relationship edge.',
          'controls.ariaLabel': 'Knowledge graph controls',
          'minimap.ariaLabel': 'Knowledge graph minimap',
        }}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
        <Controls className="bg-card/80 backdrop-blur" />
        <MiniMap
          className="bg-card/80"
          nodeColor={(node) => NODE_COLORS[(node.data as { nodeType: string }).nodeType] || '#64748b'}
          maskColor="rgba(15, 23, 42, 0.7)"
        />
      </ReactFlow>
    </div>
  );
}
