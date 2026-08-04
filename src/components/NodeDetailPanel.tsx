import { useState } from 'react';
import type { GraphNode, GraphEdge } from '../lib/graphLoader';
import { getIncomingEdges, getOutgoingEdges } from '../lib/graphLoader';
import type { GraphIndex } from '../lib/graphLoader';

interface Props {
  node: GraphNode;
  index: GraphIndex;
  explanation: string | null;
  onNodeClick: (nodeId: string) => void;
}

export default function NodeDetailPanel({ node, index, explanation, onNodeClick }: Props) {
  const [explanationMode, setExplanationMode] = useState<'beginner' | 'technical'>('beginner');
  const incoming = getIncomingEdges(index, node.id);
  const outgoing = getOutgoingEdges(index, node.id);

  const renderConnectedNodes = (edges: GraphEdge[], label: string, direction: 'source' | 'target') => {
    if (edges.length === 0) return null;
    const connectedIds = new Set(edges.map((e) => e[direction]));
    const connected = Array.from(connectedIds)
      .map((id) => index.nodeById.get(id))
      .filter(Boolean) as GraphNode[];
    if (connected.length === 0) return null;

    return (
      <div style={{ marginTop: '0.75rem' }}>
        <h4 style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
          {label} ({connected.length})
        </h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
          {connected.slice(0, 15).map((n) => (
            <button
              key={n.id}
              onClick={() => onNodeClick(n.id)}
              style={{
                padding: '0.15rem 0.4rem',
                fontSize: '0.75rem',
                border: '1px solid var(--border)',
                borderRadius: '0.2rem',
                background: 'var(--bg)',
                color: 'var(--text)',
                cursor: 'pointer',
              }}
            >
              {n.name}
            </button>
          ))}
          {connected.length > 15 && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', padding: '0.15rem' }}>
              +{connected.length - 15} more
            </span>
          )}
        </div>
      </div>
    );
  };

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '0.5rem',
        padding: '1rem',
        overflowY: 'auto',
        maxHeight: '100%',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span
          style={{
            padding: '0.15rem 0.4rem',
            fontSize: '0.7rem',
            borderRadius: '0.2rem',
            background: node.type === 'file' ? 'var(--blue)' : node.type === 'function' ? 'var(--green)' : 'var(--purple)',
            color: 'var(--bg)',
            fontWeight: 600,
            textTransform: 'uppercase',
          }}
        >
          {node.type}
        </span>
        <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>{node.name}</h2>
      </div>

      {node.relativePath && (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
          {node.relativePath}
        </div>
      )}

      {node.language && (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
          Language: {node.language}
        </div>
      )}

      {node.lineCount != null && node.lineCount > 0 && (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
          Lines: {node.lineCount}
        </div>
      )}

      {node.tags && node.tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginBottom: '0.5rem' }}>
          {node.tags.map((tag) => (
            <span
              key={tag}
              style={{
                padding: '0.1rem 0.3rem',
                fontSize: '0.7rem',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: '0.2rem',
                color: 'var(--text-muted)',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {node.lineCount != null && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <strong>Lines:</strong> {node.lineCount}
        </div>
      )}

      {node.sourceHash && (
        <div style={{ marginTop: '0.25rem', fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace', wordBreak: 'break-all' }}>
          <strong>Source hash:</strong> {node.sourceHash.slice(0, 16)}…
        </div>
      )}

      {explanation && (
        <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'var(--bg)', borderRadius: '0.375rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h4 style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Explanation
            </h4>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              <button
                onClick={() => setExplanationMode('beginner')}
                style={{
                  padding: '0.1rem 0.4rem',
                  fontSize: '0.7rem',
                  border: '1px solid var(--border)',
                  borderRadius: '0.2rem',
                  background: explanationMode === 'beginner' ? 'var(--accent)' : 'transparent',
                  color: explanationMode === 'beginner' ? 'var(--bg)' : 'var(--text)',
                  cursor: 'pointer',
                }}
              >
                Beginner
              </button>
              <button
                onClick={() => setExplanationMode('technical')}
                style={{
                  padding: '0.1rem 0.4rem',
                  fontSize: '0.7rem',
                  border: '1px solid var(--border)',
                  borderRadius: '0.2rem',
                  background: explanationMode === 'technical' ? 'var(--accent)' : 'transparent',
                  color: explanationMode === 'technical' ? 'var(--bg)' : 'var(--text)',
                  cursor: 'pointer',
                }}
              >
                Technical
              </button>
            </div>
          </div>
          {explanationMode === 'beginner' ? (
            <p style={{ fontSize: '0.85rem', lineHeight: 1.5 }}>{explanation}</p>
          ) : (
            <div style={{ fontSize: '0.8rem', lineHeight: 1.5 }}>
              {explanation.split(/\[(STRUCTURAL FACT|DERIVED|INTERPRETATION|UNKNOWN)\]/).filter(Boolean).map((part, i) => {
                if (part === 'STRUCTURAL FACT' || part === 'DERIVED' || part === 'INTERPRETATION' || part === 'UNKNOWN') {
                  const colors: Record<string, string> = {
                    'STRUCTURAL FACT': 'var(--green)',
                    'DERIVED': 'var(--blue)',
                    'INTERPRETATION': 'var(--yellow)',
                    'UNKNOWN': 'var(--text-muted)',
                  };
                  return (
                    <span key={i} style={{ color: colors[part], fontWeight: 600, fontSize: '0.7rem', marginRight: '0.25rem' }}>
                      {part}
                    </span>
                  );
                }
                return <span key={i}>{part}</span>;
              })}
            </div>
          )}
          <div style={{ marginTop: '0.5rem', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            <span style={{ color: 'var(--green)' }}>■</span> Structural fact
            <span style={{ marginLeft: '0.5rem', color: 'var(--blue)' }}>■</span> Derived
            <span style={{ marginLeft: '0.5rem', color: 'var(--yellow)' }}>■</span> Interpretation
            <span style={{ marginLeft: '0.5rem', color: 'var(--text-muted)' }}>■</span> Unknown
          </div>
        </div>
      )}

      {renderConnectedNodes(outgoing, 'Calls / Contains', 'target')}
      {renderConnectedNodes(incoming, 'Called by / Contained by', 'source')}
    </div>
  );
}
