import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ClipboardCheck, Download, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import RoleAccessGate from '@/components/RoleAccessGate';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  OFFICIAL_AVALANCHE_PROBLEM_OPTIONS,
  buildDailyVerificationAnalytics,
  buildDailyVerificationExport,
  createDailyVerification,
  fetchDailyVerifications,
  type DailyVerificationDangerLevel,
  type DailyVerificationRecord,
  type OfficialAvalancheProblem,
} from '@/lib/scientistValidation';

const DANGER_LEVELS: Array<{ value: DailyVerificationDangerLevel; label: string }> = [
  { value: '1', label: '1 Low' },
  { value: '2', label: '2 Moderate' },
  { value: '3', label: '3 Considerable' },
  { value: '4', label: '4 High' },
  { value: '5', label: '5 Very high' },
  { value: 'not_assessed', label: 'Not assessed' },
];

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function formatRate(value: number | null): string {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`;
}

export default function ScientistDailyVerificationPage() {
  return (
    <div className="min-h-screen bg-background px-4 py-4 text-foreground sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-4">
        <header className="flex flex-col gap-3 rounded-[1.5rem] border border-border/70 bg-card/70 p-4 shadow-2xl shadow-black/20 backdrop-blur-2xl sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold uppercase tracking-[0.18em]">Daily Verification</div>
            <div className="text-xs text-muted-foreground">Paired scientist-vs-model comparison evidence</div>
          </div>
          <Button asChild variant="outline" className="rounded-2xl">
            <Link to="/scientist">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Scientist queue
            </Link>
          </Button>
        </header>
        <RoleAccessGate
          allowedRoles={['scientist', 'admin']}
          gateTitle="Scientist Access"
          routeLabel="daily verification session"
          sessionLabel="Scientist Session"
        >
          <DailyVerificationWorkbench />
        </RoleAccessGate>
      </div>
    </div>
  );
}

function DailyVerificationWorkbench() {
  const [records, setRecords] = useState<DailyVerificationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [regionKey, setRegionKey] = useState('himalayas_nepal');
  const [regionName, setRegionName] = useState('Himalayas Nepal');
  const [verificationDate, setVerificationDate] = useState(todayIsoDate());
  const [forecastRunId, setForecastRunId] = useState('');
  const [forecastGridId, setForecastGridId] = useState('');
  const [forecastHour, setForecastHour] = useState('12');
  const [scientistDangerLevel, setScientistDangerLevel] = useState<DailyVerificationDangerLevel>('not_assessed');
  const [modelDangerLevel, setModelDangerLevel] = useState<DailyVerificationDangerLevel>('not_assessed');
  const [officialProblem, setOfficialProblem] = useState<OfficialAvalancheProblem>('not_assessed');
  const [modelProblem, setModelProblem] = useState<OfficialAvalancheProblem>('not_assessed');
  const [observedOutcome, setObservedOutcome] = useState<'event_observed' | 'no_event_observed' | 'unknown'>('unknown');
  const [notes, setNotes] = useState('');
  const analytics = useMemo(() => buildDailyVerificationAnalytics(records), [records]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      setRecords(await fetchDailyVerifications(30));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load daily verifications');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const submit = async () => {
    if (scientistDangerLevel === 'not_assessed' || modelDangerLevel === 'not_assessed') {
      toast.error('Scientist and model danger levels are required for paired verification.');
      return;
    }
    setSubmitting(true);
    try {
      await createDailyVerification({
        region_key: regionKey || null,
        region_name: regionName || null,
        verification_date: verificationDate,
        forecast_run_id: forecastRunId || null,
        forecast_grid_id: forecastGridId || null,
        forecast_hour: forecastHour ? Number(forecastHour) : null,
        scientist_danger_level: scientistDangerLevel,
        model_danger_level: modelDangerLevel,
        observed_outcome: observedOutcome,
        official_avalanche_problem: officialProblem,
        model_avalanche_problem: modelProblem,
        notes: notes || null,
        evidence_refs: {
          claim_boundary: 'paired_verification_not_public_promotion',
        },
      });
      toast.success('Daily verification saved');
      setNotes('');
      await loadRecords();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save daily verification');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm uppercase tracking-[0.18em]">
            <ClipboardCheck className="h-4 w-4" />
            Paired Input
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <Field label="Region key" value={regionKey} onChange={setRegionKey} />
          <Field label="Region name" value={regionName} onChange={setRegionName} />
          <Field label="Verification date" value={verificationDate} onChange={setVerificationDate} type="date" />
          <Field label="Forecast hour" value={forecastHour} onChange={setForecastHour} type="number" />
          <Field label="Forecast run id" value={forecastRunId} onChange={setForecastRunId} />
          <Field label="Forecast grid id" value={forecastGridId} onChange={setForecastGridId} />
          <SelectField label="Scientist danger level" value={scientistDangerLevel} options={DANGER_LEVELS} onChange={(value) => setScientistDangerLevel(value as DailyVerificationDangerLevel)} />
          <SelectField label="Model danger level" value={modelDangerLevel} options={DANGER_LEVELS} onChange={(value) => setModelDangerLevel(value as DailyVerificationDangerLevel)} />
          <SelectField label="Scientist EAWS problem" value={officialProblem} options={OFFICIAL_AVALANCHE_PROBLEM_OPTIONS} onChange={(value) => setOfficialProblem(value as OfficialAvalancheProblem)} />
          <SelectField label="Model EAWS problem" value={modelProblem} options={OFFICIAL_AVALANCHE_PROBLEM_OPTIONS} onChange={(value) => setModelProblem(value as OfficialAvalancheProblem)} />
          <div className="space-y-1 sm:col-span-2">
            <Label className="text-xs">Observed outcome</Label>
            <Select value={observedOutcome} onValueChange={(value) => setObservedOutcome(value as typeof observedOutcome)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="unknown">Unknown</SelectItem>
                <SelectItem value="event_observed">Event observed</SelectItem>
                <SelectItem value="no_event_observed">No event observed</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label className="text-xs">Notes</Label>
            <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Record scientist reasoning, model disagreement, and next evidence needed." />
          </div>
          <Button className="sm:col-span-2" onClick={submit} disabled={submitting}>
            {submitting ? 'Saving...' : 'Save Paired Verification'}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="text-sm uppercase tracking-[0.18em]">Analytics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <Metric label="Records" value={analytics.record_count} />
              <Metric label="Assessable pairs" value={analytics.assessable_danger_pair_count} />
              <Metric label="Danger agreement" value={formatRate(analytics.exact_danger_match_rate)} />
              <Metric label="Disagreements" value={analytics.danger_disagreement_count} />
              <Metric label="Outcome-linked" value={analytics.outcome_linked_pair_count} />
              <Metric label="False-alarm candidates" value={analytics.false_alarm_candidate_count} />
              <Metric label="Miss candidates" value={analytics.miss_candidate_count} />
              <Metric label="High-danger recall proxy" value={formatRate(analytics.high_danger_recall_proxy)} />
              <Metric label="Unknown outcomes" value={analytics.unknown_outcome_count} />
            </div>
            <MatrixSummary title="Danger confusion matrix" matrix={analytics.danger_level_confusion_matrix} />
            <MatrixSummary title="EAWS problem confusion matrix" matrix={analytics.avalanche_problem_confusion_matrix} />
            <div className="rounded-lg border border-border/60 bg-black/10 p-2">
              <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Observed outcomes</div>
              <div className="space-y-1 text-[10px] font-mono text-foreground">
                {Object.entries(analytics.observed_outcome_distribution).length === 0 ? (
                  <div className="text-muted-foreground">No outcome records</div>
                ) : Object.entries(analytics.observed_outcome_distribution).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2">
                    <span>{key}</span>
                    <span>{value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-border/60 bg-black/10 p-2 text-[10px] text-muted-foreground">
              {analytics.claim_boundary}
            </div>
            <div className="rounded-lg border border-border/60 bg-black/10 p-2">
              <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Disagreement queue</div>
              <div className="max-h-24 space-y-1 overflow-y-auto text-[10px] font-mono text-foreground">
                {analytics.disagreement_queue.length === 0 ? (
                  <div className="text-muted-foreground">No assessable scientist/model danger disagreements</div>
                ) : analytics.disagreement_queue.slice(0, 6).map((item) => (
                  <div key={item.id} className="flex justify-between gap-2">
                    <span className="truncate">{item.verification_date} · {item.region}</span>
                    <span>s{item.scientist_danger_level}/m{item.model_danger_level} · {item.observed_outcome}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-border/70 bg-card/60 backdrop-blur-xl">
          <CardHeader className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm uppercase tracking-[0.18em]">Recent Pairs</CardTitle>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={loadRecords} disabled={loading}>
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
            <Button variant="outline" size="sm" onClick={() => downloadText(`daily-verification-${todayIsoDate()}.json`, buildDailyVerificationExport(records))} disabled={records.length === 0}>
              <Download className="mr-2 h-4 w-4" />
              Export pairs
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {records.length === 0 ? (
              <div className="rounded-lg border border-border/60 bg-black/10 p-3 text-xs text-muted-foreground">
                No paired daily verification records yet.
              </div>
            ) : records.map((record) => (
              <div key={record.id} className="rounded-lg border border-border/60 bg-black/10 p-2 text-xs">
                <div className="font-mono text-foreground">{record.verification_date} · {record.region_name ?? record.region_key ?? 'region n/a'}</div>
                <div className="text-muted-foreground">Scientist {record.scientist_danger_level} · model {record.model_danger_level} · {record.observed_outcome}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-black/10 p-2">
      <div className="text-[9px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="font-mono text-sm text-foreground">{value}</div>
    </div>
  );
}

function MatrixSummary({ title, matrix }: { title: string; matrix: Record<string, Record<string, number>> }) {
  const rows = Object.entries(matrix);
  return (
    <div className="rounded-lg border border-border/60 bg-black/10 p-2">
      <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{title}</div>
      <div className="max-h-24 space-y-1 overflow-y-auto text-[10px] font-mono text-foreground">
        {rows.length === 0 ? (
          <div className="text-muted-foreground">No paired records</div>
        ) : rows.map(([scientistValue, modelValues]) => (
          <div key={scientistValue} className="break-words">
            {scientistValue}: {Object.entries(modelValues).map(([modelValue, count]) => `${modelValue}=${count}`).join(', ')}
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function SelectField<T extends string>({
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
        <SelectTrigger><SelectValue /></SelectTrigger>
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
