import { useState, useEffect } from 'react';
import {
  loadForecastMap,
  loadForecastMapManifest,
  type ForecastMap,
  type ForecastMapManifest,
} from '../lib/mapLoader';

export default function MapPage() {
  const [mapData, setMapData] = useState<ForecastMap | null>(null);
  const [manifest, setManifest] = useState<ForecastMapManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [map, man] = await Promise.all([
          loadForecastMap(),
          loadForecastMapManifest(),
        ]);
        if (!active) return;
        setMapData(map);
        setManifest(man);
        setLoading(false);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load map data');
        setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  if (loading) {
    return <div className="loading">Loading map data…</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  if (!mapData) {
    return <div className="error">Map data not available</div>;
  }

  // Blocked state — no fabricated data
  if (mapData.status === 'blocked') {
    return (
      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        <h1 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Avalanche Forecast Map</h1>

        <div
          style={{
            padding: '1.5rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--orange)',
            borderRadius: '0.5rem',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>MAP_SNAPSHOT_NOT_AVAILABLE</div>
          <p style={{ color: 'var(--text-muted)', marginTop: '0.5rem', lineHeight: 1.6 }}>
            {mapData.disclaimer}
          </p>
          {mapData.blockedReason && (
            <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem', fontSize: '0.85rem' }}>
              <strong>Reason:</strong> {mapData.blockedReason}
            </p>
          )}
        </div>

        <div
          style={{
            marginTop: '1.5rem',
            padding: '1rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '0.5rem',
            fontSize: '0.85rem',
          }}
        >
          <h2 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>What Is Required</h2>
          <p style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
            To display the map, an approved, rights-cleared static forecast snapshot must be supplied with:
          </p>
          <ul style={{ color: 'var(--text-muted)', lineHeight: 1.8, marginLeft: '1.5rem', marginTop: '0.5rem' }}>
            <li>Source name and license</li>
            <li>Attribution text</li>
            <li>Valid-from and valid-to times</li>
            <li>Uncertainty statement</li>
            <li>Public-use approval confirmation</li>
          </ul>
          <p style={{ color: 'var(--text-muted)', marginTop: '0.5rem' }}>
            See <code style={{ fontSize: '0.85rem' }}>handoff/MAP_INPUT_REQUEST.md</code> for full requirements.
          </p>
        </div>

        <div
          style={{
            marginTop: '1rem',
            padding: '0.75rem',
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '0.5rem',
            fontSize: '0.8rem',
            color: 'var(--text-muted)',
          }}
        >
          <strong>Manifest status:</strong> {manifest?.status ?? 'unknown'}
          {manifest?.blockedReason && (
            <div style={{ marginTop: '0.25rem' }}>{manifest.blockedReason}</div>
          )}
        </div>
      </div>
    );
  }

  // Approved state — render map (future implementation)
  return (
    <div>
      <h1 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Avalanche Forecast Map</h1>
      <p style={{ color: 'var(--text-muted)' }}>
        Map rendering for approved snapshots will be implemented when an approved snapshot is supplied.
      </p>
    </div>
  );
}
