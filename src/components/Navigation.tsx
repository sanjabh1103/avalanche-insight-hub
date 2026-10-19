import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Home' },
  { to: '/graph', label: 'Graph' },
  { to: '/map', label: 'Map' },
  { to: '/about', label: 'About' },
];

export default function Navigation() {
  return (
    <nav
      style={{
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border)',
        padding: '0.75rem 1.5rem',
        display: 'flex',
        alignItems: 'center',
        gap: '1.5rem',
      }}
    >
      <span style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--accent)' }}>
        Avalanche Insight Hub
      </span>
      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
        Knowledge Graph & Map Learning
      </span>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: '1rem' }}>
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            style={({ isActive }) => ({
              color: isActive ? 'var(--accent)' : 'var(--text-muted)',
              fontWeight: isActive ? 600 : 400,
              padding: '0.25rem 0.5rem',
              borderRadius: '0.25rem',
            })}
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
