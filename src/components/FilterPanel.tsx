import type { PerspectiveId } from '../lib/perspectives';
import { perspectives } from '../lib/perspectives';

interface Props {
  activePerspective: PerspectiveId;
  onPerspectiveChange: (id: PerspectiveId) => void;
  nodeTypeFilter: Set<string>;
  onNodeTypeChange: (types: Set<string>) => void;
  languageFilter: string | null;
  onLanguageChange: (lang: string | null) => void;
  availableLanguages: string[];
  edgeTypeFilter: Set<string>;
  onEdgeTypeChange: (types: Set<string>) => void;
  availableEdgeTypes: string[];
}

const NODE_TYPES = ['file', 'function', 'class'];

export default function FilterPanel({
  activePerspective,
  onPerspectiveChange,
  nodeTypeFilter,
  onNodeTypeChange,
  languageFilter,
  onLanguageChange,
  availableLanguages,
  edgeTypeFilter,
  onEdgeTypeChange,
  availableEdgeTypes,
}: Props) {
  const toggleType = (type: string) => {
    const next = new Set(nodeTypeFilter);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    if (next.size === 0) next.add(type); // Keep at least one
    onNodeTypeChange(next);
  };

  const toggleEdgeType = (type: string) => {
    const next = new Set(edgeTypeFilter);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    onEdgeTypeChange(next);
  };

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '0.5rem',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
      }}
    >
      <div>
        <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Perspective
        </h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
          {perspectives.map((p) => (
            <button
              key={p.id}
              onClick={() => onPerspectiveChange(p.id)}
              title={p.description}
              style={{
                padding: '0.25rem 0.5rem',
                fontSize: '0.8rem',
                border: '1px solid var(--border)',
                borderRadius: '0.25rem',
                background: activePerspective === p.id ? 'var(--accent)' : 'transparent',
                color: activePerspective === p.id ? 'var(--bg)' : 'var(--text)',
                cursor: 'pointer',
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Node Type
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {NODE_TYPES.map((type) => (
            <label key={type} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.85rem' }}>
              <input
                type="checkbox"
                checked={nodeTypeFilter.has(type)}
                onChange={() => toggleType(type)}
              />
              {type}
            </label>
          ))}
        </div>
      </div>

      <div>
        <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Language
        </h3>
        <select
          value={languageFilter ?? ''}
          onChange={(e) => onLanguageChange(e.target.value || null)}
          style={{
            width: '100%',
            padding: '0.25rem 0.5rem',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: '0.25rem',
            color: 'var(--text)',
            fontSize: '0.85rem',
          }}
        >
          <option value="">All languages</option>
          {availableLanguages.map((lang) => (
            <option key={lang} value={lang}>{lang}</option>
          ))}
        </select>
      </div>

      {availableEdgeTypes.length > 0 && (
        <div>
          <h3 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Edge Type
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
            {availableEdgeTypes.map((type) => (
              <label key={type} style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.8rem' }}>
                <input
                  type="checkbox"
                  checked={edgeTypeFilter.has(type)}
                  onChange={() => toggleEdgeType(type)}
                />
                {type}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
