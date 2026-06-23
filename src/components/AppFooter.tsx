import { Link } from 'react-router-dom';
import { Mountain, AlertTriangle, Github, Mail, ExternalLink } from 'lucide-react';

const DATA_SOURCES = [
  { name: 'Open-Meteo', url: 'https://open-meteo.com/' },
  { name: 'Copernicus Sentinel-1', url: 'https://dataspace.copernicus.eu/' },
  { name: 'OpenStreetMap', url: 'https://www.openstreetmap.org/' },
  { name: 'NASA GIBS', url: 'https://earthdata.nasa.gov/gibs' },
  { name: 'EnviDat (WSL)', url: 'https://www.envidat.ch/' },
];

const PLATFORM_LINKS = [
  { label: 'Methods & Validation', to: '/methods' },
  { label: 'Explore Map', to: '/explore' },
  { label: 'Model Card (RF4)', to: '/methods' },
  { label: 'Reproducibility', to: '/methods' },
];

export default function AppFooter() {
  return (
    <footer className="mt-auto border-t border-border/40 bg-card/50 backdrop-blur-sm">
      <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {/* Data Sources */}
          <div>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Data Sources
            </h3>
            <ul className="space-y-2">
              {DATA_SOURCES.map((source) => (
                <li key={source.name}>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <ExternalLink className="h-3 w-3 shrink-0" />
                    {source.name}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* Platform */}
          <div>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Platform
            </h3>
            <ul className="space-y-2">
              {PLATFORM_LINKS.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.to}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Disclaimer & Contact */}
          <div>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              About & Contact
            </h3>
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/15 bg-amber-500/5 px-3 py-2.5">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
              <p className="text-xs leading-relaxed text-muted-foreground">
                <strong className="text-amber-400">Experimental AI system</strong> — Not for life-critical decisions.
                Use official avalanche centers where available.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <a
                href="https://github.com/sanjabh1103/avalanche-insight-hub"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                <Github className="h-4 w-4" />
                GitHub
              </a>
              <a
                href="mailto:contact@avalanche-insight-hub.app"
                className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                <Mail className="h-4 w-4" />
                Contact
              </a>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-8 flex flex-col items-center justify-between gap-2 border-t border-border/30 pt-4 sm:flex-row">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Mountain className="h-3 w-3 text-emerald-400/60" />
            <span>Avalanche Insight Hub — Decision-support prototype rendering published Colorado technical artifacts.</span>
          </div>
          <div className="text-[11px] font-mono text-muted-foreground/70">
            v1.0.0 — {new Date().getFullYear()}
          </div>
        </div>

        {/* Citation guidance */}
        <div className="mt-3 rounded-lg bg-secondary/20 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground/80">
          <strong className="text-muted-foreground">Citation:</strong> If using this platform in research, cite as:
          "Avalanche Insight Hub (2026). AI-assisted avalanche forecasting decision-support prototype."
          See <Link to="/methods" className="text-emerald-400/80 hover:text-emerald-400">Methods</Link> for full references.
        </div>
      </div>
    </footer>
  );
}
