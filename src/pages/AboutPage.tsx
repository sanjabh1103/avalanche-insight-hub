export default function AboutPage() {
  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>About This Site</h1>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>What This Is</h2>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
          This is a public learning resource for understanding the Avalanche Insight Hub codebase
          and avalanche forecasting concepts. It contains:
        </p>
        <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>
            <strong style={{ color: 'var(--text)' }}>Knowledge Graph</strong> — An interactive
            visualization of the codebase structure, showing files, functions, and classes and how
            they connect. Explore by perspective, search, or table view.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>Avalanche Forecast Map</strong> — Currently
            <strong style={{ color: 'var(--yellow)' }}> unavailable</strong>. No approved,
            rights-cleared static map snapshot exists. The map page shows an explicit blocked state.
          </li>
        </ul>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>What the Knowledge Graph Represents</h2>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
          The knowledge graph is a structural snapshot of the Avalanche Insight Hub codebase,
          containing {`4,926`} nodes (files, functions, and classes) and {`8,183`} edges showing
          relationships between them. It was generated from a specific commit of the codebase and
          does not change in real time.
        </p>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
          Each node includes metadata such as relative path, language, tags, line count, and
          source hash (for file nodes). Deterministic explanations are generated from this metadata — no
          AI is used.
        </p>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
          <strong style={{ color: 'var(--text)' }}>Source hashes:</strong> 907 file nodes include a
          non-null <code style={{ fontSize: '0.85rem' }}>sourceHash</code> (SHA-256 of the file content).
          4,019 function and class nodes have <code style={{ fontSize: '0.85rem' }}>sourceHash: null</code>
          because the source analysis only computed content hashes at the file level, not per-function
          or per-class.
        </p>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Map Status: Unavailable</h2>
        <div
          style={{
            padding: '1rem',
            background: 'rgba(250, 204, 21, 0.1)',
            border: '1px solid var(--yellow)',
            borderRadius: '0.375rem',
            marginBottom: '0.75rem',
          }}
        >
          <p style={{ color: 'var(--yellow)', fontSize: '0.9rem', fontWeight: 600 }}>
            MAP_SNAPSHOT_NOT_AVAILABLE
          </p>
          <p style={{ color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
            No approved, rights-cleared static forecast snapshot exists in the source repository.
            The source contains a Swiss research dataset (Envidat) with private station identifiers
            that is not cleared for public redistribution.
          </p>
        </div>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
          To display the map, an approved static forecast snapshot must be supplied with:
        </p>
        <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>Source name and license</li>
          <li>Attribution text</li>
          <li>Valid-from and valid-to times</li>
          <li>Uncertainty statement</li>
          <li>Public-use approval confirmation</li>
        </ul>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
          See <code style={{ fontSize: '0.85rem' }}>handoff/MAP_INPUT_REQUEST.md</code> for full requirements.
          No fabricated or synthetic map data is used.
        </p>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: 'var(--yellow)' }}>
          Limitations
        </h2>
        <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>
            <strong style={{ color: 'var(--text)' }}>Graph is a static snapshot</strong> — taken on
            2026-08-04 from commit <code style={{ fontSize: '0.85rem' }}>f582d1822b39</code>. It does not
            reflect the current state of the codebase.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>Graph export is an approved static snapshot</strong> —
            it is pinned to a clean scoped source commit and does not auto-update.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>Map is unavailable</strong> — no approved static
            snapshot exists. No fabricated or synthetic data is displayed.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>No live backend</strong> — this is a static
            site with no server-side code, no API calls, and no real-time data.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>No external resources</strong> — no external
            map tiles, fonts, scripts, or CDN resources. All assets are same-origin.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>No AI</strong> — all explanations are
            deterministic, generated from templates. No Gemini, OpenAI, or other AI APIs are called.
          </li>
        </ul>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Attribution</h2>
        <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem' }}>
          <li>
            <strong style={{ color: 'var(--text)' }}>Knowledge graph</strong> — Generated from the
            Avalanche Insight Hub codebase structural analysis. MIT License.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>Map data</strong> — Not available. No
            third-party data is used.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>Explanations</strong> — Deterministic,
            template-generated from node metadata. No AI-generated content.
          </li>
          <li>
            <strong style={{ color: 'var(--text)' }}>Dependencies</strong> — React, Vite,
            TypeScript, Vitest. All MIT or Apache-2.0 licensed.
          </li>
        </ul>
      </section>

      <section style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>License</h2>
        <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
          This project is licensed under the MIT License.
        </p>
        <pre
          style={{
            marginTop: '0.5rem',
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '0.375rem',
            fontSize: '0.8rem',
            overflow: 'auto',
            lineHeight: 1.5,
          }}
        >
{`MIT License

Copyright (c) 2026 Avalanche Insight Hub

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`}
        </pre>
      </section>

      <section>
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.5rem' }}>Provenance</h2>
        <div
          style={{
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '0.375rem',
            fontSize: '0.85rem',
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '0.5rem 1rem' }}>
            <span style={{ color: 'var(--text-muted)' }}>Graph content hash:</span>
            <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>
              cc26ff2f74f49fc3632cb2ba1b8504bde2e18d430e8f07348db8c018b9c3a040
            </span>
            <span style={{ color: 'var(--text-muted)' }}>Graph file SHA-256:</span>
            <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>
              df77d44e305e0877c4024e343b93da2c29ac7bf2dea9402e3ae1d0588caf3224
            </span>
            <span style={{ color: 'var(--text-muted)' }}>Graph nodes:</span>
            <span>4,926</span>
            <span style={{ color: 'var(--text-muted)' }}>Graph edges:</span>
            <span>8,183</span>
            <span style={{ color: 'var(--text-muted)' }}>Analyzed commit:</span>
            <span style={{ fontFamily: 'monospace' }}>f582d1822b39</span>
            <span style={{ color: 'var(--text-muted)' }}>Analyzed at:</span>
            <span>2026-08-04</span>
            <span style={{ color: 'var(--text-muted)' }}>Export status:</span>
            <span style={{ color: 'var(--green)' }}>approved (clean scoped source snapshot)</span>
            <span style={{ color: 'var(--text-muted)' }}>Map status:</span>
            <span style={{ color: 'var(--yellow)' }}>blocked (no approved snapshot)</span>
            <span style={{ color: 'var(--text-muted)' }}>License:</span>
            <span>MIT</span>
          </div>
        </div>
      </section>
    </div>
  );
}
