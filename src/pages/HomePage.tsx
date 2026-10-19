import { Link } from 'react-router-dom';

export default function HomePage() {
  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Avalanche Insight Hub — Learning Site</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
        A public learning resource for understanding the Avalanche Insight Hub codebase
        and avalanche forecasting concepts.
      </p>

      <div
        style={{
          padding: '0.75rem 1rem',
          background: 'rgba(250, 204, 21, 0.1)',
          border: '1px solid var(--yellow)',
          borderRadius: '0.375rem',
          marginBottom: '1.5rem',
          fontSize: '0.85rem',
          color: 'var(--yellow)',
        }}
      >
        This is an educational resource, not an operational safety system.
        The map is currently unavailable (no approved static snapshot).
      </div>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>What This Site Contains</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.75rem' }}>
          <Link
            to="/graph"
            style={{
              display: 'block',
              padding: '1rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '0.5rem',
              textDecoration: 'none',
              color: 'var(--text)',
            }}
          >
            <h3 style={{ fontSize: '1rem', marginBottom: '0.25rem' }}>Code Knowledge Graph →</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Explore 4,926 nodes and 8,183 edges showing the structure of the codebase.
              Search, filter by perspective, view as table or graph.
            </p>
          </Link>
          <Link
            to="/map"
            style={{
              display: 'block',
              padding: '1rem',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: '0.5rem',
              textDecoration: 'none',
              color: 'var(--text)',
            }}
          >
            <h3 style={{ fontSize: '1rem', marginBottom: '0.25rem' }}>Avalanche Forecast Map →</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Currently unavailable — no approved static snapshot exists.
              See the map page for details on what is required.
            </p>
          </Link>
        </div>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>How to Use the Graph</h2>
        <ol style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>Open the <Link to="/graph" style={{ color: 'var(--accent)' }}>Knowledge Graph</Link> page</li>
          <li>Choose a <strong style={{ color: 'var(--text)' }}>perspective</strong> from the left panel (e.g., "Architecture", "ML Pipeline", "Security Gates")</li>
          <li>Use <strong style={{ color: 'var(--text)' }}>search</strong> to find specific nodes by name or path</li>
          <li>Filter by <strong style={{ color: 'var(--text)' }}>node type</strong> (file, function, class) or <strong style={{ color: 'var(--text)' }}>language</strong></li>
          <li>Click a node to see its details, connections, and explanation</li>
          <li>Switch to <strong style={{ color: 'var(--text)' }}>Table View</strong> for a sortable, paginated list</li>
        </ol>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>How to Read the Forecast Map</h2>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
          The map is currently unavailable because no approved, rights-cleared static
          forecast snapshot exists. When a snapshot is supplied, the map will show:
        </p>
        <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>Risk bands (color-coded by severity)</li>
          <li>Uncertainty bands</li>
          <li>Valid-from and valid-to times</li>
          <li>Source attribution and limitations</li>
        </ul>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
          <strong style={{ color: 'var(--text)' }}>Important:</strong> The map will never be a live
          operational forecast. It is for educational purposes only.
        </p>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Snapshot Date</h2>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          <strong style={{ color: 'var(--text)' }}>Graph analyzed:</strong> 2026-08-04<br />
          <strong style={{ color: 'var(--text)' }}>Source commit:</strong> <code style={{ fontFamily: 'monospace' }}>f582d1822b39</code><br />
          <strong style={{ color: 'var(--text)' }}>Export status:</strong> approved (clean scoped source snapshot)<br />
          <strong style={{ color: 'var(--text)' }}>Map status:</strong> blocked (no approved snapshot)
        </div>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Source and License</h2>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
          The knowledge graph is generated from the Avalanche Insight Hub codebase
          under the <strong style={{ color: 'var(--text)' }}>MIT License</strong>.
          See <Link to="/about" style={{ color: 'var(--accent)' }}>About</Link> for full
          attribution, limitations, and provenance.
        </p>
      </section>

      <section>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Public Limitations</h2>
        <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>Graph is a static snapshot — does not reflect current codebase state</li>
          <li>Map is unavailable — no approved static snapshot exists</li>
          <li>No live backend, no API calls, no AI endpoints</li>
          <li>No external map tiles, fonts, or CDN resources</li>
          <li>Not an operational safety decision system</li>
        </ul>
      </section>
    </div>
  );
}
