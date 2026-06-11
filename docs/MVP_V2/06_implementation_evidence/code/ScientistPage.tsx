import { Link } from 'react-router-dom';
import { ArrowLeft, ClipboardCheck, FileCheck2, Mountain, ShieldCheck } from 'lucide-react';

import RoleAccessGate from '@/components/RoleAccessGate';
import ScientistValidationWorkbench from '@/components/ScientistValidationWorkbench';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const scientistGateStatuses = [
  {
    key: 'public_scoring_boundary',
    label: 'Public scorer boundary',
    status: 'current' as const,
    detail: 'Scientist reviews are evidence inputs only; they do not change production scoring automatically.',
  },
  {
    key: 'sar_candidate',
    label: 'SAR candidate',
    status: 'gated' as const,
    detail: 'SAR remains blocked until SnowSlide research-grade and fresh final holdout gates pass.',
  },
  {
    key: 'himalayan_validation',
    label: 'Himalayan validation',
    status: 'candidate' as const,
    detail: 'Use grounded cases from forecast artifacts, outcomes, and field reports only.',
  },
];

export default function ScientistPage() {
  return (
    <div className="min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_30%),radial-gradient(circle_at_80%_0%,_hsl(199_90%_60%_/_0.09),_transparent_24%)]" />

      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="rounded-[1.75rem] border border-border/70 bg-card/70 px-4 py-4 shadow-2xl shadow-black/20 backdrop-blur-2xl">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/10 shadow-[0_0_24px_hsl(156_74%_45%_/_0.18)]">
                <Mountain className="h-5 w-5 text-emerald-400" />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-semibold uppercase tracking-[0.18em] text-foreground">Scientist Workspace</div>
                <div className="text-[10px] uppercase tracking-[0.28em] text-muted-foreground">Validation and sign-off lane</div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <Button asChild variant="outline" className="h-11 justify-center gap-2 rounded-2xl border-border/70 bg-black/10 text-[11px] font-semibold uppercase tracking-[0.18em]">
                <Link to="/">
                  <ArrowLeft className="h-4 w-4" />
                  Forecast
                </Link>
              </Button>
              <Button type="button" disabled className="h-11 justify-center gap-2 rounded-2xl bg-emerald-500 text-[11px] font-semibold uppercase tracking-[0.18em] text-black opacity-100 disabled:pointer-events-none disabled:opacity-100">
                <FileCheck2 className="h-4 w-4" />
                Scientist
              </Button>
              <Button asChild variant="outline" className="h-11 justify-center gap-2 rounded-2xl border-border/70 bg-black/10 text-[11px] font-semibold uppercase tracking-[0.18em]">
                <Link to="/scientist/daily-verification">
                  <ClipboardCheck className="h-4 w-4" />
                  Daily
                </Link>
              </Button>
            </div>
          </div>
        </header>

        <main className="relative flex-1 overflow-y-auto py-4">
          <div className="rounded-[1.75rem] border border-border/70 bg-card/50 p-4 shadow-2xl shadow-black/20 backdrop-blur-2xl sm:p-5 lg:p-6">
            <RoleAccessGate
              allowedRoles={['scientist', 'admin']}
              gateTitle="Scientist Access"
              routeLabel="scientist validation session"
              sessionLabel="Scientist Session"
            >
              <div className="space-y-4">
                <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
                  <CardContent className="grid gap-3 p-4 md:grid-cols-[auto_minmax(0,1fr)] md:items-center">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-emerald-500/20 bg-emerald-500/10">
                      <ShieldCheck className="h-5 w-5 text-emerald-400" />
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-[0.22em] text-foreground">Review Boundary</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Reviews can downgrade, block, or request evidence for a claim. They do not promote SAR, MTS-LSTM, runout, weak-layer, or production-scoring claims without separate release artifacts.
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <ScientistValidationWorkbench gateStatuses={scientistGateStatuses} />
              </div>
            </RoleAccessGate>
          </div>
        </main>
      </div>
    </div>
  );
}
