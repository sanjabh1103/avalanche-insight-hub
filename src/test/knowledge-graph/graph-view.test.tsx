import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { KnowledgeGraphView } from '@/components/knowledge-graph/KnowledgeGraphView';
import type { GraphNode, GraphEdge } from '@/lib/knowledge-graph/graphData';
import type { Perspective } from '@/lib/knowledge-graph/perspectives';

// ReactFlow requires dimensions — mock the container
vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual('@xyflow/react');
  return {
    ...actual,
    // Avoid dimension errors in jsdom
    useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  };
});

const mockNodes: GraphNode[] = [
  { id: 'file:a.ts', name: 'a.ts', type: 'file', filePath: 'a.ts' },
  { id: 'function:a.ts:foo', name: 'foo', type: 'function', filePath: 'a.ts' },
  { id: 'file:b.ts', name: 'b.ts', type: 'file', filePath: 'b.ts' },
];

const mockEdges: GraphEdge[] = [
  { source: 'file:a.ts', target: 'function:a.ts:foo', type: 'contains', direction: 'forward', weight: 1 },
  { source: 'function:a.ts:foo', target: 'file:b.ts', type: 'calls', direction: 'forward', weight: 1 },
  { source: 'function:a.ts:foo', target: 'file:b.ts', type: 'imports', direction: 'forward', weight: 1 },
];

const mockPerspective: Perspective = {
  id: 'architecture',
  label: 'Architecture',
  description: 'Test perspective',
  icon: 'Network',
  filter: (node) => node.type === 'file',
  edgeFilter: (edge) => edge.type === 'imports' || edge.type === 'contains',
};

describe('KnowledgeGraphView', () => {
  it('renders edge-type filter controls with all 4 edge types', () => {
    render(
      <KnowledgeGraphView
        nodes={mockNodes}
        edges={mockEdges}
        perspective={mockPerspective}
        selectedNodeId={null}
        onNodeClick={vi.fn()}
      />,
    );

    // All 4 edge types should be visible as checkboxes
    expect(screen.getByText('contains')).toBeInTheDocument();
    expect(screen.getByText('imports')).toBeInTheDocument();
    expect(screen.getByText('calls')).toBeInTheDocument();
    expect(screen.getByText('tested_by')).toBeInTheDocument();
  });

  it('all edge type checkboxes are checked by default', () => {
    render(
      <KnowledgeGraphView
        nodes={mockNodes}
        edges={mockEdges}
        perspective={mockPerspective}
        selectedNodeId={null}
        onNodeClick={vi.fn()}
      />,
    );

    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(4);
    for (const cb of checkboxes) {
      expect(cb).toBeChecked();
    }
  });

  it('toggling an edge type checkbox changes its state', () => {
    render(
      <KnowledgeGraphView
        nodes={mockNodes}
        edges={mockEdges}
        perspective={mockPerspective}
        selectedNodeId={null}
        onNodeClick={vi.fn()}
      />,
    );

    const callsCheckbox = screen.getByLabelText('calls');
    expect(callsCheckbox).toBeChecked();

    fireEvent.click(callsCheckbox);
    expect(callsCheckbox).not.toBeChecked();

    // Re-enable
    fireEvent.click(callsCheckbox);
    expect(callsCheckbox).toBeChecked();
  });

  it('renders the graph description with node and edge counts', () => {
    render(
      <KnowledgeGraphView
        nodes={mockNodes}
        edges={mockEdges}
        perspective={mockPerspective}
        selectedNodeId={null}
        onNodeClick={vi.fn()}
      />,
    );

    // The sr-only description should mention node count
    const description = document.getElementById('graph-description');
    expect(description).toBeInTheDocument();
    expect(description?.textContent).toContain('3 nodes');
  });

  it('renders without crashing with empty graph', () => {
    render(
      <KnowledgeGraphView
        nodes={[]}
        edges={[]}
        perspective={mockPerspective}
        selectedNodeId={null}
        onNodeClick={vi.fn()}
      />,
    );

    // Edge type controls should still be present
    expect(screen.getByText('contains')).toBeInTheDocument();
  });
});
