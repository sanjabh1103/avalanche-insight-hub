import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>Page not found</h1>
      <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
        This address is not part of the learning site. Return to the start page or open the graph.
      </p>
      <p style={{ marginTop: '1rem' }}>
        <Link to="/" style={{ color: 'var(--accent)', marginRight: '1rem' }}>Start here</Link>
        <Link to="/graph" style={{ color: 'var(--accent)' }}>Open the knowledge graph</Link>
      </p>
    </div>
  );
}
