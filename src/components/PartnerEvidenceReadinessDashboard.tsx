import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ClipboardCheck, Database, Gauge, ShieldCheck, TriangleAlert } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { REQUIRED_PARTNER_EVIDENCE_FILES } from '@/lib/partnerEvidenceReadiness';
import { getDefaultFeatureFlags } from '@/lib/featureFlags';

const readinessGates = [
  {
    label: 'Source governance',
    status: 'template ready',
    detail: 'Partner manifest and SHA-256 refs are required before evidence can be trusted.',
  },
  {
    label: 'Station X/Y/Z',
    status: 'partner pending',
    detail: 'GPxyz and uncertainty maps remain blocked until reviewed latitude, longitude, and elevation coverage exists.',
  },
  {
    label: 'D_tidy labels',
    status: 'partner pending',
    detail: 'Raw bulletins are context only; reviewed labels need source, basis, regime, timing, and notes.',
  },
  {
    label: 'Local holdout',
    status: 'blocked',
    detail: 'No Himalayan release claim until a leakage-checked independent holdout and named release attestation pass.',
  },
];

function statusTone(status: string) {
  if (status === 'template ready') return 'bg-sky-500/15 text-sky-300';
  if (status === 'partner pending') return 'bg-amber-500/15 text-amber-300';
  return 'bg-red-500/15 text-red-200';
}

export default function PartnerEvidenceReadinessDashboard() {
  const { partnerIntake: partnerIntakeEnabled } = useMemo(() => getDefaultFeatureFlags(), []);
  return (
    <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
      <CardHeader className="p-4 pb-2">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em]">
              <Database className="h-4 w-4 text-emerald-400" />
              Himalayan Evidence Readiness
            </CardTitle>
            <div className="mt-1 text-xs text-muted-foreground">
              Compact status for partner intake, scientist review, uncertainty, and claim locks before real client data arrives.
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm" className="rounded-xl text-[11px]">
              <Link to="/scientist/daily-verification">
                <ClipboardCheck className="mr-2 h-3.5 w-3.5" />
                Daily verification
              </Link>
            </Button>
            {partnerIntakeEnabled ? (
              <Button asChild size="sm" className="rounded-xl bg-emerald-500 text-[11px] text-black hover:bg-emerald-400">
                <Link to="/scientist/partner-intake">
                  Partner intake
                  <ArrowRight className="ml-2 h-3.5 w-3.5" />
                </Link>
              </Button>
            ) : (
              <Badge variant="outline" className="rounded-xl px-3 py-2 text-[10px]">
                Partner intake UI flag off
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-2">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {readinessGates.map((gate) => (
            <div key={gate.label} className="rounded-xl border border-border/60 bg-black/10 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-foreground">{gate.label}</div>
                  <div className="mt-1 text-[10px] text-muted-foreground">{gate.detail}</div>
                </div>
                <Badge className={`shrink-0 rounded-full border-0 text-[9px] ${statusTone(gate.status)}`}>
                  {gate.status}
                </Badge>
              </div>
            </div>
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="rounded-xl border border-border/60 bg-black/10 p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5" />
              Evidence groups
            </div>
            <div className="max-h-64 space-y-1 overflow-y-auto pr-1">
              {REQUIRED_PARTNER_EVIDENCE_FILES.map((item) => (
                <div key={item.key} className="grid gap-1 rounded-lg border border-border/40 bg-black/10 px-2 py-1.5 text-[10px] md:grid-cols-[160px_minmax(0,1fr)_90px] md:items-center">
                  <div className="font-mono text-foreground">{item.filename}</div>
                  <div className="min-w-0">
                    <div className="font-semibold text-foreground">{item.label}</div>
                    <div className="line-clamp-1 text-muted-foreground">{item.owner} · {item.nextAction}</div>
                  </div>
                  <Badge variant="outline" className="justify-center rounded-full text-[9px]">
                    UI {item.uiToday}
                  </Badge>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div className="rounded-xl border border-border/60 bg-black/10 p-3">
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                <Gauge className="h-3.5 w-3.5" />
                Uncertainty readiness
              </div>
              <div className="space-y-2 text-[10px] text-muted-foreground">
                <div><span className="font-mono text-foreground">Calibration:</span> pending local reviewed labels and holdout rows.</div>
                <div><span className="font-mono text-foreground">GPxyz:</span> blocked until station X/Y/Z coverage passes.</div>
                <div><span className="font-mono text-foreground">SAR:</span> shadow-only; scene transfer and fresh-final gates remain blocked.</div>
              </div>
            </div>
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3">
              <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-amber-200">
                <TriangleAlert className="h-3.5 w-3.5" />
                Live geography boundary
              </div>
              <div className="text-[10px] text-muted-foreground">
                Colorado Rockies remains the live technical proof region. Himalayan readiness is evidence intake and review only until local data, holdout metrics, and release-gate attestation pass.
              </div>
              <div className="mt-2 font-mono text-[10px] text-foreground">
                production_scoring_allowed=false<br />
                himalayan_accuracy_claim_allowed=false
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
