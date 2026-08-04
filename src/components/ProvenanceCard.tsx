import type { GraphManifest } from '../lib/graphLoader';

interface Props {
  manifest: GraphManifest | null;
}

export default function ProvenanceCard({ manifest }: Props) {
  if (!manifest) return null;

  const shortCommit = manifest.sourceCommit?.slice(0, 12) ?? 'unknown';
  const statusColor = manifest.exportStatus === 'approved' ? 'var(--green)' : 'var(--yellow)';

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '0.5rem',
        padding: '0.75rem',
        fontSize: '0.8rem',
      }}
    >
      <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Provenance
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '0.25rem 0.75rem' }}>
        <span style={{ color: 'var(--text-muted)' }}>Status:</span>
        <span style={{ color: statusColor, fontWeight: 600 }}>{manifest.exportStatus}</span>
        <span style={{ color: 'var(--text-muted)' }}>Nodes:</span>
        <span>{manifest.nodeCount.toLocaleString()}</span>
        <span style={{ color: 'var(--text-muted)' }}>Edges:</span>
        <span>{manifest.edgeCount.toLocaleString()}</span>
        <span style={{ color: 'var(--text-muted)' }}>Commit:</span>
        <span style={{ fontFamily: 'monospace' }}>{shortCommit}</span>
        <span style={{ color: 'var(--text-muted)' }}>Analyzed:</span>
        <span>{manifest.analyzedAt?.slice(0, 10) ?? 'unknown'}</span>
        <span style={{ color: 'var(--text-muted)' }}>Content hash:</span>
        <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>
          {manifest.contentHash?.slice(0, 16)}...
        </span>
        <span style={{ color: 'var(--text-muted)' }}>License:</span>
        <span>{manifest.license}</span>
        {manifest.worktreeDirty != null && (
          <>
            <span style={{ color: 'var(--text-muted)' }}>Worktree dirty:</span>
            <span style={{ color: manifest.worktreeDirty ? 'var(--yellow)' : 'var(--green)' }}>
              {manifest.worktreeDirty ? 'Yes' : 'No'}
            </span>
          </>
        )}
      </div>
      <div
        style={{
          marginTop: '0.5rem',
          padding: '0.5rem',
          background: 'var(--bg)',
          borderRadius: '0.25rem',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          border: '1px solid var(--border)',
        }}
      >
        {manifest.disclaimer}
      </div>
    </div>
  );
}
