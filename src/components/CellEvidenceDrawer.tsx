import { useEffect, useMemo, useState } from 'react';
import { FilePlus2, ShieldCheck, Snowflake, Waypoints } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { GridCell } from '@/lib/gridUtils';
import {
  buildCellValidationCaseInput,
  createScientistValidationCase,
  fetchCellEvidenceLinks,
  type CellEvidenceLinks,
} from '@/lib/scientistValidation';

interface Props {
  selectedCell: GridCell | null;
  regionKey?: string | null;
  regionName?: string | null;
  forecastRunId?: string | null;
  forecastGridId?: string | null;
  forecastHour?: number | null;
  modelMetadata?: Record<string, unknown> | null;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
}

function evidenceBadgeTone(value: string | null | undefined): string {
  if (value === 'tree_shap' || value === 'ready' || value === 'available') return 'bg-emerald-500/15 text-emerald-300';
  if (value === 'heuristic_fallback' || value === 'high') return 'bg-amber-500/15 text-amber-300';
  if (value === 'unavailable' || value === 'blocked') return 'bg-red-500/15 text-red-300';
  return 'bg-sky-500/15 text-sky-300';
}

export default function CellEvidenceDrawer({
  selectedCell,
  regionKey,
  regionName,
  forecastRunId,
  forecastGridId,
  forecastHour,
  modelMetadata,
}: Props) {
  const [queueing, setQueueing] = useState(false);
  const [linkedEvidence, setLinkedEvidence] = useState<CellEvidenceLinks>({ outcomes: [], field_reports: [] });
  const [linkedEvidenceStatus, setLinkedEvidenceStatus] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');

  const caseInput = useMemo(() => {
    if (!selectedCell) return null;
    return buildCellValidationCaseInput({
      selectedCell,
      regionKey,
      regionName,
      forecastRunId,
      forecastGridId,
      forecastHour,
      modelMetadata,
    });
  }, [forecastGridId, forecastHour, forecastRunId, modelMetadata, regionKey, regionName, selectedCell]);

  useEffect(() => {
    if (!selectedCell) {
      setLinkedEvidence({ outcomes: [], field_reports: [] });
      setLinkedEvidenceStatus('idle');
      return;
    }
    let cancelled = false;
    setLinkedEvidenceStatus('loading');
    fetchCellEvidenceLinks({
      regionKey,
      forecastRunId,
      forecastGridId,
      cellRow: selectedCell.row,
      cellCol: selectedCell.col,
    })
      .then((links) => {
        if (!cancelled) {
          setLinkedEvidence(links);
          setLinkedEvidenceStatus('loaded');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLinkedEvidence({ outcomes: [], field_reports: [] });
          setLinkedEvidenceStatus('error');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [forecastGridId, forecastRunId, regionKey, selectedCell]);

  const queueCase = async () => {
    if (!caseInput) return;
    setQueueing(true);
    try {
      const created = await createScientistValidationCase({
        ...caseInput,
        evidence: {
          ...caseInput.evidence,
          forecast_outcomes: linkedEvidence.outcomes,
          field_reports: linkedEvidence.field_reports,
          snowpack_proxy: selectedCell?.snowpackProxy ?? null,
        },
      });
      toast.success(`Queued scientist validation case ${created.id.slice(0, 8)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to queue validation case');
    } finally {
      setQueueing(false);
    }
  };

  return (
    <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="flex items-center gap-1.5 text-xs uppercase tracking-[0.24em] text-muted-foreground">
          <ShieldCheck className="h-3 w-3" />
          Cell Evidence
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-3 pt-2">
        {!selectedCell ? (
          <p className="text-xs italic text-muted-foreground">
            Select a forecast cell to inspect validation evidence and queue scientist review.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge className="rounded-full border-0 bg-sky-500/15 text-sky-300">
                r{selectedCell.row} c{selectedCell.col}
              </Badge>
              <Badge className={`rounded-full border-0 ${evidenceBadgeTone(selectedCell.uncertaintyClass)}`}>
                uncertainty {selectedCell.uncertaintyClass ?? 'n/a'}
              </Badge>
              <Badge className={`rounded-full border-0 ${evidenceBadgeTone(selectedCell.explainabilityMode)}`}>
                {selectedCell.explainabilityMode ?? 'explanation n/a'}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
              <div className="text-muted-foreground">Risk score</div>
              <div className="text-right font-mono text-foreground">{selectedCell.riskScore}/5</div>
              <div className="text-muted-foreground">Probability</div>
              <div className="text-right font-mono text-foreground">{formatNumber(selectedCell.probability)}</div>
              <div className="text-muted-foreground">Uncertainty span</div>
              <div className="text-right font-mono text-foreground">{formatNumber(selectedCell.uncertaintySpan)}</div>
              <div className="text-muted-foreground">Dominant driver</div>
              <div className="text-right font-mono text-foreground">{selectedCell.dominantDriverFeature ?? 'n/a'}</div>
              <div className="text-muted-foreground">Runout seed</div>
              <div className="text-right font-mono text-foreground">{selectedCell.runoutSeed ? 'yes' : 'no'}</div>
              <div className="text-muted-foreground">Public mask</div>
              <div className="text-right font-mono text-foreground">
                {selectedCell.publicEligible === false ? 'withheld' : 'eligible'}
              </div>
            </div>

            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground">
              <div className="mb-1 flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em]">
                <Snowflake className="h-3 w-3" />
                Weak-layer proxy
              </div>
              <div>
                Shear strength proxy {formatNumber(selectedCell.snowpackProxy?.estimated_shear_strength)} index · settlement {formatNumber(selectedCell.snowpackProxy?.snow_settlement_index)}
              </div>
              <div className="mt-1">
                This is a proxy signal for review, not completed weak-layer validation.
              </div>
            </div>

            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground">
              <div className="mb-1 flex items-center gap-1.5 font-semibold uppercase tracking-[0.18em]">
                <Waypoints className="h-3 w-3" />
                Linked reality evidence
              </div>
              <div>
                Forecast outcomes {linkedEvidenceStatus === 'loading' ? 'loading' : linkedEvidence.outcomes.length} · field reports {linkedEvidenceStatus === 'loading' ? 'loading' : linkedEvidence.field_reports.length}
              </div>
              <div className="mt-1">{caseInput?.summary}</div>
              {selectedCell.publicMaskReasons?.length ? (
                <div className="mt-1">Mask reasons: {selectedCell.publicMaskReasons.join(', ')}</div>
              ) : null}
              {linkedEvidenceStatus === 'error' ? (
                <div className="mt-1 text-amber-300">Linked evidence lookup unavailable; queue will still include the cell snapshot.</div>
              ) : null}
            </div>

            <Button
              variant="outline"
              size="sm"
              className="h-8 w-full justify-center gap-2 rounded-2xl border-border/70 bg-black/10 text-[10px] uppercase tracking-[0.16em] hover:bg-white/5"
              onClick={queueCase}
              disabled={queueing}
            >
              <FilePlus2 className="h-3.5 w-3.5" />
              {queueing ? 'Queueing...' : 'Queue For Scientist Review'}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
