import { Suspense, lazy } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader2, Mountain, Settings2 } from 'lucide-react';

import AdminAccessGate from '@/components/AdminAccessGate';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

const LazyAdminDashboard = lazy(() => import('@/components/AdminDashboard'));

function AdminDashboardFallback() {
  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-border/70 bg-card/60 p-4 backdrop-blur-xl">
        <div className="flex items-center gap-3 text-sm uppercase tracking-[0.2em] text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
          <span>Loading admin dashboard</span>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="space-y-4">
          <Skeleton className="h-56 rounded-3xl bg-white/5" />
          <Skeleton className="h-80 rounded-3xl bg-white/5" />
        </div>
        <div className="space-y-4">
          <Skeleton className="h-44 rounded-3xl bg-white/5" />
          <Skeleton className="h-44 rounded-3xl bg-white/5" />
          <Skeleton className="h-44 rounded-3xl bg-white/5" />
        </div>
      </div>
    </div>
  );
}

export default function AdminPage() {
  return (
    <div className="min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_30%),radial-gradient(circle_at_80%_0%,_hsl(199_90%_60%_/_0.09),_transparent_24%)]" />

      <div className="relative mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="rounded-[1.75rem] border border-border/70 bg-card/70 px-4 py-4 shadow-2xl shadow-black/20 backdrop-blur-2xl">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/10 shadow-[0_0_24px_hsl(156_74%_45%_/_0.18)]">
                <Mountain className="h-5 w-5 text-emerald-400" />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-semibold uppercase tracking-[0.18em] text-foreground">Avalanche Hub</div>
                <div className="text-[10px] uppercase tracking-[0.28em] text-muted-foreground">Admin control lane</div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Button asChild variant="outline" className="h-11 justify-center gap-2 rounded-2xl border-border/70 bg-black/10 text-[11px] font-semibold uppercase tracking-[0.18em]">
                <Link to="/">
                  <ArrowLeft className="h-4 w-4" />
                  Dashboard
                </Link>
              </Button>
              <Button type="button" disabled className="h-11 justify-center gap-2 rounded-2xl bg-emerald-500 text-[11px] font-semibold uppercase tracking-[0.18em] text-black opacity-100 disabled:pointer-events-none disabled:opacity-100">
                <Settings2 className="h-4 w-4" />
                Admin
              </Button>
            </div>
          </div>
        </header>

        <main className="relative flex-1 overflow-y-auto py-4">
          <div className="rounded-[1.75rem] border border-border/70 bg-card/50 p-4 shadow-2xl shadow-black/20 backdrop-blur-2xl sm:p-5 lg:p-6">
            <AdminAccessGate>
              <Suspense fallback={<AdminDashboardFallback />}>
                <LazyAdminDashboard />
              </Suspense>
            </AdminAccessGate>
          </div>
        </main>
      </div>
    </div>
  );
}
