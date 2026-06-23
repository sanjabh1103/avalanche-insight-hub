import { useState, useEffect } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Mountain, Menu, X, FlaskConical, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ThemeToggle from '@/components/ThemeToggle';
import { cn } from '@/lib/utils';

const NAV_LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/explore', label: 'Explore' },
  { to: '/methods', label: 'Methods' },
  { to: '/data', label: 'Data', disabled: true, tooltip: 'Coming soon' },
];

export default function AppNavbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <header
      className={cn(
        'sticky top-0 z-50 w-full transition-all duration-300',
        scrolled
          ? 'glass-panel border-b border-border/60 shadow-lg shadow-black/10'
          : 'border-b border-border/30 bg-background/80 backdrop-blur-md',
      )}
    >
      <nav className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link to="/" className="flex shrink-0 items-center gap-2.5" aria-label="Avalanche Insight Hub home">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/20 shadow-[0_0_20px_hsl(156_74%_45%_/_0.15)]">
            <Mountain className="h-4.5 w-4.5 text-emerald-400" />
          </div>
          <div className="hidden sm:block">
            <span className="text-sm font-semibold tracking-tight text-foreground">Avalanche Insight Hub</span>
            <span className="ml-2 text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">v1.0</span>
          </div>
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map((link) =>
            link.disabled ? (
              <span
                key={link.to}
                title={link.tooltip}
                className="px-3 py-2 text-sm font-medium text-muted-foreground/40 cursor-not-allowed select-none rounded-lg"
              >
                {link.label}
              </span>
            ) : (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  cn(
                    'relative px-3 py-2 text-sm font-medium transition-colors rounded-lg',
                    isActive
                      ? 'text-emerald-400'
                      : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {link.label}
                    {isActive && (
                      <span className="absolute bottom-0 left-1/2 h-0.5 w-6 -translate-x-1/2 rounded-full bg-emerald-400" />
                    )}
                  </>
                )}
              </NavLink>
            ),
          )}
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <div className="hidden sm:block">
            <ThemeToggle />
          </div>

          {/* Auth-aware links */}
          <div className="hidden lg:flex items-center gap-1">
            <NavLink
              to="/scientist"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                  isActive
                    ? 'text-emerald-400 bg-emerald-500/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
                )
              }
            >
              <FlaskConical className="h-4 w-4" />
              Scientist
            </NavLink>
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                  isActive
                    ? 'text-emerald-400 bg-emerald-500/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
                )
              }
            >
              <Settings2 className="h-4 w-4" />
              Admin
            </NavLink>
          </div>

          {/* Mobile hamburger */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden h-10 w-10 rounded-xl"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>
      </nav>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-border/40 bg-card/95 backdrop-blur-xl">
          <div className="flex flex-col gap-1 px-4 py-4">
            {NAV_LINKS.map((link) =>
              link.disabled ? (
                <span
                  key={link.to}
                  className="px-3 py-2.5 text-sm font-medium text-muted-foreground/40 cursor-not-allowed rounded-lg"
                >
                  {link.label} <span className="text-[10px]">({link.tooltip})</span>
                </span>
              ) : (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end}
                  className={({ isActive }) =>
                    cn(
                      'px-3 py-2.5 text-sm font-medium rounded-lg transition-colors',
                      isActive
                        ? 'text-emerald-400 bg-emerald-500/10'
                        : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
                    )
                  }
                >
                  {link.label}
                </NavLink>
              ),
            )}
            <div className="my-2 h-px bg-border/40" />
            <NavLink
              to="/scientist"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors',
                  isActive
                    ? 'text-emerald-400 bg-emerald-500/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
                )
              }
            >
              <FlaskConical className="h-4 w-4" />
              Scientist
            </NavLink>
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors',
                  isActive
                    ? 'text-emerald-400 bg-emerald-500/10'
                    : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
                )
              }
            >
              <Settings2 className="h-4 w-4" />
              Admin
            </NavLink>
            <div className="mt-2 flex items-center justify-between">
              <ThemeToggle />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
