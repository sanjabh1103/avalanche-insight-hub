import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, BrainCircuit, CheckCircle2, Download, FileCheck2, Flag, RefreshCw, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  EVIDENCE_NEEDED_OPTIONS,
  LABEL_QUALITY_OPTIONS,
  MODEL_ERROR_OPTIONS,
  OFFICIAL_AVALANCHE_PROBLEM_OPTIONS,
  PUBLICATION_REFERENCES,
  TERRAIN_SAR_AMBIGUITY_OPTIONS,
  buildValidationPacket,
  buildValidationSummaryMarkdown,
  buildValidationSummaryPacket,
  createScientistValidationReview,
  fetchScientistValidationActions,
  fetchScientistValidationCases,
  fetchScientistValidationReviews,
  isSyntheticDemoCase,
  optionLabel,
  updateScientistValidationAction,
  type EvidenceNeededNext,
  type LabelQualityVerdict,
  type ModelErrorVerdict,
  type OfficialAvalancheProblem,
  type ScientistValidationCase,
  type ScientistValidationAction,
  type ScientistValidationReview,
  type ScientistValidationVerdict,
  type TerrainSarAmbiguity,
  validationCaseTypeLabel,
  validationStatusLabel,
} from '@/lib/scientistValidation';

interface GateStatus {
  key: string;
  label: string;
  status: 'current' | 'candidate' | 'gated' | 'fallback';
  detail: string;
}

interface Props {
  gateStatuses?: GateStatus[];
}

function statusTone(status: string): string {
  switch (status) {
    case 'reviewed':
    case 'current':
      return 'bg-emerald-500/15 text-emerald-300';
    case 'accepted_limitation':
    case 'candidate':
      return 'bg-sky-500/15 text-sky-300';
    case 'blocked':
    case 'fallback':
      return 'bg-amber-500/15 text-amber-300';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

function downloadText(filename: string, content: string, type = 'application/json;charset=utf-8') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ScientistValidationWorkbench({ gateStatuses = [] }: Props) {
  const [cases, setCases] = useState<ScientistValidationCase[]>([]);
  const [reviews, setReviews] = useState<ScientistValidationReview[]>([]);
  const [actions, setActions] = useState<ScientistValidationAction[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCase, setSelectedCase] = useState<ScientistValidationCase | null>(null);
  const [verdict, setVerdict] = useState<ScientistValidationVerdict>('needs_info');
  const [claimImpact, setClaimImpact] = useState<'no_change' | 'downgrade' | 'block' | 'promote_candidate'>('no_change');
  const [officialAvalancheProblem, setOfficialAvalancheProblem] = useState<OfficialAvalancheProblem>('not_assessed');
  const [labelQualityVerdict, setLabelQualityVerdict] = useState<LabelQualityVerdict>('not_assessed');
  const [modelErrorVerdict, setModelErrorVerdict] = useState<ModelErrorVerdict>('not_assessed');
  const [terrainSarAmbiguity, setTerrainSarAmbiguity] = useState<TerrainSarAmbiguity>('not_assessed');
  const [evidenceNeededNext, setEvidenceNeededNext] = useState<EvidenceNeededNext>('not_assessed');
  const [confidenceRationale, setConfidenceRationale] = useState('');
  const [selectedReferenceIds, setSelectedReferenceIds] = useState<string[]>([]);
  const [notes, setNotes] = useState('');
  const [failureMode, setFailureMode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [updatingActionId, setUpdatingActionId] = useState<string | null>(null);
  const [escalationLog, setEscalationLog] = useState<Array<{ caseId: string; title: string; reason: string; escalatedAt: string }>>([]);

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    try {
      const nextCases = await fetchScientistValidationCases(30);
      const caseIds = nextCases.map((item) => item.id);
      setCases(nextCases);
      setReviews(await fetchScientistValidationReviews(caseIds));
      setActions(await fetchScientistValidationActions(caseIds));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load validation workbench');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkbench();
  }, [loadWorkbench]);

  const reviewsByCase = useMemo(() => {
    const mapping = new Map<string, ScientistValidationReview[]>();
    reviews.forEach((review) => {
      const existing = mapping.get(review.case_id) ?? [];
      existing.push(review);
      mapping.set(review.case_id, existing);
    });
    return mapping;
  }, [reviews]);

  const actionsByCase = useMemo(() => {
    const mapping = new Map<string, ScientistValidationAction[]>();
    actions.forEach((action) => {
      const existing = mapping.get(action.case_id) ?? [];
      existing.push(action);
      mapping.set(action.case_id, existing);
    });
    return mapping;
  }, [actions]);

  const summary = useMemo(() => ({
    pending: cases.filter((item) => item.status === 'pending' || item.status === 'in_review').length,
    reviewed: cases.filter((item) => item.status === 'reviewed').length,
    blocked: cases.filter((item) => item.status === 'blocked').length,
    acceptedLimitations: cases.filter((item) => item.status === 'accepted_limitation').length,
  }), [cases]);

  const drdoPairedComparison = useMemo(() => {
    const reviewedCases = cases.filter((c) => c.status === 'reviewed' || c.status === 'accepted_limitation');
    const disagreements = cases.filter((c) => (c.disagreement_count ?? 0) > 0);
    const modelOverconfident = reviewedCases.filter((c) => {
      const cellRisk = c.cell_snapshot?.riskScore ?? 0;
      const scientistVerdict = reviewsByCase.get(c.id)?.[0]?.verdict;
      return cellRisk >= 4 && scientistVerdict === 'rejected';
    });
    const modelUnderconfident = reviewedCases.filter((c) => {
      const cellRisk = c.cell_snapshot?.riskScore ?? 0;
      const scientistVerdict = reviewsByCase.get(c.id)?.[0]?.verdict;
      return cellRisk <= 2 && scientistVerdict === 'accepted';
    });
    const twoReviewerPending = cases.filter((c) => c.requires_two_reviewers && c.status === 'pending');
    const twoReviewerComplete = cases.filter((c) => c.requires_two_reviewers && (reviewsByCase.get(c.id)?.length ?? 0) >= 2);
    const agreementRate = reviewedCases.length > 0
      ? ((reviewedCases.length - disagreements.filter((c) => reviewedCases.includes(c)).length) / reviewedCases.length * 100).toFixed(0)
      : '—';
    return {
      totalReviewed: reviewedCases.length,
      disagreements: disagreements.length,
      modelOverconfident: modelOverconfident.length,
      modelUnderconfident: modelUnderconfident.length,
      twoReviewerPending: twoReviewerPending.length,
      twoReviewerComplete: twoReviewerComplete.length,
      agreementRate,
    };
  }, [cases, reviewsByCase]);

  const resetReviewForm = () => {
    setNotes('');
    setFailureMode('');
    setVerdict('needs_info');
    setClaimImpact('no_change');
    setOfficialAvalancheProblem('not_assessed');
    setLabelQualityVerdict('not_assessed');
    setModelErrorVerdict('not_assessed');
    setTerrainSarAmbiguity('not_assessed');
    setEvidenceNeededNext('not_assessed');
    setConfidenceRationale('');
    setSelectedReferenceIds([]);
  };

  const toggleReference = (referenceId: string, checked: boolean) => {
    setSelectedReferenceIds((current) => (
      checked
        ? [...new Set([...current, referenceId])]
        : current.filter((item) => item !== referenceId)
    ));
  };

  const updateActionStatus = async (action: ScientistValidationAction, status: ScientistValidationAction['status']) => {
    setUpdatingActionId(action.id);
    try {
      await updateScientistValidationAction(action.id, {
        status,
        resolution_notes: status === 'resolved' ? 'Closed from scientist validation workbench after review.' : null,
      });
      toast.success('Validation action updated');
      await loadWorkbench();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update validation action');
    } finally {
      setUpdatingActionId(null);
    }
  };

  const submitReview = async () => {
    if (!selectedCase) return;
    if (selectedCase.priority >= 4) {
      const missingStructuredFields = [
        officialAvalancheProblem,
        labelQualityVerdict,
        modelErrorVerdict,
        terrainSarAmbiguity,
        evidenceNeededNext,
      ].includes('not_assessed');
      if (missingStructuredFields || confidenceRationale.trim().length < 8) {
        toast.error('Priority 4/5 cases require structured verdict fields and a confidence rationale.');
        return;
      }
    }
    setSubmitting(true);
    try {
      await createScientistValidationReview(selectedCase.id, {
        verdict,
        confidence: 0.75,
        notes,
        failure_mode: failureMode || null,
        claim_impact: claimImpact,
        official_avalanche_problem: officialAvalancheProblem,
        label_quality_verdict: labelQualityVerdict,
        model_error_verdict: modelErrorVerdict,
        terrain_sar_ambiguity: terrainSarAmbiguity,
        evidence_needed_next: evidenceNeededNext,
        confidence_rationale: confidenceRationale,
        evidence_refs: {
          forecast_run_id: selectedCase.forecast_run_id,
          forecast_hour: selectedCase.forecast_hour,
          cell_row: selectedCase.cell_row,
          cell_col: selectedCase.cell_col,
          attached_publications: PUBLICATION_REFERENCES.filter((reference) => selectedReferenceIds.includes(reference.id)),
          linked_evidence_counts: {
            forecast_outcomes: Array.isArray(selectedCase.evidence?.forecast_outcomes) ? selectedCase.evidence.forecast_outcomes.length : 0,
            field_reports: Array.isArray(selectedCase.evidence?.field_reports) ? selectedCase.evidence.field_reports.length : 0,
          },
          snowpack_proxy: selectedCase.evidence?.snowpack_proxy ?? selectedCase.cell_snapshot?.snowpackProxy ?? null,
        },
      });
      toast.success('Scientist validation review saved');
      setSelectedCase(null);
      resetReviewForm();
      await loadWorkbench();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save review');
    } finally {
      setSubmitting(false);
    }
  };

  const exportCase = (caseRow: ScientistValidationCase) => {
    const packet = buildValidationPacket(caseRow, reviewsByCase.get(caseRow.id) ?? []);
    downloadText(`scientist-validation-${caseRow.id}.json`, packet);
  };

  const exportSummaryJson = () => {
    downloadText(
      `scientist-validation-signoff-${new Date().toISOString().slice(0, 10)}.json`,
      buildValidationSummaryPacket(cases, reviews, gateStatuses, actions),
    );
  };

  const exportSummaryMarkdown = () => {
    downloadText(
      `scientist-validation-signoff-${new Date().toISOString().slice(0, 10)}.md`,
      buildValidationSummaryMarkdown(cases, reviews, gateStatuses, actions),
      'text/markdown;charset=utf-8',
    );
  };

  return (
    <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
      <CardHeader className="p-2 pb-1">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-1.5 text-xs uppercase tracking-[0.24em] text-muted-foreground">
            <FileCheck2 className="h-3 w-3" />
            Scientist Validation Workbench
          </CardTitle>
          <Button variant="ghost" size="icon" className="h-7 w-7 rounded-xl" onClick={loadWorkbench} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 p-2 pt-1.5">
        <div className="grid grid-cols-4 gap-1.5 text-[10px]">
          <Metric label="Pending" value={summary.pending} />
          <Metric label="Reviewed" value={summary.reviewed} />
          <Metric label="Blocked" value={summary.blocked} />
          <Metric label="Limits" value={summary.acceptedLimitations} />
        </div>
        <div className="rounded-lg border border-border/60 bg-black/10 px-2 py-1 text-[10px] text-muted-foreground">
          Governed actions: <span className="font-mono text-foreground">{actions.length}</span> · open{' '}
          <span className="font-mono text-foreground">{actions.filter((action) => action.status === 'open' || action.status === 'in_progress').length}</span>
        </div>

        <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-sky-300">
            <BrainCircuit className="h-3 w-3" />
            DRDO Paired Comparison
          </div>
          <div className="grid grid-cols-3 gap-1.5 text-[10px]">
            <div className="rounded-md border border-border/40 bg-black/10 px-2 py-1">
              <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Reviewed</div>
              <div className="font-mono text-sm text-foreground">{drdoPairedComparison.totalReviewed}</div>
            </div>
            <div className="rounded-md border border-border/40 bg-black/10 px-2 py-1">
              <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Agreement</div>
              <div className="font-mono text-sm text-foreground">{drdoPairedComparison.agreementRate}%</div>
            </div>
            <div className="rounded-md border border-border/40 bg-black/10 px-2 py-1">
              <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Disagreements</div>
              <div className="font-mono text-sm text-amber-300">{drdoPairedComparison.disagreements}</div>
            </div>
            <div className="rounded-md border border-border/40 bg-black/10 px-2 py-1">
              <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Model Over</div>
              <div className="font-mono text-sm text-red-300">{drdoPairedComparison.modelOverconfident}</div>
            </div>
            <div className="rounded-md border border-border/40 bg-black/10 px-2 py-1">
              <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Model Under</div>
              <div className="font-mono text-sm text-sky-300">{drdoPairedComparison.modelUnderconfident}</div>
            </div>
            <div className="rounded-md border border-border/40 bg-black/10 px-2 py-1">
              <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">2-Reviewer Done</div>
              <div className="font-mono text-sm text-emerald-300">{drdoPairedComparison.twoReviewerComplete}</div>
            </div>
          </div>
          {drdoPairedComparison.twoReviewerPending > 0 && (
            <div className="mt-1 text-[10px] text-amber-300">
              {drdoPairedComparison.twoReviewerPending} priority 5 case(s) awaiting second reviewer
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border/60 bg-black/10 p-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            <BookOpen className="h-3 w-3" />
            Reference Library
          </div>
          <div className="grid gap-1 sm:grid-cols-2">
            {PUBLICATION_REFERENCES.map((reference) => (
              <div key={reference.id} className="rounded-md border border-border/40 bg-black/10 px-2 py-1 text-[10px]">
                <div className="font-mono text-foreground">{reference.year} · {reference.topic}</div>
                <div className="line-clamp-1 text-muted-foreground">{reference.title}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-1.5">
          <Button variant="outline" size="sm" className="h-8 rounded-xl text-[10px]" onClick={exportSummaryMarkdown} disabled={cases.length === 0}>
            <Download className="mr-1 h-3 w-3" />
            Sign-off MD
          </Button>
          <Button variant="outline" size="sm" className="h-8 rounded-xl text-[10px]" onClick={exportSummaryJson} disabled={cases.length === 0}>
            <Download className="mr-1 h-3 w-3" />
            Sign-off JSON
          </Button>
        </div>

        <div className="rounded-lg border border-border/60 bg-black/10 p-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            <BrainCircuit className="h-3 w-3" />
            Promotion Gates
          </div>
          <div className="space-y-1">
            {gateStatuses.length === 0 ? (
              <div className="text-[10px] text-muted-foreground">No gate summary provided yet</div>
            ) : gateStatuses.map((gate) => (
              <div key={gate.key} className="flex items-start justify-between gap-2 text-[10px]">
                <div className="min-w-0">
                  <div className="font-mono text-foreground">{gate.label}</div>
                  <div className="line-clamp-1 text-muted-foreground">{gate.detail}</div>
                </div>
                <Badge className={`shrink-0 rounded-full border-0 text-[9px] ${statusTone(gate.status)}`}>
                  {gate.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-1 max-h-60 overflow-y-auto pr-1">
          {cases.length === 0 ? (
            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-xs text-muted-foreground">
              No scientist validation cases yet. Use the expert cell evidence drawer or backend case-pack generator to seed review cases.
            </div>
          ) : cases.map((caseRow) => {
            const caseReviews = reviewsByCase.get(caseRow.id) ?? [];
            const caseActions = actionsByCase.get(caseRow.id) ?? [];
            const syntheticDemo = isSyntheticDemoCase(caseRow);
            return (
              <div key={caseRow.id} className="rounded-lg border border-border/60 bg-black/10 px-2 py-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="line-clamp-1 text-[11px] font-semibold text-foreground">{caseRow.title}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {validationCaseTypeLabel(caseRow.case_type)} · p{caseRow.priority} · {caseRow.region_name ?? 'region n/a'}
                    </div>
                  </div>
                  <Badge className={`shrink-0 rounded-full border-0 text-[9px] ${statusTone(caseRow.status)}`}>
                    {validationStatusLabel(caseRow.status)}
                  </Badge>
                </div>
                <div className="mt-1 text-[10px] text-muted-foreground">
                  {caseRow.forecast_run_id ? `Run ${caseRow.forecast_run_id}` : 'No run id'} · h{caseRow.forecast_hour ?? 'n/a'} · r{caseRow.cell_row ?? 'n/a'} c{caseRow.cell_col ?? 'n/a'}
                </div>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <span className="text-[10px] text-muted-foreground">
                    {caseReviews.length} review(s) · {caseActions.length} action(s)
                  </span>
                  <div className="flex items-center gap-1">
                    {caseRow.requires_two_reviewers ? (
                      <Badge variant="outline" className="rounded-full text-[9px]">
                        2 reviewers
                      </Badge>
                    ) : null}
                    {syntheticDemo ? (
                      <Badge className="rounded-full border-0 bg-purple-500/15 text-[9px] text-purple-200">
                        synthetic demo
                      </Badge>
                    ) : null}
                    {(caseRow.disagreement_count ?? 0) > 0 ? (
                      <Badge className="rounded-full border-0 bg-amber-500/15 text-[9px] text-amber-300">
                        {caseRow.disagreement_count} disagreement
                      </Badge>
                    ) : null}
                    <Button variant="ghost" size="sm" className="h-7 rounded-xl px-2 text-[10px]" onClick={() => exportCase(caseRow)}>
                      <Download className="mr-1 h-3 w-3" />
                      Export
                    </Button>
                    <Button variant="outline" size="sm" className="h-7 rounded-xl px-2 text-[10px]" onClick={() => {
                      resetReviewForm();
                      setSelectedCase(caseRow);
                    }}>
                      Review
                    </Button>
                    {(caseRow.disagreement_count ?? 0) > 0 && (
                      <Button
                        variant="destructive"
                        size="sm"
                        className="h-7 rounded-xl px-2 text-[10px]"
                        data-testid={`escalate-btn-${caseRow.id}`}
                        onClick={() => {
                          const reason = prompt('Escalation reason (required for SLA routing):');
                          if (reason && reason.trim()) {
                            const entry = {
                              caseId: caseRow.id,
                              title: caseRow.title,
                              reason: reason.trim(),
                              escalatedAt: new Date().toISOString(),
                            };
                            setEscalationLog((prev) => [entry, ...prev]);
                            toast.success(`Case "${caseRow.title}" escalated to Senior Admin for SLA routing.`);
                          }
                        }}
                      >
                        <Flag className="mr-1 h-3 w-3" />
                        Escalate
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="rounded-lg border border-border/60 bg-black/10 p-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            <CheckCircle2 className="h-3 w-3" />
            Action Closure Queue
          </div>
          {actions.length === 0 ? (
            <div className="text-[10px] text-muted-foreground">No governed actions yet.</div>
          ) : (
            <div className="space-y-1">
              {actions.slice(0, 6).map((action) => (
                <div key={action.id} className="grid gap-1 rounded-md border border-border/40 bg-black/10 px-2 py-1 text-[10px] sm:grid-cols-[minmax(0,1fr)_120px] sm:items-center">
                  <div className="min-w-0">
                    <div className="line-clamp-1 font-mono text-foreground">{action.action_type} · p{action.priority} · {action.owner_role}</div>
                    <div className="line-clamp-1 text-muted-foreground">{action.summary}</div>
                  </div>
                  <Select
                    value={action.status}
                    onValueChange={(value) => updateActionStatus(action, value as ScientistValidationAction['status'])}
                    disabled={updatingActionId === action.id}
                  >
                    <SelectTrigger className="h-7 text-[10px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="open">Open</SelectItem>
                      <SelectItem value="in_progress">In progress</SelectItem>
                      <SelectItem value="resolved">Resolved</SelectItem>
                      <SelectItem value="rejected">Rejected</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          )}
        </div>

        {escalationLog.length > 0 && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-2">
            <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] text-red-300">
              <Flag className="h-3 w-3" />
              Escalation Log ({escalationLog.length})
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {escalationLog.map((entry, idx) => (
                <div key={`${entry.caseId}-${idx}`} className="rounded-md border border-red-500/20 bg-black/10 px-2 py-1 text-[10px]">
                  <div className="font-mono text-red-200">{entry.title}</div>
                  <div className="text-muted-foreground">
                    Reason: {entry.reason} · {new Date(entry.escalatedAt).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>

      <Dialog open={Boolean(selectedCase)} onOpenChange={(open) => {
        if (!open) {
          setSelectedCase(null);
          resetReviewForm();
        }
      }}>
        <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto border-border bg-card">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-foreground">
              <ShieldAlert className="h-4 w-4 text-amber-300" />
              Scientist Review
            </DialogTitle>
            <DialogDescription>{selectedCase?.title}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Verdict</Label>
                <Select value={verdict} onValueChange={(value) => setVerdict(value as ScientistValidationVerdict)}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="accepted">Accepted</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                    <SelectItem value="needs_info">Needs info</SelectItem>
                    <SelectItem value="accepted_limitation">Accepted limitation</SelectItem>
                    <SelectItem value="blocked">Blocked</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Claim impact</Label>
                <Select value={claimImpact} onValueChange={(value) => setClaimImpact(value as typeof claimImpact)}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="no_change">No change</SelectItem>
                    <SelectItem value="downgrade">Downgrade</SelectItem>
                    <SelectItem value="block">Block</SelectItem>
                    <SelectItem value="promote_candidate">Promote candidate</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <ReviewSelect
                label="EAWS problem"
                value={officialAvalancheProblem}
                options={OFFICIAL_AVALANCHE_PROBLEM_OPTIONS}
                onChange={(value) => setOfficialAvalancheProblem(value as OfficialAvalancheProblem)}
              />
              <ReviewSelect
                label="Label quality"
                value={labelQualityVerdict}
                options={LABEL_QUALITY_OPTIONS}
                onChange={(value) => setLabelQualityVerdict(value as LabelQualityVerdict)}
              />
              <ReviewSelect
                label="Model error"
                value={modelErrorVerdict}
                options={MODEL_ERROR_OPTIONS}
                onChange={(value) => setModelErrorVerdict(value as ModelErrorVerdict)}
              />
              <ReviewSelect
                label="Terrain/SAR ambiguity"
                value={terrainSarAmbiguity}
                options={TERRAIN_SAR_AMBIGUITY_OPTIONS}
                onChange={(value) => setTerrainSarAmbiguity(value as TerrainSarAmbiguity)}
              />
            </div>
            <ReviewSelect
              label="Evidence needed next"
              value={evidenceNeededNext}
              options={EVIDENCE_NEEDED_OPTIONS}
              onChange={(value) => setEvidenceNeededNext(value as EvidenceNeededNext)}
            />
            <div className="rounded-lg border border-border/60 bg-black/10 p-2">
              <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                <BookOpen className="h-3 w-3" />
                Attach References
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {PUBLICATION_REFERENCES.map((reference) => (
                  <label key={reference.id} className="flex items-start gap-2 rounded-md border border-border/40 bg-black/10 p-2 text-[10px]">
                    <Checkbox
                      checked={selectedReferenceIds.includes(reference.id)}
                      onCheckedChange={(checked) => toggleReference(reference.id, checked === true)}
                    />
                    <span>
                      <span className="block font-mono text-foreground">{reference.year} · {reference.topic}</span>
                      <span className="block text-muted-foreground">{reference.evidence_note}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground">
              Claim boundary{' '}
              <span className="font-mono text-foreground">
                {selectedCase?.claim_boundary ?? 'n/a'}
              </span>
              {selectedCase && isSyntheticDemoCase(selectedCase) ? (
                <span className="ml-1 text-purple-200">
                  · synthetic demo only, excluded from training/public promotion
                </span>
              ) : null}
            </div>
            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground">
              Linked evidence: forecast outcomes{' '}
              <span className="font-mono text-foreground">
                {Array.isArray(selectedCase?.evidence?.forecast_outcomes) ? selectedCase.evidence.forecast_outcomes.length : 0}
              </span>{' '}
              · field reports{' '}
              <span className="font-mono text-foreground">
                {Array.isArray(selectedCase?.evidence?.field_reports) ? selectedCase.evidence.field_reports.length : 0}
              </span>{' '}
              · snowpack proxy{' '}
              <span className="font-mono text-foreground">
                {selectedCase?.evidence?.snowpack_proxy || selectedCase?.cell_snapshot?.snowpackProxy ? 'available' : 'n/a'}
              </span>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Failure mode</Label>
              <Textarea value={failureMode} onChange={(event) => setFailureMode(event.target.value)} placeholder="weak layer, runout mismatch, SAR coverage gap, false alarm..." />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Confidence rationale</Label>
              <Textarea
                value={confidenceRationale}
                onChange={(event) => setConfidenceRationale(event.target.value)}
                placeholder="Explain why this review is confident enough, or what uncertainty remains."
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes</Label>
              <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Capture scientist reasoning and next evidence needed." />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setSelectedCase(null)} disabled={submitting}>Cancel</Button>
              <Button onClick={submitReview} disabled={submitting}>{submitting ? 'Saving...' : 'Save Review'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border/60 bg-black/10 px-2 py-1">
      <div className="text-[9px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="font-mono text-sm text-foreground">{value}</div>
    </div>
  );
}

function ReviewSelect<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-9">
          <SelectValue>{optionLabel(options, value)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
