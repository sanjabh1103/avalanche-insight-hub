import { useState, useMemo } from 'react';
import type { GraphNode } from '../lib/graphLoader';

interface Props {
  nodes: GraphNode[];
  onNodeClick: (nodeId: string) => void;
}

const PAGE_SIZE = 50;

type SortKey = 'name' | 'type' | 'language' | 'relativePath';

export default function TableView({ nodes, onNodeClick }: Props) {
  const [page, setPage] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortAsc, setSortAsc] = useState(true);

  const sorted = useMemo(() => {
    const arr = [...nodes];
    arr.sort((a, b) => {
      const av = (a[sortKey] ?? '').toString().toLowerCase();
      const bv = (b[sortKey] ?? '').toString().toLowerCase();
      return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    return arr;
  }, [nodes, sortKey, sortAsc]);

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageNodes = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const sortArrow = (key: SortKey) => (sortKey === key ? (sortAsc ? ' ↑' : ' ↓') : '');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ overflow: 'auto', flex: 1 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 1 }}>
            <tr>
              <th onClick={() => handleSort('name')} style={{ padding: '0.5rem', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                Name{sortArrow('name')}
              </th>
              <th onClick={() => handleSort('type')} style={{ padding: '0.5rem', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                Type{sortArrow('type')}
              </th>
              <th onClick={() => handleSort('language')} style={{ padding: '0.5rem', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                Language{sortArrow('language')}
              </th>
              <th onClick={() => handleSort('relativePath')} style={{ padding: '0.5rem', cursor: 'pointer', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                File Path{sortArrow('relativePath')}
              </th>
            </tr>
          </thead>
          <tbody>
            {pageNodes.map((node) => (
              <tr
                key={node.id}
                onClick={() => onNodeClick(node.id)}
                style={{ cursor: 'pointer', borderBottom: '1px solid var(--border)' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = '')}
              >
                <td style={{ padding: '0.4rem 0.5rem' }}>{node.name}</td>
                <td style={{ padding: '0.4rem 0.5rem' }}>
                  <span style={{
                    padding: '0.1rem 0.3rem',
                    fontSize: '0.7rem',
                    borderRadius: '0.2rem',
                    background: node.type === 'file' ? 'var(--blue)' : node.type === 'function' ? 'var(--green)' : 'var(--purple)',
                    color: 'var(--bg)',
                  }}>
                    {node.type}
                  </span>
                </td>
                <td style={{ padding: '0.4rem 0.5rem', color: 'var(--text-muted)' }}>{node.language ?? '—'}</td>
                <td style={{ padding: '0.4rem 0.5rem', color: 'var(--text-muted)', fontSize: '0.8rem' }}>{node.relativePath ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem', borderTop: '1px solid var(--border)' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {sorted.length} nodes — page {page + 1} of {totalPages}
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            style={{
              padding: '0.25rem 0.75rem',
              border: '1px solid var(--border)',
              borderRadius: '0.25rem',
              background: 'var(--bg-card)',
              color: page === 0 ? 'var(--text-muted)' : 'var(--text)',
              cursor: page === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            Prev
          </button>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            style={{
              padding: '0.25rem 0.75rem',
              border: '1px solid var(--border)',
              borderRadius: '0.25rem',
              background: 'var(--bg-card)',
              color: page >= totalPages - 1 ? 'var(--text-muted)' : 'var(--text)',
              cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer',
            }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
