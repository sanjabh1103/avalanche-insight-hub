import { Link } from 'react-router-dom';
import { Mountain, Map, FlaskConical, Home } from 'lucide-react';

const SUGGESTIONS = [
  { to: '/', label: 'Dashboard', icon: Home, description: 'Overview of regions, model status, and recent activity' },
  { to: '/explore', label: 'Explore Map', icon: Map, description: 'Interactive hazard map with forecast grid' },
  { to: '/methods', label: 'Methods & Validation', icon: FlaskConical, description: 'Model architecture, calibration, and limitations' },
];

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 py-16">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 border border-emerald-500/20">
        <Mountain className="h-8 w-8 text-emerald-400" />
      </div>
      <h1 className="mb-2 text-5xl font-bold tracking-tight text-foreground">404</h1>
      <p className="mb-1 text-lg text-foreground">This page doesn't exist or has moved.</p>
      <p className="mb-8 text-sm text-muted-foreground">
        Try one of these sections instead:
      </p>
      <div className="grid w-full max-w-2xl gap-3 sm:grid-cols-3">
        {SUGGESTIONS.map((s) => (
          <Link
            key={s.to}
            to={s.to}
            className="glass-panel-hover rounded-2xl border border-border/60 bg-card/40 p-4 text-center transition-all"
          >
            <s.icon className="mx-auto mb-2 h-6 w-6 text-emerald-400" />
            <div className="text-sm font-semibold text-foreground">{s.label}</div>
            <div className="mt-1 text-xs text-muted-foreground">{s.description}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
